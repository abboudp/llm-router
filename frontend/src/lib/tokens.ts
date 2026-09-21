import type { Usage } from "../api/types";

/**
 * Sums prompt + completion tokens across a list of messages. Usage is only
 * ever attached (client-side) to messages received during the current
 * session — historical ones loaded from the server don't carry it — so this
 * naturally reports "tokens used so far this session", not a conversation's
 * lifetime total.
 */
export function totalTokens(messages: Array<{ usage?: Usage | null }>): number {
  return messages.reduce((sum, message) => {
    if (!message.usage) return sum;
    return sum + message.usage.prompt_tokens + message.usage.completion_tokens;
  }, 0);
}
