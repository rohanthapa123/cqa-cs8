import { CheckCircle2 } from "lucide-react";
import { FileBadPractices } from "../../types/analysis";

export default function PracticesTab({ data }: { data: FileBadPractices[] }) {
  const filesWithIssues = data.filter((f) => f.issues.length > 0);

  if (!filesWithIssues.length) {
    return (
      <div className="flex items-center gap-3 p-5 rounded-2xl bg-green-500/10 border border-green-500/20 text-green-400">
        <CheckCircle2 className="w-5 h-5 shrink-0" />
        <p className="font-medium">No bad practices detected</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {filesWithIssues.map((file, i) => (
        <div key={i} className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
          <p className="text-sm font-medium text-rose-300 truncate mb-4" title={file.file_path}>
            {file.file_path.split("/").pop()}{" "}
            <span className="text-slate-500 font-normal">
              ({file.issues.length} issue{file.issues.length !== 1 ? "s" : ""})
            </span>
          </p>
          <div className="space-y-2.5">
            {file.issues.map((issue, j) => (
              <div key={j} className="flex items-start gap-3 text-xs">
                <span className="shrink-0 px-1.5 py-0.5 rounded font-mono bg-slate-800 text-slate-400">
                  L{issue.line}
                </span>
                <span className="shrink-0 px-1.5 py-0.5 rounded bg-rose-500/15 text-rose-400 font-medium">
                  {issue.type}
                </span>
                <span className="text-slate-400">{issue.message}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
