import type { Message } from "../api/types";
import { renderMarkdown } from "../lib/markdown";
import { LatencyChip } from "./LatencyChip";

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
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
      {!isUser && message.latency_ms != null && <LatencyChip latencyMs={message.latency_ms} />}
    </div>
  );
}
