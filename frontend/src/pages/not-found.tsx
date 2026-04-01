import { PageLayout } from "@/components/layout/page-layout";
import { Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Home } from "lucide-react";

export function NotFound() {
  return (
    <PageLayout title="404" description="Страница не найдена">
      <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4 text-center">
        <h1 className="text-4xl font-bold text-muted-foreground">404</h1>
        <p className="text-muted-foreground max-w-sm">Мы не смогли найти запрашиваемую страницу.</p>
        <Link to="/">
          <Button type="button" className="mt-4">
            <Home className="mr-2 h-4 w-4" />
            Вернуться на главную
          </Button>
        </Link>
      </div>
    </PageLayout>
  );
}
