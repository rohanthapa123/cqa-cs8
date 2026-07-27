from pydantic import BaseModel, HttpUrl
from typing import Dict, List


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
    health_score: HealthScore


# ---------------------------------------------------------------------------
# top-level response
# ---------------------------------------------------------------------------

class AnalyzeResponse(BaseModel):
    summary: RepositorySummary
    complexity: ComplexityReport
    duplication: DuplicationReport
    maintainability: MaintainabilityReport
    bad_practices: List[FileBadPractices]
