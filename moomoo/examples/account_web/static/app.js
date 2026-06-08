const $ = (id) => document.getElementById(id);

let activeLoadId = 0;
let activeWatchlistsLoadId = 0;
let activePage = "overview";
let privacyMode = true;
let activeSignalFilter = "all";
let currentDashboard = null;
let currentPositions = [];
let currentWatchlistsPayload = null;
let currentWatchlists = [];
let activeDetailCode = null;
let activeWatchlistDataLoadId = 0;
let watchlistsLoaded = false;
let currentWatchlistsParamsKey = null;
let watchlistsSyncing = false;
let watchlistSearchQuery = "";
let watchlistExpansionMode = "all-expanded";
let expandedWatchlists = new Set();
let collapsedWatchlists = new Set();
let activeDetailMode = "position";

const numericColumns = new Set([
  "qty",
  "can_sell_qty",
  "cost_price",
  "nominal_price",
  "market_val",
  "pl_val",
  "pl_ratio",
  "total_assets",
  "cash",
  "power",
  "hk_cash",
  "hkd_assets",
  "us_cash",
  "usd_assets",
  "au_cash",
  "aud_assets",
  "md_price",
  "md_rsi14",
]);

const sensitiveColumns = new Set([
  "qty",
  "can_sell_qty",
  "cost_price",
  "nominal_price",
  "market_val",
  "pl_val",
  "pl_ratio",
  "total_assets",
  "cash",
  "power",
  "hk_cash",
  "hkd_assets",
  "us_cash",
  "usd_assets",
  "au_cash",
  "aud_assets",
]);

const positionColumns = [
  "signal",
  "code",
  "stock_name",
  "qty",
  "can_sell_qty",
  "cost_price",
  "nominal_price",
  "market_val",
  "pl_val",
  "pl_ratio",
  "position_side",
  "md_ticker",
  "md_price",
  "md_trend",
  "md_rsi14",
  "md_as_of",
  "md_quality",
];

const watchlistColumns = [
  "holding_status",
  "code",
  "name",
  "md_ticker",
  "md_price",
  "md_trend",
  "md_rsi14",
  "md_quality",
  "md_as_of",
  "market_data_url",
];

const columnLabels = {
  holding_status: "status",
  md_ticker: "ticker",
  md_price: "price",
  md_trend: "trend",
  md_rsi14: "rsi",
  md_quality: "quality",
  md_as_of: "as_of",
  market_data_url: "lab",
};

const WATCHLIST_SNAPSHOT_BATCH_SIZE = 80;
const DEFAULT_EXPANDED_WATCHLISTS = 3;

function text(value) {
  if (value === null || value === undefined || value === "") return "N/A";
  return String(value);
}

function lowerText(value) {
  return text(value).toLowerCase();
}

