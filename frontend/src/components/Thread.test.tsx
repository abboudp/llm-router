import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../state/store";
import { useApp } from "../state/store";
import { Thread } from "./Thread";

vi.mock("../state/store", () => ({ useApp: vi.fn() }));

function mockApp(messages: AppState["messages"], pending = false) {
  const actions = {};
  vi.mocked(useApp).mockReturnValue({
    state: { messages, pending } as AppState,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    actions: actions as any,
  });
  return actions;
}

const userMsg = {
  id: "u1", conversation_id: "c1", role: "user" as const, content: "hi",
  latency_ms: null, created_at: 0,
};
const assistantMsg = (usage?: { prompt_tokens: number; completion_tokens: number }) => ({
  id: "a1", conversation_id: "c1", role: "assistant" as const, content: "hello",
  latency_ms: 10, created_at: 1, usage,
});

describe("Thread", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("hides the token total when no message carries usage", () => {
    mockApp([userMsg, assistantMsg()]);
    render(<Thread />);
    expect(screen.queryByTestId("thread-token-total")).not.toBeInTheDocument();
  });

  it("shows the summed token total once usage is attached", () => {
    mockApp([userMsg, assistantMsg({ prompt_tokens: 10, completion_tokens: 5 })]);
    render(<Thread />);
    expect(screen.getByTestId("thread-token-total")).toHaveTextContent("15 tokens this session");
  });
});
