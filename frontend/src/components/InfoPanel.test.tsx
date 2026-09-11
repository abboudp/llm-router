import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { InfoPanel } from "./InfoPanel";

vi.mock("../api/client", () => ({
  api: { getInfo: vi.fn() },
}));

describe("InfoPanel", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing before the request resolves", () => {
    vi.mocked(api.getInfo).mockReturnValue(new Promise(() => {}));
    const { container } = render(<InfoPanel />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders name, version, and a humanized uptime once loaded", async () => {
    vi.mocked(api.getInfo).mockResolvedValue({
      name: "llm-router",
      version: "0.1.0",
      models: ["default", "mock-large"],
      uptime_s: 125,
    });

    render(<InfoPanel />);

    expect(await screen.findByTestId("info-panel")).toBeInTheDocument();
    expect(screen.getByText("llm-router")).toBeInTheDocument();
    expect(screen.getByText("v0.1.0")).toBeInTheDocument();
    expect(screen.getByText("up 2m")).toBeInTheDocument();
  });

  it("exposes the available models as a title tooltip", async () => {
    vi.mocked(api.getInfo).mockResolvedValue({
      name: "llm-router",
      version: "0.1.0",
      models: ["default", "mock-large"],
      uptime_s: 0,
    });

    render(<InfoPanel />);

    const panel = await screen.findByTestId("info-panel");
    expect(panel).toHaveAttribute("title", "Available models: default, mock-large");
  });

  it("stays empty if the info request fails", async () => {
    vi.mocked(api.getInfo).mockRejectedValue(new Error("network error"));
    const { container } = render(<InfoPanel />);
    await waitFor(() => expect(api.getInfo).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
