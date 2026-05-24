import { CheckCircle2, XCircle, FileCode } from "lucide-react";
import { TestCoverage } from "../../types/analysis";

export default function TestsTab({ data }: { data: TestCoverage }) {
  return (
    <div className="space-y-5">
      {/* Status banner */}
      <div
        className={[
          "flex items-center gap-3 p-5 rounded-2xl border",
          data.has_tests
            ? "bg-green-500/10 border-green-500/20 text-green-400"
            : "bg-red-500/10 border-red-500/20 text-red-400",
        ].join(" ")}
      >
        {data.has_tests ? (
          <CheckCircle2 className="w-5 h-5 shrink-0" />
        ) : (
          <XCircle className="w-5 h-5 shrink-0" />
        )}
        <div>
          <p className="font-semibold">
            {data.has_tests ? `${data.test_count} test file${data.test_count !== 1 ? "s" : ""} found` : "No tests found"}
          </p>
          <p className="text-sm opacity-75 mt-0.5">
            {data.has_tests
              ? "Test files follow test_*.py or *_test.py naming convention."
              : "No files matching test_*.py or *_test.py were detected. Consider adding tests."}
          </p>
        </div>
      </div>

      {/* File list */}
      {data.has_tests && (
        <div className="rounded-2xl border border-slate-800 overflow-hidden">
          <div className="px-5 py-3 bg-slate-900 border-b border-slate-800">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Test files</p>
          </div>
          <ul className="divide-y divide-slate-800/60">
            {data.test_files.map((fp, i) => (
              <li key={i} className="flex items-center gap-3 px-5 py-3 hover:bg-slate-800/30 transition-colors">
                <FileCode className="w-4 h-4 text-indigo-400 shrink-0" />
                <span className="text-sm text-slate-300 font-mono truncate" title={fp}>
                  {fp.split("/").slice(-2).join("/")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
