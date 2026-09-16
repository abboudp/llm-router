import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AppState } from "../state/store";
import { useApp } from "../state/store";
import { ErrorToast } from "./ErrorToast";

vi.mock("../state/store", () => ({ useApp: vi.fn() }));

function mockApp(stateOverrides: Partial<AppState> = {}) {
  const actions = { dismissError: vi.fn(), retryLast: vi.fn() };
  vi.mocked(useApp).mockReturnValue({
    state: { error: null, failedText: null, ...stateOverrides } as AppState,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    actions: actions as any,
  });
  return actions;
}

describe("ErrorToast", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when there is no error", () => {
    mockApp({ error: null });
    const { container } = render(<ErrorToast />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the error message without a retry button when nothing is retryable", () => {
    mockApp({ error: "conversation not found", failedText: null });
    render(<ErrorToast />);
    expect(screen.getByTestId("error-toast")).toHaveTextContent("conversation not found");
    expect(screen.queryByTestId("retry-message")).not.toBeInTheDocument();
  });

  it("shows a retry button once a failed send has stashed text", () => {
    mockApp({ error: "network error", failedText: "what is a hash map?" });
    render(<ErrorToast />);
    expect(screen.getByTestId("retry-message")).toBeInTheDocument();
  });

  it("invokes retryLast when the retry button is clicked", () => {
    const actions = mockApp({ error: "network error", failedText: "what is a hash map?" });
    render(<ErrorToast />);
    fireEvent.click(screen.getByTestId("retry-message"));
    expect(actions.retryLast).toHaveBeenCalledTimes(1);
  });

  it("dismisses the toast when the close button is clicked", () => {
    const actions = mockApp({ error: "network error", failedText: "hi" });
    render(<ErrorToast />);
    fireEvent.click(screen.getByLabelText("Dismiss"));
    expect(actions.dismissError).toHaveBeenCalledTimes(1);
  });
});
