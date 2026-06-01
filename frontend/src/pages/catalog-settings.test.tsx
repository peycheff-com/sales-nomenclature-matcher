import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  deleteCatalogProduct,
  getCatalogStats,
  importFromOnec,
  reindexCatalog,
  searchCatalog,
  uploadCatalogFile,
} from "@/api/catalog";
import {
  getModels,
  getSettings,
  testOneCConnection,
  updateSettings,
} from "@/api/settings";
import CatalogPage from "@/pages/catalog";
import SettingsPage from "@/pages/settings";
import { toast } from "sonner";

const mocks = vi.hoisted(() => ({
  invalidateQueries: vi.fn(),
  setQueryData: vi.fn(),
  queryLoading: new Set<string>(),
  queryErrors: new Map<string, Error>(),
  mutationPending: false,
  settings: {
    llm_provider: "openai",
    embedding_provider: "jina",
    rerank_provider: "cohere",
    providers_registry: [
      {
        id: "openai",
        name: "OpenAI",
        api_key_set: false,
        base_url: "https://api.openai.com/v1",
        supports_chat: true,
        supports_embeddings: true,
        supports_rerank: false,
        rerank_mode: null,
        is_beta: false,
        notes: null,
      },
      {
        id: "jina",
        name: "Jina",
        api_key_set: true,
        base_url: "https://api.jina.ai/v1",
        supports_chat: false,
        supports_embeddings: true,
        supports_rerank: true,
        rerank_mode: "api",
        is_beta: false,
        notes: null,
      },
      {
        id: "cohere",
        name: "Cohere",
        api_key_set: true,
        base_url: "https://api.cohere.com/v2",
        supports_chat: false,
        supports_embeddings: false,
        supports_rerank: true,
        rerank_mode: "api",
        is_beta: false,
        notes: null,
      },
    ],
    llm_model: "gpt-4o-mini",
    llm_rerank_model: "rerank-v3.5",
    embedding_model: "jina-embeddings-v3",
    embedding_dimensions: 1024,
    auto_match_threshold: 0.9,
    review_threshold: 0.6,
    retrieval_top_n: 10,
    rerank_top_n: 5,
    agentic_resolution_enabled: false,
    small_catalog_threshold: 500,
    llm_matcher_enabled: true,
    llm_matcher_model: "",
    llm_matcher_batch_size: 5,
    onec: {
      base_url: "",
      username: "",
      password: "",
      catalog_endpoint: "/hs/catalog/v1/nomenclature",
      enabled: false,
    },
  },
  stats: {
    total_products: 2,
    embedded_products: 1,
    embedding_model: "jina-embeddings-v3",
    embedding_coverage_pct: 50,
    onec_connected: true,
  },
  products: [
    {
      product_id: "p1",
      name: "Pump alpha",
      article: "A-1",
      brand: "Grundfos",
      category_path: "Pumps",
      is_active: true,
    },
    {
      product_id: "p2",
      name: "Valve archive",
      article: "V-2",
      brand: "Danfoss",
      category_path: "Valves",
      is_active: false,
    },
  ],
  modelsData: {
    models: [
      { id: "gpt-4o-mini", name: "GPT 4o mini", context_length: 128000, type: "chat" },
      { id: "jina-embeddings-v3", name: "Jina Embeddings", context_length: 8192, type: "embedding" },
      { id: "rerank-v3.5", name: "Cohere Rerank", context_length: 4096, type: "rerank" },
    ],
  } as { models: Array<{ id: string; name: string; context_length: number; type: string }> } | undefined,
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({
    invalidateQueries: mocks.invalidateQueries,
    setQueryData: mocks.setQueryData,
  }),
  useQuery: ({ queryKey, queryFn }: { queryKey: unknown[]; queryFn: () => Promise<unknown> }) => {
    const key = String(queryKey[0]);
    try {
      void queryFn().catch(() => undefined);
    } catch {
      // Inline mock data below is authoritative for these component tests.
    }
    const error = mocks.queryErrors.get(key);
    const dataByKey: Record<string, unknown> = {
      settings: mocks.settings,
      models: mocks.modelsData,
      "catalog-stats": mocks.stats,
      "catalog-search": mocks.products,
    };
    return {
      data: dataByKey[key],
      isLoading: mocks.queryLoading.has(key),
      isFetching: false,
      isError: !!error,
      error,
      refetch: mocks.invalidateQueries,
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
    mutateAsync: async (input?: unknown) => {
      const data = await mutationFn(input);
      onSuccess?.(data);
      return data;
    },
  }),
}));

vi.mock("@/hooks/use-debounced-value", () => ({
  useDebouncedValue: <T,>(value: T) => value,
}));

