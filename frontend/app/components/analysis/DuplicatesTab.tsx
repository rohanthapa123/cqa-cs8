"use client";

import { useState } from "react";
import { Copy, Code2 } from "lucide-react";
import { DuplicateBlock, DuplicatePair, DuplicationReport } from "../../types/analysis";
import DuplicationModal from "./DuplicationModal";

function fmtRanges(blocks: DuplicateBlock[]) {
  if (!blocks.length) return "—";
  return blocks.map((b) => (b.start === b.end ? `${b.start}` : `${b.start}–${b.end}`)).join(", ");
}

export default function DuplicatesTab({ data }: { data: DuplicationReport }) {
  const [active, setActive] = useState<DuplicatePair | null>(null);

  return (
    <div className="space-y-5">
      {/* Overall duplication */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 flex flex-wrap items-center gap-6">
        <div>
          <p className="text-xs text-slate-500">Overall duplication</p>
          <p className="text-2xl font-bold text-slate-100">{data.duplication_percentage}%</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Duplicated lines</p>
          <p className="text-2xl font-bold text-slate-100">
            {data.duplicated_lines}
            <span className="text-sm text-slate-500"> / {data.total_lines}</span>
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Duplicate pairs</p>
          <p className="text-2xl font-bold text-slate-100">{data.pair_count}</p>
        </div>
        <p className="w-full text-xs text-slate-600">
          Detected with the Winnowing fingerprinting algorithm over AST-normalized tokens.
        </p>
      </div>

      {/* Duplicate pairs + line ranges */}
      {data.duplicate_pairs.length ? (
        <div className="space-y-3">
          {data.duplicate_pairs.map((p, i) => (
            <div key={i} className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800">
              <div className="flex items-center justify-between gap-3 mb-3">
                <div className="flex items-center gap-2 min-w-0 text-xs text-slate-300">
                  <Copy className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                  <span className="truncate" title={p.file_a}>{p.file_a.split("/").pop()}</span>
                  <span className="text-slate-600">↔</span>
                  <span className="truncate" title={p.file_b}>{p.file_b.split("/").pop()}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="px-2 py-0.5 rounded-md font-mono text-xs bg-indigo-500/15 text-indigo-300">
                    {p.similarity}%
                  </span>
                  <button
                    onClick={() => setActive(p)}
                    className="flex items-center gap-1 px-2 py-1 rounded-md text-xs bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
                  >
                    <Code2 className="w-3.5 h-3.5" /> View code
                  </button>
                </div>
              </div>
              <div className="grid sm:grid-cols-2 gap-2 text-xs">
                <div className="text-slate-500">
                  <span className="text-slate-400">Lines in {p.file_a.split("/").pop()}: </span>
                  <span className="font-mono text-slate-300">{fmtRanges(p.blocks_a)}</span>
                </div>
                <div className="text-slate-500">
                  <span className="text-slate-400">Lines in {p.file_b.split("/").pop()}: </span>
                  <span className="font-mono text-slate-300">{fmtRanges(p.blocks_b)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-center text-slate-500 text-sm py-10">No significant duplication detected</p>
      )}

      {active && <DuplicationModal pair={active} onClose={() => setActive(null)} />}
    </div>
  );
}
