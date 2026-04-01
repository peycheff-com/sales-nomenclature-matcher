import { createContext, useContext, useState, useEffect } from "react";
import { Outlet, useNavigate } from "@tanstack/react-router";
import { LogIn } from "lucide-react";
import { onSessionExpired } from "@/lib/auth-store";
import Header from "./header";
import Sidebar from "./sidebar";
import CommandPalette from "@/components/command-palette";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

interface SidebarContextValue {
  open: boolean;
  toggle: () => void;
}

const SidebarContext = createContext<SidebarContextValue>({ open: false, toggle: () => {} });

export function useSidebarContext() {
  return useContext(SidebarContext);
}

export default function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    return onSessionExpired(() => setSessionExpired(true));
  }, []);

  function handleReLogin() {
    setSessionExpired(false);
    navigate({ to: "/login" });
  }

  return (
    <SidebarContext.Provider value={{ open: sidebarOpen, toggle: () => setSidebarOpen((v) => !v) }}>
      {/* Skip to content link (GAP-9.14) */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground focus:text-sm focus:font-medium focus:shadow-lg"
      >
        Перейти к основному содержимому
      </a>
      <div className="flex h-screen overflow-hidden bg-background">
        {/* Desktop sidebar */}
        <div className="hidden lg:block">
          <Sidebar />
        </div>

        {/* Mobile sidebar overlay */}
        {sidebarOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div
              className="absolute inset-0 bg-black/50"
              onClick={() => setSidebarOpen(false)}
            />
            <div className="relative z-50 h-full w-56">
              <Sidebar onNavigate={() => setSidebarOpen(false)} />
            </div>
          </div>
        )}

        <div className="flex flex-1 flex-col overflow-hidden">
          <Header />
          <main id="main-content" className="flex-1 overflow-auto p-4 md:p-6">
            <Outlet />
          </main>
        </div>
      </div>

      <CommandPalette />

      <AlertDialog open={sessionExpired}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Сессия истекла</AlertDialogTitle>
            <AlertDialogDescription>
              Ваша сессия истекла. Пожалуйста, войдите в систему повторно.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction onClick={handleReLogin}>
              <LogIn className="h-4 w-4 mr-2" />
              Войти снова
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </SidebarContext.Provider>
  );
}
