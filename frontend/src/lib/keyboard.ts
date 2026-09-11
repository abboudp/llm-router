/** True for the Cmd+K (macOS) / Ctrl+K (everywhere else) "new conversation" hotkey. */
export function isNewConversationHotkey(event: Pick<KeyboardEvent, "metaKey" | "ctrlKey" | "key">): boolean {
  return (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
}

const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/**
 * True when `target` is a form control or a contentEditable node — i.e. a
 * keypress there is regular typing and should not be hijacked as a global
 * keyboard shortcut (e.g. "/" for search, which is also a normal character).
 */
export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (EDITABLE_TAGS.has(target.tagName)) return true;
  const contentEditable = target.getAttribute("contenteditable");
  return contentEditable === "true" || contentEditable === "";
}
