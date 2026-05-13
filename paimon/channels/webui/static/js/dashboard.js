/* dashboard 页脚本 — 调用统计 + 柱状图 */
(function () {
  let P = 'day';
  let M = 'tokens';
  const cache = {};
  const BAR_H = 200;
  const WD = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

  const $ = (id) => document.getElementById(id);
  const fN = (n) => (n || 0).toLocaleString();
  const fC = (n) => '$' + (n || 0).toFixed(4);
  const fS = (n) => {
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toFixed(0);
  };
  const esc = (s) => s ? String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : '';

  function renderCards(g) {
    $('cCalls').textContent = fN(g.count);
    const tot = (g.total_input_tokens || 0) + (g.total_output_tokens || 0);
    $('cTokens').textContent = fN(tot);
    $('cTokensSub').textContent = '输入 ' + fN(g.total_input_tokens) + ' / 输出 ' + fN(g.total_output_tokens);
    $('cCost').textContent = fC(g.total_cost_usd);
    const cw = g.total_cache_creation_tokens || 0;
    const cr = g.total_cache_read_tokens || 0;
    const ct = cw + cr;
    $('cCache').textContent = ct > 0 ? ((cr / ct) * 100).toFixed(1) + '%' : '—';
    $('cCacheSub').textContent = '写入 ' + fN(cw) + ' / 命中 ' + fN(cr);
  }

  function renderDetail(detail) {
    const el = $('detailEl');
    el.classList.remove('pm-empty');
    if (!detail || !detail.length) {
      el.innerHTML =
        '<div class="pm-empty"><span class="pm-empty__icon" data-icon="inbox"></span>' +
        '<p class="pm-empty__title">暂无数据</p>' +
        '<p class="pm-empty__desc">还没有 LLM 调用记录。聊一两句话或等下次定时任务跑完，这里会出现统计明细。</p></div>';
      window.pmIcon && window.pmIcon.enhanceAll(el);
      return;
    }
    const rows = detail.map((d) => {
      const t = (d.input_tokens || 0) + (d.output_tokens || 0);
      return '<tr>' +
        '<td>' + esc(d.purpose || '-') + '</td>' +
        '<td style="text-align:right;font-variant-numeric:tabular-nums">' + fN(t) + '</td>' +
        '<td style="text-align:right;font-variant-numeric:tabular-nums">' + fN(d.input_tokens) + '</td>' +
        '<td style="text-align:right;font-variant-numeric:tabular-nums">' + fN(d.output_tokens) + '</td>' +
        '<td style="text-align:right;font-variant-numeric:tabular-nums">' + fN(d.cache_read_tokens || 0) + '</td>' +
        '<td style="text-align:right;font-variant-numeric:tabular-nums">' + fC(d.cost_usd) + '</td>' +
        '<td style="text-align:right;font-variant-numeric:tabular-nums">' + fN(d.count) + '</td>' +
        '</tr>';
    }).join('');
    el.innerHTML = '<table class="pm-table"><thead><tr>' +
      '<th>用途</th>' +
      '<th style="text-align:right">总 Token</th><th style="text-align:right">输入</th>' +
      '<th style="text-align:right">输出</th><th style="text-align:right">缓存命中</th>' +
      '<th style="text-align:right">花费</th><th style="text-align:right">调用次数</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';
  }

  async function loadStats() {
    try {
      const r = await fetch('/api/token_stats');
      const d = await r.json();
      renderCards(d.global);
      renderDetail(d.detail);
    } catch (e) {
      $('detailEl').innerHTML = '<div class="pm-empty"><p class="pm-empty__desc">加载失败</p></div>';
    }
  }

  function bindCtrlGroup(selector, getActive, setActive) {
    document.querySelectorAll(selector).forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll(selector).forEach((b) => b.classList.remove('is-active'));
        btn.classList.add('is-active');
        setActive(btn.dataset[selector.includes('data-p') ? 'p' : 'm']);
      });
    });
  }

  function zeroPoint(period) {
    return { period, input_tokens: 0, output_tokens: 0, cost_usd: 0, count: 0, cache_creation_tokens: 0, cache_read_tokens: 0 };
  }

  function isoWeek(d) {
    // ISO 8601 week: 周一为一周首日；返回 [year, weekNum]
    const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    const day = t.getUTCDay() || 7;
    t.setUTCDate(t.getUTCDate() + 4 - day);
    const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
    const wk = Math.ceil(((t - yearStart) / 86400000 + 1) / 7);
    return [t.getUTCFullYear(), wk];
  }

  function fill(data) {
    const m = {};
    data.forEach((d) => { m[d.period] = d; });
    const now = new Date();
    const out = [];

    if (P === 'hour') {
      for (let h = 0; h < 24; h++) out.push(m[h] || zeroPoint(h));
      return out;
    }
    if (P === 'weekday') {
      for (let w = 0; w < 7; w++) out.push(m[w] || zeroPoint(w));
      return out;
    }
    if (P === 'day') {
      // 最近 14 天，period = YYYY-MM-DD
      for (let i = 13; i >= 0; i--) {
        const dt = new Date(now);
        dt.setDate(now.getDate() - i);
        const key = dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0') + '-' + String(dt.getDate()).padStart(2, '0');
        out.push(m[key] || zeroPoint(key));
      }
      return out;
    }
    if (P === 'week') {
      // 最近 8 周，period = YYYY-Www
      for (let i = 7; i >= 0; i--) {
        const dt = new Date(now);
        dt.setDate(now.getDate() - i * 7);
        const [yr, wk] = isoWeek(dt);
        const key = yr + '-W' + String(wk).padStart(2, '0');
        out.push(m[key] || zeroPoint(key));
      }
      return out;
    }
    if (P === 'month') {
      // 最近 6 月，period = YYYY-MM
      for (let i = 5; i >= 0; i--) {
        const dt = new Date(now.getFullYear(), now.getMonth() - i, 1);
        const key = dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0');
        out.push(m[key] || zeroPoint(key));
      }
      return out;
    }
    return data;
  }

  function lbl(d) {
    if (P === 'hour') return d.period + ':00';
    if (P === 'weekday') return WD[d.period] || d.period;
    const s = String(d.period || '');
    if (P === 'day' && s.length === 10) return s.slice(5);
    return s;
  }

  async function fetchC(p) {
    const el = $('chartArea');
    el.innerHTML = '<span class="pm-spinner pm-spinner--lg"></span>';
    const cnt = p === 'day' ? 14 : p === 'week' ? 8 : p === 'month' ? 6 : 30;
    try {
      const r = await fetch('/api/token_stats/timeline?period=' + p + '&count=' + cnt);
      const d = await r.json();
      cache[p] = d.data || [];
      renderC();
    } catch (e) {
      el.innerHTML = '<div class="pm-empty"><p class="pm-empty__desc">加载失败</p></div>';
    }
  }

  function renderC() {
    const raw = cache[P] || [];
    const el = $('chartArea');
    if (!raw.length) {
      el.innerHTML = '<div class="pm-empty"><p class="pm-empty__desc">所选范围暂无数据</p></div>';
      return;
    }
    const data = fill(raw);
    const isCost = M === 'cost';
    let maxV = 0;
    const items = data.map((d) => {
      const v = isCost ? (d.cost_usd || 0) : ((d.input_tokens || 0) + (d.output_tokens || 0));
      if (v > maxV) maxV = v;
      return { l: lbl(d), v, cost: d.cost_usd || 0, tok: (d.input_tokens || 0) + (d.output_tokens || 0), cnt: d.count || 0 };
    });
    if (maxV <= 0) maxV = 1;
    let yHtml = '';
    for (let i = 4; i >= 0; i--) {
      const yv = maxV * i / 4;
      yHtml += '<span>' + (isCost ? fC(yv) : fS(yv)) + '</span>';
    }
    let barsHtml = '';
    let lblsHtml = '';
    items.forEach((it) => {
      let h = Math.round(it.v / maxV * BAR_H);
      if (it.v > 0 && h < 3) h = 3;
      const cls = isCost ? 'dash-chart-bar is-cost' : 'dash-chart-bar';
      const tip = it.l + '\n' + fN(it.tok) + ' tok\n' + fC(it.cost) + '\n' + it.cnt + '次调用';
      barsHtml += '<div class="dash-chart-col"><div class="' + cls + '" style="height:' + h + 'px"><div class="dash-chart-tip">' + esc(tip) + '</div></div></div>';
      lblsHtml += '<div class="dash-chart-lbl">' + esc(it.l) + '</div>';
    });
    el.innerHTML = '<div class="dash-chart-wrap">' +
      '<div class="dash-chart-y">' + yHtml + '</div>' +
      '<div class="dash-chart-cols" style="height:' + BAR_H + 'px">' + barsHtml + '</div>' +
      '<div class="dash-chart-labels">' + lblsHtml + '</div>' +
      '</div>';
  }

  document.addEventListener('DOMContentLoaded', () => {
    bindCtrlGroup('.pm-btn[data-p]', () => P, (v) => { P = v; cache[P] ? renderC() : fetchC(P); });
    bindCtrlGroup('.pm-btn[data-m]', () => M, (v) => { M = v; renderC(); });

    $('dash-refresh').addEventListener('click', async (e) => {
      await window.pmBtn.runAsync(e.currentTarget, async () => {
        for (const k of Object.keys(cache)) delete cache[k];
        await loadStats();
        await fetchC(P);
      }, { loadingText: '刷新中…' });
    });

    // Tab 切到 chart 时如果未加载则拉数据
    document.addEventListener('pm-tab:change', (e) => {
      if (e.detail.tab.dataset.target === 'dash-chart' && !cache[P]) fetchC(P);
    });

    loadStats();
    fetchC('day');
  });
})();