function numberLike(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function privateValue(key) {
  return privacyMode && sensitiveColumns.has(key);
}

function formatValue(value, key = "") {
  if (privateValue(key)) return "Hidden";
  if (!numberLike(value)) return text(value);
  if (key === "pl_ratio") return `${value.toFixed(2)}%`;
  if (key === "md_rsi14") return value.toFixed(1);
  if (Number.isInteger(value)) return value.toLocaleString();
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatPercent(value) {
  if (!numberLike(value)) return "N/A";
  return `${(value * 100).toFixed(1)}%`;
}

function formatReturn(value) {
  if (!numberLike(value)) return "N/A";
  return formatPercent(value);
}

function valueTone(value, key = "") {
  if (!numberLike(value)) return "";
  if (!["pl_val", "pl_ratio"].includes(key)) return "";
  if (value > 0) return " positive";
  if (value < 0) return " negative";
  return "";
}

function setMessage(label, tone = "muted") {
  $("message").className = `status-badge ${tone}`;
  $("message").textContent = label;
}

function setMarketDataStatus(label, tone = "muted") {
  $("market-data-status").className = `market-status ${tone}`;
  $("market-data-status").textContent = label;
}

function setWatchlistStatus(label, tone = "muted") {
  $("watchlist-status").className = `market-status ${tone}`;
  $("watchlist-status").textContent = label;
}

function setWatchlistsSyncing(syncing) {
  watchlistsSyncing = syncing;
  const button = $("watchlists-sync");
  button.disabled = syncing;
  button.textContent = syncing ? "Syncing..." : "Sync from OpenD";
}

function pageFromHash() {
  const page = window.location.hash.replace("#", "").trim();
  return ["overview", "watchlists"].includes(page) ? page : "overview";
}

function setActivePage(page) {
  activePage = ["overview", "watchlists"].includes(page) ? page : "overview";

  document.querySelectorAll("[data-page]").forEach((panel) => {
    panel.hidden = panel.dataset.page !== activePage;
  });

  document.querySelectorAll("[data-page-target]").forEach((item) => {
    item.classList.toggle("active", item.dataset.pageTarget === activePage);
  });

  if (activePage === "watchlists") loadWatchlistsPage();
}

function updatePrivacyButtons() {
  const label = privacyMode ? "Reveal" : "Hide";
  $("privacy-toggle").textContent = label;
  $("detail-privacy").textContent = label;
}

function togglePrivacyMode() {
  privacyMode = !privacyMode;
  updatePrivacyButtons();
  if (currentDashboard) renderDashboardData(currentDashboard);
  renderSignalsAndPositions();
  renderWatchlists(currentWatchlists);
}

function metric(name, value, key = "") {
  const item = document.createElement("div");
  item.className = "metric";

  const label = document.createElement("div");
  label.className = "name";
  label.textContent = name;

  const display = document.createElement("div");
  display.className = `value${valueTone(value, key)}`;
  display.textContent = formatValue(value, key);

  item.append(label, display);
  return item;
}

function renderMetrics(id, items) {
  const target = $(id);
  target.replaceChildren(...items.map(([name, value, key]) => metric(name, value, key)));
}

function cellClass(column, value) {
  const classes = [];
  if (["code", "md_ticker"].includes(column)) classes.push("ticker");
  if (numericColumns.has(column)) classes.push("numeric");
  if (column === "signal") classes.push("signal-cell");
  if (["pl_val", "pl_ratio"].includes(column)) {
    if (numberLike(value) && value > 0) classes.push("positive");
    if (numberLike(value) && value < 0) classes.push("negative");
  }
  if (column === "md_quality") {
    if (value === "ok") classes.push("positive");
    if (value === "partial") classes.push("warning");
    if (value === "unavailable") classes.push("negative");
  }
  return classes.join(" ");
}

function renderTable(id, rows, columns) {
  const table = $(id);
  table.replaceChildren();

  if (!rows || rows.length === 0) {
    const body = document.createElement("tbody");
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.className = "muted";
    cell.textContent = "No rows";
    table.appendChild(body);
    return;
  }

  const head = document.createElement("thead");
  const headerRow = head.insertRow();
  columns.forEach((column) => {
    const header = document.createElement("th");
    header.textContent = columnLabels[column] || column;
    if (numericColumns.has(column)) header.className = "numeric";
    headerRow.appendChild(header);
  });

  const body = document.createElement("tbody");
  rows.forEach((source) => {
    const row = body.insertRow();
    columns.forEach((column) => {
      const value = source[column];
      const cell = row.insertCell();
      cell.className = cellClass(column, value);
      cell.textContent = formatValue(value, column);
    });
  });

  table.append(head, body);
}

function renderMarketDataLinkCell(cell, url) {
  if (!url) {
    cell.className = "muted";
    cell.textContent = "N/A";
    return;
  }

  const link = document.createElement("a");
  link.className = "watchlist-link";
  link.href = url;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = "Open";
  link.title = "Open Market Data Lab";
  cell.appendChild(link);
}

function renderHoldingStatusCell(cell, security) {
  const status = holdingStatusForSecurity(security);
  cell.appendChild(chip(status, status === "Held" ? "positive" : "muted"));
}

function renderWatchlistTable(rows) {
  const wrapper = document.createElement("div");
  wrapper.className = "table-scroll";
  const table = document.createElement("table");
  table.className = "watchlist-table";

  if (!rows || rows.length === 0) {
    const body = document.createElement("tbody");
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.className = "muted";
    cell.textContent = "No securities";
    table.appendChild(body);
    wrapper.appendChild(table);
    return wrapper;
  }

  const head = document.createElement("thead");
  const headerRow = head.insertRow();
  watchlistColumns.forEach((column) => {
    const header = document.createElement("th");
    header.textContent = columnLabels[column] || column;
    if (numericColumns.has(column)) header.className = "numeric";
    headerRow.appendChild(header);
  });

  const body = document.createElement("tbody");
  rows.forEach((source) => {
    const row = body.insertRow();
    bindOpenWatchlistDetail(row, source);
    watchlistColumns.forEach((column) => {
      const value = source[column];
      const cell = row.insertCell();
      cell.className = cellClass(column, value);
      if (column === "holding_status") {
        renderHoldingStatusCell(cell, source);
      } else if (column === "market_data_url") {
        renderMarketDataLinkCell(cell, value);
      } else {
        if (column === "name") cell.title = text(value);
        cell.textContent = formatValue(value, column);
      }
    });
  });

  table.append(head, body);
  wrapper.appendChild(table);
  return wrapper;
}

function bindOpenDetail(node, position) {
  const code = position && position.code;
  if (!code) return;

  node.classList.add("actionable");
  node.tabIndex = 0;
  node.setAttribute("role", "button");
  node.setAttribute("aria-label", `Open ${code} position detail`);
  node.addEventListener("click", () => openPositionDetail(code));
  node.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openPositionDetail(code);
    }
  });
}

function bindOpenWatchlistDetail(node, security) {
  const code = security && security.code;
  if (!code) return;

  node.classList.add("actionable");
  node.tabIndex = 0;
  node.setAttribute("role", "button");
  node.setAttribute("aria-label", `Open ${code} watchlist detail`);
  node.addEventListener("click", (event) => {
    if (event.target.closest("a")) return;
    openWatchlistDetail(code);
  });
  node.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openWatchlistDetail(code);
    }
  });
}

function renderPositionsTable(rows) {
  const table = $("positions-table");
  table.replaceChildren();

  if (!rows || rows.length === 0) {
    const body = document.createElement("tbody");
    const row = body.insertRow();
    const cell = row.insertCell();
    cell.className = "muted";
    cell.textContent = "No rows";
    table.appendChild(body);
    return;
  }

  const head = document.createElement("thead");
  const headerRow = head.insertRow();
  positionColumns.forEach((column) => {
    const header = document.createElement("th");
    header.textContent = column;
    if (numericColumns.has(column)) header.className = "numeric";
    headerRow.appendChild(header);
  });

  const body = document.createElement("tbody");
  rows.forEach((source) => {
    const row = body.insertRow();
    bindOpenDetail(row, source);
    positionColumns.forEach((column) => {
      const value = source[column];
      const cell = row.insertCell();
      cell.className = cellClass(column, value);
      cell.textContent = formatValue(value, column);
    });
  });

  table.append(head, body);
}

function uniqueCodes(positions) {
  const seen = new Set();
  const codes = [];
  positions.forEach((position) => {
    const code = position.code;
    if (code && !seen.has(code)) {
      seen.add(code);
      codes.push(code);
    }
  });
  return codes;
}

function holdingForCode(code) {
  if (!code) return null;
  return currentPositions.find((position) => position.code === code) || null;
}

function holdingStatusForSecurity(security) {
  return holdingForCode(security && security.code) ? "Held" : "Watch";
}

function watchlistKey(group, index) {
  return `${index}:${group.group_name || "watchlist"}`;
}

