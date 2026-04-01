import React, { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Search, Server, Upload, RefreshCw, ChevronDown, ChevronRight, Trash2 } from "lucide-react";
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
import { PageLayout } from "@/components/layout/page-layout";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton, SkeletonTable } from "@/components/ui/skeleton";
import { QueryErrorBanner } from "@/components/ui/query-error-banner";
import { Pagination } from "@/components/ui/pagination";

const PAGE_SIZE = 25;

export default function CatalogPage() {
  const queryClient = useQueryClient();
  const [searchInput, setSearchInput] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [page, setPage] = useState(1);

  // Debounced live search - fires 400ms after user stops typing
  useEffect(() => {
    if (searchInput.trim().length < 2) {
      setDebouncedQuery("");
      return;
    }
    const timer = setTimeout(() => {
      setDebouncedQuery(searchInput.trim());
      setPage(1);
      setExpandedProduct(null);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);
  const [expandedProduct, setExpandedProduct] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const statsQuery = useQuery({
    queryKey: ["catalog-stats"],
    queryFn: getCatalogStats,
  });

  const productsQuery = useQuery({
    queryKey: ["catalog-search", debouncedQuery],
    queryFn: () => searchCatalog(debouncedQuery, 1000),
    enabled: !!debouncedQuery,
  });

  const importMutation = useMutation({
    mutationFn: importFromOnec,
    onSuccess: () => {
      toast.success("Импорт из 1С запущен (в фоне)");
    },
    onError: () => {
      toast.error("Ошибка при запуске импорта");
    },
  });

  const reindexMutation = useMutation({
    mutationFn: reindexCatalog,
    onSuccess: () => {
      toast.success("Переиндексация поиска запущена (в фоне)");
    },
    onError: () => {
      toast.error("Ошибка при запуске переиндексации");
    },
  });

  const uploadMutation = useMutation({
    mutationFn: uploadCatalogFile,
    onSuccess: () => {
      toast.success("Файл загружен. Импорт запущен (в фоне)");
      queryClient.invalidateQueries({ queryKey: ["catalog-stats"] });
    },
    onError: () => {
      toast.error("Ошибка при загрузке файла");
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
    onError: () => {
      toast.error("Ошибка при удалении товара");
    },
  });

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    uploadMutation.mutate(file);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setDebouncedQuery(searchInput.trim());
    setPage(1);
    setExpandedProduct(null);
  };

  const fetchedData = productsQuery.data ?? [];
  const totalPages = Math.ceil(fetchedData.length / PAGE_SIZE) || 1;
  const paginatedData = fetchedData.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <PageLayout
      title="Базовый каталог"
      description="Эталонная номенклатура (1С/PIM)."
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
                {statsQuery.isLoading ? <Skeleton className="h-8 w-20" /> : statsQuery.data?.total_products.toLocaleString() ?? "—"}
              </div>
              <p className="text-xs text-muted-foreground mt-1">Всего позиций в индексе</p>

              <div className="mt-4 pt-4 border-t border-border flex flex-col gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start text-xs"
                  onClick={() => importMutation.mutate()}
                  disabled={importMutation.isPending}
                >
                  <Server className="mr-2 h-4 w-4 text-blue-500" />
                  Синхронизировать с 1С
                </Button>
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
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadMutation.isPending}
                >
                  <Upload className="mr-2 h-4 w-4 text-green-500" />
                  {uploadMutation.isPending ? "Загрузка..." : "Загрузить из файла"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full justify-start text-xs"
                  onClick={() => reindexMutation.mutate()}
                  disabled={reindexMutation.isPending}
                >
                  <RefreshCw className="mr-2 h-4 w-4 text-orange-500" />
                  Обновить индекс поиска
                </Button>
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
              <form onSubmit={handleSearch} className="flex gap-2">
                <Input
                  placeholder="Артикул, наименование, бренд..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  className="max-w-md"
                />
                <Button type="submit" disabled={productsQuery.isFetching}>
                  <Search className="mr-2 h-4 w-4" />
                  Искать
                </Button>
              </form>

              <div className="mt-6 rounded-md border border-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10"></TableHead>
                      <TableHead>Артикул</TableHead>
                      <TableHead>Наименование</TableHead>
                      <TableHead>Бренд / Категория</TableHead>
                      <TableHead>Статус</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {!debouncedQuery ? (
                      <TableRow>
                        <TableCell colSpan={5} className="py-12 text-center text-sm text-muted-foreground">
                          Введите запрос для поиска по каталогу.
                        </TableCell>
                      </TableRow>
                    ) : productsQuery.isLoading ? (
                      <TableRow>
                        <TableCell colSpan={5} className="py-6">
                          <SkeletonTable rows={3} columns={4} />
                        </TableCell>
                      </TableRow>
                    ) : paginatedData.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="py-8">
                          <EmptyState
                            icon={Search}
                            title="Ничего не найдено"
                            description="По вашему запросу не найдено ни одного товара в каталоге."
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
                            <TableCell className="font-mono text-xs">{prod.article ?? "—"}</TableCell>
                            <TableCell className="font-medium text-sm max-w-[300px] truncate" title={prod.name}>
                              {prod.name}
                            </TableCell>
                            <TableCell>
                              <div className="flex flex-col text-xs text-muted-foreground max-w-[200px]">
                                <span className="font-medium text-foreground truncate" title={prod.brand}>{prod.brand ?? "—"}</span>
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
                              <TableCell colSpan={5} className="p-4 border-t-0">
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
                                        <dd className="font-mono select-all">{prod.article ?? "—"}</dd>
                                      </div>
                                      <div className="flex justify-between border-b pb-1">
                                        <dt className="text-muted-foreground">Бренд</dt>
                                        <dd>{prod.brand ?? "—"}</dd>
                                      </div>
                                      <div className="flex justify-between border-b pb-1">
                                        <dt className="text-muted-foreground">Категория</dt>
                                        <dd>{prod.category_path ?? "—"}</dd>
                                      </div>
                                      <div className="flex justify-between border-b pb-1">
                                        <dt className="text-muted-foreground">Статус</dt>
                                        <dd>{prod.is_active ? "Доступен для маппинга" : "Архивный (скрыт)"}</dd>
                                      </div>
                                    </dl>
                                  </div>
                                  <div>
                                    <h4 className="font-medium mb-2 text-muted-foreground">Полное наименование</h4>
                                    <p className="text-xs border p-2 rounded bg-muted/30 select-all mb-4">
                                      {prod.name}
                                    </p>

                                    <div className="flex justify-end pt-4 border-t border-border mt-auto h-full items-end">
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
                  total={fetchedData.length}
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

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить товар из каталога?</AlertDialogTitle>
            <AlertDialogDescription>
              Товар «{deleteTarget?.name}» и все привязанные к нему алиасы будут безвозвратно удалены.
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
    </PageLayout>
  );
}
