import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { reindexCatalog } from "@/api/catalog";
import { deleteMatchRequest, listMatchRequests } from "@/api/match";
import { getQualityMetrics, getTokenUsage } from "@/api/metrics";
import { listSuppliers } from "@/api/suppliers";
import { listUsers } from "@/api/users";
import { MetricsTab } from "@/components/features/metrics-tab";
import { RequestsTab } from "@/components/features/requests-tab";
import { toast } from "sonner";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  invalidateQueries: vi.fn(),
  refetch: vi.fn(),
  clipboardWrite: vi.fn(),
  queryError: null as Error | null,
  queryErrors: new Map<string, Error>(),
  queryLoading: new Set<string>(),
  mutationPending: false,
  metrics: {
    total_cases: 1200,
    top1_accuracy: 0.91,
    top3_recall: 0.97,
    review_acceptance_rate: 0.84,
  },
  tokenUsage: {
    period_days: 30,
    totals: {
      prompt_tokens: 1500,
      completion_tokens: 500,
      total_tokens: 2000,
      total_cost_usd: 0.42,
      api_calls: 20,
    },
    by_provider: [{ provider: "local", total_tokens: 2000, cost_usd: 0, calls: 20 }],
    by_model: [
      {
        provider: "local",
        model: "bge-small",
        operation: "embedding",
        prompt_tokens: 1500,
        completion_tokens: 0,
        total_tokens: 1500,
        cost_usd: 0,
        calls: 10,
      },
    ],
    daily: [{ date: "2026-01-01", total_tokens: 2000, cost_usd: 0 }],
  },
  users: {
    items: [
      {
        user_id: "u1",
        username: "admin",
        full_name: "Admin",
        role: "admin",
        is_active: true,
        must_change_password: false,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        user_id: "u2",
        username: "operator",
        full_name: "Operator",
        role: "operator",
        is_active: true,
        must_change_password: false,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        user_id: "u3",
        username: "viewer",
        full_name: "Viewer",
        role: "viewer",
        is_active: true,
        must_change_password: false,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
  },
  suppliers: {
    items: [{ supplier_id: "s1", supplier_name: "ACME", strict_mode: false, is_active: true }],
  },
  health: { status: "ok", database: "connected", redis: "connected" },
  requests: {
    items: [
      {
        request_id: "req-alpha-123",
        supplier_id: "s1",
        source_type: "csv",
        file_name: "alpha.csv",
        status: "done" as const,
        total_items: 10,
        processed_items: 10,
        auto_matched_items: 7,
        review_needed_items: 2,
        no_match_items: 1,
        created_at: "2026-01-02T12:00:00Z",
      },
      {
        request_id: "req-beta-456",
        supplier_id: undefined,
        source_type: "api",
        status: "failed" as const,
        total_items: 3,
        processed_items: 1,
        auto_matched_items: 0,
        review_needed_items: 0,
        no_match_items: 1,
        created_at: "2026-01-01T12:00:00Z",
      },
    ],
    total: 2,
  },
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
  useQuery: ({
    queryKey,
    queryFn,
    refetchInterval,
  }: {
    queryKey: unknown[];
    queryFn: () => Promise<unknown>;
    refetchInterval?: unknown | (() => unknown);
  }) => {
    const key = String(queryKey[0]);
    try {
      void queryFn().catch(() => undefined);
    } catch {
      // Some component queries use browser APIs that are replaced by inline mock data here.
    }
    if (typeof refetchInterval === "function") {
      refetchInterval();
    }
    const error = mocks.queryErrors.get(key) ?? (mocks.queryError && key === "match-requests" ? mocks.queryError : null);
    if (error) {
      return {
        isError: true,
        error,
        isLoading: false,
        refetch: mocks.refetch,
      };
    }
    const dataByKey: Record<string, unknown> = {
      suppliers: mocks.suppliers,
      "quality-metrics": mocks.metrics,
      health: mocks.health,
      "token-usage": mocks.tokenUsage,
      users: mocks.users,
      "match-requests": mocks.requests,
    };
    return {
      data: dataByKey[key],
      isLoading: mocks.queryLoading.has(key),
      isError: false,
      error: null,
      refetch: mocks.refetch,
    };
  },
  useMutation: ({
    mutationFn,
    onSuccess,
    onError,
  }: {
    mutationFn: (input?: unknown) => Promise<unknown>;
    onSuccess?: (data: unknown) => void;
    onError?: (error: Error) => void;
  }) => ({
    isPending: mocks.mutationPending,
    mutate: async (input?: unknown) => {
      try {
        const data = await mutationFn(input);
        onSuccess?.(data);
      } catch (error) {
        onError?.(error as Error);
      }
    },
  }),
}));

