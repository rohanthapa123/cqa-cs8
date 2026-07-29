import { RepositorySummary } from "../../types/analysis";
import {
  FileCode2, FunctionSquare, Boxes, AlignLeft, Activity, Copy, Gauge,
  ShieldAlert, Type, Trash2, Award,
} from "lucide-react";

function gradeColor(grade: string) {
  switch (grade) {
    case "A": return { ring: "#22c55e", text: "text-green-400" };
    case "B": return { ring: "#84cc16", text: "text-lime-400" };
    case "C": return { ring: "#f59e0b", text: "text-amber-400" };
    case "D": return { ring: "#f97316", text: "text-orange-400" };
    default: return { ring: "#ef4444", text: "text-red-400" };
  }
}

function HealthRing({ score, grade }: { score: number; grade: string }) {
  const { ring, text } = gradeColor(grade);
  const r = 52;
  const c = 2 * Math.PI * r;
  const offset = c - (score / 100) * c;
  return (
    <div className="relative w-32 h-32 shrink-0">
      <svg className="w-32 h-32 -rotate-90" viewBox="0 0 120 120">
        <circle cx="60" cy="60" r={r} fill="none" stroke="#1e293b" strokeWidth="10" />
        <circle
          cx="60" cy="60" r={r} fill="none" stroke={ring} strokeWidth="10"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={offset}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-3xl font-bold ${text}`}>{score}</span>
        <span className="text-xs text-slate-500">Grade {grade}</span>
      </div>
    </div>
  );
}

function Stat({ Icon, label, value }: { Icon: React.ElementType; label: string; value: string | number }) {
  return (
    <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800">
      <div className="flex items-center gap-1.5 text-slate-500 mb-1.5">
        <Icon className="w-3.5 h-3.5" />
        <span className="text-xs">{label}</span>
      </div>
      <p className="text-lg font-semibold text-slate-100">{value}</p>
    </div>
  );
}

export default function SummaryPanel({ summary }: { summary: RepositorySummary }) {
  const h = summary.health_score;
  const components = [
    { key: "maintainability", label: "Maintainability", value: h.components.maintainability, weight: h.weights.maintainability },
    { key: "complexity", label: "Complexity", value: h.components.complexity, weight: h.weights.complexity },
    { key: "duplication", label: "Duplication", value: h.components.duplication, weight: h.weights.duplication },
  ];

  return (
    <div className="space-y-5">
      {/* Health score card */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 flex flex-col sm:flex-row items-center gap-6">
        <HealthRing score={h.score} grade={h.grade} />
        <div className="flex-1 w-full space-y-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-200">Overall Repository Health</h3>
            <p className="text-xs text-slate-500">Weighted from maintainability, complexity and duplication.</p>
          </div>
          <div className="space-y-2">
            {components.map((c) => (
              <div key={c.key} className="flex items-center gap-3 text-xs">
                <span className="w-28 text-slate-400">{c.label}</span>
                <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${c.value}%` }} />
                </div>
                <span className="w-10 text-right font-mono text-slate-300">{c.value}</span>
                <span className="w-10 text-right text-slate-600">{Math.round(c.weight * 100)}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Metric grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat Icon={FileCode2} label="Python Files" value={summary.python_files} />
        <Stat Icon={AlignLeft} label="Lines of Code" value={summary.lines_of_code} />
        <Stat Icon={FunctionSquare} label="Functions" value={summary.total_functions} />
        <Stat Icon={Boxes} label="Classes" value={summary.total_classes} />
        <Stat Icon={Activity} label="Avg Complexity" value={summary.average_complexity} />
        <Stat Icon={Copy} label="Duplication" value={`${summary.duplication_percentage}%`} />
        <Stat Icon={Gauge} label="Avg Maintainability" value={summary.average_maintainability} />
        <Stat Icon={Award} label="Health Grade" value={h.grade} />
        <Stat Icon={ShieldAlert} label="Security Score" value={`${summary.security_score}/100`} />
        <Stat Icon={Type} label="Type Hint Coverage" value={`${summary.type_hint_coverage}%`} />
        <Stat Icon={Trash2} label="Dead Code Items" value={summary.dead_code_items} />
      </div>
    </div>
  );
}
