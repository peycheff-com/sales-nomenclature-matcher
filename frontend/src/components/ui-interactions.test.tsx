import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Checkbox } from "@/components/ui/checkbox";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { ModelCombobox } from "@/components/ui/model-combobox";
import { Pagination } from "@/components/ui/pagination";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { QueryErrorBanner } from "@/components/ui/query-error-banner";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger, tabsListVariants } from "@/components/ui/tabs";

describe("interactive ui primitives", () => {
  it("renders checkbox, switch, and label controls", async () => {
    const user = userEvent.setup();
    const onCheckboxChange = vi.fn();
    const onSwitchChange = vi.fn();

    render(
      <>
        <Label htmlFor="approved">Approved</Label>
        <Checkbox id="approved" aria-label="Approved" onCheckedChange={onCheckboxChange} />
        <Switch aria-label="Enabled" onCheckedChange={onSwitchChange} />
      </>,
    );

    await user.click(screen.getByRole("checkbox", { name: "Approved" }));
    await user.click(screen.getByRole("switch", { name: "Enabled" }));

    expect(screen.getByText("Approved")).toHaveAttribute("data-slot", "label");
    expect(onCheckboxChange).toHaveBeenCalledWith(true, expect.objectContaining({ reason: "none" }));
    expect(onSwitchChange).toHaveBeenCalledWith(true);
  });

  it("renders pagination ranges and disabled empty state", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    const { rerender } = render(
      <Pagination page={2} totalPages={5} total={42} pageSize={10} onPageChange={onPageChange} />,
    );

    expect(screen.getByText("Показано 11–20 из 42")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Предыдущая страница" }));
    await user.click(screen.getByRole("button", { name: "Следующая страница" }));
    expect(onPageChange).toHaveBeenNthCalledWith(1, 1);
    expect(onPageChange).toHaveBeenNthCalledWith(2, 3);

    rerender(<Pagination page={1} totalPages={0} total={0} pageSize={10} onPageChange={vi.fn()} />);

    expect(screen.getByText("Нет записей")).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Предыдущая страница" })).toBeDisabled();
  });

  it("renders query errors with optional retry action", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const { rerender } = render(
      <QueryErrorBanner error={new Error("Backend unavailable")} onRetry={onRetry} />,
    );

    expect(screen.getByRole("alert")).toHaveAttribute("data-slot", "query-error-banner");
    expect(screen.getByText("Backend unavailable")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Повторить" }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    rerender(<QueryErrorBanner error={null} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders tab slots and active content", async () => {
    const user = userEvent.setup();
    render(
      <Tabs defaultValue="one" orientation="vertical">
        <TabsList variant="line">
          <TabsTrigger value="one">One</TabsTrigger>
          <TabsTrigger value="two">Two</TabsTrigger>
        </TabsList>
        <TabsContent value="one">First panel</TabsContent>
        <TabsContent value="two">Second panel</TabsContent>
      </Tabs>,
    );

    expect(screen.getByText("First panel")).toHaveAttribute("data-slot", "tabs-content");
    expect(tabsListVariants({ variant: "line" })).toContain("bg-transparent");
    await user.click(screen.getByRole("tab", { name: "Two" }));
    expect(screen.getByText("Second panel")).toBeInTheDocument();
  });

  it("selects existing and custom model values", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ModelCombobox
        value="qwen"
        onChange={onChange}
        options={[
          { id: "qwen", name: "Qwen Local", context_length: 32_000 },
          { id: "llama", name: "Llama Local", context_length: 8_000 },
        ]}
      />,
    );

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByText("Llama Local"));
    expect(onChange).toHaveBeenCalledWith("llama");

    await user.click(screen.getByRole("combobox"));
    await user.type(await screen.findByPlaceholderText("Поиск модели..."), "custom/free");
    await user.click(await screen.findByText('Использовать "custom/free"'));
    expect(onChange).toHaveBeenCalledWith("custom/free");
  });

  it("renders model combobox loading and empty search states", async () => {
    const user = userEvent.setup();

    const { unmount } = render(
      <ModelCombobox value="" onChange={vi.fn()} options={[]} isLoading />,
    );

    await user.click(screen.getByRole("combobox"));
    expect(await screen.findByText("Загрузка моделей...")).toBeInTheDocument();

    unmount();
    render(<ModelCombobox value="" onChange={vi.fn()} options={[]} />);
    await user.click(screen.getByRole("combobox"));
    expect(await screen.findByText("Модели не найдены.")).toBeInTheDocument();
  });

  it("shows raw model ids when the selected model is not in options", () => {
    render(<ModelCombobox value="custom/model" onChange={vi.fn()} options={[]} />);

    expect(screen.getByRole("combobox")).toHaveTextContent("custom/model");
  });

  it("renders popover structural slots", async () => {
    const user = userEvent.setup();
    render(
      <Popover>
        <PopoverTrigger>Open popover</PopoverTrigger>
        <PopoverContent className="custom-popover" align="start" side="top" alignOffset={2} sideOffset={8}>
          <PopoverHeader className="custom-header">
            <PopoverTitle>Provider details</PopoverTitle>
            <PopoverDescription>Configure provider metadata.</PopoverDescription>
          </PopoverHeader>
        </PopoverContent>
      </Popover>,
    );

    await user.click(screen.getByRole("button", { name: "Open popover" }));

    expect(await screen.findByText("Provider details")).toHaveAttribute("data-slot", "popover-title");
    expect(screen.getByText("Configure provider metadata.")).toHaveAttribute(
      "data-slot",
      "popover-description",
    );
    expect(screen.getByText("Provider details").closest('[data-slot="popover-content"]')).toHaveClass(
      "custom-popover",
    );
    expect(screen.getByText("Provider details").closest('[data-slot="popover-header"]')).toHaveClass(
      "custom-header",
    );
  });

  it("renders command palette slots and selectable items", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();

    render(
      <>
        <Command>
          <CommandInput placeholder="Search commands" />
          <CommandList>
            <CommandEmpty>No commands</CommandEmpty>
            <CommandGroup heading="Actions">
              <CommandItem value="sync" onSelect={onSelect}>
                Sync catalog
                <CommandShortcut>⌘S</CommandShortcut>
              </CommandItem>
              <CommandSeparator />
            </CommandGroup>
          </CommandList>
        </Command>
        <CommandDialog open title="Quick Actions" description="Run an action">
          <Command>
            <CommandList>
              <CommandItem value="open">Open action</CommandItem>
            </CommandList>
          </Command>
        </CommandDialog>
      </>,
    );

    await user.click(screen.getByText("Sync catalog"));

    expect(screen.getByPlaceholderText("Search commands")).toHaveAttribute("data-slot", "command-input");
    expect(screen.getByText("Sync catalog")).toHaveAttribute("data-slot", "command-item");
    expect(screen.getByText("⌘S")).toHaveAttribute("data-slot", "command-shortcut");
    expect(document.querySelector('[data-slot="command-separator"]')).toBeInTheDocument();
    expect(screen.getByText("Quick Actions")).toHaveAttribute("data-slot", "dialog-title");
    expect(onSelect).toHaveBeenCalledWith("sync");
  });

  it("renders dialog and alert dialog optional sections", () => {
    render(
      <>
        <Dialog>
          <DialogTrigger>Open dialog trigger</DialogTrigger>
          <DialogClose>Close dialog trigger</DialogClose>
        </Dialog>
        <Dialog open>
          <DialogContent showCloseButton={false}>
            <DialogHeader className="custom-dialog-header">
              <DialogTitle>Dialog title</DialogTitle>
              <DialogDescription>Dialog description</DialogDescription>
            </DialogHeader>
            <DialogFooter showCloseButton>
              <button type="button">Primary action</button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        <AlertDialog>
          <AlertDialogTrigger>Open alert trigger</AlertDialogTrigger>
        </AlertDialog>
        <AlertDialog open>
          <AlertDialogContent size="sm">
            <AlertDialogHeader>
              <AlertDialogMedia>!</AlertDialogMedia>
              <AlertDialogTitle>Archive item?</AlertDialogTitle>
              <AlertDialogDescription>Archive confirmation text.</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel size="sm">Cancel archive</AlertDialogCancel>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </>,
    );

    expect(screen.getByText("Dialog title")).toHaveAttribute("data-slot", "dialog-title");
    expect(screen.getByText("Open dialog trigger")).toHaveAttribute("data-slot", "dialog-trigger");
    expect(screen.getByText("Close dialog trigger")).toHaveAttribute("data-slot", "dialog-close");
    expect(screen.getByText("Dialog description")).toHaveAttribute("data-slot", "dialog-description");
    expect(screen.getByText("Primary action").closest('[data-slot="dialog-footer"]')).toBeInTheDocument();
    expect(screen.getByText("Open alert trigger")).toHaveAttribute("data-slot", "alert-dialog-trigger");
    expect(screen.getByText("Archive item?")).toHaveAttribute("data-slot", "alert-dialog-title");
    expect(screen.getByText("!")).toHaveAttribute("data-slot", "alert-dialog-media");

    expect(screen.getByText("Cancel archive")).toHaveAttribute("data-slot", "alert-dialog-cancel");
  });
});
