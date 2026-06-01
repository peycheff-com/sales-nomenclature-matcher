import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AppShell, { useSidebarContext } from "@/components/layout/app-shell";
import { notifySessionExpired } from "@/lib/auth-store";

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock("@tanstack/react-router", () => ({
  Outlet: () => <div>Current route</div>,
  useNavigate: () => mocks.navigate,
}));

vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({
    data: {
      username: "operator",
      full_name: "Operator User",
      role: "operator",
    },
  }),
}));

vi.mock("@/api/auth", () => ({
  getMe: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("@/components/layout/sidebar", () => ({
  default: ({ onNavigate }: { onNavigate?: () => void }) => (
    <aside>
      <button type="button" onClick={onNavigate}>
        {onNavigate ? "Mobile sidebar link" : "Desktop sidebar"}
      </button>
    </aside>
  ),
}));

vi.mock("@/components/command-palette", () => ({
  default: () => <div>Command palette</div>,
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
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuTrigger: ({ children }: { children: ReactNode }) => <button>{children}</button>,
}));

describe("AppShell", () => {
  beforeEach(() => {
    mocks.navigate.mockReset();
  });

  it("opens and closes the mobile sidebar around routed content", async () => {
    const user = userEvent.setup();

    const { container } = render(<AppShell />);

    expect(screen.getByText("Current route")).toBeInTheDocument();
    expect(screen.getByText("Command palette")).toBeInTheDocument();
    expect(screen.getByText("Desktop sidebar")).toBeInTheDocument();
    expect(screen.queryByText("Mobile sidebar link")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Открыть меню" }));
    expect(screen.getByText("Mobile sidebar link")).toBeInTheDocument();

    fireEvent.click(container.querySelector(".absolute.inset-0")!);
    expect(screen.queryByText("Mobile sidebar link")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Открыть меню" }));
    expect(screen.getByText("Mobile sidebar link")).toBeInTheDocument();

    await user.click(screen.getByText("Mobile sidebar link"));
    expect(screen.queryByText("Mobile sidebar link")).not.toBeInTheDocument();
  });

  it("shows the session-expired dialog and routes to login", async () => {
    const user = userEvent.setup();

    render(<AppShell />);

    notifySessionExpired();

    expect(await screen.findByText("Сессия истекла")).toBeInTheDocument();
    expect(screen.getByText("Ваша сессия истекла. Пожалуйста, войдите в систему повторно.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Войти снова/ }));

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith({ to: "/login" }));
  });

  it("exposes a harmless closed sidebar context default", () => {
    function SidebarProbe() {
      const sidebar = useSidebarContext();
      sidebar.toggle();
      return <div>{sidebar.open ? "open" : "closed"}</div>;
    }

    render(<SidebarProbe />);

    expect(screen.getByText("closed")).toBeInTheDocument();
  });
});
