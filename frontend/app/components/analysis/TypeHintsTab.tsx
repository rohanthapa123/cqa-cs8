import { Type, FileWarning, Sparkles } from "lucide-react";
import { TypeHintReport } from "../../types/analysis";

function ratingColor(rating: string) {
  switch (rating) {
    case "Excellent": return "text-green-400";
    case "Good": return "text-lime-400";
    case "Fair": return "text-amber-400";
    default: return "text-red-400";
  }
}

function coverageBar(coverage: number) {
  if (coverage >= 90) return "bg-green-500";
  if (coverage >= 70) return "bg-lime-500";
  if (coverage >= 40) return "bg-amber-500";
  return "bg-red-500";
}

function base(path: string) {
  return path.split("/").pop() ?? path;
}

export default function TypeHintsTab({ data }: { data: TypeHintReport }) {
  if (data.function_count === 0) {
    return <p className="text-center text-slate-500 text-sm py-10">No functions to annotate</p>;
  }

  const segments = [
    { label: "Fully typed", value: data.fully_typed, color: "bg-green-500" },
    { label: "Partially typed", value: data.partially_typed, color: "bg-amber-500" },
    { label: "Untyped", value: data.untyped, color: "bg-red-500" },
  ];
  const total = data.function_count || 1;

  return (
    <div className="space-y-5">
      {/* Coverage overview */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
        <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
          <div>
            <p className="text-xs text-slate-500">Coverage</p>
            <p className={`text-3xl font-bold ${ratingColor(data.rating)}`}>
              {data.coverage}
              <span className="text-base font-normal text-slate-600">%</span>
            </p>
            <p className="text-[11px] text-slate-600">{data.rating}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500">Annotated slots</p>
            <p className="text-3xl font-bold text-slate-100">{data.annotated_slots}</p>
            <p className="text-[11px] text-slate-600">of {data.total_slots}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500">Functions</p>
            <p className="text-3xl font-bold text-slate-100">{data.function_count}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500">Annotated variables</p>
            <p className="text-3xl font-bold text-slate-100">{data.annotated_variables}</p>
          </div>
        </div>

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
        <p className="text-[11px] text-slate-600">
          Coverage counts one slot per parameter plus one for the return type. `self` and `cls` are
          excluded, since annotating them is neither conventional nor useful.
        </p>
      </div>

      {/* Least-annotated files */}
      {data.lowest_files.length > 0 && (
        <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
          <p className="flex items-center gap-2 text-sm font-medium text-slate-200 mb-1">
            <FileWarning className="w-4 h-4 text-amber-400" /> Least-annotated files
          </p>
          <p className="text-xs text-slate-500 mb-4">Where adding hints buys the most type safety.</p>
          <div className="space-y-2.5">
            {data.lowest_files.map((f, i) => (
              <div key={i} className="space-y-1">
                <div className="flex items-center justify-between gap-3 text-xs">
                  <span className="text-slate-300 truncate min-w-0" title={f.file_path}>
                    {base(f.file_path)}
                  </span>
                  <span className="shrink-0 font-mono text-slate-500">
                    {f.coverage}% · {f.untyped}/{f.function_count} untyped
                  </span>
                </div>
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${coverageBar(f.coverage)}`} style={{ width: `${f.coverage}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Untyped public API */}
      {data.untyped_public_functions.length > 0 && (
        <div className="p-5 rounded-2xl bg-amber-500/5 border border-amber-500/20">
          <p className="flex items-center gap-2 text-sm font-medium text-amber-300 mb-1">
            <Sparkles className="w-4 h-4" /> Untyped public functions
          </p>
          <p className="text-xs text-slate-500 mb-4">
            Public, entirely unannotated functions — the API surface other code type-checks against,
            so these are the highest-value fixes.
          </p>
          <div className="space-y-1.5">
            {data.untyped_public_functions.map((fn, i) => (
              <div key={i} className="flex items-center gap-3 text-xs">
                <Type className="w-3 h-3 shrink-0 text-slate-600" />
                <span className="font-mono text-slate-300 truncate min-w-0">{fn.name}</span>
                <span className="shrink-0 text-slate-600">{fn.parameters} params</span>
                <span className="ml-auto shrink-0 text-slate-600 truncate max-w-[11rem]" title={fn.file_path}>
                  {base(fn.file_path)}:{fn.lineno}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per-file breakdown */}
      <div className="grid gap-4 sm:grid-cols-2">
        {data.files.map((file, i) => (
          <div key={i} className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
            <div className="flex items-center justify-between gap-2 mb-3">
              <p className="text-sm font-medium text-indigo-300 truncate" title={file.file_path}>
                {base(file.file_path)}
              </p>
              <span className={`shrink-0 text-xs font-mono ${ratingColor(file.rating)}`}>{file.coverage}%</span>
            </div>
            <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden mb-3">
              <div className={`h-full rounded-full ${coverageBar(file.coverage)}`} style={{ width: `${file.coverage}%` }} />
            </div>
            <div className="space-y-1.5">
              {file.functions.slice(0, 8).map((fn, j) => (
                <div key={j} className="flex items-center justify-between gap-3 text-xs">
                  <span className="text-slate-400 truncate min-w-0">{fn.name}</span>
                  <span className="shrink-0 font-mono text-[11px] text-slate-600">
                    {fn.annotated_parameters}/{fn.parameters} {fn.has_return_annotation ? "→ typed" : "→ any"}
                  </span>
                </div>
              ))}
              {file.functions.length > 8 && (
                <p className="text-[11px] text-slate-600 italic">
                  +{file.functions.length - 8} more
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
