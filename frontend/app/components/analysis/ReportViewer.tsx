"use client";

import { useState } from "react";
import {
  CheckCircle2, X, BarChart3, Copy, Gauge, Shield, Download, LayoutDashboard,
  ShieldAlert, Trash2, Type, Flame, TrendingUp,
} from "lucide-react";
import { AnalysisReport } from "../../types/analysis";
import SummaryPanel from "./SummaryPanel";
import ComplexityTab from "./ComplexityTab";
import DuplicatesTab from "./DuplicatesTab";
import MaintainabilityTab from "./MaintainabilityTab";
import SecurityTab from "./SecurityTab";
import DeadCodeTab from "./DeadCodeTab";
import TypeHintsTab from "./TypeHintsTab";
import HotspotsTab from "./HotspotsTab";
import TrendsTab from "./TrendsTab";
import PracticesTab from "./PracticesTab";

type Tab =
  | "overview" | "hotspots" | "trends" | "security" | "complexity"
  | "duplicates" | "maintainability" | "deadcode" | "typehints" | "practices";

const TABS: { id: Tab; label: string; Icon: React.ElementType }[] = [
  { id: "overview", label: "Overview", Icon: LayoutDashboard },
  { id: "hotspots", label: "Hotspots", Icon: Flame },
  { id: "trends", label: "Trends", Icon: TrendingUp },
  { id: "security", label: "Security", Icon: ShieldAlert },
  { id: "complexity", label: "Complexity", Icon: BarChart3 },
  { id: "duplicates", label: "Duplicates", Icon: Copy },
  { id: "maintainability", label: "Maintainability", Icon: Gauge },
  { id: "deadcode", label: "Dead Code", Icon: Trash2 },
  { id: "typehints", label: "Type Hints", Icon: Type },
  { id: "practices", label: "Bad Practices", Icon: Shield },
];

function base(path: string) {
  return path.split("/").pop() ?? path;
}

