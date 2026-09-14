import { describe, expect, it } from "vitest";
import { totalTokens } from "./tokens";

describe("totalTokens", () => {
  it("returns 0 for an empty list", () => {
    expect(totalTokens([])).toBe(0);
  });

  it("ignores messages without usage attached", () => {
    expect(totalTokens([{ usage: null }, {}])).toBe(0);
  });

  it("sums prompt and completion tokens across messages", () => {
    const messages = [
      { usage: { prompt_tokens: 10, completion_tokens: 5 } },
      { usage: { prompt_tokens: 20, completion_tokens: 8 } },
    ];
    expect(totalTokens(messages)).toBe(43);
  });

  it("mixes messages with and without usage", () => {
    const messages = [
      { usage: { prompt_tokens: 10, completion_tokens: 5 } },
      { usage: undefined },
      { usage: { prompt_tokens: 3, completion_tokens: 1 } },
    ];
    expect(totalTokens(messages)).toBe(19);
  });
});
