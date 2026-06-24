const state = {
  payload: null,
  currentSymbol: null,
  currentMode: "demo",
  currentConfig: null,
  availableModes: [],
  autoRefreshEnabled: true,
  autoRefreshSeconds: 30,
  autoRefreshTimer: null,
  refreshInFlight: false,
  lastFetchMs: null,
  chart: null,
  candleSeries: null,
  volumeSeries: null,
};

const elements = {
  metricGrid: document.getElementById("metric-grid"),
  statusStrip: document.getElementById("status-strip"),
  modeSwitcher: document.getElementById("mode-switcher"),
  heroEyebrow: document.getElementById("hero-eyebrow"),
  watchlist: document.getElementById("watchlist"),
  updatedAt: document.getElementById("updated-at"),
  botThesis: document.getElementById("bot-thesis"),
  signalFeed: document.getElementById("signal-feed"),
  signalCount: document.getElementById("signal-count"),
  newsFeed: document.getElementById("news-feed"),
  newsCount: document.getElementById("news-count"),
  fillsTableBody: document.getElementById("fills-table-body"),
  chartSymbol: document.getElementById("chart-symbol"),
  chartCaption: document.getElementById("chart-caption"),
  detailGrid: document.getElementById("detail-grid"),
  refreshButton: document.getElementById("refresh-button"),
  autoRefreshToggle: document.getElementById("auto-refresh-toggle"),
  refreshInterval: document.getElementById("refresh-interval"),
  modePill: document.getElementById("mode-pill"),
  chartContainer: document.getElementById("chart"),
};

