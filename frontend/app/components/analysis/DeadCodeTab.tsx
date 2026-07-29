import { CheckCircle2, Trash2, PackageX, Variable, SkipForward, Info } from "lucide-react";
import { DeadCodeReport, DeadDefinition } from "../../types/analysis";

const CONFIDENCE_STYLE: Record<DeadDefinition["confidence"], string> = {
  high: "bg-red-500/15 text-red-400 border-red-500/30",
  medium: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  low: "bg-slate-500/15 text-slate-400 border-slate-600/30",
};

function base(path: string) {
  return path.split("/").pop() ?? path;
}

function Section({
  Icon,
  title,
  description,
  count,
  children,
}: {
  Icon: React.ElementType;
  title: string;
  description: string;
  count: number;
  children: React.ReactNode;
}) {
  if (count === 0) return null;
  return (
    <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
      <p className="flex items-center gap-2 text-sm font-medium text-slate-200 mb-1">
        <Icon className="w-4 h-4 text-indigo-400" /> {title}
        <span className="text-slate-600 font-normal">({count})</span>
      </p>
      <p className="text-xs text-slate-500 mb-4">{description}</p>
      {children}
    </div>
  );
}

export default function DeadCodeTab({ data }: { data: DeadCodeReport }) {
  const unreferenced = [...data.dead_functions, ...data.dead_classes];

  if (data.total_items === 0) {
    return (
      <div className="flex items-center gap-3 p-5 rounded-2xl bg-green-500/10 border border-green-500/20 text-green-400">
        <CheckCircle2 className="w-5 h-5 shrink-0" />
        <p className="font-medium">No dead code detected</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Summary */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
        <div className="flex flex-wrap gap-x-8 gap-y-4">
          <div>
            <p className="text-xs text-slate-500">Total items</p>
            <p className="text-3xl font-bold text-slate-100">{data.total_items}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500">Dead lines</p>
            <p className="text-3xl font-bold text-slate-100">{data.dead_lines}</p>
            <p className="text-[11px] text-slate-600">{data.dead_code_percentage}% of the codebase</p>
          </div>
          <div>
            <p className="text-xs text-slate-500">High confidence</p>
            <p className="text-3xl font-bold text-rose-400">{data.high_confidence_count}</p>
            <p className="text-[11px] text-slate-600">safe to remove</p>
          </div>
        </div>

        <div className="flex items-start gap-2 p-2.5 rounded-lg bg-slate-950/40 border border-slate-800">
          <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-slate-500" />
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Reachability is computed across the whole project, and self-references are discounted so
            a recursive function nobody calls is still reported. Python is dynamic, though — plugin
            registries and runtime <span className="font-mono">getattr</span> can reach code that
            looks unreferenced, which is what the confidence level is telling you.
          </p>
        </div>
      </div>

      <Section
        Icon={Trash2}
        title="Unreferenced definitions"
        description="Functions and classes no other code in the repository ever names."
        count={unreferenced.length}
      >
        <div className="space-y-1.5">
          {unreferenced.map((d, i) => (
            <div key={i} className="flex items-center gap-3 text-xs">
              <span className="shrink-0 px-1.5 py-0.5 rounded bg-slate-800 text-slate-500 text-[10px]">
                {d.kind}
              </span>
              <span className="font-mono text-slate-300 truncate min-w-0">
                {d.owner ? `${d.owner}.` : ""}{d.name}
              </span>
              <span className="text-slate-600 truncate min-w-0" title={d.file_path}>
                {base(d.file_path)}:{d.lineno}
              </span>
              <span className="ml-auto shrink-0 text-slate-600">{d.lines} lines</span>
              <span className={`shrink-0 px-1.5 py-0.5 rounded border text-[10px] ${CONFIDENCE_STYLE[d.confidence]}`}>
                {d.confidence}
              </span>
            </div>
          ))}
        </div>
      </Section>

      <Section
        Icon={PackageX}
        title="Unused imports"
        description="Module-level bindings the file never reads. Imports marked # noqa are left alone."
        count={data.unused_imports.length}
      >
        <div className="space-y-1.5">
          {data.unused_imports.map((imp, i) => (
            <div key={i} className="flex items-center gap-3 text-xs">
              <span className="shrink-0 px-1.5 py-0.5 rounded font-mono bg-slate-800 text-slate-500 text-[10px]">
                L{imp.lineno}
              </span>
              <span className="font-mono text-slate-400 truncate min-w-0">{imp.statement}</span>
              <span className="ml-auto shrink-0 text-slate-600 truncate max-w-[10rem]" title={imp.file_path}>
                {base(imp.file_path)}
              </span>
            </div>
          ))}
        </div>
      </Section>

      <Section
        Icon={Variable}
        title="Unused local variables"
        description="Assigned inside a function and never read afterwards."
        count={data.unused_locals.length}
      >
        <div className="space-y-1.5">
          {data.unused_locals.map((v, i) => (
            <div key={i} className="flex items-center gap-3 text-xs">
              <span className="shrink-0 px-1.5 py-0.5 rounded font-mono bg-slate-800 text-slate-500 text-[10px]">
                L{v.lineno}
              </span>
              <span className="font-mono text-slate-300">{v.name}</span>
              <span className="text-slate-600 truncate min-w-0">in {v.function}()</span>
              <span className="ml-auto shrink-0 text-slate-600 truncate max-w-[10rem]" title={v.file_path}>
                {base(v.file_path)}
              </span>
            </div>
          ))}
        </div>
      </Section>

      <Section
        Icon={SkipForward}
        title="Unreachable statements"
        description="Code that follows an unconditional return, raise, break or continue."
        count={data.unreachable_code.length}
      >
        <div className="space-y-1.5">
          {data.unreachable_code.map((u, i) => (
            <div key={i} className="flex items-center gap-3 text-xs">
              <span className="shrink-0 px-1.5 py-0.5 rounded font-mono bg-slate-800 text-slate-500 text-[10px]">
                L{u.lineno}
              </span>
              <span className="text-slate-400">
                {u.statements} statement{u.statements !== 1 ? "s" : ""} after{" "}
                <span className="font-mono text-rose-400">{u.after}</span> on L{u.after_line}
              </span>
              <span className="ml-auto shrink-0 text-slate-600 truncate max-w-[10rem]" title={u.file_path}>
                {base(u.file_path)}
              </span>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}