function watchlistNamesForCode(code) {
  if (!code) return [];
  const names = [];
  currentWatchlists.forEach((group) => {
    if (group.error) return;
    const hasCode = (group.securities || []).some((security) => security.code === code);
    if (hasCode) names.push(group.group_name || "Watchlist");
  });
  return names;
}

function allWatchlistMatchesForCode(code) {
  if (!code) return [];
  return currentWatchlists.flatMap((group) =>
    (group.securities || [])
      .filter((security) => security.code === code)
      .map((security) => ({ ...security, group_name: group.group_name || "Watchlist" })),
  );
}

function watchlistDetailForCode(code) {
  const matches = allWatchlistMatchesForCode(code);
  if (matches.length === 0) return null;
  const security = matches[0];
  const holding = holdingForCode(code);
  return {
    ...security,
    holding,
    holding_status: holding ? "Held" : "Watch",
    watchlist_names: [...new Set(matches.map((item) => item.group_name))],
  };
}

function watchlistCardStats(group) {
  const securities = group.error ? [] : group.securities || [];
  const held = securities.filter((security) => holdingForCode(security.code)).length;
  const mapped = securities.filter((security) => security.md_ticker).length;
  const dataGap = securities.filter((security) => !security.md_ticker || security.md_quality === "unavailable").length;
  return {
    securities: securities.length,
    held,
    mapped,
    dataGap,
  };
}

function watchlistGroupMatches(group, query) {
  if (!query) return true;
  const groupNameMatches = lowerText(group.group_name).includes(query);
  if (groupNameMatches) return true;
  return (group.securities || []).some((security) => watchlistSecurityMatches(security, query));
}

function watchlistSecurityMatches(security, query) {
  if (!query) return true;
  return [security.code, security.name, security.md_ticker, holdingStatusForSecurity(security)]
    .some((value) => lowerText(value).includes(query));
}

function visibleWatchlistGroups(groups) {
  const query = watchlistSearchQuery.trim().toLowerCase();
  return (groups || [])
    .map((group, index) => {
      if (!query) return { ...group, _watchlist_index: index };
      if (!watchlistGroupMatches(group, query)) return null;
      const groupNameMatches = lowerText(group.group_name).includes(query);
      return {
        ...group,
        _watchlist_index: index,
        securities: groupNameMatches
          ? group.securities || []
          : (group.securities || []).filter((security) => watchlistSecurityMatches(security, query)),
      };
    })
    .filter(Boolean);
}

function isWatchlistCollapsed(group, index) {
  if (watchlistSearchQuery.trim()) return false;
  const key = watchlistKey(group, index);
  if (expandedWatchlists.has(key)) return false;
  if (collapsedWatchlists.has(key)) return true;
  if (watchlistExpansionMode === "all-expanded") return false;
  if (watchlistExpansionMode === "all-collapsed") return true;
  return index >= DEFAULT_EXPANDED_WATCHLISTS;
}

function toggleWatchlistCollapsed(group, index) {
  const key = watchlistKey(group, index);
  if (isWatchlistCollapsed(group, index)) {
    expandedWatchlists.add(key);
    collapsedWatchlists.delete(key);
  } else {
    collapsedWatchlists.add(key);
    expandedWatchlists.delete(key);
  }
  renderWatchlists(currentWatchlists);
}

function setWatchlistExpansionMode(mode) {
  watchlistExpansionMode = mode;
  expandedWatchlists = new Set();
  collapsedWatchlists = new Set();
  renderWatchlists(currentWatchlists);
}

function snapshotQuality(snapshot) {
  if (!snapshot) return "unavailable";
  if (snapshot.data_quality && snapshot.data_quality.status) return snapshot.data_quality.status;
  return snapshot.mapping_status || "unavailable";
}

function relativeStrength(snapshot) {
  if (!snapshot || !snapshot.relative_strength_vs_spy) return "unavailable";
  return snapshot.relative_strength_vs_spy.status || "unavailable";
}

function volumeStatus(snapshot) {
  if (!snapshot || !snapshot.volume_signal) return "unavailable";
  return snapshot.volume_signal.status || "unavailable";
}

function volumeRatio(snapshot) {
  if (!snapshot || !snapshot.volume_signal) return null;
  return snapshot.volume_signal.ratio;
}

function withMarketData(position, snapshot) {
  const enriched = {
    ...position,
    md_ticker: snapshot ? snapshot.ticker : null,
    md_price: snapshot ? snapshot.price : null,
    md_trend: snapshot ? snapshot.trend : "unavailable",
    md_rsi14: snapshot ? snapshot.rsi14 : null,
    md_as_of: snapshot ? snapshot.as_of : null,
    md_quality: snapshotQuality(snapshot),
    md_breakout_status: snapshot ? snapshot.breakout_status : "unavailable",
    md_relative_strength: relativeStrength(snapshot),
    md_volume_status: volumeStatus(snapshot),
    md_volume_ratio: volumeRatio(snapshot),
    md_trend_score: snapshot ? snapshot.trend_score : null,
    md_liquidity_score: snapshot ? snapshot.liquidity_score : null,
    md_return_1m: snapshot ? snapshot.return_1m : null,
    md_return_3m: snapshot ? snapshot.return_3m : null,
    market_data_url: snapshot ? snapshot.market_data_url : null,
  };
  const signal = classifySignal(enriched);
  return { ...enriched, ...signal };
}

function withWatchlistMarketData(security, snapshot) {
  return {
    ...security,
    md_ticker: snapshot ? snapshot.ticker : null,
    md_price: snapshot ? snapshot.price : null,
    md_trend: snapshot ? snapshot.trend : "unavailable",
    md_rsi14: snapshot ? snapshot.rsi14 : null,
    md_as_of: snapshot ? snapshot.as_of : null,
    md_quality: snapshotQuality(snapshot),
    md_breakout_status: snapshot ? snapshot.breakout_status : "unavailable",
    md_relative_strength: relativeStrength(snapshot),
    md_volume_status: volumeStatus(snapshot),
    md_volume_ratio: volumeRatio(snapshot),
    md_return_1m: snapshot ? snapshot.return_1m : null,
    md_return_3m: snapshot ? snapshot.return_3m : null,
    market_data_url: snapshot ? snapshot.market_data_url : null,
  };
}

