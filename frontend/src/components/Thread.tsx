import { useEffect, useRef } from "react";
import { useApp } from "../state/store";
import { MessageBubble } from "./MessageBubble";
import { PendingBubble } from "./PendingBubble";

export function Thread() {
  const { state } = useApp();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [state.messages.length, state.pending]);

  return (
    <div className="thread-panel">
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
