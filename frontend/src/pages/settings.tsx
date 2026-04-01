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
  CardFooter,
} from "@/components/ui/card";
import { RefreshCw, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PageLayout } from "@/components/layout/page-layout";
import { ModelCombobox } from "@/components/ui/model-combobox";

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

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: getModels,
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
    onError: () => {
      toast.error("Ошибка при сохранении настроек");
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
    onError: (err: any) => {
      setTestResult({
        status: "error",
        detail: err?.message || "Неизвестная ошибка",
      });
    },
  });

  function prepareUpdateData(data: SettingsResponse & { new_api_keys?: Record<string, string> }) {
    const { new_api_keys, ...rest } = data;
    const updateData: any = { ...rest };
    if (rest.providers_registry) {
      updateData.providers_registry = rest.providers_registry.map(p => {
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

  if (settingsQuery.isLoading) {
    return (
      <div className="text-sm text-muted-foreground p-6 animate-pulse">
        Загрузка настроек...
      </div>
    );
  }

  const llmProvider = form.watch("llm_provider");
  const embeddingProvider = form.watch("embedding_provider");
  const rerankProvider = form.watch("rerank_provider");
  
  const activeProviderIds = Array.from(new Set([llmProvider, embeddingProvider, rerankProvider])).filter(Boolean);
  const registry = form.watch("providers_registry") || [];

  return (
    <PageLayout
      title="Настройки системы"
      description="Управление моделями, порогами и подключениями."
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
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-6 max-w-4xl pb-24"
      >
        <Card>
          <CardHeader>
            <CardTitle>Провайдеры ИИ (LLM & Embeddings)</CardTitle>
            <CardDescription>
              Настройка провайдеров и моделей для обработки номенклатуры.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
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
                    {registry.map(p => (
                      <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Ранжирующая LLM модель</Label>
                <div className="flex gap-2 relative">
                  <ModelCombobox
                    value={form.watch("llm_model")}
                    onChange={(val) =>
                      form.setValue("llm_model", val, { shouldDirty: true })
                    }
                    options={modelsQuery.data?.models || []}
                    isLoading={modelsQuery.isLoading}
                    placeholder="Например: gpt-4o-mini"
                  />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border">
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
                    {registry.map(p => (
                      <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
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
                  options={modelsQuery.data?.models || []}
                  isLoading={modelsQuery.isLoading}
                  placeholder="Например: text-embedding-3-large"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border">
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
                    {registry.map(p => (
                      <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
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
                  options={modelsQuery.data?.models || []}
                  isLoading={modelsQuery.isLoading}
                  placeholder="Например: BAAI/bge-reranker-v2-m3"
                />
              </div>
            </div>

            {registry.filter(p => activeProviderIds.includes(p.id) && p.id !== "local").map(p => (
              <div key={p.id} className="grid grid-cols-2 gap-4 pt-4 border-t border-border">
                <div className="space-y-2 col-span-2 sm:col-span-1">
                  <Label>{p.name} Base URL</Label>
                  <Input 
                    placeholder="Base URL..." 
                    {...form.register(`providers_registry.${registry.findIndex(x => x.id === p.id)}.base_url` as any)} 
                  />
                </div>
                <div className="space-y-2 col-span-2 sm:col-span-1">
                  <Label>{p.name} API Key</Label>
                  <Input
                    type="password"
                    placeholder={p.api_key_set ? "••••••••••••••••" : "Введите API ключ"}
                    {...form.register(`new_api_keys.${p.id}` as any)}
                  />
                </div>
              </div>
            ))}
            
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

            <div className="grid grid-cols-2 gap-4 pt-2 border-t border-border">
              <div className="space-y-2">
                <Label>Размерности (Dimensions) Embeddings</Label>
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

            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border">
              <div className="space-y-2">
                <Label>Количество кандидатов для Rerank (top_n)</Label>
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
                <div className="grid grid-cols-2 gap-4">
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

                <div className="grid grid-cols-2 gap-4">
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

        <div className="fixed bottom-0 left-64 right-0 p-4 bg-background/80 backdrop-blur-md border-t flex justify-end gap-2 shadow-sm z-10 transition-all">
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
    </PageLayout>
  );
}
