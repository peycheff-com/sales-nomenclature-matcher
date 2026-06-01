import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Search } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import type { MatchRequestDetails } from "@/api/types";
import { PageLayout } from "@/components/layout/page-layout";
import StatsBar from "@/components/match/stats-bar";
import StatusBadge from "@/components/match/status-badge";
import { Badge, badgeVariants } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { QueryErrorBanner } from "@/components/ui/query-error-banner";

function request(overrides: Partial<MatchRequestDetails> = {}): MatchRequestDetails {
  return {
    request_id: "r1",
    status: "running",
    total_items: 10,
    processed_items: 4,
    auto_matched_items: 2,
    review_needed_items: 1,
    no_match_items: 1,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("small reusable components", () => {
  it("renders status labels and variant class helpers", () => {
    const { rerender } = render(<StatusBadge status="review_needed" />);

    expect(screen.getByText("На проверку")).toBeInTheDocument();
    rerender(<StatusBadge status={"custom_status" as never} />);
    expect(screen.getByText("custom_status")).toBeInTheDocument();
    expect(buttonVariants({ variant: "destructive", size: "icon" })).toContain("size-8");
    expect(badgeVariants({ variant: "outline" })).toContain("border-border");
  });

  it("renders stats, status fallbacks, and running progress without dividing by zero", () => {
    const { rerender } = render(<StatsBar request={request()} />);

    expect(screen.getByText("Обработка")).toBeInTheDocument();
    expect(screen.getByText(/Обработано:/)).toHaveTextContent("Обработано: 4 из 10 (40%)");
    expect(screen.getByText("2")).toBeInTheDocument();

    rerender(<StatsBar request={request({ status: "done", total_items: 0, processed_items: 0 })} />);

    expect(screen.getByText("Готово")).toBeInTheDocument();
    expect(screen.getByText(/Обработано:/)).toHaveTextContent("Обработано: 0 из 0 (0%)");

    rerender(<StatsBar request={request({ status: "paused" as never })} />);
    expect(screen.getByText("paused")).toBeInTheDocument();
  });

  it("renders empty and error states with the appropriate action behavior", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const action = <Button>Создать</Button>;
    const { rerender } = render(
      <EmptyState
        icon={Search}
        title="Нет данных"
        description="Ничего не найдено"
        action={action}
        variant="no-results"
      />,
    );

    expect(screen.getByText("Нет данных")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Создать" })).toBeInTheDocument();

    rerender(
      <EmptyState
        icon={Search}
        title="Ошибка"
        description="Повторите запрос"
        variant="error"
        onRetry={onRetry}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Создать" })).not.toBeInTheDocument();
  });

  it("renders base UI primitives and page layout slots", () => {
    render(
      <PageLayout
        title="Заголовок"
        description="Описание"
        header={<Badge variant="secondary">Header</Badge>}
        actions={<Button variant="outline">Action</Button>}
        className="custom-layout"
      >
        <Button size="sm">Child</Button>
      </PageLayout>,
    );

    expect(screen.getByRole("heading", { name: "Заголовок" })).toBeInTheDocument();
    expect(screen.getByText("Описание")).toBeInTheDocument();
    expect(screen.getByText("Header")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Action" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Child" })).toBeInTheDocument();
  });

  it("renders query error banner null, fallback-message, and no-retry branches", () => {
    const { rerender, container } = render(<QueryErrorBanner error={null} />);

    expect(container).toBeEmptyDOMElement();

    rerender(<QueryErrorBanner error={new Error("")} title="Custom title" className="extra-class" />);

    expect(screen.getByRole("alert")).toHaveTextContent("Custom title");
    expect(screen.getByRole("alert")).toHaveTextContent("Произошла неизвестная ошибка");
    expect(screen.getByRole("alert")).toHaveClass("extra-class");
    expect(screen.queryByRole("button", { name: "Повторить" })).not.toBeInTheDocument();
  });
});
