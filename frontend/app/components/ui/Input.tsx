import { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
}

export default function Input({ label, error, className = "", ...props }: InputProps) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm text-slate-300 font-medium">{label}</label>
      <input
        className={[
          "w-full px-4 py-3 bg-slate-900 border rounded-xl text-slate-200",
          "placeholder:text-slate-600 focus:outline-none focus:ring-1 transition-colors",
          error
            ? "border-red-500 focus:border-red-500 focus:ring-red-500"
            : "border-slate-700 focus:border-indigo-500 focus:ring-indigo-500",
          className,
        ].join(" ")}
        {...props}
      />
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
