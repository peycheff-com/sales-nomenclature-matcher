import { Badge } from "@/components/ui/badge";
import { STATUS_COLORS, STATUS_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: "auto_match" | "review_needed" | "no_match";
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <Badge variant="outline" className={cn("text-xs", STATUS_COLORS[status])}>
      {STATUS_LABELS[status] ?? status}
    </Badge>
  );
}
