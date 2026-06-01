import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getMe, logout } from "@/api/auth";
import { listMatchRequests } from "@/api/match";
import CommandPalette from "@/components/command-palette";
import { ErrorBoundary } from "@/components/error-boundary";
import Header from "@/components/layout/header";
import { PageLayout } from "@/components/layout/page-layout";
import Sidebar from "@/components/layout/sidebar";
import { NotFound } from "@/pages/not-found";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  matchRoute: vi.fn(),
  queryData: new Map<string, unknown>(),
}));

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to, ...props }: { children: ReactNode; to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  useNavigate: () => mocks.navigate,
  useMatchRoute: () => mocks.matchRoute,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryKey, queryFn }: { queryKey: unknown[]; queryFn?: () => Promise<unknown> }) => {
    try {
      void queryFn?.().catch(() => undefined);
    } catch {
      // Component tests use inline query data below.
    }
    return {
      data: mocks.queryData.get(JSON.stringify(queryKey)),
    };
  },
}));

vi.mock("@/api/auth", () => ({
  getMe: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("@/api/match", () => ({
  listMatchRequests: vi.fn(),
}));

vi.mock("@/components/layout/app-shell", () => ({
  useSidebarContext: () => ({ open: false, toggle: mocks.navigate }),
}));

let crashEnabled = false;

function Crash() {
  if (crashEnabled) {
    throw new Error("render failed");
  }
  return <div>Loaded</div>;
}

describe("layout and navigation components", () => {
  beforeEach(() => {
    mocks.navigate.mockReset();
    mocks.matchRoute.mockReset();
    mocks.queryData.clear();
    vi.mocked(logout).mockResolvedValue(undefined);
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "" },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders sidebar role-aware navigation, active state, and request badge", () => {
    mocks.queryData.set(JSON.stringify(["me"]), { role: "operator" });
    mocks.queryData.set(JSON.stringify(["match-requests"]), {
      items: [{ status: "queued" }, { status: "running" }, { status: "done" }],
    });
    mocks.matchRoute.mockImplementation(({ to }: { to: string }) => to === "/");
    const onNavigate = vi.fn();

    render(<Sidebar onNavigate={onNavigate} />);

    expect(screen.getByText("Matcher")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Рабочий стол/ })).toHaveClass("font-medium");
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.queryByText("Пользователи")).not.toBeInTheDocument();
    expect(screen.queryByText("Система")).not.toBeInTheDocument();
    expect(getMe).toBeDefined();
    expect(listMatchRequests).toBeDefined();
  });

  it("shows admin navigation items in the sidebar", () => {
    mocks.queryData.set(JSON.stringify(["me"]), { role: "admin" });
    mocks.queryData.set(JSON.stringify(["match-requests"]), { items: [] });

    render(<Sidebar />);

    expect(screen.getByText("Пользователи")).toBeInTheDocument();
    expect(screen.getByText("Система")).toBeInTheDocument();
  });

  it("renders sidebar without a request badge when request data is missing", () => {
    mocks.queryData.set(JSON.stringify(["me"]), { role: "viewer" });

    render(<Sidebar />);

    expect(screen.getByText("Рабочий стол")).toBeInTheDocument();
    expect(screen.queryByText("1")).not.toBeInTheDocument();
  });

  it("renders the header user menu and clears local session on logout", async () => {
    const user = userEvent.setup();
    mocks.queryData.set(JSON.stringify(["me"]), {
      username: "ivan",
      full_name: "Ivan Petrov",
      role: "admin",
    });

    render(<Header />);

    expect(screen.getByText("Ivan Petrov")).toBeInTheDocument();
    expect(screen.getByText("Админ")).toBeInTheDocument();
    await user.click(screen.getByText("Ivan Petrov"));
    await user.click(await screen.findByText("Мой профиль"));
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/profile" });

    await user.click(screen.getByText("Ivan Petrov"));
    await user.click(await screen.findByText("Выйти"));
    await user.click(await screen.findByRole("button", { name: "Отмена" }));

    await user.click(screen.getByText("Ivan Petrov"));
    await user.click(await screen.findByText("Выйти"));
    await user.click(await screen.findByRole("button", { name: "Выйти" }));

    expect(logout).toHaveBeenCalledTimes(1);
    expect(window.location.href).toBe("/login");
  });

  it("renders header fallbacks for non-admin users and best-effort logout failures", async () => {
    const user = userEvent.setup();
    vi.mocked(logout).mockRejectedValueOnce(new Error("logout offline"));
    mocks.queryData.set(JSON.stringify(["me"]), {
      username: "operator1",
      full_name: "",
      role: "operator",
    });
    const { rerender } = render(<Header />);

    expect(screen.getByText("operator1")).toBeInTheDocument();
    expect(screen.getByText("Оператор")).toBeInTheDocument();

    await user.click(screen.getByText("operator1"));
    await user.click(await screen.findByText("Выйти"));
    await user.click(await screen.findByRole("button", { name: "Выйти" }));
    expect(window.location.href).toBe("/login");

    window.location.href = "";
    mocks.queryData.set(JSON.stringify(["me"]), {
      username: "viewer1",
      full_name: null,
      role: "viewer",
    });
    rerender(<Header />);

    expect(screen.getByText("viewer1")).toBeInTheDocument();
    expect(screen.getByText("Наблюдатель")).toBeInTheDocument();
  });

  it("renders page layout optional header and children without title chrome", () => {
    render(
      <PageLayout header={<div>Custom header</div>} className="custom-layout">
        <div>Body only</div>
      </PageLayout>,
    );

    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
    expect(screen.getByText("Custom header")).toBeInTheDocument();
    expect(screen.getByText("Body only").closest(".custom-layout")).toBeInTheDocument();
  });

  it("opens the command palette with keyboard shortcut and navigates on selection", async () => {
    const user = userEvent.setup();

    render(<CommandPalette />);
    await user.keyboard("{Control>}k{/Control}");

    expect(await screen.findByPlaceholderText("Перейти к странице...")).toBeInTheDocument();
    await user.click(screen.getByText("База данных"));

    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/catalog" });
  });

  it("recovers from render errors and can route back to home", async () => {
    const user = userEvent.setup();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    crashEnabled = true;
    const { rerender } = render(
      <ErrorBoundary>
        <Crash />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("heading", { name: "Произошла ошибка" })).toBeInTheDocument();
    expect(screen.getByText("render failed")).toBeInTheDocument();

    crashEnabled = false;
    await user.click(screen.getByRole("button", { name: "Попробовать снова" }));
    expect(screen.getByText("Loaded")).toBeInTheDocument();

    crashEnabled = true;
    rerender(
      <ErrorBoundary key="home-error">
        <Crash />
      </ErrorBoundary>,
    );
    await user.click(screen.getByRole("button", { name: "На главную" }));
    expect(window.location.href).toBe("/");
  });

  it("renders the not-found page with a home link", () => {
    render(<NotFound />);

    expect(screen.getAllByText("404")).toHaveLength(2);
    expect(screen.getByText("Страница не найдена")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Вернуться на главную/ })).toHaveAttribute(
      "href",
      "/",
    );
  });
});
