from pydantic import BaseModel, HttpUrl
from typing import Dict, List, Optional


class AnalyzeRequest(BaseModel):
    repo_url: HttpUrl


# ---------------------------------------------------------------------------
# 1. Complexity (Cyclomatic / McCabe)
# ---------------------------------------------------------------------------

class FunctionComplexity(BaseModel):
    name: str
    complexity: int
    lineno: int
    is_high_risk: bool


class FileComplexity(BaseModel):
    file_path: str
    functions: List[FunctionComplexity]
    average_complexity: float
    total_complexity: int
    max_complexity: int
    function_count: int


class HighRiskFunction(BaseModel):
    name: str
    complexity: int
    lineno: int
    file_path: str


class ComplexityReport(BaseModel):
    files: List[FileComplexity]
    average_complexity: float
    total_complexity: int
    function_count: int
    high_risk_functions: List[HighRiskFunction]
    distribution: Dict[str, int]


# ---------------------------------------------------------------------------
# 2. Duplication (Winnowing)
# ---------------------------------------------------------------------------

class DuplicateBlock(BaseModel):
    start: int
    end: int
    code: str


class DuplicatePair(BaseModel):
    file_a: str
    file_b: str
    similarity: float
    blocks_a: List[DuplicateBlock]
    blocks_b: List[DuplicateBlock]
    shared_fingerprints: int


class DuplicationReport(BaseModel):
    duplicate_pairs: List[DuplicatePair]
    duplication_percentage: float
    duplicated_lines: int
    total_lines: int
    pair_count: int


# ---------------------------------------------------------------------------
# 3. Maintainability (Halstead + MI)
# ---------------------------------------------------------------------------

class HalsteadMetrics(BaseModel):
    distinct_operators: int
    distinct_operands: int
    total_operators: int
    total_operands: int
    vocabulary: int
    length: int
    volume: float
    difficulty: float
    effort: float


class FileMaintainability(BaseModel):
    file_path: str
    halstead: HalsteadMetrics
    cyclomatic_complexity: int
    loc: int
    maintainability_index: float
    rating: str


class LowestMaintainability(BaseModel):
    file_path: str
    maintainability_index: float
    rating: str


class MaintainabilityReport(BaseModel):
    files: List[FileMaintainability]
    average_maintainability: float
    rating: str
    lowest_files: List[LowestMaintainability]


# ---------------------------------------------------------------------------
# 4. Security (AST patterns + secrets + dependency CVEs)
# ---------------------------------------------------------------------------

class SecurityIssue(BaseModel):
    line: int
    rule: str
    severity: str
    title: str
    message: str
    recommendation: str
    cwe: Optional[str] = None
    match: Optional[str] = None  # redacted secret, when the rule found one
    in_test: bool = False        # found in test code, so severity was lowered


class FileSecurityIssues(BaseModel):
    file_path: str
    issues: List[SecurityIssue]
    issue_count: int
    highest_severity: str
    is_test: bool = False


class DependencyVulnerability(BaseModel):
    package: str
    version: str
    pinned: bool
    constraint: str
    source: str
    vulnerability_id: str
    cve: Optional[str] = None
    severity: str
    summary: str
    fixed_versions: List[str]
    reference: str


class DependencyScan(BaseModel):
    available: bool
    reason: Optional[str] = None
    dependencies_checked: int
    unpinned_count: int = 0
    vulnerabilities: List[DependencyVulnerability]
    vulnerable_package_count: int


class SecurityReport(BaseModel):
    files: List[FileSecurityIssues]
    dependencies: DependencyScan
    severity_counts: Dict[str, int]
    total_issues: int
    test_issues: int = 0
    affected_files: int
    security_score: float


# ---------------------------------------------------------------------------
# 5. Dead code (reachability analysis)
# ---------------------------------------------------------------------------

class DeadDefinition(BaseModel):
    file_path: str
    name: str
    kind: str          # function | method | class
    lineno: int
    lines: int
    owner: Optional[str] = None
    confidence: str    # high | medium | low


class UnusedImport(BaseModel):
    file_path: str
    lineno: int
    name: str
    statement: str


class UnusedLocal(BaseModel):
    file_path: str
    function: str
    name: str
    lineno: int


class UnreachableCode(BaseModel):
    file_path: str
    lineno: int
    after: str
    after_line: int
    statements: int


class DeadCodeReport(BaseModel):
    dead_functions: List[DeadDefinition]
    dead_classes: List[DeadDefinition]
    unused_imports: List[UnusedImport]
    unused_locals: List[UnusedLocal]
    unreachable_code: List[UnreachableCode]
    counts: Dict[str, int]
    total_items: int
    dead_lines: int
    dead_code_percentage: float
    high_confidence_count: int


# ---------------------------------------------------------------------------
# 6. Type hint coverage
# ---------------------------------------------------------------------------

class FunctionTypeHints(BaseModel):
    name: str
    lineno: int
    parameters: int
    annotated_parameters: int
    has_return_annotation: bool
    coverage: float
    is_public: bool


class FileTypeHints(BaseModel):
    file_path: str
    functions: List[FunctionTypeHints]
    function_count: int
    annotated_slots: int
    total_slots: int
    coverage: float
    fully_typed: int
    partially_typed: int
    untyped: int
    annotated_variables: int
    rating: str


class LowestTypeCoverage(BaseModel):
    file_path: str
    coverage: float
    function_count: int
    untyped: int
    rating: str


