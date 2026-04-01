import { type FormEvent, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { BarChart3, Eye, EyeOff } from "lucide-react";
import { login } from "@/api/auth";
import { setAuthenticated, setMustChangePassword } from "@/lib/auth-store";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await login(username, password);
      // Cookie is set by the backend; mark in-memory state
      setAuthenticated(true);
      setMustChangePassword(result.must_change_password);
      navigate({ to: result.must_change_password ? "/change-password" : "/" });
    } catch (err: unknown) {
      if (err && typeof err === "object" && "response" in err) {
        const httpErr = err as { response: Response };
        if (httpErr.response.status === 401) {
          // Check if account is deactivated
          try {
            const body = await httpErr.response.json() as { detail?: string };
            if (
              body.detail &&
              (body.detail.toLowerCase().includes("deactivated") ||
                body.detail.toLowerCase().includes("disabled"))
            ) {
              setError("Ваш аккаунт деактивирован. Обратитесь к администратору.");
            } else {
              setError("Неверное имя пользователя или пароль");
            }
          } catch {
            setError("Неверное имя пользователя или пароль");
          }
        } else {
          setError("Ошибка сервера. Попробуйте позже.");
        }
      } else {
        setError("Не удалось подключиться к серверу");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-primary">
            <BarChart3 className="h-5 w-5 text-primary-foreground" />
          </div>
          <CardTitle className="text-lg">Вход в систему</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="username">Имя пользователя</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Логин"
                autoComplete="username"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Пароль</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Пароль"
                  autoComplete="current-password"
                  className="pr-10"
                  required
                />
                <button
                  type="button"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  onClick={() => setShowPassword((v) => !v)}
                  tabIndex={-1}
                  aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </div>

            {error && (
              <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Вход..." : "Войти"}
            </Button>
          </form>
          <p className="text-xs text-muted-foreground text-center mt-4">
            Забыли пароль? Обратитесь к администратору системы для сброса.
          </p>
          <p className="text-[11px] text-muted-foreground text-center mt-2">
            Сессия активна в течение рабочего дня. При истечении потребуется повторный вход.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
