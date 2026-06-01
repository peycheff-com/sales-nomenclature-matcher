import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import AppShell from "@/components/layout/app-shell";
import { Toaster } from "@/components/ui/sonner";
import {
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectScrollDownButton,
  SelectScrollUpButton,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { queryClient } from "@/lib/query-client";

const mocks = vi.hoisted(() => ({
  dismiss: vi.fn(),
  error: vi.fn(() => "offline-toast"),
  success: vi.fn(),
  sonnerRender: vi.fn(({ className }: { className?: string }) => <div data-testid="sonner">{className}</div>),
  navigate: vi.fn(),
  sessionExpired: undefined as undefined | (() => void),
}));

vi.mock("sonner", () => ({
  toast: {
    dismiss: mocks.dismiss,
    error: mocks.error,
    success: mocks.success,
  },
  Toaster: mocks.sonnerRender,
}));

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual<typeof import("@tanstack/react-query")>("@tanstack/react-query");
  return {
    ...actual,
    QueryClientProvider: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  };
});

vi.mock("@tanstack/react-router", () => ({
  Outlet: () => <div>Outlet content</div>,
  RouterProvider: () => <div>Router content</div>,
  useNavigate: () => mocks.navigate,
}));

vi.mock("@/router", () => ({
  router: {},
}));

vi.mock("@/lib/auth-store", () => ({
  onSessionExpired: (callback: () => void) => {
    mocks.sessionExpired = callback;
    return vi.fn();
  },
}));

vi.mock("@/components/layout/header", () => ({
  default: () => <header>Header</header>,
}));

vi.mock("@/components/layout/sidebar", () => ({
  default: ({ onNavigate }: { onNavigate?: () => void }) => (
    <nav>
      Sidebar
      {onNavigate && <button onClick={onNavigate}>close sidebar</button>}
    </nav>
  ),
}));

vi.mock("@/components/command-palette", () => ({
  default: () => <div>Command palette</div>,
}));

vi.mock("@/components/ui/alert-dialog", () => ({
  AlertDialog: ({ children, open }: { children: ReactNode; open?: boolean }) =>
    open ? <div>{children}</div> : null,
  AlertDialogAction: ({ children, onClick }: { children: ReactNode; onClick?: () => void }) => (
    <button onClick={onClick}>{children}</button>
  ),
  AlertDialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));

vi.mock("@base-ui/react/select", () => ({
  Select: {
    Root: ({ children }: { children: ReactNode }) => <div data-slot="select-root">{children}</div>,
    Group: ({ children, className }: { children: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    Value: ({ className, placeholder }: { className?: string; placeholder?: string }) => (
      <span className={className}>{placeholder}</span>
    ),
    Trigger: ({ children, className }: { children: ReactNode; className?: string }) => (
      <button className={className}>{children}</button>
    ),
    Icon: ({ render }: { render: ReactNode }) => <span>{render}</span>,
    Portal: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    Positioner: ({ children, className }: { children: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    Popup: ({ children, className }: { children: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    List: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    GroupLabel: ({ children, className }: { children: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    Item: ({ children, className }: { children: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    ItemText: ({ children, className }: { children: ReactNode; className?: string }) => (
      <span className={className}>{children}</span>
    ),
    ItemIndicator: ({ children, render }: { children: ReactNode; render: ReactNode }) => (
      <span>{render}{children}</span>
    ),
    Separator: ({ className }: { className?: string }) => <hr className={className} />,
    ScrollUpArrow: ({ children, className }: { children: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    ScrollDownArrow: ({ children, className }: { children: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
  },
}));

vi.mock("@base-ui/react/tooltip", () => ({
  Tooltip: {
    Root: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    Trigger: ({ children }: { children: ReactNode }) => <button>{children}</button>,
    Portal: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    Positioner: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    Popup: ({ children, className }: { children: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
  },
}));

describe("bootstrap wrappers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.sessionExpired = undefined;
  });

  it("renders App providers and handles offline and online events", () => {
    vi.useFakeTimers();
    render(<App />);

    expect(screen.getByText("Router content")).toBeInTheDocument();
    expect(screen.getByTestId("sonner")).toHaveTextContent("toaster group");

    act(() => {
      window.dispatchEvent(new Event("offline"));
      vi.advanceTimersByTime(1000);
    });
    expect(mocks.error).toHaveBeenCalledWith("Нет подключения к интернету", {
      duration: Infinity,
      id: "offline-status",
    });

    act(() => window.dispatchEvent(new Event("online")));
    expect(mocks.dismiss).toHaveBeenCalledWith("offline-toast");
    expect(mocks.success).toHaveBeenCalledWith("Подключение восстановлено", { duration: 3000 });
    vi.useRealTimers();
  });

  it("shows the expired session dialog and navigates back to login", async () => {
    const user = userEvent.setup();
    render(<AppShell />);

    expect(screen.getByText("Header")).toBeInTheDocument();
    expect(screen.getByText("Outlet content")).toBeInTheDocument();

    act(() => mocks.sessionExpired?.());
    expect(screen.getByText("Сессия истекла")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Войти снова/ }));
    expect(mocks.navigate).toHaveBeenCalledWith({ to: "/login" });
  });

  it("renders select and tooltip wrapper components", () => {
    render(
      <>
        <SelectGroup>
          <SelectLabel>Group label</SelectLabel>
          <SelectTrigger>
            <SelectValue placeholder="Pick one" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="a">Alpha</SelectItem>
            <SelectSeparator />
            <SelectScrollUpButton />
            <SelectScrollDownButton />
          </SelectContent>
        </SelectGroup>
        <Tooltip>
          <TooltipTrigger>Help</TooltipTrigger>
          <TooltipContent className="extra">Tooltip body</TooltipContent>
        </Tooltip>
      </>,
    );

    expect(screen.getByText("Group label")).toBeInTheDocument();
    expect(screen.getByText("Pick one")).toBeInTheDocument();
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Tooltip body")).toHaveClass("extra");
  });

  it("exposes the configured query client and toaster wrapper", () => {
    expect(queryClient.getDefaultOptions().queries?.retry).toBe(1);
    expect(queryClient.getDefaultOptions().queries?.refetchOnWindowFocus).toBe(false);

    render(<Toaster position="bottom-left" />);
    expect(mocks.sonnerRender).toHaveBeenCalledWith(
      expect.objectContaining({
        position: "bottom-left",
        theme: "light",
      }),
      undefined,
    );
  });
});