function unavailablePositions(positions) {
  return positions.map((position) =>
    withMarketData(position, {
      ticker: null,
      price: null,
      trend: "unavailable",
      rsi14: null,
      as_of: null,
      breakout_status: "unavailable",
      relative_strength_vs_spy: { status: "unavailable" },
      volume_signal: { status: "unavailable" },
      data_quality: { status: "unavailable" },
      market_data_url: null,
    }),
  );
}

function unavailableWatchlistSecurities(securities) {
  return securities.map((security) =>
    withWatchlistMarketData(security, {
      ticker: null,
      price: null,
      trend: "unavailable",
      rsi14: null,
      as_of: null,
      breakout_status: "unavailable",
      relative_strength_vs_spy: { status: "unavailable" },
      volume_signal: { status: "unavailable" },
      data_quality: { status: "unavailable" },
      market_data_url: null,
    }),
  );
}

function classifySignal(position) {
  const reasons = [];
  const trend = position.md_trend || "unavailable";
  const quality = position.md_quality || "unavailable";
  const breakout = position.md_breakout_status || "unavailable";
  const rs = position.md_relative_strength || "unavailable";
  const volumeRatioValue = position.md_volume_ratio;
  const rsi = position.md_rsi14;
  const plVal = position.pl_val;
  const plRatio = position.pl_ratio;

  if (quality === "unavailable" || trend === "unavailable") {
    reasons.push("market data unavailable");
    return signalPayload("Data Gap", 95, reasons);
  }

  if (quality === "partial") reasons.push("partial history");
  if (trend === "bearish") reasons.push("bearish trend");
  if (numberLike(rsi) && rsi < 40) reasons.push(`RSI ${rsi.toFixed(1)}`);
  if (rs === "underperforming") reasons.push("underperforming SPY");
  if (numberLike(plVal) && plVal < 0) reasons.push("position P/L negative");
  if (trend === "bearish" || rs === "underperforming" || (numberLike(rsi) && rsi < 35)) {
    return signalPayload("Risk Review", 86, reasons);
  }

  if (numberLike(plVal) && plVal > 0 && numberLike(plRatio) && plRatio > 8) {
    reasons.push("gains to protect");
    if (numberLike(rsi) && rsi > 65) reasons.push(`RSI ${rsi.toFixed(1)}`);
    return signalPayload("Protect Gains", 78, reasons);
  }

  if (breakout === "breakout" || breakout === "near_breakout") {
    reasons.push(breakout.replace("_", " "));
    if (numberLike(volumeRatioValue) && volumeRatioValue >= 1) reasons.push(`volume ${volumeRatioValue.toFixed(2)}x`);
    return signalPayload("Breakout Watch", 72, reasons);
  }

  if (["bullish", "constructive"].includes(trend)) {
    reasons.push(`${trend} trend`);
    if (rs === "outperforming") reasons.push("outperforming SPY");
    if (numberLike(position.md_trend_score)) reasons.push(`trend score ${position.md_trend_score.toFixed(0)}`);
    return signalPayload("Momentum", 66, reasons);
  }

  reasons.push(`${trend} trend`);
  if (breakout !== "unavailable") reasons.push(breakout.replace("_", " "));
  return signalPayload("Neutral", 30, reasons);
}

function signalPayload(signal, priority, reasons) {
  return {
    signal,
    signal_priority: priority,
    signal_reasons: reasons.filter(Boolean).slice(0, 3),
  };
}

function sortedPositions(positions) {
  return [...positions].sort((left, right) => {
    const priorityDiff = (right.signal_priority || 0) - (left.signal_priority || 0);
    if (priorityDiff !== 0) return priorityDiff;
    return Math.abs(right.pl_val || 0) - Math.abs(left.pl_val || 0);
  });
}

function filteredPositions() {
  const sorted = sortedPositions(currentPositions);
  if (activeSignalFilter === "all") return sorted;
  if (activeSignalFilter === "Risk Review") {
    return sorted.filter((item) => ["Risk Review", "Protect Gains"].includes(item.signal));
  }
  return sorted.filter((item) => item.signal === activeSignalFilter);
}

function renderMarketDataStatus(payload) {
  if (!payload.available) {
    setMarketDataStatus(payload.error || "Market Data Lab unavailable", "error");
    return;
  }
  setMarketDataStatus(
    `${payload.mapped_count}/${payload.requested_count} mapped via ${payload.api_url}`,
    "positive",
  );
}

function signalTone(signal) {
  if (signal === "Momentum" || signal === "Breakout Watch") return "positive";
  if (signal === "Risk Review" || signal === "Data Gap") return "negative";
  if (signal === "Protect Gains") return "warning";
  return "muted";
}

function chip(label, tone = "muted") {
  const node = document.createElement("span");
  node.className = `signal-chip ${tone}`;
  node.textContent = label;
  return node;
}

function selectedPosition() {
  if (!activeDetailCode) return null;
  return currentPositions.find((position) => position.code === activeDetailCode) || null;
}

function detailItem(label, value, key = "", formatter = null) {
  const item = document.createElement("div");
  item.className = "detail-item";

  const name = document.createElement("div");
  name.className = "detail-label";
  name.textContent = label;

  const display = document.createElement("div");
  display.className = `detail-value${valueTone(value, key)}`;
  display.textContent = formatter ? formatter(value) : formatValue(value, key);

  item.append(name, display);
  return item;
}

function detailSection(title, children) {
  const section = document.createElement("section");
  section.className = "detail-section";

  const heading = document.createElement("h3");
  heading.textContent = title;

  const body = document.createElement("div");
  body.className = "detail-grid";
  body.append(...children);

  section.append(heading, body);
  return section;
}

