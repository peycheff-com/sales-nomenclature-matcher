import { ChevronLeft, ChevronRight } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

interface PaginationProps {
  page: number
  totalPages: number
  total: number
  pageSize: number
  onPageChange: (page: number) => void
  className?: string
}

function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPageChange,
  className,
}: PaginationProps) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)

  return (
    <div
      data-slot="pagination"
      className={cn(
        "flex items-center justify-between gap-4 text-sm text-muted-foreground",
        className
      )}
    >
      <span>
        {total > 0
          ? `Показано ${from}\u2013${to} из ${total}`
          : "Нет записей"}
      </span>
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="icon-sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="Предыдущая страница"
        >
          <ChevronLeft />
        </Button>
        <span className="px-2 tabular-nums">
          {page} / {totalPages || 1}
        </span>
        <Button
          variant="outline"
          size="icon-sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label="Следующая страница"
        >
          <ChevronRight />
        </Button>
      </div>
    </div>
  )
}

export { Pagination }
export type { PaginationProps }