vi.mock("@/components/ui/select", () => ({
  Select: ({ children, onValueChange }: { children: ReactNode; onValueChange?: (value: string) => void }) => (
    <div>
      {children}
      {onValueChange && (
        <>
          <button type="button" onClick={() => onValueChange("active")}>select active</button>
          <button type="button" onClick={() => onValueChange("archive")}>select archive</button>
          <button type="button" onClick={() => onValueChange("llm-fallback")}>select llm fallback</button>
          <button type="button" onClick={() => onValueChange("")}>select blank</button>
        </>
      )}
    </div>
  ),
  SelectContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children, disabled }: { children: ReactNode; disabled?: boolean }) => (
    <button disabled={disabled}>{children}</button>
  ),
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder ?? "selected"}</span>,
}));

vi.mock("@/components/ui/model-combobox", () => ({
  ModelCombobox: ({
    value,
    onChange,
    placeholder,
  }: {
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
  }) => (
    <input
      aria-label={placeholder}
      placeholder={placeholder}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));

vi.mock("@/components/features/metrics-tab", () => ({
  MetricsTab: () => <div>Metrics tab</div>,
}));

vi.mock("@/components/ui/tabs", () => ({
  Tabs: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TabsList: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children }: { children: ReactNode }) => <button>{children}</button>,
  TabsContent: ({ children }: { children: ReactNode }) => <section>{children}</section>,
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({
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
        <button type="button" onClick={() => onOpenChange?.(false)}>close dialog</button>
      </div>
    ) : null,
  DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
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
        <button type="button" onClick={() => onOpenChange?.(false)}>close dialog</button>
      </div>
    ) : null,
  AlertDialogAction: ({
    children,
    onClick,
    disabled,
  }: {
    children: ReactNode;
    onClick?: () => void;
    disabled?: boolean;
  }) => <button disabled={disabled} onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children, onClick }: { children: ReactNode; onClick?: () => void }) => (
    <button onClick={onClick}>{children}</button>
  ),
  AlertDialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  TooltipTrigger: ({ children, render }: { children?: ReactNode; render?: ReactNode }) => (
    <span>{render ?? children}</span>
  ),
  TooltipContent: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}));

vi.mock("@/api/settings", () => ({
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
  getModels: vi.fn(),
  testOneCConnection: vi.fn(),
}));

vi.mock("@/api/catalog", () => ({
  searchCatalog: vi.fn(),
  getCatalogStats: vi.fn(),
  importFromOnec: vi.fn(),
  reindexCatalog: vi.fn(),
  uploadCatalogFile: vi.fn(),
  deleteCatalogProduct: vi.fn(),
}));

vi.mock("sonner", () => {
  const toastFn = vi.fn();
  return {
    toast: Object.assign(toastFn, {
      success: vi.fn(),
      error: vi.fn(),
    }),
  };
});