function detailChipList(items) {
  const list = document.createElement("div");
  list.className = "detail-chips";
  items.filter(Boolean).forEach((item) => {
    if (item instanceof Node) {
      list.appendChild(item);
    } else {
      list.appendChild(chip(item));
    }
  });
  return list;
}

function marketDataLink(position) {
  if (!position.market_data_url) {
    const unavailable = document.createElement("span");
    unavailable.className = "detail-link-disabled";
    unavailable.textContent = "Market Data Lab link unavailable";
    return unavailable;
  }

  const link = document.createElement("a");
  link.className = "detail-link";
  link.href = position.market_data_url;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = "Open Market Data Lab";
  return link;
}

function renderPositionDetail(position) {
  const content = $("detail-content");
  $("detail-kicker").textContent = "Position research";
  if (!position) {
    $("detail-title").textContent = "Holding Detail";
    content.replaceChildren();
    return;
  }

  $("detail-title").textContent = position.code || "Holding Detail";

  const summary = detailSection("Holding Summary", [
    detailItem("Name", position.stock_name || position.md_ticker),
    detailItem("Quantity", position.qty, "qty"),
    detailItem("Market Value", position.market_val, "market_val"),
    detailItem("P/L", position.pl_val, "pl_val"),
    detailItem("P/L Ratio", position.pl_ratio, "pl_ratio"),
    detailItem("Side", position.position_side),
  ]);

  const signal = detailSection("Signal Review", [
    detailChipList([chip(position.signal || "Neutral", signalTone(position.signal)), ...(position.signal_reasons || [])]),
    detailItem("Priority", position.signal_priority),
  ]);

  const market = detailSection("Market Data Lab Snapshot", [
    detailItem("Ticker", position.md_ticker),
    detailItem("Price", position.md_price, "md_price"),
    detailItem("Trend", position.md_trend),
    detailItem("RSI 14", position.md_rsi14, "md_rsi14"),
    detailItem("Breakout", position.md_breakout_status),
    detailItem("Relative Strength", position.md_relative_strength),
    detailItem("Volume Signal", position.md_volume_status),
    detailItem("Volume Ratio", position.md_volume_ratio),
    detailItem("1M Return", position.md_return_1m, "", formatReturn),
    detailItem("3M Return", position.md_return_3m, "", formatReturn),
    detailItem("As Of", position.md_as_of),
  ]);

  const quality = detailSection("Data Quality", [
    detailItem("Quality", position.md_quality),
    detailItem("Mapped Ticker", position.md_ticker),
    detailItem("Snapshot Date", position.md_as_of),
    marketDataLink(position),
  ]);

  content.replaceChildren(summary, signal, market, quality);
}

function renderWatchlistDetail(security) {
  const content = $("detail-content");
  $("detail-kicker").textContent = "Watchlist research";
  if (!security) {
    $("detail-title").textContent = "Watchlist Detail";
    content.replaceChildren();
    return;
  }

  const holding = security.holding;
  $("detail-title").textContent = security.code || "Watchlist Detail";

  const summary = detailSection("Watchlist Summary", [
    detailItem("Name", security.name || security.md_ticker),
    detailItem("Code", security.code),
    detailItem("Lists", (security.watchlist_names || []).join(", ")),
    detailItem("Status", security.holding_status),
    detailItem("Type", security.stock_type),
    detailItem("Mapped Ticker", security.md_ticker),
  ]);

  const holdingItems = holding
    ? [
        detailItem("Holding", "Held"),
        detailItem("Quantity", holding.qty, "qty"),
        detailItem("Market Value", holding.market_val, "market_val"),
        detailItem("P/L", holding.pl_val, "pl_val"),
        detailItem("P/L Ratio", holding.pl_ratio, "pl_ratio"),
        detailItem("Side", holding.position_side),
      ]
    : [
        detailItem("Holding", "Not held"),
        detailItem("Quantity", null, "qty"),
        detailItem("Market Value", null, "market_val"),
        detailItem("P/L", null, "pl_val"),
        detailItem("P/L Ratio", null, "pl_ratio"),
        detailItem("Side", null),
      ];

  const market = detailSection("Market Data Lab Snapshot", [
    detailItem("Ticker", security.md_ticker),
    detailItem("Price", security.md_price, "md_price"),
    detailItem("Trend", security.md_trend),
    detailItem("RSI 14", security.md_rsi14, "md_rsi14"),
    detailItem("Breakout", security.md_breakout_status),
    detailItem("Relative Strength", security.md_relative_strength),
    detailItem("Volume Signal", security.md_volume_status),
    detailItem("Volume Ratio", security.md_volume_ratio),
    detailItem("1M Return", security.md_return_1m, "", formatReturn),
    detailItem("3M Return", security.md_return_3m, "", formatReturn),
    detailItem("As Of", security.md_as_of),
  ]);

  const quality = detailSection("Data Quality", [
    detailItem("Quality", security.md_quality),
    detailItem("Mapped Ticker", security.md_ticker),
    detailItem("Snapshot Date", security.md_as_of),
    marketDataLink(security),
  ]);

  content.replaceChildren(summary, detailSection("Holding Match", holdingItems), market, quality);
}

function refreshActiveDetail() {
  if (!activeDetailCode) return;
  if (activeDetailMode === "watchlist") {
    renderWatchlistDetail(watchlistDetailForCode(activeDetailCode));
    return;
  }
  const position = selectedPosition();
  if (position) {
    renderPositionDetail(position);
  } else {
    closePositionDetail();
  }
}

function setDetailVisible(visible) {
  $("detail-backdrop").hidden = !visible;
  $("position-detail").hidden = !visible;
  $("position-detail").setAttribute("aria-hidden", visible ? "false" : "true");
  document.body.classList.toggle("detail-open", visible);
}

function openPositionDetail(code) {
  activeDetailMode = "position";
  activeDetailCode = code;
  renderPositionDetail(selectedPosition());
  setDetailVisible(true);
}

