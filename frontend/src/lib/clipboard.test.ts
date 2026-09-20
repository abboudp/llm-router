import { afterEach, describe, expect, it, vi } from "vitest";
import { copyToClipboard } from "./clipboard";

// jsdom doesn't implement document.execCommand at all, so it can't be
// spied on with vi.spyOn (there's nothing to wrap) — stub it directly.
function stubExecCommand(returnValue: boolean) {
  const mock = vi.fn().mockReturnValue(returnValue);
  document.execCommand = mock as unknown as typeof document.execCommand;
  return mock;
}

describe("copyToClipboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    // @ts-expect-error - undo the jsdom stub, restoring the "unimplemented" baseline
    delete document.execCommand;
  });

  it("uses the async Clipboard API when available", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    const ok = await copyToClipboard("hello");

    expect(ok).toBe(true);
    expect(writeText).toHaveBeenCalledWith("hello");
  });

  it("falls back to execCommand when the Clipboard API is unavailable", async () => {
    vi.stubGlobal("navigator", {});
    const execCommand = stubExecCommand(true);

    const ok = await copyToClipboard("fallback text");

    expect(ok).toBe(true);
    expect(execCommand).toHaveBeenCalledWith("copy");
  });

  it("falls back to execCommand when the Clipboard API throws (e.g. permission denied)", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const execCommand = stubExecCommand(true);

    const ok = await copyToClipboard("hello again");

    expect(ok).toBe(true);
    expect(execCommand).toHaveBeenCalled();
  });

  it("reports failure when neither the Clipboard API nor execCommand work", async () => {
    vi.stubGlobal("navigator", {});
    stubExecCommand(false);

    const ok = await copyToClipboard("nope");

    expect(ok).toBe(false);
  });

  it("cleans up the temporary textarea used for the fallback path", async () => {
    vi.stubGlobal("navigator", {});
    stubExecCommand(true);

    await copyToClipboard("cleanup check");

    expect(document.querySelectorAll("textarea")).toHaveLength(0);
  });
});
