import { useQuery } from "@tanstack/react-query";
import { LogOut, User } from "lucide-react";
import { getMe, logout } from "@/api/auth";
import { setAuthenticated } from "@/lib/auth-store";
import { Button } from "@/components/ui/button";

export default function Header() {
  const userQuery = useQuery({
    queryKey: ["me"],
    queryFn: getMe,
    retry: false,
  });

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Best-effort: even if the API call fails, clear local state
    }
    setAuthenticated(false);
    window.location.href = "/login";
  }

  return (
    <header className="flex h-14 items-center justify-end border-b border-border bg-background px-4">
      <div className="flex items-center gap-3">
        {userQuery.data && (
          <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <User className="h-4 w-4" />
            {userQuery.data.full_name || userQuery.data.username}
            {userQuery.data.role === "admin" && (
              <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
                admin
              </span>
            )}
          </span>
        )}
        <Button variant="ghost" size="sm" onClick={handleLogout}>
          <LogOut className="mr-1 h-4 w-4" />
          Выйти
        </Button>
      </div>
    </header>
  );
}
