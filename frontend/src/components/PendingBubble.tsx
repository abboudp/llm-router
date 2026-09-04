import { useEffect, useState } from "react";

/** Shown while a chat request is in flight: animated dots + a live elapsed counter. */
export function PendingBubble() {
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const timer = window.setInterval(() => setElapsedMs(Date.now() - start), 100);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="message message-assistant" data-testid="pending-bubble">
      <div className="message-bubble pending-bubble">
        <span className="pending-dots">
          <span />
          <span />
          <span />
        </span>
        <span className="pending-elapsed">{(elapsedMs / 1000).toFixed(1)}s…</span>
      </div>
    </div>
  );
}
