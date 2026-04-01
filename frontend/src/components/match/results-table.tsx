import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ChevronDown, ChevronRight } from "lucide-react";
import { getMatchItems, getItemCandidates } from "@/api/match";
import type { Candidate, MatchResult } from "@/api/types";
import { formatConfidence } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import StatusBadge from "./status-badge";
import ReviewActions from "@/components/review/review-actions";

interface ResultsTableProps {
  requestId: string;
}

const PAGE_SIZE = 20;

export default function ResultsTable({ requestId }: ResultsTableProps) {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  const itemsQuery = useQuery({
    queryKey: ["match-items", requestId, statusFilter, page],
    queryFn: () =>
      getMatchItems(requestId, {
        status: statusFilter === "all" ? undefined : statusFilter,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  const candidatesQuery = useQuery({
    queryKey: ["candidates", expandedRow],
    queryFn: () => getItemCandidates(expandedRow!),
    enabled: !!expandedRow,
  });

  const columns: ColumnDef<MatchResult>[] = [
    {
      id: "expand",
      header: "",
      size: 32,
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={() =>
            setExpandedRow(
              expandedRow === row.original.request_item_id
                ? null
                : row.original.request_item_id,
            )
          }
        >
          {expandedRow === row.original.request_item_id ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </Button>
      ),
    },
    {
      accessorKey: "line_id",
      header: "#",
      size: 50,
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground">
          {row.original.line_id ?? row.index + 1}
        </span>
      ),
    },
    {
      accessorKey: "raw_text",
      header: "Исходный текст",
      size: 300,
      cell: ({ row }) => (
        <div className="max-w-[300px]">
          <div className="truncate text-sm font-medium">
            {row.original.raw_text}
          </div>
          {row.original.normalized_text &&
            row.original.normalized_text !== row.original.raw_text && (
              <div className="truncate text-xs text-muted-foreground">
                {row.original.normalized_text}
              </div>
            )}
        </div>
      ),
    },
    {
      accessorKey: "status",
      header: "Статус",
      size: 100,
      cell: ({ row }) => <StatusBadge status={row.original.status} />,
    },
    {
      accessorKey: "confidence",
      header: "Уверенность",
      size: 90,
      cell: ({ row }) => (
        <span className="text-sm">{formatConfidence(row.original.confidence)}</span>
      ),
    },
    {
      id: "best_match",
      header: "Лучший результат",
      size: 250,
      cell: ({ row }) => {
        const best = row.original.best_candidate;
        if (!best) return <span className="text-sm text-muted-foreground">\u2014</span>;
        return (
          <div className="max-w-[250px]">
            <div className="truncate text-sm">{best.name}</div>
            {best.article && (
              <div className="text-xs text-muted-foreground">
                Арт: {best.article}
              </div>
            )}
          </div>
        );
      },
    },
    {
      id: "actions",
      header: "Действия",
      size: 200,
      cell: ({ row }) => (
        <ReviewActions
          item={row.original}
          onReviewed={() => itemsQuery.refetch()}
        />
      ),
    },
  ];

  const data = itemsQuery.data?.items ?? [];
  const totalPages = itemsQuery.data
    ? Math.ceil(itemsQuery.data.total / PAGE_SIZE)
    : 0;

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="space-y-4">
      <Tabs
        value={statusFilter}
        onValueChange={(val) => {
          setStatusFilter(val);
          setPage(1);
        }}
      >
        <TabsList>
          <TabsTrigger value="all">Все</TabsTrigger>
          <TabsTrigger value="auto_match">Найдено</TabsTrigger>
          <TabsTrigger value="review_needed">На проверку</TabsTrigger>
          <TabsTrigger value="no_match">Не найдено</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="rounded-md border border-border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id} style={{ width: header.getSize() }}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {itemsQuery.isLoading ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-center py-8">
                  <span className="text-muted-foreground">Загрузка...</span>
                </TableCell>
              </TableRow>
            ) : data.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="text-center py-8">
                  <span className="text-muted-foreground">Нет данных</span>
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => (
                <>
                  <TableRow key={row.id} className="hover:bg-muted/50">
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                  {expandedRow === row.original.request_item_id && (
                    <TableRow key={`${row.id}-expanded`}>
                      <TableCell colSpan={columns.length} className="bg-muted/30 p-4">
                        <CandidatesPanel
                          candidates={candidatesQuery.data?.candidates}
                          isLoading={candidatesQuery.isLoading}
                          reasons={row.original.reasons}
                          attributes={row.original.extracted_attributes}
                        />
                      </TableCell>
                    </TableRow>
                  )}
                </>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Страница {page} из {totalPages} (всего{" "}
            {itemsQuery.data?.total ?? 0})
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Назад
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Вперёд
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function CandidatesPanel({
  candidates,
  isLoading,
  reasons,
  attributes,
}: {
  candidates: Candidate[] | undefined;
  isLoading: boolean;
  reasons: string[];
  attributes: Record<string, unknown>;
}) {
  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Загрузка кандидатов...</div>;
  }

  return (
    <div className="space-y-3">
      {Object.keys(attributes).length > 0 && (
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-1">
            Извлечённые атрибуты:
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(attributes).map(([key, value]) => (
              <span
                key={key}
                className="rounded bg-muted px-2 py-0.5 text-xs"
              >
                {key}: {String(value)}
              </span>
            ))}
          </div>
        </div>
      )}

      {reasons.length > 0 && (
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-1">
            Причины:
          </div>
          <ul className="list-disc pl-4 text-xs text-muted-foreground">
            {reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {candidates && candidates.length > 0 && (
        <div>
          <div className="text-xs font-medium text-muted-foreground mb-1">
            Кандидаты ({candidates.length}):
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="pb-1 pr-3">#</th>
                <th className="pb-1 pr-3">Наименование</th>
                <th className="pb-1 pr-3">Артикул</th>
                <th className="pb-1 pr-3">Бренд</th>
                <th className="pb-1 pr-3">Итоговый балл</th>
                <th className="pb-1 pr-3">Причины</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((c, i) => (
                <tr key={c.product_id} className="border-b border-border/50">
                  <td className="py-1 pr-3 text-muted-foreground">{i + 1}</td>
                  <td className="py-1 pr-3">{c.name}</td>
                  <td className="py-1 pr-3">{c.article ?? "\u2014"}</td>
                  <td className="py-1 pr-3">{c.brand ?? "\u2014"}</td>
                  <td className="py-1 pr-3">
                    {c.final_score != null
                      ? `${Math.round(c.final_score * 100)}%`
                      : "\u2014"}
                  </td>
                  <td className="py-1 pr-3 text-muted-foreground">
                    {c.reasons.join(", ") || "\u2014"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(!candidates || candidates.length === 0) && !isLoading && (
        <div className="text-sm text-muted-foreground">Кандидатов нет</div>
      )}
    </div>
  );
}
