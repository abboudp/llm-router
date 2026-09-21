import { useState } from "react";
import type { Message } from "../api/types";
import { copyToClipboard } from "../lib/clipboard";
import { renderMarkdown } from "../lib/markdown";
import { LatencyChip } from "./LatencyChip";

const COPIED_LABEL_MS = 1500;

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  const copy = async () => {
    const ok = await copyToClipboard(message.content);
    setCopyState(ok ? "copied" : "failed");
    window.setTimeout(() => setCopyState("idle"), COPIED_LABEL_MS);
  };

  const copyLabel = copyState === "copied" ? "Copied" : copyState === "failed" ? "Failed" : "Copy";

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
          <button
            className="copy-message"
            data-testid="copy-message"
            onClick={() => void copy()}
            aria-label="Copy message"
          >
            {copyLabel}
          </button>
        </div>
      )}
    </div>
  );
}
