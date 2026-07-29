"use client";

import { useEffect, useMemo, useState } from "react";
import { TrendingUp, TrendingDown, Minus, History, ArrowRight } from "lucide-react";
import api, { apiErrorMessage } from "../../api";
import { ComparisonReport, MetricChange, TrendSeries } from "../../types/analysis";

const DIRECTION_STYLE: Record<MetricChange["direction"], { text: string; Icon: React.ElementType }> = {
  improved: { text: "text-green-400", Icon: TrendingUp },
  regressed: { text: "text-rose-400", Icon: TrendingDown },
  unchanged: { text: "text-slate-500", Icon: Minus },
  changed: { text: "text-slate-400", Icon: ArrowRight },
};

const VERDICT_STYLE: Record<ComparisonReport["verdict"], { box: string; label: string }> = {
  improved: { box: "bg-green-500/10 border-green-500/20 text-green-400", label: "Improved" },
  regressed: { box: "bg-rose-500/10 border-rose-500/20 text-rose-400", label: "Regressed" },
  unchanged: { box: "bg-slate-800/40 border-slate-700 text-slate-300", label: "No material change" },
  baseline: { box: "bg-indigo-500/10 border-indigo-500/20 text-indigo-300", label: "Baseline" },
};

function ChangeRow({ change }: { change: MetricChange }) {
  const { text, Icon } = DIRECTION_STYLE[change.direction];
  const sign = change.delta > 0 ? "+" : "";

  return (
    <div className="flex items-center gap-3 text-xs py-1.5">
      <Icon className={`w-3.5 h-3.5 shrink-0 ${text}`} />
      <span className="text-slate-300 truncate min-w-0 flex-1">{change.label}</span>
      <span className="shrink-0 font-mono text-slate-500">
        {change.before}
        {change.unit}
      </span>
      <ArrowRight className="w-3 h-3 shrink-0 text-slate-700" />
      <span className="shrink-0 font-mono text-slate-300">
        {change.after}
        {change.unit}
      </span>
      <span className={`shrink-0 w-20 text-right font-mono ${text}`}>
        {change.direction === "unchanged" ? "—" : `${sign}${change.delta}${change.unit}`}
      </span>
    </div>
  );
}

