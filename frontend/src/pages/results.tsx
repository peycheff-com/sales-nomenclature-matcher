import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, Loader2, Trash2 } from "lucide-react";
import { getMatchRequest, deleteMatchRequest } from "@/api/match";
import { POLLING_INTERVAL } from "@/lib/constants";
import { formatDate } from "@/lib/format";
import StatsBar from "@/components/match/stats-bar";
import ResultsTable from "@/components/match/results-table";
import ExportButton from "@/components/export/export-button";
import { Button } from "@/components/ui/button";

export default function ResultsPage() {
  const { requestId } = useParams({ from: "/auth/requests/$requestId" as never });

  const requestQuery = useQuery({
    queryKey: ["match-request", requestId],
    queryFn: () => getMatchRequest(requestId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "queued" || status === "running") return POLLING_INTERVAL;
      return false;
    },
  });

  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const deleteMutation = useMutation({
    mutationFn: deleteMatchRequest,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["match-requests"] });
      navigate({ to: "/requests" });
    },
  });

  const request = requestQuery.data;
  const isProcessing =
    request?.status === "queued" || request?.status === "running";

  if (requestQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (requestQuery.isError || !request) {
    return (
      <div className="space-y-4">
        <div className="py-12 text-center text-sm text-muted-foreground">
          Запрос не найден
        </div>
        <div className="text-center">
          <Link to="/requests">
            <Button variant="outline" size="sm">
              <ArrowLeft className="mr-1 h-4 w-4" />
              К списку запросов
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/requests">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="mr-1 h-4 w-4" />
              Назад
            </Button>
          </Link>
          <div>
            <h1 className="text-lg font-semibold">
              Запрос {request.request_id}
            </h1>
            <p className="text-xs text-muted-foreground">
              Создан: {formatDate(request.created_at)}
              {request.supplier_id && ` | Поставщик: ${request.supplier_id}`}
            </p>
          </div>
        </div>

        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            className="text-red-600 hover:text-red-700 hover:bg-red-50"
            disabled={deleteMutation.isPending}
            onClick={() => {
              if (window.confirm("Вы действительно хотите безвозвратно удалить этот запрос?")) {
                deleteMutation.mutate(request.request_id);
              }
            }}
          >
            <Trash2 className="h-4 w-4 mr-2" />
            Удалить
          </Button>
          {request.status === "done" && (
            <ExportButton
              requestId={request.request_id}
              totalItems={request.total_items}
            />
          )}
        </div>
      </div>

      {/* Stats bar */}
      <StatsBar request={request} />

      {/* Processing indicator */}
      {isProcessing && (
        <div className="flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
          <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
          <span className="text-sm text-blue-800">
            {request.status === "queued"
              ? "Запрос в очереди на обработку..."
              : `Обрабатывается: ${request.processed_items} из ${request.total_items}...`}
          </span>
        </div>
      )}

      {/* Results table -- show when there are processed items or when done */}
      {(request.processed_items > 0 || request.status === "done") && (
        <ResultsTable requestId={request.request_id} />
      )}

      {/* Failed state */}
      {request.status === "failed" && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          Обработка завершилась с ошибкой. Обратитесь к администратору.
        </div>
      )}
    </div>
  );
}
