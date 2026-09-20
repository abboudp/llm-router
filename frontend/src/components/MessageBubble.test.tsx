import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Message } from "../api/types";
import * as clipboard from "../lib/clipboard";
import { MessageBubble } from "./MessageBubble";

vi.mock("../lib/clipboard", () => ({
  copyToClipboard: vi.fn(),
}));

function message(overrides: Partial<Message>): Message {
  return {
    id: "m1",
    conversation_id: "c1",
    role: "assistant",
    content: "hello",
    latency_ms: null,
    created_at: 0,
    ...overrides,
  };
}

describe("MessageBubble", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders user messages as plain, unrendered text", () => {
    render(<MessageBubble message={message({ role: "user", content: "**not bold**" })} />);
    expect(screen.getByTestId("message-user")).toHaveTextContent("**not bold**");
    expect(screen.queryByRole("strong")).not.toBeInTheDocument();
  });

  it("renders assistant messages through the markdown pipeline", () => {
    render(<MessageBubble message={message({ content: "**bold**" })} />);
    const bubble = screen.getByTestId("message-assistant");
    expect(bubble.querySelector("strong")).toHaveTextContent("bold");
  });

  it("shows a latency chip only for assistant messages that have one", () => {
    render(<MessageBubble message={message({ latency_ms: 842 })} />);
    expect(screen.getByTestId("latency-chip")).toHaveTextContent("842 ms");
  });

  it("omits the latency chip when latency is null", () => {
    render(<MessageBubble message={message({ latency_ms: null })} />);
    expect(screen.queryByTestId("latency-chip")).not.toBeInTheDocument();
  });

  it("does not render a copy button for user messages", () => {
    render(<MessageBubble message={message({ role: "user" })} />);
    expect(screen.queryByTestId("copy-message")).not.toBeInTheDocument();
  });

  it("copies the message content and shows a 'Copied' state that clears itself", async () => {
    vi.mocked(clipboard.copyToClipboard).mockResolvedValue(true);
    render(<MessageBubble message={message({ content: "copy me" })} />);

    fireEvent.click(screen.getByTestId("copy-message"));

    expect(await screen.findByText("Copied")).toBeInTheDocument();
    expect(clipboard.copyToClipboard).toHaveBeenCalledWith("copy me");
  });

  it("shows a 'Failed' state when the copy does not succeed", async () => {
    vi.mocked(clipboard.copyToClipboard).mockResolvedValue(false);
    render(<MessageBubble message={message({ content: "oops" })} />);

    fireEvent.click(screen.getByTestId("copy-message"));

    expect(await screen.findByText("Failed")).toBeInTheDocument();
  });
});
