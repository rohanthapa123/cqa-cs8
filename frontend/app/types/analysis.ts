// ---- 1. Complexity ----
export interface FunctionComplexity {
  name: string;
  complexity: number;
  lineno: number;
  is_high_risk: boolean;
}
export interface FileComplexity {
  file_path: string;
  functions: FunctionComplexity[];
  average_complexity: number;
  total_complexity: number;
  max_complexity: number;
  function_count: number;
}
export interface HighRiskFunction {
  name: string;
  complexity: number;
  lineno: number;
  file_path: string;
}
export interface ComplexityReport {
  files: FileComplexity[];
  average_complexity: number;
  total_complexity: number;
  function_count: number;
  high_risk_functions: HighRiskFunction[];
  distribution: { low: number; moderate: number; high: number };
}

// ---- 2. Duplication (Winnowing) ----
export interface DuplicateBlock {
  start: number;
  end: number;
  code: string;
}
export interface DuplicatePair {
  file_a: string;
  file_b: string;
  similarity: number;
  blocks_a: DuplicateBlock[];
  blocks_b: DuplicateBlock[];
  shared_fingerprints: number;
}
export interface DuplicationReport {
  duplicate_pairs: DuplicatePair[];
  duplication_percentage: number;
  duplicated_lines: number;
  total_lines: number;
  pair_count: number;
}

// ---- 3. Maintainability (Halstead + MI) ----
export interface HalsteadMetrics {
  distinct_operators: number;
  distinct_operands: number;
  total_operators: number;
  total_operands: number;
  vocabulary: number;
  length: number;
  volume: number;
  difficulty: number;
  effort: number;
}
export interface FileMaintainability {
  file_path: string;
  halstead: HalsteadMetrics;
  cyclomatic_complexity: number;
  loc: number;
  maintainability_index: number;
  rating: string;
}
export interface LowestMaintainability {
  file_path: string;
  maintainability_index: number;
  rating: string;
}
export interface MaintainabilityReport {
  files: FileMaintainability[];
  average_maintainability: number;
  rating: string;
  lowest_files: LowestMaintainability[];
}

// ---- Auxiliary: bad practices ----
export interface BadPractice { line: number; type: string; message: string; }
export interface FileBadPractices { file_path: string; issues: BadPractice[]; }

// ---- Dashboard summary + health ----
export interface HealthScore {
  score: number;
  grade: string;
  components: { maintainability: number; complexity: number; duplication: number };
  weights: { maintainability: number; complexity: number; duplication: number };
}
export interface RepositorySummary {
  repository_name: string;
  python_files: number;
  total_functions: number;
  total_classes: number;
  lines_of_code: number;
  average_complexity: number;
  duplication_percentage: number;
  average_maintainability: number;
  health_score: HealthScore;
}

// ---- top-level ----
export interface AnalysisReport {
  summary: RepositorySummary;
  complexity: ComplexityReport;
  duplication: DuplicationReport;
  maintainability: MaintainabilityReport;
  bad_practices: FileBadPractices[];
}
