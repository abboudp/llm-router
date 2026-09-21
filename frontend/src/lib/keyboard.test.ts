import { describe, expect, it } from "vitest";
import { isEditableTarget } from "./keyboard";

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
