import { FileComplexity } from "../../types/analysis";

function badge(complexity: number) {
  if (complexity > 10) return "bg-red-500/15 text-red-400";
  if (complexity > 5) return "bg-amber-500/15 text-amber-400";
  return "bg-green-500/15 text-green-400";
}

export default function ComplexityTab({ data }: { data: FileComplexity[] }) {
  if (!data.length) return <Empty message="No Python functions found" />;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {data.map((file, i) => (
        <div key={i} className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
          <p className="text-sm font-medium text-indigo-300 truncate mb-4" title={file.file_path}>
            {file.file_path.split("/").pop()}
          </p>
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
  );
}

function Empty({ message }: { message: string }) {
  return <p className="text-center text-slate-500 text-sm py-10">{message}</p>;
}
