import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("escapes HTML in input", () => {
    expect(renderMarkdown("<script>alert(1)</script>")).not.toContain("<script>");
    expect(renderMarkdown("<b>x</b>")).toContain("&lt;b&gt;");
  });
  it("renders bold, italic, inline code", () => {
    expect(renderMarkdown("**hi**")).toContain("<strong>hi</strong>");
    expect(renderMarkdown("*hi*")).toContain("<em>hi</em>");
    expect(renderMarkdown("`x = 1`")).toContain("<code>x = 1</code>");
  });
  it("renders fenced code blocks", () => {
    const html = renderMarkdown("```\nline1\nline2\n```");
    expect(html).toContain("<pre><code>line1\nline2</code></pre>");
  });
  it("preserves paragraphs", () => {
    expect(renderMarkdown("a\n\nb")).toContain("</p><p>");
  });
});
