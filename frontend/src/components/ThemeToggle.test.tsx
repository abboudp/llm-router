import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ThemeToggle } from "./ThemeToggle";

describe("ThemeToggle", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  afterEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
  });

  it("starts in light mode by default and shows the sun icon", () => {
    render(<ThemeToggle />);
    expect(screen.getByTestId("theme-toggle")).toHaveTextContent("☀️");
  });

  it("switches to dark on click, applying the attribute and persisting it", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByTestId("theme-toggle"));

    expect(screen.getByTestId("theme-toggle")).toHaveTextContent("🌙");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem("llm-router-theme")).toBe("dark");
  });

  it("toggles back to light on a second click", () => {
    render(<ThemeToggle />);
    const button = screen.getByTestId("theme-toggle");
    fireEvent.click(button);
    fireEvent.click(button);

    expect(button).toHaveTextContent("☀️");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(window.localStorage.getItem("llm-router-theme")).toBe("light");
  });

  it("starts in dark mode if a dark theme was already stored", () => {
    window.localStorage.setItem("llm-router-theme", "dark");
    render(<ThemeToggle />);
    expect(screen.getByTestId("theme-toggle")).toHaveTextContent("🌙");
  });
});
