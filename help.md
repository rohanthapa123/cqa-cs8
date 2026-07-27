# Code Analyzer — Algorithms Guide (`help.md`)

How each analysis algorithm works, what values it takes, and exactly where it lives in the code.

## Pipeline overview

1. User selects a GitHub repo → `POST /analyze` (`backend/routers/analyze.py`).
2. `analyze_repository()` clones the repo (shallow, `depth=1`), verifies it's a Python project, reads every `.py` file once, then runs the three core modules + bad-practices.
3. Results are combined into a repository **health score** and returned as `AnalyzeResponse`.

**Orchestrator:** `backend/services/analysis.py` → `analyze_repository()` (line 144)
**Per-file helpers:** `clone_repo()` (l.32), `is_python_project()`, `collect_python_files()`, `file_stats()` (l.68).

---

## 1. Cyclomatic Complexity (McCabe)

**File:** `backend/services/complexity.py`

### How it works
Each file's source is parsed into an Abstract Syntax Tree and the number of **decision points** (branches) in every function is counted. Complexity starts at 1 (the base path) and increases by 1 for each `if`, `for`, `while`, boolean operator, `except`, etc. This is done by radon's `cc_visit()` (`from radon.complexity import cc_visit`, l.15).

- Per function → a complexity score.
- Per file → average, total, and max of its functions.
- Per repository → overall average and a list of **high-risk** functions.

A function is flagged **high-risk** when its score exceeds `HIGH_RISK_THRESHOLD = 10` (l.19).

### Values it takes / produces
- `analyze_file(file_path: str, source: str)` (l.22) → `{ functions[], average_complexity, total_complexity, max_complexity, function_count }`; each function is `{ name, complexity, lineno, is_high_risk }`.
- `summarize(file_reports)` (l.59) → `{ average_complexity, total_complexity, function_count, high_risk_functions[], distribution }` where `distribution` buckets functions into `low (≤5)`, `moderate (6–10)`, `high (>10)`.

### Formula
- Graph form: `M = E − N + 2P` (E = edges, N = nodes, P = connected components).
- AST form used here: `M = D + 1` (D = decision points).

---

## 2. Duplicate Detection — Winnowing

**File:** `backend/services/duplication.py`

### How it works
1. **AST normalization** — `_normalize_tokens()` (l.41) parses the file and emits a token per AST node, replacing identifiers with `ID`, literals with `LIT:<type>`, attributes with `ATTR`, and keeping structural node types. Low-signal nodes are skipped: `_SKIP_NODES = (ast.expr_context, ast.Module, ast.arguments, ast.alias, ast.Load, ast.Store)` (l.34). This makes renamed/reformatted copies still match.
2. **k-grams + hashing** — `_hash_kgrams()` (l.83) slides a window of `K_GRAM = 9` (l.26) tokens, joins them, and hashes each with MD5 → an integer, keeping the min/max source line of the window.
3. **Winnowing** — `_winnow()` (l.103) slides a window of `WINDOW = 5` (l.27) hashes and keeps the minimum hash of each window (rightmost on ties) as a **fingerprint**, mapped back to line ranges.
4. **Comparison** — `analyze()` (l.174) compares every file pair using **Jaccard similarity** of their fingerprint sets; pairs below `MIN_PAIR_SIMILARITY = 10.0`% (l.30) are dropped. Shared fingerprints are mapped to merged duplicate line ranges (`_merge_ranges`), and the actual code is attached (`_blocks_with_code`).

### Values it takes / produces
- `fingerprint_file(source: str)` (l.137) → `{ hash: [(start_line, end_line), …] }`.
- `analyze(file_sources: List[(path, source)], loc_by_file: Dict[path,int])` (l.174) → `{ duplicate_pairs[], duplication_percentage, duplicated_lines, total_lines, pair_count }`. Each pair: `{ file_a, file_b, similarity, blocks_a[], blocks_b[], shared_fingerprints }`, block = `{ start, end, code }`.

