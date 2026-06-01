import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getItemCandidates, getMatchItems } from "@/api/match";
import { reviewBatch, reviewItem } from "@/api/review";
import type { Candidate, MatchItemsPage, MatchResult, ReviewInput } from "@/api/types";
import ResultsTable from "@/components/match/results-table";
import { toast } from "sonner";

const mocks = vi.hoisted(() => ({
  matchItems: null as MatchItemsPage | null,
  matchItemsByPage: null as Record<number, MatchItemsPage> | null,
  candidates: null as { candidates: Candidate[] } | null,
  itemsLoading: false,
  candidatesLoading: false,
  setQueryData: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({
    setQueryData: mocks.setQueryData,
  }),
  useQuery: ({
    queryKey,
    queryFn,
  }: {
    queryKey: unknown[];
    queryFn: () => Promise<unknown>;
    enabled?: boolean;
  }) => {
    try {
      const result = queryFn();
      void result?.catch?.(() => undefined);
    } catch {
      // Component tests use inline query data below.
    }
    if (queryKey[0] === "match-items") {
      const page = Number(queryKey[3] ?? 1);
      return {
        data: mocks.matchItemsByPage?.[page] ?? mocks.matchItems,
        isLoading: mocks.itemsLoading,
      };
    }
    if (queryKey[0] === "candidates") {
      return {
        data: mocks.candidates,
        isLoading: mocks.candidatesLoading,
      };
    }
    return { data: undefined, isLoading: false };
  },
  useMutation: ({
    mutationFn,
    onSuccess,
    onError,
  }: {
    mutationFn: (input: unknown) => Promise<unknown>;
    onSuccess?: (data: unknown) => void;
    onError?: (error: Error) => void;
  }) => ({
    isPending: false,
    mutate: async (input: unknown) => {
      try {
        const data = await mutationFn(input);
        onSuccess?.(data);
      } catch (error) {
        onError?.(error as Error);
      }
    },
  }),
}));

vi.mock("@/api/match", () => ({
  getMatchItems: vi.fn(),
  getItemCandidates: vi.fn(),
}));

vi.mock("@/api/review", () => ({
  reviewItem: vi.fn(),
  reviewBatch: vi.fn(),
}));

vi.mock("@/hooks/use-debounced-value", () => ({
  useDebouncedValue: <T,>(value: T) => value,
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock("@/components/review/review-actions", () => ({
  default: ({
    item,
    onReviewed,
  }: {
    item: MatchResult;
    onReviewed: (decision: string) => void;
  }) => (
    <button onClick={() => onReviewed("accepted")}>Mock review {item.request_item_id}</button>
  ),
}));

vi.mock("@/components/ui/tabs", () => ({
  Tabs: ({
    children,
    value,
    onValueChange,
  }: {
    children: ReactNode;
    value?: string;
    onValueChange?: (value: string) => void;
  }) => (
    <div data-current-value={value} data-testid={`tabs-${value ?? "none"}`}>
      {children}
      {onValueChange && (
        <>
          <button type="button" onClick={() => onValueChange("review_needed")}>
            set review needed
          </button>
          <button type="button" onClick={() => onValueChange("pending")}>
            set pending
          </button>
          <button type="button" onClick={() => onValueChange("reviewed")}>
            set reviewed
          </button>
        </>
      )}
    </div>
  ),
  TabsList: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, value }: { children: ReactNode; value: string }) => (
    <button type="button" data-value={value}>
      {children}
    </button>
  ),
}));

function result(overrides: Partial<MatchResult> = {}): MatchResult {
  return {
    request_item_id: "item-1",
    line_id: "1",
    raw_text: "Grundfos pump raw",
    normalized_text: "grundfos pump",
    extracted_attributes: { brand: "Grundfos", article: "A-1" },
    status: "auto_match",
    confidence: 0.94,
    best_candidate: {
      product_id: "p-best",
      name: "Best pump",
      article: "A-1",
      brand: "Grundfos",
    },
    alternatives: [],
    reasons: ["brand_match", "article_match"],
    ...overrides,
  };
}

function candidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    product_id: "p-alt",
    name: "Alternative pump",
    article: "A-2",
    brand: "Grundfos",
    retrieval_rank: 1,
    lexical_score: 0.8,
    semantic_score: 0.7,
    rerank_score: 0.6,
    rules_score: 0.5,
    final_score: 0.88,
    reasons: ["candidate_reason"],
    ...overrides,
  };
}

