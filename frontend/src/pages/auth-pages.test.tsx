import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { login } from "@/api/auth";
import {
  deleteMatchRequest,
  getMatchRequest,
  getReviewQueue,
  retryMatchRequest,
} from "@/api/match";
import { reviewItem } from "@/api/review";
import { changePassword, forceChangePassword, updateProfile } from "@/api/users";
import ForceChangePasswordPage from "@/pages/force-change-password";
import LoginPage from "@/pages/login";
import ProfilePage from "@/pages/profile";
import ResultsPage from "@/pages/results";
import ReviewPage from "@/pages/review";
import { toast } from "sonner";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  invalidateQueries: vi.fn(),
  refetch: vi.fn(),
  params: { requestId: "req-12345678" },
  queryData: new Map<string, unknown>(),
  queryError: new Map<string, Error>(),
  queryLoading: new Set<string>(),
  mutationPending: false,
}));

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => <a href={to}>{children}</a>,
  useNavigate: () => mocks.navigate,
  useParams: () => mocks.params,
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
  useQuery: ({
    queryKey,
    queryFn,
    refetchInterval,
  }: {
    queryKey: unknown[];
    queryFn?: () => unknown;
    refetchInterval?: (query: { state: { data: { status?: string } | undefined } }) => false | number;
  }) => {
    const key = String(queryKey[0]);
    const error = mocks.queryError.get(key);
    const data = mocks.queryData.get(key) as { status?: string } | undefined;
    queryFn?.();
    refetchInterval?.({ state: { data } });
    return {
      data,
      isLoading: mocks.queryLoading.has(key),
      isError: !!error,
      error,
      refetch: mocks.refetch,
    };
  },
  useMutation: ({
    mutationFn,
    onSuccess,
    onError,
  }: {
    mutationFn: (input?: unknown) => Promise<unknown>;
    onSuccess?: (data: unknown, input?: unknown) => void;
    onError?: (error: Error) => void;
  }) => ({
    isPending: mocks.mutationPending,
    mutate: async (input?: unknown) => {
      try {
        const data = await mutationFn(input);
        onSuccess?.(data, input);
      } catch (error) {
        onError?.(error as Error);
      }
    },
  }),
}));

vi.mock("@/api/auth", () => ({
  getMe: vi.fn(),
  login: vi.fn(),
}));

vi.mock("@/api/users", () => ({
  updateProfile: vi.fn(),
  changePassword: vi.fn(),
  forceChangePassword: vi.fn(),
}));

vi.mock("@/api/match", () => ({
  getMatchRequest: vi.fn(),
  deleteMatchRequest: vi.fn(),
  retryMatchRequest: vi.fn(),
  listMatchRequests: vi.fn(),
  getReviewQueue: vi.fn(),
}));

vi.mock("@/api/suppliers", () => ({
  listSuppliers: vi.fn(),
}));

vi.mock("@/api/review", () => ({
  reviewItem: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/components/match/results-table", () => ({
  default: ({ requestId }: { requestId: string }) => <div>Results table {requestId}</div>,
}));

