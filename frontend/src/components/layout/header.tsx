import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export default function Header() {
  const { toggle } = useSidebarContext();
  const navigate = useNavigate();
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

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
    <>
      <header className="flex h-14 items-center justify-between border-b border-border bg-background px-4">
        <Button variant="ghost" size="sm" className="lg:hidden" onClick={toggle} aria-label="Открыть меню">
          <Menu className="h-5 w-5" />
        </Button>
        <div className="flex-1" />
        <div className="flex items-center gap-3">
          {userQuery.data && (
            <DropdownMenu>
              <DropdownMenuTrigger className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground hover:bg-muted transition-colors">
                <User className="h-4 w-4" />
                <span className="hidden sm:inline">
                  {userQuery.data.full_name || userQuery.data.username}
                </span>
                <span className={`rounded px-1.5 py-0.5 text-xs ${
                  userQuery.data.role === "admin" ? "bg-purple-100 text-purple-700" :
                  userQuery.data.role === "operator" ? "bg-blue-100 text-blue-700" :
                  "bg-gray-100 text-gray-700"
                }`}>
                  {userQuery.data.role === "admin" ? "Админ" :
                   userQuery.data.role === "operator" ? "Оператор" : "Наблюдатель"}
                </span>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuItem
                  className="flex items-center gap-2 cursor-pointer"
                  onClick={() => navigate({ to: "/profile" })}
                >
                  <UserCircle className="h-4 w-4" />
                  Мой профиль
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="flex items-center gap-2 cursor-pointer"
                  onClick={() => setShowLogoutConfirm(true)}
                >
                  <LogOut className="h-4 w-4" />
                  Выйти
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </header>

      <AlertDialog open={showLogoutConfirm} onOpenChange={setShowLogoutConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Выход из системы</AlertDialogTitle>
            <AlertDialogDescription>
              Вы уверены, что хотите выйти из системы?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setShowLogoutConfirm(false)}>
              Отмена
            </AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleLogout}>
              Выйти
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