function generateMarkdownReport(report: AnalysisReport): string {
  const date = new Date().toISOString().split("T")[0];
  const s = report.summary;
  const h = s.health_score;

  const lines: string[] = [
    `# CodeAnalysis Report`,
    `**Repository:** ${s.repository_name}`,
    `**Generated:** ${date}`,
    ...(report.commit_sha ? [`**Commit:** \`${report.commit_sha.slice(0, 10)}\``] : []),
    ``,
    `## Overall Repository Health`,
    `**Health Score: ${h.score}/100 (Grade ${h.grade})**`,
    ``,
    `| Component | Score | Weight |`,
    `|-----------|-------|--------|`,
    `| Maintainability | ${h.components.maintainability} | ${Math.round(h.weights.maintainability * 100)}% |`,
    `| Complexity | ${h.components.complexity} | ${Math.round(h.weights.complexity * 100)}% |`,
    `| Duplication | ${h.components.duplication} | ${Math.round(h.weights.duplication * 100)}% |`,
    ``,
    `## Summary`,
    `| Metric | Value |`,
    `|--------|-------|`,
    `| Python files | ${s.python_files} |`,
    `| Lines of code | ${s.lines_of_code} |`,
    `| Total functions | ${s.total_functions} |`,
    `| Total classes | ${s.total_classes} |`,
    `| Average cyclomatic complexity | ${s.average_complexity} |`,
    `| Duplicate code | ${s.duplication_percentage}% |`,
    `| Average maintainability index | ${s.average_maintainability} |`,
    `| Security score | ${s.security_score}/100 |`,
    `| Type hint coverage | ${s.type_hint_coverage}% |`,
    `| Dead code items | ${s.dead_code_items} |`,
    ``,
    `---`,
    ``,
    `## 1. Cyclomatic Complexity`,
    `Average CC **${report.complexity.average_complexity}** across ${report.complexity.function_count} functions.`,
    ``,
  ];

  if (report.complexity.high_risk_functions.length) {
    lines.push(`### High-risk functions (CC > 10)`, ``, `| Function | File | CC | Line |`, `|----------|------|----|------|`);
    for (const fn of report.complexity.high_risk_functions) {
      lines.push(`| \`${fn.name}\` | ${base(fn.file_path)} | ${fn.complexity} | ${fn.lineno} |`);
    }
  } else {
    lines.push(`_No high-risk functions._`);
  }

  lines.push(``, `---`, ``, `## 2. Duplicate Code Detection (Winnowing)`,
    `Overall duplication: **${report.duplication.duplication_percentage}%** (${report.duplication.duplicated_lines}/${report.duplication.total_lines} lines).`, ``);
  if (report.duplication.duplicate_pairs.length) {
    lines.push(`| File A | File B | Similarity | Duplicate ranges (A) |`, `|--------|--------|-----------|----------------------|`);
    for (const p of report.duplication.duplicate_pairs) {
      const ranges = p.blocks_a.map((b) => `${b.start}-${b.end}`).join(", ") || "—";
      lines.push(`| \`${base(p.file_a)}\` | \`${base(p.file_b)}\` | ${p.similarity}% | ${ranges} |`);
    }
  } else {
    lines.push(`_No significant duplication detected._`);
  }

  lines.push(``, `---`, ``, `## 3. Maintainability (Halstead + MI)`,
    `Average Maintainability Index: **${report.maintainability.average_maintainability}** (${report.maintainability.rating}).`, ``);
  if (report.maintainability.lowest_files.length) {
    lines.push(`### Lowest-maintainability files`, ``, `| File | MI | Rating |`, `|------|----|--------|`);
    for (const f of report.maintainability.lowest_files) {
      lines.push(`| \`${base(f.file_path)}\` | ${f.maintainability_index} | ${f.rating} |`);
    }
  }

  // ---- 4. Security ----
  const sec = report.security;
  const counts = sec.severity_counts;
  lines.push(``, `---`, ``, `## 4. Security`,
    `Security score: **${sec.security_score}/100** — ${sec.total_issues} finding(s) across ${sec.affected_files} file(s).`,
    ``,
    `Critical: ${counts.critical ?? 0} · High: ${counts.high ?? 0} · Medium: ${counts.medium ?? 0} · Low: ${counts.low ?? 0}`,
    ``);
  if (sec.files.length) {
    lines.push(`### Code findings`, ``, `| Severity | File | Line | Issue | CWE |`, `|----------|------|------|-------|-----|`);
    for (const file of sec.files) {
      for (const issue of file.issues) {
        lines.push(`| ${issue.severity} | \`${base(file.file_path)}\` | L${issue.line} | ${issue.title} | ${issue.cwe ?? "—"} |`);
      }
    }
  } else {
    lines.push(`_No code-level security findings._`);
  }

  const deps = report.security.dependencies;
  lines.push(``, `### Dependency vulnerabilities`, ``);
  if (!deps.available) {
    lines.push(`_${deps.reason}_`);
  } else if (deps.vulnerabilities.length) {
    lines.push(
      `${deps.vulnerabilities.length} advisory(ies) affecting ${deps.vulnerable_package_count} of ${deps.dependencies_checked} package(s).`,
      ``,
      `| Severity | Package | Constraint | Advisory | Fixed in |`,
      `|----------|---------|-----------|----------|----------|`);
    for (const v of deps.vulnerabilities) {
      lines.push(`| ${v.severity} | \`${v.package}\` | ${v.constraint} | ${v.cve ?? v.vulnerability_id} | ${v.fixed_versions.join(", ") || "—"} |`);
    }
  } else {
    lines.push(`_No known vulnerabilities in ${deps.dependencies_checked} package(s)._`);
  }

  // ---- 5. Dead code ----
  const dead = report.dead_code;
  lines.push(``, `---`, ``, `## 5. Dead Code`,
    `${dead.total_items} item(s), covering ${dead.dead_lines} line(s) (${dead.dead_code_percentage}% of the codebase).`,
    ``, `| Category | Count |`, `|----------|-------|`,
    `| Unreferenced functions | ${dead.counts.dead_functions ?? 0} |`,
    `| Unreferenced classes | ${dead.counts.dead_classes ?? 0} |`,
    `| Unused imports | ${dead.counts.unused_imports ?? 0} |`,
    `| Unused local variables | ${dead.counts.unused_locals ?? 0} |`,
    `| Unreachable statements | ${dead.counts.unreachable_code ?? 0} |`);
  const unreferenced = [...dead.dead_functions, ...dead.dead_classes];
  if (unreferenced.length) {
    lines.push(``, `### Unreferenced definitions`, ``,
      `| Name | Kind | File | Line | Lines | Confidence |`, `|------|------|------|------|-------|------------|`);
    for (const d of unreferenced) {
      lines.push(`| \`${d.name}\` | ${d.kind} | ${base(d.file_path)} | ${d.lineno} | ${d.lines} | ${d.confidence} |`);
    }
  }

  // ---- 6. Type hints ----
  const th = report.type_hints;
  lines.push(``, `---`, ``, `## 6. Type Hint Coverage`,
    `Coverage: **${th.coverage}%** (${th.rating}) — ${th.annotated_slots} of ${th.total_slots} annotatable slots.`,
    ``,
    `Fully typed: ${th.fully_typed} · Partially typed: ${th.partially_typed} · Untyped: ${th.untyped} (of ${th.function_count} functions)`,
    ``);
  if (th.lowest_files.length) {
    lines.push(`### Least-annotated files`, ``, `| File | Coverage | Functions | Untyped |`, `|------|----------|-----------|---------|`);
    for (const f of th.lowest_files) {
      lines.push(`| \`${base(f.file_path)}\` | ${f.coverage}% | ${f.function_count} | ${f.untyped} |`);
    }
  }

  // ---- 7. Behavioural history ----
  const hist = report.history;
  lines.push(``, `---`, ``, `## 7. Behavioural Analysis (git history)`, ``);
  if (!hist.available) {
    lines.push(`_${hist.reason}_`);
  } else {
    lines.push(`${hist.commits_analyzed} commits from ${hist.contributor_count} contributor(s) over ${hist.period_days} days (${hist.first_commit} to ${hist.last_commit}).`, ``);

    if (hist.hotspots.length) {
      lines.push(`### Hotspots (churn × complexity)`, ``,
        `| File | Risk | Category | Complexity | Churn | Commits |`, `|------|------|----------|------------|-------|---------|`);
      for (const h of hist.hotspots) {
        lines.push(`| \`${base(h.file_path)}\` | ${h.risk_score} | ${h.category} | ${h.complexity} | ${h.churn} | ${h.commits} |`);
      }
    }

    if (hist.churn_files.length) {
      lines.push(``, `### Most-changed files`, ``,
        `| File | Commits | +Lines | -Lines | Authors |`, `|------|---------|--------|--------|---------|`);
      for (const c of hist.churn_files.slice(0, 15)) {
        lines.push(`| \`${base(c.file_path)}\` | ${c.commits} | ${c.insertions} | ${c.deletions} | ${c.author_count} |`);
      }
    }

    if (hist.coupling.length) {
      lines.push(``, `### Change coupling`, ``,
        `| File A | File B | Co-changes | Degree |`, `|--------|--------|-----------|--------|`);
      for (const c of hist.coupling) {
        lines.push(`| \`${base(c.file_a)}\` | \`${base(c.file_b)}\` | ${c.co_changes} | ${c.degree}% |`);
      }
    }

    const bf = hist.bus_factor;
    lines.push(``, `### Knowledge distribution`,
      `Repository bus factor: **${bf.repository_bus_factor}** (${bf.contributor_count} contributors, ${bf.at_risk_count} file(s) with concentrated ownership).`, ``);
    if (bf.top_contributors.length) {
      lines.push(`| Contributor | Commits | Lines | Share |`, `|-------------|---------|-------|-------|`);
      for (const c of bf.top_contributors.slice(0, 10)) {
        lines.push(`| ${c.author} | ${c.commits} | ${c.lines} | ${c.share}% |`);
      }
    }
    if (bf.at_risk_files.length) {
      lines.push(``, `#### Files with concentrated ownership`, ``,
        `| File | Primary author | Share | Authors |`, `|------|----------------|-------|---------|`);
      for (const f of bf.at_risk_files.slice(0, 10)) {
        lines.push(`| \`${base(f.file_path)}\` | ${f.primary_author} | ${f.primary_author_share}% | ${f.author_count} |`);
      }
    }
  }

  // ---- Change since the previous run ----
  const cmp = report.comparison;
  if (cmp?.available) {
    lines.push(``, `---`, ``, `## Change Since Previous Run`, `**Verdict: ${cmp.verdict.toUpperCase()}**`, ``,
      `| Metric | Before | After | Change |`, `|--------|--------|-------|--------|`);
    for (const c of cmp.changes) {
      if (c.direction === "unchanged") continue;
      const sign = c.delta > 0 ? "+" : "";
      lines.push(`| ${c.label} | ${c.before}${c.unit} | ${c.after}${c.unit} | ${sign}${c.delta}${c.unit} (${c.direction}) |`);
    }
    if (!cmp.regressions.length) lines.push(``, `_No regressions detected._`);
  }

  lines.push(``, `---`, ``, `## Bad Practices (auxiliary)`, ``);
  const filesWithIssues = report.bad_practices.filter((f) => f.issues.length);
  if (filesWithIssues.length) {
    for (const file of filesWithIssues) {
      lines.push(`### ${base(file.file_path)}`, `| Line | Type | Message |`, `|------|------|---------|`);
      for (const issue of file.issues) {
        lines.push(`| L${issue.line} | \`${issue.type}\` | ${issue.message} |`);
      }
      lines.push(``);
    }
  } else {
    lines.push(`No bad practices detected.`);
  }

  lines.push(``, `---`, `_Generated by CodeAnalysis_`);
  return lines.join("\n");
}

