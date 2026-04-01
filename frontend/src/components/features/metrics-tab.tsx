import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  BarChart3,
  Settings2,
  Activity,
  Users,
  Database,
  RefreshCw,
  Server,
  Search,
  HelpCircle,
  ArrowRight,
  Shield,
  UserCog,
  Eye,
  Coins,
} from "lucide-react";
import { toast } from "sonner";
import { getQualityMetrics, getTokenUsage } from "@/api/metrics";
import { listSuppliers } from "@/api/suppliers";
import { listUsers } from "@/api/users";
import { reindexCatalog } from "@/api/catalog";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from "@/components/ui/table";
import { QueryErrorBanner } from "@/components/ui/query-error-banner";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";

export function MetricsTab() {
  const [supplierFilter, setSupplierFilter] = useState<string>("__all__");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [tokenDays, setTokenDays] = useState<number>(30);

  const suppliersQuery = useQuery({
    queryKey: ["suppliers"],
    queryFn: listSuppliers,
  });

  const metricsQuery = useQuery({
    queryKey: ["quality-metrics", supplierFilter, categoryFilter],
    queryFn: () => getQualityMetrics({
      ...(supplierFilter !== "__all__" && { supplier_id: supplierFilter }),
      ...(categoryFilter && { category_id: categoryFilter }),
    }),
  });

  const reindexMutation = useMutation({
    mutationFn: reindexCatalog,
    onSuccess: () => toast.success("Переиндексация запущена"),
    onError: () => toast.error("Ошибка при запуске переиндексации"),
  });

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: () => fetch("/api/v1/health").then((r) => r.json()),
    refetchInterval: 30000,
  });

  const tokenUsageQuery = useQuery({
    queryKey: ["token-usage", tokenDays],
    queryFn: () => getTokenUsage(tokenDays),
  });

  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });

  const metrics = metricsQuery.data;
  const suppliers = suppliersQuery.data?.items ?? [];
  const allUsers = usersQuery.data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-1 mb-4">
        <h2 className="text-lg font-medium">Метрики и Администрирование</h2>
        <p className="text-sm text-muted-foreground">Управление системой, метрики качества и интеграции.</p>
      </div>

      <Tabs defaultValue="metrics" className="w-full">
        <TabsList className="mb-4">
          <TabsTrigger value="metrics">
            <BarChart3 className="mr-2 h-4 w-4" />
            Метрики качества
          </TabsTrigger>
          <TabsTrigger value="system">
            <Server className="mr-2 h-4 w-4" />
            Система и Задачи
          </TabsTrigger>
          <TabsTrigger value="tokens">
            <Coins className="mr-2 h-4 w-4" />
            Токены и расходы
          </TabsTrigger>
          <TabsTrigger value="access">
            <Users className="mr-2 h-4 w-4" />
            Доступ
          </TabsTrigger>
        </TabsList>
        
        <TabsContent value="metrics" className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between mb-4">
            <h2 className="text-lg font-medium">Статистика сопоставления</h2>
            <div className="flex flex-wrap items-center gap-2">
              <Select value={supplierFilter} onValueChange={(val: string | null) => val && setSupplierFilter(val)}>
                <SelectTrigger className="w-[220px] bg-background">
                  <SelectValue placeholder="Все поставщики" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">Все поставщики (Сводно)</SelectItem>
                  {suppliers.map(s => (
                    <SelectItem key={s.supplier_id} value={s.supplier_id}>{s.supplier_name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Категория..."
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  className="w-[180px] pl-8 bg-background"
                />
              </div>
            </div>
          </div>

          {metricsQuery.isError && (
            <QueryErrorBanner
              error={metricsQuery.error}
              onRetry={() => metricsQuery.refetch()}
            />
          )}

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Всего позиций</CardTitle>
                <Database className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {metricsQuery.isLoading ? <Skeleton className="h-8 w-20" /> : metrics?.total_cases?.toLocaleString() ?? "—"}
                </div>
                <p className="text-xs text-muted-foreground">обработано за всё время</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-1">
                  Точность Top-1
                  <Tooltip>
                    <TooltipTrigger className="cursor-help">
                      <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
                    </TooltipTrigger>
                    <TooltipContent>Процент случаев, когда лучший кандидат совпал с выбранным оператором</TooltipContent>
                  </Tooltip>
                </CardTitle>
                <Activity className="h-4 w-4 text-green-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-green-600">
                  {metricsQuery.isLoading ? <Skeleton className="h-8 w-20" /> : metrics ? `${(metrics.top1_accuracy ? metrics.top1_accuracy * 100 : 0).toFixed(1)}%` : "—"}
                </div>
                <p className="text-xs text-muted-foreground">лучший кандидат совпал с выбором</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-1">
                  Полнота Top-3
                  <Tooltip>
                    <TooltipTrigger className="cursor-help">
                      <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
                    </TooltipTrigger>
                    <TooltipContent>Процент случаев, когда верный ответ был среди трёх лучших кандидатов</TooltipContent>
                  </Tooltip>
                </CardTitle>
                <Settings2 className="h-4 w-4 text-yellow-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-yellow-600">
                  {metricsQuery.isLoading ? <Skeleton className="h-8 w-20" /> : metrics ? `${(metrics.top3_recall ? metrics.top3_recall * 100 : 0).toFixed(1)}%` : "—"}
                </div>
                <p className="text-xs text-muted-foreground">верный ответ в топ 3 кандидатах</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Принято операторами</CardTitle>
                <Activity className="h-4 w-4 text-primary" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-primary">
                  {metricsQuery.isLoading ? <Skeleton className="h-8 w-20" /> : metrics ? `${(metrics.review_acceptance_rate ? metrics.review_acceptance_rate * 100 : 0).toFixed(1)}%` : "—"}
                </div>
                <p className="text-xs text-muted-foreground">успешные ручные проверки</p>
              </CardContent>
            </Card>
          </div>

          <Card className="mt-6">
            <CardHeader>
              <CardTitle>Обзор метрик</CardTitle>
              <CardDescription>Визуализация основных показателей качества</CardDescription>
            </CardHeader>
            <CardContent>
              {metricsQuery.isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-6 w-full" />
                  ))}
                </div>
              ) : metrics ? (
                <div className="space-y-3">
                  {[
                    { label: "Точность Top-1", value: metrics.top1_accuracy ?? 0, color: "bg-green-500" },
                    { label: "Полнота Top-3", value: metrics.top3_recall ?? 0, color: "bg-yellow-500" },
                    { label: "Принято операторами", value: metrics.review_acceptance_rate ?? 0, color: "bg-primary" },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>{label}</span>
                        <span className="font-medium">{(value * 100).toFixed(1)}%</span>
                      </div>
                      <div className="h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${color}`}
                          style={{ width: `${value * 100}%` }}
                        />
                      </div>
                    </div>
                  ))}
                  <div className="pt-2 border-t mt-3">
                    <div className="flex justify-between text-xs">
                      <span>Всего обработано</span>
                      <span className="font-medium">{metrics.total_cases?.toLocaleString() ?? 0}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">Нет данных</div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="system" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Состояние сервисов</CardTitle>
              <CardDescription>Подключение к базе данных и очередям задач</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-4">
                {healthQuery.isLoading ? (
                  <>
                    <Skeleton className="h-8 w-40" />
                    <Skeleton className="h-8 w-40" />
                  </>
                ) : (
                  <>
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">База данных:</span>
                      <Badge
                        variant="outline"
                        className={
                          healthQuery.data?.database === "connected" || healthQuery.data?.status === "ok"
                            ? "bg-green-50 text-green-700"
                            : "bg-red-50 text-red-700"
                        }
                      >
                        {healthQuery.data?.database === "connected" || healthQuery.data?.status === "ok"
                          ? "Подключена"
                          : "Недоступна"}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2">
                      <Server className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">Redis:</span>
                      <Badge
                        variant="outline"
                        className={
                          healthQuery.data?.redis === "connected" || healthQuery.data?.status === "ok"
                            ? "bg-green-50 text-green-700"
                            : "bg-red-50 text-red-700"
                        }
                      >
                        {healthQuery.data?.redis === "connected" || healthQuery.data?.status === "ok"
                          ? "Подключён"
                          : "Недоступен"}
                      </Badge>
                    </div>
                  </>
                )}
                {healthQuery.isError && (
                  <span className="text-sm text-destructive">Не удалось получить статус</span>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Фоновые задачи</CardTitle>
              <CardDescription>Статус долгих системных операций</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-3 border-b border-border text-sm">
                  <div className="flex flex-col gap-1">
                    <span className="font-medium">Импорт номенклатуры (1С)</span>
                    <span className="text-xs text-muted-foreground">Последний запуск: сегодня 10:45</span>
                  </div>
                  <Badge variant="outline" className="bg-green-50 text-green-700">Завершено</Badge>
                </div>

                <div className="flex items-center justify-between py-3 border-b border-border text-sm">
                  <div className="flex flex-col gap-1">
                    <span className="font-medium">Полная переиндексация векторов (Cohere)</span>
                    <span className="text-xs text-muted-foreground">Автозапуск отключен</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant="outline" className="bg-gray-50 text-gray-700">Ожидает</Badge>
                    <Button size="sm" variant="outline" onClick={() => reindexMutation.mutate()} disabled={reindexMutation.isPending}>
                      <RefreshCw className="mr-2 h-3 w-3" />
                      Запустить
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tokens" className="space-y-4">
          {/* Period selector */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-sm font-medium text-muted-foreground">Период:</span>
            {[
              { label: "7 дн.", value: 7 },
              { label: "30 дн.", value: 30 },
              { label: "90 дн.", value: 90 },
            ].map((p) => (
              <Button
                key={p.value}
                size="sm"
                variant={tokenDays === p.value ? "default" : "outline"}
                onClick={() => setTokenDays(p.value)}
              >
                {p.label}
              </Button>
            ))}
          </div>

          {tokenUsageQuery.isError && (
            <QueryErrorBanner
              error={tokenUsageQuery.error}
              onRetry={() => tokenUsageQuery.refetch()}
            />
          )}

          {/* Summary cards */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Всего токенов</CardTitle>
                <Database className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {tokenUsageQuery.isLoading ? <Skeleton className="h-8 w-24" /> : tokenUsageQuery.data?.totals.total_tokens.toLocaleString() ?? "—"}
                </div>
                <p className="text-xs text-muted-foreground">
                  {tokenUsageQuery.data ? `${tokenUsageQuery.data.totals.prompt_tokens.toLocaleString()} prompt / ${tokenUsageQuery.data.totals.completion_tokens.toLocaleString()} completion` : ""}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Расходы ($)</CardTitle>
                <Coins className="h-4 w-4 text-yellow-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-yellow-600">
                  {tokenUsageQuery.isLoading ? <Skeleton className="h-8 w-20" /> : tokenUsageQuery.data ? `$${tokenUsageQuery.data.totals.total_cost_usd.toFixed(4)}` : "—"}
                </div>
                <p className="text-xs text-muted-foreground">за {tokenDays} дн.</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">API вызовов</CardTitle>
                <Activity className="h-4 w-4 text-blue-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-blue-600">
                  {tokenUsageQuery.isLoading ? <Skeleton className="h-8 w-16" /> : tokenUsageQuery.data?.totals.api_calls.toLocaleString() ?? "—"}
                </div>
                <p className="text-xs text-muted-foreground">общее кол-во запросов</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Средн. токенов/вызов</CardTitle>
                <BarChart3 className="h-4 w-4 text-green-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-green-600">
                  {tokenUsageQuery.isLoading ? (
                    <Skeleton className="h-8 w-16" />
                  ) : tokenUsageQuery.data && tokenUsageQuery.data.totals.api_calls > 0 ? (
                    Math.round(tokenUsageQuery.data.totals.total_tokens / tokenUsageQuery.data.totals.api_calls).toLocaleString()
                  ) : (
                    "—"
                  )}
                </div>
                <p className="text-xs text-muted-foreground">токенов на запрос</p>
              </CardContent>
            </Card>
          </div>

          {/* Provider breakdown */}
          <Card>
            <CardHeader>
              <CardTitle>По провайдерам</CardTitle>
              <CardDescription>Распределение токенов и расходов по провайдерам</CardDescription>
            </CardHeader>
            <CardContent>
              {tokenUsageQuery.isLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-8 w-full" />
                  ))}
                </div>
              ) : tokenUsageQuery.data && tokenUsageQuery.data.by_provider.length > 0 ? (
                <div className="space-y-3">
                  {(() => {
                    const maxTokens = Math.max(...tokenUsageQuery.data.by_provider.map((p) => p.total_tokens), 1);
                    return tokenUsageQuery.data.by_provider.map((p) => (
                      <div key={p.provider} className="space-y-1">
                        <div className="flex justify-between text-sm">
                          <span className="font-medium">{p.provider}</span>
                          <span className="text-muted-foreground">
                            {p.total_tokens.toLocaleString()} токенов &middot; ${p.cost_usd.toFixed(4)} &middot; {p.calls} вызовов
                          </span>
                        </div>
                        <div className="h-3 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full bg-primary transition-all"
                            style={{ width: `${(p.total_tokens / maxTokens) * 100}%` }}
                          />
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">Нет данных</div>
              )}
            </CardContent>
          </Card>

          {/* Daily usage chart */}
          <Card>
            <CardHeader>
              <CardTitle>Ежедневное потребление</CardTitle>
              <CardDescription>Токены по дням за выбранный период</CardDescription>
            </CardHeader>
            <CardContent>
              {tokenUsageQuery.isLoading ? (
                <div className="flex items-end gap-1 h-32">
                  {Array.from({ length: 14 }).map((_, i) => (
                    <Skeleton key={i} className="flex-1 h-full" />
                  ))}
                </div>
              ) : tokenUsageQuery.data && tokenUsageQuery.data.daily.length > 0 ? (
                <div className="space-y-2">
                  <div className="flex items-end gap-1 h-40">
                    {(() => {
                      const daily = tokenUsageQuery.data.daily;
                      const maxTokens = Math.max(...daily.map((d) => d.total_tokens), 1);
                      return daily.map((d) => {
                        const heightPct = Math.max((d.total_tokens / maxTokens) * 100, 2);
                        return (
                          <Tooltip key={d.date}>
                            <TooltipTrigger
                              render={
                                <div
                                  className="flex-1 bg-primary/80 hover:bg-primary rounded-t transition-all cursor-default min-w-[4px]"
                                  style={{ height: `${heightPct}%` }}
                                />
                              }
                            />
                            <TooltipContent>
                              <div className="text-xs">
                                <div className="font-medium">{d.date}</div>
                                <div>{d.total_tokens.toLocaleString()} токенов</div>
                                <div>${d.cost_usd.toFixed(4)}</div>
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        );
                      });
                    })()}
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>{tokenUsageQuery.data.daily[0]?.date}</span>
                    <span>{tokenUsageQuery.data.daily[tokenUsageQuery.data.daily.length - 1]?.date}</span>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">Нет данных</div>
              )}
            </CardContent>
          </Card>

          {/* Model detail table */}
          <Card>
            <CardHeader>
              <CardTitle>По моделям</CardTitle>
              <CardDescription>Детализация потребления по моделям и операциям</CardDescription>
            </CardHeader>
            <CardContent>
              {tokenUsageQuery.isLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-8 w-full" />
                  ))}
                </div>
              ) : tokenUsageQuery.data && tokenUsageQuery.data.by_model.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Провайдер</TableHead>
                      <TableHead>Модель</TableHead>
                      <TableHead>Операция</TableHead>
                      <TableHead className="text-right">Токены</TableHead>
                      <TableHead className="text-right">Расход ($)</TableHead>
                      <TableHead className="text-right">Вызовы</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tokenUsageQuery.data.by_model.map((m, idx) => (
                      <TableRow key={`${m.provider}-${m.model}-${m.operation}-${idx}`}>
                        <TableCell>
                          <Badge variant="outline">{m.provider}</Badge>
                        </TableCell>
                        <TableCell className="font-mono text-xs">{m.model}</TableCell>
                        <TableCell>
                          <Badge variant="secondary">{m.operation}</Badge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{m.total_tokens.toLocaleString()}</TableCell>
                        <TableCell className="text-right tabular-nums">${m.cost_usd.toFixed(4)}</TableCell>
                        <TableCell className="text-right tabular-nums">{m.calls.toLocaleString()}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <div className="text-sm text-muted-foreground">Нет данных</div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="access" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Всего пользователей</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {usersQuery.isLoading ? <Skeleton className="h-8 w-12" /> : allUsers.length}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Администраторы</CardTitle>
                <Shield className="h-4 w-4 text-purple-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {usersQuery.isLoading ? <Skeleton className="h-8 w-12" /> : allUsers.filter((u) => u.role === "admin").length}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Операторы</CardTitle>
                <UserCog className="h-4 w-4 text-blue-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {usersQuery.isLoading ? <Skeleton className="h-8 w-12" /> : allUsers.filter((u) => u.role === "operator").length}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Наблюдатели</CardTitle>
                <Eye className="h-4 w-4 text-gray-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {usersQuery.isLoading ? <Skeleton className="h-8 w-12" /> : allUsers.filter((u) => u.role === "viewer").length}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
