import { useEffect } from "react";
import { useApp } from "../state/store";

export function ErrorToast() {
  const { state, actions } = useApp();

  useEffect(() => {
    if (!state.error) return;
    const timer = window.setTimeout(() => actions.dismissError(), 6000);
    return () => window.clearTimeout(timer);
    // Deliberately omit `actions` here: AppProvider rebuilds it on every
    // render, and including it would restart this timer on any unrelated
    // dispatch while the toast is showing. The dispatch identity behind
    // `actions.dismissError` is stable, so calling it from this closure
    // after the dependency-triggered re-render is safe.
  }, [state.error]);

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
