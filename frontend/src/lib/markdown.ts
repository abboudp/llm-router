function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

// Only these URL schemes (plus in-page anchors and root-relative paths) are
// allowed as link targets. Anything else — javascript:, data:, vbscript:,
// unknown schemes — is neutralized to "#" so a link can never execute script.
const SAFE_HREF = /^(https?:|mailto:)/i;

function sanitizeHref(rawHref: string): string {
  const href = rawHref.trim();
  if (href.startsWith("#")) return href;
  // A root-relative path ("/foo") stays on this origin and is safe, but a
  // *protocol-relative* one ("//evil.com") is not: browsers resolve the
  // leading "//" against the current scheme, so it navigates off-site just
  // like a full "https://evil.com" href would.
  if (href.startsWith("/") && !href.startsWith("//")) return href;
  return SAFE_HREF.test(href) ? href : "#";
}

function inline(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label: string, href: string) => {
      const safeHref = sanitizeHref(href);
      return `<a href="${safeHref}" rel="noopener noreferrer" target="_blank">${label}</a>`;
    })
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

/** Renders one blank-line-delimited block: a rule, heading, list, blockquote, or paragraph. */
function renderBlock(block: string): string {
  const trimmed = block.trim();
  const lines = trimmed.split("\n");

  if (lines.length === 1 && /^-{3,}$/.test(lines[0])) {
    return "<hr>";
  }

  const heading = lines.length === 1 ? /^(#{1,3})\s+(.+)$/.exec(lines[0]) : null;
  if (heading) {
    const level = heading[1].length;
    return `<h${level}>${inline(heading[2])}</h${level}>`;
  }

  if (lines.every((line) => /^[-*]\s+/.test(line))) {
    const items = lines.map((line) => `<li>${inline(line.replace(/^[-*]\s+/, ""))}</li>`);
    return `<ul>${items.join("")}</ul>`;
  }

  if (lines.every((line) => /^\d+\.\s+/.test(line))) {
    const items = lines.map((line) => `<li>${inline(line.replace(/^\d+\.\s+/, ""))}</li>`);
    return `<ol>${items.join("")}</ol>`;
  }

  // The whole input is HTML-escaped before blocks are split out, so a
  // literal ">" has already become "&gt;" by the time we get here.
  if (lines.every((line) => /^&gt;\s?/.test(line))) {
    const content = lines.map((line) => line.replace(/^&gt;\s?/, "")).join("\n");
    return `<blockquote>${inline(content)}</blockquote>`;
  }

  return `<p>${inline(trimmed)}</p>`;
}

/**
 * Minimal, safe markdown renderer: escape first, then fenced code blocks,
 * headings (#/##/###), unordered/ordered lists, blockquotes, horizontal
 * rules, links, and bold/italic/code. Links are restricted to
 * http(s)/mailto/relative targets — anything else (e.g. `javascript:`) is
 * neutralized.
 */
export function renderMarkdown(text: string): string {
  const parts = escapeHtml(text).split(/```\n?/);
  const html: string[] = [];
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      html.push(`<pre><code>${part.replace(/\n$/, "")}</code></pre>`);
    } else if (part.trim()) {
      const blocks = part.split(/\n{2,}/).filter((block) => block.trim());
      html.push(blocks.map(renderBlock).join(""));
    }
  });
  return html.join("");
}
