import { useState, useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  LayoutDashboard,
  Database,
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
  { label: "Рабочий стол", to: "/", icon: LayoutDashboard, keywords: "upload dashboard главная загрузка запросы requests" },
  { label: "База данных", to: "/catalog", icon: Database, keywords: "catalog каталог товары продукты поставщики suppliers" },
  { label: "Система", to: "/settings", icon: Settings, keywords: "settings настройки admin метрики users пользователи" },
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
