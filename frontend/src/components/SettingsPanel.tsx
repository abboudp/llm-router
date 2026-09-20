import { useApp } from "../state/store";

const MAX_TOKENS_OPTIONS = [16, 32, 64, 128, 256];
const MODEL_OPTIONS = [
  { value: "default", label: "default" },
  { value: "mock-large", label: "mock-large" },
];

export function SettingsPanel() {
  const { state, actions } = useApp();

  return (
    <div className="settings-panel">
      <label className="settings-field">
        <span>Max tokens</span>
        <select
          data-testid="settings-max-tokens"
          value={state.settings.maxTokens}
          onChange={(event) => actions.setSettings({ maxTokens: Number(event.target.value) })}
        >
          {MAX_TOKENS_OPTIONS.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label className="settings-field">
        <span>Model</span>
        <select
          data-testid="settings-model"
          value={state.settings.model}
          onChange={(event) => actions.setSettings({ model: event.target.value })}
        >
          {MODEL_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
