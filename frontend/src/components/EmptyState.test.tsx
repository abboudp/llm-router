import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("keeps the empty-state test id", () => {
    render(<EmptyState />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });

  it("shows onboarding tips mentioning the core shortcuts", () => {
    render(<EmptyState />);
    expect(screen.getByText(/Shift\+Enter/)).toBeInTheDocument();
    expect(screen.getByText(/search your conversations/)).toBeInTheDocument();
    expect(screen.getByText(/closes an open conversation menu/)).toBeInTheDocument();
  });
});
