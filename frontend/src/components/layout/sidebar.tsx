import { Link, useMatchRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, FileSearch, LayoutDashboard, Settings as SettingsIcon, Database, Users, Shield, UserCog } from "lucide-react";
import { getMe } from "@/api/auth";
import { listMatchRequests } from "@/api/match";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Загрузка", icon: LayoutDashboard, adminOnly: false, badgeKey: null },
  { to: "/requests", label: "Запросы", icon: FileSearch, adminOnly: false, badgeKey: "requests" as const },
  { to: "/catalog", label: "Каталог", icon: Database, adminOnly: false, badgeKey: null },
  { to: "/suppliers", label: "Поставщики", icon: Users, adminOnly: false, badgeKey: null },
  { to: "/admin", label: "Админ / Метрики", icon: Shield, adminOnly: true, badgeKey: null },
  { to: "/users", label: "Пользователи", icon: UserCog, adminOnly: true, badgeKey: null },
  { to: "/settings", label: "Настройки", icon: SettingsIcon, adminOnly: true, badgeKey: null },
] as const;

interface SidebarProps {
  onNavigate?: () => void;
}

export default function Sidebar({ onNavigate }: SidebarProps) {
  const matchRoute = useMatchRoute();
  const userQuery = useQuery({ queryKey: ["me"], queryFn: getMe, retry: false });
  const role = userQuery.data?.role;

  // Badge: count of active (queued/running) requests
  const requestsQuery = useQuery({
    queryKey: ["match-requests"],
    queryFn: () => listMatchRequests(),
    staleTime: 30_000,
  });
  const activeRequestCount = (requestsQuery.data?.items ?? []).filter(
    (r) => r.status === "running" || r.status === "queued"
  ).length;

  const badges: Record<string, number> = {
    requests: activeRequestCount,
  };

  const visibleItems = navItems.filter((item) => !item.adminOnly || role === "admin");

  return (
    <aside className="flex h-full w-56 flex-col border-r border-border bg-sidebar-background">
      <div className="flex h-14 items-center border-b border-border px-4">
        <Link to="/" className="flex items-center w-full">
          <BarChart3 className="mr-2 h-5 w-5 text-primary" />
          <span className="text-sm font-semibold text-foreground">
            Matcher
          </span>
        </Link>
      </div>
      <nav className="flex-1 space-y-1 p-2">
        {visibleItems.map((item) => {
          const isActive =
            item.to === "/"
              ? matchRoute({ to: "/", fuzzy: false })
              : matchRoute({ to: item.to, fuzzy: true });
          return (
            <Link
              key={item.to}
              to={item.to}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
              )}
            >
              <item.icon className="h-4 w-4" />
              <span className="flex-1">{item.label}</span>
              {item.badgeKey && badges[item.badgeKey] > 0 && (
                <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[10px] font-medium text-primary-foreground">
                  {badges[item.badgeKey]}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-border px-4 py-2">
        <span className="text-[10px] text-muted-foreground/60">v0.1.0</span>
      </div>
    </aside>
  );
}
