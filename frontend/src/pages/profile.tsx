import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { getMe } from "@/api/auth";
import { updateProfile, changePassword } from "@/api/users";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PageLayout } from "@/components/layout/page-layout";
import { Loader2 } from "lucide-react";

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

  return (
    <PageLayout title="Мой профиль" description="Информация об аккаунте и смена пароля.">
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
                <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
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
      </div>
    </PageLayout>
  );
}
