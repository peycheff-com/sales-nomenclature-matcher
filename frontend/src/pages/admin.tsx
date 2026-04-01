import { useCallback, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Database,
  RefreshCw,
  BarChart3,
  Loader2,
  Upload,
  Server,
  FileSpreadsheet,
  CheckCircle2,
  AlertCircle,
  Link,
} from "lucide-react";
import { toast } from "sonner";
import {
  getCatalogStats,
  importFromOnec,
  reindexCatalog,
  uploadCatalogFile,
} from "@/api/catalog";
import { getQualityMetrics } from "@/api/metrics";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function AdminPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Администрирование</h1>

      <div className="space-y-6 max-w-4xl">
        <CatalogSection />
        <MetricsSection />
      </div>
    </div>
  );
}

function CatalogSection() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [reindexStatus, setReindexStatus] = useState<string | null>(null);

  const statsQuery = useQuery({
    queryKey: ["catalog-stats"],
    queryFn: getCatalogStats,
  });

  const uploadMutation = useMutation({
    mutationFn: uploadCatalogFile,
    onSuccess: (data) => {
      toast.success(`Импорт запущен (${data.job_id})`);
      queryClient.invalidateQueries({ queryKey: ["catalog-stats"] });
    },
    onError: () => toast.error("Не удалось загрузить файл"),
  });

  const onecMutation = useMutation({
    mutationFn: importFromOnec,
    onSuccess: (data) => {
      toast.success(`Импорт из 1С запущен (${data.job_id})`);
      queryClient.invalidateQueries({ queryKey: ["catalog-stats"] });
    },
    onError: () => toast.error("Не удалось подключиться к 1С. Проверьте настройки."),
  });

  const reindexMutation = useMutation({
    mutationFn: () => reindexCatalog(),
    onSuccess: (data) => {
      setReindexStatus(`Задача: ${data.job_id}`);
      toast.success("Переиндексация запущена");
    },
    onError: () => toast.error("Не удалось запустить переиндексацию"),
  });

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        uploadMutation.mutate(file);
        e.target.value = "";
      }
    },
    [uploadMutation],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (file && (file.name.endsWith(".csv") || file.name.endsWith(".xlsx"))) {
        uploadMutation.mutate(file);
      } else {
        toast.error("Поддерживаются только файлы CSV и XLSX");
      }
    },
    [uploadMutation],
  );

  const stats = statsQuery.data;
  const anyLoading = uploadMutation.isPending || onecMutation.isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Database className="h-5 w-5" />
          Каталог номенклатуры
        </CardTitle>
        <CardDescription>
          {stats ? (
            <span className="flex items-center gap-4">
              <span className="flex items-center gap-1">
                <FileSpreadsheet className="h-3.5 w-3.5" />
                {stats.total_products.toLocaleString("ru-RU")} товаров в базе
              </span>
              <span className="flex items-center gap-1">
                {stats.onec_connected ? (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                    <span className="text-green-700">1С подключена</span>
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>1С не настроена</span>
                  </>
                )}
              </span>
            </span>
          ) : (
            "Загрузка..."
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Method 1: File Upload — primary */}
        <div className="space-y-2">
          <div className="text-sm font-medium flex items-center gap-2">
            <Upload className="h-4 w-4" />
            Загрузить файл из 1С
          </div>
          <p className="text-xs text-muted-foreground">
            Откройте справочник «Номенклатура» в 1С → Ещё → Вывести список → Сохранить как Excel (.xlsx) или CSV.
            Затем перетащите файл сюда.
          </p>
          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            className="flex items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/25 p-6 transition-colors hover:border-muted-foreground/50 cursor-pointer"
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={handleFileSelect}
            />
            {uploadMutation.isPending ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Загрузка и обработка файла...
              </div>
            ) : (
              <div className="text-center">
                <FileSpreadsheet className="mx-auto h-8 w-8 text-muted-foreground/50" />
                <div className="mt-2 text-sm text-muted-foreground">
                  Перетащите CSV или XLSX файл сюда
                </div>
                <div className="text-xs text-muted-foreground/70">
                  или нажмите для выбора
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Method 2: 1C OData — secondary */}
        <div className="flex items-center justify-between rounded-md border border-border p-3">
          <div>
            <div className="text-sm font-medium flex items-center gap-2">
              <Server className="h-4 w-4" />
              Импорт из 1С по OData
            </div>
            <div className="text-xs text-muted-foreground">
              {stats?.onec_connected
                ? "Автоматически загрузить номенклатуру через REST API 1С"
                : "Сначала настройте подключение к 1С в разделе Настройки"}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!stats?.onec_connected && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => (window.location.href = "/settings")}
              >
                <Link className="mr-1 h-3.5 w-3.5" />
                Настроить
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => onecMutation.mutate()}
              disabled={anyLoading || !stats?.onec_connected}
            >
              {onecMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <Database className="mr-1 h-4 w-4" />
                  Импорт
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Reindex */}
        <div className="flex items-center justify-between rounded-md border border-border p-3">
          <div>
            <div className="text-sm font-medium flex items-center gap-2">
              <RefreshCw className="h-4 w-4" />
              Переиндексация
            </div>
            <div className="text-xs text-muted-foreground">
              Обновить поисковый индекс и эмбеддинги после импорта
            </div>
            {reindexStatus && (
              <div className="mt-1 text-xs text-muted-foreground">
                {reindexStatus}
              </div>
            )}
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => reindexMutation.mutate()}
            disabled={reindexMutation.isPending}
          >
            {reindexMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              "Переиндексировать"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function MetricsSection() {
  const metricsQuery = useQuery({
    queryKey: ["quality-metrics"],
    queryFn: () => getQualityMetrics(),
  });

  const metrics = metricsQuery.data;

  function formatPct(val: number | null | undefined): string {
    if (val == null) return "—";
    return `${(val * 100).toFixed(1)}%`;
  }

  function formatMs(val: number | null | undefined): string {
    if (val == null) return "—";
    return `${Math.round(val)} мс`;
  }

  const cards = [
    {
      label: "Всего кейсов",
      value: metrics?.total_cases ?? "—",
    },
    {
      label: "Top-1 точность",
      value: formatPct(metrics?.top1_accuracy),
    },
    {
      label: "Top-3 recall",
      value: formatPct(metrics?.top3_recall),
    },
    {
      label: "Precision@1",
      value: formatPct(metrics?.precision_at_1),
    },
    {
      label: "Ложные автосопоставления",
      value: formatPct(metrics?.auto_match_false_positive_rate),
    },
    {
      label: "Принятие ревью",
      value: formatPct(metrics?.review_acceptance_rate),
    },
    {
      label: "Средняя задержка",
      value: formatMs(metrics?.avg_latency_ms),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4" />
          Метрики качества
        </CardTitle>
      </CardHeader>
      <CardContent>
        {metricsQuery.isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : metricsQuery.isError ? (
          <div className="py-4 text-center text-sm text-muted-foreground">
            Не удалось загрузить метрики
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {cards.map((card) => (
              <div
                key={card.label}
                className="rounded-md border border-border p-3"
              >
                <div className="text-xs text-muted-foreground">
                  {card.label}
                </div>
                <div className="mt-1 text-lg font-semibold">{card.value}</div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
