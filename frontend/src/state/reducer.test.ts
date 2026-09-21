import { describe, expect, it } from "vitest";
import { initialState, reducer } from "./store";

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

  it("send failure sets the error, unlocks, removes the orphaned optimistic message, and stashes its text", () => {
    let s = reducer(initialState, { type: "selected", id: "c1", messages: [] });
    s = reducer(s, { type: "send_started", userText: "hi" });
    expect(s.messages).toHaveLength(1);
    s = reducer(s, { type: "send_failed", error: "conversation not found", userText: "hi" });
    expect(s.pending).toBe(false);
    expect(s.error).toBe("conversation not found");
    // The optimistic user message never made it into server-side history,
    // so it's removed rather than left as an orphaned bubble...
    expect(s.messages).toHaveLength(0);
    // ...and its text is stashed so the error toast's retry button can
    // re-send it.
    expect(s.failedText).toBe("hi");
  });

  it("only removes the failed send's own optimistic message, not earlier history", () => {
    let s = reducer(initialState, {
      type: "selected",
      id: "c1",
      messages: [
        { id: "m1", conversation_id: "c1", role: "user", content: "earlier", latency_ms: null, created_at: 0 },
        { id: "m2", conversation_id: "c1", role: "assistant", content: "reply", latency_ms: 5, created_at: 1 },
      ],
    });
    s = reducer(s, { type: "send_started", userText: "second try" });
    s = reducer(s, { type: "send_failed", error: "boom", userText: "second try" });
    expect(s.messages.map((m) => m.id)).toEqual(["m1", "m2"]);
    expect(s.failedText).toBe("second try");
  });

  it("starting a new send clears any previously stashed failure", () => {
    let s = reducer(initialState, { type: "send_failed", error: "conversation not found", userText: "hi" });
    expect(s.error).toBe("conversation not found");
    expect(s.failedText).toBe("hi");
    s = reducer(s, { type: "send_started", userText: "hi" });
    expect(s.error).toBeNull();
    expect(s.failedText).toBeNull();
  });

  it("selecting a different conversation clears any stashed failure from the previous one", () => {
    let s = reducer(initialState, { type: "send_failed", error: "conversation not found", userText: "hi" });
    s = reducer(s, { type: "selected", id: "c2", messages: [] });
    expect(s.failedText).toBeNull();
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

  it("tracks whether a conversation creation is in flight", () => {
    let s = reducer(initialState, { type: "conversation_create_started" });
    expect(s.creatingConversation).toBe(true);
    s = reducer(s, { type: "conversation_create_finished" });
    expect(s.creatingConversation).toBe(false);
  });
});
