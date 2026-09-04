function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function inline(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

/** Minimal, safe markdown: escape first, then bold/italic/code + fences + paragraphs. */
export function renderMarkdown(text: string): string {
  const parts = escapeHtml(text).split(/```\n?/);
  const html: string[] = [];
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      html.push(`<pre><code>${part.replace(/\n$/, "")}</code></pre>`);
    } else if (part.trim()) {
      const paragraphs = part.split(/\n{2,}/).map((p) => inline(p.trim()));
      html.push(`<p>${paragraphs.join("</p><p>")}</p>`);
    }
  });
  return html.join("");
}
