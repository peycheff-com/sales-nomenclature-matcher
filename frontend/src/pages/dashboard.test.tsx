import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React, { type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getCatalogStats } from "@/api/catalog";
import { getHealth } from "@/api/health";
import {
  listMatchRequests,
  matchBatch,
  parseFilePreview,
  parseFileStructured,
  previewGoogleSheet,
  smartUpload,
} from "@/api/match";
import { listSuppliers } from "@/api/suppliers";
import DashboardPage from "@/pages/dashboard";
import { toast } from "sonner";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  suppliers: {
    items: [{ supplier_id: "s1", supplier_name: "ACME", strict_mode: false, is_active: true }],
  },
  recent: {
    items: [
      {
        request_id: "recent-1",
        supplier_id: "s1",
        status: "done" as const,
        total_items: 2,
        processed_items: 2,
        auto_matched_items: 1,
        review_needed_items: 1,
        no_match_items: 0,
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
  },
  health: {
    status: "ok" as "ok" | "degraded",
    version: "test",
    checks: { providers: "ok", catalog: "ok", index: "ok", db: "ok", redis: "ok" },
  },
  queryLoading: new Set<string>(),
  mutationPending: false,
  catalogStats: {
    total_products: 10,
    embedded_products: 10,
    embedding_model: "local",
    embedding_coverage_pct: 100,
    onec_connected: false,
  },
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryKey, queryFn }: { queryKey: unknown[]; queryFn?: () => Promise<unknown> }) => {
    try {
      void queryFn?.().catch(() => undefined);
    } catch {
      // Component tests use inline query data below.
    }
    const dataByKey: Record<string, unknown> = {
      suppliers: mocks.suppliers,
      "match-requests": mocks.recent,
      health: mocks.health,
      "catalog-stats": mocks.catalogStats,
    };
    return {
      data: dataByKey[String(queryKey[0])],
      isLoading: mocks.queryLoading.has(String(queryKey[0])),
    };
  },
  useMutation: ({
    mutationFn,
    onSuccess,
    onError,
  }: {
    mutationFn: (input: unknown) => Promise<unknown>;
    onSuccess?: (data: unknown) => void;
    onError?: (error: Error, input?: unknown) => void;
  }) => ({
    isPending: mocks.mutationPending,
    mutate: async (input: unknown) => {
      try {
        const data = await mutationFn(input);
        onSuccess?.(data);
      } catch (error) {
        onError?.(error as Error, input);
      }
    },
  }),
}));

const TabsContext = React.createContext<((value: string) => void) | undefined>(undefined);

vi.mock("@/components/ui/tabs", async () => {
  const ReactModule = await import("react");
  return {
    Tabs: ({
      children,
      onValueChange,
    }: {
      children: ReactNode;
      value?: string;
      defaultValue?: string;
      onValueChange?: (value: string) => void;
    }) => (
      <TabsContext.Provider value={onValueChange}>
        <div>{children}</div>
      </TabsContext.Provider>
    ),
    TabsList: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    TabsTrigger: ({ children, value }: { children: ReactNode; value: string }) => {
      const onValueChange = ReactModule.useContext(TabsContext);
      return (
        <button type="button" onClick={() => onValueChange?.(value)}>
          {children}
        </button>
      );
    },
    TabsContent: ({ children }: { children: ReactNode; value: string }) => <section>{children}</section>,
  };
});

vi.mock("@/components/ui/select", () => ({
  Select: ({
    children,
    onValueChange,
  }: {
    children: ReactNode;
    value?: string;
    onValueChange?: (value: string) => void;
  }) => (
    <div>
      {children}
      {onValueChange && (
        <>
          <button type="button" onClick={() => onValueChange("s1")}>
            choose supplier
          </button>
          <button type="button" onClick={() => onValueChange("__all__")}>
            clear supplier
          </button>
          <button type="button" onClick={() => onValueChange(null as never)}>
            clear supplier null
          </button>
        </>
      )}
    </div>
  ),
  SelectContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: ReactNode }) => <button>{children}</button>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
}));

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  TooltipTrigger: ({ children, render }: { children?: ReactNode; render?: ReactNode }) => (
    <span>{render ?? children}</span>
  ),
  TooltipContent: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}));

