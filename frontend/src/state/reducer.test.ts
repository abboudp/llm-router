import { describe, expect, it } from "vitest";
import { initialState, lastRetryableUserText, reducer } from "./store";

describe("reducer", () => {
  it("selects a conversation and stores messages", () => {
    let s = reducer(initialState, {
      type: "conversations_loaded",
      conversations: [{ id: "c1", title: "T", created_at: 0, updated_at: 0, pinned: false }],
    });
    s = reducer(s, { type: "selected", id: "c1", messages: [] });
    expect(s.selectedId).toBe("c1");
  });

  it("tracks a pending send then appends both turns", () => {
    let s = reducer(initialState, { type: "selected", id: "c1", messages: [] });
    s = reducer(s, { type: "send_started", userText: "hi" });
    expect(s.pending).toBe(true);
    expect(s.messages.at(-1)?.role).toBe("user");
    s = reducer(s, {
      type: "send_succeeded",
      message: { id: "m2", conversation_id: "c1", role: "assistant",
                 content: "yo", latency_ms: 1200, created_at: 1 },
      usage: null,
    });
    expect(s.pending).toBe(false);
    expect(s.messages.at(-1)?.content).toBe("yo");
  });

  it("attaches usage to the newly-received assistant message", () => {
    let s = reducer(initialState, { type: "selected", id: "c1", messages: [] });
    s = reducer(s, { type: "send_started", userText: "hi" });
    s = reducer(s, {
      type: "send_succeeded",
      message: { id: "m2", conversation_id: "c1", role: "assistant",
                 content: "yo", latency_ms: 1200, created_at: 1 },
      usage: { prompt_tokens: 12, completion_tokens: 4 },
    });
    expect(s.messages.at(-1)?.usage).toEqual({ prompt_tokens: 12, completion_tokens: 4 });
  });

  it("send failure sets error and unlocks", () => {
    let s = reducer(initialState, { type: "selected", id: "c1", messages: [] });
    s = reducer(s, { type: "send_started", userText: "hi" });
    s = reducer(s, { type: "send_failed", error: "conversation not found" });
    expect(s.pending).toBe(false);
    expect(s.error).toBe("conversation not found");
  });

  it("retry_requested clears a stale error", () => {
    let s = reducer(initialState, { type: "send_failed", error: "conversation not found" });
    expect(s.error).toBe("conversation not found");
    s = reducer(s, { type: "retry_requested" });
    expect(s.error).toBeNull();
  });

  it("tracks the search query and the filtered conversation list", () => {
    let s = reducer(initialState, { type: "search_changed", query: "kube" });
    expect(s.searchQuery).toBe("kube");
    s = reducer(s, {
      type: "conversations_loaded",
      conversations: [
        { id: "c1", title: "Kubernetes plan", created_at: 0, updated_at: 0, pinned: false },
      ],
    });
    expect(s.conversations).toHaveLength(1);
  });

  it("opens and closes the shortcuts modal", () => {
    let s = reducer(initialState, { type: "shortcuts_opened" });
    expect(s.shortcutsOpen).toBe(true);
    s = reducer(s, { type: "shortcuts_closed" });
    expect(s.shortcutsOpen).toBe(false);
  });

  it("tracks whether a conversation creation is in flight", () => {
    let s = reducer(initialState, { type: "conversation_create_started" });
    expect(s.creatingConversation).toBe(true);
    s = reducer(s, { type: "conversation_create_finished" });
    expect(s.creatingConversation).toBe(false);
  });
});

describe("lastRetryableUserText", () => {
  const user = (content: string) =>
    ({ id: "u", conversation_id: "c1", role: "user" as const, content, latency_ms: null, created_at: 0 });
  const assistant = (content: string) =>
    ({ id: "a", conversation_id: "c1", role: "assistant" as const, content, latency_ms: 10, created_at: 1 });

  it("returns null for an empty conversation", () => {
    expect(lastRetryableUserText([])).toBeNull();
  });

  it("returns null when the last message is from the user (still pending)", () => {
    expect(lastRetryableUserText([user("hi")])).toBeNull();
  });

  it("returns the preceding user text when the last message is an assistant reply", () => {
    expect(lastRetryableUserText([user("what is a hash map?"), assistant("it's...")])).toBe(
      "what is a hash map?",
    );
  });

  it("only considers the very last exchange, not earlier ones", () => {
    const messages = [user("first"), assistant("reply one"), user("second"), assistant("reply two")];
    expect(lastRetryableUserText(messages)).toBe("second");
  });

  it("returns null if two assistant messages are somehow adjacent", () => {
    expect(lastRetryableUserText([assistant("one"), assistant("two")])).toBeNull();
  });
});
