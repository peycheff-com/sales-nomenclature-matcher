import { AlertCircle, RefreshCw } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

interface QueryErrorBannerProps {
  error: Error | null
  onRetry?: () => void
  title?: string
  className?: string
}

function QueryErrorBanner({
  error,
  onRetry,
  title = "Ошибка загрузки данных",
  className,
}: QueryErrorBannerProps) {
  if (!error) return null

  return (
    <div
      role="alert"
      data-slot="query-error-banner"
      className={cn(
        "flex items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm",
        className
      )}
    >
      <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
      <div className="flex-1 space-y-1">
        <p className="font-medium text-destructive">{title}</p>
        <p className="text-muted-foreground">
          {error.message || "Произошла неизвестная ошибка. Попробуйте позже."}
        </p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="shrink-0">
          <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
          Повторить
        </Button>
      )}
    </div>
  )
}

export { QueryErrorBanner }
export type { QueryErrorBannerProps }
