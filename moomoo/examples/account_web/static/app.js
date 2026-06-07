const $ = (id) => document.getElementById(id);

let activeLoadId = 0;
let privacyMode = true;
let activeSignalFilter = "all";
let currentDashboard = null;
let currentPositions = [];

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

function text(value) {
  if (value === null || value === undefined || value === "") return "N/A";
  return String(value);
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
    header.textContent = column;
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
  };
  const signal = classifySignal(enriched);
  return { ...enriched, ...signal };
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
  renderTable("positions-table", filteredPositions(), positionColumns);
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
  const params = new URLSearchParams({ codes: codes.join(",") });

  try {
    const response = await fetch(`/api/market-data/snapshots?${params.toString()}`);
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail);
    }

    const payload = await response.json();
    const snapshotsByCode = new Map(payload.results.map((snapshot) => [snapshot.source_code, snapshot]));
    renderMarketDataStatus(payload);
    return positions.map((position) => withMarketData(position, snapshotsByCode.get(position.code)));
  } catch (error) {
    setMarketDataStatus(error.message, "error");
    return unavailablePositions(positions);
  }
}

async function loadDashboard() {
  const loadId = ++activeLoadId;
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
    setMessage(`${data.position_count} positions`, "positive");

    const enrichedPositions = await loadMarketData(data.positions);
    if (loadId !== activeLoadId) return;
    currentPositions = enrichedPositions;
    renderSignalsAndPositions();
  } catch (error) {
    if (loadId !== activeLoadId) return;
    setMessage(error.message, "error");
  }
}

$("controls").addEventListener("submit", (event) => {
  event.preventDefault();
  loadDashboard();
});

$("privacy-toggle").addEventListener("click", () => {
  privacyMode = !privacyMode;
  $("privacy-toggle").textContent = privacyMode ? "Reveal" : "Hide";
  if (currentDashboard) renderDashboardData(currentDashboard);
  renderSignalsAndPositions();
});

document.querySelectorAll(".filter-button").forEach((button) => {
  button.addEventListener("click", () => {
    activeSignalFilter = button.dataset.filter;
    renderSignalsAndPositions();
  });
});

loadDashboard();
