import { useCallback, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import Papa from "papaparse";
import { getMatchItems } from "@/api/match";
import type { MatchResult } from "@/api/types";
import { STATUS_LABELS } from "@/lib/constants";
import { formatConfidence } from "@/lib/format";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface ExportButtonProps {
  requestId: string;
  totalItems: number;
}

export default function ExportButton({ requestId, totalItems }: ExportButtonProps) {
  const [exporting, setExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState("");

  const fetchAll = useCallback(async (): Promise<MatchResult[]> => {
    const allItems: MatchResult[] = [];
    let page = 1;
    const pageSize = 100;
    const totalPages = Math.ceil(totalItems / pageSize);
    while (allItems.length < totalItems) {
      setExportProgress(`стр. ${page} из ${totalPages}`);
      const resp = await getMatchItems(requestId, { page, page_size: pageSize });
      allItems.push(...resp.items);
      if (resp.items.length < pageSize) break;
      page++;
    }
    setExportProgress("");
    return allItems;
  }, [requestId, totalItems]);

  function toRows(items: MatchResult[]) {
    return items.map((item) => {
      const best = item.best_candidate;

      if (item.original_row && Object.keys(item.original_row).length > 0) {
        const row = { ...item.original_row };
        // Try to populate the specific template columns if they exist
        if ("Номенклатура.1" in row || "Товар 1С" in row) {
          const colName = "Номенклатура.1" in row ? "Номенклатура.1" : "Товар 1С";
          row[colName] = best?.name ?? "";
        } else {
          row["Найдено в 1С (Товар)"] = best?.name ?? "";
        }

        row["Найдено в 1С (ID)"] = best?.product_id ?? "";
        row["Найдено в 1С (Артикул)"] = best?.article ?? "";
        row["Найдено в 1С (Бренд)"] = best?.brand ?? "";
        row["Уверенность"] = formatConfidence(item.confidence);
        row["Статус"] = STATUS_LABELS[item.status] ?? item.status;
        row["Причины"] = item.reasons.join("; ");

        return row;
      }

      // Fallback
      return {
        "Строка": item.line_id ?? "",
        "Исходный текст": item.raw_text,
        "Нормализованный": item.normalized_text ?? "",
        "Статус": STATUS_LABELS[item.status] ?? item.status,
        "Уверенность": formatConfidence(item.confidence),
        "Найденный товар": best?.name ?? "",
        "Артикул": best?.article ?? "",
        "Бренд": best?.brand ?? "",
        "ID товара": best?.product_id ?? "",
        "Причины": item.reasons.join("; "),
      };
    });
  }

  async function handleExportCSV() {
    setExporting(true);
    try {
      const items = await fetchAll();
      const rows = toRows(items);
      const csv = Papa.unparse(rows);
      downloadFile(csv, `results-${requestId}.csv`, "text/csv");
    } finally {
      setExporting(false);
    }
  }

  async function handleExportXLSX() {
    setExporting(true);
    try {
      const items = await fetchAll();
      const rows = toRows(items);

      const { default: ExcelJS } = await import("exceljs");
      const wb = new ExcelJS.Workbook();
      const ws = wb.addWorksheet("Результаты");

      if (rows.length > 0) {
        const headers = Object.keys(rows[0]);
        ws.addRow(headers);
        for (const row of rows) {
          ws.addRow(headers.map((h) => row[h] ?? ""));
        }
      }

      const buffer = await wb.xlsx.writeBuffer();
      const blob = new Blob([buffer], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `results-${requestId}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={exporting}
        className="inline-flex items-center justify-center rounded-lg border border-input bg-background px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50"
      >
        {exporting ? (
          <>
            <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            Экспортируем... {exportProgress && <span className="ml-1 text-xs text-muted-foreground">({exportProgress})</span>}
          </>
        ) : (
          <>
            <Download className="mr-1.5 h-4 w-4" />
            Экспорт
          </>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onClick={handleExportCSV}>
          Экспорт всех результатов (CSV)
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleExportXLSX}>
          Экспорт всех результатов (XLSX)
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function downloadFile(content: string, filename: string, mimeType: string) {
  const blob = new Blob(["\uFEFF" + content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
