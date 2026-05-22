import { AlertCircle, CheckCircle2, Info } from "lucide-react";
import { ReactNode } from "react";

interface AlertProps {
  variant?: "error" | "success" | "info";
  children: ReactNode;
}

const config = {
  error: {
    classes: "bg-red-500/10 border-red-500/20 text-red-400",
    Icon: AlertCircle,
  },
  success: {
    classes: "bg-green-500/10 border-green-500/20 text-green-400",
    Icon: CheckCircle2,
  },
  info: {
    classes: "bg-indigo-500/10 border-indigo-500/20 text-indigo-400",
    Icon: Info,
  },
};

export default function Alert({ variant = "error", children }: AlertProps) {
  const { classes, Icon } = config[variant];
  return (
    <div className={`flex items-start gap-2.5 p-3.5 rounded-xl border text-sm ${classes}`}>
      <Icon className="w-4 h-4 shrink-0 mt-0.5" />
      <span>{children}</span>
    </div>
  );
}
