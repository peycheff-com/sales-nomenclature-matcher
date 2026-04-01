import { type ChangeEvent, type DragEvent, useCallback, useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FileUp, Upload, ClipboardList, Loader2, Trash2, AlertTriangle, Database, PackageSearch } from "lucide-react";
import { toast } from "sonner";
import { matchBatch, parseFilePreview, parseFileStructured, smartUpload, listMatchRequests, previewGoogleSheet } from "@/api/match";
import type { FileAnalysisResult } from "@/api/match";
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
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { PageLayout } from "@/components/layout/page-layout";
import { EmptyState } from "@/components/ui/empty-state";

const SUPPLIER_KEY = "matcher_supplier_id";

export default function DashboardPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [supplierId, setSupplierId] = useState<string | undefined>(() => {
    return localStorage.getItem(SUPPLIER_KEY) || undefined;
  });

  const [activeTab, setActiveTab] = useState<string>("file");
  const [useAi, setUseAi] = useState(true);

  const [parsedItems, setParsedItems] = useState<MatchItemInput[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  // Structured analysis state (two-panel mode)
  const [structuredMode, setStructuredMode] = useState(false);
  const [catalogItems, setCatalogItems] = useState<any[]>([]);
  const [detectedSupplierName, setDetectedSupplierName] = useState<string | null>(null);
  const [editedSupplierName, setEditedSupplierName] = useState("");

  const [textInput, setTextInput] = useState("");
  const [gsheetUrl, setGsheetUrl] = useState("");


  const suppliersQuery = useQuery({
    queryKey: ["suppliers"],
    queryFn: listSuppliers,
  });

  const recentQuery = useQuery({
    queryKey: ["match-requests"],
    queryFn: () => listMatchRequests(),
  });

  const gsheetMutation = useMutation({
    mutationFn: previewGoogleSheet,
    onSuccess: (data) => {
      setParsedItems(extractItemsFromData(data.rows));
      setFileName("Google Sheet (" + gsheetUrl.slice(0, 30) + "...)");
    },
    onError: (err: any) => {
      toast.error("Ошибка при чтении Google Таблицы. Проверьте права доступа по ссылке.");
    }
  });

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

  const parseMutation = useMutation({
    mutationFn: ({ file, supplierId, useAiColumnPicker }: { file: File; supplierId?: string, useAiColumnPicker: boolean }) => parseFilePreview(file, useAiColumnPicker),
    onSuccess: (data) => {
      setStructuredMode(false);
      setCatalogItems([]);
      setDetectedSupplierName(null);
      setParsedItems(data.items);
      toast.success(`Извлечено ${data.items.length} позиций для предпросмотра`);
    },
    onError: (err: any) => {
      toast.error("Ошибка при разборе файла. Проверьте формат.");
    },
  });

  const structuredMutation = useMutation({
    mutationFn: (file: File) => parseFileStructured(file),
    onSuccess: (data) => {
      setStructuredMode(true);
      const supplierItems = (data.supplier_items || []).map((item: any, idx: number) => ({
        raw_text: item.raw_text,
        line_id: item.line_id || String(idx + 1),
        original_row: item.original_row,
      }));
      setParsedItems(supplierItems);
      setCatalogItems(data.catalog_items || []);
      const sn = data.supplier_name || null;
      setDetectedSupplierName(sn);
      setEditedSupplierName(sn || "");
      
      const msgs: string[] = [];
      if (supplierItems.length > 0) msgs.push(`${supplierItems.length} позиций поставщика`);
      if ((data.catalog_items || []).length > 0) msgs.push(`${data.catalog_items.length} позиций каталога`);
      if (sn) msgs.push(`поставщик: ${sn}`);
      toast.success(`Обнаружено ${data.tables_detected} таблиц: ${msgs.join(", ")}`);
    },
    onError: () => {
      toast.error("Ошибка при анализе структуры файла.");
    },
  });

  const smartUploadMutation = useMutation({
    mutationFn: ({ file, supplierName, supplierId }: { file: File; supplierName?: string; supplierId?: string }) =>
      smartUpload(file, { supplierName, supplierId }),
    onSuccess: (data) => {
      toast.success("Каталог + сопоставление запущены");
      navigate({ to: "/requests/$requestId", params: { requestId: data.request_id } });
    },
    onError: () => {
      toast.error("Ошибка при умной загрузке");
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
        row["Номенклатура клиента"] ||
        row["Номенклатура"] ||
        row["raw_text"] ||
        row["text"] ||
        row["name"] ||
        row["наименование"] ||
        row["Наименование"] ||
        Object.values(row).find(v => typeof v === 'string' && isNaN(Number(v))) ||
        Object.values(row)[0] ||
        "";
      const lineId = row["line_id"] || row["id"] || row["№"] || String(idx + 1);
      return { raw_text: String(rawText).trim(), line_id: String(lineId), original_row: row };
    }).filter((i) => i.raw_text.length > 0);
  }

  function processFile(file: File) {
    if (file.name.endsWith(".xls") || file.name.endsWith(".xlsx") || file.name.endsWith(".csv") || file.name.endsWith(".tsv") || file.name.endsWith(".txt")) {
      setSelectedFile(file);
      setFileName(file.name);
      if (useAi) {
        structuredMutation.mutate(file);
      } else {
        parseMutation.mutate({ file, supplierId, useAiColumnPicker: false });
      }
    } else {
      toast.error("Поддерживаются только форматы .xlsx, .xls, .csv, .txt");
    }
  }


  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) processFile(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
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

  function getTextItems(): MatchItemInput[] {
    return textInput
      .split("\n")
      .map((line, idx) => ({
        raw_text: line.trim(),
        line_id: String(idx + 1),
      }))
      .filter((i) => i.raw_text.length > 0);
  }

  const handleItemEdit = (idx: number, newText: string) => {
    const newItems = [...parsedItems];
    newItems[idx].raw_text = newText;
    setParsedItems(newItems);
  };

  const handleItemRemove = (idx: number) => {
    const newItems = [...parsedItems];
    newItems.splice(idx, 1);
    setParsedItems(newItems);
  };

  const checkDuplicates = (items: MatchItemInput[]) => {
    // Check internal duplicates
    const seen = new Set();
    let internalDups = 0;
    for (const item of items) {
      const lower = item.raw_text.toLowerCase();
      if (seen.has(lower)) internalDups++;
      seen.add(lower);
    }

    // Check recent requests for identical count (cheap heuristic for re-submission)
    const recentRequests = recentQuery.data?.items ?? [];
    const isResubmission = recentRequests.some(r => r.total_items === items.length && r.status !== 'failed');

    return { internalDups, isResubmission };
  };

  function handleSubmit() {
    // Smart upload path: structured mode with catalog items
    if (structuredMode && catalogItems.length > 0 && selectedFile) {
      const items = parsedItems;
      if (items.length === 0) {
        toast.error("Нет данных поставщика для сопоставления");
        return;
      }
      smartUploadMutation.mutate({
        file: selectedFile,
        supplierName: editedSupplierName || undefined,
        supplierId: supplierId,
      });
      return;
    }

    // Standard path
    const items = activeTab === "text" ? getTextItems() : parsedItems;
    if (items.length === 0) {
      toast.error("Нет данных для сопоставления");
      return;
    }

    const { internalDups, isResubmission } = checkDuplicates(items);
    if (isResubmission || internalDups > 0) {
      let msg = "";
      if (isResubmission) msg += `Кажется, вы уже отправляли запрос с таким же количеством позиций (${items.length}).\n`;
      if (internalDups > 0) msg += `Внутри списка найдено ${internalDups} дублирующихся строк.\n`;
      msg += "Хотите продолжить отправку?";

      if (!window.confirm(msg)) {
        return;
      }
    }

    let ext = "text";
    if (activeTab === "gsheet") {
      ext = "google_sheet";
    } else if (activeTab === "file" && fileName) {
      const split = fileName.split('.');
      ext = split[split.length - 1].toLowerCase();
    }

    matchMutation.mutate({
      supplier_id: supplierId,
      source_type: ext,
      items,
    });
  }

  const currentItems = activeTab === "text" ? getTextItems() : parsedItems;
  const recentRequests = (recentQuery.data?.items ?? []).slice(0, 5);

  const activeSuppliers = suppliersQuery.data?.items.filter(s => s.is_active) ?? [];

  return (
    <PageLayout
      title="Загрузка данных"
      description="Загрузите прайс-листы для сопоставления"
    >

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
                {activeSuppliers.map((s) => (
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
                  <TabsTrigger value="gsheet">Google Таблицы</TabsTrigger>
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
                          {fileName}
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
                    {fileName && (
                      <div className="flex items-center space-x-2 pt-2 px-1 mb-2">
                        <Switch id="ai-mode" checked={useAi} onCheckedChange={(val) => {
                          setUseAi(val);
                          if (selectedFile) parseMutation.mutate({ file: selectedFile, useAiColumnPicker: val });
                        }} />
                        <Label htmlFor="ai-mode" className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                          Использовать ИИ для поиска колонки (умный поиск)
                        </Label>
                        {parseMutation.isPending && <Loader2 className="ml-2 h-4 w-4 text-muted-foreground animate-spin" />}
                      </div>
                    )}
                    
                    {/* Preview table (Editable) */}
                    {parsedItems.length > 0 && activeTab === "file" && !structuredMode && (
                      <div className="space-y-2 mt-4">
                        <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
                          <span>Убедитесь, что ИИ или система выбрала правильную колонку (отображается до 50 строк)</span>
                          <span>Извлечено: {parsedItems.length} позиций</span>
                        </div>
                        <div className="max-h-80 overflow-auto rounded-md border border-border">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="w-16">#</TableHead>
                                <TableHead>Извлеченный текст для сопоставления</TableHead>
                                <TableHead className="w-12"></TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {parsedItems.slice(0, 50).map((item, idx) => (
                                <TableRow key={idx}>
                                  <TableCell className="text-xs text-muted-foreground py-1">
                                    {item.line_id || ""}
                                  </TableCell>
                                  <TableCell className="py-1">
                                    <Input 
                                      value={item.raw_text}
                                      onChange={(e) => handleItemEdit(idx, e.target.value)}
                                      className="h-7 px-2 text-sm"
                                    />
                                  </TableCell>
                                  <TableCell className="py-1 pr-4">
                                    <Button 
                                      variant="ghost" 
                                      size="sm" 
                                      className="h-7 w-7 p-0 text-muted-foreground hover:text-red-500"
                                      onClick={() => handleItemRemove(idx)}
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </Button>
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    )}

                    {/* Structured Mode Preview (Two-Panel UI) */}
                    {structuredMode && activeTab === "file" && (
                      <div className="mt-6 space-y-6">
                        <div className="rounded-lg border border-purple-200 bg-purple-50 p-4">
                          <h3 className="font-semibold text-purple-900 mb-2 flex items-center gap-2">
                            <Database className="h-4 w-4" />
                            Программный анализ структуры
                          </h3>
                          <p className="text-sm text-purple-800 mb-4">
                            ИИ успешно разобрал сложный файл и выделил отдельную таблицу каталога и прайс-лист поставщика.
                          </p>
                          <div className="space-y-3 max-w-sm">
                            <Label className="text-purple-900 font-medium text-xs uppercase tracking-wider">Определенный поставщик (исправьте при необходимости)</Label>
                            <Input 
                              value={editedSupplierName} 
                              onChange={(e) => setEditedSupplierName(e.target.value)}
                              placeholder="Название поставщика"
                              className="bg-white border-purple-200"
                            />
                          </div>
                        </div>

                        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                          {/* Supplier Panel */}
                          <div className="space-y-2 border rounded-md p-3 relative">
                            <div className="flex items-center justify-between text-sm font-semibold mb-2">
                              <span className="flex items-center gap-2"><ClipboardList className="h-4 w-4 text-primary" /> Позиции поставщика</span>
                              <Badge variant="secondary">{parsedItems.length}</Badge>
                            </div>
                            <div className="max-h-[300px] overflow-auto rounded border border-border">
                              <Table>
                                <TableHeader className="bg-muted/50 sticky top-0 z-10">
                                  <TableRow>
                                    <TableHead className="py-2 px-2 text-xs">#</TableHead>
                                    <TableHead className="py-2 px-2 text-xs">Номенклатура для сопоставления</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {parsedItems.slice(0, 50).map((item, idx) => (
                                    <TableRow key={idx}>
                                      <TableCell className="text-xs text-muted-foreground py-1 px-2">{item.line_id}</TableCell>
                                      <TableCell className="py-1 px-2 text-xs font-medium">{item.raw_text}</TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </div>
                            <p className="text-[10px] text-muted-foreground text-center mt-1">Отображаются первые 50 строк. Проверьте правильность выделения колонки.</p>
                          </div>

                          {/* Catalog Panel */}
                          <div className="space-y-2 border rounded-md p-3 border-blue-200 bg-blue-50/20">
                            <div className="flex items-center justify-between text-sm font-semibold mb-2">
                              <span className="flex items-center gap-2"><PackageSearch className="h-4 w-4 text-blue-600" /> Таблица каталога (Будет добавлена в базу)</span>
                              <Badge className="bg-blue-100 text-blue-800 hover:bg-blue-100">{catalogItems.length}</Badge>
                            </div>
                            <div className="max-h-[300px] overflow-auto rounded border border-blue-100 bg-white">
                              <Table>
                                <TableHeader className="bg-blue-50/50 sticky top-0 z-10">
                                  <TableRow>
                                    <TableHead className="py-2 px-2 text-xs">Наименование для каталога</TableHead>
                                    <TableHead className="py-2 px-2 text-xs w-[60px]">Ед.изм.</TableHead>
                                    <TableHead className="py-2 px-2 text-xs w-[60px]">Цена</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {catalogItems.slice(0, 50).map((item, idx) => (
                                    <TableRow key={idx}>
                                      <TableCell className="py-1 px-2 text-xs font-medium">{item.raw_text}</TableCell>
                                      <TableCell className="py-1 px-2 text-xs text-muted-foreground">{item.unit || "—"}</TableCell>
                                      <TableCell className="py-1 px-2 text-xs text-muted-foreground">{item.price || "—"}</TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </div>
                            <p className="text-[10px] text-muted-foreground text-center mt-1">При нажатии "Начать сопоставление", эти позиции пополнят ваш каталог перед алгоритмами поиска.</p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="gsheet">
                  <div className="mt-4 space-y-4">
                    <p className="text-sm text-muted-foreground">Вставьте ссылку на публичную Google Таблицу (обязательно включите доступ "Все у кого есть ссылка")</p>
                    <div className="flex gap-2">
                      <Input
                        placeholder="https://docs.google.com/spreadsheets/d/..."
                        value={gsheetUrl}
                        onChange={(e) => setGsheetUrl(e.target.value)}
                        className="flex-1"
                      />
                      <Button 
                        onClick={() => gsheetMutation.mutate(gsheetUrl)}
                        disabled={!gsheetUrl.trim() || gsheetMutation.isPending}
                      >
                        {gsheetMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        Загрузить
                      </Button>
                    </div>

                    {/* Preview table (Editable) */}
                    {parsedItems.length > 0 && activeTab === "gsheet" && (
                      <div className="space-y-2 mt-4">
                        <div className="flex items-center justify-between text-xs text-muted-foreground px-1">
                          <span>Предпросмотр данных (первые 50 строк)</span>
                          <span>Всего: {parsedItems.length}</span>
                        </div>
                        <div className="max-h-80 overflow-auto rounded-md border border-border">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead className="w-16">#</TableHead>
                                <TableHead>Текст для сопоставления</TableHead>
                                <TableHead className="w-12"></TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {parsedItems.slice(0, 50).map((item, idx) => (
                                <TableRow key={idx}>
                                  <TableCell className="text-xs text-muted-foreground py-1">
                                    <Input 
                                      value={item.line_id || ""}
                                      onChange={(e) => {
                                        const newItems = [...parsedItems];
                                        newItems[idx].line_id = e.target.value;
                                        setParsedItems(newItems);
                                      }}
                                      className="h-7 px-2 w-16 text-xs bg-muted/30"
                                    />
                                  </TableCell>
                                  <TableCell className="py-1">
                                    <Input 
                                      value={item.raw_text}
                                      onChange={(e) => handleItemEdit(idx, e.target.value)}
                                      className="h-7 px-2 text-sm"
                                    />
                                  </TableCell>
                                  <TableCell className="py-1 pr-4">
                                    <Button 
                                      variant="ghost" 
                                      size="sm" 
                                      className="h-7 w-7 p-0 text-muted-foreground hover:text-red-500"
                                      onClick={() => handleItemRemove(idx)}
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </Button>
                                  </TableCell>
                                </TableRow>
                              ))}
                              {parsedItems.length > 50 && (
                                <TableRow>
                                  <TableCell
                                    colSpan={3}
                                    className="text-center text-xs text-muted-foreground p-3"
                                  >
                                    ... и ещё {parsedItems.length - 50} строк
                                  </TableCell>
                                </TableRow>
                              )}
                            </TableBody>
                          </Table>
                        </div>
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
                      <div className="flex justify-between items-center text-xs text-muted-foreground px-1">
                        <span>{getTextItems().length} позиций</span>
                      </div>
                    )}
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          <Button
            size="lg"
            onClick={handleSubmit}
            disabled={currentItems.length === 0 || matchMutation.isPending || parseMutation.isPending}
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
                <EmptyState
                  icon={ClipboardList}
                  title="Нет запросов"
                  description="Загрузите ваш первый прайс-лист для сопоставления."
                />
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
    </PageLayout>
  );
}
