import { useState, useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  LayoutDashboard,
  FileSearch,
  Database,
  Users,
  Shield,
  UserCog,
  Settings,
  User,
} from "lucide-react";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

const pages = [
  { label: "Загрузка данных", to: "/", icon: LayoutDashboard, keywords: "upload dashboard главная загрузка" },
  { label: "Запросы", to: "/requests", icon: FileSearch, keywords: "requests запросы список" },
  { label: "Каталог", to: "/catalog", icon: Database, keywords: "catalog каталог товары продукты" },
  { label: "Поставщики", to: "/suppliers", icon: Users, keywords: "suppliers поставщики" },
  { label: "Админ / Метрики", to: "/admin", icon: Shield, keywords: "admin метрики качество" },
  { label: "Пользователи", to: "/users", icon: UserCog, keywords: "users пользователи" },
  { label: "Настройки", to: "/settings", icon: Settings, keywords: "settings настройки" },
  { label: "Мой профиль", to: "/profile", icon: User, keywords: "profile профиль аккаунт" },
];

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  function handleSelect(to: string) {
    setOpen(false);
    navigate({ to });
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <Command>
        <CommandInput placeholder="Перейти к странице..." />
        <CommandList>
          <CommandEmpty>Ничего не найдено</CommandEmpty>
          <CommandGroup heading="Страницы">
            {pages.map((page) => (
              <CommandItem
                key={page.to}
                value={`${page.label} ${page.keywords}`}
                onSelect={() => handleSelect(page.to)}
                className="flex items-center gap-2 cursor-pointer"
              >
                <page.icon className="h-4 w-4 text-muted-foreground" />
                {page.label}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
