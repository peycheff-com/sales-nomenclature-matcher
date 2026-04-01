import type { MatchRequestDetails } from "@/api/types";
import { REQUEST_STATUS_LABELS } from "@/lib/constants";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface StatsBarProps {
  request: MatchRequestDetails;
}

export default function StatsBar({ request }: StatsBarProps) {
  const pct =
    request.total_items > 0
      ? Math.round((request.processed_items / request.total_items) * 100)
      : 0;

  const requestStatusColor: Record<string, string> = {
    queued: "bg-gray-100 text-gray-800",
    running: "bg-blue-100 text-blue-800",
    done: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card p-4">
      <Badge
        variant="outline"
        className={cn("text-xs", requestStatusColor[request.status])}
      >
        {REQUEST_STATUS_LABELS[request.status] ?? request.status}
      </Badge>

      <div className="text-sm text-muted-foreground">
        Обработано: <span className="font-medium text-foreground">{request.processed_items}</span>{" "}
        из {request.total_items} ({pct}%)
      </div>

      <div className="flex items-center gap-3 text-sm">
        <span className="text-green-700">
          Найдено: <strong>{request.auto_matched_items}</strong>
        </span>
        <span className="text-yellow-700">
          На проверку: <strong>{request.review_needed_items}</strong>
        </span>
        <span className="text-red-700">
          Не найдено: <strong>{request.no_match_items}</strong>
        </span>
      </div>

      {request.status === "running" && (
        <div className="ml-auto h-2 w-40 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}
