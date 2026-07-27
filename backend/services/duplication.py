"""
Duplicate code detection via the Winnowing algorithm.

Pipeline:
    1. Parse each file with Python's `ast` and emit a *normalized* token
       stream. Identifiers and literals are replaced with generic tokens so
       that renamed / re-formatted copies still match (structural fingerprint).
    2. Build overlapping k-grams over the token stream and hash each one.
    3. Run Winnowing over the hash sequence to select a robust, position-
       preserving subset of fingerprints per file.
    4. Compare files pairwise via Jaccard similarity of their fingerprint sets
       and map shared fingerprints back to source line ranges.

Reference:
    S. Schleimer, D. S. Wilkerson, A. Aiken, "Winnowing: Local Algorithms for
    Document Fingerprinting", SIGMOD 2003.
"""

import ast
import hashlib
from typing import Dict, List, Optional, Tuple

# k-gram size (in normalized tokens) and Winnowing window size.
# Guarantee: any shared substring of >= (K + W - 1) tokens is detected.
# A larger k-gram avoids matching short, ubiquitous Python idioms.
K_GRAM = 9
WINDOW = 5

# Minimum similarity (%) for a file pair to be reported.
MIN_PAIR_SIMILARITY = 10.0

# Structural AST nodes that carry no duplication signal (expression contexts,
# module/argument wrappers). Emitting them floods the stream with noise.
_SKIP_NODES = (ast.expr_context, ast.Module, ast.arguments, ast.alias, ast.Load, ast.Store)


# ---------------------------------------------------------------------------
# 1. AST normalization → token stream
# ---------------------------------------------------------------------------

def _normalize_tokens(source: str) -> List[Tuple[str, int]]:
    """
    Walk the AST in pre-order and emit (token, lineno) pairs.

    Identifiers (`Name`, function args) collapse to ``ID`` and constants to
    ``LIT:<type>`` so that copies differing only in names/values still match,
    while control-flow and operators keep their structure.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    tokens: List[Tuple[str, int]] = []

    def visit(node: ast.AST, parent_line: int) -> None:
        lineno = getattr(node, "lineno", parent_line)
        if not isinstance(node, _SKIP_NODES):
            tokens.append((_token_for(node), lineno))
        for child in ast.iter_child_nodes(node):
            visit(child, lineno)

    visit(tree, 1)
    return tokens


def _token_for(node: ast.AST) -> str:
    if isinstance(node, (ast.Name, ast.arg)):
        return "ID"
    if isinstance(node, ast.Attribute):
        return "ATTR"
    if isinstance(node, ast.Constant):
        return f"LIT:{type(node.value).__name__}"
    # Everything else (statements, operators, comprehensions, ...) is kept as
    # its node type, which is exactly the structural signal we want.
    return type(node).__name__


# ---------------------------------------------------------------------------
# 2. k-grams + hashing
# ---------------------------------------------------------------------------

def _hash_kgrams(tokens: List[Tuple[str, int]]) -> List[Tuple[int, int, int]]:
    """
    Produce (hash, start_line, end_line) for each k-gram window of tokens.
    """
    grams: List[Tuple[int, int, int]] = []
    n = len(tokens)
    for i in range(n - K_GRAM + 1):
        window = tokens[i : i + K_GRAM]
        text = "|".join(t for t, _ in window)
        digest = hashlib.md5(text.encode("utf-8")).hexdigest()
        value = int(digest[:16], 16)
        lines = [ln for _, ln in window]
        grams.append((value, min(lines), max(lines)))
    return grams


# ---------------------------------------------------------------------------
# 3. Winnowing
# ---------------------------------------------------------------------------

def _winnow(grams: List[Tuple[int, int, int]]) -> Dict[int, List[Tuple[int, int]]]:
    """
    Select fingerprints from the k-gram hashes using Winnowing.

    Returns a mapping ``hash -> list of (start_line, end_line)`` for the
    selected fingerprints of a single file.
    """
    fingerprints: Dict[int, List[Tuple[int, int]]] = {}
    n = len(grams)
    if n == 0:
        return fingerprints

    def record(gram: Tuple[int, int, int]) -> None:
        value, start, end = gram
        fingerprints.setdefault(value, []).append((start, end))

    if n < WINDOW:
        # Not enough hashes for a full window: keep the global minimum.
        record(min(grams, key=lambda g: g[0]))
        return fingerprints

    last_selected = -1
    for i in range(n - WINDOW + 1):
        # rightmost-minimum within the window (standard robust winnowing)
        min_idx = i
        for j in range(i, i + WINDOW):
            if grams[j][0] <= grams[min_idx][0]:
                min_idx = j
        if min_idx != last_selected:
            record(grams[min_idx])
            last_selected = min_idx
    return fingerprints


def fingerprint_file(source: str) -> Dict[int, List[Tuple[int, int]]]:
    """Full pipeline for one file: normalize → k-gram → winnow."""
    return _winnow(_hash_kgrams(_normalize_tokens(source)))


# ---------------------------------------------------------------------------
# 4. Pairwise comparison + repository aggregation
# ---------------------------------------------------------------------------

def _merge_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Merge overlapping/adjacent (start, end) line ranges."""
    if not ranges:
        return []
    ordered = sorted(ranges)
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def _count_lines(ranges: List[Tuple[int, int]]) -> int:
    return sum(end - start + 1 for start, end in ranges)


