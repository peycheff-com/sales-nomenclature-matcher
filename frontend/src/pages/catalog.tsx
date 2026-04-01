import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { searchCatalog } from "@/api/catalog";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Search } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function CatalogPage() {
  const [query, setQuery] = useState("");
  const [searchTrigger, setSearchTrigger] = useState("");

  const catalogQuery = useQuery({
    queryKey: ["catalog", searchTrigger],
    queryFn: () => searchCatalog(searchTrigger),
    enabled: true,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearchTrigger(query);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Каталог товаров</h1>
        <p className="text-muted-foreground">Поиск и просмотр активной номенклатуры (для ручного сопоставления).</p>
      </div>

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSearch} className="flex gap-2">
            <Input
              placeholder="Поиск по названию, артикулу, бренду..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="max-w-md"
            />
            <Button type="submit" disabled={catalogQuery.isFetching}>
              <Search className="h-4 w-4 mr-2" />
              Искать
            </Button>
          </form>
        </CardContent>
      </Card>

      <div className="rounded-md border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Артикул</TableHead>
              <TableHead>Наименование</TableHead>
              <TableHead>Бренд</TableHead>
              <TableHead>ID (UUID)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {catalogQuery.isLoading ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center py-8 text-muted-foreground">Загрузка...</TableCell>
              </TableRow>
            ) : catalogQuery.data?.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center py-8 text-muted-foreground">Товары не найдены</TableCell>
              </TableRow>
            ) : (
              catalogQuery.data?.map(p => (
                <TableRow key={p.product_id}>
                  <TableCell className="font-mono text-xs">{p.article || "\u2014"}</TableCell>
                  <TableCell>{p.name}</TableCell>
                  <TableCell>{p.brand || "\u2014"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{p.product_id}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
