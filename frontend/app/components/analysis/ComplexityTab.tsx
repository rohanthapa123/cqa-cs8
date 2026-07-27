import { AlertTriangle } from "lucide-react";
import { ComplexityReport } from "../../types/analysis";

function badge(complexity: number) {
  if (complexity > 10) return "bg-red-500/15 text-red-400";
  if (complexity > 5) return "bg-amber-500/15 text-amber-400";
  return "bg-green-500/15 text-green-400";
}

function DistributionBar({ dist }: { dist: ComplexityReport["distribution"] }) {
  const total = dist.low + dist.moderate + dist.high || 1;
  const segments = [
    { label: "Low (≤5)", value: dist.low, color: "bg-green-500" },
    { label: "Moderate (6–10)", value: dist.moderate, color: "bg-amber-500" },
    { label: "High (>10)", value: dist.high, color: "bg-red-500" },
  ];
  return (
    <div className="space-y-2">
      <div className="flex h-3 rounded-full overflow-hidden bg-slate-800">
        {segments.map((s) => (
          <div key={s.label} className={s.color} style={{ width: `${(s.value / total) * 100}%` }} title={`${s.label}: ${s.value}`} />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-400">
        {segments.map((s) => (
          <span key={s.label} className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${s.color}`} /> {s.label}: {s.value}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ComplexityTab({ data }: { data: ComplexityReport }) {
  if (!data.files.length) return <p className="text-center text-slate-500 text-sm py-10">No Python functions found</p>;

  return (
    <div className="space-y-5">
      {/* Repo-level summary + distribution */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
        <div className="flex flex-wrap gap-6">
          <div>
            <p className="text-xs text-slate-500">Average complexity</p>
            <p className="text-2xl font-bold text-slate-100">{data.average_complexity}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500">Total functions</p>
            <p className="text-2xl font-bold text-slate-100">{data.function_count}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500">High-risk (CC &gt; 10)</p>
            <p className="text-2xl font-bold text-red-400">{data.high_risk_functions.length}</p>
          </div>
        </div>
        <DistributionBar dist={data.distribution} />
      </div>

      {/* High-risk functions */}
      {data.high_risk_functions.length > 0 && (
        <div className="p-5 rounded-2xl bg-red-500/5 border border-red-500/20">
          <p className="flex items-center gap-2 text-sm font-medium text-red-300 mb-3">
            <AlertTriangle className="w-4 h-4" /> High-risk functions
          </p>
          <div className="space-y-2">
            {data.high_risk_functions.map((fn, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-slate-300 truncate pr-3">
                  <span className="font-mono">{fn.name}</span>
                  <span className="text-slate-600"> · {fn.file_path.split("/").pop()}:{fn.lineno}</span>
                </span>
                <span className={`px-2 py-0.5 rounded-md font-mono shrink-0 ${badge(fn.complexity)}`}>CC {fn.complexity}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per-file / per-function breakdown */}
      <div className="grid gap-4 sm:grid-cols-2">
        {data.files.map((file, i) => (
          <div key={i} className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm font-medium text-indigo-300 truncate pr-2" title={file.file_path}>
                {file.file_path.split("/").pop()}
              </p>
              <span className="text-xs text-slate-500 shrink-0">avg {file.average_complexity}</span>
            </div>
            <div className="space-y-2.5">
              {file.functions.length ? (
                file.functions.map((fn, j) => (
                  <div key={j} className="flex items-center justify-between text-sm">
                    <span className="text-slate-400 truncate pr-3 text-xs">{fn.name}</span>
                    <span className={`px-2 py-0.5 rounded-md font-mono text-xs shrink-0 ${badge(fn.complexity)}`}>
                      CC {fn.complexity}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-xs text-slate-600 italic">No functions</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