function formatMoney(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatNumber(value, digits = 2) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function formatPercent(value) {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${formatNumber(value, 2)}%`;
}

function formatTime(unixSeconds) {
  return new Date(unixSeconds * 1000).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function renderModeSwitcher() {
  if (!state.availableModes.length) {
    return;
  }

  elements.modeSwitcher.innerHTML = state.availableModes
    .filter((mode) => mode.available)
    .map((mode) => {
      const activeClass = mode.key === state.currentMode ? "is-active" : "";
      return `
        <button class="mode-option ${activeClass}" data-mode="${mode.key}" data-config-path="${mode.config_path}" type="button">
          <span class="mode-option-title">${mode.label}</span>
          <span class="mode-option-copy">${mode.description}</span>
        </button>
      `;
    })
    .join("");

  elements.modeSwitcher.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.currentMode = button.dataset.mode;
      state.currentConfig = button.dataset.configPath || null;
      renderModeSwitcher();
      loadDashboard();
    });
  });
}

function refreshStatusLabel() {
  if (!state.autoRefreshEnabled) {
    return "Manual refresh";
  }
  if (state.refreshInFlight) {
    return "Refreshing now";
  }
  return `Every ${state.autoRefreshSeconds}s`;
}

function syncRefreshControls() {
  elements.autoRefreshToggle.checked = state.autoRefreshEnabled;
  elements.refreshInterval.value = String(state.autoRefreshSeconds);
  elements.refreshInterval.disabled = !state.autoRefreshEnabled;
  elements.autoRefreshToggle.disabled = state.refreshInFlight && !state.payload;
}

function clearAutoRefreshTimer() {
  if (state.autoRefreshTimer) {
    window.clearTimeout(state.autoRefreshTimer);
    state.autoRefreshTimer = null;
  }
}

function scheduleAutoRefresh() {
  clearAutoRefreshTimer();
  if (!state.autoRefreshEnabled) {
    return;
  }
  state.autoRefreshTimer = window.setTimeout(() => {
    loadDashboard();
  }, state.autoRefreshSeconds * 1000);
}

function renderSystemStatus() {
  if (!state.payload) {
    elements.statusStrip.innerHTML = "";
    return;
  }

  const status = state.payload.system_status || {};
  const cards = [
    {
      label: "Broker",
      value: status.broker_label || "Demo Engine",
      detail: status.market_context || "Market snapshot",
    },
    {
      label: "Execution",
      value: status.execution_label || "Preview",
      detail: state.payload.execute_orders ? "Orders may be sent" : "Orders blocked at preview",
    },
    {
      label: "Universe",
      value: `${status.symbol_count || state.payload.instruments.length} symbols`,
      detail: status.symbols_preview || "No symbols configured",
    },
    {
      label: "Refresh",
      value: refreshStatusLabel(),
      detail: state.lastFetchMs !== null ? `${state.lastFetchMs} ms last fetch` : "Waiting for snapshot",
    },
  ];

  elements.statusStrip.innerHTML = cards
    .map(
      (card) => `
        <article class="status-card">
          <div class="status-label">${card.label}</div>
          <div class="status-value">${card.value}</div>
          <div class="status-detail">${card.detail}</div>
        </article>
      `
    )
    .join("");
}

function ensureChart() {
  if (state.chart || !window.LightweightCharts) {
    return;
  }

  state.chart = LightweightCharts.createChart(elements.chartContainer, {
    layout: {
      background: { color: "transparent" },
      textColor: "#9fb7c7",
      fontFamily: "'IBM Plex Sans', sans-serif",
    },
    grid: {
      vertLines: { color: "rgba(255,255,255,0.05)" },
      horzLines: { color: "rgba(255,255,255,0.05)" },
    },
    crosshair: {
      vertLine: { color: "rgba(246, 173, 85, 0.35)" },
      horzLine: { color: "rgba(246, 173, 85, 0.25)" },
    },
    rightPriceScale: {
      borderColor: "rgba(255,255,255,0.08)",
    },
    timeScale: {
      borderColor: "rgba(255,255,255,0.08)",
      timeVisible: true,
      secondsVisible: false,
    },
  });

  state.volumeSeries = state.chart.addSeries(LightweightCharts.HistogramSeries, {
    color: "rgba(54, 207, 201, 0.35)",
    priceFormat: { type: "volume" },
    priceScaleId: "",
  });
  state.volumeSeries.priceScale().applyOptions({
    scaleMargins: {
      top: 0.78,
      bottom: 0,
    },
  });

  state.candleSeries = state.chart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: "#36cfc9",
    downColor: "#ff6b6b",
    borderVisible: false,
    wickUpColor: "#36cfc9",
    wickDownColor: "#ff6b6b",
  });
  state.candleSeries.priceScale().applyOptions({
    scaleMargins: {
      top: 0.06,
      bottom: 0.26,
    },
  });

  window.addEventListener("resize", resizeChart);
  resizeChart();
}

function resizeChart() {
  if (!state.chart) {
    return;
  }
  const { width, height } = elements.chartContainer.getBoundingClientRect();
  state.chart.resize(width, height);
}

function renderMetrics(metrics) {
  const isLiveSnapshot = Boolean(state.payload?.live_mode);
  const equityFootnote = isLiveSnapshot
    ? `Cash Base ${formatMoney(metrics.starting_cash)}`
    : `Start ${formatMoney(metrics.starting_cash)}`;
  const cashFootnote = state.payload?.paper_trading
    ? "Paper account cash"
    : isLiveSnapshot
      ? "Live account cash"
      : "Simulated cash";
  const cards = [
    {
      label: "Ending Equity",
      value: formatMoney(metrics.ending_equity),
      footnote: equityFootnote,
    },
    {
      label: "Net PnL",
      value: formatMoney(metrics.pnl),
      footnote: formatPercent(metrics.return_pct),
      deltaClass: metrics.pnl >= 0 ? "delta-positive" : "delta-negative",
    },
    {
      label: "Executed Fills",
      value: String(metrics.fill_count),
      footnote: `${metrics.open_position_count} open positions`,
    },
    {
      label: "Available Cash",
      value: formatMoney(metrics.ending_cash),
      footnote: cashFootnote,
    },
  ];

  elements.metricGrid.innerHTML = cards
    .map(
      (card) => `
        <article class="metric-card">
          <div class="metric-label">${card.label}</div>
          <div class="metric-value ${card.deltaClass ?? ""}">${card.value}</div>
          <div class="metric-footnote">${card.footnote}</div>
        </article>
      `
    )
    .join("");
}

function renderWatchlist(instruments) {
  elements.watchlist.innerHTML = instruments
    .map((instrument) => {
      const activeClass = instrument.symbol === state.currentSymbol ? "is-active" : "";
      const deltaClass = instrument.change_pct >= 0 ? "delta-positive" : "delta-negative";
      return `
        <button class="watchlist-button ${activeClass}" data-symbol="${instrument.symbol}" type="button">
          <div class="watchlist-symbol">
            <span>${instrument.symbol}</span>
            <span class="${deltaClass}">${formatPercent(instrument.change_pct)}</span>
          </div>
          <div class="watchlist-meta">
            <span>${instrument.asset_class}</span>
            <span>${formatMoney(instrument.latest_price)}</span>
          </div>
        </button>
      `;
    })
    .join("");

  elements.watchlist.querySelectorAll("[data-symbol]").forEach((button) => {
    button.addEventListener("click", () => {
      state.currentSymbol = button.dataset.symbol;
      renderSelectedSymbol();
      renderWatchlist(state.payload.instruments);
    });
  });
}

function buildMarker(decision) {
  const isBuy = decision.signal === "buy";
  const executed = decision.status === "executed";
  const preview = decision.status === "preview";
  return {
    time: decision.time,
    position: isBuy ? "belowBar" : "aboveBar",
    color: executed ? (isBuy ? "#2ed47a" : "#ff6b6b") : "#f6ad55",
    shape: executed ? (isBuy ? "arrowUp" : "arrowDown") : "circle",
    text: executed ? decision.signal.toUpperCase() : (preview ? "PREVIEW" : "BLOCKED"),
  };
}

function renderChart(instrument) {
  ensureChart();
  if (!state.chart || !instrument) {
    return;
  }

  state.candleSeries.setData(instrument.candles);
  state.volumeSeries.setData(
    instrument.candles.map((candle) => ({
      time: candle.time,
      value: candle.volume,
      color: candle.close >= candle.open ? "rgba(46, 212, 122, 0.32)" : "rgba(255, 107, 107, 0.32)",
    }))
  );

  const decisions = state.payload.decisions
    .filter((decision) => decision.symbol === instrument.symbol)
    .map(buildMarker);
  if (typeof state.candleSeries.setMarkers === "function") {
    state.candleSeries.setMarkers(decisions);
  } else if (typeof LightweightCharts.createSeriesMarkers === "function") {
    LightweightCharts.createSeriesMarkers(state.candleSeries, decisions);
  }
  state.chart.timeScale().fitContent();
  resizeChart();
}

function renderSignalFeed(symbol) {
  const decisions = state.payload.decisions
    .filter((decision) => decision.symbol === symbol)
    .slice()
    .reverse();

  elements.signalCount.textContent = `${decisions.length} signals`;
  elements.signalFeed.innerHTML = decisions.length
    ? decisions
        .map((decision) => {
          const directionClass = decision.signal === "buy" ? "tag-buy" : "tag-sell";
          const statusClass = decision.status === "rejected"
            ? "tag-rejected"
            : decision.status === "preview"
              ? "tag-preview"
              : directionClass;
          const statusLabel = decision.status === "executed"
            ? decision.signal.toUpperCase()
            : decision.status.toUpperCase();
          return `
            <article class="signal-card">
              <div class="signal-topline">
                <div>
                  <div class="signal-symbol">${decision.symbol}</div>
                  <div class="detail-label">${formatTime(decision.time)}</div>
                </div>
                <span class="tag ${statusClass}">${statusLabel}</span>
              </div>
              <div class="signal-reason">${decision.reason || "No strategy explanation supplied."}</div>
              ${
                decision.detail
                  ? `<div class="signal-reason">Risk note: ${decision.detail}</div>`
                  : ""
              }
            </article>
          `;
        })
        .join("")
    : `<article class="signal-card"><div class="signal-reason">No actionable signals yet for ${symbol}.</div></article>`;
}

function renderNews(symbol) {
  const instrument = state.payload.instruments.find((candidate) => candidate.symbol === symbol);
  const articles = instrument?.news || [];

  if (state.payload.news_error) {
    elements.newsCount.textContent = "news offline";
    elements.newsFeed.innerHTML = `
      <article class="news-card">
        <div class="signal-reason">Unable to load Alpaca news right now: ${state.payload.news_error}</div>
      </article>
    `;
    return;
  }

  elements.newsCount.textContent = `${articles.length} articles`;
  elements.newsFeed.innerHTML = articles.length
    ? articles
        .map((article) => {
          const source = article.source ? article.source.toUpperCase() : "NEWS";
          const image = article.image_url
            ? `<img class="news-media" src="${article.image_url}" alt="${article.headline}">`
            : "";
          const summary = article.summary || "No summary available for this article yet.";
          const related = article.related_symbols?.length
            ? `<div class="news-related">${article.related_symbols.join(" · ")}</div>`
            : "";
          return `
            <article class="news-card">
              ${image}
              <div class="news-meta">
                <span>${source}</span>
                <span>${formatTime(article.time)}</span>
              </div>
              <a class="news-link" href="${article.url}" target="_blank" rel="noreferrer">${article.headline}</a>
              <div class="news-summary">${summary}</div>
              ${related}
            </article>
          `;
        })
        .join("")
    : `<article class="news-card"><div class="signal-reason">No recent Alpaca news matched ${symbol}.</div></article>`;
}

function renderDetails(instrument) {
  const position = instrument.position;
  const lastSignal = instrument.last_signal;
  const details = [
    {
      label: "Asset Class",
      value: instrument.asset_class,
    },
    {
      label: "Latest Price",
      value: formatMoney(instrument.latest_price),
    },
    {
      label: "Open Position",
      value: position ? formatNumber(position.quantity, 4) : "0.0000",
    },
    {
      label: "Last Signal",
      value: lastSignal ? `${lastSignal.signal.toUpperCase()} / ${lastSignal.status}` : "No signal",
    },
  ];

  elements.detailGrid.innerHTML = details
    .map(
      (detail) => `
        <div class="detail-item">
          <div class="detail-label">${detail.label}</div>
          <div class="detail-value">${detail.value}</div>
        </div>
      `
    )
    .join("");
}

function renderFills(symbol) {
  const fills = state.payload.fills
    .filter((fill) => fill.symbol === symbol)
    .slice()
    .reverse();
  elements.fillsTableBody.innerHTML = fills.length
    ? fills
        .map(
          (fill) => `
            <tr>
              <td>${formatTime(fill.time)}</td>
              <td>${fill.symbol}</td>
              <td class="${fill.side === "buy" ? "delta-positive" : "delta-negative"}">${fill.side.toUpperCase()}</td>
              <td>${formatNumber(fill.quantity, 4)}</td>
              <td>${formatMoney(fill.price)}</td>
            </tr>
          `
        )
        .join("")
    : `<tr><td colspan="5">No fills yet for ${symbol}.</td></tr>`;
}

function renderSelectedSymbol() {
  const instrument = state.payload.instruments.find(
    (candidate) => candidate.symbol === state.currentSymbol
  );
  if (!instrument) {
    return;
  }

  const latestSignal = instrument.last_signal;
  elements.chartSymbol.textContent = instrument.symbol;
  elements.chartCaption.textContent = latestSignal
    ? `${instrument.asset_class} · Last ${latestSignal.signal.toUpperCase()} ${latestSignal.status} at ${formatMoney(latestSignal.price)}`
    : `${instrument.asset_class} · No actionable signal yet`;
  elements.botThesis.textContent = instrument.analysis_summary || state.payload.bot_summary;

  renderChart(instrument);
  renderSignalFeed(instrument.symbol);
  renderNews(instrument.symbol);
  renderDetails(instrument);
  renderFills(instrument.symbol);
}

function renderPayload(payload) {
  state.payload = payload;
  state.currentMode = payload.mode || state.currentMode;
  if (!payload.instruments.some((instrument) => instrument.symbol === state.currentSymbol)) {
    state.currentSymbol = payload.instruments[0]?.symbol || null;
  }
  elements.modePill.textContent = payload.mode_label || (payload.paper_trading ? "Paper Mode" : "Live Mode");
  elements.heroEyebrow.textContent = payload.mode_label || "Trading Dashboard";
  elements.updatedAt.textContent = `Updated ${new Date(payload.generated_at).toLocaleTimeString()}`;
  renderSystemStatus();
  renderMetrics(payload.metrics);
  renderModeSwitcher();
  renderWatchlist(payload.instruments);
  renderSelectedSymbol();
}

async function loadModes() {
  const response = await fetch("/api/modes", { cache: "no-store" });
  const payload = await response.json();
  state.availableModes = payload.modes || [];
  state.currentMode = payload.default_mode || state.currentMode;
  state.currentConfig = payload.default_config || null;
  renderModeSwitcher();
}

async function loadDashboard() {
  if (state.refreshInFlight) {
    return;
  }
  clearAutoRefreshTimer();
  const requestStartedAt = performance.now();
  state.refreshInFlight = true;
  syncRefreshControls();
  renderSystemStatus();
  elements.refreshButton.disabled = true;
  elements.refreshButton.textContent = "Refreshing...";
  try {
    const query = state.currentConfig
      ? `/api/dashboard?config=${encodeURIComponent(state.currentConfig)}`
      : `/api/dashboard?mode=${encodeURIComponent(state.currentMode)}`;
    const response = await fetch(query, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Dashboard request failed.");
    }
    state.lastFetchMs = Math.round(performance.now() - requestStartedAt);
    renderPayload(payload);
  } catch (error) {
    elements.botThesis.textContent = `Unable to load dashboard data: ${error.message}`;
  } finally {
    state.refreshInFlight = false;
    syncRefreshControls();
    renderSystemStatus();
    scheduleAutoRefresh();
    elements.refreshButton.disabled = false;
    elements.refreshButton.textContent = "Refresh Snapshot";
  }
}

elements.refreshButton.addEventListener("click", loadDashboard);
elements.autoRefreshToggle.addEventListener("change", () => {
  state.autoRefreshEnabled = elements.autoRefreshToggle.checked;
  syncRefreshControls();
  renderSystemStatus();
  scheduleAutoRefresh();
});
elements.refreshInterval.addEventListener("change", () => {
  state.autoRefreshSeconds = Number.parseInt(elements.refreshInterval.value, 10) || 30;
  syncRefreshControls();
  renderSystemStatus();
  scheduleAutoRefresh();
});
window.addEventListener("load", () => {
  const boot = () => {
    if (!window.LightweightCharts) {
      window.setTimeout(boot, 100);
      return;
    }
    syncRefreshControls();
    loadModes().then(loadDashboard).catch((error) => {
      elements.botThesis.textContent = `Unable to initialize dashboard: ${error.message}`;
    });
  };
  boot();
});
