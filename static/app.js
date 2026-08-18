const state = {
  symbol: 'BTCUSDT',
  interval: '15m',
  overview: [],
  chart: null,
  candleSeries: null,
  lineSeries: null,
  ws: null,
  signal: null,
  requestId: 0,
  overviewLoading: false,
  activeLoading: false,
  refreshTimer: null,
  liveBar: null,
  symbolMenuOpen: false
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const fmt = (value) => value === undefined || value === null || Number.isNaN(Number(value))
  ? '—'
  : Number(value).toLocaleString('en-US', { maximumFractionDigits: 8 });
const pct = (value) => `${Number(value || 0) >= 0 ? '+' : ''}${Number(value || 0).toFixed(2)}%`;
const intervalSeconds = { '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 };

function toast(text) {
  const el = $('#toast');
  if (!el) return;
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove('show'), 2400);
}

async function api(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { Accept: 'application/json', ...(options.headers || {}) } });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function renderWatchlist() {
  const query = ($('#symbol-search')?.value || '').trim().toUpperCase();
  const rows = state.overview.filter((item) => item.symbol.includes(query));
  const watchlist = $('#watchlist');
  const existingSymbols = $$('.watch-item').map((element) => element.dataset.symbol).join(',');
  const nextSymbols = rows.map((item) => item.symbol).join(',');
  if (existingSymbols !== nextSymbols) {
    watchlist.innerHTML = rows.length
      ? rows.map((item) => `<button class="watch-item" data-symbol="${item.symbol}" type="button">
          <span><span class="watch-symbol">${item.symbol}</span><span class="watch-sub"></span></span>
          <span><span class="watch-price"></span><span class="watch-change"></span></span>
        </button>`).join('')
      : '<div class="empty-state">لا توجد عملة مطابقة</div>';
    $$('.watch-item').forEach((element) => {
      element.addEventListener('click', () => selectSymbol(element.dataset.symbol));
    });
  }
  rows.forEach((item) => updateWatchItem(item));
  const mobileSelect = $('#mobile-symbol-select');
  if (mobileSelect) {
    const selectSymbols = [...mobileSelect.options].map((option) => option.value).join(',');
    const overviewSymbols = state.overview.map((item) => item.symbol).join(',');
    if (!state.symbolMenuOpen && selectSymbols !== overviewSymbols) {
      mobileSelect.innerHTML = state.overview.map((item) => `<option value="${item.symbol}">${item.symbol}</option>`).join('');
    }
    if (!state.symbolMenuOpen && mobileSelect.value !== state.symbol) mobileSelect.value = state.symbol;
  }
  renderMobileSymbolPicker();
}

function renderMobileSymbolPicker() {
  const menu = $('#mobile-symbol-menu');
  const label = $('#mobile-symbol-label');
  if (!menu || !label) return;
  label.textContent = state.symbol;
  const symbols = state.overview.map((item) => item.symbol);
  const existing = [...menu.querySelectorAll('.mobile-symbol-option')].map((element) => element.dataset.symbol);
  if (existing.join(',') !== symbols.join(',')) {
    menu.innerHTML = symbols.map((symbol) => `<button type="button" class="mobile-symbol-option" role="option" data-symbol="${symbol}">${symbol}</button>`).join('');
  }
  menu.querySelectorAll('.mobile-symbol-option').forEach((element) => {
    element.classList.toggle('active', element.dataset.symbol === state.symbol);
    element.setAttribute('aria-selected', element.dataset.symbol === state.symbol ? 'true' : 'false');
  });
}

function setMobileSymbolMenu(open) {
  const picker = $('#mobile-symbol-picker');
  const trigger = $('#mobile-symbol-trigger');
  const menu = $('#mobile-symbol-menu');
  if (!picker || !trigger || !menu) return;
  state.symbolMenuOpen = open;
  picker.classList.toggle('open', open);
  trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
  menu.hidden = !open;
  if (open) {
    renderMobileSymbolPicker();
    menu.querySelector('.mobile-symbol-option.active')?.scrollIntoView({ block: 'nearest' });
  }
}

function updateWatchItem(item) {
  const element = document.querySelector(`.watch-item[data-symbol="${item.symbol}"]`);
  if (!element) return;
  const ticker = item.ticker || {};
  const change = Number(ticker.change || 0);
  element.classList.toggle('active', item.symbol === state.symbol);
  element.querySelector('.watch-sub').textContent = `${item.signal || 'NO TRADE'} · ${item.confidence || 0}%`;
  element.querySelector('.watch-price').textContent = fmt(ticker.price ?? item.price);
  const changeElement = element.querySelector('.watch-change');
  changeElement.textContent = pct(change);
  changeElement.className = `watch-change ${change >= 0 ? 'positive' : 'negative'}`;
}

