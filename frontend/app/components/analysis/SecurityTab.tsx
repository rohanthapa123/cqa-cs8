import { useState } from "react";
import { ShieldCheck, ShieldAlert, Package, ChevronDown, ExternalLink, Info } from "lucide-react";
import { SecurityReport, Severity, SecurityIssue } from "../../types/analysis";

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];

const SEVERITY_STYLE: Record<Severity, { pill: string; bar: string; text: string }> = {
  critical: { pill: "bg-red-500/15 text-red-400 border-red-500/30", bar: "bg-red-500", text: "text-red-400" },
  high: { pill: "bg-orange-500/15 text-orange-400 border-orange-500/30", bar: "bg-orange-500", text: "text-orange-400" },
  medium: { pill: "bg-amber-500/15 text-amber-400 border-amber-500/30", bar: "bg-amber-500", text: "text-amber-400" },
  low: { pill: "bg-sky-500/15 text-sky-400 border-sky-500/30", bar: "bg-sky-500", text: "text-sky-400" },
};

function scoreColor(score: number) {
  if (score >= 80) return "text-green-400";
  if (score >= 50) return "text-amber-400";
  return "text-red-400";
}

function IssueRow({ issue }: { issue: SecurityIssue }) {
  const [open, setOpen] = useState(false);
  const style = SEVERITY_STYLE[issue.severity];

  return (
    <div className="rounded-xl bg-slate-950/40 border border-slate-800/80 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-start gap-3 p-3 text-left hover:bg-slate-900/60 transition-colors"
      >
        <span className={`shrink-0 px-1.5 py-0.5 rounded border text-[10px] font-semibold uppercase tracking-wide ${style.pill}`}>
          {issue.severity}
        </span>
        <span className="shrink-0 px-1.5 py-0.5 rounded font-mono text-[11px] bg-slate-800 text-slate-400">
          L{issue.line}
        </span>
        <span className="flex-1 min-w-0 text-xs text-slate-300">{issue.title}</span>
        {issue.cwe && <span className="shrink-0 text-[10px] font-mono text-slate-600">{issue.cwe}</span>}
        <ChevronDown className={`w-3.5 h-3.5 shrink-0 text-slate-600 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="px-3 pb-3 pt-0 space-y-2 text-xs">
          <p className="text-slate-400 leading-relaxed">{issue.message}</p>
          {issue.match && (
            <p className="font-mono text-[11px] text-slate-500">
              Matched value: <span className="text-slate-400">{issue.match}</span>
            </p>
          )}
          <div className="flex items-start gap-2 p-2.5 rounded-lg bg-indigo-500/5 border border-indigo-500/20">
            <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-indigo-400" />
            <p className="text-slate-400 leading-relaxed">{issue.recommendation}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SecurityTab({ data }: { data: SecurityReport }) {
  const counts = data.severity_counts;
  const deps = data.dependencies;
  const totalForBar = SEVERITY_ORDER.reduce((sum, s) => sum + (counts[s] ?? 0), 0) || 1;

  return (
    <div className="space-y-5">
      {/* Score + severity breakdown */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
        <div className="flex flex-wrap items-start gap-6">
          <div>
            <p className="text-xs text-slate-500">Security score</p>
            <p className={`text-3xl font-bold ${scoreColor(data.security_score)}`}>
              {data.security_score}
              <span className="text-base font-normal text-slate-600">/100</span>
            </p>
          </div>
          <div>
            <p className="text-xs text-slate-500">Total findings</p>
            <p className="text-3xl font-bold text-slate-100">{data.total_issues}</p>
            {data.test_issues > 0 && (
              <p className="text-[11px] text-slate-600">{data.test_issues} in test code</p>
            )}
          </div>
          <div>
            <p className="text-xs text-slate-500">Affected files</p>
            <p className="text-3xl font-bold text-slate-100">{data.affected_files}</p>
          </div>
        </div>

        <div className="flex h-3 rounded-full overflow-hidden bg-slate-800">
          {SEVERITY_ORDER.map((s) => (
            <div
              key={s}
              className={SEVERITY_STYLE[s].bar}
              style={{ width: `${((counts[s] ?? 0) / totalForBar) * 100}%` }}
              title={`${s}: ${counts[s] ?? 0}`}
            />
          ))}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
          {SEVERITY_ORDER.map((s) => (
            <span key={s} className="flex items-center gap-1.5 capitalize">
              <span className={`w-2 h-2 rounded-full ${SEVERITY_STYLE[s].bar}`} /> {s}: {counts[s] ?? 0}
            </span>
          ))}
        </div>
      </div>

      {/* Dependency vulnerabilities */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
        <p className="flex items-center gap-2 text-sm font-medium text-slate-200 mb-1">
          <Package className="w-4 h-4 text-indigo-400" /> Dependency vulnerabilities
        </p>
        <p className="text-xs text-slate-500 mb-4">
          Declared requirements checked against the OSV.dev advisory database.
        </p>

        {!deps.available ? (
          <p className="text-xs text-slate-500 italic">{deps.reason}</p>
        ) : deps.vulnerabilities.length === 0 ? (
          <p className="flex items-center gap-2 text-xs text-green-400">
            <ShieldCheck className="w-4 h-4" />
            No known advisories across {deps.dependencies_checked} package(s).
          </p>
        ) : (
          <div className="space-y-2">
            <p className="text-xs text-slate-400 mb-3">
              {deps.vulnerabilities.length} advisory(ies) affecting{" "}
              <span className="text-rose-300">{deps.vulnerable_package_count}</span> of{" "}
              {deps.dependencies_checked} package(s)
              {deps.unpinned_count > 0 && (
                <span className="text-slate-600"> · {deps.unpinned_count} checked at their lower bound</span>
              )}
            </p>
            {deps.vulnerabilities.map((v, i) => {
              const style = SEVERITY_STYLE[v.severity];
              return (
                <div key={i} className="p-3 rounded-xl bg-slate-950/40 border border-slate-800/80 space-y-1.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold uppercase ${style.pill}`}>
                      {v.severity}
                    </span>
                    <span className="font-mono text-xs text-slate-200">{v.package}</span>
                    <span className="font-mono text-[11px] text-slate-500">{v.constraint}</span>
                    {!v.pinned && (
                      <span className="text-[10px] text-slate-600 border border-slate-700 rounded px-1">unpinned</span>
                    )}
                    <a
                      href={v.reference}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-auto flex items-center gap-1 text-[11px] font-mono text-indigo-400 hover:text-indigo-300"
                    >
                      {v.cve ?? v.vulnerability_id}
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                  {v.summary && <p className="text-xs text-slate-400 leading-relaxed">{v.summary}</p>}
                  {v.fixed_versions.length > 0 && (
                    <p className="text-[11px] text-slate-500">
                      Fixed in <span className="font-mono text-green-400">{v.fixed_versions.join(", ")}</span>
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Code findings */}
      {data.files.length === 0 ? (
        <div className="flex items-center gap-3 p-5 rounded-2xl bg-green-500/10 border border-green-500/20 text-green-400">
          <ShieldCheck className="w-5 h-5 shrink-0" />
          <p className="font-medium">No code-level security issues detected</p>
        </div>
      ) : (
        <div className="space-y-4">
          {data.files.map((file, i) => (
            <div key={i} className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
              <p className="flex items-center gap-2 text-sm font-medium mb-1">
                <ShieldAlert className={`w-4 h-4 shrink-0 ${SEVERITY_STYLE[file.highest_severity].text}`} />
                <span className="text-slate-200 truncate" title={file.file_path}>
                  {file.file_path.split("/").pop()}
                </span>
                {file.is_test && (
                  <span className="shrink-0 px-1.5 py-0.5 rounded border border-slate-700 text-[10px] text-slate-500">
                    test code
                  </span>
                )}
                <span className="text-slate-600 font-normal text-xs">
                  ({file.issue_count} issue{file.issue_count !== 1 ? "s" : ""})
                </span>
              </p>
              <p className="text-[11px] text-slate-600 mb-3 truncate" title={file.file_path}>
                {file.is_test
                  ? "Test code is not shipped attack surface — these are reported one severity lower."
                  : file.file_path}
              </p>
              <div className="space-y-2">
                {file.issues.map((issue, j) => (
                  <IssueRow key={j} issue={issue} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
