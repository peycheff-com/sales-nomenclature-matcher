import React, { useState, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Search, Server, Upload, RefreshCw, ChevronDown, ChevronRight,
  Trash2, AlertTriangle, Loader2, CheckCircle, Info, FileText, AlertCircle,
} from "lucide-react";
import { toast } from "sonner";
import {
  searchCatalog,
  getCatalogStats,
  importFromOnec,
  reindexCatalog,
  uploadCatalogFile,
  deleteCatalogProduct,
} from "@/api/catalog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PageLayout } from "@/components/layout/page-layout";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton, SkeletonTable } from "@/components/ui/skeleton";
import { QueryErrorBanner } from "@/components/ui/query-error-banner";
import { Pagination } from "@/components/ui/pagination";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

const PAGE_SIZE = 25;

type StatusFilter = "all" | "active" | "archive";

export default function CatalogPage() {
  const queryClient = useQueryClient();
  const [searchInput, setSearchInput] = useState("");
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  // GAP-5.3: Bulk selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);

  // GAP-5.5: Import progress state
  const [importStatus, setImportStatus] = useState<string | null>(null);

  // GAP-5.8 & 5.9: File upload dialogs
  const [fileFormatDialogOpen, setFileFormatDialogOpen] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [fileConfirmOpen, setFileConfirmOpen] = useState(false);

  // Debounced live search via hook — fires 400ms after user stops typing
  const debouncedInput = useDebouncedValue(searchInput, 400);
  const debouncedQuery = debouncedInput.trim();

  const [expandedProduct, setExpandedProduct] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const statsQuery = useQuery({
    queryKey: ["catalog-stats"],
    queryFn: getCatalogStats,
  });

  const productsQuery = useQuery({
    queryKey: ["catalog-search", debouncedQuery],
    queryFn: () => searchCatalog(debouncedQuery, 500),
  });

  const importMutation = useMutation({
    mutationFn: importFromOnec,
    onSuccess: () => {
      toast.success("Импорт из 1С запущен (в фоне)");
      setImportStatus("sync");
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "";
      toast.error(`Ошибка при запуске импорта: ${msg}`);
      setImportStatus(null);
    },
  });

  const reindexMutation = useMutation({
    mutationFn: reindexCatalog,
    onSuccess: () => {
      toast.success("Переиндексация поиска запущена (в фоне)");
      // Poll stats every 5s to show progress
      const interval = setInterval(() => {
        queryClient.invalidateQueries({ queryKey: ["catalog-stats"] });
      }, 5000);
      setTimeout(() => clearInterval(interval), 120_000);
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "";
      toast.error(`Ошибка при запуске переиндексации: ${msg}`);
    },
  });

  const uploadMutation = useMutation({
    mutationFn: uploadCatalogFile,
    onSuccess: () => {
      toast.success("Файл загружен. Импорт запущен (в фоне)");
      queryClient.invalidateQueries({ queryKey: ["catalog-stats"] });
      setImportStatus("file");
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "";
      toast.error(`Ошибка при загрузке файла: ${msg}`);
      setImportStatus(null);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCatalogProduct,
    onSuccess: () => {
      toast.success("Товар удален из каталога");
      setDeleteTarget(null);
      setExpandedProduct(null);
      queryClient.invalidateQueries({ queryKey: ["catalog-stats"] });
      queryClient.invalidateQueries({ queryKey: ["catalog-search"] });
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "";
      toast.error(`Ошибка при удалении товара: ${msg}`);
    },
  });

  // GAP-5.3: Bulk delete mutation
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const handleBulkDelete = useCallback(async () => {
    if (bulkDeleting) return;
    setBulkDeleting(true);
    try {
      const ids = Array.from(selectedIds);
      let successCount = 0;
      let errorCount = 0;
      for (const id of ids) {
        try {
          await deleteCatalogProduct(id);
          successCount++;
        } catch {
          errorCount++;
        }
      }
      setBulkDeleteOpen(false);
      setSelectedIds(new Set());
      setExpandedProduct(null);
      if (successCount > 0) {
        toast.success(`Удалено товаров: ${successCount}`);
        queryClient.invalidateQueries({ queryKey: ["catalog-stats"] });
        queryClient.invalidateQueries({ queryKey: ["catalog-search"] });
      }
      if (errorCount > 0) {
        toast.error(`Не удалось удалить: ${errorCount}`);
      }
    } finally {
      setBulkDeleting(false);
    }
  }, [bulkDeleting, selectedIds, queryClient]);

  // GAP-5.8: Open format info dialog instead of file picker directly
  const handleFileButtonClick = () => {
    setFileFormatDialogOpen(true);
  };

  const handleFileFormatContinue = () => {
    setFileFormatDialogOpen(false);
    fileInputRef.current?.click();
  };

  // GAP-5.9: After file selection, show confirmation
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPendingFile(file);
    setFileConfirmOpen(true);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleFileConfirm = () => {
    if (pendingFile) {
      uploadMutation.mutate(pendingFile);
    }
    setPendingFile(null);
    setFileConfirmOpen(false);
  };

  const handleFileCancel = () => {
    setPendingFile(null);
    setFileConfirmOpen(false);
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setExpandedProduct(null);
    setSelectedIds(new Set());
  };

  // GAP-5.1: Client-side status filtering
  const fetchedData = productsQuery.data ?? [];
  const filteredData = statusFilter === "all"
    ? fetchedData
    : statusFilter === "active"
      ? fetchedData.filter((p) => p.is_active)
      : fetchedData.filter((p) => !p.is_active);
  const totalPages = Math.ceil(filteredData.length / PAGE_SIZE) || 1;
  const paginatedData = filteredData.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // GAP-5.3: Checkbox helpers
  const allPageSelected = paginatedData.length > 0 && paginatedData.every((p) => selectedIds.has(p.product_id));
  const somePageSelected = paginatedData.some((p) => selectedIds.has(p.product_id));

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allPageSelected) {
        for (const p of paginatedData) next.delete(p.product_id);
      } else {
        for (const p of paginatedData) next.add(p.product_id);
      }
      return next;
    });
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <PageLayout
      title="База данных"
      description="Единый справочник"
    >
          <div className="grid gap-6 md:grid-cols-4">
        <div className="md:col-span-1 space-y-6">
          {statsQuery.isError && (
            <QueryErrorBanner
              error={statsQuery.error}
              title="Ошибка загрузки статистики"
              onRetry={() => statsQuery.refetch()}
            />
          )}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Статистика каталога</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {statsQuery.isLoading ? <Skeleton className="h-8 w-20" /> : statsQuery.data?.total_products.toLocaleString() ?? "\u2014"}
              </div>
              <p className="text-xs text-muted-foreground mt-1">Всего позиций в индексе</p>

              {/* Index health: embedding coverage */}
              {statsQuery.data && (() => {
                const { total_products, embedded_products, embedding_coverage_pct, embedding_model } = statsQuery.data;
                const fullCoverage = embedded_products >= total_products && total_products > 0;
                const noEmbeddings = embedded_products === 0 && total_products > 0;
                return (
                  <div className="mt-3 space-y-2">
                    {/* Coverage bar */}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="text-muted-foreground">Эмбеддинги</span>
                        <span className={`font-medium ${fullCoverage ? "text-green-600" : noEmbeddings ? "text-red-600" : "text-yellow-600"}`}>
                          {embedded_products.toLocaleString()} / {total_products.toLocaleString()}
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${fullCoverage ? "bg-green-500" : noEmbeddings ? "bg-red-400" : "bg-yellow-500"}`}
                          style={{ width: `${Math.min(embedding_coverage_pct, 100)}%` }}
                        />
                      </div>
                    </div>
                    {/* Status line */}
                    <div className="flex items-center gap-1.5 text-xs">
                      {fullCoverage ? (
                        <>
                          <CheckCircle className="h-3.5 w-3.5 text-green-500 shrink-0" />
                          <span className="text-green-700">Индекс актуален</span>
                        </>
                      ) : noEmbeddings ? (
                        <>
                          <AlertCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
                          <span className="text-red-700">Индекс не построен</span>
                        </>
                      ) : (
                        <>
                          <AlertCircle className="h-3.5 w-3.5 text-yellow-500 shrink-0" />
                          <span className="text-yellow-700">Индекс неполный ({embedding_coverage_pct}%)</span>
                        </>
                      )}
                    </div>
                    {embedding_model && (
                      <p className="text-[10px] text-muted-foreground">Модель: {embedding_model}</p>
                    )}
                  </div>
                );
              })()}

              <div className="mt-4 pt-4 border-t border-border flex flex-col gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start text-xs"
                  onClick={() => importMutation.mutate()}
                  disabled={importMutation.isPending}
                >
                  {importMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin text-blue-500" />
                  ) : (
                    <Server className="mr-2 h-4 w-4 text-blue-500" />
                  )}
                  Синхронизировать с 1С
                </Button>
                {/* GAP-5.6: Last sync info */}
                <p className="text-[10px] text-muted-foreground ml-1">
                  Последняя синхронизация: Нет данных
                </p>
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileUpload}
                  accept=".csv,.xlsx"
                  className="hidden"
                />
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start text-xs"
                  onClick={handleFileButtonClick}
                  disabled={uploadMutation.isPending}
                >
                  {uploadMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin text-green-500" />
                  ) : (
                    <Upload className="mr-2 h-4 w-4 text-green-500" />
                  )}
                  {uploadMutation.isPending ? "Загрузка..." : "Загрузить из файла"}
                </Button>
                <Button
                  variant={statsQuery.data && statsQuery.data.embedded_products < statsQuery.data.total_products ? "default" : "outline"}
                  size="sm"
                  className={`w-full justify-start text-xs ${
                    statsQuery.data && statsQuery.data.embedded_products < statsQuery.data.total_products
                      ? "bg-orange-500 hover:bg-orange-600 text-white"
                      : ""
                  }`}
                  onClick={() => reindexMutation.mutate()}
                  disabled={reindexMutation.isPending}
                >
                  {reindexMutation.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className={`mr-2 h-4 w-4 ${
                      statsQuery.data && statsQuery.data.embedded_products < statsQuery.data.total_products
                        ? ""
                        : "text-orange-500"
                    }`} />
                  )}
                  {reindexMutation.isPending ? "Индексация запущена..." : "Обновить индекс поиска"}
                </Button>
                {/* GAP-5.5: Import progress indicator */}
                {importStatus && (
                  <div className="flex items-start gap-2 rounded-md border border-blue-200 bg-blue-50 p-2.5 mt-1">
                    <Loader2 className="h-4 w-4 animate-spin text-blue-600 mt-0.5 shrink-0" />
                    <div className="text-xs text-blue-800">
                      <p className="font-medium">
                        {importStatus === "sync" ? "Синхронизация запущена" : "Импорт из файла запущен"}
                      </p>
                      <p className="mt-0.5 text-blue-600">
                        Обработка может занять несколько минут...
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="md:col-span-3 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium">Поиск по каталогу</CardTitle>
            </CardHeader>
            <CardContent>
              {/* GAP-5.1 & 5.2: Search with status filter */}
              <form onSubmit={handleSearch} className="flex gap-2 flex-wrap">
                <Input
                  placeholder="Поиск по артикулу, наименованию, бренду, категории..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  className="max-w-md"
                />
                <Select
                  value={statusFilter}
                  onValueChange={(val) => {
                    setStatusFilter((val || "all") as StatusFilter);
                    setPage(1);
                    setSelectedIds(new Set());
                  }}
                >
                  <SelectTrigger className="w-[160px]">
                    <SelectValue placeholder="Статус" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Все</SelectItem>
                    <SelectItem value="active">Активные</SelectItem>
                    <SelectItem value="archive">Архивные</SelectItem>
                  </SelectContent>
                </Select>
                <Button type="submit" disabled={productsQuery.isFetching}>
                  <Search className="mr-2 h-4 w-4" />
                  Искать
                </Button>
              </form>

              {/* GAP-5.3: Bulk action bar */}
              {selectedIds.size > 0 && (
                <div className="mt-3 flex items-center gap-3 rounded-md border border-orange-200 bg-orange-50 p-2.5">
                  <span className="text-xs font-medium text-orange-800">
                    Выбрано: {selectedIds.size}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs border-red-300 text-red-700 hover:bg-red-50 hover:text-red-800"
                    onClick={() => setBulkDeleteOpen(true)}
                  >
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                    Удалить выбранные ({selectedIds.size})
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs text-muted-foreground"
                    onClick={() => setSelectedIds(new Set())}
                  >
                    Снять выделение
                  </Button>
                </div>
              )}

              <div className="mt-6 rounded-md border border-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {/* GAP-5.3: Select-all checkbox header */}
                      <TableHead className="w-10">
                        {paginatedData.length > 0 && (
                          <Checkbox
                            checked={allPageSelected}
                            indeterminate={somePageSelected && !allPageSelected}
                            onCheckedChange={toggleSelectAll}
                            aria-label="Выбрать все на странице"
                          />
                        )}
                      </TableHead>
                      <TableHead className="w-10"></TableHead>
                      <TableHead>Артикул</TableHead>
                      <TableHead>Наименование</TableHead>
                      <TableHead>Бренд / Категория</TableHead>
                      <TableHead>Статус</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {productsQuery.isLoading ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-6">
                          <SkeletonTable rows={3} columns={5} />
                        </TableCell>
                      </TableRow>
                    ) : paginatedData.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="py-8">
                          <EmptyState
                            icon={Search}
                            title={debouncedQuery ? "Ничего не найдено" : "Каталог пуст"}
                            description={debouncedQuery ? "По вашему запросу не найдено ни одного товара в каталоге." : "В базовом каталоге пока нет данных. Выполните синхронизацию с 1С или загрузите файл."}
                            variant="no-results"
                          />
                        </TableCell>
                      </TableRow>
                    ) : (
                      paginatedData.map((prod) => (
                        <React.Fragment key={prod.product_id}>
                          <TableRow
                            className={`cursor-pointer transition-colors ${expandedProduct === prod.product_id ? "bg-muted/30" : "hover:bg-muted/50"}`}
                            onClick={() => setExpandedProduct(expandedProduct === prod.product_id ? null : prod.product_id)}
                          >
                            {/* GAP-5.3: Row checkbox */}
                            <TableCell onClick={(e) => e.stopPropagation()}>
                              <Checkbox
                                checked={selectedIds.has(prod.product_id)}
                                onCheckedChange={() => toggleSelect(prod.product_id)}
                                aria-label={`Выбрать ${prod.name}`}
                              />
                            </TableCell>
                            <TableCell
                              role="button"
                              aria-label={expandedProduct === prod.product_id ? "Свернуть" : "Развернуть"}
                            >
                              {expandedProduct === prod.product_id ? (
                                <ChevronDown className="h-4 w-4 text-muted-foreground" />
                              ) : (
                                <ChevronRight className="h-4 w-4 text-muted-foreground" />
                              )}
                            </TableCell>
                            <TableCell className="font-mono text-xs">{prod.article ?? "\u2014"}</TableCell>
                            <TableCell className="font-medium text-sm max-w-[300px] truncate" title={prod.name}>
                              {prod.name}
                            </TableCell>
                            <TableCell>
                              <div className="flex flex-col text-xs text-muted-foreground max-w-[200px]">
                                <span className="font-medium text-foreground truncate" title={prod.brand}>{prod.brand ?? "\u2014"}</span>
                                <span className="truncate" title={prod.category_path}>{prod.category_path ?? "Без категории"}</span>
                              </div>
                            </TableCell>
                            <TableCell>
                              {prod.is_active ? (
                                <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">Активен</Badge>
                              ) : (
                                <Badge variant="outline" className="bg-gray-50 text-gray-700 border-gray-200">Архив</Badge>
                              )}
                            </TableCell>
                          </TableRow>
                          {expandedProduct === prod.product_id && (
                            <TableRow className="bg-muted/10">
                              <TableCell colSpan={6} className="p-4 border-t-0">
                                <div className="grid grid-cols-2 gap-4 text-sm bg-card p-4 rounded border">
                                  <div>
                                    <h4 className="font-medium mb-2 text-muted-foreground">Основная информация</h4>
                                    <dl className="space-y-1 text-xs">
                                      <div className="flex justify-between border-b pb-1">
                                        <dt className="text-muted-foreground">ID системный</dt>
                                        <dd className="font-mono select-all">{prod.product_id}</dd>
                                      </div>
                                      <div className="flex justify-between border-b pb-1">
                                        <dt className="text-muted-foreground">Артикул</dt>
                                        <dd className="font-mono select-all">{prod.article ?? "\u2014"}</dd>
                                      </div>
                                      <div className="flex justify-between border-b pb-1">
                                        <dt className="text-muted-foreground">Бренд</dt>
                                        <dd>{prod.brand ?? "\u2014"}</dd>
                                      </div>
                                      <div className="flex justify-between border-b pb-1">
                                        <dt className="text-muted-foreground">Категория</dt>
                                        <dd>{prod.category_path ?? "\u2014"}</dd>
                                      </div>
                                      <div className="flex justify-between border-b pb-1">
                                        <dt className="text-muted-foreground">Статус</dt>
                                        <dd>{prod.is_active ? "Доступен для маппинга" : "Архивный (скрыт)"}</dd>
                                      </div>
                                    </dl>
                                  </div>
                                  <div className="flex flex-col">
                                    <h4 className="font-medium mb-2 text-muted-foreground">Полное наименование</h4>
                                    <p className="text-xs border p-2 rounded bg-muted/30 select-all mb-4">
                                      {prod.name}
                                    </p>

                                    <div className="flex justify-end pt-4 border-t border-border mt-auto">
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="text-red-500 hover:bg-red-50 hover:text-red-700 h-8"
                                        onClick={() => setDeleteTarget({ id: prod.product_id, name: prod.name })}
                                        aria-label="Удалить товар"
                                      >
                                        <Trash2 className="h-4 w-4 mr-2" />
                                        Удалить товар
                                      </Button>
                                    </div>
                                  </div>
                                </div>
                              </TableCell>
                            </TableRow>
                          )}
                        </React.Fragment>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>

              {totalPages > 1 && (
                <Pagination
                  page={page}
                  totalPages={totalPages}
                  total={filteredData.length}
                  pageSize={PAGE_SIZE}
                  onPageChange={(p) => {
                    setPage(p);
                    setExpandedProduct(null);
                  }}
                  className="mt-4"
                />
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* GAP-5.4: Enhanced single delete confirmation with warning */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-red-500" />
              Удалить товар из каталога?
            </AlertDialogTitle>
            <AlertDialogDescription>
              <div className="space-y-3">
                <p>
                  Товар &laquo;{deleteTarget?.name}&raquo; будет безвозвратно удален.
                </p>
                <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3">
                  <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />
                  <p className="text-xs text-red-800">
                    Это действие необратимо. Товар и все его алиасы будут удалены из системы и из поискового индекса.
                  </p>
                </div>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-700 text-white"
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
              disabled={deleteMutation.isPending}
            >
              Удалить безвозвратно
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* GAP-5.3: Bulk delete confirmation */}
      <AlertDialog open={bulkDeleteOpen} onOpenChange={(open) => !open && setBulkDeleteOpen(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-red-500" />
              Удалить выбранные товары?
            </AlertDialogTitle>
            <AlertDialogDescription>
              <div className="space-y-3">
                <p>
                  Будет удалено товаров: {selectedIds.size}.
                </p>
                <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3">
                  <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />
                  <p className="text-xs text-red-800">
                    Это действие необратимо. Все выбранные товары и их алиасы будут удалены из системы и из поискового индекса.
                  </p>
                </div>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={bulkDeleting}>Отмена</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-700 text-white"
              onClick={handleBulkDelete}
              disabled={bulkDeleting}
            >
              {bulkDeleting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Удаление...
                </>
              ) : (
                `Удалить (${selectedIds.size})`
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* GAP-5.8: File format documentation dialog */}
      <Dialog open={fileFormatDialogOpen} onOpenChange={setFileFormatDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-green-600" />
              Загрузка каталога из файла
            </DialogTitle>
            <DialogDescription>
              Ознакомьтесь с требованиями к формату файла перед загрузкой.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="flex items-start gap-2 rounded-md border bg-muted/30 p-3">
              <Info className="h-4 w-4 text-blue-500 mt-0.5 shrink-0" />
              <div className="text-xs space-y-2">
                <p><span className="font-medium">Поддерживаемые форматы:</span> CSV, XLSX</p>
                <p><span className="font-medium">Обязательные колонки:</span> &laquo;Наименование&raquo; (name)</p>
                <p>
                  <span className="font-medium">Опциональные:</span>{" "}
                  &laquo;Артикул&raquo; (article), &laquo;Бренд&raquo; (brand),
                  &laquo;Категория&raquo; (category_path), &laquo;Единица&raquo; (unit)
                </p>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFileFormatDialogOpen(false)}>Отмена</Button>
            <Button onClick={handleFileFormatContinue}>
              <Upload className="mr-2 h-4 w-4" />
              Выбрать файл
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* GAP-5.9: File upload confirmation dialog */}
      <AlertDialog open={fileConfirmOpen} onOpenChange={(open) => !open && handleFileCancel()}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Подтверждение загрузки</AlertDialogTitle>
            <AlertDialogDescription>
              Будет загружено из файла: <span className="font-medium text-foreground">{pendingFile?.name}</span>.
              Данные будут добавлены в каталог. Продолжить?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={handleFileCancel}>Отмена</AlertDialogCancel>
            <AlertDialogAction onClick={handleFileConfirm}>
              Загрузить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}