function initChart() {
  const container = $('#chart');
  state.chart = LightweightCharts.createChart(container, {
    layout: { background: { color: '#0b1621' }, textColor: '#7890a2' },
    grid: { vertLines: { color: '#132534' }, horzLines: { color: '#132534' } },
    rightPriceScale: { borderColor: '#22394a' },
    timeScale: { borderColor: '#22394a', timeVisible: true, secondsVisible: false },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal }
  });
  state.candleSeries = state.chart.addCandlestickSeries({ upColor: '#33d69a', downColor: '#ff6b78', borderVisible: false, wickUpColor: '#33d69a', wickDownColor: '#ff6b78' });
  state.lineSeries = state.chart.addLineSeries({ color: '#54a9ff', lineWidth: 2, visible: false });
  new ResizeObserver(() => state.chart.applyOptions({ width: container.clientWidth })).observe(container);
}

async function loadChart(requestId = state.requestId) {
  const data = await api(`/api/market/candles?symbol=${encodeURIComponent(state.symbol)}&interval=${encodeURIComponent(state.interval)}&limit=250`);
  if (requestId !== state.requestId) return;
  const candles = data.candles || [];
  state.candleSeries.setData(candles.map((candle) => ({ time: candle.time, open: candle.open, high: candle.high, low: candle.low, close: candle.close })));
  state.lineSeries.setData(candles.map((candle) => ({ time: candle.time, value: candle.close })));
  state.liveBar = candles.length ? { ...candles[candles.length - 1] } : null;
  state.chart.timeScale().fitContent();
}

function renderSignal(item) {
  if (!item) return;
  state.signal = item;
  const signal = item.signal || 'NO TRADE';
  const ticker = item.ticker || {};
  const badge = $('#active-signal');
  badge.textContent = signal;
  badge.className = `signal-badge ${signal === 'LONG' ? 'long' : signal === 'SHORT' ? 'short' : 'neutral'}`;
  $('#active-symbol').textContent = item.symbol;
  $('#active-price').textContent = fmt(ticker.price ?? item.price);
  $('#active-regime').textContent = item.regime || '—';
  $('#active-confidence').textContent = `${item.confidence || 0}%`;
  $('#active-rr').textContent = item.rr ? `1:${item.rr}` : '—';
  $('#active-change').textContent = pct(ticker.change);
  $('#active-change').className = Number(ticker.change || 0) >= 0 ? 'positive' : 'negative';
  const color = signal === 'LONG' ? 'positive' : signal === 'SHORT' ? 'negative' : 'neutral';
  const context = [item.asset_profile_label, item.regime].filter(Boolean).join(' · ') || 'TRANSITION';
  $('#signal-content').innerHTML = `<div class="signal-main"><div><span class="eyebrow">${context}</span><div class="signal-word ${color}">${signal}</div></div><div><span class="eyebrow">CONFIDENCE</span><div class="confidence">${item.confidence || 0}</div></div></div><div class="reasons">${(item.reasons || [item.reason || 'لا توجد أسباب كافية']).map((reason) => `<span class="reason">✓ ${reason}</span>`).join('')}</div><div class="levels"><div class="level"><small>ENTRY</small><strong>${fmt(item.entry)}</strong></div><div class="level"><small>STOP LOSS</small><strong class="negative">${fmt(item.stop_loss)}</strong></div><div class="level"><small>TP1</small><strong class="positive">${fmt(item.take_profit_1)}</strong></div><div class="level"><small>TP2</small><strong class="positive">${fmt(item.take_profit_2)}</strong></div></div>`;
}

function updateLiveChart(candle) {
  if (!state.candleSeries || !candle || (candle.symbol && candle.symbol !== state.symbol)) return;
  const seconds = intervalSeconds[state.interval] || 900;
  const bucketTime = Math.floor(Number(candle.time) / seconds) * seconds;
  if (!state.liveBar || state.liveBar.time !== bucketTime) {
    state.liveBar = { time: bucketTime, open: candle.open, high: candle.high, low: candle.low, close: candle.close };
  } else {
    state.liveBar.high = Math.max(state.liveBar.high, candle.high);
    state.liveBar.low = Math.min(state.liveBar.low, candle.low);
    state.liveBar.close = candle.close;
  }
  state.candleSeries.update({ time: state.liveBar.time, open: state.liveBar.open, high: state.liveBar.high, low: state.liveBar.low, close: state.liveBar.close });
  state.lineSeries.update({ time: state.liveBar.time, value: state.liveBar.close });
}

