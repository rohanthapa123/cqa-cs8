import { MaintainabilityReport, FileMaintainability } from "../../types/analysis";

function ratingStyle(rating: string) {
  switch (rating) {
    case "Excellent": return "bg-green-500/15 text-green-400";
    case "Good": return "bg-lime-500/15 text-lime-400";
    case "Fair": return "bg-amber-500/15 text-amber-400";
    default: return "bg-red-500/15 text-red-400";
  }
}

function barColor(rating: string) {
  switch (rating) {
    case "Excellent": return "bg-green-500";
    case "Good": return "bg-lime-500";
    case "Fair": return "bg-amber-500";
    default: return "bg-red-500";
  }
}

function FileRow({ file }: { file: FileMaintainability }) {
  const h = file.halstead;
  return (
    <div className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800">
      <div className="flex items-center justify-between gap-3 mb-3">
        <p className="text-sm font-medium text-indigo-300 truncate pr-2" title={file.file_path}>
          {file.file_path.split("/").pop()}
        </p>
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-mono text-sm text-slate-200">{file.maintainability_index}</span>
          <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${ratingStyle(file.rating)}`}>{file.rating}</span>
        </div>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden mb-3">
        <div className={`h-full rounded-full ${barColor(file.rating)}`} style={{ width: `${file.maintainability_index}%` }} />
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2 text-xs">
        <Metric label="Length" value={h.length} />
        <Metric label="Vocab" value={h.vocabulary} />
        <Metric label="Volume" value={h.volume} />
        <Metric label="Difficulty" value={h.difficulty} />
        <Metric label="Effort" value={h.effort} />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <p className="text-slate-600">{label}</p>
      <p className="font-mono text-slate-300 truncate" title={String(value)}>{value}</p>
    </div>
  );
}

export default function MaintainabilityTab({ data }: { data: MaintainabilityReport }) {
  if (!data.files.length) return <p className="text-center text-slate-500 text-sm py-10">No files to analyze</p>;

  return (
    <div className="space-y-5">
      {/* Summary */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 flex flex-wrap items-center gap-6">
        <div>
          <p className="text-xs text-slate-500">Average Maintainability Index</p>
          <p className="text-2xl font-bold text-slate-100">{data.average_maintainability}</p>
        </div>
        <span className={`px-2.5 py-1 rounded-lg text-sm font-medium ${ratingStyle(data.rating)}`}>{data.rating}</span>
        <p className="w-full text-xs text-slate-600">
          MI = max(0, (171 − 5.2·ln(Volume) − 0.23·CC − 16.2·ln(LOC)) · 100 / 171). Halstead metrics from AST operators/operands.
        </p>
      </div>

      {/* Lowest maintainability files */}
      {data.lowest_files.length > 0 && (
        <div className="p-5 rounded-2xl bg-amber-500/5 border border-amber-500/20">
          <p className="text-sm font-medium text-amber-300 mb-3">Lowest-maintainability files</p>
          <div className="space-y-2">
            {data.lowest_files.map((f, i) => (
              <div key={i} className="flex items-center justify-between text-xs">
                <span className="text-slate-300 truncate pr-3" title={f.file_path}>{f.file_path.split("/").pop()}</span>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="font-mono text-slate-200">{f.maintainability_index}</span>
                  <span className={`px-1.5 py-0.5 rounded ${ratingStyle(f.rating)}`}>{f.rating}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per-file Halstead + MI */}
      <div className="space-y-3">
        {data.files.map((file, i) => (
          <FileRow key={i} file={file} />
        ))}
      </div>
    </div>
  );
}
