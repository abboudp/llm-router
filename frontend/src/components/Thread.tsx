import { useEffect, useRef } from "react";
import { totalTokens } from "../lib/tokens";
import { useApp } from "../state/store";
import { MessageBubble } from "./MessageBubble";
import { PendingBubble } from "./PendingBubble";

export function Thread() {
  const { state } = useApp();
  const bottomRef = useRef<HTMLDivElement>(null);
  const total = totalTokens(state.messages);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [state.messages.length, state.pending]);

  return (
    <div className="thread-panel">
      {total > 0 && (
        <div className="thread-header" data-testid="thread-token-total">
          {total} tokens this session
        </div>
      )}
      <div className="thread" data-testid="thread">
        {state.messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {state.pending && <PendingBubble />}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