describe("ResultsTable", () => {
  beforeEach(() => {
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 1,
      items: [result()],
    };
    mocks.matchItemsByPage = null;
    mocks.candidates = { candidates: [candidate()] };
    mocks.itemsLoading = false;
    mocks.candidatesLoading = false;
    mocks.setQueryData.mockReset();
    mocks.setQueryData.mockImplementation((_: unknown, updater: unknown) => {
      if (typeof updater === "function") {
        return updater(mocks.matchItems);
      }
      return updater;
    });
    vi.mocked(getMatchItems).mockReset();
    vi.mocked(getItemCandidates).mockReset();
    vi.mocked(reviewItem).mockResolvedValue({ ok: true });
    vi.mocked(reviewBatch).mockClear();
    vi.mocked(reviewBatch).mockResolvedValue({ ok: true, processed_count: 1 });
    vi.mocked(toast.success).mockClear();
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.info).mockClear();
  });

  it("renders loading and empty states", () => {
    mocks.itemsLoading = true;
    mocks.matchItems = null;
    const { rerender } = render(<ResultsTable requestId="req-1" />);

    expect(screen.getByRole("status", { name: "Загрузка таблицы" })).toBeInTheDocument();

    mocks.itemsLoading = false;
    mocks.matchItems = { page: 1, page_size: 20, total: 0, items: [] };
    rerender(<ResultsTable requestId="req-1" />);

    expect(screen.getByText("Нет данных")).toBeInTheDocument();
    expect(screen.getByText("По выбранным фильтрам ничего не найдено")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "ArrowDown" });
  });

  it("renders empty states when item query data is absent", () => {
    mocks.matchItems = null;

    render(<ResultsTable requestId="req-1" />);

    expect(screen.getByText("Нет данных")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Принять авто (0 на стр.)" })).toBeInTheDocument();
  });

  it("approves visible auto matches and updates cached rows", async () => {
    const user = userEvent.setup();
    render(<ResultsTable requestId="req-1" />);

    expect(screen.getByText("Grundfos pump raw")).toBeInTheDocument();
    expect(screen.getByText("Best pump")).toBeInTheDocument();
    expect(screen.getByText("Проверено: 0 из 1 на странице")).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Выбрать все" }));
    expect(screen.getByText(/Выбрано: 1/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Mock review item-1" }));
    expect(mocks.setQueryData).toHaveBeenCalled();
    await user.click(screen.getByRole("checkbox", { name: "Выбрать все" }));

    await user.click(screen.getByRole("button", { name: "Принять авто (1 на стр.)" }));

    await waitFor(() =>
      expect(reviewBatch).toHaveBeenCalledWith([
        {
          request_item_id: "item-1",
          final_decision: "accepted",
          final_product_id: "p-best",
          create_supplier_mapping: true,
        },
      ]),
    );
    expect(toast.success).toHaveBeenCalledWith("Обработано 1 записей");
    expect(mocks.setQueryData).toHaveBeenCalled();
  });

  it("updates only the reviewed row in cached multi-row pages", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 2,
      items: [
        result({ request_item_id: "item-1", raw_text: "Reviewed pump" }),
        result({ request_item_id: "item-2", raw_text: "Untouched valve" }),
      ],
    };

    render(<ResultsTable requestId="req-1" />);

    await user.click(screen.getByRole("button", { name: "Mock review item-1" }));

    const latestUpdate = mocks.setQueryData.mock.results.at(-1)?.value as MatchItemsPage;
    expect(latestUpdate.items[0]).toEqual(
      expect.objectContaining({ request_item_id: "item-1", final_decision: "accepted" }),
    );
    expect(latestUpdate.items[1]).toEqual(
      expect.objectContaining({ request_item_id: "item-2" }),
    );
    expect(latestUpdate.items[1]).not.toHaveProperty("final_decision");
  });

  it("filters by local search text and review status", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 2,
      items: [
        result(),
        result({
          request_item_id: "item-2",
          line_id: "2",
          raw_text: "Valve item",
          normalized_text: "valve item",
          status: "review_needed",
          final_decision: "accepted",
        }),
      ],
    };

    render(<ResultsTable requestId="req-1" />);

    await user.type(screen.getByPlaceholderText("Поиск по тексту..."), "valve");

    expect(screen.queryByText("Grundfos pump raw")).not.toBeInTheDocument();
    expect(screen.getByText("Valve item")).toBeInTheDocument();

    await user.click(screen.getAllByText("set reviewed")[1]);
    expect(screen.getByText("Valve item")).toBeInTheDocument();

    await user.click(screen.getAllByText("set pending")[1]);
    expect(screen.getByText("Нет данных")).toBeInTheDocument();
  });

  it("expands candidates and saves a selected candidate", async () => {
    const user = userEvent.setup();
    mocks.candidates = {
      candidates: [
        candidate(),
        candidate({
          product_id: "p-sparse",
          name: "Sparse candidate",
          article: undefined,
          brand: undefined,
          lexical_score: 0,
          semantic_score: 0,
          rerank_score: 0,
          rules_score: 0,
          final_score: undefined,
        }),
      ],
    };
    render(<ResultsTable requestId="req-1" />);

    await user.click(screen.getByRole("button", { name: "Развернуть" }));

    expect(screen.getByText("Извлечённые атрибуты:")).toBeInTheDocument();
    expect(screen.getByText("brand: Grundfos")).toBeInTheDocument();
    expect(screen.getByText("Факторы совпадения:")).toBeInTheDocument();
    expect(screen.getByText("Alternative pump")).toBeInTheDocument();
    expect(screen.getByText("Sparse candidate")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("-").length).toBeGreaterThanOrEqual(4);

    await user.click(screen.getByRole("button", { name: "Свернуть" }));
    expect(screen.queryByText("Sparse candidate")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Развернуть" }));

    await user.click(screen.getAllByRole("button", { name: "Выбрать" })[0]);

    await waitFor(() =>
      expect(reviewItem).toHaveBeenCalledWith("item-1", {
        final_decision: "corrected",
        final_product_id: "p-alt",
        create_alias: true,
        create_supplier_mapping: true,
      } satisfies ReviewInput),
    );
    expect(toast.success).toHaveBeenCalledWith("Выбранный кандидат сохранен");
    expect(mocks.setQueryData).toHaveBeenCalled();
  });

  it("rejects selected rows and supports keyboard accept/reject shortcuts", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 2,
      items: [
        result({ request_item_id: "item-1", line_id: "1", raw_text: "Pump one" }),
        result({ request_item_id: "item-2", line_id: "2", raw_text: "Pump two" }),
      ],
    };

    render(<ResultsTable requestId="req-1" />);

    await user.click(screen.getAllByRole("checkbox", { name: "Выбрать строку" })[0]);
    expect(screen.getByText(/Выбрано: 1/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Отклонить выбранные/ }));

    await waitFor(() =>
      expect(reviewBatch).toHaveBeenCalledWith([
        {
          request_item_id: "item-1",
          final_decision: "rejected",
        },
      ]),
    );

    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");
    await waitFor(() =>
      expect(reviewBatch).toHaveBeenCalledWith([
        {
          request_item_id: "item-1",
          final_decision: "accepted",
          final_product_id: "p-best",
          create_supplier_mapping: true,
        },
      ]),
    );

    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(reviewBatch).toHaveBeenCalledWith([
        {
          request_item_id: "item-2",
          final_decision: "rejected",
        },
      ]),
    );

    await user.keyboard("{ArrowUp}");
    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(reviewBatch).toHaveBeenCalledWith([
        {
          request_item_id: "item-1",
          final_decision: "rejected",
        },
      ]),
    );
  });

  it("sorts by confidence in both directions and hides equal normalized text", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 2,
      items: [
        result({
          request_item_id: "low-confidence",
          line_id: "1",
          raw_text: "Same text",
          normalized_text: "Same text",
          confidence: 0.2,
        }),
        result({
          request_item_id: "high-confidence",
          line_id: "2",
          raw_text: "Higher confidence",
          normalized_text: "",
          confidence: 0.9,
        }),
      ],
    };

    const { container } = render(<ResultsTable requestId="req-1" />);

    expect(screen.getByText("Same text")).toBeInTheDocument();
    expect(screen.getByText("Higher confidence")).toBeInTheDocument();
    expect(screen.queryAllByText("Same text")).toHaveLength(1);

    await user.click(screen.getByText("Уверенность").closest("th")!);
    expect(container.querySelector(".lucide-chevron-down")).toBeInTheDocument();

    await user.click(screen.getByText("Уверенность").closest("th")!);
    expect(container.querySelector(".lucide-chevron-down")).toBeInTheDocument();
  });

  it("ignores keyboard accept and reject shortcuts for finalized or incomplete rows", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 2,
      items: [
        result({
          request_item_id: "no-best",
          line_id: "1",
          raw_text: "No best candidate",
          best_candidate: undefined,
        }),
        result({
          request_item_id: "already-final",
          line_id: "2",
          raw_text: "Already final",
          final_decision: "accepted",
        }),
      ],
    };

    render(<ResultsTable requestId="req-1" />);

    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Escape}");

    expect(reviewBatch).not.toHaveBeenCalled();
  });

  it("wraps keyboard navigation upward from no expanded row", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 2,
      items: [
        result({ request_item_id: "item-1", line_id: "1", raw_text: "First pump" }),
        result({ request_item_id: "item-2", line_id: "2", raw_text: "Last pump" }),
      ],
    };

    render(<ResultsTable requestId="req-1" />);

    await user.keyboard("{ArrowUp}");

    expect(screen.getByText("Alternative pump")).toBeInTheDocument();
  });

  it("ignores escape before a row has been expanded", async () => {
    const user = userEvent.setup();

    render(<ResultsTable requestId="req-1" />);

    await user.keyboard("{Escape}");

    expect(reviewBatch).not.toHaveBeenCalled();
  });

  it("ignores enter when the expanded row is no longer visible", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 2,
      items: [
        result({ request_item_id: "item-1", raw_text: "Visible pump" }),
        result({ request_item_id: "item-2", raw_text: "Hidden valve" }),
      ],
    };

    render(<ResultsTable requestId="req-1" />);

    await user.click(screen.getAllByRole("button", { name: "Развернуть" })[0]);
    await user.type(screen.getByPlaceholderText("Поиск по тексту..."), "Hidden");
    await user.keyboard("{Enter}");

    expect(reviewBatch).not.toHaveBeenCalled();
    expect(screen.getByText("Hidden valve")).toBeInTheDocument();
  });

  it("shows candidate loading and empty states", async () => {
    const user = userEvent.setup();
    mocks.candidatesLoading = true;
    mocks.candidates = null;

    const { rerender } = render(<ResultsTable requestId="req-1" />);

    await user.click(screen.getByRole("button", { name: "Развернуть" }));
    expect(screen.getAllByRole("status", { name: "Загрузка таблицы" }).length).toBeGreaterThan(0);

    mocks.candidatesLoading = false;
    mocks.candidates = { candidates: [] };
    rerender(<ResultsTable requestId="req-1" />);

    expect(screen.getByText("Кандидаты не найдены")).toBeInTheDocument();
    expect(screen.getByText("Альтернативные кандидаты для этой позиции не найдены")).toBeInTheDocument();
  });

  it("reports fast review errors and disables candidate selection after a decision", async () => {
    const user = userEvent.setup();
    vi.mocked(reviewItem).mockRejectedValueOnce(new Error("candidate failed"));

    const { rerender } = render(<ResultsTable requestId="req-1" />);

    await user.click(screen.getByRole("button", { name: "Развернуть" }));
    await user.click(screen.getByRole("button", { name: "Выбрать" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при сохранении: candidate failed"),
    );

    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 1,
      items: [result({ final_decision: "accepted" })],
    };
    rerender(<ResultsTable requestId="req-1" />);

    expect(screen.getByRole("button", { name: "Выбрать" })).toBeDisabled();
  });

  it("uses fallback messages for non-Error review failures and line numbers without IDs", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 1,
      items: [result({ line_id: undefined as never })],
    };
    vi.mocked(reviewItem).mockRejectedValueOnce("candidate string failure");
    vi.mocked(reviewBatch).mockRejectedValueOnce("bulk string failure");

    render(<ResultsTable requestId="req-1" />);

    expect(screen.getByText("1")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Развернуть" }));
    await user.click(screen.getByRole("button", { name: "Выбрать" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при сохранении: Неизвестная ошибка"),
    );

    await user.click(screen.getByRole("checkbox", { name: "Выбрать строку" }));
    await user.click(screen.getByRole("button", { name: /Отклонить выбранные/ }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при массовой обработке: Неизвестная ошибка"),
    );
  });

  it("handles cache update guards and reviewed row color variants", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 3,
      items: [
        result({ request_item_id: "accepted", line_id: "1", final_decision: "accepted" }),
        result({ request_item_id: "corrected", line_id: "2", final_decision: "corrected" }),
        result({ request_item_id: "rejected", line_id: "3", final_decision: "rejected" }),
      ],
    };
    mocks.setQueryData.mockImplementation((_: unknown, updater: unknown) => {
      if (typeof updater === "function") {
        return updater(undefined);
      }
      return updater;
    });

    const { container } = render(<ResultsTable requestId="req-1" />);

    expect(container.querySelector(".border-l-green-500")).toBeInTheDocument();
    expect(container.querySelector(".border-l-blue-500")).toBeInTheDocument();
    expect(container.querySelector(".border-l-red-500")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Mock review accepted" }));
    await waitFor(() => expect(mocks.setQueryData).toHaveBeenCalled());

    await user.click(screen.getByRole("checkbox", { name: "Выбрать все" }));
    await user.click(screen.getByRole("button", { name: /Отклонить выбранные/ }));

    await waitFor(() => expect(reviewBatch).toHaveBeenCalled());
  });

  it("reports bulk review errors and handles pages without auto matches", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 1,
      items: [
        result({
          status: "review_needed",
          confidence: 0.72,
          best_candidate: undefined,
          extracted_attributes: {},
          reasons: [],
        }),
      ],
    };
    vi.mocked(reviewBatch).mockRejectedValueOnce(new Error("batch failed"));

    render(<ResultsTable requestId="req-1" />);

    await user.click(screen.getByRole("button", { name: "Принять авто (0 на стр.)" }));
    expect(toast.info).toHaveBeenCalledWith("Нет доступных авто-сопоставлений для подтверждения");

    await user.click(screen.getByRole("checkbox", { name: "Выбрать строку" }));
    await user.click(screen.getByRole("button", { name: /Принять выбранные/ }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при массовой обработке: batch failed"),
    );
    expect(reviewBatch).toHaveBeenCalledWith([
      {
        request_item_id: "item-1",
        final_decision: "accepted",
        final_product_id: undefined,
        create_supplier_mapping: true,
      },
    ]);
  });

  it("resets expanded rows and selections when filters or pages change", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: 41,
      items: [
        result({ request_item_id: "item-1", line_id: "1", raw_text: "Pump one" }),
        result({ request_item_id: "item-2", line_id: "2", raw_text: "Pump two" }),
      ],
    };

    render(<ResultsTable requestId="req-1" />);

    await user.click(screen.getAllByRole("button", { name: "Развернуть" })[0]);
    expect(screen.getByText("Alternative pump")).toBeInTheDocument();

    await user.click(screen.getAllByRole("checkbox", { name: "Выбрать строку" })[0]);
    expect(screen.getByText(/Выбрано: 1/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Следующая страница" }));
    expect(screen.queryByText("Alternative pump")).not.toBeInTheDocument();
    expect(screen.queryByText(/Выбрано: 1/)).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Развернуть" })[0]);
    await user.click(screen.getAllByText("set review needed")[0]);

    expect(screen.queryByText("Alternative pump")).not.toBeInTheDocument();
  });

  it("auto-advances drained pending pages", async () => {
    const user = userEvent.setup();
    mocks.matchItemsByPage = {
      1: {
        page: 1,
        page_size: 20,
        total: 41,
        items: [result({ final_decision: "accepted" })],
      },
      2: {
        page: 2,
        page_size: 20,
        total: 41,
        items: [],
      },
    };

    render(<ResultsTable requestId="req-1" />);

    await user.click(screen.getAllByText("set pending")[1]);

    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith("Страница 2: все позиции проверены, переход..."),
    );
  });

  it("returns to the first page when the last pending page is drained", async () => {
    const user = userEvent.setup();
    mocks.matchItemsByPage = {
      1: {
        page: 1,
        page_size: 20,
        total: 21,
        items: [result({ request_item_id: "item-1", final_decision: undefined })],
      },
      2: {
        page: 2,
        page_size: 20,
        total: 21,
        items: [result({ request_item_id: "item-2", final_decision: "accepted" })],
      },
    };

    render(<ResultsTable requestId="req-1" />);

    await user.click(screen.getByRole("button", { name: "Следующая страница" }));
    await user.click(screen.getAllByText("set pending")[1]);

    await waitFor(() => expect(screen.getByText("Grundfos pump raw")).toBeInTheDocument());
  });

  it("uses pagination total fallback when item totals are absent", async () => {
    const user = userEvent.setup();
    mocks.matchItems = {
      page: 1,
      page_size: 20,
      total: undefined as never,
      items: [result()],
    };

    render(<ResultsTable requestId="req-1" />);

    await user.keyboard("{ArrowDown}");
    expect(screen.getByText("Grundfos pump raw")).toBeInTheDocument();
  });
});
