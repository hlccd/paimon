/* selfcheck 页脚本 — Quick + Deep 自检历史 + 自动升级 + 回退警示 */
(function () {
  function esc(s) { if (s == null) return ''; return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function fmtTime(ts) {
    if (!ts || ts <= 0) return '-';
    const d = new Date(ts * 1000);
    const pad = (n) => n.toString().padStart(2, '0');
    return (d.getMonth() + 1) + '-' + d.getDate() + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
  }
  function fmtDur(s) {
    if (!s || s < 0) return '-';
    if (s < 1) return (s * 1000).toFixed(0) + 'ms';
    if (s < 60) return s.toFixed(1) + 's';
    const m = Math.floor(s / 60);
    const ss = Math.floor(s % 60);
    return m + 'm' + (ss ? ss + 's' : '');
  }

  // 从 DOM 中读 active tab 决定初始 currentTab（兼容 deep_hidden 模式）
  function getInitialTab() {
    const t = document.querySelector('.tab.active');
    return (t && t.dataset.tab) || 'quick';
  }
  let currentTab = getInitialTab();

  async function loadLatestQuick() {
    const pill = document.getElementById('statusPill');
    try {
      const r = await fetch('/api/selfcheck/quick/latest');
      const data = await r.json();
      if (data && data.run) {
        const o = (data.run.quick_summary || {}).overall || 'unknown';
        const icon = { ok: '✅', degraded: '⚠️', critical: '🚨' }[o] || '❓';
        pill.className = 'status-pill status-' + o;
        pill.textContent = icon + ' ' + o + ' · ' + fmtTime(data.run.triggered_at);
      } else {
        pill.className = 'status-pill';
        pill.textContent = '尚无 Quick 记录';
      }
    } catch (e) {
      pill.className = 'status-pill status-critical';
      pill.textContent = '加载失败';
    }
  }

  async function loadRuns(kind) {
    const el = document.getElementById('tabPanel');
    el.innerHTML = '<div class="empty-state">加载中…</div>';
    try {
      const r = await fetch('/api/selfcheck/runs?kind=' + kind + '&limit=100');
      const data = await r.json();
      const runs = data.runs || [];
      if (!runs.length) {
        el.innerHTML = '<div class="empty-state">暂无 ' + kind + ' 历史</div>';
        return;
      }
      el.innerHTML = kind === 'deep' ? renderDeepTable(runs) : renderQuickTable(runs);
    } catch (e) {
      el.innerHTML = '<div class="empty-state">加载失败: ' + esc(String(e)) + '</div>';
    }
  }

  function fmtProgress(p) {
    if (!p || !Object.keys(p).length) return '';
    const it = p.current_iteration || 0, max = p.max_iter || 0;
    const cc = p.consecutive_clean || 0, ci = p.clean_iter || 0;
    const parts = [];
    if (max > 0) parts.push('iter ' + it + '/' + max);
    if (ci > 0) parts.push('clean ' + cc + '/' + ci);
    if (p.total_candidates != null) parts.push('候选 ' + p.total_candidates);
    return parts.join(' · ');
  }

  function renderDeepTable(runs) {
    const rows = runs.map((r) => {
      const statusIcon = r.status === 'completed' ? '✓' : (r.status === 'running' ? '…' : '✗');
      let p0, p1, p2, p3, total;
      if (r.status === 'running' && r.progress && Object.keys(r.progress).length) {
        p0 = r.progress.p0 || 0; p1 = r.progress.p1 || 0;
        p2 = r.progress.p2 || 0; p3 = r.progress.p3 || 0;
        total = r.progress.total_confirmed != null ? r.progress.total_confirmed : (r.progress.total_candidates || 0);
      } else {
        p0 = r.p0_count; p1 = r.p1_count; p2 = r.p2_count; p3 = r.p3_count;
        total = r.findings_total;
      }
      const sevCells = [
        '<td class="num sev-p0">' + p0 + '</td>',
        '<td class="num sev-p1">' + p1 + '</td>',
        '<td class="num sev-p2">' + p2 + '</td>',
        '<td class="num sev-p3">' + p3 + '</td>',
      ].join('');
      let statusCell = statusIcon + ' ' + esc(r.status);
      if (r.status === 'running') {
        const prog = fmtProgress(r.progress);
        if (prog) statusCell += ' <span style="color:var(--pm-text-muted);font-size:11px">· ' + esc(prog) + '</span>';
      }
      if (r.error) {
        statusCell += ' <span style="color:var(--pm-danger)" title="' + esc(r.error) + '">!</span>';
      }
      const actions = r.status === 'completed'
        ? '<button class="mini-btn" onclick="viewDeep(\'' + r.id + '\')">查看</button>' +
          '<button class="mini-btn danger" onclick="deleteRun(\'' + r.id + '\')">删除</button>'
        : (r.status === 'running'
          ? '<button class="mini-btn" onclick="viewDeep(\'' + r.id + '\')">详情</button>'
          : '<button class="mini-btn danger" onclick="deleteRun(\'' + r.id + '\')">删除</button>');
      return '<tr>' +
        '<td>' + fmtTime(r.triggered_at) + '</td>' +
        '<td class="id">' + esc(r.id.substring(0, 8)) + '</td>' +
        '<td>' + esc(r.triggered_by) + '</td>' +
        '<td>' + fmtDur(r.duration_seconds) + '</td>' +
        sevCells +
        '<td class="num">' + total + '</td>' +
        '<td>' + statusCell + '</td>' +
        '<td class="actions">' + actions + '</td>' +
        '</tr>';
    }).join('');
    return '<div class="table-wrap"><table class="runs">' +
      '<thead><tr>' +
      '<th>时间</th><th>ID</th><th>触发</th><th>耗时</th>' +
      '<th>P0</th><th>P1</th><th>P2</th><th>P3</th>' +
      '<th>总数</th><th>状态 / 进度</th><th></th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function renderQuickTable(runs) {
    const rows = runs.map((r) => {
      const overall = (r.quick_summary || {}).overall || '?';
      const compList = ((r.quick_summary || {}).components || []);
      const compSummary = compList.map((c) => {
        const icon = { ok: '✓', degraded: '△', critical: '✗' }[c.status] || '?';
        return '<span class="sev-' + (c.status === 'critical' ? 'p0' : c.status === 'degraded' ? 'p1' : 'p3') + '">' + icon + ' ' + esc(c.name) + '</span>';
      }).join(' · ');
      const overallCls = 'status-' + overall;
      return '<tr>' +
        '<td>' + fmtTime(r.triggered_at) + '</td>' +
        '<td class="id">' + esc(r.id.substring(0, 8)) + '</td>' +
        '<td class="' + overallCls + '">' + esc(overall) + '</td>' +
        '<td>' + fmtDur(r.duration_seconds) + '</td>' +
        '<td>' + compSummary + '</td>' +
        '<td class="actions">' +
        '<button class="mini-btn" onclick="viewQuick(\'' + r.id + '\')">查看</button>' +
        '<button class="mini-btn danger" onclick="deleteRun(\'' + r.id + '\')">删除</button>' +
        '</td></tr>';
    }).join('');
    return '<div class="table-wrap"><table class="runs">' +
      '<thead><tr><th>时间</th><th>ID</th><th>整体</th><th>耗时</th><th>组件</th><th></th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div>';
  }

  let _modalRefreshTimer = null;
  function _clearModalRefresh() {
    if (_modalRefreshTimer) {
      clearInterval(_modalRefreshTimer);
      _modalRefreshTimer = null;
    }
  }

  async function _loadDeepOnce(runId) {
    const metaR = await fetch('/api/selfcheck/runs/' + runId);
    const meta = (await metaR.json()).run;
    if (!meta) return null;
    if (meta.status === 'running') {
      renderDeepProgress(meta);
      return 'running';
    }
    _clearModalRefresh();
    const findingsR = await fetch('/api/selfcheck/runs/' + runId + '/findings');
    const findings = (await findingsR.json()).findings || [];
    renderDeepDetail(runId, meta, findings);
    return meta.status;
  }

  window.viewDeep = async function (runId) {
    _clearModalRefresh();
    openModal('Deep 报告 · ' + runId, '<div class="empty-state">加载中…</div>');
    try {
      const st = await _loadDeepOnce(runId);
      if (st === 'running') {
        _modalRefreshTimer = setInterval(() => {
          if (!document.getElementById('modal').classList.contains('show')) {
            _clearModalRefresh();
            return;
          }
          _loadDeepOnce(runId).catch((e) => console.warn('Modal 刷新失败', e));
        }, 5000);
      }
    } catch (e) {
      document.getElementById('modalBody').innerHTML = '<div class="empty-state">加载失败</div>';
    }
  };

  function renderDeepProgress(meta) {
    const p = meta.progress || {};
    const has = Object.keys(p).length > 0;
    const elapsed = (Date.now() / 1000 - meta.triggered_at);
    let iterBar = '';
    if (p.max_iter > 0) {
      const pct = Math.min(100, Math.round((p.current_iteration || 0) / p.max_iter * 100));
      iterBar = '<div style="background:var(--pm-bg-hover);height:8px;border-radius:4px;overflow:hidden;margin-top:4px">' +
        '<div style="background:var(--pm-primary);height:100%;width:' + pct + '%;transition:width .3s"></div></div>';
    }
    let cleanBar = '';
    if (p.clean_iter > 0) {
      const cpct = Math.min(100, Math.round((p.consecutive_clean || 0) / p.clean_iter * 100));
      cleanBar = '<div style="background:var(--pm-bg-hover);height:8px;border-radius:4px;overflow:hidden;margin-top:4px">' +
        '<div style="background:var(--pm-success);height:100%;width:' + cpct + '%;transition:width .3s"></div></div>';
    }
    let body =
      '<div class="modal-meta">' +
      '<div class="meta-item"><div class="meta-label">开始时间</div><div class="meta-value">' + fmtTime(meta.triggered_at) + '</div></div>' +
      '<div class="meta-item"><div class="meta-label">已进行</div><div class="meta-value">' + fmtDur(elapsed) + '</div></div>' +
      '<div class="meta-item"><div class="meta-label">触发</div><div class="meta-value">' + esc(meta.triggered_by) + '</div></div>' +
      '<div class="meta-item"><div class="meta-label">参数</div><div class="meta-value">' + esc(meta.check_args) + '</div></div>' +
      '</div>';
    if (!has) {
      body += '<div class="empty-state">等 check skill 写第一份 state.json（通常 10~30 秒）…</div>';
    } else {
      body +=
        '<div class="modal-meta">' +
        '<div class="meta-item"><div class="meta-label">大轮次</div>' +
        '<div class="meta-value">' + (p.current_iteration || 0) + ' / ' + (p.max_iter || '?') + '</div>' + iterBar + '</div>' +
        '<div class="meta-item"><div class="meta-label">连续 clean</div>' +
        '<div class="meta-value">' + (p.consecutive_clean || 0) + ' / ' + (p.clean_iter || '?') + '</div>' + cleanBar + '</div>' +
        '<div class="meta-item"><div class="meta-label">候选 / 确认</div>' +
        '<div class="meta-value">' + (p.total_candidates || 0) + ' / ' + (p.total_confirmed || 0) + '</div></div>' +
        '<div class="meta-item"><div class="meta-label">发现 / 验证 轮次</div>' +
        '<div class="meta-value">' + (p.discovery_rounds || '?') + ' / ' + (p.validation_rounds || '?') + '</div></div>' +
        '</div>' +
        '<div class="sev-bar">' +
        '<div class="sev-chip"><span class="label">P0</span><span class="sev-p0">' + (p.p0 || 0) + '</span></div>' +
        '<div class="sev-chip"><span class="label">P1</span><span class="sev-p1">' + (p.p1 || 0) + '</span></div>' +
        '<div class="sev-chip"><span class="label">P2</span><span class="sev-p2">' + (p.p2 || 0) + '</span></div>' +
        '<div class="sev-chip"><span class="label">P3</span><span class="sev-p3">' + (p.p3 || 0) + '</span></div>' +
        '</div>';
      const mods = p.modules_processed || [];
      if (mods.length) {
        body += '<div style="margin-top:12px;padding:10px;background:var(--pm-bg-subtle);border-radius:6px">' +
          '<div class="meta-label">已扫 module (' + mods.length + ')</div>' +
          '<div style="margin-top:4px;color:var(--pm-text-secondary);font-size:13px">' + mods.map(esc).join(', ') + '</div>' +
          '</div>';
      }
      if (p.polled_at) {
        body += '<div style="margin-top:10px;color:var(--pm-text-muted);font-size:11px">' +
          '进度快照时间: ' + fmtTime(p.polled_at) + '（watcher 每 5 秒轮询一次 state.json）</div>';
      }
    }
    body += '<div style="margin-top:16px;text-align:center;color:var(--pm-text-muted);font-size:12px">' +
      'Modal 每 5 秒自动刷新；自检完成后会自动切换到最终详情视图</div>';
    document.getElementById('modalBody').innerHTML = body;
  }

  function renderDeepDetail(runId, meta, findings) {
    const sev = { P0: meta.p0_count, P1: meta.p1_count, P2: meta.p2_count, P3: meta.p3_count };
    const metaHtml =
      '<div class="modal-meta">' +
      '<div class="meta-item"><div class="meta-label">时间</div><div class="meta-value">' + fmtTime(meta.triggered_at) + '</div></div>' +
      '<div class="meta-item"><div class="meta-label">触发</div><div class="meta-value">' + esc(meta.triggered_by) + '</div></div>' +
      '<div class="meta-item"><div class="meta-label">耗时</div><div class="meta-value">' + fmtDur(meta.duration_seconds) + '</div></div>' +
      '<div class="meta-item"><div class="meta-label">参数</div><div class="meta-value">' + esc(meta.check_args) + '</div></div>' +
      '<div class="meta-item"><div class="meta-label">总数</div><div class="meta-value">' + meta.findings_total + '</div></div>' +
      '<div class="meta-item"><div class="meta-label">状态</div><div class="meta-value">' + esc(meta.status) + (meta.error ? (' (' + esc(meta.error) + ')') : '') + '</div></div>' +
      '</div>' +
      '<div class="sev-bar">' +
      Object.keys(sev).map((k) => {
        const cls = { P0: 'sev-p0', P1: 'sev-p1', P2: 'sev-p2', P3: 'sev-p3' }[k];
        return '<div class="sev-chip"><span class="label">' + k + '</span><span class="' + cls + '">' + sev[k] + '</span></div>';
      }).join('') +
      '</div>' +
      '<div class="findings-filter">' +
      '<select id="filterSev"><option value="">全部严重度</option><option value="P0">仅 P0</option><option value="P1">仅 P1</option><option value="P2">仅 P2</option><option value="P3">仅 P3</option></select>' +
      '<input id="filterFile" placeholder="文件路径包含..."/>' +
      '<input id="filterModule" placeholder="模块包含..."/>' +
      '<button class="btn" onclick="downloadReport(\'' + runId + '\')">下载 report.md</button>' +
      '</div>' +
      '<div class="findings-list" id="findingsList"></div>';
    document.getElementById('modalBody').innerHTML = metaHtml;

    function renderFindings() {
      const fs = document.getElementById('filterSev').value;
      const ff = (document.getElementById('filterFile').value || '').toLowerCase();
      const fm = (document.getElementById('filterModule').value || '').toLowerCase();
      const filtered = findings.filter((f) => {
        const s = (f.severity || 'P2').toUpperCase();
        if (fs && s !== fs) return false;
        if (ff && !((f.file || '').toLowerCase().indexOf(ff) >= 0)) return false;
        if (fm && !((f.module || '').toLowerCase().indexOf(fm) >= 0)) return false;
        return true;
      });
      const list = document.getElementById('findingsList');
      if (!filtered.length) {
        list.innerHTML = '<div class="empty-state">无匹配 findings</div>';
        return;
      }
      list.innerHTML = filtered.map((f) => {
        const sev = (f.severity || 'P2').toUpperCase();
        const loc = f.file ? (esc(f.file) + (f.line ? ':' + f.line : '')) : '';
        const icon = { P0: '🔴', P1: '🟠', P2: '🔵', P3: '⚪' }[sev] || '•';
        return '<div class="finding ' + sev.toLowerCase() + '">' +
          '<div class="finding-head">' +
          '<span class="sev-' + sev.toLowerCase() + '">' + icon + ' ' + sev + '</span>' +
          (loc ? '<span class="finding-loc">' + loc + '</span>' : '') +
          (f.module ? '<span class="finding-module">[' + esc(f.module) + ']</span>' : '') +
          '</div>' +
          '<div class="finding-desc">' + esc(f.description || '') + '</div>' +
          (f.evidence ? '<div class="finding-evidence">' + esc(f.evidence) + '</div>' : '') +
          '</div>';
      }).join('');
    }
    document.getElementById('filterSev').onchange = renderFindings;
    document.getElementById('filterFile').oninput = renderFindings;
    document.getElementById('filterModule').oninput = renderFindings;
    renderFindings();
  }

  window.viewQuick = async function (runId) {
    openModal('Quick 快照 · ' + runId, '<div class="empty-state">加载中…</div>');
    try {
      const [metaR, snapR] = await Promise.all([
        fetch('/api/selfcheck/runs/' + runId),
        fetch('/api/selfcheck/runs/' + runId + '/quick'),
      ]);
      const meta = (await metaR.json()).run;
      const snap = (await snapR.json()).snapshot || {};
      renderQuickDetail(meta, snap);
    } catch (e) {
      document.getElementById('modalBody').innerHTML = '<div class="empty-state">加载失败</div>';
    }
  };

  function renderQuickDetail(meta, snap) {
    const overall = snap.overall || meta.quick_summary && meta.quick_summary.overall || '?';
    const comps = snap.components || [];
    const head =
      '<div class="modal-meta">' +
      '<div class="meta-item"><div class="meta-label">时间</div><div class="meta-value">' + fmtTime(meta.triggered_at) + '</div></div>' +
      '<div class="meta-item"><div class="meta-label">整体</div><div class="meta-value status-' + overall + '">' + esc(overall) + '</div></div>' +
      '<div class="meta-item"><div class="meta-label">耗时</div><div class="meta-value">' + fmtDur(meta.duration_seconds) + '</div></div>' +
      '<div class="meta-item"><div class="meta-label">触发</div><div class="meta-value">' + esc(meta.triggered_by) + '</div></div>' +
      '</div>';
    const compsHtml = '<div class="quick-snapshot"><div class="comp-grid">' +
      comps.map((c) => {
        const details = c.details ? JSON.stringify(c.details, null, 2) : '';
        return '<div class="comp-card ' + esc(c.status || 'ok') + '">' +
          '<div class="comp-name">' + esc(c.name) + ' <span class="comp-latency">' + (c.latency_ms || 0).toFixed(1) + 'ms</span></div>' +
          (c.error ? '<div style="color:var(--pm-danger);font-size:12px;margin-top:4px">' + esc(c.error) + '</div>' : '') +
          (details ? '<div class="comp-details">' + esc(details) + '</div>' : '') +
          '</div>';
      }).join('') +
      '</div></div>';
    const warns = (snap.warnings || []).length
      ? '<div style="margin-top:16px;padding:10px;background:var(--pm-bg-subtle);border-radius:6px"><strong>⚠️ 告警</strong><ul style="margin-top:6px;padding-left:20px">' +
        (snap.warnings || []).map((w) => '<li>' + esc(w) + '</li>').join('') +
        '</ul></div>'
      : '';
    document.getElementById('modalBody').innerHTML = head + warns + compsHtml;
  }

  window.downloadReport = function (runId) {
    window.open('/api/selfcheck/runs/' + runId + '/report', '_blank');
  };

  window.deleteRun = async function (runId) {
    const ok = await window.pmModal.confirm({
      title: '删除 run',
      message: '确认删除 run=' + runId.substring(0, 8) + '？blob 文件会一并删除。',
      confirmText: '删除',
      danger: true,
    });
    if (!ok) return;
    const r = await fetch('/api/selfcheck/runs/' + runId, { method: 'DELETE' });
    if (r.ok) { loadRuns(currentTab); loadLatestQuick(); window.pmToast.success('已删除'); }
    else window.pmToast.error('删除失败');
  };

  function openModal(title, bodyHtml) {
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('modalBody').innerHTML = bodyHtml;
    document.getElementById('modal').classList.add('show');
  }
  window.closeModal = function () {
    _clearModalRefresh();
    document.getElementById('modal').classList.remove('show');
  };

  // ── 升级 / 重启 / 回退 ─────────
  let _upgradeChecking = false;
  let _upgradeData = null;

  function escapeHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // 仅读本地 HEAD，秒回 —— 进页面用这个，避免 git fetch 走网络阻塞 UX
  async function loadUpgradeLocal() {
    const bar = document.getElementById('upgradeBar');
    const headEl = document.getElementById('upgradeHead');
    const behindEl = document.getElementById('upgradeBehind');
    const btnApply = document.getElementById('btnUpgradeApply');
    const commitsEl = document.getElementById('upgradeCommits');
    try {
      const r = await fetch('/api/selfcheck/upgrade/local');
      const d = await r.json();
      if (!d.ok) {
        headEl.textContent = '读取失败';
        return;
      }
      let sub = d.head_subject || '';
      if (sub.length > 70) sub = sub.substring(0, 70) + '…';
      headEl.textContent = sub
        ? '当前: ' + sub + ' (' + d.head_short + ')'
        : '当前 ' + d.head_short;
      behindEl.textContent = '· 点「检查更新」查看远程';
      behindEl.className = '';
      bar.classList.remove('has-update');
      btnApply.style.display = 'none';
      commitsEl.style.display = 'none';
    } catch (e) {
      // 静默：本地 git 应该不会失败
    }
  }

  // 主动 git fetch 检查远程是否有更新（5-30s 网络 IO，仅按钮触发）
  async function loadUpgradeStatus() {
    if (_upgradeChecking) return;
    _upgradeChecking = true;
    const bar = document.getElementById('upgradeBar');
    const headEl = document.getElementById('upgradeHead');
    const behindEl = document.getElementById('upgradeBehind');
    const btnApply = document.getElementById('btnUpgradeApply');
    const commitsEl = document.getElementById('upgradeCommits');
    try {
      const r = await fetch('/api/selfcheck/upgrade/check');
      const d = await r.json();
      if (!d.ok) {
        headEl.textContent = '检查失败';
        behindEl.textContent = '· ' + (d.error || '');
        behindEl.className = '';
        bar.classList.remove('has-update');
        btnApply.style.display = 'none';
        commitsEl.style.display = 'none';
        return;
      }
      _upgradeData = d;
      let sub = d.head_subject || '';
      if (sub.length > 70) sub = sub.substring(0, 70) + '…';
      headEl.textContent = sub
        ? '当前: ' + sub + ' (' + d.head_short + ')'
        : '当前 ' + d.head_short;
      if (d.behind > 0) {
        behindEl.textContent = '· 远程领先 ' + d.behind + ' commits';
        behindEl.className = 'has-update';
        bar.classList.add('has-update');
        btnApply.style.display = '';
        let html = '<div style="margin-bottom:6px;color:var(--pm-primary)">📋 待拉取的 commits：</div>';
        d.commits.forEach((c) => {
          html += '<div class="upgrade-commit">' +
            '<span class="h">' + c.hash + '</span> ' +
            escapeHtml(c.subject) +
            '<span class="a">(' + c.age + ')</span>' +
            '</div>';
        });
        commitsEl.innerHTML = html;
        commitsEl.style.display = '';
      } else {
        behindEl.textContent = '· 已是最新';
        behindEl.className = '';
        bar.classList.remove('has-update');
        btnApply.style.display = 'none';
        commitsEl.style.display = 'none';
      }
    } catch (e) {
      headEl.textContent = '检查失败';
      behindEl.textContent = '· ' + e.message;
    } finally {
      _upgradeChecking = false;
    }
  }

  function showToast(msg, kind) {
    let t = document.getElementById('upgradeToast');
    if (t) t.remove();
    t = document.createElement('div');
    t.id = 'upgradeToast';
    t.className = 'upgrade-toast ' + (kind || 'info');
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => { if (t.parentNode) t.remove(); }, 3000);
  }

  async function loadRollbackStatus() {
    const el = document.getElementById('rollbackWarning');
    try {
      const r = await fetch('/api/selfcheck/upgrade/rollback_status');
      const d = await r.json();
      if (!d || !d.has_rollback) { el.style.display = 'none'; return; }
      const d2 = new Date((d.ts || 0) * 1000);
      const pad = (n) => n.toString().padStart(2, '0');
      const when = (d2.getMonth() + 1) + '-' + d2.getDate() + ' ' + pad(d2.getHours()) + ':' + pad(d2.getMinutes());
      const before = (d.before || '').substring(0, 8) || '?';
      const after = (d.after || '').substring(0, 8) || '?';
      const isManual = d.kind === 'NEEDS_MANUAL';
      let title, meta;
      if (isManual) {
        el.classList.add('needs-manual');
        title = '🚨 watchdog 回退失败 — 需要人工介入';
        meta = 'HEAD 已等于 last_good_commit (<code>' + before + '</code>)，回退无效。' +
          '可能 last_good 本身有问题。请 ssh 上去 <code>git log</code> 选更早稳定 commit 手动 reset。' +
          '<br>失败次数: ' + d.fail_count + ' · 时间: ' + when;
      } else {
        el.classList.remove('needs-manual');
        title = '⚠ watchdog 已自动回退';
        meta = '从 <code>' + before + '</code> 回退到 <code>' + after + '</code>（last_good_commit）' +
          '<br>失败次数: ' + d.fail_count + ' · 触发时间: ' + when;
      }
      el.innerHTML = '<div class="rb-content">' +
        '<div class="rb-title">' + title + '</div>' +
        '<div class="rb-meta">' + meta + '</div>' +
        '</div>' +
        '<div class="rb-actions">' +
        '<button class="btn" onclick="ackRollback()">我知道了</button>' +
        '</div>';
      el.style.display = '';
    } catch (e) {
      el.style.display = 'none';
    }
  }

  window.ackRollback = async function () {
    try {
      const r = await fetch('/api/selfcheck/upgrade/rollback_ack', { method: 'POST' });
      const d = await r.json();
      if (d.ok) {
        document.getElementById('rollbackWarning').style.display = 'none';
        showToast('✅ 警示条已消除', 'success');
      } else {
        showToast('❌ 操作失败：' + (d.error || '未知'), 'error');
      }
    } catch (e) {
      showToast('❌ 请求失败', 'error');
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    function activateTab(t) {
      document.querySelectorAll('.tab').forEach((x) => {
        x.classList.remove('active');
        x.setAttribute('aria-selected', 'false');
      });
      t.classList.add('active');
      t.setAttribute('aria-selected', 'true');
      currentTab = t.getAttribute('data-tab');
      loadRuns(currentTab);
    }
    document.querySelectorAll('.tab').forEach((t) => {
      t.addEventListener('click', () => activateTab(t));
      t.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activateTab(t); }
      });
    });

    const btnQuick = document.getElementById('btnQuick');
    if (btnQuick) {
      btnQuick.addEventListener('click', async function () {
        this.disabled = true;
        this.textContent = 'Quick 运行中…';
        try {
          const r = await fetch('/api/selfcheck/quick/run', { method: 'POST' });
          await r.json();
          await loadLatestQuick();
          if (currentTab === 'quick') loadRuns('quick');
        } finally {
          this.disabled = false;
          this.textContent = '⚡ 跑 Quick';
        }
      });
    }

    const btnDeep = document.getElementById('btnDeep');
    if (btnDeep) {
      btnDeep.addEventListener('click', async function () {
        this.disabled = true;
        this.textContent = 'Deep 启动中…';
        try {
          const r = await fetch('/api/selfcheck/deep/run', { method: 'POST' });
          const data = await r.json();
          if (data.started) {
            window.pmToast.success('Deep 已启动 run=' + data.run_id.substring(0, 8) + '，后台跑约 5-15 分钟，完成自动刷新');
            setTimeout(() => loadRuns('deep'), 2000);
          } else {
            window.pmToast.warning('未启动: ' + data.reason);
          }
        } catch (e) {
          window.pmToast.error('调用失败');
        } finally {
          this.disabled = false;
          this.textContent = '🔬 跑 Deep';
        }
      });
    }

    const btnUpgradeCheck = document.getElementById('btnUpgradeCheck');
    if (btnUpgradeCheck) {
      btnUpgradeCheck.addEventListener('click', async function () {
        if (this.disabled) return;
        const origText = this.textContent;
        this.disabled = true;
        this.textContent = '⏳ 检查中…';
        try {
          await loadUpgradeStatus();
          if (_upgradeData && _upgradeData.ok) {
            if (_upgradeData.behind > 0) {
              showToast('🔄 发现 ' + _upgradeData.behind + ' 个新 commit，可点击「拉取并重启」升级', 'info');
            } else {
              showToast('✅ 已是最新 (' + _upgradeData.head_short + ')', 'success');
            }
          } else {
            showToast('❌ 检查失败', 'error');
          }
        } finally {
          this.disabled = false;
          this.textContent = origText;
        }
      });
    }

    const btnUpgradeApply = document.getElementById('btnUpgradeApply');
    if (btnUpgradeApply) {
      btnUpgradeApply.addEventListener('click', async function () {
        if (!_upgradeData || _upgradeData.behind <= 0) {
          window.pmToast.warning('当前没有可升级的内容，请先点「检查更新」');
          return;
        }
        const ok = await window.pmModal.confirm({
          title: '拉取并重启',
          message: '将拉取 ' + _upgradeData.behind + ' 个 commit 并重启进程。前端会暂时无响应（5-10 秒），重启后页面会自动刷新。',
          confirmText: '拉取并重启',
        });
        if (!ok) return;

        this.disabled = true;
        this.textContent = '升级中…';
        try {
          const r = await fetch('/api/selfcheck/upgrade/trigger', {
            method: 'POST',
            headers: { 'X-Confirm': 'yes' },
          });
          const d = await r.json();
          if (!d.ok) {
            window.pmToast.error('升级失败：' + (d.error || '未知'));
            this.disabled = false;
            this.textContent = '⬇️ 拉取并重启';
            return;
          }
          let html = '<div class="upgrade-status success">' +
            '✅ ' + escapeHtml(d.message || '已触发升级') + '<br>' +
            '<small>新 HEAD: ' + escapeHtml(d.new_head_short || '?') + '</small>';
          if (d.deps_warning) html += '<br><br>⚠️ ' + escapeHtml(d.deps_warning);
          html += '</div>';
          document.getElementById('upgradeCommits').innerHTML = html;
          document.getElementById('upgradeCommits').style.display = '';
          setTimeout(() => location.reload(), 10000);
        } catch (e) {
          window.pmToast.error('请求失败：' + e.message);
          this.disabled = false;
          this.textContent = '⬇️ 拉取并重启';
        }
      });
    }

    const btnRestart = document.getElementById('btnRestart');
    if (btnRestart) {
      btnRestart.addEventListener('click', async function () {
        const ok = await window.pmModal.confirm({
          title: '重启 paimon',
          message: '用当前代码重启（不拉取更新）。前端会暂时无响应（5-10 秒），重启后页面会自动刷新。',
          confirmText: '重启',
        });
        if (!ok) return;
        this.disabled = true;
        this.textContent = '重启中…';
        try {
          const r = await fetch('/api/selfcheck/restart', {
            method: 'POST',
            headers: { 'X-Confirm': 'yes' },
          });
          const d = await r.json();
          if (!d.ok) {
            alert('重启失败：' + (d.error || '未知'));
            this.disabled = false;
            this.textContent = '♻️ 重启';
            return;
          }
          const html = '<div class="upgrade-status success">' +
            '✅ ' + escapeHtml(d.message || '已触发重启') +
            '</div>';
          document.getElementById('upgradeCommits').innerHTML = html;
          document.getElementById('upgradeCommits').style.display = '';
          setTimeout(() => location.reload(), 10000);
        } catch (e) {
          window.pmToast.error('请求失败：' + e.message);
          this.disabled = false;
          this.textContent = '♻️ 重启';
        }
      });
    }

    const modal = document.getElementById('modal');
    if (modal) {
      modal.addEventListener('click', function (e) {
        if (e.target === this) closeModal();
      });
    }

    loadLatestQuick();
    loadRuns(currentTab);
    loadUpgradeLocal();   // 进页面只读本地 HEAD，不 fetch 远端（避免 30s 卡顿）
    loadRollbackStatus();
    setInterval(() => {
      loadLatestQuick();
      loadRuns(currentTab);
    }, 30000);
    setInterval(() => {
      loadRollbackStatus();
    }, 300000);

    // ESC 关 modal
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const m = document.getElementById('modal');
        if (m && m.classList.contains('show')) closeModal();
      }
    });
  });
})();
