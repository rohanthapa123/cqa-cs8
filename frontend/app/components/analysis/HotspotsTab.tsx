import { Flame, GitCommitHorizontal, Link2, Users, AlertTriangle, History } from "lucide-react";
import { HistoryReport, Hotspot } from "../../types/analysis";

const CATEGORY_STYLE: Record<Hotspot["category"], { dot: string; pill: string; fill: string }> = {
  critical: { dot: "bg-red-500", pill: "bg-red-500/15 text-red-400 border-red-500/30", fill: "#ef4444" },
  high: { dot: "bg-orange-500", pill: "bg-orange-500/15 text-orange-400 border-orange-500/30", fill: "#f97316" },
  moderate: { dot: "bg-amber-500", pill: "bg-amber-500/15 text-amber-400 border-amber-500/30", fill: "#f59e0b" },
  low: { dot: "bg-slate-500", pill: "bg-slate-500/15 text-slate-400 border-slate-600/30", fill: "#64748b" },
};

function base(path: string) {
  return path.split("/").pop() ?? path;
}

/**
 * Churn x complexity scatter plot.
 *
 * Churn is drawn on a log scale because it is heavily long-tailed — on a linear
 * axis a single generated file squashes everything else against the origin.
 * The shaded top-right quadrant is the danger zone: complicated code that also
 * changes constantly.
 */
function HotspotScatter({ hotspots }: { hotspots: Hotspot[] }) {
  const W = 460;
  const H = 280;
  const PAD = { top: 16, right: 16, bottom: 34, left: 44 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const maxChurn = Math.max(...hotspots.map((h) => h.churn), 1);
  const maxComplexity = Math.max(...hotspots.map((h) => h.complexity), 1);

  const x = (churn: number) => PAD.left + (Math.log1p(churn) / Math.log1p(maxChurn)) * plotW;
  const y = (complexity: number) => PAD.top + plotH - (complexity / maxComplexity) * plotH;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Churn versus complexity scatter plot">
      {/* danger quadrant */}
      <rect
        x={PAD.left + plotW / 2} y={PAD.top}
        width={plotW / 2} height={plotH / 2}
        fill="#ef4444" fillOpacity="0.06"
      />
      <text x={PAD.left + plotW - 6} y={PAD.top + 14} textAnchor="end" className="fill-red-400/70" fontSize="9">
        danger zone
      </text>

      {/* axes */}
      <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={PAD.top + plotH} stroke="#1e293b" strokeWidth="1" />
      <line x1={PAD.left} y1={PAD.top + plotH} x2={PAD.left + plotW} y2={PAD.top + plotH} stroke="#1e293b" strokeWidth="1" />

      {/* quadrant guides */}
      <line
        x1={PAD.left + plotW / 2} y1={PAD.top} x2={PAD.left + plotW / 2} y2={PAD.top + plotH}
        stroke="#1e293b" strokeWidth="1" strokeDasharray="3 3"
      />
      <line
        x1={PAD.left} y1={PAD.top + plotH / 2} x2={PAD.left + plotW} y2={PAD.top + plotH / 2}
        stroke="#1e293b" strokeWidth="1" strokeDasharray="3 3"
      />

      {/* axis labels */}
      <text x={PAD.left + plotW / 2} y={H - 6} textAnchor="middle" className="fill-slate-500" fontSize="10">
        Churn (lines changed, log scale) →
      </text>
      <text
        x={-(PAD.top + plotH / 2)} y={12} textAnchor="middle"
        transform="rotate(-90)" className="fill-slate-500" fontSize="10"
      >
        Complexity →
      </text>
      <text x={PAD.left - 6} y={PAD.top + 4} textAnchor="end" className="fill-slate-600" fontSize="9">
        {maxComplexity}
      </text>
      <text x={PAD.left - 6} y={PAD.top + plotH} textAnchor="end" className="fill-slate-600" fontSize="9">
        0
      </text>

      {/* points */}
      {hotspots.map((h, i) => (
        <g key={i}>
          <circle
            cx={x(h.churn)} cy={y(h.complexity)}
            r={4 + (h.risk_score / 100) * 8}
            fill={CATEGORY_STYLE[h.category].fill}
            fillOpacity="0.35"
            stroke={CATEGORY_STYLE[h.category].fill}
            strokeWidth="1.5"
          >
            <title>{`${h.file_path}\nrisk ${h.risk_score} · complexity ${h.complexity} · churn ${h.churn} · ${h.commits} commits`}</title>
          </circle>
        </g>
      ))}
    </svg>
  );
}

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-2xl font-bold text-slate-100">{value}</p>
      {hint && <p className="text-[11px] text-slate-600">{hint}</p>}
    </div>
  );
}