function updateLivePrice(price, updatedAt = Math.floor(Date.now() / 1000)) {
  const value = Number(price);
  if (!state.candleSeries || !Number.isFinite(value)) return;
  const seconds = intervalSeconds[state.interval] || 900;
  const bucketTime = Math.floor(Number(updatedAt) / seconds) * seconds;
  if (!state.liveBar || state.liveBar.time !== bucketTime) {
    state.liveBar = { time: bucketTime, open: value, high: value, low: value, close: value };
  } else {
    state.liveBar.high = Math.max(state.liveBar.high, value);
    state.liveBar.low = Math.min(state.liveBar.low, value);
    state.liveBar.close = value;
  }
  state.candleSeries.update({ time: state.liveBar.time, open: state.liveBar.open, high: state.liveBar.high, low: state.liveBar.low, close: state.liveBar.close });
  state.lineSeries.update({ time: state.liveBar.time, value });
}

function activeOverviewItem() {
  return state.overview.find((item) => item.symbol === state.symbol);
}

async function selectSymbol(symbol) {
  if (!symbol || symbol === state.symbol && state.activeLoading) return;
  state.symbol = symbol.toUpperCase();
  const requestId = ++state.requestId;
  renderWatchlist();
  const active = activeOverviewItem();
  if (active) renderSignal(active);
  state.activeLoading = true;
  try {
    const [signal] = await Promise.all([
      api(`/api/signals/${encodeURIComponent(state.symbol)}?interval=${encodeURIComponent(state.interval)}`),
      loadChart(requestId)
    ]);
    if (requestId !== state.requestId) return;
    renderSignal({ ...signal, ticker: activeOverviewItem()?.ticker });
    $('#last-update').textContent = new Date().toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' });
  } catch (error) {
    if (requestId === state.requestId) toast(`تعذر تحميل ${state.symbol}`);
  } finally {
    if (requestId === state.requestId) state.activeLoading = false;
  }
}

async function loadOverview() {
  if (state.overviewLoading) return;
  state.overviewLoading = true;
  try {
    const data = await api(`/api/market/overview?interval=${encodeURIComponent(state.interval)}`);
    const previousSymbol = state.symbol;
    state.overview = Array.isArray(data) ? data : [];
    if (!state.overview.some((item) => item.symbol === state.symbol)) state.symbol = state.overview[0]?.symbol || state.symbol;
    renderWatchlist();
    if (previousSymbol !== state.symbol || !state.signal) {
      await selectSymbol(state.symbol);
    } else {
      const active = activeOverviewItem();
      if (active) renderSignal(active);
    }
  } catch (error) {
    toast('تعذر الاتصال بمصدر السوق');
  } finally {
    state.overviewLoading = false;
  }
}

async function refreshActive() {
  if (state.activeLoading || !state.symbol) return;
  const requestId = ++state.requestId;
  state.activeLoading = true;
  try {
    const [signal] = await Promise.all([
      api(`/api/signals/${encodeURIComponent(state.symbol)}?interval=${encodeURIComponent(state.interval)}`),
      loadChart(requestId)
    ]);
    if (requestId !== state.requestId) return;
    renderSignal({ ...signal, ticker: activeOverviewItem()?.ticker });
    renderWatchlist();
    $('#last-update').textContent = new Date().toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' });
  } catch (error) {
    // Live websocket remains available even when a refresh request fails.
  } finally {
    if (requestId === state.requestId) state.activeLoading = false;
  }
}

async function loadTrades(status = 'open') {
  try {
    const rows = await api(`/api/trades?status=${status === 'open' ? 'OPEN' : 'CLOSED'}`);
    $('#trades-body').innerHTML = rows.length
      ? rows.map((trade) => `<tr><td>${trade.symbol}</td><td class="${trade.direction === 'LONG' ? 'positive' : 'negative'}">${trade.direction}</td><td>${fmt(trade.entry)}</td><td>${fmt(trade.stop_loss)}</td><td>${fmt(trade.take_profit_1)}</td><td>${trade.status}</td></tr>`).join('')
      : `<tr><td colspan="6" class="neutral">لا توجد صفقات ${status === 'open' ? 'مفتوحة' : 'مغلقة'} بعد</td></tr>`;
  } catch (error) {
    toast('تعذر تحميل سجل الصفقات');
  }
}

