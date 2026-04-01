import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listSuppliers, createSupplier, updateSupplier } from "@/api/suppliers";
import type { SupplierCreate, SupplierUpdate } from "@/api/suppliers";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";

export default function SuppliersPage() {
  const queryClient = useQueryClient();
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [newSupplier, setNewSupplier] = useState<SupplierCreate>({
    supplier_id: "",
    supplier_name: "",
    strict_mode: false,
  });

  const suppliersQuery = useQuery({
    queryKey: ["suppliers", "all"],
    queryFn: listSuppliers,
  });

  const createMutation = useMutation({
    mutationFn: createSupplier,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppliers"] });
      setIsAddOpen(false);
      setNewSupplier({ supplier_id: "", supplier_name: "", strict_mode: false });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string, data: SupplierUpdate }) => updateSupplier(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["suppliers"] }),
  });

  const items = suppliersQuery.data?.items || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Поставщики</h1>
          <p className="text-muted-foreground">Управление поставщиками и профилями маппинга.</p>
        </div>
        
        <Dialog open={isAddOpen} onOpenChange={setIsAddOpen}>
          <DialogTrigger>
            <Button>Добавить поставщика</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Новый поставщик</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label>ID поставщика (уникальный)</Label>
                <Input
                  value={newSupplier.supplier_id}
                  onChange={(e) => setNewSupplier(s => ({ ...s, supplier_id: e.target.value }))}
                />
              </div>
              <div className="space-y-2">
                <Label>Наименование</Label>
                <Input
                  value={newSupplier.supplier_name}
                  onChange={(e) => setNewSupplier(s => ({ ...s, supplier_name: e.target.value }))}
                />
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={newSupplier.strict_mode}
                  onCheckedChange={(v: boolean) => setNewSupplier(s => ({ ...s, strict_mode: v }))}
                />
                <Label>Строгий режим (только точные совпадения)</Label>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={() => createMutation.mutate(newSupplier)} disabled={createMutation.isPending || !newSupplier.supplier_id || !newSupplier.supplier_name}>
                Сохранить
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="rounded-md border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Наименование</TableHead>
              <TableHead>Строгий режим</TableHead>
              <TableHead>Активен</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {suppliersQuery.isLoading ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center py-8">Загрузка...</TableCell>
              </TableRow>
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center py-8 text-muted-foreground">Нет поставщиков</TableCell>
              </TableRow>
            ) : (
              items.map(s => (
                <TableRow key={s.supplier_id}>
                  <TableCell className="font-mono">{s.supplier_id}</TableCell>
                  <TableCell>{s.supplier_name}</TableCell>
                  <TableCell>
                    <Switch
                      checked={s.strict_mode}
                      onCheckedChange={(v: boolean) => updateMutation.mutate({ id: s.supplier_id, data: { strict_mode: v } })}
                    />
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={s.is_active}
                      onCheckedChange={(v: boolean) => updateMutation.mutate({ id: s.supplier_id, data: { is_active: v } })}
                    />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