function openWatchlistDetail(code) {
  activeDetailMode = "watchlist";
  activeDetailCode = code;
  renderWatchlistDetail(watchlistDetailForCode(code));
  setDetailVisible(true);
}

function closePositionDetail() {
  activeDetailCode = null;
  activeDetailMode = "position";
  setDetailVisible(false);
  renderPositionDetail(null);
}

function renderFocusList() {
  const target = $("focus-list");
  const positions = filteredPositions().slice(0, 8);
  if (positions.length === 0) {
    const empty = document.createElement("div");
    empty.className = "focus-empty";
    empty.textContent = "No matching positions";
    target.replaceChildren(empty);
    return;
  }

  const cards = positions.map((position) => {
    const card = document.createElement("article");
    card.className = "focus-card";
    bindOpenDetail(card, position);

    const top = document.createElement("div");
    top.className = "focus-card-top";

    const title = document.createElement("div");
    title.className = "focus-title";
    title.textContent = position.code || "N/A";

    const label = chip(position.signal || "Neutral", signalTone(position.signal));
    top.append(title, label);

    const name = document.createElement("div");
    name.className = "focus-name";
    name.textContent = position.stock_name || position.md_ticker || "N/A";

    const reasonList = document.createElement("div");
    reasonList.className = "focus-reasons";
    (position.signal_reasons || ["review"]).forEach((reason) => {
      reasonList.appendChild(chip(reason));
    });

    const meta = document.createElement("div");
    meta.className = "focus-meta";
    meta.append(
      chip(`Trend ${text(position.md_trend)}`),
      chip(`RSI ${formatValue(position.md_rsi14, "md_rsi14")}`),
      chip(`P/L ${formatValue(position.pl_ratio, "pl_ratio")}`, valueTone(position.pl_ratio, "pl_ratio").trim() || "muted"),
      chip(`Quality ${text(position.md_quality)}`, signalTone(position.md_quality === "unavailable" ? "Data Gap" : "Neutral")),
    );

    card.append(top, name, reasonList, meta);
    return card;
  });

  target.replaceChildren(...cards);
}

function updateFilterButtons() {
  document.querySelectorAll(".filter-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === activeSignalFilter);
  });
}

function renderSignalsAndPositions() {
  updateFilterButtons();
  renderFocusList();
  renderPositionsTable(filteredPositions());
  refreshActiveDetail();
}

function renderWatchlistSummary(visibleGroups = currentWatchlists) {
  const target = $("watchlist-summary");
  const payload = currentWatchlistsPayload;
  const partialErrors = currentWatchlists.filter((group) => group.error).length;
  const items = [];

  if (payload) {
    items.push(chip(`${payload.group_count} lists`));
    items.push(chip(`${payload.security_count} securities`));
    items.push(chip(payload.group_type));
    items.push(chip(payload.source || "cache"));
    if (payload.synced_at) items.push(chip(`synced ${payload.synced_at}`));
  }

  if (watchlistSearchQuery.trim()) {
    const visibleSecurityCount = visibleGroups.reduce((total, group) => total + ((group.securities || []).length), 0);
    items.push(chip(`${visibleGroups.length} matching lists`));
    items.push(chip(`${visibleSecurityCount} shown`));
  }

  if (partialErrors > 0) items.push(chip(`${partialErrors} partial errors`, "warning"));

  target.replaceChildren(...items);
}

function watchlistStatusText(group) {
  if (group.error) return "partial error";
  const count = group.count || (group.securities || []).length;
  return `${count} securities`;
}

function renderWatchlistCard(group, index) {
  const card = document.createElement("article");
  card.className = "watchlist-card";
  const sourceIndex = group._watchlist_index ?? index;
  const collapsed = isWatchlistCollapsed(group, sourceIndex);
  if (collapsed) card.classList.add("is-collapsed");

  const header = document.createElement("div");
  header.className = "watchlist-card-header";

  const titleBlock = document.createElement("div");
  titleBlock.className = "watchlist-card-title";

  const title = document.createElement("h3");
  title.textContent = group.group_name || `Watchlist ${index + 1}`;

  const meta = document.createElement("div");
  meta.className = "watchlist-card-meta";
  const stats = watchlistCardStats(group);
  meta.append(
    chip(group.group_type || "CUSTOM"),
    chip(watchlistStatusText(group), group.error ? "warning" : "muted"),
    chip(`${stats.held} held`, stats.held > 0 ? "positive" : "muted"),
    chip(`${stats.mapped}/${stats.securities} mapped`),
    chip(`${stats.dataGap} data gaps`, stats.dataGap > 0 ? "warning" : "muted"),
  );

  titleBlock.append(title, meta);
  const toggle = document.createElement("button");
  toggle.className = "secondary-button watchlist-toggle";
  toggle.type = "button";
  toggle.textContent = collapsed ? "Expand" : "Collapse";
  toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  toggle.addEventListener("click", () => toggleWatchlistCollapsed(group, sourceIndex));

  header.append(titleBlock, toggle);
  card.appendChild(header);

  if (group.error) {
    const error = document.createElement("div");
    error.className = "watchlist-error";
    error.textContent = group.error;
    card.appendChild(error);
  }

  if (!collapsed) card.appendChild(renderWatchlistTable(group.securities || []));
  return card;
}

function renderWatchlists(groups) {
  const target = $("watchlists-list");
  const visibleGroups = visibleWatchlistGroups(groups);
  renderWatchlistSummary(visibleGroups);

  if (!visibleGroups || visibleGroups.length === 0) {
    const empty = document.createElement("div");
    empty.className = "watchlist-empty";
    empty.textContent =
      currentWatchlistsPayload?.source === "cache_missing"
        ? "No cache yet. Sync from OpenD to load your watchlists."
        : watchlistSearchQuery.trim()
          ? "No matching watchlists"
        : "No custom watchlists";
    target.replaceChildren(empty);
    return;
  }

  target.replaceChildren(...visibleGroups.map((group, index) => renderWatchlistCard(group, index)));
  refreshActiveDetail();
}