function downloadFile(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

interface Props {
  repoName: string;
  report: AnalysisReport;
  onClose: () => void;
}

export default function ReportViewer({ repoName, report, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("overview");

  const handleDownload = () => {
    const md = generateMarkdownReport(report);
    downloadFile(md, `${repoName}-analysis.md`, "text/markdown");
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3 p-4 rounded-xl bg-slate-900/60 border border-slate-800">
        <CheckCircle2 className="w-5 h-5 text-green-400 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-white truncate">{repoName}</p>
          <p className="text-xs text-slate-500">
            {report.summary.python_files} file(s) · Health {report.summary.health_score.score}/100
          </p>
        </div>
        <button
          onClick={handleDownload}
          title="Download Markdown report"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          <span className="hidden sm:block">Report</span>
        </button>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Tabs. They wrap rather than scroll: with ten of them, `flex-1` would
          squash every label to nothing, and a horizontal scroll strip hides
          tabs behind a gesture people don't know is there. */}
      <div className="flex flex-wrap gap-1 p-1 bg-slate-900 rounded-xl border border-slate-800">
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            title={label}
            className={[
              "shrink-0 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-sm font-medium transition-all whitespace-nowrap",
              activeTab === id ? "bg-indigo-600 text-white shadow" : "text-slate-400 hover:text-slate-200",
            ].join(" ")}
          >
            <Icon className="w-3.5 h-3.5 shrink-0" />
            <span className="hidden md:block">{label}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "overview" && <SummaryPanel summary={report.summary} />}
      {activeTab === "hotspots" && <HotspotsTab data={report.history} />}
      {activeTab === "trends" && (
        <TrendsTab repoName={report.summary.repository_name} comparison={report.comparison} />
      )}
      {activeTab === "security" && <SecurityTab data={report.security} />}
      {activeTab === "complexity" && <ComplexityTab data={report.complexity} />}
      {activeTab === "duplicates" && <DuplicatesTab data={report.duplication} />}
      {activeTab === "maintainability" && <MaintainabilityTab data={report.maintainability} />}
      {activeTab === "deadcode" && <DeadCodeTab data={report.dead_code} />}
      {activeTab === "typehints" && <TypeHintsTab data={report.type_hints} />}
      {activeTab === "practices" && <PracticesTab data={report.bad_practices} />}
    </div>
  );
}
