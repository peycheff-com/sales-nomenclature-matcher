import type { LucideIcon } from "lucide-react";
import { RefreshCw } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
  variant?: "empty" | "no-results" | "error";
  onRetry?: () => void;
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  variant = "empty",
  onRetry,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center p-8 text-center rounded-xl border",
        variant === "error"
          ? "min-h-[200px] border-destructive/30 bg-destructive/5"
          : variant === "no-results"
            ? "min-h-[200px] border-dashed bg-muted/30"
            : "min-h-[300px] border-dashed bg-muted/30",
        className,
      )}
    >
      <div
        className={cn(
          "flex h-16 w-16 items-center justify-center rounded-full mb-4",
          variant === "error"
            ? "bg-destructive/10 text-destructive"
            : "bg-muted/50 text-muted-foreground",
        )}
      >
        <Icon className="h-8 w-8" />
      </div>
      <h3 className="text-xl font-semibold mb-2">{title}</h3>
      <p className="text-muted-foreground mb-6 max-w-sm">{description}</p>
      {variant === "error" && onRetry && (
        <Button variant="outline" onClick={onRetry}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Повторить
        </Button>
      )}
      {variant !== "error" && action && <div>{action}</div>}
    </div>
  );
}
