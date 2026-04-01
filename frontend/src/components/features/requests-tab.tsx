import { useState, useMemo, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Trash2, Copy, Check, FileSearch, Calendar, Search, ChevronUp, ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { listMatchRequests, deleteMatchRequest } from "@/api/match";
import { listSuppliers } from "@/api/suppliers";
import { REQUEST_STATUS_LABELS } from "@/lib/constants";
import { formatDate } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { EmptyState } from "@/components/ui/empty-state";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

const PAGE_SIZE = 20;

type SortField = "created_at" | "status" | "total_items";
type SortDir = "asc" | "desc";

export function RequestsTab() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [bulkDeleteConfirm, setBulkDeleteConfirm] = useState(false);

  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("all");
  const [supplierFilter, setSupplierFilter] = useState("__all__");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedSearchQuery = useDebouncedValue(searchQuery, 300);

  // GAP-3.1: Sorting state
  const [sortBy, setSortBy] = useState<SortField | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // GAP-3.4: Bulk selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const requestsQuery = useQuery({
    queryKey: ["match-requests", page, statusFilter, supplierFilter, dateRange],
    queryFn: () => {
      let createdAfter: string | undefined;
      if (dateRange === "today") createdAfter = new Date(new Date().setHours(0, 0, 0, 0)).toISOString();
      else if (dateRange === "3d") createdAfter = new Date(Date.now() - 3 * 86400000).toISOString();
      else if (dateRange === "7d") createdAfter = new Date(Date.now() - 7 * 86400000).toISOString();
      else if (dateRange === "30d") createdAfter = new Date(Date.now() - 30 * 86400000).toISOString();
      return listMatchRequests({
        page,
        limit: PAGE_SIZE,
        status: statusFilter,
        supplier_id: supplierFilter,
        created_after: createdAfter,
      });
    },
    refetchInterval: () => {
      if (document.hidden) return false;
      return 10_000;
    },
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
    onError: (err) => {
      setDeleteTarget(null);
      const msg = err instanceof Error ? err.message : "Неизвестная ошибка";
      toast.error(`Не удалось удалить запрос: ${msg}`);
    },
  });

  // GAP-3.4: Bulk delete mutation
  const bulkDeleteMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      for (const id of ids) {
        await deleteMatchRequest(id);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["match-requests"] });
      setSelectedIds(new Set());
      setBulkDeleteConfirm(false);
      toast.success(`Удалено запросов: ${selectedIds.size}`);
    },
    onError: (err) => {
      queryClient.invalidateQueries({ queryKey: ["match-requests"] });
      setSelectedIds(new Set());
      setBulkDeleteConfirm(false);
      const msg = err instanceof Error ? err.message : "Неизвестная ошибка";
      toast.error(`Не удалось удалить некоторые запросы: ${msg}`);
    },
  });

  const rawRequests = useMemo(() => requestsQuery.data?.items ?? [], [requestsQuery.data]);
  const total = requestsQuery.data?.total ?? 0;
  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;

  // GAP-3.2: Client-side search filter (debounced to avoid per-keystroke filtering)
  const filteredRequests = useMemo(() => {
    if (!debouncedSearchQuery.trim()) return rawRequests;
    const q = debouncedSearchQuery.trim().toLowerCase();
    return rawRequests.filter((req) => req.request_id.toLowerCase().includes(q));
  }, [rawRequests, debouncedSearchQuery]);

  // GAP-3.1: Client-side sorting
  const requests = useMemo(() => {
    if (!sortBy) return filteredRequests;
    const sorted = [...filteredRequests];
    sorted.sort((a, b) => {
      let cmp = 0;
      switch (sortBy) {
        case "created_at":
          cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
          break;
        case "status": {
          const statusOrder: Record<string, number> = { queued: 0, running: 1, done: 2, failed: 3 };
          cmp = (statusOrder[a.status] ?? 99) - (statusOrder[b.status] ?? 99);
          break;
        }
        case "total_items":
          cmp = a.total_items - b.total_items;
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [filteredRequests, sortBy, sortDir]);

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

  // GAP-3.1: Toggle sort handler
  const handleSort = useCallback((field: SortField) => {
    if (sortBy === field) {
      if (sortDir === "asc") {
        setSortDir("desc");
      } else {
        // Clicking third time resets sorting
        setSortBy(null);
        setSortDir("desc");
      }
    } else {
      setSortBy(field);
      setSortDir("asc");
    }
  }, [sortBy, sortDir]);

  // GAP-3.4: Selection helpers
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (selectedIds.size === requests.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(requests.map((r) => r.request_id)));
    }
  }, [requests, selectedIds.size]);

  const isAllSelected = requests.length > 0 && selectedIds.size === requests.length;
  const hasFiltersApplied = statusFilter !== "all" || supplierFilter !== "__all__" || dateRange !== "all" || debouncedSearchQuery.trim() !== "";

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          {/* GAP-3.2: Search by request ID */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Поиск по ID запроса..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-[220px] pl-8 h-9"
            />
          </div>

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

          {/* GAP-3.3: Extended date range options */}
          <Select value={dateRange} onValueChange={(val) => { setDateRange(val || "all"); setPage(1); }}>
            <SelectTrigger className="w-[160px]">
              <Calendar className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
              <SelectValue placeholder="Период" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Всё время</SelectItem>
              <SelectItem value="today">Сегодня</SelectItem>
              <SelectItem value="3d">3 дня</SelectItem>
              <SelectItem value="7d">7 дней</SelectItem>
              <SelectItem value="30d">30 дней</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* GAP-3.4: Bulk actions bar */}
      {selectedIds.size > 0 && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-border bg-muted/50 px-4 py-2.5">
          <span className="text-sm text-muted-foreground">
            Выбрано: <span className="font-medium text-foreground">{selectedIds.size}</span>
          </span>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setBulkDeleteConfirm(true)}
            disabled={bulkDeleteMutation.isPending}
          >
            <Trash2 className="mr-1.5 h-3.5 w-3.5" />
            Удалить выбранные ({selectedIds.size})
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSelectedIds(new Set())}
          >
            Снять выделение
          </Button>
        </div>
      )}

      {requestsQuery.isLoading ? (
        <SkeletonTable rows={5} columns={8} />
      ) : requestsQuery.isError ? (
        <QueryErrorBanner error={requestsQuery.error} onRetry={() => requestsQuery.refetch()} />
      ) : requests.length === 0 && hasFiltersApplied ? (
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
                {/* GAP-3.4: Select all checkbox */}
                <TableHead className="w-10">
                  <Checkbox
                    checked={isAllSelected}
                    onCheckedChange={toggleSelectAll}
                    aria-label="Выбрать все"
                  />
                </TableHead>
                <TableHead>ID запроса</TableHead>
                <TableHead>Поставщик</TableHead>
                {/* GAP-3.1: Sortable status header */}
                <TableHead
                  className="group cursor-pointer select-none"
                  onClick={() => handleSort("status")}
                >
                  <span className="inline-flex items-center">
                    Статус
                    <SortIndicator field="status" sortBy={sortBy} sortDir={sortDir} />
                  </span>
                </TableHead>
                <TableHead>Прогресс</TableHead>
                <TableHead>Результаты (Найдено/Проверка/Нет)</TableHead>
                {/* GAP-3.1: Sortable total items header */}
                <TableHead
                  className="group cursor-pointer select-none"
                  onClick={() => handleSort("total_items")}
                >
                  <span className="inline-flex items-center">
                    Всего
                    <SortIndicator field="total_items" sortBy={sortBy} sortDir={sortDir} />
                  </span>
                </TableHead>
                {/* GAP-3.1: Sortable created date header */}
                <TableHead
                  className="group cursor-pointer select-none"
                  onClick={() => handleSort("created_at")}
                >
                  <span className="inline-flex items-center">
                    Создан
                    <SortIndicator field="created_at" sortBy={sortBy} sortDir={sortDir} />
                  </span>
                </TableHead>
                <TableHead className="w-12"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requests.map((req) => (
                <TableRow
                  key={req.request_id}
                  className="cursor-pointer hover:bg-muted/50 transition-colors"
                  data-state={selectedIds.has(req.request_id) ? "selected" : undefined}
                  onClick={() =>
                    navigate({
                      to: "/requests/$requestId",
                      params: { requestId: req.request_id },
                    })
                  }
                >
                  {/* GAP-3.4: Row checkbox */}
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selectedIds.has(req.request_id)}
                      onCheckedChange={() => toggleSelect(req.request_id)}
                      aria-label={`Выбрать запрос ${req.request_id.slice(0, 8)}`}
                    />
                  </TableCell>
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
                    {/* GAP-3.5: File name / source type display */}
                    {(req.file_name || req.source_type) && (
                      <div className="mt-0.5 text-xs text-muted-foreground/70 truncate max-w-[180px]" title={req.file_name}>
                        {req.file_name || req.source_type}
                      </div>
                    )}
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
                  <TableCell className="text-sm tabular-nums">
                    {req.total_items}
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

      {/* Single delete confirmation dialog */}
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

      {/* GAP-3.4: Bulk delete confirmation dialog */}
      <AlertDialog open={bulkDeleteConfirm} onOpenChange={(open) => !open && setBulkDeleteConfirm(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить выбранные запросы?</AlertDialogTitle>
            <AlertDialogDescription>
              Будет удалено запросов: <span className="font-medium text-foreground">{selectedIds.size}</span>.
              Все связанные результаты будут безвозвратно удалены. Это действие нельзя отменить.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={bulkDeleteMutation.isPending}>
              Отмена
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-700 text-white"
              disabled={bulkDeleteMutation.isPending}
              onClick={() => {
                bulkDeleteMutation.mutate(Array.from(selectedIds));
              }}
            >
              {bulkDeleteMutation.isPending ? "Удаление..." : `Удалить (${selectedIds.size})`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function SortIndicator({ field, sortBy, sortDir }: { field: SortField; sortBy: SortField | null; sortDir: SortDir }) {
  if (sortBy !== field) {
    return (
      <span className="ml-1 inline-flex opacity-0 group-hover:opacity-40 transition-opacity">
        <ChevronUp className="h-3 w-3" />
      </span>
    );
  }
  return (
    <span className="ml-1 inline-flex text-foreground">
      {sortDir === "asc" ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
    </span>
  );
}
