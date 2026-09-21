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
  pinned: false,
};

function mockApp(
  stateOverrides: Partial<AppState> = {},
  actionOverrides: Partial<Record<string, unknown>> = {},
) {
  const actions = {
    select: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
    setPinned: vi.fn(),
    ...actionOverrides,
  };
  vi.mocked(useApp).mockReturnValue({
    state: { selectedId: null, ...stateOverrides } as AppState,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    actions: actions as any,
  });
  return actions;
}

function openMenu() {
  fireEvent.click(screen.getByTestId("conversation-menu"));
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

  it("keeps the menu items hidden until the … button is clicked", () => {
    mockApp();
    render(<ConversationItem conversation={conversation} />);
    expect(screen.queryByTestId("pin-conversation")).not.toBeInTheDocument();
    expect(screen.queryByTestId("rename-conversation")).not.toBeInTheDocument();
    expect(screen.queryByTestId("export-conversation")).not.toBeInTheDocument();
    expect(screen.queryByTestId("delete-conversation")).not.toBeInTheDocument();
  });

  it("opens the menu when the … button is clicked, without selecting the row", () => {
    const actions = mockApp();
    render(<ConversationItem conversation={conversation} />);
    fireEvent.click(screen.getByTestId("conversation-menu"));
    expect(screen.getByTestId("rename-conversation")).toBeInTheDocument();
    expect(actions.select).not.toHaveBeenCalled();
  });

  it("closes the menu when Escape is pressed", () => {
    mockApp();
    render(<ConversationItem conversation={conversation} />);
    openMenu();
    expect(screen.getByTestId("rename-conversation")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByTestId("rename-conversation")).not.toBeInTheDocument();
  });

  it("closes the menu when clicking outside of it", () => {
    mockApp();
    render(
      <div>
        <div data-testid="outside">elsewhere</div>
        <ConversationItem conversation={conversation} />
      </div>,
    );
    openMenu();
    expect(screen.getByTestId("rename-conversation")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByTestId("outside"));
    expect(screen.queryByTestId("rename-conversation")).not.toBeInTheDocument();
  });

  it("renames via a prompt dialog without also selecting the row, then closes the menu", () => {
    const actions = mockApp();
    vi.spyOn(window, "prompt").mockReturnValue("New title");
    render(<ConversationItem conversation={conversation} />);
    openMenu();
    fireEvent.click(screen.getByTestId("rename-conversation"));
    expect(actions.rename).toHaveBeenCalledWith("c1", "New title");
    expect(actions.select).not.toHaveBeenCalled();
    expect(screen.queryByTestId("rename-conversation")).not.toBeInTheDocument();
  });

  it("does not rename when the prompt is cancelled or unchanged", () => {
    const actions = mockApp();
    vi.spyOn(window, "prompt").mockReturnValue(conversation.title);
    render(<ConversationItem conversation={conversation} />);
    openMenu();
    fireEvent.click(screen.getByTestId("rename-conversation"));
    expect(actions.rename).not.toHaveBeenCalled();
  });

  it("deletes without also selecting the row, then closes the menu", () => {
    const actions = mockApp();
    render(<ConversationItem conversation={conversation} />);
    openMenu();
    fireEvent.click(screen.getByTestId("delete-conversation"));
    expect(actions.remove).toHaveBeenCalledWith("c1");
    expect(actions.select).not.toHaveBeenCalled();
    expect(screen.queryByTestId("delete-conversation")).not.toBeInTheDocument();
  });

  it("triggers an export download without also selecting the row, then closes the menu", () => {
    const actions = mockApp();
    render(<ConversationItem conversation={conversation} />);
    openMenu();
    fireEvent.click(screen.getByTestId("export-conversation"));
    expect(actions.select).not.toHaveBeenCalled();
    expect(screen.queryByTestId("export-conversation")).not.toBeInTheDocument();
  });

  it("pins an unpinned conversation without also selecting the row", () => {
    const actions = mockApp();
    render(<ConversationItem conversation={conversation} />);
    openMenu();
    fireEvent.click(screen.getByTestId("pin-conversation"));
    expect(actions.setPinned).toHaveBeenCalledWith("c1", true);
    expect(actions.select).not.toHaveBeenCalled();
  });

  it("unpins an already-pinned conversation", () => {
    const actions = mockApp();
    render(<ConversationItem conversation={{ ...conversation, pinned: true }} />);
    openMenu();
    fireEvent.click(screen.getByTestId("pin-conversation"));
    expect(actions.setPinned).toHaveBeenCalledWith("c1", false);
  });

  it("marks the pin menu item as checked only when the conversation is pinned", () => {
    mockApp();
    const { rerender } = render(<ConversationItem conversation={conversation} />);
    openMenu();
    expect(screen.getByTestId("pin-conversation")).toHaveAttribute("role", "menuitemcheckbox");
    expect(screen.getByTestId("pin-conversation")).toHaveAttribute("aria-checked", "false");

    rerender(<ConversationItem conversation={{ ...conversation, pinned: true }} />);
    expect(screen.getByTestId("pin-conversation")).toHaveAttribute("aria-checked", "true");
  });

  it("adds a pinned class to the row when pinned", () => {
    mockApp();
    render(<ConversationItem conversation={{ ...conversation, pinned: true }} />);
    expect(screen.getByTestId("conversation-item")).toHaveClass("pinned");
  });
});