/** Sparkline of one metric across every stored run for this repository. */
function TrendChart({ series, metricKey, label }: { series: TrendSeries; metricKey: string; label: string }) {
  const W = 460;
  const H = 150;
  const PAD = { top: 14, right: 14, bottom: 24, left: 40 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const values = series.points.map((p) => Number(p[metricKey] ?? 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat series would divide by zero, so give it an artificial band.
  const span = max - min || Math.max(1, Math.abs(max) * 0.1);
  const lo = min - span * 0.1;
  const hi = max + span * 0.1;

  const x = (i: number) => PAD.left + (values.length === 1 ? plotW / 2 : (i / (values.length - 1)) * plotW);
  const y = (v: number) => PAD.top + plotH - ((v - lo) / (hi - lo)) * plotH;

  const line = values.map((v, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(v)}`).join(" ");
  const area = `${line} L ${x(values.length - 1)} ${PAD.top + plotH} L ${x(0)} ${PAD.top + plotH} Z`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label={`${label} over time`}>
      <defs>
        <linearGradient id={`grad-${metricKey}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6366f1" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
        </linearGradient>
      </defs>

      <line x1={PAD.left} y1={PAD.top + plotH} x2={PAD.left + plotW} y2={PAD.top + plotH} stroke="#1e293b" />
      <text x={PAD.left - 6} y={PAD.top + 4} textAnchor="end" className="fill-slate-600" fontSize="9">
        {Math.round(hi)}
      </text>
      <text x={PAD.left - 6} y={PAD.top + plotH} textAnchor="end" className="fill-slate-600" fontSize="9">
        {Math.round(lo)}
      </text>

      <path d={area} fill={`url(#grad-${metricKey})`} />
      <path d={line} fill="none" stroke="#6366f1" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />

      {values.map((v, i) => (
        <circle key={i} cx={x(i)} cy={y(v)} r="3" fill="#6366f1" stroke="#0f172a" strokeWidth="1.5">
          <title>{`${series.points[i].date?.toString().split("T")[0]} · ${label}: ${v}`}</title>
        </circle>
      ))}
    </svg>
  );
}

interface Props {
  repoName: string;
  comparison: ComparisonReport | null;
}

export default function TrendsTab({ repoName, comparison }: Props) {
  const [series, setSeries] = useState<TrendSeries | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [metricKey, setMetricKey] = useState("health_score");

  useEffect(() => {
    let cancelled = false;

    (async () => {
      setLoading(true);
      setError("");
      try {
        const res = await api.get<TrendSeries>("/analyses/trend", { params: { repo_name: repoName } });
        if (!cancelled) setSeries(res.data);
      } catch (e) {
        if (!cancelled) setError(apiErrorMessage(e, "Could not load the analysis history."));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [repoName]);

  const headlineChanges = useMemo(
    () => (comparison?.changes ?? []).filter((c) => c.headline),
    [comparison]
  );
  const otherChanges = useMemo(
    () => (comparison?.changes ?? []).filter((c) => !c.headline),
    [comparison]
  );

  const chartMetrics = series?.metrics.filter((m) => m.headline) ?? [];
  const activeMetric = chartMetrics.find((m) => m.key === metricKey) ?? chartMetrics[0];

  return (
    <div className="space-y-5">
      {/* Verdict + change table */}
      {comparison && (
        <div className="space-y-4">
          <div className={`p-4 rounded-2xl border ${VERDICT_STYLE[comparison.verdict].box}`}>
            <p className="font-semibold text-sm">{VERDICT_STYLE[comparison.verdict].label}</p>
            {comparison.reason ? (
              <p className="text-xs opacity-80 mt-0.5">{comparison.reason}</p>
            ) : (
              <p className="text-xs opacity-80 mt-0.5">
                {comparison.regressions.length} regression(s), {comparison.improvements.length} improvement(s)
                since the previous run.
              </p>
            )}
          </div>

          {comparison.available && (
            <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
              <p className="text-sm font-medium text-slate-200 mb-3">Change since the previous run</p>
              <div className="divide-y divide-slate-800/70">
                {headlineChanges.map((c) => (
                  <ChangeRow key={c.metric} change={c} />
                ))}
              </div>
              {otherChanges.length > 0 && (
                <>
                  <p className="text-xs text-slate-500 mt-4 mb-1">Counts</p>
                  <div className="divide-y divide-slate-800/70">
                    {otherChanges.map((c) => (
                      <ChangeRow key={c.metric} change={c} />
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* History chart */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800">
        <p className="flex items-center gap-2 text-sm font-medium text-slate-200 mb-1">
          <History className="w-4 h-4 text-indigo-400" /> Metric history
        </p>
        <p className="text-xs text-slate-500 mb-4">
          Every analysis of <span className="font-mono text-slate-400">{repoName}</span>, oldest first.
        </p>

        {loading ? (
          <p className="text-xs text-slate-500 py-6 text-center">Loading history…</p>
        ) : error ? (
          <p className="text-xs text-rose-400 py-6 text-center">{error}</p>
        ) : !series || series.run_count < 2 ? (
          <p className="text-xs text-slate-500 py-6 text-center">
            {series?.run_count === 1
              ? "Only one run so far — analyse this repository again to start a trend."
              : "No stored runs yet."}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-1.5 mb-4">
              {chartMetrics.map((m) => (
                <button
                  key={m.key}
                  onClick={() => setMetricKey(m.key)}
                  className={[
                    "px-2.5 py-1 rounded-lg text-xs font-medium transition-colors",
                    (activeMetric?.key === m.key)
                      ? "bg-indigo-600 text-white"
                      : "bg-slate-800/60 text-slate-400 hover:text-slate-200",
                  ].join(" ")}
                >
                  {m.label}
                </button>
              ))}
            </div>

            {activeMetric && (
              <TrendChart series={series} metricKey={activeMetric.key} label={activeMetric.label} />
            )}

            <p className="text-[11px] text-slate-600 mt-2 text-center">
              {series.run_count} run(s) · {series.points[0]?.date?.toString().split("T")[0]} →{" "}
              {series.points[series.points.length - 1]?.date?.toString().split("T")[0]}
            </p>
          </>
        )}
      </div>
    </div>
  );
}
