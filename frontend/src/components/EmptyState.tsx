const TIPS = [
  "Enter to send, Shift+Enter for a new line",
  "Press / to search your conversations",
  "Esc closes an open conversation menu",
];

export function EmptyState() {
  return (
    <div className="empty-state" data-testid="empty-state">
      <div className="empty-state-card">
        <p className="empty-state-title">Select or start a conversation</p>
        <ul className="empty-state-tips">
          {TIPS.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
