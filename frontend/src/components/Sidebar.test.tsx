import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../state/store";
import { useApp } from "../state/store";
import { Sidebar } from "./Sidebar";

vi.mock("../state/store", () => ({ useApp: vi.fn() }));
vi.mock("../api/client", () => ({
  api: {
    getInfo: vi.fn().mockResolvedValue({
      name: "llm-router",
      version: "0.1.0",
      models: ["default"],
      uptime_s: 1,
    }),
  },
}));

function mockApp(
  conversations: AppState["conversations"],
  actionOverrides: Partial<Record<string, unknown>> = {},
) {
  const actions = {
    select: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
    newConversation: vi.fn(),
    search: vi.fn(),
    setSettings: vi.fn(),
    openShortcuts: vi.fn(),
    ...actionOverrides,
  };
  vi.mocked(useApp).mockReturnValue({
    state: {
      conversations,
      selectedId: null,
      searchQuery: "",
      settings: { maxTokens: 64, model: "default" },
      creatingConversation: false,
    } as AppState,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    actions: actions as any,
  });
  return actions;
}

describe("Sidebar", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("renders one row per conversation", () => {
    mockApp([
      { id: "c1", title: "One", created_at: 0, updated_at: 0 },
      { id: "c2", title: "Two", created_at: 0, updated_at: 0 },
    ]);
    render(<Sidebar />);
    expect(screen.getAllByTestId("conversation-item")).toHaveLength(2);
  });

  it("debounces the search box before calling actions.search", () => {
    const actions = mockApp([]);
    render(<Sidebar />);

    fireEvent.change(screen.getByTestId("conversation-search"), { target: { value: "kube" } });
    expect(actions.search).not.toHaveBeenCalled();

    vi.advanceTimersByTime(249);
    expect(actions.search).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(actions.search).toHaveBeenCalledWith("kube");
  });

  it("does not fire a search on mount for the initial empty query", () => {
    const actions = mockApp([]);
    render(<Sidebar />);
    vi.advanceTimersByTime(1000);
    expect(actions.search).not.toHaveBeenCalled();
  });

  it("shows a no-results message instead of the list when a search matches nothing", () => {
    mockApp([]);
    render(<Sidebar />);
    fireEvent.change(screen.getByTestId("conversation-search"), { target: { value: "nothing" } });
    expect(screen.getByTestId("conversation-search-empty")).toHaveTextContent(
      "No conversations match “nothing”.",
    );
  });

  it("disables the new-conversation button while a create is already in flight", () => {
    vi.mocked(useApp).mockReturnValue({
      state: {
        conversations: [],
        selectedId: null,
        searchQuery: "",
        settings: { maxTokens: 64, model: "default" },
        creatingConversation: true,
      } as unknown as AppState,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      actions: { newConversation: vi.fn() } as any,
    });
    render(<Sidebar />);
    expect(screen.getByTestId("new-conversation")).toBeDisabled();
  });

  it("focuses the search box when '/' is pressed outside a text field", () => {
    mockApp([]);
    render(<Sidebar />);
    fireEvent.keyDown(window, { key: "/" });
    expect(screen.getByTestId("conversation-search")).toHaveFocus();
  });
});
