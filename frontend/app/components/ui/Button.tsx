"use client";

import { Loader2 } from "lucide-react";
import { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  fullWidth?: boolean;
}

const variants = {
  primary: "bg-indigo-600 hover:bg-indigo-500 text-white",
  secondary: "bg-slate-700 hover:bg-slate-600 text-white",
  ghost: "text-slate-400 hover:text-slate-200 hover:bg-slate-800",
  danger: "bg-red-600 hover:bg-red-500 text-white",
};

const sizes = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2.5 text-sm",
  lg: "px-4 py-3 text-base",
};

export default function Button({
  loading,
  variant = "primary",
  size = "md",
  fullWidth,
  children,
  className = "",
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={[
        "flex items-center justify-center gap-2 rounded-xl font-medium transition-all",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        variants[variant],
        sizes[size],
        fullWidth ? "w-full" : "",
        className,
      ].join(" ")}
      {...props}
    >
      {loading && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </button>
  );
}
