export interface Conversation {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  latency_ms: number | null;
  created_at: number;
}

export interface ChatResponse {
  message: Message;
  latency_ms: number;
  model: string | null;
  usage: { prompt_tokens: number; completion_tokens: number } | null;
}