### Tunable values
| Constant | Value | Meaning |
|----------|-------|---------|
| `K_GRAM` | 9 | k-gram size (noise threshold) |
| `WINDOW` | 5 | winnowing window size |
| `MIN_PAIR_SIMILARITY` | 10.0 | min % to report a pair |

Guarantee: any shared run of ≥ `K_GRAM + WINDOW − 1` = **13** tokens is always detected.

### Formula
- Similarity: `Sim(A,B) = |F(A) ∩ F(B)| / |F(A) ∪ F(B)| × 100%`
- Repo duplication: `Dup% = (duplicated_lines / total_lines) × 100`

---

## 3. Maintainability — Halstead Metrics + Maintainability Index

**File:** `backend/services/maintainability.py`

### How it works
1. `_halstead_counts()` (l.31) walks the AST and counts **operators** (arithmetic/boolean/comparison operator nodes plus keyword nodes like `If`, `For`, `Call`, `Return`, listed in `_KEYWORD_OPERATORS`) and **operands** (`Name`, `arg`, `Constant`, `Attribute`).
2. `_halstead_metrics()` (l.52) derives vocabulary, length, volume, difficulty, effort.
3. `analyze_file()` (l.103) combines Halstead Volume with the file's cyclomatic complexity and LOC to compute the **Maintainability Index**, normalized to 0–100, and assigns a rating.

### Values it takes / produces
- `analyze_file(file_path: str, source: str, cc_total: int, loc: int)` (l.103) → `{ halstead{…}, cyclomatic_complexity, loc, maintainability_index, rating }`.
  - `cc_total` comes from module 1 (the file's total cyclomatic complexity).
  - `loc` comes from `file_stats()` (source lines, excluding blanks/comments).
- `summarize(file_reports)` (l.128) → `{ average_maintainability, rating, lowest_files[] }`.

### Formulas
Base counts: `n₁` distinct operators, `n₂` distinct operands, `N₁` total operators, `N₂` total operands.
- Vocabulary `n = n₁ + n₂`
- Length `N = N₁ + N₂`
- Volume `V = N × log₂(n)`
- Difficulty `D = (n₁ / 2) × (N₂ / n₂)`
- Effort `E = D × V`
- Maintainability Index (l.114): `MI = max(0, (171 − 5.2·ln(V) − 0.23·G − 16.2·ln(L)) × 100 / 171)` where `G` = file cyclomatic complexity, `L` = LOC.

### Rating bands (`_rating()`, l.93)
`MI ≥ 80` Excellent · `60–79` Good · `40–59` Fair · `< 40` Poor.

---

## Overall Health Score

**File:** `backend/services/analysis.py` → `compute_health_score()` (l.98)

Weighted 0–100 score, `HEALTH_WEIGHTS = { maintainability: 0.40, complexity: 0.30, duplication: 0.30 }` (l.25):
- `maintainability_score` = average MI (already 0–100)
- `complexity_score` = `100` at avg CC ≤ 5, dropping to `0` by avg CC 25
- `duplication_score` = `100 − duplication_percentage`
- `score = 0.40·maintainability + 0.30·complexity + 0.30·duplication`

Grade bands: A ≥ 80 · B ≥ 65 · C ≥ 50 · D ≥ 35 · F otherwise. Returns `{ score, grade, components, weights }`.

---

## Auxiliary: Bad Practices

**File:** `backend/services/practices.py` → `detect(source)` — an AST linter flagging bare `except`, mutable default args, `>5` args, wildcard imports, `eval`/`exec`, and global usage. Not one of the three core metrics.

## Where results are assembled

- `backend/services/analysis.py` `analyze_repository()` (l.144) calls each module and builds the response dict.
- `backend/routers/analyze.py` `_build_response()` converts it to the `AnalyzeResponse` schema (`backend/schemas/analysis.py`) and also records the run in the `analyses` table for the admin dashboard.
- Frontend renders the sections in `frontend/app/components/analysis/` (`ComplexityTab`, `DuplicatesTab`, `MaintainabilityTab`, `SummaryPanel`).
