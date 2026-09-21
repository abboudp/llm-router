import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { AppState } from "./state/store";
import { useApp } from "./state/store";

vi.mock("./state/store", () => ({ useApp: vi.fn() }));

function mockApp(
  stateOverrides: Partial<AppState> = {},
  actionOverrides: Partial<Record<string, unknown>> = {},
) {
  const actions = {
    newConversation: vi.fn(),
    dismissError: vi.fn(),
    select: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
    search: vi.fn(),
    send: vi.fn(),
    ...actionOverrides,
  };
  vi.mocked(useApp).mockReturnValue({
    state: {
      conversations: [],
      selectedId: null,
      messages: [],
      pending: false,
      error: null,
      searchQuery: "",
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
});
