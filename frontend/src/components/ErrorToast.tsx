import { useEffect } from "react";
import { useApp } from "../state/store";

export function ErrorToast() {
  const { state, actions } = useApp();

  useEffect(() => {
    if (!state.error) return;
    const timer = window.setTimeout(() => actions.dismissError(), 6000);
    return () => window.clearTimeout(timer);
  }, [state.error, actions]);

  if (!state.error) return null;

  return (
    <div className="error-toast" data-testid="error-toast">
      <span className="error-toast-message">{state.error}</span>
      <button className="error-toast-close" onClick={() => actions.dismissError()} aria-label="Dismiss">
        &times;
      </button>
    </div>
  );
}
