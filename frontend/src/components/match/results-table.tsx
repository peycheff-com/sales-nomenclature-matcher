import React, { useState, useMemo, useEffect } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ChevronDown, ChevronRight, Check, X, Search, MousePointerClick, PackageSearch } from "lucide-react";
import { getMatchItems, getItemCandidates } from "@/api/match";
import { reviewItem, reviewBatch, type BatchReviewItem } from "@/api/review";
import type { Candidate, MatchResult, ReviewInput, MatchItemsPage } from "@/api/types";
import { formatConfidence } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import StatusBadge from "./status-badge";
import ReviewActions from "@/components/review/review-actions";
import { toast } from "sonner";
import { SkeletonTable } from "@/components/ui/skeleton";
import { Pagination } from "@/components/ui/pagination";
import { EmptyState } from "@/components/ui/empty-state";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

interface ResultsTableProps {
  requestId: string;
}

const PAGE_SIZE = 20;

export default function ResultsTable({ requestId }: ResultsTableProps) {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [reviewFilter, setReviewFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedSearchQuery = useDebouncedValue(searchQuery, 300);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowSelection, setRowSelection] = useState({});

  const itemsQuery = useQuery({
    queryKey: ["match-items", requestId, statusFilter, page],
    queryFn: () =>
      getMatchItems(requestId, {
        status: statusFilter === "all" ? undefined : statusFilter,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  const candidatesQuery = useQuery({
    queryKey: ["candidates", expandedRow],
    queryFn: () => getItemCandidates(expandedRow!),
    enabled: !!expandedRow,
  });

  const bulkMutation = useMutation({
    mutationFn: async ({ action, items }: { action: "accepted" | "rejected"; items: MatchResult[] }) => {
      const batchItems: BatchReviewItem[] = items.map(item => {
        const payload: BatchReviewItem = {
          request_item_id: item.request_item_id,
          final_decision: action,
        };
        if (action === "accepted") {
          payload.final_product_id = item.best_candidate?.product_id;
          payload.create_supplier_mapping = true;
        }
        return payload;
      });
      const result = await reviewBatch(batchItems);
      return { count: result.processed_count, items: batchItems };
    },
    onSuccess: (result) => {
      toast.success(`Обработано ${result.count} записей`);
      setRowSelection({});
      // Optimistic update
      queryClient.setQueryData<MatchItemsPage>(
        ["match-items", requestId, statusFilter, page],
        (old) => {
          if (!old) return old;
          const map = new Map(result.items.map(r => [r.request_item_id, r.final_decision]));
          return {
            ...old,
            items: old.items.map(i => map.has(i.request_item_id) ? { ...i, final_decision: map.get(i.request_item_id) as MatchResult["final_decision"] } : i)
          };
        }
      );
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "Неизвестная ошибка";
      toast.error(`Ошибка при массовой обработке: ${msg}`);
    },
  });

  const fastReviewMutation = useMutation({
    mutationFn: async ({ itemId, candidateId }: { itemId: string; candidateId: string }) => {
      const input: ReviewInput = {
        final_decision: "corrected",
        final_product_id: candidateId,
        create_alias: true,
        create_supplier_mapping: true,
      };
      await reviewItem(itemId, input);
      return { itemId, decision: "corrected" };
    },
    onSuccess: (result) => {
      toast.success("Выбранный кандидат сохранен");
      setExpandedRow(null);
      handleReviewed(result.itemId, result.decision);
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "Неизвестная ошибка";
      toast.error(`Ошибка при сохранении: ${msg}`);
    },
  });

  const columns: ColumnDef<MatchResult>[] = [
    {
      id: "select",
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllPageRowsSelected() || (table.getIsSomePageRowsSelected() as boolean)}
          onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          aria-label="Выбрать все"
          className="translate-y-[2px]"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
          aria-label="Выбрать строку"
          className="translate-y-[2px]"
        />
      ),
      size: 40,
      enableSorting: false,
    },
    {
      id: "expand",
      header: "",
      size: 32,
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          aria-label={expandedRow === row.original.request_item_id ? "Свернуть" : "Развернуть"}
          onClick={() =>
            setExpandedRow(
              expandedRow === row.original.request_item_id
                ? null
                : row.original.request_item_id,
            )
          }
        >
          {expandedRow === row.original.request_item_id ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </Button>
      ),
      enableSorting: false,
    },
    {
      accessorKey: "line_id",
      header: "#",
      size: 50,
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground">
          {row.original.line_id ?? row.index + 1}
        </span>
      ),
    },
    {
      accessorKey: "raw_text",
      header: "Исходный текст",
      size: 300,
      cell: ({ row }) => (
        <div className="max-w-[300px]">
          <div className="truncate text-sm font-medium">
            {row.original.raw_text}
          </div>
          {row.original.normalized_text &&
            row.original.normalized_text !== row.original.raw_text && (
              <div className="truncate text-xs text-muted-foreground">
                {row.original.normalized_text}
              </div>
            )}
        </div>
      ),
    },
    {
      accessorKey: "status",
      header: "Статус",
      size: 100,
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    },
    {
      accessorKey: "confidence",
      header: "Уверенность",
      size: 90,
      meta: { className: "hidden md:table-cell" },
      cell: ({ row }) => (
        <span className="text-sm">{formatConfidence(row.original.confidence)}</span>
      ),
    },
    {
      id: "best_match",
      header: "Лучший результат",
      size: 250,
      enableSorting: false,
      meta: { className: "hidden md:table-cell" },
      cell: ({ row }) => {
        const best = row.original.best_candidate;
        if (!best) return <span className="text-sm text-muted-foreground">\u2014</span>;
        return (
          <div className="max-w-[250px]">
            <div className="truncate text-sm">{best.name}</div>
            {best.article && (
              <div className="text-xs text-muted-foreground">
                Арт: {best.article}
              </div>
            )}
          </div>
        );
      },
    },
    {
      id: "actions",
      header: "Действия",
      size: 200,
      enableSorting: false,
      cell: ({ row }) => (
        <ReviewActions
          item={row.original}
          onReviewed={(decision) => handleReviewed(row.original.request_item_id, decision)}
        />
      ),
    },
  ];

  const handleReviewed = (itemId: string, decision: string) => {
    queryClient.setQueryData<MatchItemsPage>(
      ["match-items", requestId, statusFilter, page],
      (old) => {
        if (!old) return old;
        return {
          ...old,
          items: old.items.map((i) =>
            i.request_item_id === itemId ? { ...i, final_decision: decision as MatchResult["final_decision"] } : i
          ),
        };
      }
    );
  };

  const fetchedData = useMemo(() => itemsQuery.data?.items ?? [], [itemsQuery.data]);

  const filteredData = useMemo(() => {
    let result = fetchedData;
    if (debouncedSearchQuery.trim()) {
      const q = debouncedSearchQuery.toLowerCase();
      result = result.filter(item =>
        item.raw_text.toLowerCase().includes(q) ||
        (item.normalized_text && item.normalized_text.toLowerCase().includes(q))
      );
    }
    if (reviewFilter === "reviewed") {
      result = result.filter(item => !!item.final_decision);
    } else if (reviewFilter === "pending") {
      result = result.filter(item => !item.final_decision);
    }
    return result;
  }, [fetchedData, debouncedSearchQuery, reviewFilter]);

  const totalItems = itemsQuery.data?.total ?? 0;
  const totalPages = Math.ceil(totalItems / PAGE_SIZE);

  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: filteredData,
    columns,
    state: {
      sorting,
      rowSelection,
    },
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  // GAP-1: Auto-advance if the user is filtering by "pending" and the current page is drained
  useEffect(() => {
    if (reviewFilter === "pending" && !itemsQuery.isLoading && itemsQuery.data) {
      if (filteredData.length === 0 && itemsQuery.data.items.length > 0) {
        if (page < totalPages) {
          toast.info(`Страница ${page + 1}: все позиции проверены, переход...`);
          setPage((p) => p + 1);
        } else if (page > 1) {
          setPage(1);
        }
      }
    }
  }, [filteredData.length, reviewFilter, itemsQuery.isLoading, itemsQuery.data, page, totalPages]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement) return;

      const visibleRows = table.getRowModel().rows;
      if (visibleRows.length === 0) return;

      const expandedIndex = visibleRows.findIndex(r => r.original.request_item_id === expandedRow);
      
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const nextIdx = expandedIndex >= 0 && expandedIndex < visibleRows.length - 1 ? expandedIndex + 1 : 0;
        setExpandedRow(visibleRows[nextIdx].original.request_item_id);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prevIdx = expandedIndex > 0 ? expandedIndex - 1 : visibleRows.length - 1;
        setExpandedRow(visibleRows[prevIdx].original.request_item_id);
      } else if (e.key === 'Enter' && expandedRow) {
        const row = visibleRows.find(r => r.original.request_item_id === expandedRow);
        if (row && row.original.best_candidate && !row.original.final_decision) {
          e.preventDefault();
          bulkMutation.mutate({ action: "accepted", items: [row.original] });
        }
      } else if (e.key === 'Escape' && expandedRow) {
        const row = visibleRows.find(r => r.original.request_item_id === expandedRow);
        if (row && !row.original.final_decision) {
          e.preventDefault();
          bulkMutation.mutate({ action: "rejected", items: [row.original] });
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [expandedRow, table, bulkMutation]);

  const selectedRows = table.getSelectedRowModel().rows.map(r => r.original);

  const autoMatchesOnPage = useMemo(
    () => filteredData.filter(i => i.status === "auto_match" && !i.final_decision),
    [filteredData]
  );

  const approveAllAutoMatches = () => {
    if (autoMatchesOnPage.length === 0) {
      toast.info("Нет доступных авто-сопоставлений для подтверждения");
      return;
    }
    bulkMutation.mutate({ action: "accepted", items: autoMatchesOnPage });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <Tabs
          value={statusFilter}
          onValueChange={(val) => {
            setStatusFilter(val);
            setPage(1);
            setRowSelection({});
            setExpandedRow(null);
          }}
        >
          <TabsList>
            <TabsTrigger value="all">Все</TabsTrigger>
            <TabsTrigger value="auto_match">Найдено</TabsTrigger>
            <TabsTrigger value="review_needed">На проверку</TabsTrigger>
            <TabsTrigger value="no_match">Не найдено</TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="flex gap-2 items-center">
          <Tabs value={reviewFilter} onValueChange={setReviewFilter}>
            <TabsList className="bg-muted/50 text-xs h-9">
              <TabsTrigger value="all" className="px-2">Все</TabsTrigger>
              <TabsTrigger value="pending" className="px-2">Ждут проверки</TabsTrigger>
              <TabsTrigger value="reviewed" className="px-2">Проверены</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Поиск по тексту..."
              className="pl-8 h-9 w-[200px]"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>
      </div>

      {filteredData.length > 0 && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground px-1">
          <span>
            Проверено: {filteredData.filter(i => !!i.final_decision).length} из {filteredData.length} на странице
          </span>
          <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden max-w-[200px]">
            <div
              className="h-full bg-primary/60 rounded-full transition-all"
              style={{ width: `${(filteredData.filter(i => !!i.final_decision).length / filteredData.length) * 100}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 p-2 bg-muted/30 border border-border rounded-md min-h-[52px]">
        <div className="flex flex-wrap items-center gap-2">
          {selectedRows.length > 0 ? (
            <>
              <span className="text-sm font-medium mr-2 ml-1 text-muted-foreground">
                Выбрано: {selectedRows.length} <span className="text-[10px] opacity-70">(выбор только на текущей странице)</span>
              </span>
              <Button size="sm" variant="outline" className="text-green-700 hover:text-green-800" disabled={bulkMutation.isPending} onClick={() => bulkMutation.mutate({ action: "accepted", items: selectedRows })}>
                <Check className="h-4 w-4 mr-1"/> Принять выбранные
              </Button>
              <Button size="sm" variant="outline" className="text-red-700 hover:text-red-800" disabled={bulkMutation.isPending} onClick={() => bulkMutation.mutate({ action: "rejected", items: selectedRows })}>
                <X className="h-4 w-4 mr-1"/> Отклонить выбранные
              </Button>
            </>
          ) : (
            <Button size="sm" variant="outline" onClick={approveAllAutoMatches} disabled={bulkMutation.isPending || itemsQuery.isLoading}>
              <Check className="h-4 w-4 mr-1 text-green-600"/> Принять авто ({autoMatchesOnPage.length} на стр.)
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2 lg:gap-4 text-[8px] lg:text-[10px] text-muted-foreground mr-2 font-mono opacity-80 cursor-default select-none">
          <span className="flex items-center gap-1.5" title="Навигация по строкам">
            <kbd className="bg-background px-1 py-0.5 rounded border border-border/50 text-[10px]">&darr;</kbd>
            <kbd className="bg-background px-1 py-0.5 rounded border border-border/50 text-[10px]">&uarr;</kbd> Навигация
          </span>
          <span className="flex items-center gap-1.5" title="Принять лучшего кандидата">
            <kbd className="bg-background px-1.5 py-0.5 rounded border border-border/50 text-[10px]">Enter</kbd> Принять
          </span>
          <span className="flex items-center gap-1.5" title="Отклонить позицию">
            <kbd className="bg-background px-1.5 py-0.5 rounded border border-border/50 text-[10px]">Esc</kbd> Отклонить
          </span>
        </div>
      </div>

      <div className="rounded-md border border-border overflow-x-auto">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const colMeta = header.column.columnDef.meta as { className?: string } | undefined;
                  return (
                  <TableHead
                    key={header.id}
                    style={{ width: header.getSize() }}
                    className={`${header.column.getCanSort() ? "cursor-pointer select-none hover:bg-muted/50" : ""} ${colMeta?.className ?? ""}`}
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() === "asc" ? <ChevronDown className="h-3 w-3 rotate-180" /> : null}
                      {header.column.getIsSorted() === "desc" ? <ChevronDown className="h-3 w-3" /> : null}
                    </div>
                  </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {itemsQuery.isLoading ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="py-6">
                  <SkeletonTable rows={5} columns={5} />
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="py-4">
                  <EmptyState
                    icon={Search}
                    title="Нет данных"
                    description="По выбранным фильтрам ничего не найдено"
                    variant="no-results"
                  />
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => {
                let rowColor = "hover:bg-muted/50";
                if (row.original.final_decision === "accepted") rowColor = "bg-green-50/50 hover:bg-green-50 border-l-2 border-l-green-500";
                if (row.original.final_decision === "corrected") rowColor = "bg-blue-50/50 hover:bg-blue-50 border-l-2 border-l-blue-500";
                if (row.original.final_decision === "rejected") rowColor = "bg-red-50/50 hover:bg-red-50 border-l-2 border-l-red-500";

                return (
                  <React.Fragment key={row.id}>
                    <TableRow className={`${rowColor} ${expandedRow === row.original.request_item_id ? "border-b-0" : ""}`}>
                      {row.getVisibleCells().map((cell) => {
                        const cellMeta = cell.column.columnDef.meta as { className?: string } | undefined;
                        return (
                          <TableCell key={cell.id} className={cellMeta?.className}>
                            {flexRender(
                              cell.column.columnDef.cell,
                              cell.getContext(),
                            )}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                    {expandedRow === row.original.request_item_id && (
                      <TableRow className={rowColor}>
                        <TableCell colSpan={columns.length} className="bg-muted/5 border-t-0 pt-0 pb-4 px-12">
                          <CandidatesPanel
                            candidates={candidatesQuery.data?.candidates}
                            isLoading={candidatesQuery.isLoading}
                            reasons={row.original.reasons}
                            attributes={row.original.extracted_attributes}
                            onSelectCandidate={(candidateId) => fastReviewMutation.mutate({ itemId: row.original.request_item_id, candidateId })}
                            isSelecting={fastReviewMutation.isPending}
                            hasDecision={!!row.original.final_decision}
                          />
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <Pagination
          page={page}
          totalPages={totalPages}
          total={totalItems}
          pageSize={PAGE_SIZE}
          onPageChange={(p) => {
            setPage(p);
            setExpandedRow(null);
            setRowSelection({});
          }}
        />
      )}
    </div>
  );
}

function CandidatesPanel({
  candidates,
  isLoading,
  reasons,
  attributes,
  onSelectCandidate,
  isSelecting,
  hasDecision
}: {
  candidates: Candidate[] | undefined;
  isLoading: boolean;
  reasons: string[];
  attributes: Record<string, unknown>;
  onSelectCandidate: (candidateId: string) => void;
  isSelecting: boolean;
  hasDecision: boolean;
}) {
  if (isLoading) {
    return <SkeletonTable rows={3} columns={4} className="py-2" />;
  }

  return (
    <div className="space-y-4 rounded-md border border-border bg-card p-4">
      {Object.keys(attributes).length > 0 && (
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-1">
            Извлечённые атрибуты:
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(attributes).map(([key, value]) => (
              <span
                key={key}
                className="rounded bg-muted px-2 py-0.5 text-xs text-foreground"
              >
                {key}: {String(value)}
              </span>
            ))}
          </div>
        </div>
      )}

      {reasons.length > 0 && (
        <div className="bg-yellow-50/50 p-2 rounded text-yellow-800 border border-yellow-100">
          <div className="text-xs font-semibold mb-1">Факторы совпадения:</div>
          <ul className="list-disc pl-4 text-xs font-medium">
            {reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {candidates && candidates.length > 0 && (
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-2">
            Кандидаты отсортированные по релевантности ({candidates.length}):
          </div>
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-xs text-left">
              <thead className="bg-muted/50 text-muted-foreground font-medium">
                <tr>
                  <th className="py-2 pl-3 pr-2">#</th>
                  <th className="py-2 px-2">Наименование</th>
                  <th className="py-2 px-2">Бренд / Арт</th>
                  <th className="py-2 px-2 w-[240px]">Оценки (Лекс / Сем / Рэр / Прав)</th>
                  <th className="py-2 px-2 text-right">Итоговый %</th>
                  <th className="py-2 pr-3 pl-2 text-right">Действие</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {candidates.map((c, i) => (
                  <tr key={c.product_id} className="hover:bg-muted/30">
                    <td className="py-1.5 pl-3 pr-2 text-muted-foreground">{i + 1}</td>
                    <td className="py-1.5 px-2 font-medium">{c.name}</td>
                    <td className="py-1.5 px-2 text-muted-foreground">
                      <span className="block truncate max-w-[120px]">{c.brand ?? "\u2014"}</span>
                      <span className="block">{c.article ?? "\u2014"}</span>
                    </td>
                    <td className="py-1.5 px-2">
                      <div className="flex items-center gap-1.5 font-mono text-[10px]">
                        <span title="Лексический">{c.lexical_score ? (c.lexical_score).toFixed(2) : "-"}</span>
                        <span>/</span>
                        <span title="Семантический" className="text-blue-600">{c.semantic_score ? (c.semantic_score).toFixed(2) : "-"}</span>
                        <span>/</span>
                        <span title="Реранжирование" className="text-purple-600">{c.rerank_score ? (c.rerank_score).toFixed(2) : "-"}</span>
                        <span>/</span>
                        <span title="Правила">{c.rules_score ? (c.rules_score).toFixed(2) : "-"}</span>
                      </div>
                    </td>
                    <td className="py-1.5 px-2 text-right font-medium">
                      {c.final_score != null
                        ? `${Math.round(c.final_score * 100)}%`
                        : "\u2014"}
                    </td>
                    <td className="py-1.5 pr-3 pl-2 text-right">
                      <Button 
                        size="sm" 
                        variant="ghost" 
                        className="h-7 text-xs" 
                        disabled={isSelecting || hasDecision}
                        onClick={() => onSelectCandidate(c.product_id)}
                      >
                        <MousePointerClick className="mr-1 h-3.5 w-3.5" />
                        Выбрать
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(!candidates || candidates.length === 0) && !isLoading && (
        <EmptyState
          icon={PackageSearch}
          title="Кандидаты не найдены"
          description="Альтернативные кандидаты для этой позиции не найдены"
          variant="no-results"
          className="min-h-[120px]"
        />
      )}
    </div>
  );
}