export default function HotspotsTab({ data }: { data: HistoryReport }) {
  if (!data.available) {
    return (
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-2">
        <p className="flex items-center gap-2 text-sm font-medium text-slate-300">
          <History className="w-4 h-4 text-slate-500" /> Behavioural analysis unavailable
        </p>
        <p className="text-xs text-slate-500 leading-relaxed">{data.reason}</p>
        <p className="text-xs text-slate-600 leading-relaxed">
          Churn, hotspots, change coupling and bus factor are all derived from the commit log, so
          they need a repository with real history behind it.
        </p>
      </div>
    );
  }

  const bus = data.bus_factor;

  return (
    <div className="space-y-5">
      {/* Overview */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
        <div className="flex flex-wrap gap-x-8 gap-y-4">
          <Stat label="Commits analysed" value={data.commits_analyzed} hint={`over ${data.period_days} days`} />
          <Stat label="Contributors" value={data.contributor_count} />
          <Stat
            label="Critical hotspots"
            value={data.summary.critical_hotspots + data.summary.high_hotspots}
            hint="critical + high"
          />
          <Stat
            label="Bus factor"
            value={bus.repository_bus_factor}
            hint={bus.repository_bus_factor <= 1 ? "single point of failure" : "authors covering 50%"}
          />
        </div>
        <p className="text-[11px] text-slate-600">
          {data.first_commit} → {data.last_commit}
        </p>
      </div>

      {/* Hotspot scatter */}
      {data.hotspots.length > 0 && (
        <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
          <p className="flex items-center gap-2 text-sm font-medium text-slate-200 mb-1">
            <Flame className="w-4 h-4 text-orange-400" /> Hotspots
          </p>
          <p className="text-xs text-slate-500 mb-4">
            Churn × complexity. Complex code that nobody touches is cheap to leave alone; complex
            code that changes every week is where defects breed.
          </p>
          <HotspotScatter hotspots={data.hotspots} />

          <div className="mt-4 space-y-1.5">
            {data.hotspots.slice(0, 12).map((h, i) => (
              <div key={i} className="flex items-center gap-3 text-xs">
                <span className={`w-2 h-2 rounded-full shrink-0 ${CATEGORY_STYLE[h.category].dot}`} />
                <span className="text-slate-300 truncate flex-1 min-w-0" title={h.file_path}>
                  {base(h.file_path)}
                  <span className="text-slate-600"> · CC {h.complexity} · {h.commits} commits · {h.churn} lines</span>
                </span>
                <span className={`shrink-0 px-1.5 py-0.5 rounded border font-mono text-[10px] ${CATEGORY_STYLE[h.category].pill}`}>
                  {h.risk_score}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Churn */}
      {data.churn_files.length > 0 && (
        <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
          <p className="flex items-center gap-2 text-sm font-medium text-slate-200 mb-1">
            <GitCommitHorizontal className="w-4 h-4 text-indigo-400" /> Most-changed files
          </p>
          <p className="text-xs text-slate-500 mb-4">Where the team actually spends its effort.</p>
          <div className="space-y-2">
            {data.churn_files.slice(0, 12).map((f, i) => {
              const width = (f.churn / (data.churn_files[0]?.churn || 1)) * 100;
              return (
                <div key={i} className="space-y-1">
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="text-slate-300 truncate min-w-0" title={f.file_path}>
                      {base(f.file_path)}
                    </span>
                    <span className="shrink-0 font-mono text-slate-500">
                      {f.commits} commits · <span className="text-green-400">+{f.insertions}</span>{" "}
                      <span className="text-rose-400">−{f.deletions}</span>
                    </span>
                  </div>
                  <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${width}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Change coupling */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
        <p className="flex items-center gap-2 text-sm font-medium text-slate-200 mb-1">
          <Link2 className="w-4 h-4 text-violet-400" /> Change coupling
        </p>
        <p className="text-xs text-slate-500 mb-4">
          Files habitually committed together. These are implicit dependencies the import graph
          cannot see — change one and you probably have to change the other.
        </p>
        {data.coupling.length === 0 ? (
          <p className="text-xs text-slate-600 italic">No significant coupling detected.</p>
        ) : (
          <div className="space-y-2">
            {data.coupling.map((c, i) => (
              <div key={i} className="p-3 rounded-xl bg-slate-950/40 border border-slate-800/80">
                <div className="flex items-center gap-2 text-xs mb-1.5">
                  <span className="font-mono text-slate-300 truncate" title={c.file_a}>{base(c.file_a)}</span>
                  <Link2 className="w-3 h-3 shrink-0 text-slate-600" />
                  <span className="font-mono text-slate-300 truncate" title={c.file_b}>{base(c.file_b)}</span>
                  <span className="ml-auto shrink-0 font-mono text-violet-400">{c.degree}%</span>
                </div>
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div className="h-full bg-violet-500 rounded-full" style={{ width: `${c.degree}%` }} />
                </div>
                <p className="mt-1 text-[11px] text-slate-600">
                  changed together {c.co_changes} times ({c.commits_a} / {c.commits_b} commits each)
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Knowledge distribution */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
        <p className="flex items-center gap-2 text-sm font-medium text-slate-200 mb-1">
          <Users className="w-4 h-4 text-sky-400" /> Knowledge distribution
        </p>
        <p className="text-xs text-slate-500 mb-4">
          A bus factor of {bus.repository_bus_factor} means {bus.repository_bus_factor} contributor
          {bus.repository_bus_factor === 1 ? "" : "s"} account for half of all the work in this repository.
        </p>

        <div className="space-y-2 mb-5">
          {bus.top_contributors.map((c, i) => (
            <div key={i} className="space-y-1">
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="text-slate-300 truncate min-w-0">{c.author}</span>
                <span className="shrink-0 font-mono text-slate-500">
                  {c.share}% · {c.commits} commits
                </span>
              </div>
              <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div className="h-full bg-sky-500 rounded-full" style={{ width: `${c.share}%` }} />
              </div>
            </div>
          ))}
        </div>

        {bus.at_risk_files.length > 0 && (
          <div className="p-3.5 rounded-xl bg-amber-500/5 border border-amber-500/20">
            <p className="flex items-center gap-2 text-xs font-medium text-amber-300 mb-2.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              {bus.at_risk_count} file{bus.at_risk_count !== 1 ? "s" : ""} with concentrated ownership
            </p>
            <div className="space-y-1.5">
              {bus.at_risk_files.map((f, i) => (
                <div key={i} className="flex items-center gap-3 text-xs">
                  <span className="text-slate-300 truncate flex-1 min-w-0" title={f.file_path}>
                    {base(f.file_path)}
                  </span>
                  <span className="shrink-0 text-slate-500 truncate max-w-[9rem]">{f.primary_author}</span>
                  <span className="shrink-0 font-mono text-amber-400">{f.primary_author_share}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
