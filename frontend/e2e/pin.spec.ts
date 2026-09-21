import { expect, test } from "@playwright/test";

async function newConversation(page, title: string) {
  // See search-export.spec.ts for why this waits on the row count rather
  // than on composer-input becoming enabled.
  const before = await page.getByTestId("conversation-item").count();
  await page.getByTestId("new-conversation").click();
  await expect(page.getByTestId("conversation-item")).toHaveCount(before + 1);

  const item = page.getByTestId("conversation-item").first();
  page.once("dialog", (dialog) => dialog.accept(title));
  await item.getByTestId("rename-conversation").click();
  await expect(item).toContainText(title);
}

test("pinning a conversation sorts it first, even after reload", async ({ page }) => {
  // Unique titles: the e2e run shares one backend/database across every
  // spec file and test in it (see scripts/run_e2e.sh).
  const marker = `e2e-pin-${Date.now()}`;
  const pinnedTitle = `Pin me ${marker}`;
  const newerTitle = `Newer unpinned ${marker}`;

  await page.goto("/");
  await newConversation(page, pinnedTitle);
  await newConversation(page, newerTitle);

  // Before pinning: plain recency order puts the just-created one on top.
  await expect(page.getByTestId("conversation-item").first()).toContainText(newerTitle);

  const pinnedRow = page.getByTestId("conversation-item").filter({ hasText: pinnedTitle });
  await pinnedRow.getByTestId("pin-conversation").click();
  await expect(pinnedRow).toHaveClass(/pinned/);

  // After pinning: it floats to the top despite being the older conversation.
  await expect(page.getByTestId("conversation-item").first()).toContainText(pinnedTitle);

  await page.reload();
  await expect(page.getByTestId("conversation-item").first()).toContainText(pinnedTitle);

  // Cleanup: a still-pinned conversation would keep floating to the top of
  // the shared backend's list (see scripts/run_e2e.sh) for every other spec
  // that runs after this one, breaking their "the newest conversation is
  // first" assumptions. Delete both conversations this test created.
  await page
    .getByTestId("conversation-item")
    .filter({ hasText: pinnedTitle })
    .getByTestId("delete-conversation")
    .click();
  await page
    .getByTestId("conversation-item")
    .filter({ hasText: newerTitle })
    .getByTestId("delete-conversation")
    .click();
  await expect(page.getByText(pinnedTitle)).not.toBeVisible();
  await expect(page.getByText(newerTitle)).not.toBeVisible();
});
