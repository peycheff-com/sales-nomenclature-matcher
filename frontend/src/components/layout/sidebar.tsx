import { Link, useMatchRoute } from "@tanstack/react-router";
import { BarChart3, FileSearch, LayoutDashboard, Settings as SettingsIcon, Database, Users } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", label: "Загрузка", icon: LayoutDashboard },
  { to: "/requests", label: "Запросы", icon: FileSearch },
  { to: "/catalog", label: "Каталог", icon: Database },
  { to: "/suppliers", label: "Поставщики", icon: Users },
  { to: "/admin", label: "Импорт Данных", icon: SettingsIcon },
  { to: "/settings", label: "Настройки", icon: SettingsIcon },
] as const;

export default function Sidebar() {
  const matchRoute = useMatchRoute();

  return (
    <aside className="flex h-full w-56 flex-col border-r border-border bg-sidebar-background">
      <div className="flex h-14 items-center border-b border-border px-4">
        <BarChart3 className="mr-2 h-5 w-5 text-primary" />
        <span className="text-sm font-semibold text-foreground">
          Matcher
        </span>
      </div>
      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => {
          const isActive =
            item.to === "/"
              ? matchRoute({ to: "/", fuzzy: false })
              : matchRoute({ to: item.to, fuzzy: true });
          return (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground font-medium"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
