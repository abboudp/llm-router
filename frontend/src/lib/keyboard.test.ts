import { describe, expect, it } from "vitest";
import { isEditableTarget, isNewConversationHotkey } from "./keyboard";

describe("isNewConversationHotkey", () => {
  it("matches Cmd+K on macOS", () => {
    expect(isNewConversationHotkey({ metaKey: true, ctrlKey: false, key: "k" })).toBe(true);
  });

  it("matches Ctrl+K elsewhere", () => {
    expect(isNewConversationHotkey({ metaKey: false, ctrlKey: true, key: "K" })).toBe(true);
  });

  it("does not match K alone", () => {
    expect(isNewConversationHotkey({ metaKey: false, ctrlKey: false, key: "k" })).toBe(false);
  });

  it("does not match Cmd/Ctrl with a different key", () => {
    expect(isNewConversationHotkey({ metaKey: true, ctrlKey: false, key: "j" })).toBe(false);
  });
});

describe("isEditableTarget", () => {
  it("treats inputs, textareas, and selects as editable", () => {
    expect(isEditableTarget(document.createElement("input"))).toBe(true);
    expect(isEditableTarget(document.createElement("textarea"))).toBe(true);
    expect(isEditableTarget(document.createElement("select"))).toBe(true);
  });

  it("treats a contenteditable element as editable", () => {
    const div = document.createElement("div");
    div.setAttribute("contenteditable", "true");
    expect(isEditableTarget(div)).toBe(true);

    const shorthand = document.createElement("div");
    shorthand.setAttribute("contenteditable", "");
    expect(isEditableTarget(shorthand)).toBe(true);
  });

  it("treats a plain element as not editable", () => {
    expect(isEditableTarget(document.createElement("div"))).toBe(false);
    expect(isEditableTarget(document.createElement("button"))).toBe(false);
  });

  it("treats null or a non-element target as not editable", () => {
    expect(isEditableTarget(null)).toBe(false);
  });
});
