import { expect, test } from "@playwright/test";

async function newConversation(page) {
  await page.getByTestId("new-conversation").click();
  await expect(page.getByTestId("composer-input")).toBeEnabled();
}

test("loads with empty state", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("empty-state")).toBeVisible();
});

test("conversation create, rename, delete", async ({ page }) => {
  await page.goto("/");
  await newConversation(page);
  const item = page.getByTestId("conversation-item").first();
  await expect(item).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept("Renamed chat"));
  await item.getByTestId("rename-conversation").click();
  await expect(page.getByTestId("conversation-item").first()).toContainText("Renamed chat");

  await item.getByTestId("delete-conversation").click();
  await expect(page.getByTestId("empty-state")).toBeVisible();
});

test("send message renders both turns with latency chip", async ({ page }) => {
  await page.goto("/");
  await newConversation(page);
  await page.getByTestId("composer-input").fill("Explain what a request queue is.");
  await page.getByTestId("composer-send").click();

  await expect(page.getByTestId("message-user")).toContainText("request queue");
  await expect(page.getByTestId("pending-bubble")).toBeVisible();
  const assistant = page.getByTestId("message-assistant").first();
  await expect(assistant).toBeVisible();
  await expect(assistant).not.toHaveText("");
  await expect(assistant.getByTestId("latency-chip")).toHaveText(/\d+(\.\d+)?\s(ms|s)/);
});

test("conversation persists across reload", async ({ page }) => {
  await page.goto("/");
  await newConversation(page);
  await page.getByTestId("composer-input").fill("Remember me");
  await page.getByTestId("composer-send").click();
  await expect(page.getByTestId("message-assistant").first()).toBeVisible();

  await page.reload();
  await page.getByTestId("conversation-item").first().click();
  await expect(page.getByTestId("message-user").first()).toContainText("Remember me");
  await expect(page.getByTestId("message-assistant").first()).toBeVisible();
});

test("max_tokens setting applies to the next response", async ({ page }) => {
  await page.goto("/");
  await newConversation(page);
  await page.getByTestId("settings-max-tokens").selectOption("16");
  await page.getByTestId("composer-input").fill("Describe your purpose.");
  await page.getByTestId("composer-send").click();
  const assistant = page.getByTestId("message-assistant").first();
  await expect(assistant).toBeVisible();
  const words = ((await assistant.textContent()) ?? "").trim().split(/\s+/);
  expect(words.length).toBeLessThanOrEqual(20); // 16 tokens + chip text margin
});

test("error surfaces as toast and composer unlocks", async ({ page }) => {
  await page.goto("/");
  await newConversation(page);
  // delete the conversation out from under the UI, then send
  const id = await page.evaluate(async () => {
    const rows = await (await fetch("/v1/conversations")).json();
    await fetch(`/v1/conversations/${rows[0].id}`, { method: "DELETE" });
    return rows[0].id as string;
  });
  expect(id).toBeTruthy();
  await page.getByTestId("composer-input").fill("hello?");
  await page.getByTestId("composer-send").click();
  await expect(page.getByTestId("error-toast")).toBeVisible();
  await expect(page.getByTestId("composer-input")).toBeEnabled();
});
