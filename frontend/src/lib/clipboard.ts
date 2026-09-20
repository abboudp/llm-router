/**
 * Copies text to the clipboard, falling back to a legacy hidden-textarea +
 * `execCommand` trick when the async Clipboard API isn't available (e.g. an
 * insecure context, an embedded webview, or an older browser). Returns
 * whether the copy actually succeeded, so callers can decide how to react.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Permission denied or otherwise unavailable — fall through.
    }
  }
  return legacyCopy(text);
}

function legacyCopy(text: string): boolean {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  let succeeded = false;
  try {
    succeeded = document.execCommand("copy");
  } catch {
    succeeded = false;
  }
  document.body.removeChild(textarea);
  return succeeded;
}
