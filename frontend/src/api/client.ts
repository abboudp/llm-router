import { withQuery } from "../lib/query";
import type { ChatResponse, Conversation, Message } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (body.detail) detail = String(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const api = {
  listConversations: (q?: string) => request<Conversation[]>(withQuery("/v1/conversations", { q })),
  createConversation: (title?: string) =>
    request<Conversation>("/v1/conversations", {
      method: "POST",
      body: JSON.stringify(title ? { title } : {}),
    }),
  renameConversation: (id: string, title: string) =>
    request<Conversation>(`/v1/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  setPinned: (id: string, pinned: boolean) =>
    request<Conversation>(`/v1/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ pinned }),
    }),
  deleteConversation: (id: string) =>
    request<void>(`/v1/conversations/${id}`, { method: "DELETE" }),
  listMessages: (id: string, opts?: { limit?: number; before?: string }) =>
    request<Message[]>(
      withQuery(`/v1/conversations/${id}/messages`, {
        limit: opts?.limit,
        before: opts?.before,
      }),
    ),
  sendChat: (params: { conversation_id: string; message: string }) =>
    request<ChatResponse>("/v1/chat", { method: "POST", body: JSON.stringify(params) }),
};
