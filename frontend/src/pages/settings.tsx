import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  getSettings,
  updateSettings,
  getModels,
  testOneCConnection,
  type SettingsResponse,
  type SettingsUpdateInput,
} from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CheckCircle2, XCircle, AlertCircle, HelpCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PageLayout } from "@/components/layout/page-layout";
import { ModelCombobox } from "@/components/ui/model-combobox";
import { SkeletonCard } from "@/components/ui/skeleton";
import { QueryErrorBanner } from "@/components/ui/query-error-banner";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MetricsTab } from "@/components/features/metrics-tab";
import { UsersTab } from "@/components/features/users-tab";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [testResult, setTestResult] = useState<{
    status: string;
    detail?: string;
    httpStatus?: number;
  } | null>(null);

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });


  const form = useForm<SettingsResponse & { new_api_keys?: Record<string, string> }>({
    defaultValues: {
      llm_provider: "openai",
      embedding_provider: "openai",
      rerank_provider: "llm-fallback",
      providers_registry: [],
      new_api_keys: {},
      llm_model: "",
      llm_rerank_model: "",
      embedding_model: "",
      embedding_dimensions: 3072,
      auto_match_threshold: 0.9,
      review_threshold: 0.6,
      retrieval_top_n: 10,
      rerank_top_n: 5,
      onec: {
        base_url: "",
        username: "",
        password: "",
        catalog_endpoint: "/hs/catalog/v1/nomenclature",
        enabled: false,
      },
      agentic_resolution_enabled: false,
    },
  });

  const mutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: (updatedData) => {
      queryClient.setQueryData(["settings"], updatedData);
      form.reset(updatedData);
      toast.success("Настройки успешно сохранены");
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "";
      toast.error(`Ошибка при сохранении настроек: ${msg}`);
    },
  });

  useEffect(() => {
    if (settingsQuery.data) {
      form.reset({
        ...settingsQuery.data,
        new_api_keys: {},
      });
    }
  }, [settingsQuery.data, form]);

  // Unsaved changes warning
  const isDirty = form.formState.isDirty;
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue =
          "У вас есть несохраненные изменения. Вы уверены, что хотите уйти?";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  const testConnectionMutation = useMutation({
    mutationFn: testOneCConnection,
    onSuccess: (data) => {
      setTestResult({
        status: data.status,
        detail: data.detail,
        httpStatus: data.http_status,
      });
    },
    onError: (err: Error) => {
      setTestResult({
        status: "error",
        detail: err?.message || "Неизвестная ошибка",
      });
    },
  });

  function prepareUpdateData(data: SettingsResponse & { new_api_keys?: Record<string, string> }): SettingsUpdateInput {
    const { new_api_keys, providers_registry, ...rest } = data;
    const updateData: SettingsUpdateInput = { ...rest };
    if (providers_registry) {
      updateData.providers_registry = providers_registry.map(p => {
        const updatedKey = new_api_keys?.[p.id];
        if (updatedKey) {
          return { id: p.id, api_key: updatedKey, base_url: p.base_url };
        }
        return { id: p.id, base_url: p.base_url };
      });
    }
    return updateData;
  }

  function onSubmit(data: SettingsResponse & { new_api_keys?: Record<string, string> }) {
    mutation.mutate(prepareUpdateData(data));
    setTestResult(null);
  }

  function handleTestConnection() {
    form.handleSubmit(async (data) => {
      await mutation.mutateAsync(prepareUpdateData(data));
      testConnectionMutation.mutate();
    })();
  }

  // eslint-disable-next-line react-hooks/incompatible-library
  const llmProvider = form.watch("llm_provider");
  const embeddingProvider = form.watch("embedding_provider");
  const rerankProvider = form.watch("rerank_provider");

  const llmModelsQuery = useQuery({
    queryKey: ["models", llmProvider],
    queryFn: () => getModels(llmProvider),
    enabled: !!llmProvider,
  });

  const embeddingModelsQuery = useQuery({
    queryKey: ["models", embeddingProvider],
    queryFn: () => getModels(embeddingProvider),
    enabled: !!embeddingProvider,
  });

  const rerankModelsQuery = useQuery({
    queryKey: ["models", rerankProvider],
    queryFn: () => getModels(rerankProvider),
    enabled: !!rerankProvider && rerankProvider !== "llm-fallback",
  });

  if (settingsQuery.isLoading) {
    return (
      <div className="space-y-6 max-w-4xl p-6">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (settingsQuery.isError) {
    return (
      <div className="p-6 max-w-4xl">
        <QueryErrorBanner error={settingsQuery.error} onRetry={() => settingsQuery.refetch()} />
      </div>
    );
  }

  const llmModelsRaw = llmModelsQuery.data?.models || [];
  const llmModels = llmModelsRaw.filter(m => m.type !== "embedding" && m.type !== "rerank");

  const embeddingModelsRaw = embeddingModelsQuery.data?.models || [];
  const embeddingModels = embeddingModelsRaw.filter(m => m.type === "embedding");

  const rerankModelsRaw = rerankModelsQuery.data?.models || [];
  const rerankModels = rerankModelsRaw.filter(m => m.type === "rerank");

  const activeProviderIds = Array.from(new Set([llmProvider, embeddingProvider, rerankProvider])).filter(Boolean);
  const registry = form.watch("providers_registry") || [];

  const savedSettings = settingsQuery.data;
  const embeddingModelChanged = savedSettings && form.watch("embedding_model") !== savedSettings.embedding_model;
  const embeddingDimsChanged = savedSettings && form.watch("embedding_dimensions") !== savedSettings.embedding_dimensions;
  const needsReindex = embeddingModelChanged || embeddingDimsChanged;

  return (
    <PageLayout
      title="Системный раздел"
      description="Управление моделями, метриками и доступом."
      actions={
        isDirty && (
          <Badge
            variant="outline"
            className="bg-yellow-50 text-yellow-700 border-yellow-200 gap-1 h-7"
          >
            <AlertCircle className="w-3 h-3" /> Отличается от сохраненного
          </Badge>
        )
      }
    >
      <Tabs defaultValue="settings" className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="settings">API и Интеграции</TabsTrigger>
          <TabsTrigger value="metrics">Системные Метрики</TabsTrigger>
          <TabsTrigger value="users">Доступ и Пользователи</TabsTrigger>
        </TabsList>

        <TabsContent value="settings" className="mt-0">
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="space-y-6 max-w-4xl"
          >
        <Card>
          <CardHeader>
            <CardTitle>Провайдеры ИИ (LLM & Embeddings)</CardTitle>
            <CardDescription>
              Настройка провайдеров и моделей для обработки номенклатуры.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Провайдер LLM (Ранжирование)</Label>
                <Select
                  value={form.watch("llm_provider")}
                  onValueChange={(val) =>
                    form.setValue("llm_provider", val || "", {
                      shouldDirty: true,
                    })
                  }
                >
                  <SelectTrigger disabled={mutation.isPending}>
                    <SelectValue placeholder="Выберите провайдера" />
                  </SelectTrigger>
                  <SelectContent>
                    {registry.filter(p => p.supports_chat).map(p => (
                      <SelectItem key={p.id} value={p.id}>{p.name}{p.is_beta ? " (beta)" : ""}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  Ранжирующая LLM модель
                  <Tooltip>
                    <TooltipTrigger render={<button type="button" className="text-muted-foreground" />}>
                      <HelpCircle className="h-3.5 w-3.5" />
                    </TooltipTrigger>
                    <TooltipContent>Модель для ранжирования и принятия финальных решений о совпадениях. Рекомендуется: gpt-4o-mini или аналог.</TooltipContent>
                  </Tooltip>
                </Label>
                <div className="flex gap-2 relative">
                  <ModelCombobox
                    value={form.watch("llm_model")}
                    onChange={(val) =>
                      form.setValue("llm_model", val, { shouldDirty: true })
                    }
                    options={llmModels}
                    isLoading={llmModelsQuery.isLoading}
                    placeholder="Например: gpt-4o-mini"
                  />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-border">
              <div className="space-y-2">
                <Label>Провайдер Embeddings</Label>
                <Select
                  value={form.watch("embedding_provider")}
                  onValueChange={(val) =>
                    form.setValue("embedding_provider", val || "", {
                      shouldDirty: true,
                    })
                  }
                >
                  <SelectTrigger disabled={mutation.isPending}>
                    <SelectValue placeholder="Выберите провайдера" />
                  </SelectTrigger>
                  <SelectContent>
                    {registry.filter(p => p.supports_embeddings).map(p => (
                      <SelectItem key={p.id} value={p.id}>{p.name}{p.is_beta ? " (beta)" : ""}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Модель Embeddings</Label>
                <ModelCombobox
                  value={form.watch("embedding_model")}
                  onChange={(val) =>
                    form.setValue("embedding_model", val, { shouldDirty: true })
                  }
                  options={embeddingModels}
                  isLoading={embeddingModelsQuery.isLoading}
                  placeholder="Например: text-embedding-3-large"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-border">
              <div className="space-y-2">
                <Label>Провайдер Reranking</Label>
                <Select
                  value={form.watch("rerank_provider")}
                  onValueChange={(val) =>
                    form.setValue("rerank_provider", val || "", {
                      shouldDirty: true,
                    })
                  }
                >
                  <SelectTrigger disabled={mutation.isPending}>
                    <SelectValue placeholder="Выберите провайдера" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="llm-fallback">LLM Fallback</SelectItem>
                    {registry.filter(p => p.supports_rerank).map(p => (
                      <SelectItem key={p.id} value={p.id}>{p.name}{p.is_beta ? " (beta)" : ""}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Модель Reranking</Label>
                <ModelCombobox
                  value={form.watch("llm_rerank_model")}
                  onChange={(val) =>
                    form.setValue("llm_rerank_model", val, { shouldDirty: true })
                  }
                  options={rerankModels}
                  isLoading={rerankModelsQuery.isLoading}
                  placeholder="Например: BAAI/bge-reranker-v2-m3"
                />
              </div>
            </div>

            {registry.filter(p => activeProviderIds.includes(p.id) && p.id !== "local").map(p => (
              <div key={p.id} className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-border">
                <div className="space-y-2 col-span-2 sm:col-span-1">
                  <Label>{p.name} Base URL</Label>
                  <Input
                    placeholder="Base URL..."
                    {...form.register(`providers_registry.${registry.findIndex(x => x.id === p.id)}.base_url` as `providers_registry.${number}.base_url`)}
                  />
                </div>
                <div className="space-y-2 col-span-2 sm:col-span-1">
                  <Label>{p.name} API Key</Label>
                  <Input
                    type="password"
                    placeholder={p.api_key_set ? "••••••••••••••••" : "Введите API ключ"}
                    {...form.register(`new_api_keys.${p.id}` as `new_api_keys.${string}`)}
                  />
                  {!p.api_key_set && (
                    <p className="text-[10px] text-yellow-600">API ключ не настроен. Сопоставление не будет работать без ключа.</p>
                  )}
                </div>
              </div>
            ))}
            
            {/* Provider connection status + fallback warnings */}
            <div className="pt-4 border-t border-border space-y-3">
              <div className="text-xs font-semibold text-muted-foreground">Статус подключений и Fallback-режимы:</div>
              {[
                { role: "LLM (Ранжирование)", providerId: llmProvider, fallback: "Без LLM ранжирование невозможно. Система будет использовать только лексический и векторный поиск." },
                { role: "Embeddings", providerId: embeddingProvider, fallback: "Без эмбеддингов семантический поиск отключён. Система перейдёт на чисто лексический поиск (BM25). Качество снизится." },
                { role: "Reranking", providerId: rerankProvider, fallback: rerankProvider === "llm-fallback" ? "Используется LLM для переранжирования (медленнее, но не требует отдельного ключа)." : "Без реранкера система сортирует только по базовому скору. Качество топ-результатов снизится." },
              ].map(({ role, providerId, fallback }) => {
                const prov = registry.find(p => p.id === providerId);
                const isLocal = providerId === "local";
                const isLlmFallback = providerId === "llm-fallback";
                const hasKey = isLocal || isLlmFallback || (prov?.api_key_set ?? false);
                const provName = isLlmFallback ? "LLM Fallback" : prov?.name || providerId;
                return (
                  <div key={role} className={`rounded-lg border p-3 text-xs ${
                    hasKey ? "border-green-200 bg-green-50/50" : "border-yellow-300 bg-yellow-50"
                  }`}>
                    <div className="flex items-center gap-2 font-medium">
                      {hasKey ? <CheckCircle2 className="h-3.5 w-3.5 text-green-600 shrink-0" /> : <AlertCircle className="h-3.5 w-3.5 text-yellow-600 shrink-0" />}
                      <span>{role}: {provName}</span>
                      {hasKey
                        ? <span className="text-green-700 ml-auto">Подключён</span>
                        : <span className="text-yellow-700 ml-auto">Ключ не настроен</span>
                      }
                    </div>
                    {!hasKey && (
                      <div className="mt-1.5 text-yellow-700 pl-5.5">{fallback}</div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="grid grid-cols-1 gap-4 pt-4 border-t border-border">
              <div className="flex items-center justify-between rounded-lg border p-3">
                <div className="space-y-0.5">
                  <Label
                    className="text-base cursor-pointer"
                    htmlFor="agent-enable"
                  >
                    Включить Agentic Resolution (Web Search / Catalog Fallback)
                  </Label>
                  <div className="text-sm text-muted-foreground w-11/12">
                    При низком скоринге совпадений система попытается использовать интернет-поиск и глубокий поиск по базе через LLM. 
                    <b>Внимание: может увеличить время обработки 1-й строки на 3-6 секунд.</b>
                  </div>
                </div>
                <Switch
                  id="agent-enable"
                  checked={form.watch("agentic_resolution_enabled")}
                  onCheckedChange={(checked: boolean) =>
                    form.setValue("agentic_resolution_enabled", checked, { shouldDirty: true })
                  }
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-border">
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  Размерности (Dimensions) Embeddings
                  <Tooltip>
                    <TooltipTrigger render={<button type="button" className="text-muted-foreground" />}>
                      <HelpCircle className="h-3.5 w-3.5" />
                    </TooltipTrigger>
                    <TooltipContent>Количество размерностей векторного представления. Зависит от выбранной модели.</TooltipContent>
                  </Tooltip>
                </Label>
                <Input
                  type="number"
                  {...form.register("embedding_dimensions", {
                    valueAsNumber: true,
                  })}
                  placeholder="3072"
                />
                <p className="text-[10px] text-muted-foreground">
                  Должно совпадать с параметрами выбранной модели.
                </p>
              </div>
            </div>

            {needsReindex && (
              <div className="flex items-start gap-2 rounded-lg border border-yellow-300 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0 text-yellow-600" />
                <div>
                  <div className="font-medium">Требуется переиндексация каталога</div>
                  <div className="text-xs text-yellow-700 mt-0.5">
                    Вы изменили {embeddingModelChanged ? "модель эмбеддингов" : ""}{embeddingModelChanged && embeddingDimsChanged ? " и " : ""}{embeddingDimsChanged ? "размерность векторов" : ""}.
                    После сохранения необходимо выполнить полную переиндексацию каталога на странице «Каталог» → «Обновить индекс поиска».
                    До переиндексации результаты поиска будут некорректными.
                  </div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-border">
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  Количество кандидатов для Rerank (top_n)
                  <Tooltip>
                    <TooltipTrigger render={<button type="button" className="text-muted-foreground" />}>
                      <HelpCircle className="h-3.5 w-3.5" />
                    </TooltipTrigger>
                    <TooltipContent>Сколько лучших результатов векторного поиска передать в LLM для переранжирования</TooltipContent>
                  </Tooltip>
                </Label>
                <Input
                  type="number"
                  {...form.register("retrieval_top_n", { valueAsNumber: true })}
                />
                <p className="text-[10px] text-muted-foreground">
                  Кол-во лучших по вектору, передаваемых в LLM-rerank.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* GAP-8.3: Threshold configuration with visual explanation */}
        <Card>
          <CardHeader>
            <CardTitle>Пороги принятия решений</CardTitle>
            <CardDescription>
              Настройка порогов автоматического сопоставления и ручной проверки.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-4">
              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  Порог автоматического сопоставления
                  <Tooltip>
                    <TooltipTrigger render={<button type="button" className="text-muted-foreground" />}>
                      <HelpCircle className="h-3.5 w-3.5" />
                    </TooltipTrigger>
                    <TooltipContent>Позиции с оценкой выше этого порога принимаются автоматически без ручной проверки</TooltipContent>
                  </Tooltip>
                </Label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={form.watch("auto_match_threshold")}
                    onChange={(e) => form.setValue("auto_match_threshold", parseFloat(e.target.value), { shouldDirty: true })}
                    className="flex-1 h-2 accent-green-600"
                  />
                  <span className="text-sm font-mono w-12 text-right font-medium text-green-700">
                    {(form.watch("auto_match_threshold") * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              <div className="space-y-2">
                <Label className="flex items-center gap-1">
                  Порог ручной проверки
                  <Tooltip>
                    <TooltipTrigger render={<button type="button" className="text-muted-foreground" />}>
                      <HelpCircle className="h-3.5 w-3.5" />
                    </TooltipTrigger>
                    <TooltipContent>Позиции с оценкой между этим порогом и порогом авто-сопоставления отправляются на ручную проверку. Ниже — «не найдено».</TooltipContent>
                  </Tooltip>
                </Label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={form.watch("review_threshold")}
                    onChange={(e) => form.setValue("review_threshold", parseFloat(e.target.value), { shouldDirty: true })}
                    className="flex-1 h-2 accent-yellow-600"
                  />
                  <span className="text-sm font-mono w-12 text-right font-medium text-yellow-700">
                    {(form.watch("review_threshold") * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Visual threshold bar */}
              <div className="rounded-lg border p-3 bg-muted/30 space-y-2">
                <div className="text-xs font-medium text-muted-foreground">Визуализация зон решений:</div>
                <div className="flex h-6 rounded-md overflow-hidden text-[10px] font-medium">
                  <div
                    className="bg-red-200 text-red-800 flex items-center justify-center transition-all"
                    style={{ width: `${form.watch("review_threshold") * 100}%` }}
                  >
                    {form.watch("review_threshold") >= 0.15 && "Не найдено"}
                  </div>
                  <div
                    className="bg-yellow-200 text-yellow-800 flex items-center justify-center transition-all"
                    style={{ width: `${(form.watch("auto_match_threshold") - form.watch("review_threshold")) * 100}%` }}
                  >
                    {(form.watch("auto_match_threshold") - form.watch("review_threshold")) >= 0.15 && "На проверку"}
                  </div>
                  <div
                    className="bg-green-200 text-green-800 flex items-center justify-center transition-all"
                    style={{ width: `${(1 - form.watch("auto_match_threshold")) * 100}%` }}
                  >
                    {(1 - form.watch("auto_match_threshold")) >= 0.1 && "Авто"}
                  </div>
                </div>
                <div className="flex justify-between text-[10px] text-muted-foreground">
                  <span>0%</span>
                  <span>{(form.watch("review_threshold") * 100).toFixed(0)}%</span>
                  <span>{(form.watch("auto_match_threshold") * 100).toFixed(0)}%</span>
                  <span>100%</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Подключение к 1С (ERP / УТ)</CardTitle>
            <CardDescription>
              Интеграция с HTTP-сервисом 1С для загрузки эталонного каталога
              базы.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div className="space-y-0.5">
                <Label
                  className="text-base cursor-pointer"
                  htmlFor="onec-enable"
                >
                  Включить интеграцию с 1С
                </Label>
                <div className="text-sm text-muted-foreground">
                  Позволит запрашивать номенклатуру напрямую через HTTP-сервис.
                </div>
              </div>
              <Switch
                id="onec-enable"
                checked={form.watch("onec.enabled")}
                onCheckedChange={(checked: boolean) =>
                  form.setValue("onec.enabled", checked, { shouldDirty: true })
                }
              />
            </div>

            {form.watch("onec.enabled") && (
              <div className="space-y-4 pt-2">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Базовый URL (вкл. базу)</Label>
                    <Input
                      placeholder="http://1c.domain.com/base"
                      {...form.register("onec.base_url")}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Endpoint (путь каталога)</Label>
                    <Input {...form.register("onec.catalog_endpoint")} />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Имя пользователя (Логин)</Label>
                    <Input {...form.register("onec.username")} />
                  </div>
                  <div className="space-y-2">
                    <Label>
                      Пароль (Оставьте пустым для сохранения старого)
                    </Label>
                    <Input
                      type="password"
                      {...form.register("onec.password")}
                      placeholder="••••••••"
                    />
                  </div>
                </div>

                <div className="flex items-center gap-4 pt-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={handleTestConnection}
                    disabled={
                      testConnectionMutation.isPending || mutation.isPending
                    }
                  >
                    {testConnectionMutation.isPending
                      ? "Тестируем..."
                      : "Проверить соединение"}
                  </Button>

                  {testResult && (
                    <div className="flex items-center text-sm flex-1">
                      {testResult.status === "ok" ? (
                        <div className="text-green-600 flex items-center gap-1 bg-green-50 px-3 py-1.5 rounded-md border border-green-200">
                          <CheckCircle2 className="h-4 w-4" /> Успешное
                          подключение к 1С ({testResult.httpStatus})
                        </div>
                      ) : (
                        <div className="text-red-600 flex items-center gap-1 bg-red-50 px-3 py-1.5 rounded-md border border-red-200 w-full overflow-hidden">
                          <XCircle className="h-4 w-4 shrink-0" />
                          <span className="truncate" title={testResult.detail}>
                            Ошибка: {testResult.detail}{" "}
                            {testResult.httpStatus
                              ? `(${testResult.httpStatus})`
                              : ""}
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="sticky bottom-0 -mx-4 md:-mx-6 px-4 md:px-6 py-4 bg-background/80 backdrop-blur-md border-t flex justify-end gap-2 shadow-sm z-10 transition-all">
          {isDirty && (
            <Button
              type="button"
              variant="ghost"
              onClick={() => form.reset()}
              disabled={mutation.isPending}
            >
              Отменить изменения
            </Button>
          )}
          <Button
            type="submit"
            disabled={!isDirty || mutation.isPending}
            className="min-w-[120px]"
          >
            {mutation.isPending ? "Сохранение..." : "Сохранить настройки"}
          </Button>
        </div>
      </form>
        </TabsContent>
        <TabsContent value="metrics" className="mt-0">
          <MetricsTab />
        </TabsContent>
        <TabsContent value="users" className="mt-0">
          <UsersTab />
        </TabsContent>
      </Tabs>
    </PageLayout>
  );
}
