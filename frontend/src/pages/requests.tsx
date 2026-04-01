import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Trash2 } from "lucide-react";
import { listMatchRequests, deleteMatchRequest } from "@/api/match";
import { REQUEST_STATUS_LABELS } from "@/lib/constants";
import { formatDate } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function RequestsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const requestsQuery = useQuery({
    queryKey: ["match-requests"],
    queryFn: listMatchRequests,
    refetchInterval: 10_000,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteMatchRequest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["match-requests"] });
    },
  });

  const requests = requestsQuery.data?.items ?? [];

  const statusColor: Record<string, string> = {
    queued: "bg-gray-100 text-gray-800",
    running: "bg-blue-100 text-blue-800",
    done: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Запросы на сопоставление</h1>

      {requestsQuery.isLoading ? (
        <div className="py-12 text-center text-sm text-muted-foreground">
          Загрузка...
        </div>
      ) : requests.length === 0 ? (
        <div className="py-12 text-center text-sm text-muted-foreground">
          Нет запросов
        </div>
      ) : (
        <div className="rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID запроса</TableHead>
                <TableHead>Поставщик</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Прогресс</TableHead>
                <TableHead>Результаты</TableHead>
                <TableHead>Создан</TableHead>
                <TableHead className="w-12"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requests.map((req) => (
                <TableRow
                  key={req.request_id}
                  className="cursor-pointer"
                  onClick={() =>
                    navigate({
                      to: "/requests/$requestId",
                      params: { requestId: req.request_id },
                    })
                  }
                >
                  <TableCell className="font-mono text-xs">
                    {req.request_id}
                  </TableCell>
                  <TableCell className="text-sm">
                    {req.supplier_id ?? "—"}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className={statusColor[req.status] ?? ""}
                    >
                      {REQUEST_STATUS_LABELS[req.status] ?? req.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">
                    {req.processed_items}/{req.total_items}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-green-700">
                        {req.auto_matched_items}
                      </span>
                      <span className="text-muted-foreground">/</span>
                      <span className="text-yellow-700">
                        {req.review_needed_items}
                      </span>
                      <span className="text-muted-foreground">/</span>
                      <span className="text-red-700">
                        {req.no_match_items}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {formatDate(req.created_at)}
                  </TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      className="text-red-500 hover:text-red-700 h-8 w-8 p-0"
                      onClick={() => {
                        if (window.confirm("Удалить этот запрос со всеми результатами?")) {
                          deleteMutation.mutate(req.request_id);
                        }
                      }}
                      disabled={deleteMutation.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
