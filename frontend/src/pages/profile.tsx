import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { getMe } from "@/api/auth";
import { updateProfile, changePassword } from "@/api/users";
import { listMatchRequests } from "@/api/match";
import type { MatchRequestDetails } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { QueryErrorBanner } from "@/components/ui/query-error-banner";
import { PageLayout } from "@/components/layout/page-layout";
import { Loader2, History } from "lucide-react";

const ROLE_LABELS: Record<string, string> = {
  admin: "Администратор",
  operator: "Оператор",
  viewer: "Наблюдатель",
};

export default function ProfilePage() {
  const queryClient = useQueryClient();
  const meQuery = useQuery({ queryKey: ["me"], queryFn: getMe, retry: false });

  // Name editing
  const [fullName, setFullName] = useState<string | null>(null);
  const nameDirty = fullName !== null && fullName !== (meQuery.data?.full_name ?? "");

  const nameMutation = useMutation({
    mutationFn: () => updateProfile(fullName || null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      setFullName(null);
      toast.success("Имя обновлено");
    },
    onError: () => toast.error("Ошибка при обновлении имени"),
  });

  // Password change
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [pwError, setPwError] = useState<string | null>(null);

  const pwMutation = useMutation({
    mutationFn: () => changePassword(currentPw, newPw),
    onSuccess: () => {
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      setPwError(null);
      toast.success("Пароль успешно изменён");
    },
    onError: (err: unknown) => {
      if (err && typeof err === "object" && "response" in err) {
        const httpErr = err as { response: Response };
        if (httpErr.response.status === 401) {
          setPwError("Неверный текущий пароль");
          return;
        }
      }
      setPwError("Ошибка при смене пароля");
    },
  });

  function handlePasswordSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPwError(null);
    if (newPw.length < 6) {
      setPwError("Новый пароль должен содержать минимум 6 символов");
      return;
    }
    if (newPw !== confirmPw) {
      setPwError("Пароли не совпадают");
      return;
    }
    pwMutation.mutate();
  }

  const user = meQuery.data;

  const activityQuery = useQuery({
    queryKey: ["my-activity"],
    queryFn: () => listMatchRequests({ limit: 5 }),
    enabled: !!user,
  });

  const STATUS_LABELS: Record<string, string> = {
    queued: "В очереди",
    running: "Обрабатывается",
    done: "Завершено",
    failed: "Ошибка",
  };

  const STATUS_COLORS: Record<string, string> = {
    queued: "bg-gray-100 text-gray-800",
    running: "bg-blue-100 text-blue-800",
    done: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };

  return (
    <PageLayout title="Мой профиль" description="Информация об аккаунте и смена пароля.">
      {meQuery.isError && (
        <QueryErrorBanner
          error={meQuery.error}
          onRetry={() => meQuery.refetch()}
        />
      )}
      <div className="grid gap-6 max-w-xl">
        {/* Account info card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Информация об аккаунте</CardTitle>
            <CardDescription>Основные данные учётной записи.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-1.5">
              <Label className="text-muted-foreground text-xs">Имя пользователя</Label>
              <div className="text-sm font-mono">@{user?.username ?? "..."}</div>
              <p className="text-xs text-muted-foreground">Имя пользователя нельзя изменить</p>
            </div>
            <div className="grid gap-1.5">
              <Label className="text-muted-foreground text-xs">Роль</Label>
              <div>
                <Badge variant="outline">
                  {ROLE_LABELS[user?.role ?? ""] ?? user?.role ?? "..."}
                </Badge>
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="profile-name">Полное имя</Label>
              <div className="flex gap-2">
                <Input
                  id="profile-name"
                  value={fullName ?? (user?.full_name ?? "")}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Введите имя"
                />
                <Button
                  size="sm"
                  disabled={!nameDirty || nameMutation.isPending}
                  onClick={() => nameMutation.mutate()}
                >
                  {nameMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    "Сохранить"
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Password change card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Смена пароля</CardTitle>
            <CardDescription>Введите текущий и новый пароль.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handlePasswordSubmit} className="space-y-4">
              <div className="grid gap-1.5">
                <Label htmlFor="current-pw">Текущий пароль</Label>
                <Input
                  id="current-pw"
                  type="password"
                  value={currentPw}
                  onChange={(e) => setCurrentPw(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="new-pw">Новый пароль</Label>
                <Input
                  id="new-pw"
                  type="password"
                  value={newPw}
                  onChange={(e) => setNewPw(e.target.value)}
                  placeholder="Минимум 6 символов"
                  autoComplete="new-password"
                  required
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="confirm-pw">Подтвердите новый пароль</Label>
                <Input
                  id="confirm-pw"
                  type="password"
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  autoComplete="new-password"
                  required
                />
              </div>

              {pwError && (
                <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  {pwError}
                </div>
              )}

              <Button type="submit" disabled={pwMutation.isPending}>
                {pwMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Сменить пароль
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Activity history card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <History className="h-4 w-4" />
              Моя активность
            </CardTitle>
            <CardDescription>Последние запросы на сопоставление.</CardDescription>
          </CardHeader>
          <CardContent>
            {activityQuery.isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : activityQuery.data?.items && activityQuery.data.items.length > 0 ? (
              <div className="space-y-2">
                {activityQuery.data.items.map((req: MatchRequestDetails) => (
                  <Link
                    key={req.request_id}
                    to="/requests/$requestId"
                    params={{ requestId: req.request_id }}
                    className="flex items-center justify-between rounded-md border px-3 py-2 hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex flex-col gap-0.5">
                      <span className="text-sm font-medium">
                        {req.file_name ?? `Запрос от ${new Date(req.created_at).toLocaleDateString("ru-RU")}`}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(req.created_at).toLocaleDateString("ru-RU", {
                          day: "2-digit",
                          month: "2-digit",
                          year: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                        {" \u00b7 "}
                        {req.total_items} {req.total_items === 1 ? "позиция" : "позиций"}
                      </span>
                    </div>
                    <Badge
                      variant="outline"
                      className={STATUS_COLORS[req.status] ?? ""}
                    >
                      {STATUS_LABELS[req.status] ?? req.status}
                    </Badge>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Нет недавней активности.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </PageLayout>
  );
}
