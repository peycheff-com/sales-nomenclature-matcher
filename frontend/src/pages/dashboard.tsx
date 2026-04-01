import { type ChangeEvent, type DragEvent, useCallback, useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import Papa from "papaparse";
import * as xlsx from "xlsx";
import { FileUp, Upload, ClipboardList, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { matchBatch } from "@/api/match";
import { listMatchRequests } from "@/api/match";
import { listSuppliers } from "@/api/suppliers";
import type { MatchItemInput } from "@/api/types";
import { REQUEST_STATUS_LABELS } from "@/lib/constants";
import { formatDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

const SUPPLIER_KEY = "matcher_supplier_id";

export default function DashboardPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Supplier selection persisted to localStorage
  const [supplierId, setSupplierId] = useState<string | undefined>(() => {
    return localStorage.getItem(SUPPLIER_KEY) || undefined;
  });

  // Tab state
  const [activeTab, setActiveTab] = useState<string>("file");

  // File upload state
  const [parsedItems, setParsedItems] = useState<MatchItemInput[]>([]);
  const [fileName, setFileName] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  // Text paste state
  const [textInput, setTextInput] = useState("");

  // Suppliers query
  const suppliersQuery = useQuery({
    queryKey: ["suppliers"],
    queryFn: listSuppliers,
  });

  // Recent requests
  const recentQuery = useQuery({
    queryKey: ["match-requests"],
    queryFn: listMatchRequests,
  });

  // Match mutation
  const matchMutation = useMutation({
    mutationFn: matchBatch,
    onSuccess: (data) => {
      toast.success("Запрос создан");
      navigate({ to: "/requests/$requestId", params: { requestId: data.request_id } });
    },
    onError: () => {
      toast.error("Ошибка при создании запроса");
    },
  });

  function handleSupplierChange(val: string | null) {
    const id = val === "__all__" || val == null ? undefined : val;
    setSupplierId(id);
    if (id) {
      localStorage.setItem(SUPPLIER_KEY, id);
    } else {
      localStorage.removeItem(SUPPLIER_KEY);
    }
  }

  function extractItemsFromData(data: Record<string, any>[]): MatchItemInput[] {
    return data.map((row, idx) => {
      const rawText =
        row["raw_text"] ||
        row["text"] ||
        row["name"] ||
        row["наименование"] ||
        row["Наименование"] ||
        Object.values(row)[0] ||
        "";
      const lineId = row["line_id"] || row["id"] || String(idx + 1);
      return { raw_text: String(rawText).trim(), line_id: String(lineId) };
    }).filter((i) => i.raw_text.length > 0);
  }

  // File parsing (CSV & XLSX)
  async function processFile(file: File) {
    setFileName(file.name);
    
    if (file.name.endsWith(".xls") || file.name.endsWith(".xlsx")) {
      try {
        const buffer = await file.arrayBuffer();
        const workbook = xlsx.read(buffer, { type: "array" });
        const sheetName = workbook.SheetNames[0];
        const sheet = workbook.Sheets[sheetName];
        const data = xlsx.utils.sheet_to_json<Record<string, any>>(sheet);
        setParsedItems(extractItemsFromData(data));
      } catch (e) {
        toast.error("Ошибка при чтении Excel файла");
      }
    } else {
      Papa.parse<Record<string, string>>(file, {
        header: true,
        skipEmptyLines: true,
        complete: (result) => {
          setParsedItems(extractItemsFromData(result.data));
        },
        error: () => {
          toast.error("Ошибка при чтении CSV файла");
        },
      });
    }
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) processFile(file);
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) processFile(file);
  }

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
  }, []);

  // Build items from text
  function getTextItems(): MatchItemInput[] {
    return textInput
      .split("\n")
      .map((line, idx) => ({
        raw_text: line.trim(),
        line_id: String(idx + 1),
      }))
      .filter((i) => i.raw_text.length > 0);
  }

  function handleSubmit() {
    const items = activeTab === "file" ? parsedItems : getTextItems();
    if (items.length === 0) {
      toast.error("Нет данных для сопоставления");
      return;
    }
    matchMutation.mutate({
      supplier_id: supplierId,
      source_type: activeTab === "file" ? "csv" : "text",
      items,
    });
  }

  const currentItems = activeTab === "file" ? parsedItems : getTextItems();
  const recentRequests = (recentQuery.data?.items ?? []).slice(0, 5);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Загрузка данных</h1>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Main upload area */}
        <div className="lg:col-span-2 space-y-4">
          {/* Supplier selector */}
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">Поставщик:</span>
            <Select
              value={supplierId ?? "__all__"}
              onValueChange={handleSupplierChange}
            >
              <SelectTrigger className="w-[260px]">
                <SelectValue placeholder="Выберите поставщика" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">Все поставщики</SelectItem>
                {suppliersQuery.data?.items.map((s) => (
                  <SelectItem key={s.supplier_id} value={s.supplier_id}>
                    {s.supplier_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Card>
            <CardContent className="pt-4">
              <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList>
                  <TabsTrigger value="file">Загрузить файл</TabsTrigger>
                  <TabsTrigger value="text">Вставить текст</TabsTrigger>
                </TabsList>

                <TabsContent value="file">
                  <div className="mt-4 space-y-4">
                    {/* Drag-and-drop zone */}
                    <div
                      className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
                        dragging
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/50"
                      }`}
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <FileUp className="mb-2 h-8 w-8 text-muted-foreground" />
                      <p className="text-sm text-muted-foreground">
                        Перетащите CSV или XLSX файл сюда или нажмите для выбора
                      </p>
                      {fileName && (
                        <p className="mt-2 text-sm font-medium text-foreground">
                          {fileName} ({parsedItems.length} строк)
                        </p>
                      )}
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".csv,.tsv,.txt,.xlsx,.xls"
                        className="hidden"
                        onChange={handleFileChange}
                      />
                    </div>

                    {/* Preview table */}
                    {parsedItems.length > 0 && (
                      <div className="max-h-60 overflow-auto rounded-md border border-border">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead className="w-16">#</TableHead>
                              <TableHead>Текст</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {parsedItems.slice(0, 20).map((item, idx) => (
                              <TableRow key={idx}>
                                <TableCell className="text-xs text-muted-foreground">
                                  {item.line_id}
                                </TableCell>
                                <TableCell className="text-sm">
                                  {item.raw_text}
                                </TableCell>
                              </TableRow>
                            ))}
                            {parsedItems.length > 20 && (
                              <TableRow>
                                <TableCell
                                  colSpan={2}
                                  className="text-center text-xs text-muted-foreground"
                                >
                                  ... и ещё {parsedItems.length - 20} строк
                                </TableCell>
                              </TableRow>
                            )}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="text">
                  <div className="mt-4 space-y-2">
                    <Textarea
                      rows={10}
                      placeholder="Введите наименования, каждое с новой строки..."
                      value={textInput}
                      onChange={(e) => setTextInput(e.target.value)}
                      className="min-h-[200px] font-mono text-sm"
                    />
                    {textInput.trim() && (
                      <p className="text-xs text-muted-foreground">
                        {getTextItems().length} позиций
                      </p>
                    )}
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          <Button
            size="lg"
            onClick={handleSubmit}
            disabled={matchMutation.isPending || currentItems.length === 0}
            className="w-full"
          >
            {matchMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Отправка...
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                Начать сопоставление ({currentItems.length} позиций)
              </>
            )}
          </Button>
        </div>

        {/* Recent requests sidebar */}
        <div>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <ClipboardList className="h-4 w-4" />
                Последние запросы
              </CardTitle>
            </CardHeader>
            <CardContent>
              {recentRequests.length === 0 ? (
                <p className="text-sm text-muted-foreground">Нет запросов</p>
              ) : (
                <div className="space-y-2">
                  {recentRequests.map((req) => {
                    const statusColor: Record<string, string> = {
                      queued: "bg-gray-100 text-gray-800",
                      running: "bg-blue-100 text-blue-800",
                      done: "bg-green-100 text-green-800",
                      failed: "bg-red-100 text-red-800",
                    };
                    return (
                      <button
                        key={req.request_id}
                        className="flex w-full items-center justify-between rounded-md border border-border px-3 py-2 text-left text-sm transition-colors hover:bg-muted/50"
                        onClick={() =>
                          navigate({
                            to: "/requests/$requestId",
                            params: { requestId: req.request_id },
                          })
                        }
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <Badge
                              variant="outline"
                              className={statusColor[req.status] ?? ""}
                            >
                              {REQUEST_STATUS_LABELS[req.status] ?? req.status}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {req.auto_matched_items + req.review_needed_items + req.no_match_items}/{req.total_items}
                            </span>
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {formatDate(req.created_at)}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
