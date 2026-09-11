import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../state/store";
import { useApp } from "../state/store";
import { ConversationItem } from "./ConversationItem";

vi.mock("../state/store", () => ({ useApp: vi.fn() }));

const conversation = {
  id: "c1",
  title: "Kubernetes migration plan",
  created_at: 0,
  updated_at: Date.now() / 1000 - 120,
};

function mockApp(
  stateOverrides: Partial<AppState> = {},
  actionOverrides: Partial<Record<string, unknown>> = {},
) {
  const actions = {
    select: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
    ...actionOverrides,
  };
  vi.mocked(useApp).mockReturnValue({
    state: { selectedId: null, ...stateOverrides } as AppState,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    actions: actions as any,
  });
  return actions;
}

describe("ConversationItem", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the title and a relative timestamp", () => {
    mockApp();
    render(<ConversationItem conversation={conversation} />);
    expect(screen.getByText("Kubernetes migration plan")).toBeInTheDocument();
    expect(screen.getByText("2m ago")).toBeInTheDocument();
  });

  it("is marked selected when it is the active conversation", () => {
    mockApp({ selectedId: "c1" });
    render(<ConversationItem conversation={conversation} />);
    expect(screen.getByTestId("conversation-item")).toHaveClass("selected");
  });

  it("is not marked selected otherwise", () => {
    mockApp({ selectedId: "other" });
    render(<ConversationItem conversation={conversation} />);
    expect(screen.getByTestId("conversation-item")).not.toHaveClass("selected");
  });

  it("selects the conversation when the row is clicked", () => {
    const actions = mockApp();
    render(<ConversationItem conversation={conversation} />);
    fireEvent.click(screen.getByTestId("conversation-item"));
    expect(actions.select).toHaveBeenCalledWith("c1");
  });

  it("renames via a prompt dialog without also selecting the row", () => {
    const actions = mockApp();
    vi.spyOn(window, "prompt").mockReturnValue("New title");
    render(<ConversationItem conversation={conversation} />);
    fireEvent.click(screen.getByTestId("rename-conversation"));
    expect(actions.rename).toHaveBeenCalledWith("c1", "New title");
    expect(actions.select).not.toHaveBeenCalled();
  });

  it("does not rename when the prompt is cancelled or unchanged", () => {
    const actions = mockApp();
    vi.spyOn(window, "prompt").mockReturnValue(conversation.title);
    render(<ConversationItem conversation={conversation} />);
    fireEvent.click(screen.getByTestId("rename-conversation"));
    expect(actions.rename).not.toHaveBeenCalled();
  });

  it("deletes without also selecting the row", () => {
    const actions = mockApp();
    render(<ConversationItem conversation={conversation} />);
    fireEvent.click(screen.getByTestId("delete-conversation"));
    expect(actions.remove).toHaveBeenCalledWith("c1");
    expect(actions.select).not.toHaveBeenCalled();
  });

  it("triggers an export download without also selecting the row", () => {
    const actions = mockApp();
    render(<ConversationItem conversation={conversation} />);
    fireEvent.click(screen.getByTestId("export-conversation"));
    expect(actions.select).not.toHaveBeenCalled();
  });
});