function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  state.ws = new WebSocket(`${protocol}://${location.host}/ws`);
  state.ws.onopen = () => { $('#connection-dot').style.background = 'var(--green)'; };
  state.ws.onclose = () => { $('#connection-dot').style.background = 'var(--red)'; setTimeout(connectWS, 3000); };
  state.ws.onerror = () => state.ws.close();
  state.ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (!data.symbol) return;
    const item = state.overview.find((entry) => entry.symbol === data.symbol);
    if (!item) return;
    if (data.type === 'ticker') {
      item.price = data.price;
      item.ticker = data.ticker;
      updateWatchItem(item);
      if (data.symbol === state.symbol) {
        updateLivePrice(data.price, data.ticker?.updated_at);
        $('#active-price').textContent = fmt(data.price);
        $('#active-change').textContent = pct(data.ticker?.change);
        $('#active-change').className = Number(data.ticker?.change || 0) >= 0 ? 'positive' : 'negative';
      }
      return;
    }
    if (data.type !== 'candle' || !data.candle) return;
    item.price = data.ticker?.price ?? data.candle.close;
    item.ticker = data.ticker;
    updateWatchItem(item);
    if (data.symbol === state.symbol) {
      updateLiveChart({ ...data.candle, symbol: data.symbol });
      const ticker = data.ticker || {};
      $('#active-price').textContent = fmt(ticker.price ?? data.candle.close);
      $('#active-change').textContent = pct(ticker.change);
      $('#active-change').className = Number(ticker.change || 0) >= 0 ? 'positive' : 'negative';
    }
  };
}

$('#symbol-search').oninput = renderWatchlist;
$('#mobile-symbol-trigger').onclick = () => setMobileSymbolMenu(!state.symbolMenuOpen);
$('#mobile-symbol-menu').onclick = (event) => {
  const option = event.target.closest('.mobile-symbol-option');
  if (!option) return;
  setMobileSymbolMenu(false);
  selectSymbol(option.dataset.symbol);
};
document.addEventListener('click', (event) => {
  const picker = $('#mobile-symbol-picker');
  if (state.symbolMenuOpen && picker && !picker.contains(event.target)) setMobileSymbolMenu(false);
});
$('#refresh-btn').onclick = () => { loadOverview(); loadTrades(); };
$('#zoom-in').title = 'تكبير الشارت: عرض شموع أقل بتفاصيل أكبر';
$('#zoom-out').title = 'إبعاد الشارت: عرض شموع أكثر';
$('#fit-chart').title = 'ملاءمة كامل البيانات';
$('#zoom-in').onclick = () => state.chart.timeScale().scrollToPosition(5, true);
$('#zoom-out').onclick = () => state.chart.timeScale().scrollToPosition(-5, true);
$('#fit-chart').onclick = () => state.chart.timeScale().fitContent();
$('#add-symbol').onclick = () => toast('يمكن تتبع أي زوج موجود في قائمة SYMBOLS من إعدادات Render');
$('#settings-btn').onclick = () => toast('الإعدادات تحفظ عبر Supabase عند توفير SUPABASE_URL وSUPABASE_KEY');
$('#explain-btn').onclick = () => toast((state.signal?.reasons || []).join(' · ') || 'لا يوجد تفسير متاح');

$$('#timeframes button').forEach((button) => button.onclick = async () => {
  $$('#timeframes button').forEach((element) => element.classList.remove('selected'));
  button.classList.add('selected');
  state.interval = button.dataset.interval;
  await loadOverview();
});

$$('.trade-tabs button').forEach((button) => button.onclick = () => {
  $$('.trade-tabs button').forEach((element) => element.classList.remove('active'));
  button.classList.add('active');
  loadTrades(button.dataset.status);
});

$$('.chart-toolbar input[data-layer]').forEach((input) => input.onchange = () => toast(`طبقة ${input.parentElement.textContent.trim()} ${input.checked ? 'مفعلة' : 'متوقفة'} — ستظهر التفاصيل مع الإشارات القادمة`));
$$('.chart-toolbar .tool').forEach((button) => button.onclick = () => {
  $$('.chart-toolbar .tool').forEach((element) => element.classList.remove('active'));
  button.classList.add('active');
  const lineMode = button.textContent.trim() === 'خط';
  state.candleSeries.applyOptions({ visible: !lineMode });
  state.lineSeries.applyOptions({ visible: lineMode });
});

(async () => {
  initChart();
  connectWS();
  await loadOverview();
  await loadTrades();
  state.refreshTimer = setInterval(() => { refreshActive(); loadTrades(); }, 30000);
  setInterval(loadOverview, 60000);
})();