vi.mock("@/hooks/use-debounced-value", () => ({
  useDebouncedValue: <T,>(value: T) => value,
}));

vi.mock("@/api/catalog", () => ({
  reindexCatalog: vi.fn(),
}));

vi.mock("@/api/match", () => ({
  listMatchRequests: vi.fn(),
  deleteMatchRequest: vi.fn(),
}));

vi.mock("@/api/metrics", () => ({
  getQualityMetrics: vi.fn(),
  getTokenUsage: vi.fn(),
}));

vi.mock("@/api/suppliers", () => ({
  listSuppliers: vi.fn(),
}));

vi.mock("@/api/users", () => ({
  listUsers: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/components/ui/tabs", () => ({
  Tabs: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children }: { children: ReactNode; value: string }) => (
    <button type="button">{children}</button>
  ),
  TabsContent: ({ children }: { children: ReactNode; value: string }) => <section>{children}</section>,
}));

vi.mock("@/components/ui/select", () => ({
  Select: ({
    children,
    onValueChange,
  }: {
    children: ReactNode;
    onValueChange?: (value: string) => void;
  }) => (
    <div>
      {children}
      {onValueChange && (
        <>
          <button type="button" onClick={() => onValueChange("s1")}>
            select s1
          </button>
          <button type="button" onClick={() => onValueChange("done")}>
            select done
          </button>
          <button type="button" onClick={() => onValueChange("7d")}>
            select 7d
          </button>
          <button type="button" onClick={() => onValueChange("today")}>
            select today
          </button>
          <button type="button" onClick={() => onValueChange("3d")}>
            select 3d
          </button>
          <button type="button" onClick={() => onValueChange("30d")}>
            select 30d
          </button>
          <button type="button" onClick={() => onValueChange("__all__")}>
            select all
          </button>
          <button type="button" onClick={() => onValueChange("")}>
            select blank
          </button>
        </>
      )}
    </div>
  ),
  SelectContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: ReactNode; value: string }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: ReactNode }) => <button type="button">{children}</button>,
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