function renderWatchlistCacheStatus(payload) {
  if (!payload) return;
  if (payload.source === "cache_missing") {
    setWatchlistStatus("No cache yet. Click Sync from OpenD to create one.", "warning");
    return;
  }
  if (payload.source === "cache_error") {
    setWatchlistStatus(payload.error || "Watchlists cache error", "error");
    return;
  }
  if (payload.source === "cache") {
    setWatchlistStatus(
      payload.synced_at ? `Loaded from cache, synced ${payload.synced_at}` : "Loaded from cache",
      "positive",
    );
    return;
  }
  if (payload.source === "opend_sync") {
    setWatchlistStatus(
      payload.synced_at ? `Synced from OpenD at ${payload.synced_at}` : "Synced from OpenD",
      "positive",
    );
  }
}

async function fetchMarketDataSnapshots(codes) {
  const params = new URLSearchParams({ codes: codes.join(",") });
  const response = await fetch(`/api/market-data/snapshots?${params.toString()}`);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail);
  }
  return response.json();
}

async function fetchMarketDataSnapshotsInBatches(codes) {
  const payloads = [];
  for (let index = 0; index < codes.length; index += WATCHLIST_SNAPSHOT_BATCH_SIZE) {
    payloads.push(await fetchMarketDataSnapshots(codes.slice(index, index + WATCHLIST_SNAPSHOT_BATCH_SIZE)));
  }
  return payloads;
}

function allWatchlistCodes(groups) {
  const securities = groups.flatMap((group) => (group.error ? [] : group.securities || []));
  return uniqueCodes(securities);
}

function watchlistsWithUnavailableMarketData(groups) {
  return groups.map((group) => ({
    ...group,
    securities: group.error ? [] : unavailableWatchlistSecurities(group.securities || []),
  }));
}

function watchlistsWithSnapshots(groups, snapshotsByCode) {
  return groups.map((group) => ({
    ...group,
    securities: group.error
      ? []
      : (group.securities || []).map((security) =>
          withWatchlistMarketData(security, snapshotsByCode.get(security.code)),
        ),
  }));
}

function snapshotsBySourceCode(payloads) {
  return new Map(
    payloads.flatMap((payload) => payload.results || []).map((snapshot) => [snapshot.source_code, snapshot]),
  );
}

function renderWatchlistMarketDataStatus(payloads) {
  const requested = payloads.reduce((total, payload) => total + (payload.requested_count || 0), 0);
  const mapped = payloads.reduce((total, payload) => total + (payload.mapped_count || 0), 0);
  const unavailable = payloads.find((payload) => !payload.available);
  const partialErrors = currentWatchlists.filter((group) => group.error).length;

  if (unavailable) {
    setWatchlistStatus(unavailable.error || "Market Data Lab unavailable", "error");
    return;
  }

  const suffix = partialErrors ? `, ${partialErrors} partial errors` : "";
  setWatchlistStatus(
    `${currentWatchlists.length} lists, ${mapped}/${requested} mapped via ${payloads[0]?.api_url || "market-data-lab"}${suffix}`,
    partialErrors ? "warning" : "positive",
  );
}

async function enrichWatchlistsMarketData(sourceGroups) {
  const dataLoadId = ++activeWatchlistDataLoadId;
  const codes = allWatchlistCodes(sourceGroups);

  if (codes.length === 0) {
    setWatchlistStatus(sourceGroups.length === 0 ? "No custom watchlists" : "No securities to enrich", "muted");
    return;
  }

  setWatchlistStatus(`Loading market data for ${codes.length} unique securities...`, "muted");

  try {
    const payloads = await fetchMarketDataSnapshotsInBatches(codes);
    if (dataLoadId !== activeWatchlistDataLoadId) return;

    currentWatchlists = watchlistsWithSnapshots(sourceGroups, snapshotsBySourceCode(payloads));
    renderWatchlists(currentWatchlists);
    renderWatchlistMarketDataStatus(payloads);
  } catch (error) {
    if (dataLoadId !== activeWatchlistDataLoadId) return;
    currentWatchlists = watchlistsWithUnavailableMarketData(sourceGroups);
    renderWatchlists(currentWatchlists);
    setWatchlistStatus(error.message, "error");
  }
}

async function loadWatchlists(loadId) {
  setWatchlistStatus("Loading watchlists cache...", "muted");
  const params = new URLSearchParams({
    host: $("host").value,
    port: $("port").value,
    group_type: "CUSTOM",
  });

  try {
    const response = await fetch(`/api/watchlists?${params.toString()}`);
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail);
    }

    const payload = await response.json();
    if (loadId !== activeWatchlistsLoadId) return;

    currentWatchlistsPayload = payload;
    const sourceGroups = payload.groups || [];
    currentWatchlists = watchlistsWithUnavailableMarketData(sourceGroups);
    renderWatchlists(currentWatchlists);
    renderWatchlistCacheStatus(payload);
    if (sourceGroups.length === 0) return;
    await enrichWatchlistsMarketData(sourceGroups);
  } catch (error) {
    if (loadId !== activeWatchlistsLoadId) return;
    watchlistsLoaded = false;
    currentWatchlistsPayload = null;
    currentWatchlists = [];
    renderWatchlists(currentWatchlists);
    setWatchlistStatus(error.message, "error");
  }
}