describe("catalog and settings pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.queryLoading.clear();
    mocks.queryErrors.clear();
    mocks.mutationPending = false;
    mocks.modelsData = {
      models: [
        { id: "gpt-4o-mini", name: "GPT 4o mini", context_length: 128000, type: "chat" },
        { id: "jina-embeddings-v3", name: "Jina Embeddings", context_length: 8192, type: "embedding" },
        { id: "rerank-v3.5", name: "Cohere Rerank", context_length: 4096, type: "rerank" },
      ],
    };
    mocks.stats = {
      total_products: 2,
      embedded_products: 1,
      embedding_model: "jina-embeddings-v3",
      embedding_coverage_pct: 50,
      onec_connected: true,
    };
    mocks.products = [
      {
        product_id: "p1",
        name: "Pump alpha",
        article: "A-1",
        brand: "Grundfos",
        category_path: "Pumps",
        is_active: true,
      },
      {
        product_id: "p2",
        name: "Valve archive",
        article: "V-2",
        brand: "Danfoss",
        category_path: "Valves",
        is_active: false,
      },
    ];
    vi.mocked(getSettings).mockResolvedValue(mocks.settings as never);
    vi.mocked(updateSettings).mockResolvedValue(mocks.settings as never);
    vi.mocked(getModels).mockResolvedValue({ models: [] });
    vi.mocked(testOneCConnection).mockResolvedValue({
      status: "ok",
      detail: "ok",
      http_status: 200,
    });
    vi.mocked(getCatalogStats).mockResolvedValue(mocks.stats);
    vi.mocked(searchCatalog).mockResolvedValue(mocks.products);
    vi.mocked(importFromOnec).mockResolvedValue({ job_id: "sync-1" });
    vi.mocked(reindexCatalog).mockResolvedValue({ job_id: "reindex-1" });
    vi.mocked(uploadCatalogFile).mockResolvedValue({ job_id: "upload-1" });
    vi.mocked(deleteCatalogProduct).mockResolvedValue(undefined);
  });

  it("renders settings loading and error states", () => {
    mocks.queryLoading.add("settings");
    const { container, rerender } = render(<SettingsPage />);

    expect(container.querySelectorAll('[data-slot="skeleton-card"]')).toHaveLength(2);

    mocks.queryLoading.clear();
    mocks.queryErrors.set("settings", new Error("settings unavailable"));
    rerender(<SettingsPage />);

    expect(screen.getByRole("alert")).toHaveTextContent("settings unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(mocks.invalidateQueries).toHaveBeenCalled();
  });

  it("updates settings and tests the 1C connection", async () => {
    const user = userEvent.setup();
    render(<SettingsPage />);

    expect(screen.getByText("Провайдеры ИИ (LLM & Embeddings)")).toBeInTheDocument();
    expect(screen.getAllByText("OpenAI")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Ключ не настроен")[0]).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Введите API ключ"), "sk-test");
    await user.click(screen.getByRole("button", { name: "Сохранить настройки" }));
    await waitFor(() => expect(updateSettings).toHaveBeenCalled());
    expect(updateSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        providers_registry: expect.arrayContaining([
          expect.objectContaining({ id: "openai", api_key: "sk-test" }),
        ]),
      }),
    );
    expect(toast.success).toHaveBeenCalledWith("Настройки успешно сохранены");

    await user.click(screen.getByLabelText("Включить интеграцию с 1С"));
    await user.type(screen.getByPlaceholderText("http://1c.domain.com/base"), "http://1c.local/base");
    await user.click(screen.getByRole("button", { name: "Проверить соединение" }));
    await waitFor(() => expect(testOneCConnection).toHaveBeenCalledTimes(1));
  });

  it("shows settings connection failures and resets unsaved changes", async () => {
    const user = userEvent.setup();
    vi.mocked(updateSettings).mockResolvedValueOnce({
      ...mocks.settings,
      onec: { ...mocks.settings.onec, enabled: true },
    } as never);
    vi.mocked(testOneCConnection).mockRejectedValueOnce(new Error("connection refused"));
    render(<SettingsPage />);

    await user.type(screen.getByPlaceholderText("Введите API ключ"), "temporary-key");
    expect(screen.getByText("Отличается от сохраненного")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Отменить изменения" }));

    await user.click(screen.getByLabelText("Включить интеграцию с 1С"));
    await user.click(screen.getByRole("button", { name: "Проверить соединение" }));
    await waitFor(() => expect(testOneCConnection).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Ошибка: connection refused/)).toBeInTheDocument();
  });

  it("reports save failures and warns about dirty navigation", async () => {
    const user = userEvent.setup();
    vi.mocked(updateSettings).mockRejectedValueOnce(new Error("settings locked"));
    render(<SettingsPage />);

    await user.type(screen.getByPlaceholderText("Введите API ключ"), "bad-key");
    const beforeUnload = new Event("beforeunload", { cancelable: true }) as BeforeUnloadEvent;
    const allowed = window.dispatchEvent(beforeUnload);

    expect(allowed).toBe(false);
    expect(beforeUnload.defaultPrevented).toBe(true);

    await user.click(screen.getByRole("button", { name: "Сохранить настройки" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при сохранении настроек: settings locked"),
    );
  });

  it("reports non-error settings save failures", async () => {
    const user = userEvent.setup();
    vi.mocked(updateSettings).mockRejectedValueOnce("plain failure");
    render(<SettingsPage />);

    await user.type(screen.getByPlaceholderText("Введите API ключ"), "bad-key");
    await user.click(screen.getByRole("button", { name: "Сохранить настройки" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при сохранении настроек: "),
    );
  });

  it("saves settings when the provider registry is missing", async () => {
    const user = userEvent.setup();
    const originalSettings = mocks.settings;
    mocks.settings = {
      ...mocks.settings,
      providers_registry: undefined as never,
    };

    try {
      render(<SettingsPage />);

      await user.clear(screen.getByPlaceholderText("Например: gpt-4o-mini"));
      await user.type(screen.getByPlaceholderText("Например: gpt-4o-mini"), "gpt-without-registry");
      await user.click(screen.getByRole("button", { name: "Сохранить настройки" }));

      await waitFor(() => expect(updateSettings).toHaveBeenCalled());
      expect(updateSettings).toHaveBeenCalledWith(
        expect.not.objectContaining({ providers_registry: expect.anything() }),
      );
    } finally {
      mocks.settings = originalSettings;
    }
  });

  it("renders beta, local, and unknown provider status branches", () => {
    const originalSettings = mocks.settings;
    mocks.settings = {
      ...mocks.settings,
      llm_provider: "beta-chat",
      embedding_provider: "local",
      rerank_provider: "missing-rerank",
      providers_registry: [
        ...mocks.settings.providers_registry,
        {
          id: "beta-chat",
          name: "Beta Chat",
          api_key_set: false,
          base_url: "https://beta.example/v1",
          supports_chat: true,
          supports_embeddings: false,
          supports_rerank: false,
          rerank_mode: null,
          is_beta: true,
          notes: null,
        },
        {
          id: "local",
          name: "Local",
          api_key_set: false,
          base_url: "http://localhost:11434/v1",
          supports_chat: true,
          supports_embeddings: true,
          supports_rerank: false,
          rerank_mode: null,
          is_beta: false,
          notes: null,
        },
      ],
    };

    try {
      render(<SettingsPage />);

      expect(screen.getByText("Beta Chat (beta)")).toBeInTheDocument();
      expect(screen.getByText("Beta Chat Base URL")).toBeInTheDocument();
      expect(screen.getByText("Beta Chat API Key")).toBeInTheDocument();
      expect(screen.getByText(/LLM \(Ранжирование\): Beta Chat/)).toBeInTheDocument();
      expect(screen.getByText(/Embeddings: Local/)).toBeInTheDocument();
      expect(screen.getByText(/Reranking: missing-rerank/)).toBeInTheDocument();
      expect(screen.getAllByText("Ключ не настроен").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Подключён").length).toBeGreaterThan(0);
    } finally {
      mocks.settings = originalSettings;
    }
  });

  it("shows successful 1C tests, reindex warnings, and hides matcher tuning when disabled", async () => {
    const user = userEvent.setup();
    vi.mocked(updateSettings).mockResolvedValueOnce({
      ...mocks.settings,
      onec: { ...mocks.settings.onec, enabled: true },
    } as never);
    render(<SettingsPage />);

    await user.click(screen.getByLabelText("Включить интеграцию с 1С"));
    await user.click(screen.getByRole("button", { name: "Проверить соединение" }));

    expect(await screen.findByText(/Успешное\s+подключение к 1С \(200\)/)).toBeInTheDocument();

    await user.clear(screen.getByPlaceholderText("Например: text-embedding-3-large"));
    await user.type(screen.getByPlaceholderText("Например: text-embedding-3-large"), "jina-embeddings-v4");

    expect(screen.getByText("Требуется переиндексация каталога")).toBeInTheDocument();
    expect(screen.getByText(/модель эмбеддингов/)).toBeInTheDocument();

    expect(screen.getByText("Модель LLM Matcher")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Включить LLM Matcher (прямое сопоставление через LLM)"));
    expect(screen.queryByText("Модель LLM Matcher")).not.toBeInTheDocument();
  });

  it("shows combined reindex warnings and beta embedding/rerank labels", async () => {
    const user = userEvent.setup();
    const originalSettings = mocks.settings;
    mocks.settings = {
      ...mocks.settings,
      embedding_provider: "beta-embed",
      rerank_provider: "beta-rerank",
      providers_registry: [
        ...mocks.settings.providers_registry,
        {
          id: "beta-embed",
          name: "Beta Embed",
          api_key_set: true,
          base_url: "https://embed.example/v1",
          supports_chat: false,
          supports_embeddings: true,
          supports_rerank: false,
          rerank_mode: null,
          is_beta: true,
          notes: null,
        },
        {
          id: "beta-rerank",
          name: "Beta Rerank",
          api_key_set: true,
          base_url: "https://rerank.example/v1",
          supports_chat: false,
          supports_embeddings: false,
          supports_rerank: true,
          rerank_mode: "api",
          is_beta: true,
          notes: null,
        },
      ],
    };

    try {
      render(<SettingsPage />);

      expect(screen.getByText("Beta Embed (beta)")).toBeInTheDocument();
      expect(screen.getByText("Beta Rerank (beta)")).toBeInTheDocument();
      await user.clear(screen.getByPlaceholderText("Например: text-embedding-3-large"));
      await user.type(screen.getByPlaceholderText("Например: text-embedding-3-large"), "beta-embeddings-v2");
      fireEvent.change(screen.getByPlaceholderText("1024"), { target: { value: "512" } });

      expect(screen.getByText(/модель эмбеддингов и размерность векторов/)).toBeInTheDocument();
    } finally {
      mocks.settings = originalSettings;
    }
  });

  it("updates decision threshold labels from sliders", async () => {
    render(<SettingsPage />);

    const sliders = screen.getAllByRole("slider");
    fireEvent.change(sliders[0], { target: { value: "0.8" } });
    fireEvent.change(sliders[1], { target: { value: "0.2" } });

    expect(screen.getAllByText("80%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("20%").length).toBeGreaterThan(0);
    expect(screen.getByText("Не найдено")).toBeInTheDocument();
    expect(screen.getByText("На проверку")).toBeInTheDocument();
    expect(screen.getByText("Авто")).toBeInTheDocument();
  });

  it("renders settings fallbacks for missing model lists and blank provider selection", async () => {
    const user = userEvent.setup();
    const originalSettings = mocks.settings;
    mocks.modelsData = undefined;
    mocks.settings = {
      ...mocks.settings,
      auto_match_threshold: 0.95,
      review_threshold: 0.9,
    };

    try {
      render(<SettingsPage />);

      expect(screen.getByText("Провайдеры ИИ (LLM & Embeddings)")).toBeInTheDocument();
      await user.click(screen.getAllByRole("button", { name: "select blank" })[0]);
      await user.click(screen.getByRole("button", { name: "Сохранить настройки" }));

      await waitFor(() =>
        expect(updateSettings).toHaveBeenCalledWith(
          expect.objectContaining({ llm_provider: "" }),
        ),
      );
    } finally {
      mocks.settings = originalSettings;
    }
  });

  it("renders settings with no loaded settings payload and reset fallback", async () => {
    const user = userEvent.setup();
    const originalSettings = mocks.settings;
    mocks.settings = undefined as never;

    try {
      render(<SettingsPage />);

      expect(screen.getByText("Провайдеры ИИ (LLM & Embeddings)")).toBeInTheDocument();
      expect(screen.getByPlaceholderText("Например: gpt-4o-mini")).toHaveValue("");
      await user.type(screen.getByPlaceholderText("Например: gpt-4o-mini"), "fallback-model");
      await user.click(screen.getByRole("button", { name: "Отменить изменения" }));
      expect(screen.getByPlaceholderText("Например: gpt-4o-mini")).toHaveValue("");
    } finally {
      mocks.settings = originalSettings;
    }
  });

  it("hides narrow decision threshold labels and shows 1C error status codes", async () => {
    const user = userEvent.setup();
    vi.mocked(updateSettings).mockResolvedValueOnce({
      ...mocks.settings,
      onec: { ...mocks.settings.onec, enabled: true },
    } as never);
    vi.mocked(testOneCConnection).mockResolvedValueOnce({
      status: "error",
      detail: "bad gateway",
      http_status: 503,
    });
    render(<SettingsPage />);

    const sliders = screen.getAllByRole("slider");
    fireEvent.change(sliders[1], { target: { value: "0.1" } });
    expect(screen.queryByText("Не найдено")).not.toBeInTheDocument();

    fireEvent.change(sliders[1], { target: { value: "0.9" } });
    fireEvent.change(sliders[0], { target: { value: "0.95" } });
    expect(screen.queryByText("На проверку")).not.toBeInTheDocument();
    expect(screen.queryByText("Авто")).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("Включить интеграцию с 1С"));
    await user.click(screen.getByRole("button", { name: "Проверить соединение" }));

    expect(await screen.findByText(/Ошибка: bad gateway\s+\(503\)/)).toBeInTheDocument();
  });

  it("uses unknown 1C test error fallbacks", async () => {
    const user = userEvent.setup();
    vi.mocked(updateSettings).mockResolvedValueOnce({
      ...mocks.settings,
      onec: { ...mocks.settings.onec, enabled: true },
    } as never);
    vi.mocked(testOneCConnection).mockRejectedValueOnce(undefined);
    render(<SettingsPage />);

    await user.click(screen.getByLabelText("Включить интеграцию с 1С"));
    await user.click(screen.getByRole("button", { name: "Проверить соединение" }));

    expect(await screen.findByText(/Ошибка: Неизвестная ошибка/)).toBeInTheDocument();
  });

  it("warns when embedding dimensions change and allows clean navigation without prompts", () => {
    render(<SettingsPage />);

    const cleanBeforeUnload = new Event("beforeunload", { cancelable: true }) as BeforeUnloadEvent;
    expect(window.dispatchEvent(cleanBeforeUnload)).toBe(true);
    expect(cleanBeforeUnload.defaultPrevented).toBe(false);

    fireEvent.change(screen.getByPlaceholderText("1024"), { target: { value: "512" } });

    expect(screen.getByText("Требуется переиндексация каталога")).toBeInTheDocument();
    expect(screen.getByText(/размерность векторов/)).toBeInTheDocument();
  });

  it("renders pending settings and connection controls", () => {
    const originalSettings = mocks.settings;
    mocks.mutationPending = true;
    mocks.settings = {
      ...mocks.settings,
      onec: { ...mocks.settings.onec, enabled: true },
    };

    try {
      render(<SettingsPage />);

      expect(screen.getByRole("button", { name: "Тестируем..." })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Сохранение..." })).toBeDisabled();
      expect(screen.getAllByRole("button", { name: "Выберите провайдера" })[0]).toBeDisabled();
    } finally {
      mocks.settings = originalSettings;
      mocks.mutationPending = false;
    }
  });

  it("updates optional settings branches for reranking and agentic resolution", async () => {
    const user = userEvent.setup();
    render(<SettingsPage />);

    await user.clear(screen.getByPlaceholderText("Например: gpt-4o-mini"));
    await user.type(screen.getByPlaceholderText("Например: gpt-4o-mini"), "gpt-test");
    await user.click(screen.getAllByRole("button", { name: "select active" })[0]);
    await user.click(screen.getAllByRole("button", { name: "select blank" })[1]);
    await user.type(screen.getByPlaceholderText("Например: BAAI/bge-reranker-v2-m3"), "-custom");
    await user.click(screen.getByLabelText("Включить Agentic Resolution (Web Search / Catalog Fallback)"));
    await user.click(screen.getAllByRole("button", { name: "select llm fallback" })[2]);

    expect(screen.getByText(/Reranking: LLM Fallback/)).toBeInTheDocument();
    expect(screen.getAllByText("Подключён").length).toBeGreaterThanOrEqual(1);

    await user.click(screen.getAllByRole("button", { name: "select blank" })[2]);
    expect(screen.getByText(/Reranking:/)).toBeInTheDocument();
    expect(screen.getByText(/Без реранкера система сортирует/)).toBeInTheDocument();
  });

  it("runs catalog actions, filtering, upload confirmation, and deletes", async () => {
    const user = userEvent.setup();
    render(<CatalogPage />);

    expect(screen.getByText("Pump alpha")).toBeInTheDocument();
    expect(screen.getByText("Индекс неполный (50%)")).toBeInTheDocument();

    await user.type(
      screen.getByPlaceholderText("Поиск по артикулу, наименованию, бренду, категории..."),
      "pump",
    );
    await user.click(screen.getByRole("button", { name: "Искать" }));
    expect(screen.getByDisplayValue("pump")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Синхронизировать с 1С" }));
    await waitFor(() => expect(importFromOnec).toHaveBeenCalledTimes(1));
    expect(toast.success).toHaveBeenCalledWith("Импорт из 1С запущен (в фоне)");
    expect(screen.getByText("Синхронизация запущена")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Обновить индекс поиска" }));
    await waitFor(() => expect(reindexCatalog).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: "Загрузить из файла" }));
    expect(screen.getByText("Загрузка каталога из файла")).toBeInTheDocument();
    const fileInput = document.querySelector<HTMLInputElement>("input[type='file']")!;
    await user.upload(fileInput, new File(["name\nPump"], "catalog.csv", { type: "text/csv" }));
    expect(screen.getByText(/catalog.csv/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Загрузить" }));
    await waitFor(() => expect(uploadCatalogFile).toHaveBeenCalledWith(expect.any(File)));

    await user.click(screen.getAllByLabelText("Выбрать Pump alpha")[0]);
    expect(screen.getByText("Выбрано: 1")).toBeInTheDocument();
    await user.click(screen.getAllByLabelText("Выбрать Pump alpha")[0]);
    expect(screen.queryByText("Выбрано: 1")).not.toBeInTheDocument();
    await user.click(screen.getAllByLabelText("Выбрать Pump alpha")[0]);
    await user.click(screen.getByRole("button", { name: "Удалить выбранные (1)" }));
    expect(screen.getByText("Удалить выбранные товары?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Удалить (1)" }));
    await waitFor(() => expect(deleteCatalogProduct).toHaveBeenCalledWith("p1"));

    await user.click(screen.getAllByRole("button", { name: "Развернуть" })[0]);
    expect(screen.getByText("Доступен для маппинга")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Свернуть" }));
    expect(screen.queryByText("Доступен для маппинга")).not.toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Развернуть" })[0]);
    await user.click(screen.getByRole("button", { name: "Удалить товар" }));
    expect(screen.getByText("Удалить товар из каталога?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Удалить безвозвратно" }));
    await waitFor(() => expect(deleteCatalogProduct).toHaveBeenCalledWith("p1"));
  });

  it("filters catalog status, shows index states, cancels uploads, and reports bulk delete errors", async () => {
    const user = userEvent.setup();
    vi.mocked(deleteCatalogProduct)
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error("locked"));
    const { rerender } = render(<CatalogPage />);

    await user.click(screen.getByRole("button", { name: "select archive" }));
    expect(screen.queryByText("Pump alpha")).not.toBeInTheDocument();
    expect(screen.getByText("Valve archive")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "select active" }));
    expect(screen.getByText("Pump alpha")).toBeInTheDocument();
    expect(screen.queryByText("Valve archive")).not.toBeInTheDocument();

    mocks.stats = {
      total_products: 2,
      embedded_products: 2,
      embedding_model: "jina-embeddings-v3",
      embedding_coverage_pct: 100,
      onec_connected: true,
    };
    rerender(<CatalogPage />);
    expect(screen.getByText("Индекс актуален")).toBeInTheDocument();

    mocks.stats = {
      total_products: 2,
      embedded_products: 0,
      embedding_model: "jina-embeddings-v3",
      embedding_coverage_pct: 0,
      onec_connected: true,
    };
    rerender(<CatalogPage />);
    expect(screen.getByText("Индекс не построен")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Загрузить из файла" }));
    const fileInput = document.querySelector<HTMLInputElement>("input[type='file']")!;
    await user.upload(fileInput, new File(["name\nPump"], "cancel.csv", { type: "text/csv" }));
    expect(screen.getByText(/cancel.csv/)).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Отмена" }).at(-1)!);
    expect(uploadCatalogFile).not.toHaveBeenCalled();

    mocks.products = mocks.products.map((product) => ({ ...product, is_active: true }));
    rerender(<CatalogPage />);
    await user.click(screen.getByRole("checkbox", { name: "Выбрать все на странице" }));
    await user.click(screen.getByRole("button", { name: "Удалить выбранные (2)" }));
    await user.click(screen.getByRole("button", { name: "Удалить (2)" }));
    await waitFor(() => expect(deleteCatalogProduct).toHaveBeenCalledTimes(2));
    expect(toast.success).toHaveBeenCalledWith("Удалено товаров: 1");
    expect(toast.error).toHaveBeenCalledWith("Не удалось удалить: 1");
  });

  it("renders pending catalog action controls", () => {
    mocks.mutationPending = true;
    try {
      render(<CatalogPage />);

      expect(screen.getByRole("button", { name: "Синхронизировать с 1С" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Загрузка..." })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Индексация запущена..." })).toBeDisabled();
      expect(document.querySelectorAll(".lucide-loader-circle").length).toBeGreaterThanOrEqual(3);
    } finally {
      mocks.mutationPending = false;
    }
  });

  it("reports all bulk delete failures without a success toast", async () => {
    const user = userEvent.setup();
    mocks.products = mocks.products.map((product) => ({ ...product, is_active: true }));
    vi.mocked(deleteCatalogProduct).mockRejectedValue(new Error("locked"));
    render(<CatalogPage />);

    await user.click(screen.getByRole("checkbox", { name: "Выбрать все на странице" }));
    await user.click(screen.getByRole("button", { name: "Удалить выбранные (2)" }));
    await user.click(screen.getByRole("button", { name: "Удалить (2)" }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Не удалось удалить: 2"),
    );
    expect(toast.success).not.toHaveBeenCalledWith(expect.stringMatching(/^Удалено товаров:/));
  });

  it("renders catalog loading, error, and empty states", () => {
    mocks.queryLoading.add("catalog-stats");
    mocks.queryLoading.add("catalog-search");
    mocks.products = [];
    const { container, rerender } = render(<CatalogPage />);

    expect(container.querySelector('[data-slot="skeleton"]')).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Загрузка таблицы" })).toBeInTheDocument();

    mocks.queryLoading.clear();
    mocks.queryErrors.set("catalog-stats", new Error("stats offline"));
    rerender(<CatalogPage />);

    expect(screen.getByRole("alert")).toHaveTextContent("stats offline");
    expect(screen.getByText("Каталог пуст")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Поиск по артикулу, наименованию, бренду, категории..."), {
      target: { value: "missing" },
    });
    rerender(<CatalogPage />);
    expect(screen.getByText("Ничего не найдено")).toBeInTheDocument();
  });

  it("covers catalog retries, dialog close handlers, and empty file selections", async () => {
    const user = userEvent.setup();
    mocks.queryErrors.set("catalog-stats", new Error("stats offline"));
    const { rerender } = render(<CatalogPage />);

    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(mocks.invalidateQueries).toHaveBeenCalled();

    mocks.queryErrors.clear();
    rerender(<CatalogPage />);
    await waitFor(() => expect(searchCatalog).toHaveBeenCalledWith("", 500));
    fireEvent.change(screen.getByPlaceholderText("Поиск по артикулу, наименованию, бренду, категории..."), {
      target: { value: "Pump" },
    });
    await waitFor(() => expect(searchCatalog).toHaveBeenCalledWith("Pump", 500));

    const fileInput = document.querySelector<HTMLInputElement>("input[type='file']")!;
    const clickSpy = vi.spyOn(fileInput, "click").mockImplementation(() => undefined);
    fireEvent.change(fileInput, { target: { files: [] } });
    await user.click(screen.getByRole("button", { name: "Загрузить из файла" }));
    await user.click(screen.getByRole("button", { name: "close dialog" }));
    expect(screen.queryByText("Загрузка каталога из файла")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Загрузить из файла" }));
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(screen.queryByText("Загрузка каталога из файла")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Загрузить из файла" }));
    await user.click(screen.getByRole("button", { name: "Выбрать файл" }));
    expect(clickSpy).toHaveBeenCalledTimes(1);

    await user.upload(fileInput, new File(["name\nPump"], "close.csv", { type: "text/csv" }));
    expect(screen.getByText(/close.csv/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "close dialog" }));
    expect(screen.queryByText(/close.csv/)).not.toBeInTheDocument();

    await user.click(screen.getAllByLabelText("Выбрать Pump alpha")[0]);
    await user.click(screen.getByRole("button", { name: "Удалить выбранные (1)" }));
    expect(screen.getByText("Удалить выбранные товары?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "close dialog" }));
    expect(screen.queryByText("Удалить выбранные товары?")).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Выбрать все на странице" }));
    await user.click(screen.getByRole("checkbox", { name: "Выбрать все на странице" }));
    expect(screen.queryByText(/Удалить выбранные/)).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Развернуть" })[0]);
    await user.click(screen.getByRole("button", { name: "Удалить товар" }));
    expect(screen.getByText("Удалить товар из каталога?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "close dialog" }));
    expect(screen.queryByText("Удалить товар из каталога?")).not.toBeInTheDocument();
  });

  it("invalidates catalog stats while reindex polling is active", async () => {
    vi.useFakeTimers();
    try {
      render(<CatalogPage />);

      fireEvent.click(screen.getByRole("button", { name: "Обновить индекс поиска" }));
      await act(async () => {
        await Promise.resolve();
      });
      expect(reindexCatalog).toHaveBeenCalledTimes(1);

      act(() => {
        vi.advanceTimersByTime(5_000);
      });

      expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["catalog-stats"] });

      act(() => {
        vi.advanceTimersByTime(120_000);
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it("reports catalog action failures and metadata fallbacks", async () => {
    const user = userEvent.setup();
    vi.mocked(importFromOnec).mockRejectedValueOnce(new Error("onec down"));
    vi.mocked(reindexCatalog).mockRejectedValueOnce(new Error("index down"));
    vi.mocked(uploadCatalogFile).mockRejectedValueOnce(new Error("upload denied"));
    vi.mocked(deleteCatalogProduct).mockRejectedValueOnce(new Error("delete denied"));
    mocks.products = [
      {
        product_id: "missing-meta",
        name: "No metadata product",
        article: undefined as unknown as string,
        brand: undefined as unknown as string,
        category_path: undefined as unknown as string,
        is_active: false,
      },
    ];

    render(<CatalogPage />);

    expect(screen.getByText("No metadata product")).toBeInTheDocument();
    expect(screen.getByText("Без категории")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Синхронизировать с 1С" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при запуске импорта: onec down"),
    );

    await user.click(screen.getByRole("button", { name: "Обновить индекс поиска" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при запуске переиндексации: index down"),
    );

    await user.click(screen.getByRole("button", { name: "Загрузить из файла" }));
    const fileInput = document.querySelector<HTMLInputElement>("input[type='file']")!;
    await user.upload(fileInput, new File(["name\nPump"], "bad.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "Загрузить" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при загрузке файла: upload denied"),
    );

    await user.click(screen.getByRole("button", { name: "Развернуть" }));
    expect(screen.getByText("Архивный (скрыт)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Удалить товар" }));
    await user.click(screen.getByRole("button", { name: "Удалить безвозвратно" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при удалении товара: delete denied"),
    );
  });

  it("reports catalog action fallback messages for non-error failures", async () => {
    const user = userEvent.setup();
    vi.mocked(importFromOnec).mockRejectedValueOnce("onec string failure");
    vi.mocked(reindexCatalog).mockRejectedValueOnce("index string failure");
    vi.mocked(uploadCatalogFile).mockRejectedValueOnce("upload string failure");
    vi.mocked(deleteCatalogProduct).mockRejectedValueOnce("delete string failure");
    render(<CatalogPage />);

    await user.click(screen.getByRole("button", { name: "Синхронизировать с 1С" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при запуске импорта: "),
    );

    await user.click(screen.getByRole("button", { name: "Обновить индекс поиска" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при запуске переиндексации: "),
    );

    await user.click(screen.getByRole("button", { name: "Загрузить из файла" }));
    const fileInput = document.querySelector<HTMLInputElement>("input[type='file']")!;
    await user.upload(fileInput, new File(["name\nPump"], "string-fail.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "Загрузить" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при загрузке файла: "),
    );

    await user.click(screen.getAllByRole("button", { name: "Развернуть" })[0]);
    await user.click(screen.getByRole("button", { name: "Удалить товар" }));
    await user.click(screen.getByRole("button", { name: "Удалить безвозвратно" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при удалении товара: "),
    );
  });

  it("renders catalog with missing query payloads and blank status fallback", async () => {
    const user = userEvent.setup();
    mocks.stats = undefined as never;
    mocks.products = undefined as never;
    render(<CatalogPage />);

    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("Каталог пуст")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "select blank" }));
    expect(screen.getByText("Каталог пуст")).toBeInTheDocument();
  });

  it("paginates catalog results and can clear page selections", async () => {
    const user = userEvent.setup();
    mocks.products = Array.from({ length: 30 }, (_, index) => ({
      product_id: `page-${index + 1}`,
      name: `Paged product ${index + 1}`,
      article: `P-${index + 1}`,
      brand: "Paged",
      category_path: "Page",
      is_active: true,
    }));

    render(<CatalogPage />);

    expect(screen.getByText("Paged product 1")).toBeInTheDocument();
    expect(screen.queryByText("Paged product 26")).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Выбрать все на странице" }));
    expect(screen.getByText("Выбрано: 25")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Снять выделение" }));
    expect(screen.queryByText("Выбрано: 25")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Следующая страница" }));
    expect(screen.getByText("Paged product 26")).toBeInTheDocument();
    expect(screen.queryByText("Paged product 1")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Предыдущая страница" }));
    expect(screen.getByText("Paged product 1")).toBeInTheDocument();
  });
});
