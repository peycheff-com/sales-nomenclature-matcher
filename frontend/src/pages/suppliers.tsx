import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listSuppliers, createSupplier, updateSupplier, createSupplierMapping } from "@/api/suppliers";
import type { SupplierCreate, SupplierUpdate, SupplierMappingCreate } from "@/api/suppliers";
import { searchCatalog } from "@/api/catalog";
import type { CatalogProduct } from "@/api/catalog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
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

  // --- Mapping dialog state ---
  const [mappingOpen, setMappingOpen] = useState(false);
  const [mappingSupplierId, setMappingSupplierId] = useState("");
  const [mappingForm, setMappingForm] = useState<SupplierMappingCreate>({
    supplier_raw_text: "",
    product_id: "",
    mapping_type: "exact",
  });

  // Catalog product search for product_id field
  const [catalogQuery, setCatalogQuery] = useState("");
  const [catalogResults, setCatalogResults] = useState<CatalogProduct[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [showCatalogDropdown, setShowCatalogDropdown] = useState(false);
  const [selectedProductLabel, setSelectedProductLabel] = useState("");

  useEffect(() => {
    if (catalogQuery.length < 2) {
      setCatalogResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setCatalogLoading(true);
      try {
        const results = await searchCatalog(catalogQuery, 10);
        setCatalogResults(results);
        setShowCatalogDropdown(true);
      } catch {
        setCatalogResults([]);
      } finally {
        setCatalogLoading(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [catalogQuery]);

  const mappingMutation = useMutation({
    mutationFn: (params: { supplierId: string; data: SupplierMappingCreate }) =>
      createSupplierMapping(params.supplierId, params.data),
    onSuccess: () => {
      setMappingOpen(false);
      setMappingForm({ supplier_raw_text: "", product_id: "", mapping_type: "exact" });
      setCatalogQuery("");
      setSelectedProductLabel("");
    },
  });

  function openMappingDialog(supplierId: string) {
    setMappingSupplierId(supplierId);
    setMappingForm({ supplier_raw_text: "", product_id: "", mapping_type: "exact" });
    setCatalogQuery("");
    setSelectedProductLabel("");
    setCatalogResults([]);
    setShowCatalogDropdown(false);
    setMappingOpen(true);
  }

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
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {suppliersQuery.isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8">Загрузка...</TableCell>
              </TableRow>
            ) : items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">Нет поставщиков</TableCell>
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
                  <TableCell>
                    <Button variant="outline" size="sm" onClick={() => openMappingDialog(s.supplier_id)}>
                      Маппинг
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Mapping creation dialog */}
      <Dialog open={mappingOpen} onOpenChange={setMappingOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Новый маппинг — {mappingSupplierId}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Исходный текст поставщика</Label>
              <Input
                placeholder="Текст из прайса поставщика"
                value={mappingForm.supplier_raw_text ?? ""}
                onChange={(e) => setMappingForm(f => ({ ...f, supplier_raw_text: e.target.value }))}
              />
            </div>

            <div className="space-y-2">
              <Label>Товар из каталога</Label>
              <div className="relative">
                <Input
                  placeholder="Поиск по каталогу..."
                  value={selectedProductLabel || catalogQuery}
                  onChange={(e) => {
                    setCatalogQuery(e.target.value);
                    setSelectedProductLabel("");
                    setMappingForm(f => ({ ...f, product_id: "" }));
                    setShowCatalogDropdown(true);
                  }}
                  onFocus={() => {
                    if (catalogResults.length > 0) setShowCatalogDropdown(true);
                  }}
                />
                {catalogLoading && (
                  <div className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
                    Поиск...
                  </div>
                )}
                {showCatalogDropdown && catalogResults.length > 0 && (
                  <div className="absolute z-50 mt-1 max-h-48 w-full overflow-y-auto rounded-md border bg-popover shadow-md">
                    {catalogResults.map(p => (
                      <button
                        key={p.product_id}
                        type="button"
                        className="flex w-full flex-col items-start px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground"
                        onClick={() => {
                          setMappingForm(f => ({ ...f, product_id: p.product_id }));
                          const label = `${p.name}${p.article ? ` (${p.article})` : ""}`;
                          setSelectedProductLabel(label);
                          setShowCatalogDropdown(false);
                          setCatalogQuery("");
                        }}
                      >
                        <span className="font-medium">{p.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {p.article && `Арт: ${p.article}`}{p.brand && ` | ${p.brand}`}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {mappingForm.product_id && (
                <p className="text-xs text-muted-foreground">ID: {mappingForm.product_id}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label>Тип маппинга</Label>
              <Select
                value={mappingForm.mapping_type}
                onValueChange={(val) => setMappingForm(f => ({ ...f, mapping_type: val || "exact" }))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Тип маппинга" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="exact">exact — точное совпадение</SelectItem>
                  <SelectItem value="approved">approved — подтверждённый</SelectItem>
                  <SelectItem value="manual">manual — ручной</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() =>
                mappingMutation.mutate({
                  supplierId: mappingSupplierId,
                  data: mappingForm,
                })
              }
              disabled={
                mappingMutation.isPending ||
                !mappingForm.supplier_raw_text ||
                !mappingForm.product_id
              }
            >
              {mappingMutation.isPending ? "Сохранение..." : "Сохранить маппинг"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
