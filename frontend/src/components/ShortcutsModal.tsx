import { useApp } from "../state/store";

const SHORTCUTS: Array<{ keys: string; description: string }> = [
  { keys: "Cmd/Ctrl + K", description: "Start a new conversation" },
  { keys: "/", description: "Focus the conversation search box" },
  { keys: "Enter", description: "Send the current message" },
  { keys: "Shift + Enter", description: "Insert a newline in the composer" },
  { keys: "Esc", description: "Dismiss the error toast, or close this dialog" },
];

export function ShortcutsModal() {
  const { state, actions } = useApp();
  if (!state.shortcutsOpen) return null;

  return (
    <div className="shortcuts-backdrop" onClick={() => actions.closeShortcuts()}>
      <div
        className="shortcuts-modal"
        data-testid="shortcuts-modal"
        role="dialog"
        aria-label="Keyboard shortcuts"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="shortcuts-header">
          <h2>Keyboard shortcuts</h2>
          <button
            className="shortcuts-close"
            aria-label="Close"
            onClick={() => actions.closeShortcuts()}
          >
            &times;
          </button>
        </div>
        <ul className="shortcuts-list">
          {SHORTCUTS.map((shortcut) => (
            <li key={shortcut.keys}>
              <kbd>{shortcut.keys}</kbd>
              <span>{shortcut.description}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
