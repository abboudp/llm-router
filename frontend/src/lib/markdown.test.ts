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

  it("renders h1/h2/h3 headings", () => {
    expect(renderMarkdown("# Title")).toBe("<h1>Title</h1>");
    expect(renderMarkdown("## Subtitle")).toBe("<h2>Subtitle</h2>");
    expect(renderMarkdown("### Detail")).toBe("<h3>Detail</h3>");
  });

  it("renders an unordered list", () => {
    const html = renderMarkdown("- first\n- second\n- third");
    expect(html).toBe("<ul><li>first</li><li>second</li><li>third</li></ul>");
  });

  it("renders an ordered list", () => {
    const html = renderMarkdown("1. first\n2. second");
    expect(html).toBe("<ol><li>first</li><li>second</li></ol>");
  });

  it("renders inline formatting inside list items", () => {
    const html = renderMarkdown("- **bold** item\n- plain");
    expect(html).toContain("<li><strong>bold</strong> item</li>");
  });

  it("renders a link with rel=noopener noreferrer for a safe href", () => {
    const html = renderMarkdown("[docs](https://example.com/docs)");
    expect(html).toContain('<a href="https://example.com/docs" rel="noopener noreferrer"');
    expect(html).toContain(">docs</a>");
  });

  it("neutralizes a javascript: href XSS attempt", () => {
    const html = renderMarkdown("[click me](javascript:alert(1))");
    expect(html).not.toContain("javascript:");
    expect(html).toContain('href="#"');
  });

  it("neutralizes a javascript: href regardless of case or whitespace tricks", () => {
    const html = renderMarkdown("[x](  JaVaScRiPt:alert(1))");
    expect(html).not.toMatch(/javascript:/i);
    expect(html).toContain('href="#"');
  });

  it("allows mailto: and relative/anchor hrefs", () => {
    expect(renderMarkdown("[email](mailto:a@b.com)")).toContain('href="mailto:a@b.com"');
    expect(renderMarkdown("[section](#top)")).toContain('href="#top"');
    expect(renderMarkdown("[home](/)")).toContain('href="/"');
  });
});