def _blocks_with_code(source: str, ranges: List[Tuple[int, int]]) -> List[Dict]:
    """Attach the actual source text to each (1-indexed) line range."""
    lines = source.splitlines()
    blocks = []
    for start, end in ranges:
        snippet = "\n".join(lines[start - 1 : end])
        blocks.append({"start": start, "end": end, "code": snippet})
    return blocks


def analyze(
    file_sources: List[Tuple[str, str]],
    loc_by_file: Optional[Dict[str, int]] = None,
) -> Dict:
    """
    Detect duplication across a set of ``(file_path, source)`` pairs.

    Returns duplicate file pairs (with similarity % and merged duplicate line
    ranges per file) and the overall repository duplication percentage.
    """
    loc_by_file = loc_by_file or {}
    prints = {fp: fingerprint_file(src) for fp, src in file_sources}
    src_by_path = {fp: src for fp, src in file_sources}
    paths = [fp for fp, _ in file_sources]

    pairs: List[Dict] = []
    # duplicated line ranges accumulated per file across every matching pair
    dup_ranges: Dict[str, List[Tuple[int, int]]] = {fp: [] for fp in paths}

    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            a, b = paths[i], paths[j]
            fa, fb = prints[a], prints[b]
            if not fa or not fb:
                continue

            shared = set(fa) & set(fb)
            union = set(fa) | set(fb)
            if not shared:
                continue
            similarity = round(len(shared) / len(union) * 100, 1)
            if similarity < MIN_PAIR_SIMILARITY:
                continue

            blocks_a = _merge_ranges([r for h in shared for r in fa[h]])
            blocks_b = _merge_ranges([r for h in shared for r in fb[h]])
            dup_ranges[a].extend(blocks_a)
            dup_ranges[b].extend(blocks_b)

            pairs.append(
                {
                    "file_a": a,
                    "file_b": b,
                    "similarity": similarity,
                    "blocks_a": _blocks_with_code(src_by_path[a], blocks_a),
                    "blocks_b": _blocks_with_code(src_by_path[b], blocks_b),
                    "shared_fingerprints": len(shared),
                }
            )

    pairs.sort(key=lambda p: p["similarity"], reverse=True)

    total_loc = sum(loc_by_file.get(fp, 0) for fp in paths)
    duplicated_loc = 0
    for fp in paths:
        merged = _merge_ranges(dup_ranges[fp])
        # never count more duplicated lines than the file actually has
        duplicated_loc += min(_count_lines(merged), loc_by_file.get(fp, _count_lines(merged)))

    duplication_percentage = round(duplicated_loc / total_loc * 100, 1) if total_loc else 0.0

    return {
        "duplicate_pairs": pairs,
        "duplication_percentage": duplication_percentage,
        "duplicated_lines": duplicated_loc,
        "total_lines": total_loc,
        "pair_count": len(pairs),
    }
