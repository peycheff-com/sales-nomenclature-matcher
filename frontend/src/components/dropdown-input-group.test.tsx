import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuPortal,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
  InputGroupText,
  InputGroupTextarea,
} from "@/components/ui/input-group";

vi.mock("@base-ui/react/menu", () => ({
  Menu: {
    Root: ({ children, ...props }: { children: ReactNode }) => <div {...props}>{children}</div>,
    Portal: ({ children, ...props }: { children: ReactNode }) => <div {...props}>{children}</div>,
    Trigger: ({ children, ...props }: { children: ReactNode }) => <button {...props}>{children}</button>,
    Positioner: ({ children, className }: { children: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    Popup: ({ children, className, ...props }: { children: ReactNode; className?: string }) => (
      <div className={className} {...props}>{children}</div>
    ),
    Group: ({ children, ...props }: { children: ReactNode }) => <div {...props}>{children}</div>,
    GroupLabel: ({ children, className, ...props }: { children: ReactNode; className?: string }) => (
      <div className={className} {...props}>{children}</div>
    ),
    Item: ({ children, className, ...props }: { children: ReactNode; className?: string }) => (
      <button className={className} {...props}>{children}</button>
    ),
    SubmenuRoot: ({ children, ...props }: { children: ReactNode }) => <div {...props}>{children}</div>,
    SubmenuTrigger: ({ children, className, ...props }: { children: ReactNode; className?: string }) => (
      <button className={className} {...props}>{children}</button>
    ),
    CheckboxItem: ({
      children,
      className,
      checked,
      ...props
    }: {
      children: ReactNode;
      className?: string;
      checked?: boolean;
    }) => (
      <button aria-checked={checked} className={className} role="menuitemcheckbox" {...props}>
        {children}
      </button>
    ),
    CheckboxItemIndicator: ({ children }: { children: ReactNode }) => <span>{children}</span>,
    RadioGroup: ({ children, ...props }: { children: ReactNode }) => <div {...props}>{children}</div>,
    RadioItem: ({
      children,
      className,
      ...props
    }: {
      children: ReactNode;
      className?: string;
    }) => (
      <button className={className} role="menuitemradio" {...props}>
        {children}
      </button>
    ),
    RadioItemIndicator: ({ children }: { children: ReactNode }) => <span>{children}</span>,
    Separator: ({ className, ...props }: { className?: string }) => <hr className={className} {...props} />,
  },
}));

describe("dropdown menu and input group primitives", () => {
  it("renders all dropdown menu slots and variants", () => {
    render(
      <DropdownMenu>
        <DropdownMenuTrigger>Open menu</DropdownMenuTrigger>
        <DropdownMenuPortal>
          <DropdownMenuContent className="menu-content" align="end" side="top">
            <DropdownMenuGroup>
              <DropdownMenuLabel inset>Actions</DropdownMenuLabel>
              <DropdownMenuItem inset>Rename</DropdownMenuItem>
              <DropdownMenuItem variant="destructive">Delete</DropdownMenuItem>
              <DropdownMenuCheckboxItem checked>Enabled</DropdownMenuCheckboxItem>
              <DropdownMenuRadioGroup>
                <DropdownMenuRadioItem value="one">One</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSub>
                <DropdownMenuSubTrigger inset>More</DropdownMenuSubTrigger>
                <DropdownMenuSubContent>Nested</DropdownMenuSubContent>
              </DropdownMenuSub>
              <DropdownMenuSeparator />
              <DropdownMenuShortcut>⌘K</DropdownMenuShortcut>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenuPortal>
      </DropdownMenu>,
    );

    expect(screen.getByText("Open menu")).toHaveAttribute("data-slot", "dropdown-menu-trigger");
    expect(screen.getByText("Actions")).toHaveAttribute("data-slot", "dropdown-menu-label");
    expect(screen.getByText("Rename")).toHaveAttribute("data-inset", "true");
    expect(screen.getByText("Delete")).toHaveAttribute("data-variant", "destructive");
    expect(screen.getByRole("menuitemcheckbox", { name: /Enabled/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("menuitemradio", { name: /One/ })).toHaveAttribute("data-slot", "dropdown-menu-radio-item");
    expect(screen.getByText("More")).toHaveAttribute("data-slot", "dropdown-menu-sub-trigger");
    expect(screen.getByText("Nested")).toHaveAttribute("data-slot", "dropdown-menu-sub-content");
    expect(screen.getByText("⌘K")).toHaveAttribute("data-slot", "dropdown-menu-shortcut");
  });

  it("renders input group controls and focuses the input from addons", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(
      <>
        <InputGroup>
          <InputGroupAddon align="inline-start">
            <InputGroupText>Search</InputGroupText>
          </InputGroupAddon>
          <InputGroupInput aria-label="Search query" />
          <InputGroupAddon align="inline-end">
            <InputGroupButton onClick={onClick}>Go</InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
        <InputGroup>
          <InputGroupAddon align="block-start">Notes</InputGroupAddon>
          <InputGroupTextarea aria-label="Notes body" />
          <InputGroupAddon align="block-end">Footer</InputGroupAddon>
        </InputGroup>
      </>,
    );

    await user.click(screen.getByText("Search"));
    expect(screen.getByLabelText("Search query")).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("Notes body")).toHaveAttribute("data-slot", "input-group-control");
    expect(screen.getByText("Footer")).toHaveAttribute("data-align", "block-end");
  });
});
