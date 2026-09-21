import { expect, test } from "@playwright/test";

async function newConversation(page, title: string) {
  // `composer-input` becoming enabled is not a reliable signal here: it
  // stays enabled from whatever conversation was already selected, so it
  // can be satisfied before the new row has even rendered. Wait for the
  // row count to actually grow instead — this matters once a test creates
  // more than one conversation in a row (as the search test below does).
  const before = await page.getByTestId("conversation-item").count();
  await page.getByTestId("new-conversation").click();
  await expect(page.getByTestId("conversation-item")).toHaveCount(before + 1);

  const item = page.getByTestId("conversation-item").first();
  await item.getByTestId("conversation-menu").click();
  page.once("dialog", (dialog) => dialog.accept(title));
  await item.getByTestId("rename-conversation").click();
  await expect(item).toContainText(title);
}

test("sidebar search filters the conversation list", async ({ page }) => {
  // The e2e run shares one backend/database across every spec file and
  // test in it (see scripts/run_e2e.sh), so earlier tests can and do leave
  // other conversations behind — assert on these two by a marker unique to
  // this test run rather than on the total row count.
  const marker = `e2e-search-${Date.now()}`;
  const kubernetesTitle = `Kubernetes migration plan ${marker}`;
  const recipeTitle = `Weekend recipe ideas ${marker}`;

  await page.goto("/");
  await newConversation(page, kubernetesTitle);
  await newConversation(page, recipeTitle);
  await expect(page.getByText(kubernetesTitle)).toBeVisible();
  await expect(page.getByText(recipeTitle)).toBeVisible();

  await page.getByTestId("conversation-search").fill(`kubernetes migration plan ${marker}`);
  await expect(page.getByTestId("conversation-item")).toHaveCount(1);
  await expect(page.getByTestId("conversation-item").first()).toContainText(kubernetesTitle);
  await expect(page.getByText(recipeTitle)).not.toBeVisible();

  await page.getByTestId("conversation-search").fill("");
  await expect(page.getByText(kubernetesTitle)).toBeVisible();
  await expect(page.getByText(recipeTitle)).toBeVisible();
});

test("export downloads a markdown file named after the conversation", async ({ page }) => {
  await page.goto("/");
  await newConversation(page, "Export target chat");
  await page.getByTestId("composer-input").fill("hello export");
  await page.getByTestId("composer-send").click();
  await expect(page.getByTestId("message-assistant").first()).toBeVisible();

  const item = page.getByTestId("conversation-item").first();
  await item.getByTestId("conversation-menu").click();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    item.getByTestId("export-conversation").click(),
  ]);
  expect(download.suggestedFilename()).toBe("export-target-chat.md");
});
