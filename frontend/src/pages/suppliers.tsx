import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus, X, Store, Trash2, Edit2, Loader2, ChevronDown, ChevronRight,
  HelpCircle, Package, Search, Download, AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import Papa from "papaparse";
import {
  createSupplier,
  updateSupplier,
  listSuppliers,
  deleteSupplier,
  listSupplierMappings
} from "@/api/suppliers";
import { listMatchRequests } from "@/api/match";
import type { SupplierProfile } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
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
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { PageLayout } from "@/components/layout/page-layout";
import { EmptyState } from "@/components/ui/empty-state";
import { SkeletonTable } from "@/components/ui/skeleton";
import { QueryErrorBanner } from "@/components/ui/query-error-banner";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

const SUPPLIER_ID_PATTERN = /^[a-zA-Z0-9_]*$/;

export default function SuppliersPage() {
  const queryClient = useQueryClient();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newSupplierId, setNewSupplierId] = useState("");
  const [newSupplierName, setNewSupplierName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<SupplierProfile | null>(null);
  const [toggleWarning, setToggleWarning] = useState<SupplierProfile | null>(null);

  // GAP-6.1: Real-time ID validation
  const [idTouched, setIdTouched] = useState(false);
  const idValid = SUPPLIER_ID_PATTERN.test(newSupplierId);
  const idError = idTouched && newSupplierId.length > 0 && !idValid;

  // GAP-6.7: Active request count for deactivation warning
  const [activeRequestCount, setActiveRequestCount] = useState<number | null>(null);
  const [activeRequestLoading, setActiveRequestLoading] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editNameValue, setEditNameValue] = useState("");

  const [expandedSupplier, setExpandedSupplier] = useState<string | null>(null);

  const suppliersQuery = useQuery({
    queryKey: ["suppliers"],
    queryFn: listSuppliers,
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      return createSupplier({
        supplier_id: newSupplierId,
        supplier_name: newSupplierName,
        strict_mode: false,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppliers"] });
      setIsCreateOpen(false);
      setNewSupplierId("");
      setNewSupplierName("");
      setIdTouched(false);
      toast.success("Поставщик успешно добавлен");
    },
    onError: () => toast.error("Ошибка при добавлении поставщика"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, ...data }: { id: string; supplier_name?: string; strict_mode?: boolean; is_active?: boolean }) => {
      return updateSupplier(id, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppliers"] });
      toast.success("Изменения сохранены");
      setEditingId(null);
    },
    onError: () => toast.error("Ошибка при сохранении"),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteSupplier,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppliers"] });
      setDeleteTarget(null);
      toast.success("Поставщик удален");
    },
    onError: () => {
      setDeleteTarget(null);
      toast.error("Не удалось удалить поставщика");
    },
  });

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSupplierId || !newSupplierName) {
      toast.error("Заполните обязательные поля");
      return;
    }
    if (!idValid) {
      toast.error("Недопустимый формат ID");
      return;
    }
    createMutation.mutate();
  };

  const handleCreateDialogChange = (open: boolean) => {
    setIsCreateOpen(open);
    if (!open) {
      setNewSupplierId("");
      setNewSupplierName("");
      setIdTouched(false);
    }
  };

  const startEditing = (s: SupplierProfile) => {
    setEditingId(s.supplier_id);
    setEditNameValue(s.supplier_name);
  };

  // GAP-6.7: Check active requests before deactivation
  const handleToggleActive = async (s: SupplierProfile, val: boolean) => {
    if (!val) {
      setActiveRequestLoading(true);
      setActiveRequestCount(null);
      try {
        const [queuedRes, runningRes] = await Promise.all([
          listMatchRequests({ supplier_id: s.supplier_id, status: "queued", limit: 100 }),
          listMatchRequests({ supplier_id: s.supplier_id, status: "running", limit: 100 }),
        ]);
        const count = (queuedRes.items?.length ?? 0) + (runningRes.items?.length ?? 0);
        setActiveRequestCount(count);
      } catch {
        setActiveRequestCount(null);
      } finally {
        setActiveRequestLoading(false);
      }
      setToggleWarning(s);
    } else {
      updateMutation.mutate({ id: s.supplier_id, is_active: val });
    }
  };

  const suppliers = suppliersQuery.data?.items ?? [];

  return (
    <PageLayout
      title="Управление поставщиками"
      description="Настройка профилей контрагентов."
      actions={
        <Dialog open={isCreateOpen} onOpenChange={handleCreateDialogChange}>
          <DialogTrigger className="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground shadow hover:bg-primary/90 h-9 px-4 py-2">
            <Plus className="mr-2 h-4 w-4" />
            Добавить поставщика
          </DialogTrigger>
          <DialogContent>
            <form onSubmit={handleCreateSubmit}>
              <DialogHeader>
                <DialogTitle>Новый поставщик</DialogTitle>
                <DialogDescription>
                  Создайте профиль для загрузки прайс-листов и настройки правил.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="id">ID (Системный код)</Label>
                  <Input
                    id="id"
                    placeholder="partner_xyz"
                    value={newSupplierId}
                    onChange={(e) => {
                      setNewSupplierId(e.target.value);
                      if (!idTouched) setIdTouched(true);
                    }}
                    onBlur={() => setIdTouched(true)}
                    aria-invalid={idError || undefined}
                    className={idError ? "border-red-500 focus-visible:border-red-500 focus-visible:ring-red-500/20" : ""}
                  />
                  {/* GAP-6.1: Validation message */}
                  {idError ? (
                    <p className="text-[10px] text-red-600 font-medium">
                      Только латиница, цифры и подчеркивания
                    </p>
                  ) : (
                    <p className="text-[10px] text-muted-foreground">Только латиница и подчеркивания. Нельзя изменить позже.</p>
                  )}
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="name">Наименование</Label>
                  <Input
                    id="name"
                    placeholder="ООО Ромашка"
                    value={newSupplierName}
                    onChange={(e) => setNewSupplierName(e.target.value)}
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" type="button" onClick={() => handleCreateDialogChange(false)}>Отмена</Button>
                <Button
                  type="submit"
                  disabled={createMutation.isPending || !idValid || !newSupplierId || !newSupplierName}
                >
                  {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin"/>}
                  Создать
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      }
    >

      {suppliersQuery.isError && (
        <QueryErrorBanner
          error={suppliersQuery.error}
          title="Ошибка загрузки поставщиков"
          onRetry={() => suppliersQuery.refetch()}
        />
      )}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10"></TableHead>
                <TableHead>Поставщик</TableHead>
                <TableHead>Системный ID</TableHead>
                <TableHead>
                  <div className="flex items-center gap-1">
                    Строгий режим
                    <Tooltip>
                      <TooltipTrigger>
                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
                      </TooltipTrigger>
                      <TooltipContent>
                        В строгом режиме система требует точного совпадения артикулов
                      </TooltipContent>
                    </Tooltip>
                  </div>
                </TableHead>
                <TableHead>Статус</TableHead>
                <TableHead className="text-right w-24">Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {suppliersQuery.isLoading ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-6">
                    <SkeletonTable rows={3} columns={5} />
                  </TableCell>
                </TableRow>
              ) : suppliers.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-8">
                    <EmptyState
                      icon={Store}
                      title="Нет поставщиков"
                      description="Добавьте первого поставщика, чтобы начать загрузку прайс-листов."
                    />
                  </TableCell>
                </TableRow>
              ) : (
                suppliers.map((s) => (
                  <React.Fragment key={s.supplier_id}>
                    <TableRow className={expandedSupplier === s.supplier_id ? "bg-muted/30" : ""}>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0"
                          onClick={() => setExpandedSupplier(expandedSupplier === s.supplier_id ? null : s.supplier_id)}
                          aria-label={expandedSupplier === s.supplier_id ? "Свернуть" : "Развернуть"}
                        >
                          {expandedSupplier === s.supplier_id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                        </Button>
                      </TableCell>
                      <TableCell className="font-medium">
                        {editingId === s.supplier_id ? (
                          <div className="flex flex-col gap-1 w-[200px]">
                            <Input
                              value={editNameValue}
                              onChange={(e) => setEditNameValue(e.target.value)}
                              className="h-7 text-xs"
                              autoFocus
                            />
                            <div className="flex gap-1">
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-6 flex-1 text-[10px]"
                                onClick={() => updateMutation.mutate({ id: s.supplier_id, supplier_name: editNameValue })}
                              >
                                Сохранить
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 px-2 text-muted-foreground"
                                onClick={() => setEditingId(null)}
                                aria-label="Отменить редактирование"
                              >
                                <X className="h-3 w-3" />
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <Store className="h-4 w-4 text-muted-foreground" />
                            <span className="truncate max-w-[200px]" title={s.supplier_name}>{s.supplier_name}</span>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-5 w-5 opacity-50 hover:opacity-100"
                              onClick={() => startEditing(s)}
                              aria-label="Редактировать название"
                            >
                              <Edit2 className="h-3 w-3" />
                            </Button>
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {s.supplier_id}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Switch
                            checked={s.strict_mode}
                            onCheckedChange={(val) => updateMutation.mutate({ id: s.supplier_id, strict_mode: val })}
                          />
                          <span className="text-xs text-muted-foreground">
                            {s.strict_mode ? "Вкл" : "Откл"}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Switch
                            checked={s.is_active}
                            onCheckedChange={(val) => handleToggleActive(s, val)}
                          />
                          <Badge variant="outline" className={s.is_active ? "bg-green-50 text-green-700" : "bg-gray-50 text-gray-700"}>
                            {s.is_active ? "Активен" : "Отключен"}
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-red-500 hover:bg-red-50 hover:text-red-700"
                          onClick={() => setDeleteTarget(s)}
                          aria-label="Удалить поставщика"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                    {expandedSupplier === s.supplier_id && (
                      <TableRow className="bg-muted/10">
                        <TableCell colSpan={6} className="border-t-0 p-4">
                          <MappingsPanel supplier={s} />
                        </TableCell>
                      </TableRow>
                    )}
                  </React.Fragment>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* GAP-6.7: Enhanced deactivation warning with active request info */}
      <AlertDialog open={!!toggleWarning} onOpenChange={(open) => { if (!open) { setToggleWarning(null); setActiveRequestCount(null); } }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Отключить поставщика?</AlertDialogTitle>
            <AlertDialogDescription>
              <div className="space-y-3">
                <p>
                  Поставщик <span className="font-medium text-foreground">{toggleWarning?.supplier_name}</span> больше не сможет загружать данные в систему,
                  а его маппинги не будут применяться.
                </p>
                {activeRequestLoading && (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Проверка активных запросов...
                  </div>
                )}
                {activeRequestCount != null && activeRequestCount > 0 && (
                  <div className="flex items-start gap-2 rounded-md border border-orange-200 bg-orange-50 p-3">
                    <AlertTriangle className="h-4 w-4 text-orange-600 mt-0.5 shrink-0" />
                    <p className="text-xs text-orange-800">
                      У этого поставщика есть {activeRequestCount} активных запросов. Деактивация может повлиять на их обработку.
                    </p>
                  </div>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              className="bg-orange-600 hover:bg-orange-700 text-white"
              onClick={() => {
                if (toggleWarning) {
                  updateMutation.mutate({ id: toggleWarning.supplier_id, is_active: false });
                  setToggleWarning(null);
                  setActiveRequestCount(null);
                }
              }}
            >
              Отключить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить поставщика?</AlertDialogTitle>
            <AlertDialogDescription>
              Вы собираетесь навсегда удалить <span className="font-medium text-foreground">{deleteTarget?.supplier_name}</span> и
              все сопутствующие маппинги и настройки. Это действие необратимо.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-700 text-white"
              onClick={() => {
                if (deleteTarget) {
                  deleteMutation.mutate(deleteTarget.supplier_id);
                }
              }}
            >
              Удалить безвозвратно
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}

const MAPPINGS_PAGE_SIZE = 50;

function MappingsPanel({ supplier }: { supplier: SupplierProfile }) {
  const mappingsQuery = useQuery({
    queryKey: ["supplier-mappings", supplier.supplier_id],
    queryFn: () => listSupplierMappings(supplier.supplier_id, 500),
  });

  // GAP-6.5: Search within mappings
  const [mappingSearch, setMappingSearch] = useState("");
  const debouncedMappingSearch = useDebouncedValue(mappingSearch.trim().toLowerCase(), 300);

  const allMappings = mappingsQuery.data ?? [];

  const filteredMappings = useMemo(() => {
    if (!debouncedMappingSearch) return allMappings;
    return allMappings.filter(
      (m: any) =>
        (m.supplier_raw_text ?? "").toLowerCase().includes(debouncedMappingSearch) ||
        (m.product_id ?? "").toLowerCase().includes(debouncedMappingSearch) ||
        (m.supplier_article ?? "").toLowerCase().includes(debouncedMappingSearch)
    );
  }, [allMappings, debouncedMappingSearch]);

  // GAP-6.4: Pagination for mappings
  const [visibleCount, setVisibleCount] = useState(MAPPINGS_PAGE_SIZE);
  const displayedMappings = filteredMappings.slice(0, visibleCount);
  const hasMore = filteredMappings.length > visibleCount;

  // Reset visible count when search changes
  useEffect(() => {
    setVisibleCount(MAPPINGS_PAGE_SIZE);
  }, [debouncedMappingSearch]);

  // GAP-6.6: Export mappings to CSV
  const handleExportCSV = useCallback(() => {
    if (!allMappings.length) return;

    const rows = allMappings.map((m: any) => ({
      "Исходный текст поставщика": m.supplier_raw_text ?? "",
      "Артикул поставщика": m.supplier_article ?? "",
      "ID целевого товара": m.product_id ?? "",
    }));

    const csv = Papa.unparse(rows);
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `mappings-${supplier.supplier_id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [allMappings, supplier.supplier_id]);

  return (
    <div className="bg-background rounded-md border p-4 shadow-sm">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h3 className="font-medium text-sm flex items-center gap-2">
          Маппинги ({allMappings.length})
        </h3>
        <div className="flex items-center gap-2">
          {/* GAP-6.5: Search within mappings */}
          {allMappings.length > 0 && (
            <div className="relative">
              <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Поиск по маппингам..."
                value={mappingSearch}
                onChange={(e) => setMappingSearch(e.target.value)}
                className="h-7 w-[200px] pl-7 text-xs"
              />
            </div>
          )}
          {/* GAP-6.6: Export button */}
          {allMappings.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={handleExportCSV}
            >
              <Download className="mr-1.5 h-3.5 w-3.5" />
              CSV
            </Button>
          )}
        </div>
      </div>

      <p className="text-[10px] text-muted-foreground mb-3">
        Маппинги создаются автоматически при проверке результатов
      </p>

      {mappingsQuery.isLoading ? (
        <SkeletonTable rows={3} columns={3} />
      ) : !allMappings.length ? (
        <EmptyState
          icon={Package}
          title="Нет маппингов"
          description="У этого поставщика пока нет сохранённых маппингов (алиасов)."
          variant="no-results"
        />
      ) : (
        <>
          {/* Show filtered count when searching */}
          {debouncedMappingSearch && (
            <p className="text-[10px] text-muted-foreground mb-2">
              Найдено: {filteredMappings.length} из {allMappings.length}
            </p>
          )}
          <div className="max-h-[300px] overflow-auto rounded border">
            <Table>
              <TableHeader className="bg-muted/50 sticky top-0 z-10">
                <TableRow>
                  <TableHead className="py-2.5">Исходный текст поставщика</TableHead>
                  <TableHead className="py-2.5">Артикул поставщика</TableHead>
                  <TableHead className="py-2.5">ID Целевого товара (База)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {displayedMappings.map((m: any, idx: number) => (
                  <TableRow key={idx} className="text-xs">
                    <TableCell className="py-2 font-medium">{m.supplier_raw_text ?? "\u2014"}</TableCell>
                    <TableCell className="py-2 text-muted-foreground">{m.supplier_article ?? "\u2014"}</TableCell>
                    <TableCell className="py-2 font-mono text-muted-foreground">{m.product_id}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* GAP-6.4: Pagination info and "show more" */}
          {filteredMappings.length > MAPPINGS_PAGE_SIZE && (
            <div className="mt-2 flex items-center justify-between">
              <p className="text-[10px] text-muted-foreground">
                Показаны {Math.min(visibleCount, filteredMappings.length)} из {filteredMappings.length} маппингов
              </p>
              {hasMore && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-[10px]"
                  onClick={() => setVisibleCount((prev) => prev + MAPPINGS_PAGE_SIZE)}
                >
                  Показать ещё
                </Button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
