import Link from "next/link";
import { Code2, GitBranch, Zap, Shield, BarChart3, ArrowRight, GitFork } from "lucide-react";

const features = [
  {
    icon: BarChart3,
    title: "Cyclomatic Complexity",
    description: "Per-function complexity scores. Spot high-risk code that's hard to test or maintain.",
    color: "indigo",
  },
  {
    icon: GitBranch,
    title: "Duplicate Detection",
    description: "TF-IDF + cosine similarity surfaces copy-pasted files and structural clones.",
    color: "violet",
  },
  {
    icon: Zap,
    title: "Time Complexity",
    description: "AST-based Big-O analysis per function. Finds O(n²) loops and recursive bottlenecks.",
    color: "amber",
  },
  {
    icon: Shield,
    title: "Bad Practices",
    description: "Catches bare excepts, mutable defaults, wildcard imports, eval/exec, and more.",
    color: "rose",
  },
];

const steps = [
  { n: "01", title: "Connect GitHub", desc: "OAuth in one click. We never store your code." },
  { n: "02", title: "Pick a Repo", desc: "Select any Python repository from your account." },
  { n: "03", title: "Get Insights", desc: "Full analysis report in seconds, not minutes." },
];

const colorMap: Record<string, string> = {
  indigo: "bg-indigo-500/10 text-indigo-400 ring-1 ring-indigo-500/20",
  violet: "bg-violet-500/10 text-violet-400 ring-1 ring-violet-500/20",
  amber: "bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20",
  rose: "bg-rose-500/10 text-rose-400 ring-1 ring-rose-500/20",
};

export default function Home() {
  return (
    <div className="min-h-screen selection:bg-indigo-500/30">
      {/* Hero */}
      <section className="relative overflow-hidden pt-24 pb-32 px-6">
        <div className="absolute inset-0 -z-10 pointer-events-none">
          <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[700px] h-[700px] bg-indigo-600/10 rounded-full blur-3xl" />
          <div className="absolute top-1/3 left-1/4 w-[400px] h-[400px] bg-violet-600/8 rounded-full blur-3xl" />
        </div>

        <div className="max-w-4xl mx-auto text-center space-y-8">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-500/10 ring-1 ring-indigo-500/20 text-indigo-300 text-sm font-medium">
            <Code2 className="w-3.5 h-3.5" />
            Python code intelligence
          </div>

          <h1 className="text-5xl md:text-7xl font-bold tracking-tight leading-[1.08]">
            <span className="bg-gradient-to-b from-white to-slate-400 bg-clip-text text-transparent">
              Understand your
            </span>
            <br />
            <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-indigo-400 bg-clip-text text-transparent">
              codebase deeply
            </span>
          </h1>

          <p className="text-xl text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Connect your GitHub, pick a Python repo, and get instant analysis — complexity,
            duplicates, time complexity, and bad practices in one report.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-2">
            <Link
              href="/signup"
              className="flex items-center gap-2 px-7 py-3.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-semibold text-base transition-all shadow-lg shadow-indigo-500/20 hover:shadow-indigo-500/40 hover:-translate-y-0.5"
            >
              Get started free
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/login"
              className="flex items-center gap-2 px-7 py-3.5 bg-slate-800/60 hover:bg-slate-800 text-slate-200 rounded-xl font-semibold text-base transition-all ring-1 ring-slate-700"
            >
              <GitFork className="w-4 h-4" />
              Sign in
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="px-6 pb-28">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14 space-y-3">
            <h2 className="text-3xl font-bold text-white">Four lenses on your code</h2>
            <p className="text-slate-400">Everything you need to ship with confidence.</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {features.map(({ icon: Icon, title, description, color }) => (
              <div
                key={title}
                className="group p-6 rounded-2xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 transition-all hover:-translate-y-1 duration-200"
              >
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-4 ${colorMap[color]}`}>
                  <Icon className="w-5 h-5" />
                </div>
                <h3 className="font-semibold text-white mb-2">{title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="px-6 pb-28">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-14 space-y-3">
            <h2 className="text-3xl font-bold text-white">How it works</h2>
            <p className="text-slate-400">Three steps to a full report.</p>
          </div>
          <div className="grid sm:grid-cols-3 gap-10 relative">
            <div className="hidden sm:block absolute top-8 left-[33%] right-[33%] h-px bg-gradient-to-r from-transparent via-slate-700 to-transparent" />
            {steps.map(({ n, title, desc }) => (
              <div key={n} className="text-center space-y-3">
                <div className="w-16 h-16 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center mx-auto text-2xl font-bold text-indigo-400 font-mono">
                  {n}
                </div>
                <h3 className="font-semibold text-white">{title}</h3>
                <p className="text-sm text-slate-400">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 pb-32">
        <div className="max-w-2xl mx-auto text-center p-12 rounded-3xl bg-gradient-to-b from-slate-900 to-slate-950 border border-slate-800 space-y-6">
          <h2 className="text-3xl font-bold text-white">Start analyzing in seconds</h2>
          <p className="text-slate-400">No credit card. No install. Just connect GitHub and go.</p>
          <Link
            href="/signup"
            className="inline-flex items-center gap-2 px-8 py-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-semibold text-base transition-all shadow-lg shadow-indigo-500/20 hover:-translate-y-0.5"
          >
            Create free account
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
