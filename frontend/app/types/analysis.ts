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

// ---- 4. Security ----
export type Severity = "critical" | "high" | "medium" | "low";

export interface SecurityIssue {
  line: number;
  rule: string;
  severity: Severity;
  title: string;
  message: string;
  recommendation: string;
  cwe: string | null;
  match?: string | null;
  in_test: boolean;
}
export interface FileSecurityIssues {
  file_path: string;
  issues: SecurityIssue[];
  issue_count: number;
  highest_severity: Severity;
  is_test: boolean;
}
export interface DependencyVulnerability {
  package: string;
  version: string;
  pinned: boolean;
  constraint: string;
  source: string;
  vulnerability_id: string;
  cve: string | null;
  severity: Severity;
  summary: string;
  fixed_versions: string[];
  reference: string;
}
export interface DependencyScan {
  available: boolean;
  reason: string | null;
  dependencies_checked: number;
  unpinned_count: number;
  vulnerabilities: DependencyVulnerability[];
  vulnerable_package_count: number;
}
export interface SecurityReport {
  files: FileSecurityIssues[];
  dependencies: DependencyScan;
  severity_counts: Record<Severity, number>;
  total_issues: number;
  test_issues: number;
  affected_files: number;
  security_score: number;
}

// ---- 5. Dead code ----
export interface DeadDefinition {
  file_path: string;
  name: string;
  kind: string;
  lineno: number;
  lines: number;
  owner: string | null;
  confidence: "high" | "medium" | "low";
}
export interface UnusedImport { file_path: string; lineno: number; name: string; statement: string; }
export interface UnusedLocal { file_path: string; function: string; name: string; lineno: number; }
export interface UnreachableCode {
  file_path: string;
  lineno: number;
  after: string;
  after_line: number;
  statements: number;
}
export interface DeadCodeReport {
  dead_functions: DeadDefinition[];
  dead_classes: DeadDefinition[];
  unused_imports: UnusedImport[];
  unused_locals: UnusedLocal[];
  unreachable_code: UnreachableCode[];
  counts: Record<string, number>;
  total_items: number;
  dead_lines: number;
  dead_code_percentage: number;
  high_confidence_count: number;
}

// ---- 6. Type hint coverage ----
export interface FunctionTypeHints {
  name: string;
  lineno: number;
  parameters: number;
  annotated_parameters: number;
  has_return_annotation: boolean;
  coverage: number;
  is_public: boolean;
}
export interface FileTypeHints {
  file_path: string;
  functions: FunctionTypeHints[];
  function_count: number;
  annotated_slots: number;
  total_slots: number;
  coverage: number;
  fully_typed: number;
  partially_typed: number;
  untyped: number;
  annotated_variables: number;
  rating: string;
}
export interface LowestTypeCoverage {
  file_path: string;
  coverage: number;
  function_count: number;
  untyped: number;
  rating: string;
}
export interface UntypedFunction { file_path: string; name: string; lineno: number; parameters: number; }
export interface TypeHintReport {
  files: FileTypeHints[];
  coverage: number;
  rating: string;
  annotated_slots: number;
  total_slots: number;
  function_count: number;
  fully_typed: number;
  partially_typed: number;
  untyped: number;
  annotated_variables: number;
  lowest_files: LowestTypeCoverage[];
  untyped_public_functions: UntypedFunction[];
}

// ---- 7. Behavioural history (churn, hotspots, coupling, bus factor) ----
export interface ChurnFile {
  file_path: string;
  commits: number;
  insertions: number;
  deletions: number;
  churn: number;
  weighted_churn: number;
  recent_commits: number;
  author_count: number;
  first_modified: string;
  last_modified: string;
}
export interface Hotspot {
  file_path: string;
  risk_score: number;
  category: "critical" | "high" | "moderate" | "low";
  complexity: number;
  churn: number;
  commits: number;
  recent_commits: number;
  author_count: number;
  primary_author: string;
  primary_author_share: number;
  last_modified: string;
}
export interface CouplingPair {
  file_a: string;
  file_b: string;
  co_changes: number;
  commits_a: number;
  commits_b: number;
  degree: number;
  jaccard: number;
}
export interface Contributor { author: string; commits: number; lines: number; share: number; last_active: string; }
export interface AtRiskFile {
  file_path: string;
  primary_author: string;
  primary_author_share: number;
  author_count: number;
  commits: number;
  churn: number;
  bus_factor: number;
}
export interface BusFactorReport {
  repository_bus_factor: number;
  contributor_count: number;
  top_contributors: Contributor[];
  at_risk_files: AtRiskFile[];
  at_risk_count: number;
}
export interface HistoryReport {
  available: boolean;
  reason: string | null;
  commits_analyzed: number;
  contributor_count: number;
  period_days: number;
  first_commit: string | null;
  last_commit: string | null;
  churn_files: ChurnFile[];
  hotspots: Hotspot[];
  coupling: CouplingPair[];
  bus_factor: BusFactorReport;
  summary: {
    critical_hotspots: number;
    high_hotspots: number;
    coupled_pairs: number;
    knowledge_risk_files: number;
  };
}

// ---- 8. Trends and regression diffs ----
export type ChangeDirection = "improved" | "regressed" | "unchanged" | "changed";

export interface MetricChange {
  metric: string;
  label: string;
  unit: string;
  before: number;
  after: number;
  delta: number;
  percent_change: number | null;
  direction: ChangeDirection;
  headline: boolean;
}
export interface ComparisonReport {
  available: boolean;
  verdict: "baseline" | "improved" | "regressed" | "unchanged";
  reason: string | null;
  changes: MetricChange[];
  regressions: MetricChange[];
  improvements: MetricChange[];
}
export interface MetricDefinition {
  key: string;
  label: string;
  unit: string;
  higher_is_better: boolean | null;
  headline: boolean;
}
export interface TrendPoint {
  analysis_id: number;
  date: string;
  commit_sha: string | null;
  [metric: string]: number | string | null;
}
export interface TrendSeries {
  repo_name: string;
  points: TrendPoint[];
  run_count: number;
  metrics: MetricDefinition[];
  latest_comparison: ComparisonReport | null;
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
  security_score: number;
  type_hint_coverage: number;
  dead_code_items: number;
  health_score: HealthScore;
}

// ---- top-level ----
export interface AnalysisReport {
  summary: RepositorySummary;
  commit_sha: string | null;
  complexity: ComplexityReport;
  duplication: DuplicationReport;
  maintainability: MaintainabilityReport;
  security: SecurityReport;
  dead_code: DeadCodeReport;
  type_hints: TypeHintReport;
  history: HistoryReport;
  bad_practices: FileBadPractices[];
  comparison: ComparisonReport | null;
}
