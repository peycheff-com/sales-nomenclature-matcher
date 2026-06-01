import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { searchCatalog } from "@/api/catalog";
import { getMatchItems } from "@/api/match";
import { reviewItem } from "@/api/review";
import type { MatchResult, ReviewInput } from "@/api/types";
import ExportButton from "@/components/export/export-button";
import ReviewActions from "@/components/review/review-actions";
import Papa from "papaparse";
import { toast } from "sonner";

const queryMocks = vi.hoisted(() => ({
  catalogData: [
    {
      product_id: "p-correct",
      name: "Correct pump",
      article: "A-2",
      brand: "Grundfos",
      is_active: true,
    },
  ],
  catalogIsFetching: false,
  catalogIsLoading: false,
  catalogIsSuccess: true,
  mutateError: null as unknown,
}));

const excelMocks = vi.hoisted(() => ({
  addWorksheet: vi.fn(),
  addRow: vi.fn(),
  writeBuffer: vi.fn(),
}));

vi.mock("@tanstack/react-query", () => ({
  useMutation: ({
    mutationFn,
    onSuccess,
    onError,
  }: {
    mutationFn: (input: ReviewInput) => Promise<unknown>;
    onSuccess?: (data: unknown, input: ReviewInput) => void;
    onError?: (error: Error) => void;
  }) => ({
    isPending: false,
    mutate: async (input: ReviewInput) => {
      if (queryMocks.mutateError) {
        onError?.(queryMocks.mutateError as Error);
        return;
      }
      const data = await mutationFn(input);
      onSuccess?.(data, input);
    },
  }),
  useQuery: ({
    queryFn,
    enabled,
  }: {
    queryFn: () => Promise<unknown>;
    enabled?: boolean;
  }) => {
    if (enabled) {
      void queryFn();
    }
    return {
      data: queryMocks.catalogData,
      isFetching: queryMocks.catalogIsFetching,
      isLoading: queryMocks.catalogIsLoading,
      isSuccess: queryMocks.catalogIsSuccess,
    };
  },
}));

vi.mock("@/api/catalog", () => ({
  searchCatalog: vi.fn(),
}));

vi.mock("@/api/match", () => ({
  getMatchItems: vi.fn(),
}));

vi.mock("@/api/review", () => ({
  reviewItem: vi.fn(),
}));

vi.mock("papaparse", () => ({
  default: {
    unparse: vi.fn(() => "csv-output"),
  },
}));

