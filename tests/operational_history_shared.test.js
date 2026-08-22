"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const core = require(path.resolve(__dirname, "../app/static/operational_history_shared.js"));

const NOW = new Date("2026-08-22T12:00:00Z").getTime();
const item = (id, name, state, origin, finishedAt) => core.normalizeItem({
  id,
  operation_type: "update",
  name,
  woo_product_id: Number(id),
  state,
  state_label: state,
  origin,
  previous_version: "1.0",
  new_version: "2.0",
  started_at: "2026-08-01T10:00:00Z",
  finished_at: finishedAt,
  duration: 60,
  result: state,
  logs: [],
});
const items = [
  item("1", "Zulu", "completed", "UltraPack", "2026-08-22T10:00:00Z"),
  item("2", "Alpha", "rolled_back", "PluginTheme", "2026-08-20T10:00:00Z"),
  item("3", "Beta", "error", "dominio-a.test", "2026-08-15T10:00:00Z"),
  item("4", "Gama", "blocked", "dominio-b.test", "2026-07-01T10:00:00Z"),
];

assert.equal(core.bucketForState("completed"), "completed");
assert.equal(core.bucketForState("rolled_back"), "completed");
assert.equal(core.bucketForState("error"), "errors");
assert.equal(core.bucketForState("blocked"), "errors");

const filters = core.freshState();
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.id), ["1", "2"]);

filters.mode = "errors";
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.id), ["3", "4"]);

filters.mode = "completed";
filters.query = "alpha";
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.id), ["2"]);
filters.query = "1";
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.id), ["1"]);

filters.query = "";
filters.origin = "plugintheme";
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.id), ["2"]);

filters.origin = "";
filters.dateFrom = "2026-08-21";
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.id), ["1"]);
filters.dateFrom = "";
filters.dateTo = "2026-08-20";
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.id), ["2"]);

filters.dateTo = "";
filters.lastDays = "7";
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.id), ["1", "2"]);

filters.lastDays = "";
filters.sort = "recent";
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.id), ["1", "2"]);
filters.sort = "old";
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.id), ["2", "1"]);
filters.sort = "az";
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.name), ["Alpha", "Zulu"]);
filters.sort = "za";
assert.deepEqual(core.filterHistoryItems(items, filters, NOW).map(row => row.name), ["Zulu", "Alpha"]);

const pagination = core.paginateHistoryItems(items, 2, 2);
assert.equal(pagination.page, 2);
assert.equal(pagination.pageSize, 2);
assert.equal(pagination.pages, 2);
assert.deepEqual(pagination.items.map(row => row.id), ["3", "4"]);
assert.equal(core.paginateHistoryItems(items, 99, 5).page, 1);

const updateShell = core.renderOperationalHistory("update").replace('data-history-type="update"', 'data-history-type="TYPE"');
const additionShell = core.renderOperationalHistory("addition").replace('data-history-type="addition"', 'data-history-type="TYPE"');
assert.equal(updateShell, additionShell);
assert.equal((updateShell.match(/class="cs-history-tabs"/g) || []).length, 1);
assert.equal((updateShell.match(/data-history-list/g) || []).length, 1);
assert.match(core.renderHistoryRow(items[0]), /cs-history-row-main/);
assert.match(core.renderHistoryRow(items[0]), /cs-history-row-status/);
assert.match(core.renderHistoryRow(items[0]), /cs-history-row-date/);
assert.match(core.renderHistoryRow(items[0]), /cs-history-row-result/);
assert.match(core.renderHistoryRow(items[0]), /cs-history-details/);

const source = fs.readFileSync(path.resolve(__dirname, "../app/static/operational_history_shared.js"), "utf8");
assert.doesNotMatch(source, /MutationObserver|setInterval|requestAnimationFrame/);
assert.doesNotMatch(source, /compatibilityMarkup|op-history-compat/);

console.log("operational_history_shared.test.js: todos os testes passaram");