describe("feature tabs", () => {
  beforeEach(() => {
    vi.mocked(reindexCatalog).mockReset();
    vi.mocked(deleteMatchRequest).mockReset();
    vi.mocked(listMatchRequests).mockReset();
    vi.mocked(getQualityMetrics).mockReset();
    vi.mocked(getTokenUsage).mockReset();
    vi.mocked(listSuppliers).mockReset();
    vi.mocked(listUsers).mockReset();
    mocks.navigate.mockClear();
    mocks.invalidateQueries.mockClear();
    mocks.refetch.mockClear();
    mocks.queryError = null;
    mocks.queryErrors.clear();
    mocks.queryLoading.clear();
    mocks.mutationPending = false;
    mocks.metrics = {
      total_cases: 1200,
      top1_accuracy: 0.91,
      top3_recall: 0.97,
      review_acceptance_rate: 0.84,
    };
    mocks.tokenUsage = {
      period_days: 30,
      totals: {
        prompt_tokens: 1500,
        completion_tokens: 500,
        total_tokens: 2000,
        total_cost_usd: 0.42,
        api_calls: 20,
      },
      by_provider: [{ provider: "local", total_tokens: 2000, cost_usd: 0, calls: 20 }],
      by_model: [
        {
          provider: "local",
          model: "bge-small",
          operation: "embedding",
          prompt_tokens: 1500,
          completion_tokens: 0,
          total_tokens: 1500,
          cost_usd: 0,
          calls: 10,
        },
      ],
      daily: [{ date: "2026-01-01", total_tokens: 2000, cost_usd: 0 }],
    };
    mocks.suppliers = {
      items: [{ supplier_id: "s1", supplier_name: "ACME", strict_mode: false, is_active: true }],
    };
    mocks.users = {
      items: [
        {
          user_id: "u1",
          username: "admin",
          full_name: "Admin",
          role: "admin",
          is_active: true,
          must_change_password: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          user_id: "u2",
          username: "operator",
          full_name: "Operator",
          role: "operator",
          is_active: true,
          must_change_password: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
        {
          user_id: "u3",
          username: "viewer",
          full_name: "Viewer",
          role: "viewer",
          is_active: true,
          must_change_password: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    };
    mocks.health = { status: "ok", database: "connected", redis: "connected" };
    mocks.requests = {
      items: [
        {
          request_id: "req-alpha-123",
          supplier_id: "s1",
          source_type: "csv",
          file_name: "alpha.csv",
          status: "done" as const,
          total_items: 10,
          processed_items: 10,
          auto_matched_items: 7,
          review_needed_items: 2,
          no_match_items: 1,
          created_at: "2026-01-02T12:00:00Z",
        },
        {
          request_id: "req-beta-456",
          supplier_id: undefined,
          source_type: "api",
          status: "failed" as const,
          total_items: 3,
          processed_items: 1,
          auto_matched_items: 0,
          review_needed_items: 0,
          no_match_items: 1,
          created_at: "2026-01-01T12:00:00Z",
        },
      ],
      total: 2,
    };
    vi.mocked(reindexCatalog).mockResolvedValue({ job_id: "job-1" });
    vi.mocked(deleteMatchRequest).mockResolvedValue({ ok: true });
    vi.mocked(listMatchRequests).mockResolvedValue(mocks.requests);
    vi.mocked(getQualityMetrics).mockResolvedValue(mocks.metrics);
    vi.mocked(getTokenUsage).mockResolvedValue(mocks.tokenUsage);
    vi.mocked(listSuppliers).mockResolvedValue(mocks.suppliers);
    vi.mocked(listUsers).mockResolvedValue(mocks.users);
    vi.mocked(toast.success).mockClear();
    vi.mocked(toast.error).mockClear();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        json: vi.fn().mockResolvedValue(mocks.health),
      }),
    );
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mocks.clipboardWrite },
    });
    Object.defineProperty(navigator.clipboard, "writeText", {
      configurable: true,
      value: mocks.clipboardWrite,
    });
    mocks.clipboardWrite.mockClear();
  });

  it("renders metrics, system status, token usage, access counts, and starts reindexing", async () => {
    const user = userEvent.setup();
    render(<MetricsTab />);

    expect(screen.getByText("Метрики и Администрирование")).toBeInTheDocument();
    expect(screen.getAllByText("1,200").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("91.0%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("97.0%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("84.0%").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Подключена")).toBeInTheDocument();
    expect(screen.getByText("Подключён")).toBeInTheDocument();
    expect(screen.getByText("2,000")).toBeInTheDocument();
    expect(screen.getByText("$0.4200")).toBeInTheDocument();
    expect(screen.getByText("bge-small")).toBeInTheDocument();
    expect(screen.getByText("Всего пользователей")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Запустить/ }));

    await waitFor(() => expect(reindexCatalog).toHaveBeenCalledTimes(1));
    expect(toast.success).toHaveBeenCalledWith("Переиндексация запущена");
  });

  it("updates metrics filters from supplier and category controls", async () => {
    const user = userEvent.setup();
    render(<MetricsTab />);

    await user.click(screen.getAllByRole("button", { name: "select s1" })[0]);
    await user.click(screen.getAllByRole("button", { name: "select blank" })[0]);
    await user.type(screen.getByPlaceholderText("Категория..."), "Pumps");

    expect(screen.getByDisplayValue("Pumps")).toBeInTheDocument();
  });

  it("renders metrics fallbacks when optional payloads are absent", async () => {
    const user = userEvent.setup();
    mocks.metrics = undefined as never;
    mocks.suppliers = undefined as never;
    mocks.users = undefined as never;
    mocks.tokenUsage = undefined as never;
    vi.mocked(reindexCatalog).mockRejectedValueOnce("queue string failure");

    render(<MetricsTab />);

    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
    expect(screen.getAllByText("Нет данных").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText("Всего пользователей")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Запустить/ }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Ошибка при запуске переиндексации: Неизвестная ошибка",
      ),
    );
  });

  it("renders partial metric payloads with zeroed chart values", () => {
    mocks.metrics = {
      total_cases: undefined as never,
      top1_accuracy: undefined as never,
      top3_recall: undefined as never,
      review_acceptance_rate: undefined as never,
    };

    render(<MetricsTab />);

    expect(screen.getAllByText("0.0%").length).toBeGreaterThanOrEqual(6);
    expect(screen.getByText("Всего обработано")).toBeInTheDocument();
  });

  it("renders degraded metrics and empty token usage branches", async () => {
    const user = userEvent.setup();
    mocks.metrics = {
      total_cases: 0,
      top1_accuracy: 0,
      top3_recall: 0,
      review_acceptance_rate: 0,
    };
    mocks.tokenUsage = {
      period_days: 30,
      totals: {
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0,
        total_cost_usd: 0,
        api_calls: 0,
      },
      by_provider: [],
      by_model: [],
      daily: [],
    };
    mocks.health = { status: "degraded", database: "down", redis: "down" };

    render(<MetricsTab />);

    expect(screen.getByText("Недоступна")).toBeInTheDocument();
    expect(screen.getByText("Недоступен")).toBeInTheDocument();
    expect(screen.getAllByText("Нет данных").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("$0.0000")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "7 дн." }));
    expect(screen.getByText("за 7 дн.")).toBeInTheDocument();
  });

  it("renders metrics loading and error states and reports reindex failures", async () => {
    const user = userEvent.setup();
    mocks.queryLoading.add("quality-metrics");
    mocks.queryLoading.add("health");
    mocks.queryLoading.add("token-usage");
    mocks.queryLoading.add("users");
    vi.mocked(reindexCatalog).mockRejectedValueOnce(new Error("queue offline"));

    const { rerender } = render(<MetricsTab />);

    expect(screen.getAllByRole("status", { name: "Загрузка" }).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: /Запустить/ }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Ошибка при запуске переиндексации: queue offline",
      ),
    );

    mocks.queryLoading.clear();
    mocks.queryErrors.set("quality-metrics", new Error("metrics unavailable"));
    mocks.queryErrors.set("token-usage", new Error("tokens unavailable"));
    mocks.queryErrors.set("health", new Error("health unavailable"));
    rerender(<MetricsTab />);

    expect(screen.getByText("metrics unavailable")).toBeInTheDocument();
    expect(screen.getByText("tokens unavailable")).toBeInTheDocument();
    expect(screen.getByText("Не удалось получить статус")).toBeInTheDocument();
    for (const retryButton of screen.getAllByRole("button", { name: "Повторить" })) {
      await user.click(retryButton);
    }
    expect(mocks.refetch).toHaveBeenCalledTimes(2);
  });

  it("renders requests, supports search/copy/navigation, and deletes a request", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup();
    try {
      render(<RequestsTab />);

      expect(screen.getByText("req-alph")).toBeInTheDocument();
      expect(screen.getAllByText("ACME").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("alpha.csv")).toBeInTheDocument();
      expect(screen.getByText("Готово")).toBeInTheDocument();

      await user.type(screen.getByPlaceholderText("Поиск по ID запроса..."), "beta");
      expect(screen.queryByText("req-alph")).not.toBeInTheDocument();
      expect(screen.getByText("req-beta")).toBeInTheDocument();

      Object.defineProperty(navigator.clipboard, "writeText", {
        configurable: true,
        value: mocks.clipboardWrite,
      });
      fireEvent.click(screen.getByRole("button", { name: "Копировать ID" }));
      expect(mocks.clipboardWrite).toHaveBeenCalledWith("req-beta-456");
      act(() => {
        vi.advanceTimersByTime(2_000);
      });

      await user.click(screen.getByText("req-beta"));
      expect(mocks.navigate).toHaveBeenCalledWith({
        to: "/requests/$requestId",
        params: { requestId: "req-beta-456" },
      });

      await user.click(screen.getByRole("button", { name: "Удалить запрос" }));
      expect(screen.getByText("Удалить запрос?")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Удалить" }));

      await waitFor(() => expect(deleteMatchRequest).toHaveBeenCalledWith("req-beta-456"));
      expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["match-requests"] });
      expect(toast.success).toHaveBeenCalledWith("Запрос успешно удален");
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders request fallback labels for unknown status and source-only rows", () => {
    mocks.requests = {
      items: [
        {
          request_id: "req-known-111",
          supplier_id: "s1",
          source_type: "api",
          file_name: "known.csv",
          status: "done" as const,
          total_items: 1,
          processed_items: 1,
          auto_matched_items: 1,
          review_needed_items: 0,
          no_match_items: 0,
          created_at: "2026-01-03T12:00:00Z",
        },
        {
          request_id: "req-weird-999",
          supplier_id: undefined,
          source_type: "manual",
          status: "paused" as never,
          total_items: 6,
          processed_items: 2,
          auto_matched_items: 1,
          review_needed_items: 1,
          no_match_items: 0,
          created_at: "2026-01-04T12:00:00Z",
        },
      ],
      total: 1,
    };

    render(<RequestsTab />);

    expect(screen.getByText("req-weir")).toBeInTheDocument();
    expect(screen.getByText("manual")).toBeInTheDocument();
    expect(screen.getByText("paused")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("columnheader", { name: /Статус/ }));
    expect(screen.getByText("req-weir")).toBeInTheDocument();
  });

  it("sorts request statuses when the second row has an unknown status", () => {
    mocks.requests = {
      items: [
        {
          request_id: "req-weird-999",
          supplier_id: undefined,
          source_type: "manual",
          status: "paused" as never,
          total_items: 6,
          processed_items: 2,
          auto_matched_items: 1,
          review_needed_items: 1,
          no_match_items: 0,
          created_at: "2026-01-04T12:00:00Z",
        },
        {
          request_id: "req-known-111",
          supplier_id: "s1",
          source_type: "api",
          file_name: "known.csv",
          status: "done" as const,
          total_items: 1,
          processed_items: 1,
          auto_matched_items: 1,
          review_needed_items: 0,
          no_match_items: 0,
          created_at: "2026-01-03T12:00:00Z",
        },
      ],
      total: 2,
    };

    render(<RequestsTab />);

    fireEvent.click(screen.getByRole("columnheader", { name: /Статус/ }));
    expect(screen.getByText("req-weir")).toBeInTheDocument();
  });

  it("renders request supplier fallbacks while supplier data is absent", () => {
    mocks.suppliers = undefined as never;

    render(<RequestsTab />);

    expect(screen.getByText("s1")).toBeInTheDocument();
    expect(screen.getByText("req-alph")).toBeInTheDocument();
  });

  it("sorts and bulk deletes selected requests", async () => {
    const user = userEvent.setup();
    render(<RequestsTab />);

    await user.click(screen.getByRole("columnheader", { name: /Статус/ }));
    expect(screen.getByText("req-beta")).toBeInTheDocument();
    await user.click(screen.getByRole("columnheader", { name: /Статус/ }));
    await user.click(screen.getByRole("columnheader", { name: /Статус/ }));
    await user.click(screen.getByRole("columnheader", { name: /Всего/ }));
    await user.click(screen.getByRole("columnheader", { name: /Создан/ }));

    await user.click(screen.getByRole("checkbox", { name: "Выбрать запрос req-alph" }));
    expect(screen.getByText("Удалить выбранные (1)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Снять выделение" }));
    expect(screen.queryByText("Удалить выбранные (1)")).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Выбрать все" }));
    expect(screen.getByText("Выбрано:")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Выбрать все" }));
    expect(screen.queryByText("Удалить выбранные (2)")).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Выбрать все" }));
    await user.click(screen.getByRole("button", { name: "Удалить выбранные (2)" }));
    expect(screen.getByText("Удалить выбранные запросы?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Удалить (2)" }));

    await waitFor(() => {
      expect(deleteMatchRequest).toHaveBeenCalledWith("req-beta-456");
      expect(deleteMatchRequest).toHaveBeenCalledWith("req-alpha-123");
    });
    expect(toast.success).toHaveBeenCalledWith("Удалено запросов: 2");
  });

  it("shows request loading skeletons", () => {
    mocks.queryLoading.add("match-requests");

    render(<RequestsTab />);

    expect(screen.getByRole("status", { name: "Загрузка таблицы" })).toBeInTheDocument();
  });

  it("applies request query filters and closes confirmation dialogs", async () => {
    const user = userEvent.setup();
    render(<RequestsTab />);

    await user.click(screen.getAllByRole("button", { name: "select done" })[0]);
    await waitFor(() =>
      expect(listMatchRequests).toHaveBeenCalledWith(
        expect.objectContaining({ status: "done", created_after: undefined }),
      ),
    );

    await user.click(screen.getAllByRole("button", { name: "select s1" })[1]);
    await waitFor(() =>
      expect(listMatchRequests).toHaveBeenCalledWith(
        expect.objectContaining({ status: "done", supplier_id: "s1" }),
      ),
    );

    await user.click(screen.getAllByRole("button", { name: "select today" })[2]);
    await waitFor(() =>
      expect(listMatchRequests).toHaveBeenCalledWith(
        expect.objectContaining({ created_after: expect.any(String) }),
      ),
    );
    await user.click(screen.getAllByRole("button", { name: "select 3d" })[2]);
    await user.click(screen.getAllByRole("button", { name: "select 7d" })[2]);
    await user.click(screen.getAllByRole("button", { name: "select 30d" })[2]);
    await user.click(screen.getAllByRole("button", { name: "select blank" })[0]);
    await user.click(screen.getAllByRole("button", { name: "select blank" })[1]);
    await user.click(screen.getAllByRole("button", { name: "select blank" })[2]);

    await user.click(screen.getAllByRole("button", { name: "Удалить запрос" })[0]);
    expect(screen.getByText("Удалить запрос?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "close dialog" }));
    expect(screen.queryByText("Удалить запрос?")).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Выбрать все" }));
    await user.click(screen.getByRole("button", { name: "Удалить выбранные (2)" }));
    expect(screen.getByText("Удалить выбранные запросы?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "close dialog" }));
    expect(screen.queryByText("Удалить выбранные запросы?")).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Выбрать запрос req-alph" }));
    expect(screen.getByText("Удалить выбранные (1)")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Выбрать запрос req-alph" }));
    expect(screen.queryByText("Удалить выбранные (1)")).not.toBeInTheDocument();
  });

  it("does not poll requests while the document is hidden", () => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });

    render(<RequestsTab />);

    expect(screen.getByText("req-alph")).toBeInTheDocument();

    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
  });

  it("shows filtered no-results and reports bulk delete failures", async () => {
    const user = userEvent.setup();
    vi.mocked(deleteMatchRequest).mockRejectedValueOnce(new Error("delete failed"));
    render(<RequestsTab />);

    await user.type(screen.getByPlaceholderText("Поиск по ID запроса..."), "missing");
    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
    expect(screen.getByText("Попробуйте изменить параметры фильтрации")).toBeInTheDocument();

    await user.clear(screen.getByPlaceholderText("Поиск по ID запроса..."));
    await user.click(screen.getByRole("checkbox", { name: "Выбрать все" }));
    await user.click(screen.getByRole("button", { name: "Удалить выбранные (2)" }));
    await user.click(screen.getByRole("button", { name: "Удалить (2)" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Не удалось удалить некоторые запросы: delete failed",
      ),
    );
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["match-requests"] });
  });

  it("reports fallback messages for non-error request delete failures", async () => {
    const user = userEvent.setup();
    render(<RequestsTab />);

    vi.mocked(deleteMatchRequest).mockRejectedValueOnce("single delete string failure");
    await user.click(screen.getAllByRole("button", { name: "Удалить запрос" })[0]);
    await user.click(screen.getByRole("button", { name: "Удалить" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Не удалось удалить запрос: Неизвестная ошибка"),
    );

    vi.mocked(deleteMatchRequest).mockRejectedValueOnce("bulk delete string failure");
    await user.click(screen.getByRole("checkbox", { name: "Выбрать все" }));
    await user.click(screen.getByRole("button", { name: "Удалить выбранные (2)" }));
    await user.click(screen.getByRole("button", { name: "Удалить (2)" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Не удалось удалить некоторые запросы: Неизвестная ошибка",
      ),
    );
  });

  it("renders pending request delete actions", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<RequestsTab />);

    await user.click(screen.getAllByRole("button", { name: "Удалить запрос" })[0]);
    mocks.mutationPending = true;
    rerender(<RequestsTab />);
    expect(screen.getByRole("button", { name: "Удаление..." })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "close dialog" }));
    mocks.mutationPending = false;
    rerender(<RequestsTab />);
    await user.click(screen.getByRole("checkbox", { name: "Выбрать все" }));
    await user.click(screen.getByRole("button", { name: "Удалить выбранные (2)" }));
    mocks.mutationPending = true;
    rerender(<RequestsTab />);
    expect(screen.getByRole("button", { name: "Удаление..." })).toBeInTheDocument();

    mocks.mutationPending = false;
  });

  it("shows empty requests and reports single delete failures", async () => {
    const user = userEvent.setup();
    mocks.requests = { items: [], total: 0 };
    const { rerender } = render(<RequestsTab />);

    expect(screen.getByText("Нет запросов")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Загрузить данные" }));
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/" });

    mocks.requests = {
      items: [
        {
          request_id: "req-error-789",
          supplier_id: "missing-supplier",
          source_type: "api",
          file_name: "fallback.csv",
          status: "done",
          total_items: 4,
          processed_items: 0,
          auto_matched_items: 0,
          review_needed_items: 0,
          no_match_items: 0,
          created_at: "2026-01-03T12:00:00Z",
        },
      ],
      total: 1,
    };
    vi.mocked(deleteMatchRequest).mockRejectedValueOnce(new Error("single failed"));
    rerender(<RequestsTab />);

    expect(screen.getByText("missing-supplier")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Удалить запрос" }));
    await user.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Не удалось удалить запрос: single failed"),
    );
  });

  it("shows request errors through the shared query error banner", () => {
    mocks.queryError = new Error("network down");

    render(<RequestsTab />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("network down")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(mocks.refetch).toHaveBeenCalled();
  });
});
