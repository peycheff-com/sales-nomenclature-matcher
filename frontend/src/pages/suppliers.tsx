import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Check, X, Store, Trash2, Edit2, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import {
  createSupplier,
  updateSupplier,
  listSuppliers,
  deleteSupplier,
  listSupplierMappings
} from "@/api/suppliers";
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
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
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

export default function SuppliersPage() {
  const queryClient = useQueryClient();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newSupplierId, setNewSupplierId] = useState("");
  const [newSupplierName, setNewSupplierName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<SupplierProfile | null>(null);
  const [toggleWarning, setToggleWarning] = useState<SupplierProfile | null>(null);
  
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
    createMutation.mutate();
  };

  const startEditing = (s: SupplierProfile) => {
    setEditingId(s.supplier_id);
    setEditNameValue(s.supplier_name);
  };

  const handleToggleActive = (s: SupplierProfile, val: boolean) => {
    if (!val) {
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
        <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
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
                    onChange={(e) => setNewSupplierId(e.target.value)}
                  />
                  <p className="text-[10px] text-muted-foreground">Только латиница и подчеркивания. Нельзя изменить позже.</p>
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
                <Button variant="outline" type="button" onClick={() => setIsCreateOpen(false)}>Отмена</Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin"/>}
                  Создать
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      }
    >

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10"></TableHead>
                <TableHead>Поставщик</TableHead>
                <TableHead>Системный ID</TableHead>
                <TableHead>Строгий режим</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead className="text-right w-24">Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {suppliersQuery.isLoading ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-24 text-center">
                    <Loader2 className="mx-auto h-6 w-6 animate-spin text-muted-foreground" />
                  </TableCell>
                </TableRow>
              ) : suppliers.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                    Нет активных поставщиков
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
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                    {expandedSupplier === s.supplier_id && (
                      <TableRow className="bg-muted/10">
                        <TableCell colSpan={7} className="border-t-0 p-4">
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

      <AlertDialog open={!!toggleWarning} onOpenChange={(open) => !open && setToggleWarning(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Отключить поставщика?</AlertDialogTitle>
            <AlertDialogDescription>
              Поставщик <span className="font-medium text-foreground">{toggleWarning?.supplier_name}</span> больше не сможет загружать данные в систему,
              а его маппинги не будут применяться.
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

function MappingsPanel({ supplier }: { supplier: SupplierProfile }) {
  const mappingsQuery = useQuery({
    queryKey: ["supplier-mappings", supplier.supplier_id],
    queryFn: () => listSupplierMappings(supplier.supplier_id, 100),
  });

  return (
    <div className="bg-background rounded-md border p-4 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-sm flex items-center gap-2">
          Маппинги ({mappingsQuery.data?.length ?? 0})
        </h3>
      </div>
      
      {mappingsQuery.isLoading ? (
        <div className="text-center py-4 text-xs text-muted-foreground animate-pulse">Загрузка маппингов...</div>
      ) : !mappingsQuery.data || mappingsQuery.data.length === 0 ? (
        <div className="text-center py-6 text-sm text-muted-foreground border border-dashed rounded">
          У этого поставщика пока нет сохранённых маппингов (алиасов).
        </div>
      ) : (
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
              {mappingsQuery.data.map((m, idx) => (
                <TableRow key={idx} className="text-xs">
                  <TableCell className="py-2 font-medium">{m.supplier_raw_text ?? "\u2014"}</TableCell>
                  <TableCell className="py-2 text-muted-foreground">{m.supplier_article ?? "\u2014"}</TableCell>
                  <TableCell className="py-2 font-mono text-muted-foreground">{m.product_id}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
