import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  listSuppliers,
  createSupplier,
  listSupplierMappings,
  createSupplierMapping,
  updateSupplier,
} from "@/api/suppliers";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { ArrowLeft, Plus } from "lucide-react";
import type { SupplierProfile } from "@/api/types";

export default function SuppliersPage() {
  const queryClient = useQueryClient();
  const [supplierId, setSupplierId] = useState<string | null>(null);
  const [createSupplierOpen, setCreateSupplierOpen] = useState(false);
  const [createMappingOpen, setCreateMappingOpen] = useState(false);

  // Create supplier form state
  const [newSupplierId, setNewSupplierId] = useState("");
  const [newSupplierName, setNewSupplierName] = useState("");
  const [newSupplierStrict, setNewSupplierStrict] = useState(false);

  // Create mapping form state
  const [newMappingRawText, setNewMappingRawText] = useState("");
  const [newMappingProductId, setNewMappingProductId] = useState("");
  const [newMappingType, setNewMappingType] = useState("manual");

  // Queries
  const suppliersQuery = useQuery({
    queryKey: ["suppliers"],
    queryFn: listSuppliers,
  });

  const mappingsQuery = useQuery({
    queryKey: ["supplier-mappings", supplierId],
    queryFn: () => listSupplierMappings(supplierId!),
    enabled: !!supplierId,
  });

  const suppliers: SupplierProfile[] = suppliersQuery.data?.items ?? [];
  const selectedSupplier = suppliers.find((s) => s.supplier_id === supplierId);

  // Mutations
  const createSupplierMut = useMutation({
    mutationFn: () =>
      createSupplier({
        supplier_id: newSupplierId,
        supplier_name: newSupplierName,
        strict_mode: newSupplierStrict,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppliers"] });
      setCreateSupplierOpen(false);
      setNewSupplierId("");
      setNewSupplierName("");
      setNewSupplierStrict(false);
      toast.success("Поставщик создан");
    },
    onError: () => toast.error("Ошибка при создании поставщика"),
  });

  const updateSupplierMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { strict_mode?: boolean } }) =>
      updateSupplier(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["suppliers"] });
      toast.success("Поставщик обновлён");
    },
    onError: () => toast.error("Ошибка при обновлении поставщика"),
  });

  const createMappingMut = useMutation({
    mutationFn: () =>
      createSupplierMapping(supplierId!, {
        supplier_raw_text: newMappingRawText,
        product_id: newMappingProductId,
        mapping_type: newMappingType,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["supplier-mappings", supplierId],
      });
      setCreateMappingOpen(false);
      setNewMappingRawText("");
      setNewMappingProductId("");
      setNewMappingType("manual");
      toast.success("Маппинг создан");
    },
    onError: () => toast.error("Ошибка при создании маппинга"),
  });

  // Detail view
  if (supplierId && selectedSupplier) {
    const mappings = mappingsQuery.data ?? [];
    return (
      <PageLayout title="Поставщики">
        <div className="space-y-6">
          <Button
            variant="ghost"
            onClick={() => setSupplierId(null)}
            className="gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Назад
          </Button>

          {/* Supplier info card */}
          <div className="rounded-lg border p-6 space-y-4">
            <h2 className="text-xl font-semibold">
              {selectedSupplier.supplier_name}
            </h2>
            <div className="flex items-center gap-4">
              <Label htmlFor="strict-mode">Строгий режим</Label>
              <Switch
                id="strict-mode"
                checked={selectedSupplier.strict_mode}
                onCheckedChange={(checked) =>
                  updateSupplierMut.mutate({
                    id: supplierId,
                    data: { strict_mode: checked },
                  })
                }
              />
            </div>
          </div>

          <Tabs defaultValue="mappings">
            <TabsList>
              <TabsTrigger value="mappings">Маппинги</TabsTrigger>
              <TabsTrigger value="info">Информация</TabsTrigger>
            </TabsList>

            <TabsContent value="mappings" className="space-y-4">
              <div className="flex justify-end">
                <Button
                  onClick={() => setCreateMappingOpen(true)}
                  className="gap-2"
                >
                  <Plus className="h-4 w-4" />
                  Создать
                </Button>
              </div>

              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Текст поставщика</TableHead>
                    <TableHead>Продукт</TableHead>
                    <TableHead>Тип</TableHead>
                    <TableHead>Уверенность</TableHead>
                    <TableHead>Утвердил</TableHead>
                    <TableHead>Статус</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {mappings.map((m, idx) => (
                    <TableRow key={m.supplier_raw_text ?? idx}>
                      <TableCell>{m.supplier_raw_text ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{m.product_id}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{m.mapping_type ?? "—"}</Badge>
                      </TableCell>
                      <TableCell>
                        {m.confidence != null
                          ? (m.confidence * 100).toFixed(0) + "%"
                          : "—"}
                      </TableCell>
                      <TableCell>{(m as unknown as Record<string, unknown>).approved_by as string ?? "—"}</TableCell>
                      <TableCell>
                        {(m as unknown as Record<string, unknown>).is_active !== false ? (
                          <Badge variant="default">Активен</Badge>
                        ) : (
                          <Badge variant="secondary">Неактивен</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                  {mappings.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-muted-foreground">
                        Нет маппингов
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </TabsContent>

            <TabsContent value="info">
              <div className="rounded-lg border p-6 space-y-2 text-sm">
                <p>
                  <span className="font-medium">ID:</span>{" "}
                  {selectedSupplier.supplier_id}
                </p>
                <p>
                  <span className="font-medium">Название:</span>{" "}
                  {selectedSupplier.supplier_name}
                </p>
                <p>
                  <span className="font-medium">Строгий режим:</span>{" "}
                  {selectedSupplier.strict_mode ? "Да" : "Нет"}
                </p>
                <p>
                  <span className="font-medium">Статус:</span>{" "}
                  {selectedSupplier.is_active ? "Активен" : "Неактивен"}
                </p>
              </div>
            </TabsContent>
          </Tabs>
        </div>

        {/* Create mapping dialog */}
        <Dialog open={createMappingOpen} onOpenChange={setCreateMappingOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Создать маппинг</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label>Текст поставщика</Label>
                <Input
                  value={newMappingRawText}
                  onChange={(e) => setNewMappingRawText(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>ID продукта</Label>
                <Input
                  value={newMappingProductId}
                  onChange={(e) => setNewMappingProductId(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>Тип</Label>
                <Select value={newMappingType} onValueChange={(v) => setNewMappingType(v || "")}>
                  <SelectTrigger>
                    <SelectValue placeholder="Выберите тип" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">manual</SelectItem>
                    <SelectItem value="approved">approved</SelectItem>
                    <SelectItem value="exact">exact</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <DialogFooter>
              <Button
                onClick={() => createMappingMut.mutate()}
                disabled={
                  !newMappingRawText ||
                  !newMappingProductId ||
                  !newMappingType ||
                  createMappingMut.isPending
                }
              >
                Создать
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </PageLayout>
    );
  }

  // List view
  return (
    <PageLayout title="Поставщики">
      <div className="space-y-4">
        <div className="flex justify-end">
          <Button
            onClick={() => setCreateSupplierOpen(true)}
            className="gap-2"
          >
            <Plus className="h-4 w-4" />
            Создать
          </Button>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Название</TableHead>
              <TableHead>Строгий режим</TableHead>
              <TableHead>Статус</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {suppliers.map((s) => (
              <TableRow
                key={s.supplier_id}
                className="cursor-pointer"
                onClick={() => setSupplierId(s.supplier_id)}
              >
                <TableCell>{s.supplier_name}</TableCell>
                <TableCell>
                  <Badge variant={s.strict_mode ? "default" : "secondary"}>
                    {s.strict_mode ? "Строгий" : "Обычный"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={s.is_active ? "default" : "secondary"}>
                    {s.is_active ? "Активен" : "Неактивен"}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
            {suppliers.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  Нет поставщиков
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Create supplier dialog */}
      <Dialog open={createSupplierOpen} onOpenChange={setCreateSupplierOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Создать поставщика</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>ID</Label>
              <Input
                value={newSupplierId}
                onChange={(e) => setNewSupplierId(e.target.value)}
                placeholder="supplier_001"
              />
            </div>
            <div className="space-y-2">
              <Label>Название</Label>
              <Input
                value={newSupplierName}
                onChange={(e) => setNewSupplierName(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-4">
              <Label htmlFor="new-strict-mode">Строгий режим</Label>
              <Switch
                id="new-strict-mode"
                checked={newSupplierStrict}
                onCheckedChange={setNewSupplierStrict}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => createSupplierMut.mutate()}
              disabled={!newSupplierId || !newSupplierName || createSupplierMut.isPending}
            >
              Создать
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageLayout>
  );
}
