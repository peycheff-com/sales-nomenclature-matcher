import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { getSettings, updateSettings, getFreeModels, testOneCConnection, type SettingsResponse } from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { RefreshCw, CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PageLayout } from "@/components/layout/page-layout";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [testResult, setTestResult] = useState<{status: string, detail?: string, httpStatus?: number} | null>(null);

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });

  const modelsQuery = useQuery({
    queryKey: ["free-models"],
    queryFn: getFreeModels,
  });

  const form = useForm<SettingsResponse>({
    defaultValues: {
      llm_provider: "openrouter",
      embedding_provider: "openai",
      llm_model: "",
      llm_rerank_model: "",
      embedding_model: "",
      embedding_dimensions: 3072,
      openrouter_api_key_set: false,
      openai_api_key_set: false,
      google_api_key_set: false,
      cohere_api_key_set: false,
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
      }
    }
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
    }
  });

  useEffect(() => {
    if (settingsQuery.data) {
      form.reset(settingsQuery.data);
    }
  }, [settingsQuery.data, form]);

  // Unsaved changes warning
  const isDirty = form.formState.isDirty;
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = "У вас есть несохраненные изменения. Вы уверены, что хотите уйти?";
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  const testConnectionMutation = useMutation({
    mutationFn: testOneCConnection,
    onSuccess: (data) => {
      setTestResult({ status: data.status, detail: data.detail, httpStatus: data.http_status });
    },
    onError: (err: any) => {
      setTestResult({ status: "error", detail: err?.message || "Неизвестная ошибка" });
    }
  });

  function onSubmit(data: SettingsResponse) {
    const {
      openrouter_api_key_set, openai_api_key_set, google_api_key_set, cohere_api_key_set, ...updateData
    } = data;
    mutation.mutate(updateData);
    setTestResult(null); 
  }

  function handleTestConnection() {
    form.handleSubmit(async (data) => {
        const { openrouter_api_key_set, openai_api_key_set, google_api_key_set, cohere_api_key_set, ...updateData } = data;
        await mutation.mutateAsync(updateData);
        testConnectionMutation.mutate();
    })();
  }

  if (settingsQuery.isLoading) {
    return <div className="text-sm text-muted-foreground p-6 animate-pulse">Загрузка настроек...</div>;
  }

  return (
    <PageLayout
      title="Настройки системы"
      description="Управление моделями, порогами и подключениями."
      actions={
        isDirty && (
          <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200 gap-1 h-7">
            <AlertCircle className="w-3 h-3"/> Отличается от сохраненного
          </Badge>
        )
      }
    >

      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 max-w-4xl pb-24">
        <Card>
          <CardHeader>
            <CardTitle>Нейросетевые модели (LLM & Embeddings)</CardTitle>
            <CardDescription>
              Настройка провайдеров, ключей доступа и параметров моделей.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Ранжирующая модель (Оценка качества совпадений)</Label>
                <div className="flex gap-2">
                  <Select
                    value={form.watch("llm_model")}
                    onValueChange={(val) => form.setValue("llm_model", val || "", { shouldDirty: true })}
                  >
                    <SelectTrigger disabled={modelsQuery.isLoading} className="flex-1">
                      <SelectValue placeholder="Выберите LLM модель" />
                    </SelectTrigger>
                    <SelectContent>
                      {modelsQuery.data?.models.map(m => (
                        <SelectItem key={m.id} value={m.id}>
                          {m.name} ({Math.round(m.context_length/1000)}k ctx)
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {modelsQuery.isLoading && <div className="text-xs text-muted-foreground">Загрузка моделей OpenRouter...</div>}
              </div>
              <div className="space-y-2">
                <Label>API Ключ OpenRouter</Label>
                <Input
                  type="password"
                  placeholder={settingsQuery.data?.openrouter_api_key_set ? "••••••••••••••••" : "Введите новый ключ"}
                  {...form.register("openrouter_api_key" as any)}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border">
              <div className="space-y-2">
                <Label>Провайдер Embeddings</Label>
                <Select
                  value={form.watch("embedding_provider")}
                  onValueChange={(val) => form.setValue("embedding_provider", val || "", { shouldDirty: true })}
                >
                  <SelectTrigger disabled={mutation.isPending}>
                    <SelectValue placeholder="Выберите провайдера" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="openai">OpenAI</SelectItem>
                    <SelectItem value="openrouter">OpenRouter</SelectItem>
                    <SelectItem value="google">Google (Gemini)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Модель для Embeddings</Label>
                <Input {...form.register("embedding_model")} placeholder="Например: text-embedding-3-large" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              {form.watch("embedding_provider") === "openai" && (
                <div className="space-y-2 col-span-2">
                  <Label>API Ключ OpenAI</Label>
                  <Input
                    type="password"
                    placeholder={settingsQuery.data?.openai_api_key_set ? "••••••••••••••••" : "Введите новый ключ"}
                    {...form.register("openai_api_key" as any)}
                  />
                </div>
              )}
              {form.watch("embedding_provider") === "openrouter" && (
                <div className="space-y-2 col-span-2">
                  <Label>API Ключ OpenRouter (Embeddings)</Label>
                  <Input
                    type="password"
                    placeholder={settingsQuery.data?.openrouter_api_key_set ? "••••••••••••••••" : "Введите новый ключ (общий с LLM)"}
                    {...form.register("openrouter_api_key" as any)}
                  />
                </div>
              )}
              {form.watch("embedding_provider") === "google" && (
                <div className="space-y-2 col-span-2">
                  <Label>API Ключ Google Gemini</Label>
                  <Input
                    type="password"
                    placeholder={settingsQuery.data?.google_api_key_set ? "••••••••••••••••" : "Введите новый ключ"}
                    {...form.register("google_api_key" as any)}
                  />
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Размерности Embeddings</Label>
                <Input 
                  type="number" 
                  {...form.register("embedding_dimensions", { valueAsNumber: true })} 
                  placeholder="3072"
                />
                <p className="text-[10px] text-muted-foreground">Должно совпадать с параметрами выбранной модели.</p>
              </div>
              <div className="space-y-2">
                <Label>API Ключ Cohere (Для Rerank_v3 V2)</Label>
                <Input
                  type="password"
                  placeholder={settingsQuery.data?.cohere_api_key_set ? "••••••••••••••••" : "Укажите для активации Cohere Rerank"}
                  {...form.register("cohere_api_key" as any)}
                />
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border">
              <div className="space-y-2">
                <Label>Количество кандидатов для Rerank (top_n)</Label>
                <Input type="number" {...form.register("retrieval_top_n", { valueAsNumber: true })} />
                <p className="text-[10px] text-muted-foreground">Кол-во лучших по вектору, передаваемых в LLM-rerank.</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Подключение к 1С (ERP / УТ)</CardTitle>
            <CardDescription>
              Интеграция с HTTP-сервисом 1С для загрузки эталонного каталога базы.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div className="space-y-0.5">
                <Label className="text-base cursor-pointer" htmlFor="onec-enable">Включить интеграцию с 1С</Label>
                <div className="text-sm text-muted-foreground">
                  Позволит запрашивать номенклатуру напрямую через HTTP-сервис.
                </div>
              </div>
              <Switch
                id="onec-enable"
                checked={form.watch("onec.enabled")}
                onCheckedChange={(checked: boolean) => form.setValue("onec.enabled", checked, { shouldDirty: true })}
              />
            </div>

            {form.watch("onec.enabled") && (
              <div className="space-y-4 pt-2">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Базовый URL (вкл. базу)</Label>
                    <Input placeholder="http://1c.domain.com/base" {...form.register("onec.base_url")} />
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
                    <Label>Пароль (Оставьте пустым для сохранения старого)</Label>
                    <Input type="password" {...form.register("onec.password")} placeholder="••••••••" />
                  </div>
                </div>

                <div className="flex items-center gap-4 pt-2">
                  <Button 
                    type="button" 
                    variant="outline" 
                    onClick={handleTestConnection}
                    disabled={testConnectionMutation.isPending || mutation.isPending}
                  >
                    {testConnectionMutation.isPending ? "Тестируем..." : "Проверить соединение"}
                  </Button>
                  
                  {testResult && (
                    <div className="flex items-center text-sm flex-1">
                      {testResult.status === "ok" ? (
                        <div className="text-green-600 flex items-center gap-1 bg-green-50 px-3 py-1.5 rounded-md border border-green-200">
                          <CheckCircle2 className="h-4 w-4" /> Успешное подключение к 1С ({testResult.httpStatus})
                        </div>
                      ) : (
                        <div className="text-red-600 flex items-center gap-1 bg-red-50 px-3 py-1.5 rounded-md border border-red-200 w-full overflow-hidden">
                          <XCircle className="h-4 w-4 shrink-0" />
                          <span className="truncate" title={testResult.detail}>
                            Ошибка: {testResult.detail} {testResult.httpStatus ? `(${testResult.httpStatus})` : ''}
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


