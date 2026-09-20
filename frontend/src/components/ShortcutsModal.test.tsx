import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../state/store";
import { useApp } from "../state/store";
import { ShortcutsModal } from "./ShortcutsModal";

vi.mock("../state/store", () => ({ useApp: vi.fn() }));

function mockApp(shortcutsOpen: boolean) {
  const closeShortcuts = vi.fn();
  vi.mocked(useApp).mockReturnValue({
    state: { shortcutsOpen } as AppState,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    actions: { closeShortcuts } as any,
  });
  return closeShortcuts;
}

describe("ShortcutsModal", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when closed", () => {
    mockApp(false);
    const { container } = render(<ShortcutsModal />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists the app's keyboard shortcuts when open", () => {
    mockApp(true);
    render(<ShortcutsModal />);
    expect(screen.getByTestId("shortcuts-modal")).toBeVisible();
    expect(screen.getByText("Cmd/Ctrl + K")).toBeInTheDocument();
    expect(screen.getByText("Esc")).toBeInTheDocument();
  });

  it("closes via the close button", () => {
    const closeShortcuts = mockApp(true);
    render(<ShortcutsModal />);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(closeShortcuts).toHaveBeenCalledTimes(1);
  });

  it("does not close when the dialog body itself is clicked", () => {
    const closeShortcuts = mockApp(true);
    render(<ShortcutsModal />);
    fireEvent.click(screen.getByTestId("shortcuts-modal"));
    expect(closeShortcuts).not.toHaveBeenCalled();
  });

  it("closes when the backdrop behind the dialog is clicked", () => {
    const closeShortcuts = mockApp(true);
    render(<ShortcutsModal />);
    fireEvent.click(screen.getByTestId("shortcuts-modal").parentElement as HTMLElement);
    expect(closeShortcuts).toHaveBeenCalledTimes(1);
  });
});
