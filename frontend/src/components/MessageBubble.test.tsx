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

  it("shows the retry button only on the last assistant message", () => {
    const onRetry = vi.fn();
    render(<MessageBubble message={message({})} isFinalReply onRetry={onRetry} />);
    expect(screen.getByTestId("retry-message")).toBeInTheDocument();
  });

  it("hides the retry button when not the last message", () => {
    const onRetry = vi.fn();
    render(<MessageBubble message={message({})} isFinalReply={false} onRetry={onRetry} />);
    expect(screen.queryByTestId("retry-message")).not.toBeInTheDocument();
  });

  it("hides the retry button for user messages even if marked last", () => {
    const onRetry = vi.fn();
    render(<MessageBubble message={message({ role: "user" })} isFinalReply onRetry={onRetry} />);
    expect(screen.queryByTestId("retry-message")).not.toBeInTheDocument();
  });

  it("calls onRetry when the retry button is clicked", () => {
    const onRetry = vi.fn();
    render(<MessageBubble message={message({})} isFinalReply onRetry={onRetry} />);
    fireEvent.click(screen.getByTestId("retry-message"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("disables the retry button while a send is already pending", () => {
    render(<MessageBubble message={message({})} isFinalReply onRetry={vi.fn()} retryDisabled />);
    expect(screen.getByTestId("retry-message")).toBeDisabled();
  });

  it("shows a usage detail toggle when usage is attached, collapsed by default", () => {
    render(
      <MessageBubble
        message={message({ usage: { prompt_tokens: 12, completion_tokens: 4 } })}
      />,
    );
    const detail = screen.getByTestId("usage-detail");
    expect(detail).toBeInTheDocument();
    expect(detail).not.toHaveTextContent("12 prompt");
  });

  it("reveals the token counts once the usage detail is expanded", () => {
    render(
      <MessageBubble
        message={message({ usage: { prompt_tokens: 12, completion_tokens: 4 } })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Usage" }));
    const detail = screen.getByTestId("usage-detail");
    expect(detail).toHaveTextContent("12 prompt");
    expect(detail).toHaveTextContent("4 completion");
  });

  it("omits the usage detail when no usage is attached (e.g. reloaded history)", () => {
    render(<MessageBubble message={message({})} />);
    expect(screen.queryByTestId("usage-detail")).not.toBeInTheDocument();
  });
});
