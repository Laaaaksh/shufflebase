"use strict";

/**
 * Records a real, end-to-end walkthrough of `shufflebase serve` against a
 * live Postgres database: introspecting a real schema, reviewing/adjusting
 * suggested masking strategies, running a mask, and proving referential
 * integrity survived by querying the actual source and target databases.
 *
 * This does not fabricate anything shown on screen: the "before"/"after"
 * snapshot pages are literal `psql` output captured at record time, and the
 * shufflebase panels are the real running app. Run via `../../Makefile`'s
 * `demo` target, which boots Postgres and `shufflebase serve` first -- see
 * run.sh in this directory.
 */

const { chromium } = require("playwright");
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const CONTAINER = process.env.SHUFFLEBASE_DEMO_CONTAINER || "shufflebase-demo-pg";
const APP_URL = process.env.SHUFFLEBASE_DEMO_APP_URL || "http://127.0.0.1:8642";
const SOURCE_URL =
  process.env.SHUFFLEBASE_DEMO_SOURCE_URL ||
  "postgresql+psycopg://postgres:demo@127.0.0.1:5540/proddb";
const TARGET_URL =
  process.env.SHUFFLEBASE_DEMO_TARGET_URL ||
  "postgresql+psycopg://postgres:demo@127.0.0.1:5540/staging";
const OUT_DIR = path.resolve(__dirname, "../../docs/assets");
const VIDEO_DIR = fs.mkdtempSync(path.join(require("os").tmpdir(), "shufflebase-demo-"));

function psql(db, sql) {
  return execFileSync(
    "docker",
    ["exec", CONTAINER, "psql", "-U", "postgres", "-d", db, "-c", sql],
    { encoding: "utf8" }
  );
}

function snapshotHtml(title, blocks) {
  const body = blocks
    .map(
      ({ label, output }) =>
        `<div class="cmd">$ ${escapeHtml(label)}</div><pre>${escapeHtml(output)}</pre>`
    )
    .join("\n");
  return `<!doctype html><html><head><meta charset="utf-8" />
<style>
  body { background: #0d1117; color: #c9d1d9; font-family: ui-monospace, "SF Mono", Menlo, monospace;
         font-size: 20px; padding: 32px; margin: 0; }
  h1 { color: #58a6ff; font-size: 22px; margin: 0 0 24px; }
  .cmd { color: #7ee787; margin: 18px 0 6px; }
  pre { margin: 0; white-space: pre-wrap; }
</style></head>
<body><h1>${escapeHtml(title)}</h1>${body}</body></html>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function writeSnapshot(file, title, blocks) {
  const p = path.join(VIDEO_DIR, file);
  fs.writeFileSync(p, snapshotHtml(title, blocks));
  return "file://" + p;
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const beforeUrl = writeSnapshot("before.html", "Before: live source database (proddb)", [
    { label: `psql proddb -c "table customers;"`, output: psql("proddb", "table customers;") },
    {
      label: `psql proddb -c "select o.id, o.customer_id, c.email from orders o join customers c on o.customer_id = c.id;"`,
      output: psql(
        "proddb",
        "select o.id, o.customer_id, c.email from orders o join customers c on o.customer_id = c.id order by o.id;"
      ),
    },
  ]);

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2,
    recordVideo: { dir: VIDEO_DIR, size: { width: 1280, height: 800 } },
  });

  // A single page for the whole walkthrough: recordVideo captures one video
  // per page, so everything must happen in one page/tab to land in one file.
  const app = await context.newPage();
  await app.goto(beforeUrl);
  await app.waitForTimeout(8000);

  await app.goto(APP_URL);
  await app.waitForTimeout(800);

  await app.click("#source-url");
  await app.type("#source-url", SOURCE_URL, { delay: 45 });
  await app.waitForTimeout(600);
  await app.click("#connect-btn");
  await app.waitForSelector("#schema-panel:not([hidden])");
  await app.waitForTimeout(1500);

  const tableCard = (name) =>
    app.locator(".table-card").filter({ has: app.locator(`h4:text-is("${name}")`) });

  await tableCard("customers").scrollIntoViewIfNeeded();
  await app.waitForTimeout(3000);

  await tableCard("orders").scrollIntoViewIfNeeded();
  await app.waitForTimeout(2500);

  const itemsCard = tableCard("order_items");
  await itemsCard.scrollIntoViewIfNeeded();
  await app.waitForTimeout(1800);

  // The name-pattern suggestion heuristic flags product_name as a person's
  // name; correct it by hand the way a real reviewer would.
  const productNameSelect = app.locator(
    'select[data-table="order_items"][data-column="product_name"]'
  );
  await productNameSelect.scrollIntoViewIfNeeded();
  await app.waitForTimeout(800);
  await productNameSelect.selectOption("preserve");
  await app.waitForTimeout(1600);

  await app.locator("#run-panel").scrollIntoViewIfNeeded();
  await app.waitForTimeout(500);
  await app.click("#target-url");
  await app.type("#target-url", TARGET_URL, { delay: 45 });
  await app.click("#seed");
  await app.type("#seed", "42", { delay: 80 });
  await app.waitForTimeout(900);

  await app.click("#run-btn");
  await app.waitForSelector("#run-result:not([hidden])", { timeout: 15000 });
  await app.locator("#integrity-status").scrollIntoViewIfNeeded();
  await app.waitForTimeout(4500);

  const afterUrl = writeSnapshot("after.html", "After: masked target database (staging)", [
    { label: `psql staging -c "table customers;"`, output: psql("staging", "table customers;") },
    {
      label: `psql staging -c "select o.id, o.customer_id, c.email from orders o join customers c on o.customer_id = c.id;"`,
      output: psql(
        "staging",
        "select o.id, o.customer_id, c.email from orders o join customers c on o.customer_id = c.id order by o.id;"
      ),
    },
    {
      label: `psql staging -c "table order_items;"`,
      output: psql("staging", "select id, order_id, product_name, quantity from order_items order by id;"),
    },
  ]);

  await app.goto(afterUrl);
  await app.waitForTimeout(9000);

  await context.close();
  await browser.close();

  const videoPath = await app.video().path();
  const finalPath = path.join(OUT_DIR, "demo-raw.webm");
  fs.copyFileSync(videoPath, finalPath);
  console.log("Raw recording written to " + finalPath);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
