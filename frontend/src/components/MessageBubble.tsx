import { useState } from "react";
import type { Message } from "../api/types";
import { copyToClipboard } from "../lib/clipboard";
import { renderMarkdown } from "../lib/markdown";
import { LatencyChip } from "./LatencyChip";

const COPIED_LABEL_MS = 1500;

export function MessageBubble({
  message,
  isFinalReply = false,
  retryDisabled = false,
  onRetry,
}: {
  message: Message;
  isFinalReply?: boolean;
  retryDisabled?: boolean;
  onRetry?: () => void;
}) {
  const isUser = message.role === "user";
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [usageOpen, setUsageOpen] = useState(false);

  const copy = async () => {
    const ok = await copyToClipboard(message.content);
    setCopyState(ok ? "copied" : "failed");
    window.setTimeout(() => setCopyState("idle"), COPIED_LABEL_MS);
  };

  const copyLabel = copyState === "copied" ? "Copied" : copyState === "failed" ? "Failed" : "Copy";
  const canRetry = !isUser && isFinalReply && Boolean(onRetry);

  return (
    <div
      className={`message message-${message.role}`}
      data-testid={isUser ? "message-user" : "message-assistant"}
    >
      <div className="message-bubble">
        {isUser ? (
          <span className="message-text">{message.content}</span>
        ) : (
          <span
            className="message-text"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
          />
        )}
      </div>
      {!isUser && (
        <div className="message-actions">
          {message.latency_ms != null && <LatencyChip latencyMs={message.latency_ms} />}
          {message.usage && (
            // A controlled disclosure rather than native <details>: the
            // body text only enters the DOM once expanded, so a collapsed
            // usage detail doesn't add to the bubble's visible text.
            <span className="usage-detail" data-testid="usage-detail">
              <button
                type="button"
                className="usage-detail-toggle"
                onClick={() => setUsageOpen((open) => !open)}
                aria-expanded={usageOpen}
              >
                Usage
              </button>
              {usageOpen && (
                <span className="usage-detail-body">
                  {message.usage.prompt_tokens} prompt + {message.usage.completion_tokens}{" "}
                  completion tokens
                </span>
              )}
            </span>
          )}
          <button
            className="copy-message"
            data-testid="copy-message"
            onClick={() => void copy()}
            aria-label="Copy message"
          >
            {copyLabel}
          </button>
          {canRetry && (
            <button
              className="retry-message"
              data-testid="retry-message"
              onClick={onRetry}
              disabled={retryDisabled}
              aria-label="Retry this message"
            >
              Retry
            </button>
          )}
        </div>
      )}
    </div>
  );
}
