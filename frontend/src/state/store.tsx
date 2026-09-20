import { createContext, useCallback, useContext, useEffect, useReducer } from "react";
import { api } from "../api/client";
import type { Conversation, Message } from "../api/types";

export interface Settings {
  maxTokens: number;
  model: string;
}

export interface AppState {
  conversations: Conversation[];
  selectedId: string | null;
  messages: Message[];
  pending: boolean;
  settings: Settings;
  error: string | null;
}

export const initialState: AppState = {
  conversations: [],
  selectedId: null,
  messages: [],
  pending: false,
  settings: { maxTokens: 64, model: "default" },
  error: null,
};

export type Action =
  | { type: "conversations_loaded"; conversations: Conversation[] }
  | { type: "selected"; id: string | null; messages: Message[] }
  | { type: "send_started"; userText: string }
  | { type: "send_succeeded"; message: Message }
  | { type: "send_failed"; error: string }
  | { type: "settings_changed"; settings: Partial<Settings> }
  | { type: "error"; error: string }
  | { type: "error_dismissed" };

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "conversations_loaded":
      return { ...state, conversations: action.conversations };
    case "selected":
      return { ...state, selectedId: action.id, messages: action.messages, error: null };
    case "send_started": {
      const optimistic: Message = {
        id: `local-${Date.now()}`,
        conversation_id: state.selectedId ?? "",
        role: "user",
        content: action.userText,
        latency_ms: null,
        created_at: Date.now() / 1000,
      };
      return { ...state, pending: true, messages: [...state.messages, optimistic] };
    }
    case "send_succeeded":
      return { ...state, pending: false, messages: [...state.messages, action.message] };
    case "send_failed":
      return { ...state, pending: false, error: action.error };
    case "settings_changed":
      return { ...state, settings: { ...state.settings, ...action.settings } };
    case "error":
      return { ...state, error: action.error };
    case "error_dismissed":
      return { ...state, error: null };
    default:
      return state;
  }
}

const AppContext = createContext<ReturnType<typeof buildValue> | null>(null);

function buildValue(state: AppState, dispatch: React.Dispatch<Action>) {
  const refresh = async () => {
    dispatch({ type: "conversations_loaded", conversations: await api.listConversations() });
  };
  const select = async (id: string | null) => {
    dispatch({ type: "selected", id, messages: id ? await api.listMessages(id) : [] });
  };
  const actions = {
    refresh,
    select,
    newConversation: async () => {
      const conversation = await api.createConversation();
      await refresh();
      await select(conversation.id);
    },
    rename: async (id: string, title: string) => {
      await api.renameConversation(id, title);
      await refresh();
    },
    remove: async (id: string) => {
      await api.deleteConversation(id);
      await refresh();
      if (state.selectedId === id) await select(null);
    },
    send: async (text: string) => {
      if (!state.selectedId || state.pending || !text.trim()) return;
      dispatch({ type: "send_started", userText: text });
      try {
        const resp = await api.sendChat({
          conversation_id: state.selectedId,
          message: text,
          max_tokens: state.settings.maxTokens,
          ...(state.settings.model !== "default" ? { model: state.settings.model } : {}),
        });
        dispatch({ type: "send_succeeded", message: resp.message });
        await refresh(); // titles/order may have changed
      } catch (err) {
        dispatch({ type: "send_failed", error: (err as Error).message });
      }
    },
    setSettings: (settings: Partial<Settings>) =>
      dispatch({ type: "settings_changed", settings }),
    dismissError: () => dispatch({ type: "error_dismissed" }),
  };
  return { state, actions };
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const value = buildValue(state, dispatch);
  const refreshOnce = useCallback(value.actions.refresh, []);
  useEffect(() => {
    void refreshOnce();
  }, [refreshOnce]);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside provider");
  return ctx;
}