vi.mock("exceljs", () => ({
  default: {
    Workbook: vi.fn(function Workbook() {
      return {
      addWorksheet: excelMocks.addWorksheet,
      xlsx: {
        writeBuffer: excelMocks.writeBuffer,
      },
      };
    }),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({
    children,
    onClick,
  }: {
    children: ReactNode;
    onClick?: () => void;
  }) => <button onClick={onClick}>{children}</button>,
  DropdownMenuTrigger: ({
    children,
    disabled,
  }: {
    children: ReactNode;
    disabled?: boolean;
  }) => <button disabled={disabled}>{children}</button>,
}));

function matchResult(overrides: Partial<MatchResult> = {}): MatchResult {
  return {
    request_item_id: "item-1",
    line_id: "1",
    raw_text: "Pump raw",
    normalized_text: "pump raw",
    extracted_attributes: {},
    status: "review_needed",
    confidence: 0.82,
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

describe("export and review actions", () => {
  beforeEach(() => {
    vi.mocked(getMatchItems).mockReset();
    vi.mocked(reviewItem).mockReset();
    vi.mocked(reviewItem).mockResolvedValue({ ok: true });
    vi.mocked(searchCatalog).mockResolvedValue(queryMocks.catalogData);
    vi.mocked(Papa.unparse).mockClear();
    vi.mocked(toast.success).mockClear();
    vi.mocked(toast.error).mockClear();
    excelMocks.addRow.mockClear();
    excelMocks.writeBuffer.mockReset();
    excelMocks.addWorksheet.mockReset();
    excelMocks.addWorksheet.mockReturnValue({ addRow: excelMocks.addRow });
    excelMocks.writeBuffer.mockResolvedValue(new ArrayBuffer(4));
    queryMocks.catalogData = [
      {
        product_id: "p-correct",
        name: "Correct pump",
        article: "A-2",
        brand: "Grundfos",
        is_active: true,
      },
    ];
    queryMocks.catalogIsFetching = false;
    queryMocks.catalogIsLoading = false;
    queryMocks.catalogIsSuccess = true;
    queryMocks.mutateError = null;
    URL.createObjectURL = vi.fn(() => "blob:export");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("exports all match rows as CSV with original template columns preserved", async () => {
    const user = userEvent.setup();
    const anchor = document.createElement("a");
    const click = vi.spyOn(anchor, "click").mockImplementation(() => undefined);
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      if (tagName === "a") return anchor;
      return originalCreateElement(tagName);
    });
    const firstPageItems = [
      matchResult({
        original_row: {
          "Поставщик": "ACME",
          "Номенклатура.1": "",
        },
      }),
      ...Array.from({ length: 99 }, (_, index) =>
        matchResult({
          request_item_id: `filler-${index}`,
          line_id: String(index + 2),
          raw_text: `Filler ${index}`,
        }),
      ),
    ];

    vi.mocked(getMatchItems)
      .mockResolvedValueOnce({
        page: 1,
        page_size: 100,
        total: 101,
        items: firstPageItems,
      })
      .mockResolvedValueOnce({
        page: 2,
        page_size: 100,
        total: 101,
        items: [
          matchResult({
            request_item_id: "item-2",
            original_row: { Custom: "x" },
            status: "no_match",
            confidence: undefined,
            best_candidate: undefined,
          }),
        ],
      });

    render(<ExportButton requestId="req-1" totalItems={101} />);

    await user.click(screen.getByRole("button", { name: "Экспорт" }));
    await user.click(screen.getByRole("button", { name: "Экспорт всех результатов (CSV)" }));

    await waitFor(() => expect(getMatchItems).toHaveBeenCalledTimes(2));
    expect(getMatchItems).toHaveBeenNthCalledWith(1, "req-1", { page: 1, page_size: 100 });
    expect(getMatchItems).toHaveBeenNthCalledWith(2, "req-1", { page: 2, page_size: 100 });
    expect(Papa.unparse).toHaveBeenCalledWith(expect.arrayContaining([
      expect.objectContaining({
        "Поставщик": "ACME",
        "Номенклатура.1": "Best pump",
        "Найдено в 1С (ID)": "p-best",
        "Уверенность": "82%",
        "Статус": "На проверку",
      }),
      expect.objectContaining({
        Custom: "x",
        "Статус": "Не найдено",
        "Найдено в 1С (Товар)": "",
      }),
    ]));
    expect(anchor.download).toBe("results-req-1.csv");
    expect(click).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:export");
  });

  it("exports match rows as XLSX", async () => {
    const user = userEvent.setup();
    const anchor = document.createElement("a");
    const click = vi.spyOn(anchor, "click").mockImplementation(() => undefined);
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      if (tagName === "a") return anchor;
      return originalCreateElement(tagName);
    });
    vi.mocked(getMatchItems).mockResolvedValue({
      page: 1,
      page_size: 100,
      total: 1,
      items: [
        matchResult({
          original_row: {
            "Товар 1С": "",
            "Исходная строка": "Pump raw",
            "Пустая колонка": undefined,
          },
        }),
      ],
    });

    render(<ExportButton requestId="req-xlsx" totalItems={1} />);

    await user.click(screen.getByRole("button", { name: "Экспорт" }));
    await user.click(screen.getByRole("button", { name: "Экспорт всех результатов (XLSX)" }));

    await waitFor(() => expect(excelMocks.writeBuffer).toHaveBeenCalled());
    expect(excelMocks.addWorksheet).toHaveBeenCalledWith("Результаты");
    expect(excelMocks.addRow).toHaveBeenCalledWith(expect.arrayContaining(["Товар 1С"]));
    expect(excelMocks.addRow).toHaveBeenCalledWith(expect.arrayContaining(["Best pump"]));
    expect(excelMocks.addRow).toHaveBeenCalledWith(expect.arrayContaining([""]));
    expect(anchor.download).toBe("results-req-xlsx.xlsx");
    expect(click).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:export");
  });

  it("exports sparse and legacy match rows with fallback values", async () => {
    const user = userEvent.setup();
    const anchor = document.createElement("a");
    const click = vi.spyOn(anchor, "click").mockImplementation(() => undefined);
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      if (tagName === "a") return anchor;
      return originalCreateElement(tagName);
    });
    vi.mocked(getMatchItems).mockResolvedValueOnce({
      page: 1,
      page_size: 100,
      total: 2,
      items: [
        matchResult({
          request_item_id: "legacy-template",
          original_row: { "Товар 1С": "" },
          status: "legacy_status" as never,
          best_candidate: undefined,
        }),
        matchResult({
          request_item_id: "sparse-row",
          line_id: undefined as never,
          normalized_text: undefined,
          status: "legacy_status" as never,
          confidence: undefined,
          best_candidate: undefined,
        }),
      ],
    });

    render(<ExportButton requestId="req-sparse" totalItems={2} />);

    await user.click(screen.getByRole("button", { name: "Экспорт" }));
    await user.click(screen.getByRole("button", { name: "Экспорт всех результатов (CSV)" }));

    await waitFor(() => expect(Papa.unparse).toHaveBeenCalled());
    expect(Papa.unparse).toHaveBeenCalledWith([
      expect.objectContaining({
        "Товар 1С": "",
        "Найдено в 1С (ID)": "",
        "Статус": "legacy_status",
      }),
      expect.objectContaining({
        "Строка": "",
        "Нормализованный": "",
        "Статус": "legacy_status",
        "Уверенность": "—",
        "Найденный товар": "",
        "Артикул": "",
        "Бренд": "",
        "ID товара": "",
      }),
    ]);
    expect(anchor.download).toBe("results-req-sparse.csv");
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("exports an empty XLSX workbook without data rows", async () => {
    const user = userEvent.setup();
    const anchor = document.createElement("a");
    const click = vi.spyOn(anchor, "click").mockImplementation(() => undefined);
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      if (tagName === "a") return anchor;
      return originalCreateElement(tagName);
    });

    render(<ExportButton requestId="req-empty" totalItems={0} />);

    await user.click(screen.getByRole("button", { name: "Экспорт" }));
    await user.click(screen.getByRole("button", { name: "Экспорт всех результатов (XLSX)" }));

    await waitFor(() => expect(excelMocks.writeBuffer).toHaveBeenCalled());
    expect(excelMocks.addWorksheet).toHaveBeenCalledWith("Результаты");
    expect(excelMocks.addRow).not.toHaveBeenCalled();
    expect(getMatchItems).not.toHaveBeenCalled();
    expect(anchor.download).toBe("results-req-empty.xlsx");
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("accepts, rejects, and reports review mutation failures", async () => {
    const user = userEvent.setup();
    const onReviewed = vi.fn();
    const { rerender } = render(
      <ReviewActions item={matchResult()} onReviewed={onReviewed} />,
    );

    await user.click(screen.getByRole("button", { name: "Ок" }));
    await waitFor(() =>
      expect(reviewItem).toHaveBeenCalledWith("item-1", {
        final_decision: "accepted",
        final_product_id: "p-best",
        create_supplier_mapping: true,
      }),
    );
    expect(onReviewed).toHaveBeenCalledWith("accepted");

    await user.click(screen.getByRole("button", { name: "Нет" }));
    await waitFor(() =>
      expect(reviewItem).toHaveBeenCalledWith("item-1", {
        final_decision: "rejected",
      }),
    );
    expect(onReviewed).toHaveBeenCalledWith("rejected");

    queryMocks.mutateError = new Error("write failed");
    rerender(<ReviewActions item={matchResult()} onReviewed={onReviewed} />);
    await user.click(screen.getByRole("button", { name: "Нет" }));

    expect(toast.error).toHaveBeenCalledWith("Ошибка сохранения решения: write failed");

    queryMocks.mutateError = "write failed without error object";
    rerender(<ReviewActions item={matchResult()} onReviewed={onReviewed} />);
    await user.click(screen.getByRole("button", { name: "Нет" }));

    expect(toast.error).toHaveBeenCalledWith("Ошибка сохранения решения: Неизвестная ошибка");
  });

  it("corrects a reviewed item through catalog selection", async () => {
    const user = userEvent.setup();
    const onReviewed = vi.fn();

    render(<ReviewActions item={matchResult({ final_decision: "accepted" })} onReviewed={onReviewed} />);

    await user.click(screen.getByTitle("Изменить решение"));
    await user.click(screen.getByRole("button", { name: "Исправить" }));
    expect(screen.getByText("Correct pump")).toBeInTheDocument();
    await user.click(screen.getByText("Correct pump"));
    expect(screen.getByText("Выбран товар: p-correct")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() =>
      expect(reviewItem).toHaveBeenCalledWith("item-1", {
        final_decision: "corrected",
        final_product_id: "p-correct",
        create_alias: true,
        create_supplier_mapping: true,
      }),
    );
    expect(onReviewed).toHaveBeenCalledWith("corrected");
  });

  it("cancels override and correction flows without submitting", async () => {
    const user = userEvent.setup();
    const onReviewed = vi.fn();

    render(
      <ReviewActions
        item={matchResult({ final_decision: "accepted", reviewed_by: "reviewer@example.com" })}
        onReviewed={onReviewed}
      />,
    );

    expect(screen.getByText("Принято")).toBeInTheDocument();
    expect(screen.getByText("reviewer@example.com")).toBeInTheDocument();
    await user.click(screen.getByTitle("Изменить решение"));
    await user.click(screen.getByTitle("Отменить изменение"));
    expect(screen.getByText("Принято")).toBeInTheDocument();

    await user.click(screen.getByTitle("Изменить решение"));
    await user.click(screen.getByRole("button", { name: "Исправить" }));
    expect(screen.getByText("Указать правильный товар")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Отмена" }));

    expect(reviewItem).not.toHaveBeenCalled();
    expect(onReviewed).not.toHaveBeenCalled();
  });

  it("shows catalog loading and empty states while correcting", async () => {
    const user = userEvent.setup();
    const onReviewed = vi.fn();
    queryMocks.catalogIsLoading = true;
    queryMocks.catalogIsFetching = true;
    queryMocks.catalogIsSuccess = false;

    const { rerender } = render(<ReviewActions item={matchResult()} onReviewed={onReviewed} />);

    await user.click(screen.getByRole("button", { name: "Исправить" }));
    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
    expect(screen.getAllByRole("button").some((button) => button.hasAttribute("disabled"))).toBe(true);

    queryMocks.catalogIsLoading = false;
    queryMocks.catalogIsFetching = false;
    queryMocks.catalogIsSuccess = true;
    queryMocks.catalogData = [];
    rerender(<ReviewActions item={matchResult()} onReviewed={onReviewed} />);
    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
  });

  it("updates regular correction search by keyboard and search button", async () => {
    const user = userEvent.setup();
    const onReviewed = vi.fn();

    render(<ReviewActions item={matchResult()} onReviewed={onReviewed} />);

    await user.click(screen.getByRole("button", { name: "Исправить" }));
    const input = screen.getByPlaceholderText("Введите запрос и нажмите Enter");
    await user.clear(input);
    await user.type(input, "regular pump{Enter}");
    expect(searchCatalog).toHaveBeenCalledWith("regular pump", 10);

    await user.clear(input);
    await user.type(input, "button pump");
    const searchButton = input.closest("div")?.querySelector("button");
    expect(searchButton).toBeTruthy();
    await user.click(searchButton as HTMLButtonElement);

    expect(searchCatalog).toHaveBeenCalledWith("button pump", 10);
  });

  it("shows metadata fallbacks in regular correction results", async () => {
    const user = userEvent.setup();
    const onReviewed = vi.fn();
    queryMocks.catalogData = [
      {
        product_id: "p-no-meta",
        name: "Catalog item without metadata",
        article: "",
        brand: "",
        is_active: true,
      },
    ];

    render(<ReviewActions item={matchResult()} onReviewed={onReviewed} />);

    await user.click(screen.getByRole("button", { name: "Исправить" }));

    expect(screen.getByText("Catalog item without metadata")).toBeInTheDocument();
    expect(screen.getByText("Арт: —")).toBeInTheDocument();
    expect(screen.getByText("Бренд: —")).toBeInTheDocument();
  });

  it("disables accepting when no best candidate is available", () => {
    const onReviewed = vi.fn();

    render(<ReviewActions item={matchResult({ best_candidate: undefined })} onReviewed={onReviewed} />);

    expect(screen.getByRole("button", { name: "Ок" })).toBeDisabled();
  });

  it("confirms and corrects an automatic match", async () => {
    const user = userEvent.setup();
    const onReviewed = vi.fn();
    const autoItem = matchResult({ status: "auto_match" });

    render(<ReviewActions item={autoItem} onReviewed={onReviewed} />);

    expect(screen.getByText("Авто")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ок" }));
    await waitFor(() =>
      expect(reviewItem).toHaveBeenCalledWith("item-1", {
        final_decision: "accepted",
        final_product_id: "p-best",
        create_supplier_mapping: true,
      }),
    );

    await user.click(screen.getByRole("button", { name: "Исправить" }));
    expect(screen.getByText("Correct pump")).toBeInTheDocument();
    await user.click(screen.getByText("Correct pump"));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() =>
      expect(reviewItem).toHaveBeenCalledWith("item-1", {
        final_decision: "corrected",
        final_product_id: "p-correct",
        create_alias: true,
        create_supplier_mapping: true,
      }),
    );
    expect(onReviewed).toHaveBeenCalledWith("corrected");
  });

  it("updates correction search by keyboard and button and can cancel an auto correction", async () => {
    const user = userEvent.setup();
    const onReviewed = vi.fn();
    queryMocks.catalogData = [
      {
        product_id: "p-no-meta",
        name: "Catalog item without metadata",
        article: "",
        brand: "",
        is_active: true,
      },
    ];

    render(<ReviewActions item={matchResult({ status: "auto_match" })} onReviewed={onReviewed} />);

    await user.click(screen.getByRole("button", { name: "Исправить" }));
    const input = screen.getByPlaceholderText("Введите запрос и нажмите Enter");
    await user.clear(input);
    await user.type(input, "custom pump{Enter}");
    const searchButton = input.closest("div")?.querySelector("button");
    expect(searchButton).toBeTruthy();
    await user.click(searchButton as HTMLButtonElement);

    expect(screen.getByText("Catalog item without metadata")).toBeInTheDocument();
    expect(screen.getAllByText("Арт: —").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Бренд: —").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Отмена" }));

    expect(reviewItem).not.toHaveBeenCalled();
    expect(onReviewed).not.toHaveBeenCalled();
  });

  it("shows automatic correction loading and empty catalog states", async () => {
    const user = userEvent.setup();
    const onReviewed = vi.fn();
    queryMocks.catalogIsLoading = true;
    queryMocks.catalogIsFetching = true;
    queryMocks.catalogIsSuccess = false;

    const { rerender } = render(
      <ReviewActions item={matchResult({ status: "auto_match" })} onReviewed={onReviewed} />,
    );

    await user.click(screen.getByRole("button", { name: "Исправить" }));
    expect(screen.getByText("Загрузка...")).toBeInTheDocument();
    expect(document.querySelector(".lucide-loader-circle")).toBeInTheDocument();

    queryMocks.catalogIsLoading = false;
    queryMocks.catalogIsFetching = false;
    queryMocks.catalogIsSuccess = true;
    queryMocks.catalogData = [];
    rerender(<ReviewActions item={matchResult({ status: "auto_match" })} onReviewed={onReviewed} />);

    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
  });

  it("falls back to raw decision text for unknown reviewed decisions", async () => {
    const user = userEvent.setup();
    const onReviewed = vi.fn();

    render(
      <ReviewActions
        item={matchResult({ final_decision: "legacy_decision" as MatchResult["final_decision"] })}
        onReviewed={onReviewed}
      />,
    );

    expect(screen.getByText("legacy_decision")).toBeInTheDocument();
    await user.click(screen.getByTitle("Изменить решение"));
    await user.click(screen.getByRole("button", { name: "Ок" }));

    await waitFor(() =>
      expect(reviewItem).toHaveBeenCalledWith("item-1", {
        final_decision: "accepted",
        final_product_id: "p-best",
        create_supplier_mapping: true,
      }),
    );
  });
});
