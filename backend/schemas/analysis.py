from pydantic import BaseModel, HttpUrl
from typing import List


class AnalyzeRequest(BaseModel):
    repo_url: HttpUrl


# --- cyclomatic complexity ---

class FunctionComplexity(BaseModel):
    name: str
    complexity: int
    lineno: int


class FileComplexity(BaseModel):
    file_path: str
    functions: List[FunctionComplexity]


# --- duplicate detection ---

class SimilarityResult(BaseModel):
    file_pair: List[str]
    similarity: float


# --- time complexity ---

class FunctionTimeComplexity(BaseModel):
    name: str
    lineno: int
    complexity: str
    is_recursive: bool


class FileTimeComplexity(BaseModel):
    file_path: str
    functions: List[FunctionTimeComplexity]


# --- bad practices ---

class BadPractice(BaseModel):
    line: int
    type: str
    message: str


class FileBadPractices(BaseModel):
    file_path: str
    issues: List[BadPractice]


# --- test coverage ---

class TestCoverage(BaseModel):
    has_tests: bool
    test_files: List[str]
    test_count: int


# --- top-level response ---

class AnalyzeResponse(BaseModel):
    cyclomatic_complexity: List[FileComplexity]
    similarity_matrix: List[SimilarityResult]
    time_complexity: List[FileTimeComplexity]
    bad_practices: List[FileBadPractices]
    test_coverage: TestCoverage
