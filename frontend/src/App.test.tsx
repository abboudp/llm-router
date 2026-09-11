import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { AppState } from "./state/store";
import { useApp } from "./state/store";

vi.mock("./state/store", () => ({ useApp: vi.fn() }));
vi.mock("./api/client", () => ({
  api: {
    getInfo: vi.fn().mockResolvedValue({ name: "llm-router", version: "0.1.0", models: [], uptime_s: 0 }),
  },
}));

function mockApp(
  stateOverrides: Partial<AppState> = {},
  actionOverrides: Partial<Record<string, unknown>> = {},
) {
  const actions = {
    newConversation: vi.fn(),
    closeShortcuts: vi.fn(),
    dismissError: vi.fn(),
    select: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
    search: vi.fn(),
    setSettings: vi.fn(),
    openShortcuts: vi.fn(),
    send: vi.fn(),
    ...actionOverrides,
  };
  vi.mocked(useApp).mockReturnValue({
    state: {
      conversations: [],
      selectedId: null,
      messages: [],
      pending: false,
      settings: { maxTokens: 64, model: "default" },
      error: null,
      searchQuery: "",
      shortcutsOpen: false,
      creatingConversation: false,
      ...stateOverrides,
    } as AppState,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    actions: actions as any,
  });
  return actions;
}

describe("App", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows the empty state when no conversation is selected", () => {
    mockApp();
    render(<App />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });

  it("shows the thread and composer once a conversation is selected", () => {
    mockApp({ selectedId: "c1" });
    render(<App />);
    expect(screen.getByTestId("thread")).toBeInTheDocument();
    expect(screen.getByTestId("composer-input")).toBeInTheDocument();
  });

  it("starts a new conversation on Cmd/Ctrl+K from anywhere on the page", () => {
    const actions = mockApp();
    render(<App />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(actions.newConversation).toHaveBeenCalledTimes(1);
  });

  it("dismisses the error toast on Escape when the shortcuts modal is closed", () => {
    const actions = mockApp({ error: "conversation not found" });
    render(<App />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(actions.dismissError).toHaveBeenCalledTimes(1);
    expect(actions.closeShortcuts).not.toHaveBeenCalled();
  });

  it("closes the shortcuts modal on Escape in preference to the error toast", () => {
    const actions = mockApp({ error: "conversation not found", shortcutsOpen: true });
    render(<App />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(actions.closeShortcuts).toHaveBeenCalledTimes(1);
    expect(actions.dismissError).not.toHaveBeenCalled();
  });
});
