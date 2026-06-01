import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getMe } from "@/api/auth";
import { listMatchRequests } from "@/api/match";
import {
  createSupplier,
  deleteSupplier,
  listSupplierMappings,
  listSuppliers,
  updateSupplier,
} from "@/api/suppliers";
import {
  createUser,
  listUsers,
  resetUserPassword,
  updateUser,
} from "@/api/users";
import SuppliersPage from "@/pages/suppliers";
import UsersPage from "@/pages/users";
import Papa from "papaparse";
import { toast } from "sonner";

const mocks = vi.hoisted(() => ({
  invalidateQueries: vi.fn(),
  refetch: vi.fn(),
  clipboardWrite: vi.fn(),
  queryErrors: new Map<string, Error>(),
  queryLoading: new Set<string>(),
  mutationPending: false,
  users: {
    items: [
      {
        user_id: "u-current",
        username: "admin",
        full_name: "Admin User",
        role: "admin",
        is_active: true,
        must_change_password: false,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        last_login: "2026-01-02T00:00:00Z",
      },
      {
        user_id: "u-operator",
        username: "operator",
        full_name: "Operator User",
        role: "operator",
        is_active: true,
        must_change_password: false,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        last_login: null,
      },
    ],
  },
  suppliers: {
    items: [{ supplier_id: "s1", supplier_name: "ACME", strict_mode: false, is_active: true }],
  },
  mappings: [
    {
      supplier_raw_text: "Pump source",
      supplier_article: "A-1",
      product_id: "p-1",
      mapping_type: "manual",
      confidence: 1,
      is_active: true,
    },
  ],
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
  useQuery: ({ queryKey, queryFn }: { queryKey: unknown[]; queryFn: () => Promise<unknown> }) => {
    const key = String(queryKey[0]);
    try {
      void queryFn().catch(() => undefined);
    } catch {
      // Component tests use inline query data below.
    }
    const error = mocks.queryErrors.get(key);
    if (error) {
      return {
        data: undefined,
        isLoading: false,
        isError: true,
        error,
        refetch: mocks.refetch,
      };
    }
    const dataByKey: Record<string, unknown> = {
      me: { user_id: "u-current" },
      users: mocks.users,
      suppliers: mocks.suppliers,
      "supplier-mappings": mocks.mappings,
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

vi.mock("@/api/auth", () => ({
  getMe: vi.fn(),
}));

vi.mock("@/api/users", () => ({
  listUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  resetUserPassword: vi.fn(),
}));

vi.mock("@/api/suppliers", () => ({
  listSuppliers: vi.fn(),
  createSupplier: vi.fn(),
  updateSupplier: vi.fn(),
  deleteSupplier: vi.fn(),
  listSupplierMappings: vi.fn(),
}));

vi.mock("@/api/match", () => ({
  listMatchRequests: vi.fn(),
}));

vi.mock("papaparse", () => ({
  default: { unparse: vi.fn(() => "csv") },
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
        <button type="button" onClick={() => onValueChange("viewer")}>
          choose viewer
        </button>
      )}
    </div>
  ),
  SelectContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children, disabled }: { children: ReactNode; disabled?: boolean }) => (
    <button disabled={disabled}>{children}</button>
  ),
  SelectValue: () => <span>selected</span>,
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({
    children,
    onOpenChange,
  }: {
    children: ReactNode;
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
  }) => (
    <div>
      {children}
      {onOpenChange && (
        <>
          <button type="button" onClick={() => onOpenChange?.(true)}>
            keep dialog open
          </button>
          <button type="button" onClick={() => onOpenChange?.(false)}>
            close dialog
          </button>
        </>
      )}
    </div>
  ),
  DialogTrigger: ({ children, className }: { children: ReactNode; className?: string }) => (
    <button className={className}>{children}</button>
  ),
  DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
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
        <button type="button" onClick={() => onOpenChange?.(true)}>keep dialog open</button>
        <button type="button" onClick={() => onOpenChange?.(false)}>close dialog</button>
      </div>
    ) : null,
  AlertDialogAction: ({
    children,
    disabled,
    onClick,
  }: {
    children: ReactNode;
    disabled?: boolean;
    onClick?: () => void;
  }) => (
    <button disabled={disabled} onClick={onClick}>
      {children}
    </button>
  ),
  AlertDialogCancel: ({ children }: { children: ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  TooltipContent: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}));

describe("admin pages", () => {
  beforeEach(() => {
    mocks.invalidateQueries.mockClear();
    mocks.refetch.mockClear();
    mocks.clipboardWrite.mockClear();
    mocks.clipboardWrite.mockResolvedValue(undefined);
    mocks.queryErrors.clear();
    mocks.queryLoading.clear();
    mocks.mutationPending = false;
    mocks.users = {
      items: [
        {
          user_id: "u-current",
          username: "admin",
          full_name: "Admin User",
          role: "admin",
          is_active: true,
          must_change_password: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          last_login: "2026-01-02T00:00:00Z",
        },
        {
          user_id: "u-operator",
          username: "operator",
          full_name: "Operator User",
          role: "operator",
          is_active: true,
          must_change_password: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          last_login: null,
        },
      ],
    };
    mocks.suppliers = {
      items: [{ supplier_id: "s1", supplier_name: "ACME", strict_mode: false, is_active: true }],
    };
    mocks.mappings = [
      {
        supplier_raw_text: "Pump source",
        supplier_article: "A-1",
        product_id: "p-1",
        mapping_type: "manual",
        confidence: 1,
        is_active: true,
      },
    ];
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mocks.clipboardWrite },
    });
    vi.mocked(getMe).mockResolvedValue({ user_id: "u-current" } as never);
    vi.mocked(listUsers).mockResolvedValue(mocks.users as never);
    vi.mocked(createUser).mockResolvedValue(mocks.users.items[0] as never);
    vi.mocked(updateUser).mockResolvedValue(mocks.users.items[1] as never);
    vi.mocked(resetUserPassword).mockResolvedValue({ ok: true });
    vi.mocked(listSuppliers).mockResolvedValue(mocks.suppliers);
    vi.mocked(createSupplier).mockResolvedValue(mocks.suppliers.items[0]);
    vi.mocked(updateSupplier).mockResolvedValue(mocks.suppliers.items[0]);
    vi.mocked(deleteSupplier).mockResolvedValue({ ok: true });
    vi.mocked(listSupplierMappings).mockResolvedValue(mocks.mappings as never);
    vi.mocked(listMatchRequests).mockResolvedValue({ items: [{ request_id: "r1" }], total: 1 } as never);
    vi.mocked(Papa.unparse).mockClear();
    vi.mocked(toast).mockClear();
    vi.mocked(toast.success).mockClear();
    vi.mocked(toast.error).mockClear();
    URL.createObjectURL = vi.fn(() => "blob:csv");
    URL.revokeObjectURL = vi.fn();
  });

  it("creates, edits, deactivates, and resets users", async () => {
    const user = userEvent.setup();
    render(<UsersPage />);

    expect(screen.getByText("Admin User")).toBeInTheDocument();
    expect(screen.getByText("Operator User")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Имя пользователя"), "viewer1");
    await user.type(screen.getByPlaceholderText("Иванов Иван Иванович"), "Viewer One");
    await user.type(screen.getByLabelText("Временный пароль"), "secret123");
    await user.click(screen.getByRole("button", { name: "Создать" }));
    await waitFor(() =>
      expect(createUser).toHaveBeenCalledWith({
        username: "viewer1",
        full_name: "Viewer One",
        role: "operator",
        password: "secret123",
      }),
    );
    expect(toast.success).toHaveBeenCalledWith("Пользователь создан");

    await user.click(screen.getAllByRole("button", { name: "Изменить" })[1]);
    const editFullName = screen.getByDisplayValue("Operator User");
    await user.clear(editFullName);
    await user.type(editFullName, "Operator Updated");
    await user.click(screen.getAllByRole("button", { name: "Сохранить" }).at(-1)!);
    await waitFor(() =>
      expect(updateUser).toHaveBeenCalledWith("u-operator", {
        full_name: "Operator Updated",
        role: "operator",
      }),
    );

    await user.click(screen.getAllByRole("switch")[1]);
    expect(screen.getByText("Отключить пользователя?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Отключить" }));
    await waitFor(() =>
      expect(updateUser).toHaveBeenCalledWith("u-operator", { is_active: false }),
    );

    await user.click(screen.getAllByRole("button", { name: "Сбросить пароль" })[1]);
    expect(screen.getByText("Сбросить пароль?")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Новый временный пароль"));
    await user.type(screen.getByLabelText("Новый временный пароль"), "reset123");
    await user.click(screen.getAllByRole("button", { name: "Сбросить пароль" }).at(-1)!);
    await waitFor(() => expect(resetUserPassword).toHaveBeenCalledWith("u-operator", "reset123"));
  });

  it("generates temporary passwords, copies them, and shows role-change warnings", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup();
    try {
      Object.defineProperty(navigator.clipboard, "writeText", {
        configurable: true,
        value: mocks.clipboardWrite,
      });
      render(<UsersPage />);

      const createPasswordInput = screen.getByLabelText("Временный пароль");
      await user.click(createPasswordInput.parentElement!.querySelector("button")!);

      expect((createPasswordInput as HTMLInputElement).value).toHaveLength(12);
      await waitFor(() => expect(mocks.clipboardWrite).toHaveBeenCalledTimes(1));
      act(() => {
        vi.advanceTimersByTime(2_000);
      });
      expect(toast.success).toHaveBeenCalledWith("Пароль скопирован в буфер обмена");
      expect(
        screen.getByText(
          "Скопируйте пароль и передайте его пользователю. После закрытия окна пароль не будет доступен.",
        ),
      ).toBeInTheDocument();

      expect(screen.getAllByRole("switch")[0]).toBeDisabled();

      await user.click(screen.getAllByRole("button", { name: "Изменить" })[1]);
      await user.click(screen.getAllByRole("button", { name: "choose viewer" }).at(-1)!);
      expect(
        screen.getByText("Изменение роли вступит в силу при следующем входе пользователя."),
      ).toBeInTheDocument();
      await user.click(screen.getAllByRole("button", { name: "Сохранить" }).at(-1)!);
      await waitFor(() =>
        expect(updateUser).toHaveBeenCalledWith("u-operator", {
          full_name: "Operator User",
          role: "viewer",
        }),
      );

      await user.click(screen.getAllByRole("button", { name: "Сбросить пароль" })[1]);
      const resetPasswordInput = screen.getByLabelText("Новый временный пароль");
      expect((resetPasswordInput as HTMLInputElement).value).toHaveLength(12);

      await user.clear(resetPasswordInput);
      await user.type(resetPasswordInput, "short");
      expect(screen.getAllByRole("button", { name: "Сбросить пароль" }).at(-1)!).toBeDisabled();

      await user.clear(resetPasswordInput);
      await user.type(resetPasswordInput, "longer1");
      await user.click(resetPasswordInput.parentElement!.querySelector("button")!);
      expect(mocks.clipboardWrite).toHaveBeenLastCalledWith("longer1");
      expect(toast.success).toHaveBeenCalledWith("Скопировано");
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders users loading, error, empty, validation, current-user, reactivation, and failure states", async () => {
    const user = userEvent.setup();
    mocks.queryLoading.add("users");
    const { rerender } = render(<UsersPage />);

    expect(screen.getByRole("status", { name: "Загрузка таблицы" })).toBeInTheDocument();

    mocks.queryLoading.clear();
    mocks.queryErrors.set("users", new Error("users offline"));
    rerender(<UsersPage />);
    expect(screen.getByText("users offline")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(mocks.refetch).toHaveBeenCalled();

    mocks.queryErrors.clear();
    mocks.users = { items: [] };
    rerender(<UsersPage />);
    expect(screen.getByText("Нет пользователей")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Создать" }));
    expect(toast.error).toHaveBeenCalledWith("Заполните обязательные поля");

    vi.mocked(createUser).mockRejectedValueOnce(new Error("create denied"));
    await user.type(screen.getByLabelText("Имя пользователя"), "viewer2");
    await user.type(screen.getByLabelText("Временный пароль"), "secret123");
    await user.click(screen.getAllByRole("button", { name: "choose viewer" })[0]);
    await user.click(screen.getByRole("button", { name: "Создать" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при создании пользователя: create denied"),
    );

    mocks.users = {
      items: [
        {
          user_id: "u-current",
          username: "admin",
          full_name: "",
          role: "admin",
          is_active: true,
          must_change_password: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          last_login: null,
        },
        {
          user_id: "u-disabled",
          username: "disabled",
          full_name: "",
          role: "custom",
          is_active: false,
          must_change_password: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          last_login: null,
        },
      ],
    };
    vi.mocked(updateUser).mockRejectedValueOnce(new Error("save failed"));
    rerender(<UsersPage />);
    expect(screen.getByText("custom")).toBeInTheDocument();
    expect(screen.getByText("Отключён")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Изменить" })[0]);
    expect(screen.getByText("Нельзя изменить свою роль.")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Сохранить" }).at(-1)!);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Ошибка при сохранении: save failed"));

    await user.click(screen.getAllByRole("switch")[1]);
    await waitFor(() => expect(updateUser).toHaveBeenCalledWith("u-disabled", { is_active: true }));

    vi.mocked(resetUserPassword).mockRejectedValueOnce(new Error("reset failed"));
    await user.click(screen.getAllByRole("button", { name: "Сбросить пароль" })[1]);
    await user.click(screen.getAllByRole("button", { name: "Сбросить пароль" }).at(-1)!);
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при сбросе пароля: reset failed"),
    );
  });

  it("handles user mutation fallback errors and empty optional names", async () => {
    const user = userEvent.setup();
    mocks.users = {
      items: [
        {
          user_id: "u-current",
          username: "admin",
          full_name: "Admin User",
          role: "admin",
          is_active: true,
          must_change_password: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          last_login: "2026-01-02T00:00:00Z",
        },
        {
          user_id: "u-empty",
          username: "emptyname",
          full_name: undefined as unknown as string,
          role: "operator",
          is_active: true,
          must_change_password: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          last_login: null,
        },
      ],
    };
    vi.mocked(createUser).mockRejectedValueOnce("create string failure");
    vi.mocked(updateUser).mockRejectedValueOnce("update string failure");
    vi.mocked(resetUserPassword).mockRejectedValueOnce("reset string failure");
    render(<UsersPage />);

    await user.type(screen.getByLabelText("Имя пользователя"), "viewer3");
    await user.type(screen.getByLabelText("Временный пароль"), "secret123");
    await user.click(screen.getByRole("button", { name: "Создать" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Ошибка при создании пользователя: Неизвестная ошибка",
      ),
    );
    expect(createUser).toHaveBeenCalledWith(
      expect.objectContaining({ full_name: undefined }),
    );

    await user.click(screen.getAllByRole("button", { name: "Изменить" })[1]);
    await user.click(screen.getAllByRole("button", { name: "Сохранить" }).at(-1)!);
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при сохранении: Неизвестная ошибка"),
    );
    expect(updateUser).toHaveBeenCalledWith(
      "u-empty",
      expect.objectContaining({ full_name: undefined }),
    );

    await user.click(screen.getAllByRole("button", { name: "Сбросить пароль" })[1]);
    await user.click(screen.getAllByRole("button", { name: "Сбросить пароль" }).at(-1)!);
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Ошибка при сбросе пароля: Неизвестная ошибка",
      ),
    );
    expect(screen.getAllByText("emptyname").length).toBeGreaterThan(1);
  });

  it("renders pending user mutation controls", async () => {
    const user = userEvent.setup();
    mocks.mutationPending = true;
    render(<UsersPage />);

    expect(screen.getAllByRole("button", { name: /Создать/ }).at(-1)!).toBeDisabled();

    await user.click(screen.getAllByRole("button", { name: "Изменить" })[1]);
    expect(screen.getAllByRole("button", { name: /Сохранить/ }).at(-1)!).toBeDisabled();

    await user.click(screen.getAllByRole("button", { name: "Сбросить пароль" })[1]);
    expect(screen.getAllByRole("button", { name: "Сбросить пароль" }).at(-1)!).toBeDisabled();

    mocks.mutationPending = false;
  });

  it("renders pending supplier create controls", async () => {
    mocks.mutationPending = true;
    render(<SuppliersPage />);

    await userEvent.type(screen.getByLabelText("ID (Системный код)"), "pending_supplier");
    await userEvent.type(screen.getByLabelText("Наименование"), "Pending Supplier");
    expect(screen.getByRole("button", { name: /Создать/ })).toBeDisabled();

    mocks.mutationPending = false;
  });

  it("creates, updates, expands, exports, deactivates, and deletes suppliers", async () => {
    const user = userEvent.setup();
    const anchor = document.createElement("a");
    const click = vi.spyOn(anchor, "click").mockImplementation(() => undefined);
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName) => {
      if (tagName === "a") return anchor;
      return originalCreateElement(tagName);
    });

    render(<SuppliersPage />);

    await user.type(screen.getByLabelText("ID (Системный код)"), "new_supplier");
    await user.type(screen.getByLabelText("Наименование"), "New Supplier");
    await user.click(screen.getByRole("button", { name: "Создать" }));
    await waitFor(() =>
      expect(createSupplier).toHaveBeenCalledWith({
        supplier_id: "new_supplier",
        supplier_name: "New Supplier",
        strict_mode: false,
      }),
    );

    await user.click(screen.getByRole("button", { name: "Редактировать название" }));
    const supplierNameInput = screen.getByDisplayValue("ACME");
    await user.clear(supplierNameInput);
    await user.type(supplierNameInput, "ACME Updated");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(updateSupplier).toHaveBeenCalledWith("s1", { supplier_name: "ACME Updated" }),
    );

    await user.click(screen.getByRole("button", { name: "Развернуть" }));
    expect(screen.getByText("Маппинги (1)")).toBeInTheDocument();
    expect(screen.getByText("Pump source")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "CSV" }));
    expect(Papa.unparse).toHaveBeenCalledWith([
      {
        "Исходный текст поставщика": "Pump source",
        "Артикул поставщика": "A-1",
        "ID целевого товара": "p-1",
      },
    ]);
    expect(anchor.download).toBe("mappings-s1.csv");
    expect(click).toHaveBeenCalledTimes(1);

    await user.click(screen.getAllByRole("switch")[1]);
    await waitFor(() => expect(listMatchRequests).toHaveBeenCalledTimes(2));
    expect(screen.getByText(/есть 2 активных запросов/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Отключить" }));
    await waitFor(() => expect(updateSupplier).toHaveBeenCalledWith("s1", { is_active: false }));

    await user.click(screen.getByRole("button", { name: "Удалить поставщика" }));
    expect(screen.getByText("Удалить поставщика?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Удалить безвозвратно" }));
    await waitFor(() => expect(deleteSupplier).toHaveBeenCalledWith("s1"));
  });

  it("renders suppliers loading, error, empty, validation, mapping, and mutation failure states", async () => {
    const user = userEvent.setup();
    mocks.queryLoading.add("suppliers");
    const { rerender } = render(<SuppliersPage />);

    expect(screen.getByRole("status", { name: "Загрузка таблицы" })).toBeInTheDocument();

    mocks.queryLoading.clear();
    mocks.queryErrors.set("suppliers", new Error("suppliers offline"));
    rerender(<SuppliersPage />);
    expect(screen.getByText("Ошибка загрузки поставщиков")).toBeInTheDocument();
    expect(screen.getByText("suppliers offline")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(mocks.refetch).toHaveBeenCalled();

    mocks.queryErrors.clear();
    mocks.suppliers = { items: [] };
    rerender(<SuppliersPage />);
    expect(screen.getByText("Нет поставщиков")).toBeInTheDocument();

    await user.type(screen.getByLabelText("ID (Системный код)"), "bad-id!");
    await user.type(screen.getByLabelText("Наименование"), "Bad Supplier");
    expect(screen.getByText("Только латиница, цифры и подчеркивания")).toBeInTheDocument();

    vi.mocked(createSupplier).mockRejectedValueOnce(new Error("create supplier denied"));
    await user.clear(screen.getByLabelText("ID (Системный код)"));
    await user.type(screen.getByLabelText("ID (Системный код)"), "good_supplier");
    await user.click(screen.getByRole("button", { name: "Создать" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Ошибка при добавлении поставщика: create supplier denied",
      ),
    );

    vi.mocked(createSupplier).mockRejectedValueOnce("create supplier string failure");
    await user.click(screen.getByRole("button", { name: "Создать" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Ошибка при добавлении поставщика: Неизвестная ошибка",
      ),
    );

    mocks.suppliers = {
      items: [{ supplier_id: "s2", supplier_name: "Beta", strict_mode: true, is_active: false }],
    };
    mocks.mappings = [];
    rerender(<SuppliersPage />);
    expect(screen.getByText("Отключен")).toBeInTheDocument();
    expect(screen.getByText("Вкл")).toBeInTheDocument();

    vi.mocked(updateSupplier).mockRejectedValueOnce(new Error("strict failed"));
    await user.click(screen.getAllByRole("switch")[0]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Ошибка при сохранении: strict failed"));

    vi.mocked(updateSupplier).mockRejectedValueOnce("strict string failure");
    await user.click(screen.getAllByRole("switch")[0]);
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при сохранении: Неизвестная ошибка"),
    );

    await user.click(screen.getByRole("button", { name: "Развернуть" }));
    expect(screen.getByText("Нет маппингов")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Свернуть" }));

    mocks.mappings = Array.from({ length: 55 }, (_, index) => ({
      supplier_raw_text: `Pump ${index}`,
      supplier_article: index % 2 === 0 ? `A-${index}` : "",
      product_id: `p-${index}`,
      mapping_type: "manual",
      confidence: 1,
      is_active: true,
    }));
    rerender(<SuppliersPage />);
    await user.click(screen.getByRole("button", { name: "Развернуть" }));
    expect(screen.getByText("Показаны 50 из 55 маппингов")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(screen.getByText("Показаны 55 из 55 маппингов")).toBeInTheDocument();
    await user.clear(screen.getByPlaceholderText("Поиск по маппингам..."));
    await user.type(screen.getByPlaceholderText("Поиск по маппингам..."), "Pump");
    expect(screen.getByText("Показаны 50 из 55 маппингов")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(screen.getByText("Показаны 55 из 55 маппингов")).toBeInTheDocument();
    await user.clear(screen.getByPlaceholderText("Поиск по маппингам..."));
    await user.type(screen.getByPlaceholderText("Поиск по маппингам..."), "Pump 54");
    expect(screen.getByText("Найдено: 1 из 55")).toBeInTheDocument();

    vi.mocked(listMatchRequests).mockRejectedValueOnce(new Error("queued down")).mockRejectedValueOnce(new Error("running down"));
    await user.click(screen.getAllByRole("switch")[1]);
    expect(screen.queryByText(/активных запросов/)).not.toBeInTheDocument();

    vi.mocked(deleteSupplier).mockRejectedValueOnce(new Error("delete failed"));
    await user.click(screen.getByRole("button", { name: "Удалить поставщика" }));
    await user.click(screen.getByRole("button", { name: "Удалить безвозвратно" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Не удалось удалить поставщика: delete failed"),
    );

    vi.mocked(deleteSupplier).mockRejectedValueOnce("delete string failure");
    await user.click(screen.getByRole("button", { name: "Удалить поставщика" }));
    await user.click(screen.getByRole("button", { name: "Удалить безвозвратно" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Не удалось удалить поставщика: Неизвестная ошибка"),
    );
  });

  it("covers supplier cancel flows, mapping loading/fallback rows, and zero-request deactivation", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<SuppliersPage />);

    const supplierIdInput = screen.getByLabelText("ID (Системный код)");
    const supplierNameInput = screen.getByLabelText("Наименование");
    await user.type(supplierIdInput, "cancel_supplier");
    await user.type(supplierNameInput, "Cancel Supplier");
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(supplierIdInput).toHaveValue("");
    expect(supplierNameInput).toHaveValue("");

    await user.click(screen.getByRole("button", { name: "Редактировать название" }));
    expect(screen.getByDisplayValue("ACME")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Отменить редактирование" }));
    expect(screen.queryByDisplayValue("ACME")).not.toBeInTheDocument();

    mocks.queryLoading.add("supplier-mappings");
    rerender(<SuppliersPage />);
    await user.click(screen.getAllByRole("button", { name: "Развернуть" })[0]);
    expect(screen.getByRole("status", { name: "Загрузка таблицы" })).toBeInTheDocument();

    mocks.queryLoading.clear();
    mocks.mappings = [
      {
        supplier_raw_text: null as never,
        supplier_article: null as never,
        product_id: null as never,
        mapping_type: "manual",
        confidence: 1,
        is_active: true,
      },
      {
        supplier_raw_text: "Article only",
        supplier_article: "B-2",
        product_id: "target-product",
        mapping_type: "manual",
        confidence: 1,
        is_active: true,
      },
    ];
    rerender(<SuppliersPage />);
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
    await user.click(screen.getByRole("button", { name: "CSV" }));
    expect(Papa.unparse).toHaveBeenLastCalledWith([
      {
        "Исходный текст поставщика": "",
        "Артикул поставщика": "",
        "ID целевого товара": "",
      },
      {
        "Исходный текст поставщика": "Article only",
        "Артикул поставщика": "B-2",
        "ID целевого товара": "target-product",
      },
    ]);
    await user.type(screen.getByPlaceholderText("Поиск по маппингам..."), "target-product");
    expect(screen.getByText("Найдено: 1 из 2")).toBeInTheDocument();
    await user.clear(screen.getByPlaceholderText("Поиск по маппингам..."));
    await user.type(screen.getByPlaceholderText("Поиск по маппингам..."), "B-2");
    expect(screen.getByText("Найдено: 1 из 2")).toBeInTheDocument();

    vi.mocked(listMatchRequests)
      .mockResolvedValueOnce({} as never)
      .mockResolvedValueOnce({} as never);
    await user.click(screen.getAllByRole("switch")[1]);
    expect(screen.getByText("Отключить поставщика?")).toBeInTheDocument();
    expect(screen.queryByText(/активных запросов/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Отключить" }));
    await waitFor(() => expect(updateSupplier).toHaveBeenCalledWith("s1", { is_active: false }));
  });

  it("renders supplier mapping fallback when mapping data is absent", async () => {
    const user = userEvent.setup();
    mocks.mappings = undefined as never;

    render(<SuppliersPage />);

    await user.click(screen.getByRole("button", { name: "Развернуть" }));
    expect(screen.getByText("Нет маппингов")).toBeInTheDocument();
  });

  it("covers admin dialog close handlers and query functions", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<UsersPage />);

    await waitFor(() => {
      expect(getMe).toHaveBeenCalled();
      expect(listUsers).toHaveBeenCalled();
    });

    await user.click(screen.getAllByRole("button", { name: "keep dialog open" })[0]);
    vi.mocked(updateUser).mockClear();
    fireEvent.submit(screen.getByText("Редактировать пользователя").closest("form")!);
    expect(updateUser).not.toHaveBeenCalled();

    await user.click(screen.getAllByRole("button", { name: "Отмена" })[0]);

    await user.click(screen.getAllByRole("button", { name: "Изменить" })[1]);
    expect(screen.getByDisplayValue("Operator User")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "close dialog" }).at(-1)!);
    await user.click(screen.getAllByRole("button", { name: "Изменить" })[1]);
    await user.click(screen.getAllByRole("button", { name: "Отмена" }).at(-1)!);

    await user.click(screen.getAllByRole("button", { name: "Сбросить пароль" })[1]);
    expect(screen.getByText("Сбросить пароль?")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "close dialog" }).at(-1)!);
    expect(screen.queryByText("Сбросить пароль?")).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("switch")[1]);
    expect(screen.getByText("Отключить пользователя?")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "close dialog" }).at(-1)!);
    expect(screen.queryByText("Отключить пользователя?")).not.toBeInTheDocument();

    rerender(<SuppliersPage />);
    await waitFor(() => {
      expect(listSuppliers).toHaveBeenCalled();
      expect(listSupplierMappings).toHaveBeenCalledWith("s1", 500);
    });

    await user.click(screen.getAllByRole("button", { name: "keep dialog open" })[0]);
    fireEvent.submit(screen.getByLabelText("ID (Системный код)").closest("form")!);
    expect(toast.error).toHaveBeenCalledWith("Заполните обязательные поля");

    await user.type(screen.getByLabelText("ID (Системный код)"), "bad-id!");
    await user.type(screen.getByLabelText("Наименование"), "Bad Supplier");
    fireEvent.submit(screen.getByLabelText("ID (Системный код)").closest("form")!);
    expect(toast.error).toHaveBeenCalledWith("Недопустимый формат ID");

    vi.mocked(listMatchRequests)
      .mockResolvedValueOnce({ items: [], total: 0 } as never)
      .mockResolvedValueOnce({ items: [], total: 0 } as never);
    await user.click(screen.getAllByRole("switch")[1]);
    expect(screen.getByText("Отключить поставщика?")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "keep dialog open" }).at(-1)!);
    await user.click(screen.getAllByRole("button", { name: "close dialog" }).at(-1)!);
    expect(screen.queryByText("Отключить поставщика?")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Удалить поставщика" }));
    expect(screen.getByText("Удалить поставщика?")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "close dialog" }).at(-1)!);
    expect(screen.queryByText("Удалить поставщика?")).not.toBeInTheDocument();
  });
});
