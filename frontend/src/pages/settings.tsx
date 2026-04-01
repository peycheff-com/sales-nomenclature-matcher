import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useEffect, useState } from "react";
import { getSettings, updateSettings, getFreeModels, testOneCConnection, type SettingsResponse } from "@/api/settings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { RefreshCw, CheckCircle2, XCircle } from "lucide-react";

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

  const mutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
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

  // Keep form in sync when settings are loaded
  useEffect(() => {
    if (settingsQuery.data) {
      form.reset(settingsQuery.data);
    }
  }, [settingsQuery.data, form]);

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
    // Collect the updated values safely, excluding the readonly api_key_set bools and mapping password if empty
    const {
      openrouter_api_key_set, openai_api_key_set, cohere_api_key_set, ...updateData
    } = data;
    mutation.mutate(updateData);
    setTestResult(null); // Clear previous test result
  }

  function handleTestConnection() {
    // Before testing, making sure current drafted settings are saved
    form.handleSubmit(async (data) => {
        const { openrouter_api_key_set, openai_api_key_set, cohere_api_key_set, ...updateData } = data;
        await mutation.mutateAsync(updateData);
        testConnectionMutation.mutate();
    })();
  }

  if (settingsQuery.isLoading) {
    return <div className="text-sm text-muted-foreground p-6">Загрузка настроек...</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Настройки системы</h1>
        <p className="text-muted-foreground">Управление моделями, порогами и подключениями.</p>
      </div>

      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 max-w-4xl">
        <Card>
          <CardHeader>
            <CardTitle>Нейросетевые модели (LLM & Embeddings)</CardTitle>
            <CardDescription>
              Настройка провайдеров, ключей доступа и выбора моделей для ранкирования.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Ранжирующая модель (OpenRouter/OpenAI)</Label>
                <Select
                  value={form.watch("llm_model")}
                  onValueChange={(val) => form.setValue("llm_model", val || "")}
                >
                  <SelectTrigger disabled={modelsQuery.isLoading}>
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
                {modelsQuery.isLoading && <div className="text-xs text-muted-foreground">Загрузка свободных моделей OpenRouter...</div>}
              </div>
              <div className="space-y-2">
                <Label>API Ключ OpenRouter (задайте для изменения)</Label>
                <Input
                  type="password"
                  placeholder={settingsQuery.data?.openrouter_api_key_set ? "••••••••••••••••" : "Введите ключ"}
                  {...form.register("openrouter_api_key" as any)}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Модель для Embeddings (OpenAI)</Label>
                <Input {...form.register("embedding_model")} />
              </div>
              <div className="space-y-2">
                <Label>API Ключ OpenAI (задайте для изменения)</Label>
                <Input
                  type="password"
                  placeholder={settingsQuery.data?.openai_api_key_set ? "••••••••••••••••" : "Введите ключ"}
                  {...form.register("openai_api_key" as any)}
                />
              </div>
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Количество кандидатов для Rerank (top_n)</Label>
                <Input type="number" {...form.register("retrieval_top_n", { valueAsNumber: true })} />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Подключение к 1С (ERP / УТ)</CardTitle>
            <CardDescription>
              Интеграция с HTTP-сервисом 1С для импорта каталога из OData или кастомного API.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border p-3">
              <div className="space-y-0.5">
                <Label className="text-base">Включить интеграцию с 1С</Label>
                <div className="text-sm text-muted-foreground">
                  Позволит запрашивать номенклатуру напрямую через HTTP-сервис.
                </div>
              </div>
              <Switch
                checked={form.watch("onec.enabled")}
                onCheckedChange={(checked: boolean) => form.setValue("onec.enabled", checked)}
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
                    <Label>Пользователь</Label>
                    <Input {...form.register("onec.username")} />
                  </div>
                  <div className="space-y-2">
                    <Label>Пароль</Label>
                    <Input type="password" {...form.register("onec.password")} placeholder="••••••••" />
                  </div>
                </div>
              </div>
            )}
          </CardContent>
          {form.watch("onec.enabled") && (
            <CardFooter className="flex flex-col items-start gap-4">
              <div className="flex items-center gap-2">
                 <Button type="button" variant="outline" onClick={handleTestConnection} disabled={testConnectionMutation.isPending || mutation.isPending}>
                  {testConnectionMutation.isPending ? <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Сохранить и проверить соединение
                </Button>
              </div>
              {testResult && (
                <div className={`flex items-center gap-2 text-sm ${testResult.status === 'ok' ? 'text-green-600' : 'text-red-600'}`}>
                  {testResult.status === 'ok' ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
                  {testResult.status === 'ok' ? 'Соединение успешно установлено!' : `Ошибка: ${testResult.detail || 'Не удалось подключиться'}`}
                </div>
              )}
            </CardFooter>
          )}
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Пороги достоверности (Confidence)</CardTitle>
            <CardDescription>
              Определяют, когда результат считается автоматическим (без ручной проверки).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Порог автоматического подтверждения</Label>
                <div className="flex items-center gap-2">
                  <Input type="number" step="0.05" min="0" max="1" {...form.register("auto_match_threshold", { valueAsNumber: true })} />
                  <span className="text-sm text-muted-foreground w-full">(&gt; {form.watch("auto_match_threshold")})</span>
                </div>
              </div>
              <div className="space-y-2">
                <Label>Порог отправки на ручную проверку</Label>
                <div className="flex items-center gap-2">
                  <Input type="number" step="0.05" min="0" max="1" {...form.register("review_threshold", { valueAsNumber: true })} />
                  <span className="text-sm text-muted-foreground w-full">(&gt; {form.watch("review_threshold")})</span>
                </div>
              </div>
            </div>
            <div className="text-xs text-muted-foreground space-y-1">
              <p>• Уверенность &gt; {form.watch("auto_match_threshold")} → <b>Автосопоставление</b></p>
              <p>• Уверенность от {form.watch("review_threshold")} до {form.watch("auto_match_threshold")} → <b>Нужна проверка</b></p>
              <p>• Уверенность &lt; {form.watch("review_threshold")} → <b>Не найдено</b></p>
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end gap-4 pb-12">
          <Button type="button" variant="outline" onClick={() => form.reset(settingsQuery.data)} disabled={mutation.isPending}>
            Отменить изменения
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Сохранение..." : "Сохранить настройки"}
          </Button>
        </div>
      </form>
    </div>
  );
}
