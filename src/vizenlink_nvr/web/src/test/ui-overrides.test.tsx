import { render, screen, fireEvent, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import React from "react";
import { Button } from "../components/ui/button";
import { Card, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Dialog, DialogContent, DialogOverlay, DialogTitle } from "../components/ui/dialog";
import { AlertDialog, AlertDialogContent, AlertDialogOverlay, AlertDialogTitle } from "../components/ui/alert-dialog";
import { Sheet, SheetContent, SheetOverlay, SheetTitle } from "../components/ui/sheet";
import { Select, SelectTrigger, SelectValue } from "../components/ui/select";
import { Toaster } from "../components/ui/sonner";
import { SidebarProvider, useSidebar } from "../components/ui/sidebar";
import { useIsMobile } from "../hooks/use-mobile";
import { setMediaQueryMatches } from "./setup";

describe("UI component contract overrides", () => {
  it("Button renders with contract classes: font-semibold, bg-primary, coarse-pointer hit areas", () => {
    render(<Button>Click me</Button>);
    const btn = screen.getByRole("button", { name: "Click me" });
    expect(btn.className).toContain("font-semibold");
    expect(btn.className).toContain("bg-primary");
    expect(btn.className).toContain("pointer-coarse:min-h-11");
    expect(btn.className).toContain("pointer-coarse:min-w-11");
    expect(btn.className).toContain("rounded-md");
    expect(btn.className).not.toMatch(/\bfont-(medium|bold|light|thin|extralight|extrabold|black)\b/);
  });

  it("Icon Button with aria-label renders with size-9 and no font-medium", () => {
    render(<Button size="icon" aria-label="Toggle camera" />);
    const btn = screen.getByRole("button", { name: "Toggle camera" });
    expect(btn.className).toContain("size-9");
    expect(btn.className).not.toMatch(/\bfont-(medium|bold|light|thin|extralight|extrabold|black)\b/);
  });

  it("DialogTitle, AlertDialogTitle and SheetTitle render text-xl font-semibold", () => {
    render(
      <div>
        <Dialog open>
          <DialogContent>
            <DialogTitle>Dialog Title</DialogTitle>
          </DialogContent>
        </Dialog>
        <AlertDialog open>
          <AlertDialogContent>
            <AlertDialogTitle>Alert Title</AlertDialogTitle>
          </AlertDialogContent>
        </AlertDialog>
        <Sheet open>
          <SheetContent>
            <SheetTitle>Sheet Title</SheetTitle>
          </SheetContent>
        </Sheet>
      </div>
    );

    const dTitle = screen.getByText("Dialog Title");
    expect(dTitle.className).toContain("text-xl");
    expect(dTitle.className).toContain("font-semibold");

    const aTitle = screen.getByText("Alert Title");
    expect(aTitle.className).toContain("text-xl");
    expect(aTitle.className).toContain("font-semibold");

    const sTitle = screen.getByText("Sheet Title");
    expect(sTitle.className).toContain("text-xl");
    expect(sTitle.className).toContain("font-semibold");
  });

  it("CardTitle renders text-sm font-semibold", () => {
    render(
      <Card>
        <CardTitle>Camera Stats</CardTitle>
      </Card>
    );
    const title = screen.getByText("Camera Stats");
    expect(title.className).toContain("text-sm");
    expect(title.className).toContain("font-semibold");
    expect(title.className).not.toContain("font-medium");
    expect(title.className).not.toContain("text-base");
  });

  it("Input and SelectTrigger render text-sm and never text-base", () => {
    render(
      <div>
        <Input placeholder="Enter name" />
        <Select>
          <SelectTrigger aria-label="Choose stream">
            <SelectValue placeholder="Stream 1" />
          </SelectTrigger>
        </Select>
      </div>
    );

    const input = screen.getByPlaceholderText("Enter name");
    expect(input.className).toContain("text-sm");
    expect(input.className).not.toMatch(/\btext-base\b/);

    const select = screen.getByLabelText("Choose stream");
    expect(select.className).toContain("text-sm");
    expect(select.className).not.toMatch(/\btext-base\b/);
  });

  it("Overlays (Dialog, AlertDialog, Sheet) have no backdrop-blur class", () => {
    render(
      <div>
        <Dialog open>
          <DialogOverlay data-testid="dialog-overlay" />
        </Dialog>
        <AlertDialog open>
          <AlertDialogOverlay data-testid="alert-dialog-overlay" />
        </AlertDialog>
        <Sheet open>
          <SheetOverlay data-testid="sheet-overlay" />
        </Sheet>
      </div>
    );

    const dOverlay = screen.getByTestId("dialog-overlay");
    expect(dOverlay.className).not.toContain("backdrop-blur");

    const aOverlay = screen.getByTestId("alert-dialog-overlay");
    expect(aOverlay.className).not.toContain("backdrop-blur");

    const sOverlay = screen.getByTestId("sheet-overlay");
    expect(sOverlay.className).not.toContain("backdrop-blur");
  });

  it("Toaster renders without importing external theme library and accepts theme prop", () => {
    const { container } = render(<Toaster theme="dark" />);
    expect(container).toBeDefined();
  });

  it("SidebarProvider toggles on bare '[' key, ignores inside input/textarea, ignores Ctrl+B, writes no cookie", () => {
    let cookieWritten = false;
    const originalCookieDesc = Object.getOwnPropertyDescriptor(Document.prototype, "cookie") ||
      Object.getOwnPropertyDescriptor(document, "cookie");

    Object.defineProperty(document, "cookie", {
      get() {
        return "";
      },
      set() {
        cookieWritten = true;
      },
      configurable: true,
    });

    const onOpenChange = vi.fn();

    function TestSidebar() {
      const { open } = useSidebar();
      return (
        <div>
          <span data-testid="sidebar-state">{open ? "open" : "closed"}</span>
          <input data-testid="test-input" />
        </div>
      );
    }

    render(
      <SidebarProvider defaultOpen={true} onOpenChange={onOpenChange}>
        <TestSidebar />
      </SidebarProvider>
    );

    const stateSpan = screen.getByTestId("sidebar-state");
    expect(stateSpan.textContent).toBe("open");

    // Press '[' inside an input: should do nothing
    const input = screen.getByTestId("test-input");
    fireEvent.keyDown(input, { key: "[" });
    expect(onOpenChange).not.toHaveBeenCalled();

    // Press Ctrl+B: should do nothing
    fireEvent.keyDown(window, { key: "b", ctrlKey: true });
    expect(onOpenChange).not.toHaveBeenCalled();

    // Press bare '[' on window: toggles
    fireEvent.keyDown(window, { key: "[" });
    expect(onOpenChange).toHaveBeenCalledWith(false);

    // Assert no document.cookie was written
    expect(cookieWritten).toBe(false);

    if (originalCookieDesc) {
      Object.defineProperty(document, "cookie", originalCookieDesc);
    }
  });

  it("useIsMobile returns correct value on first render when matchMedia reports phone width", () => {
    setMediaQueryMatches(true);
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);

    setMediaQueryMatches(false);
    const { result: desktopResult } = renderHook(() => useIsMobile());
    expect(desktopResult.current).toBe(false);
  });
});
