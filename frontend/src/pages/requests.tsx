import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Trash2, Copy, Check, FileSearch, Calendar } from "lucide-react";
import { toast } from "sonner";
import { listMatchRequests, deleteMatchRequest } from "@/api/match";
import { listSuppliers } from "@/api/suppliers";
import { REQUEST_STATUS_LABELS } from "@/lib/constants";
import { formatDate } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Pagination } from "@/components/ui/pagination";
import { QueryErrorBanner } from "@/components/ui/query-error-banner";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SkeletonTable } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { PageLayout } from "@/components/layout/page-layout";
import { EmptyState } from "@/components/ui/empty-state";

const PAGE_SIZE = 20;

export default function RequestsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("all");
  const [supplierFilter, setSupplierFilter] = useState("__all__");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState("all");

  const createdAfter = dateRange === "7d"
    ? new Date(Date.now() - 7 * 86400000).toISOString()
    : dateRange === "30d"
    ? new Date(Date.now() - 30 * 86400000).toISOString()
    : undefined;

  const requestsQuery = useQuery({
    queryKey: ["match-requests", page, statusFilter, supplierFilter, dateRange],
    queryFn: () => listMatchRequests({
      page,
      limit: PAGE_SIZE,
      status: statusFilter,
      supplier_id: supplierFilter,
      created_after: createdAfter,
    }),
    refetchInterval: 10_000,
  });

  const suppliersQuery = useQuery({
    queryKey: ["suppliers"],
    queryFn: listSuppliers,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteMatchRequest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["match-requests"] });
      setDeleteTarget(null);
      toast.success("Запрос успешно удален");
    },
    onError: () => {
      setDeleteTarget(null);
      toast.error("Не удалось удалить запрос");
    },
  });

  const requests = requestsQuery.data?.items ?? [];
  const total = requestsQuery.data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;

  const suppliersMap = new Map(suppliersQuery.data?.items.map(s => [s.supplier_id, s.supplier_name]));

  const statusColor: Record<string, string> = {
    queued: "bg-gray-100 text-gray-800",
    running: "bg-blue-100 text-blue-800",
    done: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };

  const copyToClipboard = (e: React.MouseEvent, text: string) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedId(text);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <PageLayout
      title="Запросы на сопоставление"
      description="История загрузок и результаты."
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <Select value={statusFilter} onValueChange={(val) => { setStatusFilter((val || "all") as string); setPage(1); }}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Статус" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Все статусы</SelectItem>
              <SelectItem value="queued">В очереди</SelectItem>
              <SelectItem value="running">Обрабатывается</SelectItem>
              <SelectItem value="done">Завершено</SelectItem>
              <SelectItem value="failed">Ошибка</SelectItem>
            </SelectContent>
          </Select>
          
          <Select value={supplierFilter} onValueChange={(val) => { setSupplierFilter((val || "__all__") as string); setPage(1); }}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Поставщик" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">Все поставщики</SelectItem>
              {suppliersQuery.data?.items.map(s => (
                <SelectItem key={s.supplier_id} value={s.supplier_id}>{s.supplier_name}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={dateRange} onValueChange={(val) => { setDateRange(val || "all"); setPage(1); }}>
            <SelectTrigger className="w-[160px]">
              <Calendar className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
              <SelectValue placeholder="Период" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Всё время</SelectItem>
              <SelectItem value="7d">За 7 дней</SelectItem>
              <SelectItem value="30d">За 30 дней</SelectItem>
            </SelectContent>
          </Select>
        </div>
      }
    >

      {requestsQuery.isLoading ? (
        <SkeletonTable rows={5} columns={7} />
      ) : requestsQuery.isError ? (
        <QueryErrorBanner error={requestsQuery.error} onRetry={() => requestsQuery.refetch()} />
      ) : requests.length === 0 && (statusFilter !== "all" || supplierFilter !== "__all__" || dateRange !== "all") ? (
        <EmptyState
          icon={FileSearch}
          title="Ничего не найдено"
          description="Попробуйте изменить параметры фильтрации"
          variant="no-results"
        />
      ) : requests.length === 0 ? (
        <EmptyState
          icon={FileSearch}
          title="Нет запросов"
          description="Создайте первый запрос на главной странице"
          action={
            <Button variant="outline" size="sm" onClick={() => navigate({ to: "/" })}>
              Загрузить данные
            </Button>
          }
        />
      ) : (
        <div className="rounded-md border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID запроса</TableHead>
                <TableHead>Поставщик</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Прогресс</TableHead>
                <TableHead>Результаты (Найдено/Проверка/Нет)</TableHead>
                <TableHead>Создан</TableHead>
                <TableHead className="w-12"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requests.map((req) => (
                <TableRow
                  key={req.request_id}
                  className="cursor-pointer hover:bg-muted/50 transition-colors"
                  onClick={() =>
                    navigate({
                      to: "/requests/$requestId",
                      params: { requestId: req.request_id },
                    })
                  }
                >
                  <TableCell>
                    <div className="flex items-center gap-1 font-mono text-xs text-muted-foreground">
                      <span title={req.request_id}>{req.request_id.slice(0, 8)}</span>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5 hover:bg-muted"
                        aria-label="Копировать ID"
                        onClick={(e) => copyToClipboard(e, req.request_id)}
                      >
                        {copiedId === req.request_id ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm font-medium">
                    {req.supplier_id ? (suppliersMap.get(req.supplier_id) || req.supplier_id) : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={statusColor[req.status] ?? ""}
                    >
                      {REQUEST_STATUS_LABELS[req.status] ?? req.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">
                    {req.processed_items}/{req.total_items}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2 text-xs font-medium">
                      <span className="text-green-700 bg-green-50 px-1.5 py-0.5 rounded">
                        {req.auto_matched_items}
                      </span>
                      <span className="text-muted-foreground">/</span>
                      <span className="text-yellow-700 bg-yellow-50 px-1.5 py-0.5 rounded">
                        {req.review_needed_items}
                      </span>
                      <span className="text-muted-foreground">/</span>
                      <span className="text-red-700 bg-red-50 px-1.5 py-0.5 rounded">
                        {req.no_match_items}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDate(req.created_at)}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-red-500 hover:text-red-700 hover:bg-red-50 h-8 w-8 p-0"
                      aria-label="Удалить запрос"
                      onClick={() => setDeleteTarget(req.request_id)}
                      disabled={deleteMutation.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Pagination page={page} totalPages={totalPages} total={total} pageSize={PAGE_SIZE} onPageChange={setPage} />

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить запрос?</AlertDialogTitle>
            <AlertDialogDescription>
              Запрос <span className="font-mono text-foreground font-medium">{deleteTarget}</span> и все его
              результаты будут безвозвратно удалены. Это действие нельзя отменить.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>
              Отмена
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-700 text-white"
              disabled={deleteMutation.isPending}
              onClick={() => {
                if (deleteTarget) {
                  deleteMutation.mutate(deleteTarget);
                }
              }}
            >
              {deleteMutation.isPending ? "Удаление..." : "Удалить"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}