async function syncWatchlistsFromOpenD() {
  const loadId = ++activeWatchlistsLoadId;
  setWatchlistsSyncing(true);
  setWatchlistStatus("Syncing from OpenD... this may take about 1-2 minutes.", "muted");
  const params = new URLSearchParams({
    host: $("host").value,
    port: $("port").value,
    group_type: "CUSTOM",
  });

  try {
    const response = await fetch(`/api/watchlists/sync?${params.toString()}`, { method: "POST" });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail);
    }

    const payload = await response.json();
    if (loadId !== activeWatchlistsLoadId) return;

    watchlistsLoaded = true;
    currentWatchlistsParamsKey = watchlistsParamsKey();
    currentWatchlistsPayload = payload;
    const sourceGroups = payload.groups || [];
    currentWatchlists = watchlistsWithUnavailableMarketData(sourceGroups);
    renderWatchlists(currentWatchlists);
    renderWatchlistCacheStatus(payload);
    if (sourceGroups.length > 0) await enrichWatchlistsMarketData(sourceGroups);
  } catch (error) {
    if (loadId !== activeWatchlistsLoadId) return;
    setWatchlistStatus(error.message, "error");
  } finally {
    if (loadId === activeWatchlistsLoadId) setWatchlistsSyncing(false);
  }
}

function renderDashboardData(data) {
  renderMetrics("status", [
    ["Program", data.state.program_status_type],
    ["Quote Login", data.state.qot_logined],
    ["Trade Login", data.state.trd_logined],
    ["Server", data.state.server_ver],
  ]);
  renderMetrics("account", [
    ["Account", data.account.acc_id],
    ["Type", data.account.acc_type],
    ["Firm", data.account.security_firm],
    ["Status", data.account.acc_status],
  ]);
  renderMetrics("assets-summary", [
    ["Total", data.assets.total_assets, "total_assets"],
    ["Cash", data.assets.cash, "cash"],
    ["Market Value", data.assets.market_val, "market_val"],
    ["Currency", data.assets.currency],
  ]);
  renderTable("currency", [data.assets], ["hk_cash", "hkd_assets", "us_cash", "usd_assets", "au_cash", "aud_assets"]);
}

async function loadMarketData(positions) {
  const codes = uniqueCodes(positions);
  if (codes.length === 0) {
    setMarketDataStatus("No positions to enrich", "muted");
    return positions;
  }

  setMarketDataStatus("Loading market data...", "muted");

  try {
    const payload = await fetchMarketDataSnapshots(codes);
    const snapshotsByCode = new Map(payload.results.map((snapshot) => [snapshot.source_code, snapshot]));
    renderMarketDataStatus(payload);
    return positions.map((position) => withMarketData(position, snapshotsByCode.get(position.code)));
  } catch (error) {
    setMarketDataStatus(error.message, "error");
    return unavailablePositions(positions);
  }
}

async function loadDashboard(loadId) {
  setMessage("Loading...", "muted");
  setMarketDataStatus("Waiting for positions", "muted");
  const params = new URLSearchParams({
    host: $("host").value,
    port: $("port").value,
    market: $("market").value,
  });

  try {
    const response = await fetch(`/api/dashboard?${params.toString()}`);
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail);
    }

    const data = await response.json();
    if (loadId !== activeLoadId) return;

    currentDashboard = data;
    currentPositions = unavailablePositions(data.positions);
    renderDashboardData(data);
    renderSignalsAndPositions();
    renderWatchlists(currentWatchlists);
    setMessage(`${data.position_count} positions`, "positive");

    const enrichedPositions = await loadMarketData(data.positions);
    if (loadId !== activeLoadId) return;
    currentPositions = enrichedPositions;
    renderSignalsAndPositions();
    renderWatchlists(currentWatchlists);
  } catch (error) {
    if (loadId !== activeLoadId) return;
    setMessage(error.message, "error");
  }
}

function loadAll() {
  loadOverview();
  if (activePage === "watchlists") loadWatchlistsPage();
}

function loadOverview() {
  const loadId = ++activeLoadId;
  loadDashboard(loadId);
}

function watchlistsParamsKey() {
  return `${$("host").value}:${$("port").value}:CUSTOM`;
}

function loadWatchlistsPage(options = {}) {
  const key = watchlistsParamsKey();
  if (watchlistsLoaded && !options.force && currentWatchlistsParamsKey === key) return;
  watchlistsLoaded = true;
  currentWatchlistsParamsKey = key;
  const loadId = ++activeWatchlistsLoadId;
  loadWatchlists(loadId);
}

function refreshActivePage() {
  if (activePage === "watchlists") {
    loadWatchlistsPage({ force: true });
    return;
  }
  loadOverview();
}

$("controls").addEventListener("submit", (event) => {
  event.preventDefault();
  refreshActivePage();
});

$("privacy-toggle").addEventListener("click", togglePrivacyMode);
$("detail-privacy").addEventListener("click", togglePrivacyMode);

document.querySelectorAll(".filter-button").forEach((button) => {
  button.addEventListener("click", () => {
    activeSignalFilter = button.dataset.filter;
    renderSignalsAndPositions();
  });
});

$("watchlist-search").addEventListener("input", (event) => {
  watchlistSearchQuery = event.target.value.trim().toLowerCase();
  renderWatchlists(currentWatchlists);
});

$("watchlists-expand").addEventListener("click", () => setWatchlistExpansionMode("all-expanded"));
$("watchlists-collapse").addEventListener("click", () => setWatchlistExpansionMode("all-collapsed"));

document.querySelectorAll("[data-page-target]").forEach((item) => {
  item.addEventListener("click", (event) => {
    event.preventDefault();
    const target = item.dataset.pageTarget;
    if (window.location.hash === `#${target}`) {
      setActivePage(target);
    } else {
      window.location.hash = target;
    }
  });
});

$("watchlists-sync").addEventListener("click", syncWatchlistsFromOpenD);

$("detail-close").addEventListener("click", closePositionDetail);
$("detail-backdrop").addEventListener("click", closePositionDetail);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && activeDetailCode) closePositionDetail();
});

window.addEventListener("hashchange", () => {
  setActivePage(pageFromHash());
});

if (window.location.hash !== "#overview" && window.location.hash !== "#watchlists") {
  window.history.replaceState(null, "", "#overview");
}
setActivePage(pageFromHash());
loadAll();