vi.mock("@/components/export/export-button", () => ({
  default: ({ requestId }: { requestId: string }) => <button>Export {requestId}</button>,
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
            choose supplier
          </button>
          <button type="button" onClick={() => onValueChange("all")}>
            choose all suppliers
          </button>
          <button type="button" onClick={() => onValueChange("")}>
            clear selection
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

function responseError(status: number, detail?: string) {
  return {
    response: {
      status,
      json: async () => ({ detail }),
    },
  };
}

describe("auth and workflow pages", () => {
  beforeEach(() => {
    mocks.navigate.mockClear();
    mocks.invalidateQueries.mockClear();
    mocks.refetch.mockClear();
    mocks.queryData.clear();
    mocks.queryError.clear();
    mocks.queryLoading.clear();
    mocks.mutationPending = false;
    vi.mocked(login).mockResolvedValue({ logged_in: true, must_change_password: false });
    vi.mocked(forceChangePassword).mockResolvedValue({ ok: true });
    vi.mocked(updateProfile).mockResolvedValue({ user_id: "u1", full_name: "Ivan Updated" });
    vi.mocked(changePassword).mockResolvedValue({ ok: true });
    vi.mocked(getMatchRequest).mockResolvedValue({} as never);
    vi.mocked(deleteMatchRequest).mockResolvedValue({ ok: true } as never);
    vi.mocked(retryMatchRequest).mockResolvedValue({ job_id: "retry-1" } as never);
    vi.mocked(getReviewQueue).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    vi.mocked(reviewItem).mockResolvedValue({ ok: true });
    vi.mocked(toast.success).mockClear();
    vi.mocked(toast.error).mockClear();
  });

  it("logs in, toggles password visibility, and routes by password-change flag", async () => {
    const user = userEvent.setup();
    vi.mocked(login).mockResolvedValueOnce({ logged_in: true, must_change_password: true });
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Имя пользователя"), "ivan");
    await user.type(screen.getByLabelText("Пароль"), "secret");
    await user.click(screen.getByLabelText("Показать пароль"));
    expect(screen.getByLabelText("Пароль")).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Войти" }));

    await waitFor(() => expect(login).toHaveBeenCalledWith("ivan", "secret"));
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/change-password" });
  });

  it("routes successful logins without password changes to the dashboard", async () => {
    const user = userEvent.setup();
    vi.mocked(login).mockResolvedValueOnce({ logged_in: true, must_change_password: false });
    render(<LoginPage />);

    await user.type(screen.getByLabelText("Имя пользователя"), "ivan");
    await user.type(screen.getByLabelText("Пароль"), "secret");
    await user.click(screen.getByRole("button", { name: "Войти" }));

    await waitFor(() => expect(login).toHaveBeenCalledWith("ivan", "secret"));
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/" });
  });

  it("shows login errors for deactivated and network failures", async () => {
    const user = userEvent.setup();
    vi.mocked(login).mockRejectedValueOnce(responseError(401, "Account deactivated"));
    const { rerender } = render(<LoginPage />);

    await user.type(screen.getByLabelText("Имя пользователя"), "ivan");
    await user.type(screen.getByLabelText("Пароль"), "bad");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ваш аккаунт деактивирован");

    vi.mocked(login).mockRejectedValueOnce(new Error("offline"));
    rerender(<LoginPage />);
    await user.clear(screen.getByLabelText("Пароль"));
    await user.type(screen.getByLabelText("Пароль"), "bad2");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось подключиться");
  });

  it("shows login errors for invalid credentials, unreadable auth errors, and server failures", async () => {
    const user = userEvent.setup();
    vi.mocked(login).mockRejectedValueOnce(responseError(401, "Bad credentials"));
    const { rerender } = render(<LoginPage />);

    await user.type(screen.getByLabelText("Имя пользователя"), "ivan");
    await user.type(screen.getByLabelText("Пароль"), "bad");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Неверное имя пользователя или пароль");

    vi.mocked(login).mockRejectedValueOnce({
      response: {
        status: 401,
        json: async () => {
          throw new Error("unreadable");
        },
      },
    });
    rerender(<LoginPage />);
    await user.clear(screen.getByLabelText("Пароль"));
    await user.type(screen.getByLabelText("Пароль"), "bad2");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Неверное имя пользователя или пароль");

    vi.mocked(login).mockRejectedValueOnce(responseError(500, "down"));
    rerender(<LoginPage />);
    await user.clear(screen.getByLabelText("Пароль"));
    await user.type(screen.getByLabelText("Пароль"), "bad3");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ошибка сервера. Попробуйте позже.");
  });

  it("validates and submits forced password changes", async () => {
    const user = userEvent.setup();
    render(<ForceChangePasswordPage />);

    await user.type(screen.getByLabelText("Новый пароль"), "short");
    await user.type(screen.getByLabelText("Подтвердите пароль"), "short");
    await user.click(screen.getByRole("button", { name: "Установить пароль" }));
    expect(screen.getByRole("alert")).toHaveTextContent("минимум 6 символов");

    await user.clear(screen.getByLabelText("Новый пароль"));
    await user.clear(screen.getByLabelText("Подтвердите пароль"));
    await user.type(screen.getByLabelText("Новый пароль"), "Strong1!");
    await user.type(screen.getByLabelText("Подтвердите пароль"), "Strong1!");
    expect(screen.getByText("Надёжный")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Установить пароль" }));

    await waitFor(() => expect(forceChangePassword).toHaveBeenCalledWith("Strong1!"));
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/" });
  });

  it("shows forced password mismatch, strength levels, visibility toggles, and submit failures", async () => {
    const user = userEvent.setup();
    vi.mocked(forceChangePassword).mockRejectedValueOnce(new Error("password rejected"));
    render(<ForceChangePasswordPage />);

    await user.type(screen.getByLabelText("Новый пароль"), "abcdefgh");
    expect(screen.getByText("Средний")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Подтвердите пароль"), "abcdeg");
    await user.click(screen.getByRole("button", { name: "Установить пароль" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Пароли не совпадают");

    await user.clear(screen.getByLabelText("Новый пароль"));
    await user.clear(screen.getByLabelText("Подтвердите пароль"));
    await user.type(screen.getByLabelText("Новый пароль"), "abcdefGH");
    expect(screen.getByText("Хороший")).toBeInTheDocument();

    await user.click(screen.getAllByLabelText("Показать пароль")[0]);
    expect(screen.getByLabelText("Новый пароль")).toHaveAttribute("type", "text");
    await user.click(screen.getByLabelText("Скрыть пароль"));
    expect(screen.getByLabelText("Новый пароль")).toHaveAttribute("type", "password");

    await user.click(screen.getAllByLabelText("Показать пароль")[1]);
    expect(screen.getByLabelText("Подтвердите пароль")).toHaveAttribute("type", "text");
    await user.click(screen.getByLabelText("Скрыть пароль"));
    expect(screen.getByLabelText("Подтвердите пароль")).toHaveAttribute("type", "password");

    await user.clear(screen.getByLabelText("Новый пароль"));
    await user.clear(screen.getByLabelText("Подтвердите пароль"));
    await user.type(screen.getByLabelText("Новый пароль"), "abcdef1");
    await user.type(screen.getByLabelText("Подтвердите пароль"), "abcdef1");
    await user.click(screen.getByRole("button", { name: "Установить пароль" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Не удалось сменить пароль. Попробуйте ещё раз.",
    );
  });

  it("updates profile name and validates password form", async () => {
    const user = userEvent.setup();
    mocks.queryData.set("me", {
      user_id: "u1",
      username: "ivan",
      full_name: "Ivan",
      role: "admin",
      must_change_password: false,
    });
    mocks.queryData.set("my-activity", {
      items: [
        {
          request_id: "req-activity",
          status: "done",
          total_items: 1,
          processed_items: 1,
          auto_matched_items: 1,
          review_needed_items: 0,
          no_match_items: 0,
          created_at: "2026-01-01T00:00:00Z",
          file_name: "activity.csv",
        },
      ],
    });

    render(<ProfilePage />);

    expect(screen.getByText("@ivan")).toBeInTheDocument();
    expect(screen.getByText("Администратор")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Полное имя"));
    await user.type(screen.getByLabelText("Полное имя"), "Ivan");
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
    await user.clear(screen.getByLabelText("Полное имя"));
    await user.type(screen.getByLabelText("Полное имя"), "Ivan Updated");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith("Ivan Updated"));
    expect(toast.success).toHaveBeenCalledWith("Имя обновлено");

    await user.type(screen.getByLabelText("Текущий пароль"), "old");
    await user.type(screen.getByLabelText("Новый пароль"), "123");
    await user.type(screen.getByLabelText("Подтвердите новый пароль"), "123");
    await user.click(screen.getByRole("button", { name: "Сменить пароль" }));
    expect(screen.getByRole("alert")).toHaveTextContent("минимум 6 символов");

    await user.clear(screen.getByLabelText("Новый пароль"));
    await user.clear(screen.getByLabelText("Подтвердите новый пароль"));
    await user.type(screen.getByLabelText("Новый пароль"), "newpass");
    await user.type(screen.getByLabelText("Подтвердите новый пароль"), "newpass");
    await user.click(screen.getByRole("button", { name: "Сменить пароль" }));
    await waitFor(() => expect(changePassword).toHaveBeenCalledWith("old", "newpass"));
  });

  it("renders profile error, unknown role, activity loading, and empty activity states", async () => {
    const user = userEvent.setup();
    mocks.queryError.set("me", new Error("profile unavailable"));
    mocks.queryLoading.add("my-activity");
    const { rerender } = render(<ProfilePage />);

    expect(screen.getByText("profile unavailable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(mocks.refetch).toHaveBeenCalled();
    expect(screen.getByText("@...")).toBeInTheDocument();
    expect(screen.getByText("...")).toBeInTheDocument();
    expect(screen.getAllByRole("status", { name: "Загрузка" }).length).toBeGreaterThan(0);
    await user.type(screen.getByLabelText("Полное имя"), "Fallback Name");
    expect(screen.getByRole("button", { name: "Сохранить" })).not.toBeDisabled();

    mocks.queryError.clear();
    mocks.queryLoading.clear();
    mocks.queryData.set("me", {
      user_id: "u-unknown",
      username: "viewer",
      full_name: null,
      role: "auditor",
      must_change_password: false,
    });
    mocks.queryData.set("my-activity", { items: [] });
    rerender(<ProfilePage />);

    expect(screen.getByText("@viewer")).toBeInTheDocument();
    expect(screen.getByText("auditor")).toBeInTheDocument();
    expect(screen.getByText("Нет недавней активности.")).toBeInTheDocument();
  });

  it("reports profile name and password change failures", async () => {
    const user = userEvent.setup();
    mocks.queryData.set("me", {
      user_id: "u1",
      username: "ivan",
      full_name: "Ivan",
      role: "operator",
      must_change_password: false,
    });
    mocks.queryData.set("my-activity", {
      items: [
        {
          request_id: "req-running",
          status: "running",
          total_items: 2,
          processed_items: 1,
          auto_matched_items: 0,
          review_needed_items: 1,
          no_match_items: 0,
          created_at: "2026-01-02T00:00:00Z",
          file_name: null,
        },
        {
          request_id: "req-custom",
          status: "custom_status",
          total_items: 3,
          processed_items: 0,
          auto_matched_items: 0,
          review_needed_items: 0,
          no_match_items: 0,
          created_at: "2026-01-03T00:00:00Z",
          file_name: "custom.csv",
        },
      ],
    });
    vi.mocked(updateProfile).mockRejectedValueOnce(new Error("name write failed"));

    render(<ProfilePage />);

    expect(screen.getByText("Оператор")).toBeInTheDocument();
    expect(screen.getByText(/Запрос от/)).toBeInTheDocument();
    expect(screen.getByText("Обрабатывается")).toBeInTheDocument();
    expect(screen.getByText("custom_status")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Полное имя"));
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => expect(updateProfile).toHaveBeenCalledWith(null));
    expect(toast.error).toHaveBeenCalledWith("Ошибка при обновлении имени: name write failed");

    await user.type(screen.getByLabelText("Текущий пароль"), "old");
    await user.type(screen.getByLabelText("Новый пароль"), "newpass");
    await user.type(screen.getByLabelText("Подтвердите новый пароль"), "different");
    await user.click(screen.getByRole("button", { name: "Сменить пароль" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Пароли не совпадают");

    await user.clear(screen.getByLabelText("Подтвердите новый пароль"));
    await user.type(screen.getByLabelText("Подтвердите новый пароль"), "newpass");
    vi.mocked(changePassword).mockRejectedValueOnce({ response: { status: 401 } });
    await user.click(screen.getByRole("button", { name: "Сменить пароль" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Неверный текущий пароль");

    vi.mocked(changePassword).mockRejectedValueOnce({ response: { status: 500 } });
    await user.click(screen.getByRole("button", { name: "Сменить пароль" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ошибка при смене пароля: Неизвестная ошибка",
    );

    vi.mocked(changePassword).mockRejectedValueOnce(new Error("password service down"));
    await user.click(screen.getByRole("button", { name: "Сменить пароль" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ошибка при смене пароля: password service down",
    );
  });

  it("reports profile fallback failures for non-error mutation rejections", async () => {
    const user = userEvent.setup();
    mocks.queryData.set("me", {
      user_id: "u1",
      username: "ivan",
      full_name: "Ivan",
      role: "viewer",
      must_change_password: false,
    });
    mocks.queryData.set("my-activity", {
      items: [
        {
          request_id: "req-failed",
          status: "failed",
          total_items: 2,
          processed_items: 2,
          auto_matched_items: 0,
          review_needed_items: 0,
          no_match_items: 2,
          created_at: "2026-01-04T00:00:00Z",
          file_name: "failed.csv",
        },
      ],
    });
    vi.mocked(updateProfile).mockRejectedValueOnce("name string failure");
    vi.mocked(changePassword).mockRejectedValueOnce("password string failure");

    render(<ProfilePage />);

    expect(screen.getByText("Наблюдатель")).toBeInTheDocument();
    expect(screen.getByText("Ошибка")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Полное имя"));
    await user.type(screen.getByLabelText("Полное имя"), "Ivan Fallback");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Ошибка при обновлении имени: Неизвестная ошибка",
      ),
    );

    await user.type(screen.getByLabelText("Текущий пароль"), "old");
    await user.type(screen.getByLabelText("Новый пароль"), "newpass");
    await user.type(screen.getByLabelText("Подтвердите новый пароль"), "newpass");
    await user.click(screen.getByRole("button", { name: "Сменить пароль" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ошибка при смене пароля: Неизвестная ошибка",
    );
  });

  it("renders pending profile mutation controls", async () => {
    mocks.mutationPending = true;
    mocks.queryData.set("me", {
      user_id: "u1",
      username: "ivan",
      full_name: "Ivan",
      role: "admin",
      must_change_password: false,
    });
    mocks.queryData.set("my-activity", { items: [] });

    render(<ProfilePage />);

    const nameSave = screen.getByLabelText("Полное имя").parentElement!.querySelector("button")!;
    expect(nameSave).toBeDisabled();
    expect(screen.getByRole("button", { name: /Сменить пароль/ })).toBeDisabled();
  });

  it("renders results page with request controls and failed state", () => {
    mocks.queryData.set("match-request", {
      request_id: "req-12345678",
      supplier_id: "s1",
      status: "failed",
      total_items: 10,
      processed_items: 3,
      auto_matched_items: 1,
      review_needed_items: 1,
      no_match_items: 1,
      created_at: "2026-01-01T00:00:00Z",
      error_message: "Worker failed",
    });
    mocks.queryData.set("suppliers", {
      items: [{ supplier_id: "s1", supplier_name: "ACME", strict_mode: false, is_active: true }],
    });

    render(<ResultsPage />);

    expect(screen.getByRole("heading", { name: "Запрос req-1234" })).toBeInTheDocument();
    expect(screen.getByText(/Поставщик: ACME/)).toBeInTheDocument();
    expect(screen.getByText("Results table req-12345678")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Worker failed");
    expect(screen.getByRole("button", { name: "Export req-12345678" })).toBeInTheDocument();
  });

  it("renders result fallbacks for nameless failures and completed zero-progress exports", () => {
    mocks.queryData.set("match-request", {
      request_id: "req-12345678",
      status: "failed",
      total_items: 10,
      processed_items: 0,
      auto_matched_items: 0,
      review_needed_items: 0,
      no_match_items: 0,
      created_at: "2026-01-01T00:00:00Z",
    });
    const { rerender } = render(<ResultsPage />);

    expect(screen.getByRole("alert")).toHaveTextContent("Обработка завершилась с ошибкой.");
    expect(screen.queryByText("Results table req-12345678")).not.toBeInTheDocument();

    mocks.queryData.set("match-request", {
      request_id: "req-12345678",
      status: "done",
      total_items: 10,
      processed_items: 0,
      auto_matched_items: 0,
      review_needed_items: 0,
      no_match_items: 0,
      created_at: "2026-01-01T00:00:00Z",
    });
    rerender(<ResultsPage />);

    expect(screen.getByText("Results table req-12345678")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export req-12345678" })).toBeInTheDocument();
  });

  it("renders results page loading, error, and missing states", async () => {
    const user = userEvent.setup();
    mocks.queryLoading.add("match-request");
    const { rerender } = render(<ResultsPage />);

    expect(screen.getAllByRole("status", { name: "Загрузка" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("status", { name: "Загрузка таблицы" })).toBeInTheDocument();

    mocks.queryLoading.clear();
    mocks.queryError.set("match-request", new Error("not reachable"));
    rerender(<ResultsPage />);

    expect(screen.getByText("Запрос не найден")).toBeInTheDocument();
    expect(screen.getByText(/not reachable/)).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "Повторить" })[0]);
    expect(mocks.refetch).toHaveBeenCalled();
    await user.click(screen.getAllByRole("button", { name: "Повторить" })[1]);
    expect(mocks.refetch).toHaveBeenCalledTimes(2);

    mocks.queryError.clear();
    rerender(<ResultsPage />);
    expect(screen.getByText("Запрос не найден")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /К списку запросов/ })).toHaveAttribute("href", "/");
  });

  it("renders queued and stuck running result states with fallback supplier names", async () => {
    const user = userEvent.setup();
    const startedAt = new Date(Date.now() - 6 * 60 * 1000).toISOString();
    mocks.queryData.set("match-request", {
      request_id: "req-12345678",
      supplier_id: "supplier-missing",
      status: "running",
      total_items: 10,
      processed_items: 2,
      auto_matched_items: 1,
      review_needed_items: 1,
      no_match_items: 0,
      created_at: "2026-01-01T00:00:00Z",
      started_at: startedAt,
    });
    mocks.queryData.set("suppliers", {
      items: [{ supplier_id: "s1", supplier_name: "ACME", strict_mode: false, is_active: true }],
    });
    vi.mocked(retryMatchRequest).mockRejectedValueOnce(new Error("retry offline"));

    const { rerender } = render(<ResultsPage />);

    expect(screen.getByText(/Поставщик: supplier-missing/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Обрабатывается: 2 из 10");
    expect(screen.getByText("Results table req-12345678")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export req-12345678" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Ошибка при повторе: retry offline"));

    vi.mocked(retryMatchRequest).mockRejectedValueOnce("retry string failure");
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Ошибка при повторе: Неизвестная ошибка"),
    );

    mocks.queryData.set("match-request", {
      request_id: "req-12345678",
      status: "queued",
      total_items: 10,
      processed_items: 0,
      auto_matched_items: 0,
      review_needed_items: 0,
      no_match_items: 0,
      created_at: "2026-01-01T00:00:00Z",
    });
    rerender(<ResultsPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Запрос в очереди на обработку");
    expect(screen.queryByText("Results table req-12345678")).not.toBeInTheDocument();
  });

  it("does not poll result requests while the document is hidden", () => {
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: true,
    });
    mocks.queryData.set("match-request", {
      request_id: "req-12345678",
      status: "running",
      total_items: 10,
      processed_items: 1,
      auto_matched_items: 0,
      review_needed_items: 1,
      no_match_items: 0,
      created_at: "2026-01-01T00:00:00Z",
    });

    render(<ResultsPage />);

    expect(screen.getByRole("status")).toHaveTextContent("Обрабатывается: 1 из 10");

    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
  });

  it("retries and deletes failed result requests", async () => {
    const user = userEvent.setup();
    mocks.queryData.set("match-request", {
      request_id: "req-12345678",
      supplier_id: "s1",
      status: "failed",
      total_items: 10,
      processed_items: 0,
      auto_matched_items: 0,
      review_needed_items: 0,
      no_match_items: 0,
      created_at: "2026-01-01T00:00:00Z",
      error_message: "Worker failed",
    });
    mocks.queryData.set("suppliers", {
      items: [{ supplier_id: "s1", supplier_name: "ACME", strict_mode: false, is_active: true }],
    });

    render(<ResultsPage />);

    await user.click(screen.getByRole("button", { name: "Повторить" }));
    await waitFor(() => expect(retryMatchRequest).toHaveBeenCalledWith("req-12345678"));
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["match-request", "req-12345678"],
    });
    expect(toast.success).toHaveBeenCalledWith("Запрос поставлен в очередь на повторную обработку");

    await user.click(screen.getByRole("button", { name: "Удалить запрос" }));
    expect(screen.getByText("Удалить запрос?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() => expect(deleteMatchRequest).toHaveBeenCalledWith("req-12345678"));
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["match-requests"] });
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/" });
  });

  it("renders pending retry and delete controls on failed result requests", async () => {
    const user = userEvent.setup();
    mocks.queryData.set("match-request", {
      request_id: "req-12345678",
      status: "failed",
      total_items: 10,
      processed_items: 0,
      auto_matched_items: 0,
      review_needed_items: 0,
      no_match_items: 0,
      created_at: "2026-01-01T00:00:00Z",
      error_message: "Worker failed",
    });

    const { container, rerender } = render(<ResultsPage />);

    mocks.mutationPending = true;
    rerender(<ResultsPage />);

    expect(screen.getByRole("button", { name: "Повторить" })).toBeDisabled();
    expect(container.querySelector(".animate-spin")).toBeInTheDocument();

    mocks.mutationPending = false;
    rerender(<ResultsPage />);
    await user.click(screen.getByRole("button", { name: "Удалить запрос" }));
    mocks.mutationPending = true;
    rerender(<ResultsPage />);
    expect(screen.getByRole("button", { name: "Удаление..." })).toBeDisabled();
  });

  it("reviews queue items with buttons and keyboard shortcuts", async () => {
    const user = userEvent.setup();
    mocks.queryData.set("suppliers", {
      items: [{ supplier_id: "s1", supplier_name: "ACME", strict_mode: false, is_active: true }],
    });
    mocks.queryData.set("review-queue", {
      total: 21,
      page: 1,
      page_size: 20,
      items: [
        {
          request_item_id: "ri-1",
          request_id: "req-1",
          raw_text: "Pump one",
          status: "review_needed",
          confidence: 0.9,
          reasons: ["low margin"],
          supplier_id: "s1",
          file_name: "queue.csv",
        },
        {
          request_item_id: "ri-mid",
          request_id: "req-1",
          raw_text: "Mid confidence item",
          status: "review_needed",
          confidence: 0.8,
          reasons: ["medium confidence"],
          supplier_id: null,
          file_name: undefined,
        },
        {
          request_item_id: "ri-2",
          request_id: "req-1",
          raw_text: "Valve two",
          status: "review_needed",
          confidence: 0.6,
          reasons: [],
        },
      ],
    });

    render(<ReviewPage />);

    expect(screen.getByText("Pump one")).toBeInTheDocument();
    expect(screen.getByText("90%")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: /Принять/ })[0]);
    await waitFor(() =>
      expect(reviewItem).toHaveBeenCalledWith("ri-1", { final_decision: "accepted" }),
    );
    expect(toast.success).toHaveBeenCalledWith("Элемент принят");

    await user.keyboard("j");
    await user.keyboard("r");
    await waitFor(() =>
      expect(reviewItem).toHaveBeenCalledWith("ri-mid", { final_decision: "rejected" }),
    );

    await user.click(screen.getByText("Pump one"));
    await user.keyboard("j");
    await user.keyboard("k");
    await user.keyboard("a");
    await waitFor(() =>
      expect(reviewItem).toHaveBeenCalledWith("ri-1", { final_decision: "accepted" }),
    );

    await user.click(screen.getByRole("button", { name: "choose supplier" }));
    expect(screen.getByText("Всего: 21")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "clear selection" }));
    expect(screen.getByText("Всего: 21")).toBeInTheDocument();

    const input = document.createElement("input");
    document.body.append(input);
    input.focus();
    const callsBeforeInputShortcut = vi.mocked(reviewItem).mock.calls.length;
    await user.keyboard("r");
    expect(reviewItem).toHaveBeenCalledTimes(callsBeforeInputShortcut);
    input.remove();
  });

  it("shows empty review queue, paginates, and reports review errors", async () => {
    const user = userEvent.setup();
    mocks.queryData.set("suppliers", {
      items: [{ supplier_id: "s1", supplier_name: "ACME", strict_mode: false, is_active: true }],
    });
    mocks.queryData.set("review-queue", {
      total: 21,
      page: 1,
      page_size: 20,
      items: [
        {
          request_item_id: "ri-low",
          request_id: "req-1",
          raw_text: "Low confidence item",
          status: "review_needed",
          confidence: 0.7,
          reasons: [],
          file_name: null,
        },
        {
          request_item_id: "ri-null",
          request_id: "req-1",
          raw_text: "No confidence item",
          status: "review_needed",
          confidence: null,
          reasons: [],
        },
      ],
    });
    vi.mocked(reviewItem).mockRejectedValueOnce(new Error("write failed"));

    const { rerender } = render(<ReviewPage />);

    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("No confidence item")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);

    await user.click(screen.getAllByRole("button", { name: /Отклонить/ })[0]);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Ошибка при обработке"));

    expect(screen.getByText("Страница 1 из 2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Вперёд/ }));
    expect(screen.getByText("Страница 2 из 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Вперёд/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Назад/ }));
    expect(screen.getByText("Страница 1 из 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Назад/ })).toBeDisabled();

    mocks.queryData.set("review-queue", {
      total: 0,
      page: 1,
      page_size: 20,
      items: [],
    });
    rerender(<ReviewPage />);
    expect(screen.getByText("Нет элементов для проверки")).toBeInTheDocument();
    const callsBeforeEmptyShortcuts = vi.mocked(reviewItem).mock.calls.length;
    await user.keyboard("a");
    await user.keyboard("r");
    expect(reviewItem).toHaveBeenCalledTimes(callsBeforeEmptyShortcuts);
  });

  it("renders review queue fallbacks when query data is absent", () => {
    render(<ReviewPage />);

    expect(screen.getByText("Всего: 0")).toBeInTheDocument();
    expect(screen.getByText("Нет элементов для проверки")).toBeInTheDocument();
  });
});
