import { describe, expect, it } from "vitest";
import { initialState, reducer } from "./store";

describe("reducer", () => {
  it("selects a conversation and stores messages", () => {
    let s = reducer(initialState, {
      type: "conversations_loaded",
      conversations: [{ id: "c1", title: "T", created_at: 0, updated_at: 0 }],
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
    });
    expect(s.pending).toBe(false);
    expect(s.messages.at(-1)?.content).toBe("yo");
  });

  it("send failure sets error and unlocks", () => {
    let s = reducer(initialState, { type: "selected", id: "c1", messages: [] });
    s = reducer(s, { type: "send_started", userText: "hi" });
    s = reducer(s, { type: "send_failed", error: "conversation not found" });
    expect(s.pending).toBe(false);
    expect(s.error).toBe("conversation not found");
  });
});
