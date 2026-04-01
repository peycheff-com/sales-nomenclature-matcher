import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, Link, useNavigate } from "@tanstack/react-router";
import { ArrowLeft, FileSearch, Loader2, Trash2 } from "lucide-react";
import { getMatchRequest, deleteMatchRequest } from "@/api/match";
import { POLLING_INTERVAL } from "@/lib/constants";
import { formatDate } from "@/lib/format";
import StatsBar from "@/components/match/stats-bar";
import ResultsTable from "@/components/match/results-table";
import ExportButton from "@/components/export/export-button";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { QueryErrorBanner } from "@/components/ui/query-error-banner";
import { SkeletonCard, SkeletonTable } from "@/components/ui/skeleton";
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
import { PageLayout } from "@/components/layout/page-layout";

export default function ResultsPage() {
  const { requestId } = useParams({ from: "/auth/requests/$requestId" as never });
  const [showDelete, setShowDelete] = useState(false);

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
      <div className="space-y-6 py-6">
        <SkeletonCard />
        <SkeletonTable rows={5} columns={6} />
      </div>
    );
  }

  if (requestQuery.isError || !request) {
    return (
      <div className="space-y-4">
        {requestQuery.isError && (
          <QueryErrorBanner error={requestQuery.error} onRetry={() => requestQuery.refetch()} />
        )}
        <EmptyState
          icon={FileSearch}
          title="Запрос не найден"
          description="Запрос не существует или был удалён."
          variant={requestQuery.isError ? "error" : "empty"}
          onRetry={requestQuery.isError ? () => requestQuery.refetch() : undefined}
          action={
            <Link to="/requests">
              <Button variant="outline" size="sm">
                <ArrowLeft className="mr-1 h-4 w-4" />
                К списку запросов
              </Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <PageLayout
      title={`Запрос ${request.request_id}`}
      description={`Создан: ${formatDate(request.created_at)}${request.supplier_id ? ` | Поставщик: ${request.supplier_id}` : ""}`}
      actions={
        <div className="flex gap-2 items-center">
          <Link to="/requests">
            <Button variant="ghost" size="sm" aria-label="Назад к списку">
              <ArrowLeft className="mr-1 h-4 w-4" />
              Назад
            </Button>
          </Link>
          <Button
            variant="outline"
            size="sm"
            className="text-red-600 hover:text-red-700 hover:bg-red-50"
            aria-label="Удалить запрос"
            disabled={deleteMutation.isPending}
            onClick={() => setShowDelete(true)}
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
      }
    >

      {/* Stats bar */}
      <StatsBar request={request} />

      {/* Processing indicator */}
      {isProcessing && (
        <div role="status" className="flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
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
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          Обработка завершилась с ошибкой. Обратитесь к администратору.
        </div>
      )}

      <AlertDialog open={showDelete} onOpenChange={setShowDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Удалить запрос?</AlertDialogTitle>
            <AlertDialogDescription>
              Запрос <span className="font-mono">{request.request_id}</span> и все
              его результаты будут безвозвратно удалены.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>
              Отмена
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-700"
              disabled={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate(request.request_id)}
            >
              {deleteMutation.isPending ? "Удаление..." : "Удалить"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}
