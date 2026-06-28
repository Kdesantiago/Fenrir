// @ts-check
// Frontend smoke suite (US-107 / spec dashboard-ux-evolve US-4) — the regression guard the
// zero-test app.js lacks. Covers the AC for feat-40: US-104 board search, US-105 Top-spenders,
// US-106 relative timestamps, plus app-loads + modal open/Escape-close.
//
// Runs against a DETERMINISTIC fixture board (tests/e2e/fixture-board.json), booted by
// playwright.config.js webServer. Fixture shape (built via backend.cli):
//   epic-1 "Authentication platform"
//     feat-1 "Login and sessions"
//       us-1 "Password reset flow"   cost $12.50  (top spender)
//       us-2 "OAuth single sign-on"  cost $3.25
//       us-3 "Logout button widget"  cost $0      (excluded from top-spenders)
// "oauth" is a substring unique to us-2 → a clean single-match search assertion.

const { test, expect } = require("@playwright/test");

// Fail loudly on any uncaught page error / failed request so a silent JS break can't pass.
function guardPageErrors(page) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(`console.error: ${m.text()}`);
  });
  return errors;
}

// The SPA boots on window 'load' and fetches the board async — wait until cards exist.
async function gotoKanban(page) {
  await page.locator("#tab-kanban").click();
  await expect(page.locator("#view-kanban")).toBeVisible();
  await expect(page.locator("#kanban-cols article.card").first()).toBeVisible();
}

test.describe("dashboard SPA smoke (feat-40)", () => {
  test("app loads: sidebar nav + Overview render, no uncaught page error", async ({ page }) => {
    const errors = guardPageErrors(page);
    await page.goto("/");

    // Sidebar / nav present.
    await expect(page.locator("aside.sidebar")).toBeVisible();
    await expect(page.locator(".nav-item")).toHaveCount(5);

    // Overview is the default active view and renders its KPI host.
    await expect(page.locator("#view-overview")).toBeVisible();
    await expect(page.locator("#tab-overview")).toHaveAttribute("aria-selected", "true");

    // Board data actually loaded (board fetch resolved → kanban cards exist once we switch).
    await gotoKanban(page);

    expect(errors, `page errors:\n${errors.join("\n")}`).toEqual([]);
  });

  test("US-104 search: substring filters cards to the single match, clear restores all", async ({ page }) => {
    await page.goto("/");
    await gotoKanban(page);

    // All three fixture stories visible before filtering.
    await expect(page.locator("#kanban-cols article.card")).toHaveCount(3);

    // "oauth" matches only us-2 ("OAuth single sign-on").
    const search = page.locator("#board-search");
    await search.fill("oauth");

    await expect(page.locator("#kanban-cols article.card")).toHaveCount(1);
    await expect(page.locator('#kanban-cols article.card[data-id="us-2"]')).toBeVisible();
    await expect(page.locator('#kanban-cols article.card[data-id="us-1"]')).toHaveCount(0);
    await expect(page.locator('#kanban-cols article.card[data-id="us-3"]')).toHaveCount(0);

    // Clearing restores every card.
    await search.fill("");
    await expect(page.locator("#kanban-cols article.card")).toHaveCount(3);
  });

  test("US-104 search: matches on id substring too (composes via visibleStories)", async ({ page }) => {
    await page.goto("/");
    await gotoKanban(page);

    await page.locator("#board-search").fill("us-1");
    // "us-1" is a substring of "us-1" only (ids us-2/us-3 don't contain it).
    await expect(page.locator('#kanban-cols article.card[data-id="us-1"]')).toBeVisible();
    await expect(page.locator("#kanban-cols article.card")).toHaveCount(1);
  });

  test("modal: clicking a kanban card opens detail; Escape closes it", async ({ page }) => {
    await page.goto("/");
    await gotoKanban(page);

    const backdrop = page.locator("#modal-backdrop");
    await expect(backdrop).toBeHidden();

    await page.locator('#kanban-cols article.card[data-id="us-1"]').click();
    await expect(backdrop).toBeVisible();
    await expect(page.locator("#modal-title")).toContainText("Password reset flow");

    await page.keyboard.press("Escape");
    await expect(backdrop).toBeHidden();
  });

  test("US-105 Top-spenders: Overview table sorted desc by cost; top row opens that US", async ({ page }) => {
    await page.goto("/");
    // Overview is default; wait for the top-spenders rows to render after board+costs load.
    const rows = page.locator("#tbl-top-spenders tbody tr");
    await expect(rows.first().locator("td").first()).toHaveText(/us-\d+/);

    // Only the two stories with cost > 0 appear (us-3 is $0, excluded), and descending.
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0).locator("td").nth(0)).toHaveText("us-1");
    await expect(rows.nth(1).locator("td").nth(0)).toHaveText("us-2");

    // Cost column is descending: us-1 ($12.50) above us-2 ($3.25).
    const top = await rows.nth(0).locator("td.cost").innerText();
    const next = await rows.nth(1).locator("td.cost").innerText();
    const num = (s) => parseFloat(s.replace(/[^0-9.]/g, ""));
    expect(num(top)).toBeGreaterThan(num(next));

    // Clicking the top row opens that US's detail modal.
    await rows.nth(0).click();
    await expect(page.locator("#modal-backdrop")).toBeVisible();
    await expect(page.locator("#modal-title")).toContainText("Password reset flow");
  });

  test("US-106 relative time: .when span shows relative text + non-empty title when a timestamp exists", async ({ page }) => {
    await page.goto("/");
    // The Cost-trace view renders one .when span per work_log entry (fixture has 2).
    await page.locator("#tab-trace").click();
    await expect(page.locator("#view-trace")).toBeVisible();

    const when = page.locator("#tbl-trace tbody .when").first();
    await expect(when).toBeVisible();

    // AC regex: relative text OR an absolute fallback OR the em-dash placeholder.
    const REL = /just now|\d+[mhd] ago|[A-Z][a-z]{2} \d|—/;
    await expect(when).toHaveText(REL);

    // A real timestamp carries the absolute datetime on the title attr (hover tooltip).
    const title = await when.getAttribute("title");
    expect(title, "title attr should hold the absolute datetime").toBeTruthy();
    expect(title.length).toBeGreaterThan(0);
  });
});
