import { useCallback, useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getReviewQueue } from "@/api/match";
import { listSuppliers } from "@/api/suppliers";
import { reviewItem } from "@/api/review";
import PageLayout from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import { Check, X, ChevronLeft, ChevronRight } from "lucide-react";
import type { ReviewQueueItem, SupplierProfile } from "@/api/types";

const PAGE_SIZE = 20;

const ACTION_MAP: Record<string, "accepted" | "corrected" | "rejected"> = {
  approve: "accepted",
  reject: "rejected",
  correct: "corrected",
};

function confidenceBadge(confidence: number | undefined | null) {
  if (confidence == null) return <Badge variant="secondary">—</Badge>;
  const pct = Math.round(confidence * 100);
  const variant =
    confidence > 0.85 ? "default" : confidence > 0.75 ? "secondary" : "destructive";
  const className =
    confidence > 0.85
      ? "bg-green-600 hover:bg-green-700"
      : confidence > 0.75
        ? "bg-yellow-500 hover:bg-yellow-600 text-black"
        : "";
  return (
    <Badge variant={variant} className={className}>
      {pct}%
    </Badge>
  );
}

export default function ReviewPage() {
  const queryClient = useQueryClient();
  const [supplierId, setSupplierId] = useState<string>("all");
  const [page, setPage] = useState(0);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const suppliersQuery = useQuery({
    queryKey: ["suppliers"],
    queryFn: listSuppliers,
  });

  const reviewQuery = useQuery({
    queryKey: ["review-queue", supplierId, page],
    queryFn: () =>
      getReviewQueue({
        supplier_id: supplierId === "all" ? undefined : supplierId,
        page: page + 1,
        page_size: PAGE_SIZE,
      }),
  });

  const items: ReviewQueueItem[] = reviewQuery.data?.items ?? [];
  const totalCount: number = reviewQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  const mutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "reject" | "correct" }) =>
      reviewItem(id, { final_decision: ACTION_MAP[action] }),
    onSuccess: (_data, variables) => {
      const label = variables.action === "approve" ? "принят" : "отклонён";
      toast.success(`Элемент ${label}`);
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
    },
    onError: () => {
      toast.error("Ошибка при обработке");
    },
  });

  const handleAction = useCallback(
    (item: ReviewQueueItem, action: "approve" | "reject" | "correct") => {
      mutation.mutate({ id: item.request_item_id, action });
    },
    [mutation],
  );

  // Keyboard shortcuts
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")
        return;

      switch (e.key) {
        case "j":
          setSelectedIndex((prev) => Math.min(prev + 1, items.length - 1));
          break;
        case "k":
          setSelectedIndex((prev) => Math.max(prev - 1, 0));
          break;
        case "a": {
          const item = items[selectedIndex];
          if (item) handleAction(item, "approve");
          break;
        }
        case "r": {
          const item = items[selectedIndex];
          if (item) handleAction(item, "reject");
          break;
        }
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [items, selectedIndex, handleAction]);

  // Reset selected index when data changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [page, supplierId]);

  const suppliers: SupplierProfile[] = suppliersQuery.data?.items ?? [];

  return (
    <PageLayout title="Очередь проверки" description="Элементы, ожидающие проверки">
      <div className="space-y-4">
        {/* Toolbar */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Select value={supplierId} onValueChange={(v) => { setSupplierId(v); setPage(0); }}>
              <SelectTrigger className="w-[220px]">
                <SelectValue placeholder="Все поставщики" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Все поставщики</SelectItem>
                {suppliers.map((s) => (
                  <SelectItem key={s.supplier_id} value={s.supplier_id}>
                    {s.supplier_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <span className="text-sm text-muted-foreground">
              Всего: {totalCount}
            </span>
          </div>

          <div className="text-xs text-muted-foreground">
            <kbd className="rounded border px-1">j</kbd>/<kbd className="rounded border px-1">k</kbd> навигация,{" "}
            <kbd className="rounded border px-1">a</kbd> принять,{" "}
            <kbd className="rounded border px-1">r</kbd> отклонить
          </div>
        </div>

        {/* Table */}
        {items.length === 0 && !reviewQuery.isLoading ? (
          <div className="flex items-center justify-center rounded-md border py-12 text-muted-foreground">
            Нет элементов для проверки
          </div>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[35%]">Текст</TableHead>
                  <TableHead className="w-[90px]">Уверенность</TableHead>
                  <TableHead>Поставщик</TableHead>
                  <TableHead>Причина</TableHead>
                  <TableHead>Файл</TableHead>
                  <TableHead className="w-[160px] text-right">Действия</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item, idx) => (
                  <TableRow
                    key={item.request_item_id}
                    className={`cursor-pointer ${idx === selectedIndex ? "bg-muted" : ""}`}
                    onClick={() => setSelectedIndex(idx)}
                  >
                    <TableCell className="font-medium">{item.raw_text}</TableCell>
                    <TableCell>{confidenceBadge(item.confidence)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {item.supplier_id ?? "—"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {item.reasons?.[0] ?? "—"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {item.file_name ?? "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-green-600 hover:text-green-700"
                          onClick={(e) => { e.stopPropagation(); handleAction(item, "approve"); }}
                          disabled={mutation.isPending}
                        >
                          <Check className="mr-1 h-3.5 w-3.5" />
                          Принять
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 text-destructive hover:text-destructive"
                          onClick={(e) => { e.stopPropagation(); handleAction(item, "reject"); }}
                          disabled={mutation.isPending}
                        >
                          <X className="mr-1 h-3.5 w-3.5" />
                          Отклонить
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              Страница {page + 1} из {totalPages}
            </span>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
              >
                <ChevronLeft className="mr-1 h-4 w-4" />
                Назад
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
              >
                Вперёд
                <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