vi.mock("@/components/ui/alert-dialog", () => ({
  AlertDialog: ({
    children,
    open,
    onOpenChange,
  }: {
    children: ReactNode;
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
  }) =>
    open ? (
      <div>
        {children}
        <button type="button" onClick={() => onOpenChange?.(false)}>
          close dialog
        </button>
      </div>
    ) : null,
  AlertDialogAction: ({
    children,
    onClick,
  }: {
    children: ReactNode;
    onClick?: () => void;
  }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));

vi.mock("@/components/features/requests-tab", () => ({
  RequestsTab: () => <div>Requests history tab</div>,
}));

vi.mock("@/api/match", () => ({
  matchBatch: vi.fn(),
  parseFilePreview: vi.fn(),
  parseFileStructured: vi.fn(),
  smartUpload: vi.fn(),
  listMatchRequests: vi.fn(),
  previewGoogleSheet: vi.fn(),
}));

vi.mock("@/api/catalog", () => ({
  getCatalogStats: vi.fn(),
}));

vi.mock("@/api/health", () => ({
  getHealth: vi.fn(),
}));

vi.mock("@/api/suppliers", () => ({
  listSuppliers: vi.fn(),
}));

vi.mock("sonner", () => {
  const toastFn = vi.fn();
  return {
    toast: Object.assign(toastFn, {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
    }),
  };
});

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mocks.queryLoading.clear();
    mocks.mutationPending = false;
    mocks.navigate.mockClear();
    mocks.health = {
      status: "ok" as const,
      version: "test",
      checks: { providers: "ok", catalog: "ok", index: "ok", db: "ok", redis: "ok" },
    };
    mocks.catalogStats = {
      total_products: 10,
      embedded_products: 10,
      embedding_model: "local",
      embedding_coverage_pct: 100,
      onec_connected: false,
    };
    vi.mocked(matchBatch).mockResolvedValue({ request_id: "req-new", status: "queued" });
    vi.mocked(parseFilePreview).mockResolvedValue({
      items: [
        { raw_text: "Pump A", line_id: "1" },
        { raw_text: "Pump A", line_id: "2" },
      ],
    });
    vi.mocked(parseFileStructured).mockResolvedValue({
      mode: "structured",
      supplier_items: [
        { raw_text: "Supplier pump", line_id: "1", original_row: { Name: "Supplier pump" } },
      ],
      catalog_items: [{ raw_text: "Catalog pump", unit: "pcs", price: 42 }],
      supplier_name: "Detected Supplier",
      tables_detected: 2,
    });
    vi.mocked(smartUpload).mockResolvedValue({ request_id: "req-smart", status: "queued" });
    vi.mocked(previewGoogleSheet).mockResolvedValue({
      rows: [{ "Номенклатура": "Sheet pump", "№": "7" }],
    });
    vi.mocked(listMatchRequests).mockResolvedValue(mocks.recent);
    vi.mocked(getCatalogStats).mockResolvedValue(mocks.catalogStats);
    vi.mocked(getHealth).mockResolvedValue(mocks.health);
    vi.mocked(listSuppliers).mockResolvedValue(mocks.suppliers);
    vi.mocked(toast).mockClear();
    vi.mocked(toast.success).mockClear();
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.warning).mockClear();
  });

  it("submits pasted text items and navigates to the created request", async () => {
    const user = userEvent.setup();
    render(<DashboardPage />);

    await user.click(screen.getByRole("button", { name: "Вставить текст" }));
    await user.type(
      screen.getByPlaceholderText("Введите наименования, каждое с новой строки..."),
      "Pump A\nValve B",
    );
    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(2 позиций\)/ }));

    await waitFor(() =>
      expect(matchBatch).toHaveBeenCalledWith({
        supplier_id: undefined,
        source_type: "text",
        items: [
          { raw_text: "Pump A", line_id: "1" },
          { raw_text: "Valve B", line_id: "2" },
        ],
      }),
    );
    expect(mocks.navigate).toHaveBeenCalledWith({
      to: "/requests/$requestId",
      params: { requestId: "req-new" },
    });
  });

  it("previews a Google Sheet, rejects invalid URLs, and submits sheet items", async () => {
    const user = userEvent.setup();
    render(<DashboardPage />);

    await user.click(screen.getByRole("button", { name: "Google Таблицы" }));
    await user.type(screen.getByPlaceholderText("https://docs.google.com/spreadsheets/d/..."), "https://bad");
    await user.click(screen.getByRole("button", { name: "Загрузить" }));
    expect(toast.error).toHaveBeenCalledWith(
      "Вставьте корректную ссылку на Google Таблицу (docs.google.com/spreadsheets/...)",
    );

    await user.clear(screen.getByPlaceholderText("https://docs.google.com/spreadsheets/d/..."));
    await user.type(
      screen.getByPlaceholderText("https://docs.google.com/spreadsheets/d/..."),
      "https://docs.google.com/spreadsheets/d/abc",
    );
    await user.click(screen.getByRole("button", { name: "Загрузить" }));

    await waitFor(() =>
      expect(previewGoogleSheet).toHaveBeenCalledWith("https://docs.google.com/spreadsheets/d/abc"),
    );
    expect(screen.getByDisplayValue("Sheet pump")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(1 позиций\)/ }));
    await waitFor(() =>
      expect(matchBatch).toHaveBeenCalledWith(
        expect.objectContaining({
          source_type: "google_sheet",
          items: [expect.objectContaining({ raw_text: "Sheet pump", line_id: "7" })],
        }),
      ),
    );
  });

  it("edits and removes Google Sheet preview rows before submitting", async () => {
    const user = userEvent.setup();
    vi.mocked(previewGoogleSheet).mockResolvedValueOnce({
      rows: [
        { raw_text: "Sheet pump", line_id: "row-a" },
        { raw_text: "Sheet valve", line_id: "row-b" },
      ],
    });
    render(<DashboardPage />);

    await user.click(screen.getByRole("button", { name: "Google Таблицы" }));
    await user.type(
      screen.getByPlaceholderText("https://docs.google.com/spreadsheets/d/..."),
      "https://docs.google.com/spreadsheets/d/edit",
    );
    await user.click(screen.getByRole("button", { name: "Загрузить" }));

    await waitFor(() => expect(screen.getByDisplayValue("Sheet pump")).toBeInTheDocument());
    const lineIdInput = screen.getByDisplayValue("row-a");
    const rawTextInput = screen.getByDisplayValue("Sheet pump");
    await user.clear(lineIdInput);
    await user.type(lineIdInput, "edited-row");
    await user.clear(rawTextInput);
    await user.type(rawTextInput, "Edited pump");
    await user.click(screen.getAllByRole("button", { name: "Удалить строку" })[0]);

    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(1 позиций\)/ }));

    await waitFor(() =>
      expect(matchBatch).toHaveBeenCalledWith(
        expect.objectContaining({
          source_type: "google_sheet",
          items: [{ raw_text: "Sheet valve", line_id: "row-b", original_row: expect.any(Object) }],
        }),
      ),
    );
  });

  it("parses a structured file and starts smart upload with detected supplier name", async () => {
    const user = userEvent.setup();
    const { container } = render(<DashboardPage />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(
      input,
      new File(["content"], "catalog.xlsx", {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
    );

    await waitFor(() => expect(parseFileStructured).toHaveBeenCalled());
    expect(screen.getByText("Программный анализ структуры")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Detected Supplier")).toBeInTheDocument();
    await user.clear(screen.getByDisplayValue("Detected Supplier"));
    await user.type(screen.getByPlaceholderText("Название поставщика"), "Edited Supplier");
    expect(screen.getByText("Supplier pump")).toBeInTheDocument();
    expect(screen.getByText("Catalog pump")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(1 позиций\)/ }));

    await waitFor(() =>
      expect(smartUpload).toHaveBeenCalledWith(expect.any(File), {
        supplierName: "Edited Supplier",
        supplierId: undefined,
      }),
    );
  });

  it("blocks submission when readiness checks are not green and opens recent requests", async () => {
    const user = userEvent.setup();
    mocks.health = {
      status: "degraded" as const,
      version: "test",
      checks: { providers: "fail", catalog: "ok", index: "ok", db: "ok", redis: "ok" },
    };
    mocks.catalogStats = {
      total_products: 10,
      embedded_products: 5,
      embedding_model: "local",
      embedding_coverage_pct: 50,
      onec_connected: false,
    };

    render(<DashboardPage />);

    expect(screen.getByText(/Загрузка новых прайс-листов заблокирована/)).toBeInTheDocument();
    expect(screen.getByText(/AI-провайдеры не готовы/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Начать сопоставление/ })).toBeDisabled();

    await user.click(screen.getByText("Готово").closest("button")!);
    expect(mocks.navigate).toHaveBeenCalledWith({
      to: "/requests/$requestId",
      params: { requestId: "recent-1" },
    });
  });

  it("shows empty recent request states", () => {
    mocks.health = undefined as never;
    mocks.catalogStats = undefined as never;
    mocks.recent = { items: [] };

    render(<DashboardPage />);

    expect(screen.getByText("Нет запросов")).toBeInTheDocument();
    expect(screen.getByText("Загрузите ваш первый прайс-лист для сопоставления.")).toBeInTheDocument();
  });

  it("handles basic file preview, duplicate confirmation, and row removal undo toast", async () => {
    const user = userEvent.setup();
    const { container } = render(<DashboardPage />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const dropZone = screen
      .getAllByRole("button", { name: "Загрузить файл" })
      .find((element) => element.tagName === "DIV");

    expect(dropZone).toBeTruthy();
    fireEvent.keyDown(dropZone!, { key: "Enter" });
    await user.upload(input, new File(["a,b"], "items.csv", { type: "text/csv" }));

    await waitFor(() => expect(parseFileStructured).toHaveBeenCalled());
    await user.click(screen.getByRole("switch"));
    await waitFor(() => expect(parseFilePreview).toHaveBeenCalled());
    expect(screen.getByText(/точных дубликатов/)).toBeInTheDocument();
    const previewInput = screen.getAllByDisplayValue("Pump A")[0];
    await user.clear(previewInput);
    await user.type(previewInput, "Edited preview pump");
    expect(screen.getByDisplayValue("Edited preview pump")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Удалить строку" })[0]);
    expect(toast).toHaveBeenCalledWith(
      "Строка удалена",
      expect.objectContaining({
        action: expect.objectContaining({ label: "Отменить" }),
      }),
    );
    const toastArgs = vi.mocked(toast).mock.calls.at(-1);
    const undo = toastArgs?.[1] as { action?: { onClick?: () => void } } | undefined;
    act(() => {
      undo?.action?.onClick?.();
    });
    expect(screen.getByDisplayValue("Edited preview pump")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Pump A")).toBeInTheDocument();
  });

  it("closes duplicate confirmation and rejects confirmed launch when readiness changes", async () => {
    const user = userEvent.setup();
    vi.mocked(matchBatch).mockClear();
    const { rerender } = render(<DashboardPage />);

    await user.click(screen.getByRole("button", { name: "Вставить текст" }));
    await user.type(
      screen.getByPlaceholderText("Введите наименования, каждое с новой строки..."),
      "Pump A\nPump A",
    );
    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(2 позиций\)/ }));
    expect(screen.getByText("Подтвердите отправку")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "close dialog" }));
    expect(screen.queryByText("Подтвердите отправку")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(2 позиций\)/ }));
    mocks.health = {
      status: "degraded" as const,
      version: "test",
      checks: { providers: "ok", catalog: "ok", index: "ok", db: "fail", redis: "fail" },
    };
    rerender(<DashboardPage />);
    await user.click(screen.getByRole("button", { name: "Продолжить" }));

    expect(toast.error).toHaveBeenCalledWith("Система ещё не готова к запуску новых запросов.");
    expect(matchBatch).not.toHaveBeenCalled();
  });

  it("shows internal dependency readiness blockers", () => {
    mocks.health = {
      status: "degraded" as const,
      version: "test",
      checks: { providers: "ok", catalog: "ok", index: "ok", db: "fail", redis: "ok" },
    };

    render(<DashboardPage />);

    expect(screen.getByText(/внутренние зависимости недоступны/)).toBeInTheDocument();
  });

  it("confirms duplicate text submissions before creating a request", async () => {
    const user = userEvent.setup();
    render(<DashboardPage />);

    await user.click(screen.getByRole("button", { name: "Вставить текст" }));
    await user.type(
      screen.getByPlaceholderText("Введите наименования, каждое с новой строки..."),
      "Pump A\nPump A",
    );
    vi.mocked(matchBatch).mockClear();
    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(2 позиций\)/ }));

    expect(screen.getByText("Подтвердите отправку")).toBeInTheDocument();
    expect(screen.getByText(/дублирующихся строк/)).toBeInTheDocument();
    expect(matchBatch).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Продолжить" }));

    await waitFor(() =>
      expect(matchBatch).toHaveBeenCalledWith({
        supplier_id: undefined,
        source_type: "text",
        items: [
          { raw_text: "Pump A", line_id: "1" },
          { raw_text: "Pump A", line_id: "2" },
        ],
      }),
    );
  });

  it("confirms recent resubmissions for the selected supplier", async () => {
    const user = userEvent.setup();
    mocks.recent = {
      items: [
        {
          request_id: "recent-resubmit",
          supplier_id: "s1",
          status: "done",
          total_items: 2,
          processed_items: 2,
          auto_matched_items: 2,
          review_needed_items: 0,
          no_match_items: 0,
          created_at: new Date().toISOString(),
        },
      ],
    };
    render(<DashboardPage />);

    await user.click(screen.getByRole("button", { name: "choose supplier" }));
    await user.click(screen.getByRole("button", { name: "Вставить текст" }));
    await user.type(
      screen.getByPlaceholderText("Введите наименования, каждое с новой строки..."),
      "Pump A\nValve B",
    );
    vi.mocked(matchBatch).mockClear();
    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(2 позиций\)/ }));

    expect(screen.getByText("Подтвердите отправку")).toBeInTheDocument();
    expect(screen.getByText(/уже отправляли запрос с таким же количеством позиций/)).toBeInTheDocument();
    expect(matchBatch).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Продолжить" }));

    await waitFor(() =>
      expect(matchBatch).toHaveBeenCalledWith({
        supplier_id: "s1",
        source_type: "text",
        items: [
          { raw_text: "Pump A", line_id: "1" },
          { raw_text: "Valve B", line_id: "2" },
        ],
      }),
    );
  });

  it("pastes text from clipboard and reports clipboard failures", async () => {
    const user = userEvent.setup();
    const readText = vi.fn().mockResolvedValue("Clipboard pump");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { readText },
    });
    const { rerender } = render(<DashboardPage />);

    await user.click(screen.getByRole("button", { name: "Вставить текст" }));
    await user.click(screen.getByRole("button", { name: /Вставить из буфера/ }));

    await waitFor(() => expect(readText).toHaveBeenCalledTimes(1));
    expect(screen.getByDisplayValue("Clipboard pump")).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalledWith("Текст вставлен из буфера обмена");

    readText.mockResolvedValueOnce("Second clipboard pump");
    await user.click(screen.getByRole("button", { name: /Вставить из буфера/ }));
    await waitFor(() => expect(readText).toHaveBeenCalledTimes(2));
    expect(screen.getByPlaceholderText("Введите наименования, каждое с новой строки...")).toHaveValue(
      "Clipboard pump\nSecond clipboard pump",
    );

    readText.mockRejectedValueOnce(new Error("denied"));
    rerender(<DashboardPage />);
    await user.click(screen.getByRole("button", { name: /Вставить из буфера/ }));
    expect(toast.error).toHaveBeenCalledWith("Не удалось получить доступ к буферу обмена");
  });

  it("validates selected files and renders request history tab", async () => {
    const user = userEvent.setup();
    const { container } = render(<DashboardPage />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    fireEvent.change(input, {
      target: { files: [new File(["pdf"], "items.pdf", { type: "application/pdf" })] },
    });
    expect(toast.error).toHaveBeenCalledWith("Поддерживаются только форматы .xlsx, .xls, .csv, .txt");

    fireEvent.change(input, {
      target: { files: [new File(["a,b"], "items.csv", { type: "application/octet-stream" })] },
    });
    expect(toast.warning).toHaveBeenCalledWith(
      "Формат файла может быть некорректным. Убедитесь, что это настоящий CSV/Excel файл.",
    );
    await waitFor(() => expect(parseFileStructured).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: "История запросов" }));
    expect(screen.getByText("Requests history tab")).toBeInTheDocument();
  });

  it("persists supplier selection and validates empty or oversized submissions", async () => {
    const user = userEvent.setup();
    const { container } = render(<DashboardPage />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.click(screen.getByRole("button", { name: "choose supplier" }));
    expect(localStorage.getItem("matcher_supplier_id")).toBe("s1");
    await user.click(screen.getByRole("button", { name: "clear supplier" }));
    expect(localStorage.getItem("matcher_supplier_id")).toBeNull();

    expect(screen.getByRole("button", { name: /Начать сопоставление/ })).toBeDisabled();
    const largeFile = new File(["large"], "huge.csv", { type: "text/csv" });
    Object.defineProperty(largeFile, "size", { value: 51 * 1024 * 1024 });
    fireEvent.change(input, {
      target: { files: [largeFile] },
    });
    expect(toast.error).toHaveBeenCalledWith("Файл превышает максимальный размер 50 МБ");

  });

  it("loads persisted suppliers, clears null selections, and shows catalog/index blockers", async () => {
    const user = userEvent.setup();
    localStorage.setItem("matcher_supplier_id", "s-persisted");
    mocks.health = {
      status: "degraded" as const,
      version: "test",
      checks: { providers: "ok", catalog: "fail", index: "fail", db: "ok", redis: "ok" },
    };
    mocks.catalogStats = {
      total_products: 0,
      embedded_products: 0,
      embedding_model: "local",
      embedding_coverage_pct: 0,
      onec_connected: false,
    };

    render(<DashboardPage />);

    expect(screen.getByText(/каталог пуст, поисковый индекс не готов/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "clear supplier null" }));
    expect(localStorage.getItem("matcher_supplier_id")).toBeNull();
  });

  it("renders pending upload, sheet, and match controls", async () => {
    const user = userEvent.setup();
    mocks.mutationPending = true;
    render(<DashboardPage />);

    await user.click(screen.getByRole("button", { name: "Вставить текст" }));
    await user.type(
      screen.getByPlaceholderText("Введите наименования, каждое с новой строки..."),
      "Pending pump",
    );
    expect(screen.getByRole("button", { name: /Отправка/ })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Google Таблицы" }));
    await user.type(
      screen.getByPlaceholderText("https://docs.google.com/spreadsheets/d/..."),
      "https://docs.google.com/spreadsheets/d/pending",
    );
    expect(screen.getByRole("button", { name: "Загрузить" })).toBeDisabled();

    mocks.mutationPending = false;
  });

  it("submits standard file previews with the uploaded file extension", async () => {
    const user = userEvent.setup();
    vi.mocked(matchBatch).mockClear();
    vi.mocked(parseFilePreview).mockResolvedValueOnce({
      items: [{ raw_text: "Preview pump", line_id: "1" }],
    });
    const { container } = render(<DashboardPage />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(input, new File(["name\nPreview pump"], "items.CSV", { type: "text/csv" }));
    await waitFor(() => expect(parseFileStructured).toHaveBeenCalled());
    await user.click(screen.getByRole("switch"));
    await waitFor(() => expect(screen.getByDisplayValue("Preview pump")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(1 позиций\)/ }));

    await waitFor(() =>
      expect(matchBatch).toHaveBeenCalledWith({
        supplier_id: undefined,
        source_type: "csv",
        items: [{ raw_text: "Preview pump", line_id: "1" }],
      }),
    );
  });

  it("parses uploaded files directly when AI structure detection is disabled", async () => {
    const user = userEvent.setup();
    const { container } = render(<DashboardPage />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(input, new File(["name\nFirst pump"], "first.csv", { type: "text/csv" }));
    await waitFor(() => expect(parseFileStructured).toHaveBeenCalled());
    await user.click(screen.getByRole("switch"));
    vi.mocked(parseFilePreview).mockClear();
    await user.upload(input, new File(["name\nBasic pump"], "basic.csv", { type: "text/csv" }));

    await waitFor(() =>
      expect(parseFilePreview).toHaveBeenCalledWith(expect.any(File), false),
    );
  });

  it("handles drag-and-drop uploads and long preview truncation", async () => {
    const user = userEvent.setup();
    vi.mocked(parseFilePreview).mockResolvedValueOnce({
      items: Array.from({ length: 55 }, (_, index) => ({
        raw_text: `Dropped item ${index + 1}`,
        line_id: String(index + 1),
      })),
    });

    render(<DashboardPage />);
    const dropZone = screen
      .getAllByRole("button", { name: "Загрузить файл" })
      .find((element) => element.tagName === "DIV");
    expect(dropZone).toBeTruthy();
    const droppedFile = new File(["a,b"], "dropped.csv", { type: "text/csv" });

    fireEvent.dragOver(dropZone!, { dataTransfer: { files: [droppedFile] } });
    expect(dropZone).toHaveClass("border-primary");
    fireEvent.dragLeave(dropZone!, { dataTransfer: { files: [droppedFile] } });
    expect(dropZone).not.toHaveClass("border-primary");
    fireEvent.drop(dropZone!, { dataTransfer: { files: [droppedFile] } });

    await waitFor(() => expect(parseFileStructured).toHaveBeenCalledWith(droppedFile));
    await user.click(screen.getByRole("switch"));
    await waitFor(() => expect(parseFilePreview).toHaveBeenCalledWith(droppedFile, false));
    await waitFor(() =>
      expect(screen.getByText("Показаны первые 50 из 55 позиций")).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: "Вставить текст" }));
    fireEvent.change(screen.getByPlaceholderText("Введите наименования, каждое с новой строки..."), {
      target: { value: Array.from({ length: 31 }, (_, index) => `Text item ${index + 1}`).join("\n") },
    });
    expect(screen.getByText("... и ещё 1 позиций")).toBeInTheDocument();
  });

  it("reports parse, structured fallback, Google Sheet, match, and smart upload errors", async () => {
    const user = userEvent.setup();
    vi.mocked(previewGoogleSheet).mockRejectedValueOnce(new Error("sheet denied"));
    vi.mocked(matchBatch).mockRejectedValueOnce(new Error("match offline"));
    vi.mocked(parseFileStructured).mockRejectedValueOnce(new Error("structure failed"));
    vi.mocked(parseFilePreview)
      .mockResolvedValueOnce({ items: [{ raw_text: "Fallback pump", line_id: "1" }] })
      .mockRejectedValueOnce(new Error("parse failed"));

    const { container } = render(<DashboardPage />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.click(screen.getByRole("button", { name: "Google Таблицы" }));
    fireEvent.change(screen.getByPlaceholderText("https://docs.google.com/spreadsheets/d/..."), {
      target: { value: "https://docs.google.com/spreadsheets/d/error" },
    });
    await user.click(screen.getByRole("button", { name: "Загрузить" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Ошибка при чтении Google Таблицы. sheet denied",
      ),
    );

    await user.click(screen.getByRole("button", { name: "Вставить текст" }));
    await user.type(screen.getByPlaceholderText("Введите наименования, каждое с новой строки..."), "Pump X");
    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(1 позиций\)/ }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при создании запроса: match offline"),
    );

    await user.upload(fileInput, new File(["a,b"], "fallback.csv", { type: "text/csv" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Ошибка структуры файла: structure failed. Переключаем на базовый режим...",
      ),
    );

    vi.mocked(parseFilePreview).mockReset();
    vi.mocked(parseFilePreview).mockRejectedValueOnce(new Error("parse failed"));
    await user.click(screen.getByRole("switch"));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при разборе файла: parse failed"),
    );
  });

  it("reports smart upload failures from structured files", async () => {
    const user = userEvent.setup();
    vi.mocked(parseFileStructured).mockResolvedValueOnce({
      mode: "structured",
      supplier_items: [{ raw_text: "Supplier smart", line_id: "1" }],
      catalog_items: [{ raw_text: "Catalog smart" }],
      supplier_name: "",
      tables_detected: 2,
    });
    vi.mocked(smartUpload).mockRejectedValueOnce(new Error("smart failed"));

    const { container } = render(<DashboardPage />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(fileInput, new File(["xlsx"], "smart.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }));
    await waitFor(() => expect(screen.getByText("Supplier smart")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(1 позиций\)/ }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при умной загрузке: smart failed"),
    );
  });

  it("extracts Google Sheet rows from fallback columns and displays unknown recent statuses", async () => {
    const user = userEvent.setup();
    mocks.recent = {
      items: [
        {
          request_id: "recent-custom",
          supplier_id: "s1",
          status: "paused" as never,
          total_items: 3,
          processed_items: 1,
          auto_matched_items: 0,
          review_needed_items: 1,
          no_match_items: 0,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    };
    vi.mocked(previewGoogleSheet).mockResolvedValueOnce({
      rows: [
        { "Номенклатура клиента": "Client item", id: "client-id" },
        { text: "Text item" },
        { name: "Name item" },
        { "наименование": "Lower item" },
        { "Наименование": "Upper item" },
        { code: 42, extra: "String fallback" },
        { code: 77 },
        {},
        { raw_text: "   " },
      ],
    });

    render(<DashboardPage />);

    expect(screen.getByText("paused")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Google Таблицы" }));
    await user.type(
      screen.getByPlaceholderText("https://docs.google.com/spreadsheets/d/..."),
      "https://docs.google.com/spreadsheets/d/fallbacks",
    );
    await user.click(screen.getByRole("button", { name: "Загрузить" }));

    await waitFor(() => expect(screen.getByDisplayValue("Client item")).toBeInTheDocument());
    expect(screen.getByDisplayValue("Text item")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Name item")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Lower item")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Upper item")).toBeInTheDocument();
    expect(screen.getByDisplayValue("String fallback")).toBeInTheDocument();
    expect(screen.getByDisplayValue("77")).toBeInTheDocument();
    expect(screen.getByDisplayValue("client-id")).toBeInTheDocument();
  });

  it("truncates long Google Sheet previews and marks duplicate rows", async () => {
    const user = userEvent.setup();
    vi.mocked(previewGoogleSheet).mockResolvedValueOnce({
      rows: Array.from({ length: 51 }, (_, index) => ({
        raw_text: index < 2 ? "Repeated sheet row" : `Sheet row ${index + 1}`,
        line_id: `sheet-${index + 1}`,
      })),
    });

    render(<DashboardPage />);

    await user.click(screen.getByRole("button", { name: "Google Таблицы" }));
    await user.type(
      screen.getByPlaceholderText("https://docs.google.com/spreadsheets/d/..."),
      "https://docs.google.com/spreadsheets/d/long",
    );
    await user.click(screen.getByRole("button", { name: "Загрузить" }));

    expect(await screen.findByText("... и ещё 1 строк")).toBeInTheDocument();
    expect(screen.getByText(/точных дубликатов выделены/)).toBeInTheDocument();
  });

  it("handles empty structured parse results and file events without files", async () => {
    const user = userEvent.setup();
    vi.mocked(parseFileStructured).mockResolvedValueOnce({
      mode: "structured",
      supplier_items: undefined as never,
      catalog_items: undefined as never,
      supplier_name: undefined as never,
      tables_detected: 0,
    });
    const { container } = render(<DashboardPage />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const dropZone = screen
      .getAllByRole("button", { name: "Загрузить файл" })
      .find((element) => element.tagName === "DIV")!;

    fireEvent.change(fileInput, { target: { files: [] } });
    fireEvent.drop(dropZone, { dataTransfer: { files: [] } });
    expect(parseFileStructured).not.toHaveBeenCalled();

    await user.upload(fileInput, new File(["xlsx"], "empty.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }));

    await waitFor(() => expect(parseFileStructured).toHaveBeenCalledTimes(1));
    expect(toast.success).toHaveBeenCalledWith("Обнаружено 0 таблиц: ");
    expect(screen.getByText("Программный анализ структуры")).toBeInTheDocument();
    expect(screen.getAllByText("0").length).toBeGreaterThanOrEqual(2);
  });

  it("renders structured duplicate rows and catalog fallbacks", async () => {
    const user = userEvent.setup();
    vi.mocked(parseFileStructured).mockResolvedValueOnce({
      mode: "structured",
      supplier_items: [
        { raw_text: "Repeated structured", line_id: undefined as never },
        { raw_text: "Repeated structured", line_id: "" },
      ],
      catalog_items: [
        { raw_text: undefined, unit: "", price: 0 },
      ],
      supplier_name: null as never,
      tables_detected: 2,
    });

    const { container } = render(<DashboardPage />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(fileInput, new File(["xlsx"], "structured-fallback.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }));

    await waitFor(() => expect(screen.getAllByText("Repeated structured")).toHaveLength(2));
    expect(screen.getAllByTitle("Дубликат").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByPlaceholderText("Название поставщика")).toHaveValue("");
  });

  it("uses fallback messages for non-Error mutation failures", async () => {
    const user = userEvent.setup();
    vi.mocked(previewGoogleSheet).mockRejectedValueOnce("sheet string failure");
    vi.mocked(matchBatch).mockRejectedValueOnce("match string failure");
    vi.mocked(parseFileStructured).mockRejectedValueOnce("structure string failure");
    vi.mocked(parseFilePreview).mockRejectedValueOnce("parse string failure");
    vi.mocked(smartUpload).mockRejectedValueOnce("smart string failure");

    const { container } = render(<DashboardPage />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.click(screen.getByRole("button", { name: "Google Таблицы" }));
    await user.type(
      screen.getByPlaceholderText("https://docs.google.com/spreadsheets/d/..."),
      "https://docs.google.com/spreadsheets/d/string-error",
    );
    await user.click(screen.getByRole("button", { name: "Загрузить" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при чтении Google Таблицы. "),
    );

    await user.click(screen.getByRole("button", { name: "Вставить текст" }));
    await user.type(screen.getByPlaceholderText("Введите наименования, каждое с новой строки..."), "Pump Y");
    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(1 позиций\)/ }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при создании запроса: Неизвестная ошибка"),
    );

    await user.upload(fileInput, new File(["xlsx"], "string-error.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Ошибка структуры файла: Неизвестная ошибка. Переключаем на базовый режим...",
      ),
    );

    await user.click(screen.getByRole("switch"));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при разборе файла: Проверьте формат."),
    );

  });

  it("uses fallback messages for non-Error smart upload failures", async () => {
    const user = userEvent.setup();
    vi.mocked(parseFileStructured).mockResolvedValueOnce({
      mode: "structured",
      supplier_items: [{ raw_text: "Smart row", line_id: "1" }],
      catalog_items: [{ raw_text: "Catalog row" }],
      supplier_name: "Smart Supplier",
      tables_detected: 2,
    });
    vi.mocked(smartUpload).mockRejectedValueOnce("smart string failure");
    const { container } = render(<DashboardPage />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;

    await user.upload(fileInput, new File(["xlsx"], "smart-string.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }));
    await waitFor(() => expect(screen.getByText("Smart row")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(1 позиций\)/ }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при умной загрузке: Неизвестная ошибка"),
    );
  });

  it("renders query fallbacks when recent requests and suppliers are absent", () => {
    mocks.recent = undefined as never;
    mocks.suppliers = undefined as never;

    render(<DashboardPage />);

    expect(screen.getAllByText("Все поставщики").length).toBeGreaterThan(0);
  });

  it("renders readiness loading and file-control fallback branches", async () => {
    const user = userEvent.setup();
    mocks.queryLoading.add("catalog-stats");
    mocks.catalogStats = undefined as never;

    render(<DashboardPage />);

    expect(screen.getByText(/идёт проверка готовности/)).toBeInTheDocument();

    fireEvent.keyDown(screen.getAllByRole("button", { name: "Загрузить файл" })[1], { key: "Escape" });

    await user.click(screen.getByRole("button", { name: "Google Таблицы" }));
    await user.type(
      screen.getByPlaceholderText("https://docs.google.com/spreadsheets/d/..."),
      "https://docs.google.com/spreadsheets/d/no-selected-file",
    );
    await user.click(screen.getByRole("button", { name: "Загрузить" }));
    await waitFor(() => expect(screen.getByDisplayValue("Sheet pump")).toBeInTheDocument());

    await user.click(screen.getByRole("switch"));
    expect(parseFilePreview).not.toHaveBeenCalled();
  });

  it("renders file preview rows with empty line id fallbacks", async () => {
    const user = userEvent.setup();
    vi.mocked(parseFilePreview).mockResolvedValueOnce({
      items: [{ raw_text: "No line id row", line_id: "" }],
    });

    const { container } = render(<DashboardPage />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, new File(["name\nNo line id row"], "no-line.csv", { type: "text/csv" }));

    await waitFor(() => expect(parseFileStructured).toHaveBeenCalled());
    await user.click(screen.getByRole("switch"));
    await waitFor(() => expect(screen.getByDisplayValue("No line id row")).toBeInTheDocument());
    expect(screen.getByText("Извлечено: 1 позиций")).toBeInTheDocument();
  });

  it("renders structured rows with missing raw text and basic parse loading state", async () => {
    const user = userEvent.setup();
    vi.mocked(parseFileStructured).mockResolvedValueOnce({
      mode: "structured",
      supplier_items: [{ line_id: "missing-name", original_row: { code: "A" } }],
      catalog_items: [],
      supplier_name: "",
      tables_detected: 1,
    });

    const { container, rerender } = render(<DashboardPage />);
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, new File(["xlsx"], "missing-name.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }));

    await waitFor(() => expect(screen.getByText("missing-name")).toBeInTheDocument());

    mocks.mutationPending = true;
    rerender(<DashboardPage />);
    await user.click(screen.getByRole("switch"));
    expect(screen.getByRole("status", { name: "Загрузка" })).toBeInTheDocument();
    mocks.mutationPending = false;
  });

  it("submits pasted text when recent request data is absent", async () => {
    const user = userEvent.setup();
    mocks.recent = undefined as never;

    render(<DashboardPage />);

    await user.click(screen.getByRole("button", { name: "Вставить текст" }));
    await user.type(
      screen.getByPlaceholderText("Введите наименования, каждое с новой строки..."),
      "Fresh pump",
    );
    await user.click(screen.getByRole("button", { name: /Начать сопоставление \(1 позиций\)/ }));

    await waitFor(() =>
      expect(matchBatch).toHaveBeenCalledWith({
        supplier_id: undefined,
        source_type: "text",
        items: [{ raw_text: "Fresh pump", line_id: "1" }],
      }),
    );
  });
});
