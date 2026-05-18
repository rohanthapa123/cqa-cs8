export interface FunctionComplexity { name: string; complexity: number; lineno: number; }
export interface FileComplexity { file_path: string; functions: FunctionComplexity[]; }
export interface SimilarityResult { file_pair: string[]; similarity: number; }
export interface FunctionTimeComplexity { name: string; lineno: number; complexity: string; is_recursive: boolean; }
export interface FileTimeComplexity { file_path: string; functions: FunctionTimeComplexity[]; }
export interface BadPractice { line: number; type: string; message: string; }
export interface FileBadPractices { file_path: string; issues: BadPractice[]; }

export interface TestCoverage {
  has_tests: boolean;
  test_files: string[];
  test_count: number;
}

export interface AnalysisReport {
  cyclomatic_complexity: FileComplexity[];
  similarity_matrix: SimilarityResult[];
  time_complexity: FileTimeComplexity[];
  bad_practices: FileBadPractices[];
  test_coverage: TestCoverage;
}
