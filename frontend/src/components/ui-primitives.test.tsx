import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton, SkeletonCard, SkeletonTable, SkeletonText } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

describe("ui primitives", () => {
  it("renders card slots with size metadata", () => {
    render(
      <Card size="sm" data-testid="card">
        <CardHeader>
          <CardTitle>Title</CardTitle>
          <CardDescription>Description</CardDescription>
          <CardAction>Action</CardAction>
        </CardHeader>
        <CardContent>Content</CardContent>
        <CardFooter>Footer</CardFooter>
      </Card>,
    );

    expect(screen.getByTestId("card")).toHaveAttribute("data-size", "sm");
    expect(screen.getByText("Title")).toHaveAttribute("data-slot", "card-title");
    expect(screen.getByText("Description")).toHaveAttribute("data-slot", "card-description");
    expect(screen.getByText("Action")).toHaveAttribute("data-slot", "card-action");
    expect(screen.getByText("Content")).toHaveAttribute("data-slot", "card-content");
    expect(screen.getByText("Footer")).toHaveAttribute("data-slot", "card-footer");
  });

  it("renders form controls with slots and passed attributes", () => {
    render(
      <>
        <Input aria-label="Name" type="email" placeholder="mail" />
        <Textarea aria-label="Comment" placeholder="text" />
        <Separator orientation="vertical" data-testid="separator" />
      </>,
    );

    expect(screen.getByLabelText("Name")).toHaveAttribute("data-slot", "input");
    expect(screen.getByLabelText("Name")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Comment")).toHaveAttribute("data-slot", "textarea");
    expect(screen.getByTestId("separator")).toHaveAttribute("data-slot", "separator");
  });

  it("renders table slots and semantic structure", () => {
    render(
      <Table>
        <TableCaption>Catalog</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow data-state="selected">
            <TableCell>Pump</TableCell>
          </TableRow>
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell>Total</TableCell>
          </TableRow>
        </TableFooter>
      </Table>,
    );

    expect(screen.getByRole("table")).toHaveAttribute("data-slot", "table");
    expect(screen.getByText("Catalog")).toHaveAttribute("data-slot", "table-caption");
    expect(screen.getByText("Name")).toHaveAttribute("data-slot", "table-head");
    expect(screen.getByText("Pump")).toHaveAttribute("data-slot", "table-cell");
  });

  it("renders skeleton variants with requested dimensions", () => {
    const { container } = render(
      <>
        <Skeleton className="custom-skeleton" />
        <SkeletonText lines={2} />
        <SkeletonTable rows={2} columns={3} />
        <SkeletonCard />
      </>,
    );

    expect(container.querySelector('[data-slot="skeleton"].custom-skeleton')).toBeInTheDocument();
    expect(container.querySelectorAll('[data-slot="skeleton-text"] [data-slot="skeleton"]'))
      .toHaveLength(2);
    expect(screen.getByRole("status", { name: "Загрузка таблицы" })).toBeInTheDocument();
    expect(container.querySelectorAll('[data-slot="skeleton-table"] [data-slot="skeleton"]'))
      .toHaveLength(9);
    expect(container.querySelector('[data-slot="skeleton-card"]')).toBeInTheDocument();
  });
});