class UntypedFunction(BaseModel):
    file_path: str
    name: str
    lineno: int
    parameters: int


class TypeHintReport(BaseModel):
    files: List[FileTypeHints]
    coverage: float
    rating: str
    annotated_slots: int
    total_slots: int
    function_count: int
    fully_typed: int
    partially_typed: int
    untyped: int
    annotated_variables: int
    lowest_files: List[LowestTypeCoverage]
    untyped_public_functions: List[UntypedFunction]


# ---------------------------------------------------------------------------
# 7. Behavioural history (churn, hotspots, coupling, bus factor)
# ---------------------------------------------------------------------------

class ChurnFile(BaseModel):
    file_path: str
    commits: int
    insertions: int
    deletions: int
    churn: int
    weighted_churn: float
    recent_commits: int
    author_count: int
    first_modified: str
    last_modified: str


class Hotspot(BaseModel):
    file_path: str
    risk_score: float
    category: str      # critical | high | moderate | low
    complexity: int
    churn: int
    commits: int
    recent_commits: int
    author_count: int
    primary_author: str
    primary_author_share: float
    last_modified: str


class CouplingPair(BaseModel):
    file_a: str
    file_b: str
    co_changes: int
    commits_a: int
    commits_b: int
    degree: float
    jaccard: float


class Contributor(BaseModel):
    author: str
    commits: int
    lines: int
    share: float
    last_active: str


class AtRiskFile(BaseModel):
    file_path: str
    primary_author: str
    primary_author_share: float
    author_count: int
    commits: int
    churn: int
    bus_factor: int


class BusFactorReport(BaseModel):
    repository_bus_factor: int
    contributor_count: int
    top_contributors: List[Contributor]
    at_risk_files: List[AtRiskFile]
    at_risk_count: int


class HistorySummary(BaseModel):
    critical_hotspots: int
    high_hotspots: int
    coupled_pairs: int
    knowledge_risk_files: int


class HistoryReport(BaseModel):
    available: bool
    reason: Optional[str] = None
    commits_analyzed: int
    contributor_count: int
    period_days: int
    first_commit: Optional[str] = None
    last_commit: Optional[str] = None
    churn_files: List[ChurnFile]
    hotspots: List[Hotspot]
    coupling: List[CouplingPair]
    bus_factor: BusFactorReport
    summary: HistorySummary


# ---------------------------------------------------------------------------
# 8. Trends and regression diffs
# ---------------------------------------------------------------------------

class MetricChange(BaseModel):
    metric: str
    label: str
    unit: str
    before: float
    after: float
    delta: float
    percent_change: Optional[float] = None
    direction: str     # improved | regressed | unchanged | changed
    headline: bool


class ComparisonReport(BaseModel):
    available: bool
    verdict: str       # baseline | improved | regressed | unchanged
    reason: Optional[str] = None
    changes: List[MetricChange]
    regressions: List[MetricChange]
    improvements: List[MetricChange]


class MetricDefinition(BaseModel):
    key: str
    label: str
    unit: str
    higher_is_better: Optional[bool] = None
    headline: bool


class TrendPoint(BaseModel):
    analysis_id: int
    date: str
    commit_sha: Optional[str] = None
    health_score: Optional[float] = None
    average_maintainability: Optional[float] = None
    average_complexity: Optional[float] = None
    duplication_percentage: Optional[float] = None
    security_score: Optional[float] = None
    type_hint_coverage: Optional[float] = None
    high_risk_functions: Optional[float] = None
    critical_security_issues: Optional[float] = None
    dead_code_items: Optional[float] = None
    critical_hotspots: Optional[float] = None
    lines_of_code: Optional[float] = None
    python_files: Optional[float] = None


class TrendSeries(BaseModel):
    repo_name: str
    points: List[TrendPoint]
    run_count: int
    metrics: List[MetricDefinition]
    latest_comparison: Optional[ComparisonReport] = None


class AnalysisRun(BaseModel):
    id: int
    repo_name: str
    repo_url: str
    status: str
    health_score: Optional[int] = None
    commit_sha: Optional[str] = None
    ref: Optional[str] = None
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Auxiliary: bad practices
# ---------------------------------------------------------------------------

class BadPractice(BaseModel):
    line: int
    type: str
    message: str


class FileBadPractices(BaseModel):
    file_path: str
    issues: List[BadPractice]


# ---------------------------------------------------------------------------
# Dashboard summary + health score
# ---------------------------------------------------------------------------

class HealthScore(BaseModel):
    score: int
    grade: str
    components: Dict[str, int]
    weights: Dict[str, float]


class RepositorySummary(BaseModel):
    repository_name: str
    python_files: int
    total_functions: int
    total_classes: int
    lines_of_code: int
    average_complexity: float
    duplication_percentage: float
    average_maintainability: float
    security_score: float
    type_hint_coverage: float
    dead_code_items: int
    health_score: HealthScore


# ---------------------------------------------------------------------------
# top-level response
# ---------------------------------------------------------------------------

class AnalyzeResponse(BaseModel):
    summary: RepositorySummary
    commit_sha: Optional[str] = None
    complexity: ComplexityReport
    duplication: DuplicationReport
    maintainability: MaintainabilityReport
    security: SecurityReport
    dead_code: DeadCodeReport
    type_hints: TypeHintReport
    history: HistoryReport
    bad_practices: List[FileBadPractices]
    comparison: Optional[ComparisonReport] = None
