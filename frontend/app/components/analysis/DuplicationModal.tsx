"use client";

import { useEffect } from "react";
import { X, Copy } from "lucide-react";
import { DuplicateBlock, DuplicatePair } from "../../types/analysis";

function CodeBlock({ block }: { block: DuplicateBlock }) {
  const lines = block.code.split("\n");
  return (
    <div className="rounded-lg border border-slate-800 overflow-hidden">
      <div className="px-3 py-1.5 bg-slate-800/60 text-xs text-slate-400 font-mono">
        Lines {block.start}–{block.end}
      </div>
      <pre className="overflow-x-auto text-xs leading-relaxed bg-slate-950/60">
        <code className="block">
          {lines.map((line, i) => (
            <div key={i} className="flex">
              <span className="select-none w-10 shrink-0 pr-3 text-right text-slate-600 border-r border-slate-800">
                {block.start + i}
              </span>
              <span className="pl-3 pr-4 text-slate-300 whitespace-pre">{line || " "}</span>
            </div>
          ))}
        </code>
      </pre>
    </div>
  );
}

function FileColumn({ path, blocks }: { path: string; blocks: DuplicateBlock[] }) {
  return (
    <div className="space-y-3 min-w-0">
      <p className="text-sm font-medium text-indigo-300 truncate" title={path}>
        {path}
      </p>
      {blocks.length ? (
        blocks.map((b, i) => <CodeBlock key={i} block={b} />)
      ) : (
        <p className="text-xs text-slate-600 italic">No duplicated ranges</p>
      )}
    </div>
  );
}

interface Props {
  pair: DuplicatePair;
  onClose: () => void;
}

export default function DuplicationModal({ pair, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-5xl max-h-[85vh] flex flex-col rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 p-4 border-b border-slate-800">
          <Copy className="w-5 h-5 text-indigo-400 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-white">Duplicated code</p>
            <p className="text-xs text-slate-500 truncate">
              {pair.file_a.split("/").pop()} ↔ {pair.file_b.split("/").pop()}
            </p>
          </div>
          <span className="shrink-0 px-2 py-0.5 rounded-md font-mono text-xs bg-indigo-500/15 text-indigo-300">
            {pair.similarity}% similar
          </span>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body: side-by-side code */}
        <div className="p-4 overflow-y-auto grid md:grid-cols-2 gap-4">
          <FileColumn path={pair.file_a} blocks={pair.blocks_a} />
          <FileColumn path={pair.file_b} blocks={pair.blocks_b} />
        </div>
      </div>
    </div>
  );
}
