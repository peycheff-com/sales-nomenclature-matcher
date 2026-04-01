import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { LogOut, Menu, User, UserCircle } from "lucide-react";
import { getMe, logout } from "@/api/auth";
import { setAuthenticated } from "@/lib/auth-store";
import { useSidebarContext } from "./app-shell";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export default function Header() {
  const { toggle } = useSidebarContext();

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
    <header className="flex h-14 items-center justify-between border-b border-border bg-background px-4">
      <Button variant="ghost" size="sm" className="lg:hidden" onClick={toggle}>
        <Menu className="h-5 w-5" />
      </Button>
      <div className="flex-1" />
      <div className="flex items-center gap-3">
        {userQuery.data && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted transition-colors">
                <User className="h-4 w-4" />
                <span className="hidden sm:inline">
                  {userQuery.data.full_name || userQuery.data.username}
                </span>
                {userQuery.data.role === "admin" && (
                  <span className="rounded bg-muted px-1.5 py-0.5 text-xs">
                    admin
                  </span>
                )}
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem asChild>
                <Link to="/profile" className="flex items-center gap-2 cursor-pointer">
                  <UserCircle className="h-4 w-4" />
                  Мой профиль
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="flex items-center gap-2 cursor-pointer"
                onClick={handleLogout}
              >
                <LogOut className="h-4 w-4" />
                Выйти
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </header>
  );
}
