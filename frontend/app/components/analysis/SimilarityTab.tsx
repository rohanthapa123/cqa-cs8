import { SimilarityResult } from "../../types/analysis";

export default function SimilarityTab({ data }: { data: SimilarityResult[] }) {
  return (
    <div className="rounded-2xl border border-slate-800 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-900 border-b border-slate-800">
          <tr>
            <th className="px-5 py-3.5 text-left font-medium text-slate-400">File A</th>
            <th className="px-5 py-3.5 text-left font-medium text-slate-400">File B</th>
            <th className="px-5 py-3.5 text-left font-medium text-slate-400">Similarity</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60">
          {data.length ? (
            data.map((sim, i) => (
              <tr key={i} className="hover:bg-slate-800/30 transition-colors">
                <td className="px-5 py-3.5 text-slate-300 truncate max-w-[160px] text-xs" title={sim.file_pair[0]}>
                  {sim.file_pair[0].split("/").pop()}
                </td>
                <td className="px-5 py-3.5 text-slate-300 truncate max-w-[160px] text-xs" title={sim.file_pair[1]}>
                  {sim.file_pair[1].split("/").pop()}
                </td>
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-3">
                    <div className="w-20 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full"
                        style={{ width: `${(sim.similarity * 100).toFixed(1)}%` }}
                      />
                    </div>
                    <span className="font-mono text-indigo-400 text-xs">
                      {(sim.similarity * 100).toFixed(1)}%
                    </span>
                  </div>
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={3} className="px-5 py-10 text-center text-slate-500 text-sm">
                Not enough files to compare
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
