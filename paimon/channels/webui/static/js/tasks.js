/* tasks 页脚本 — 拉取定时任务 + 系统任务，渲染卡片网格 + 折叠分组 */
(function () {
  function esc(s) { return s ? String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : ''; }
  function fmtTime(ts) {
    if (!ts || ts <= 0) return '-';
    const d = new Date(ts * 1000);
    return (d.getMonth() + 1) + '-' + d.getDate() + ' ' + d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
  }
  function fmtTrigger(t) {
    if (t.trigger_type === 'once') return '一次性';
    if (t.trigger_type === 'interval') {
      const s = (t.trigger_value && t.trigger_value.seconds) || 0;
      if (s >= 3600) return '每' + Math.round(s / 3600) + '小时';
      if (s >= 60) return '每' + Math.round(s / 60) + '分钟';
      return '每' + s + '秒';
    }
    if (t.trigger_type === 'cron') return fmtCronZh(t.trigger_value && t.trigger_value.expr || '');
    return t.trigger_type;
  }
  function fmtCronZh(expr) {
    if (!expr) return 'cron: ?';
    const p = String(expr).trim().split(/\s+/);
    if (p.length !== 5) return 'cron: ' + expr;
    const [m, h, dom, mon, dow] = p;
    if (!/^\d+$/.test(m) || !/^\d+$/.test(h)) return 'cron: ' + expr;
    const time = h.padStart(2, '0') + ':' + m.padStart(2, '0');
    if (dom === '*' && mon === '*' && dow === '*') return '每日 ' + time;
    if (dom === '*' && mon === '*' && dow === '1-5') return '每工作日 ' + time;
    const DOW = ['日', '一', '二', '三', '四', '五', '六'];
    if (dom === '*' && mon === '*' && /^[0-6]$/.test(dow)) return '每周' + DOW[parseInt(dow)] + ' ' + time;
    if (/^\d+$/.test(dom) && mon === '*' && dow === '*') return '每月 ' + dom + ' 号 ' + time;
    return 'cron: ' + expr;
  }

  window.switchTab = function (key, btn) {
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
    document.getElementById(key).classList.add('active');
    btn.classList.add('active');
    if ((key === 'scheduled' || key === 'system') && !window._tasksLoaded) loadTasks();
  };

  function renderTaskCard(t) {
    const src = t.source || null;
    const cls = 'task-card' + (t.enabled ? '' : ' disabled') + (src ? ' internal clickable' : '');
    const badge = t.enabled
      ? '<span class="task-badge badge-enabled">运行中</span>'
      : '<span class="task-badge badge-disabled">已停止</span>';
    const err = t.last_error
      ? '<div class="task-error">' + esc(t.last_error.substring(0, 100)) +
        (t.consecutive_failures ? ' (连续' + t.consecutive_failures + '次)' : '') + '</div>'
      : '';

    let headLeft = '<span class="task-id">' + esc(t.id) + '</span>';
    let displayText = '';
    let sourceHint = '';
    if (src) {
      const chipCls = 'task-source-chip' + (src.task_type && !src.jump_url ? ' unknown' : '');
      headLeft = '<span class="' + chipCls + '">' + esc(src.label || '?') + '</span>' + headLeft;
      displayText = esc(src.description || src.task_type || '-');
      if (src.jump_url) {
        sourceHint = '<div class="task-source-hint">💡 此任务由 <a href="' + esc(src.jump_url) + '">' +
          esc(src.manager_panel || src.jump_url) + '</a> 面板创建，启停/删除请到对应面板管理</div>';
      } else if (src.task_type) {
        sourceHint = '<div class="task-source-hint">⚠️ 未知任务类型 ' + esc(src.task_type) + '（对应 archon 可能未注册或已移除）</div>';
      }
    } else {
      displayText = esc(t.prompt);
    }

    const onClick = src && src.jump_url ? ' onclick="window.location=\'' + esc(src.jump_url) + '\'"' : '';

    return '<div class="' + cls + '"' + onClick + '>' +
      '<div class="task-header"><span>' + headLeft + '</span>' + badge + '</div>' +
      '<div class="task-prompt">' + displayText + '</div>' +
      '<div class="task-meta">' +
      '<span class="task-meta-item">' + fmtTrigger(t) + '</span>' +
      '<span class="task-meta-item">下次: ' + fmtTime(t.next_run_at) + '</span>' +
      '<span class="task-meta-item">上次: ' + fmtTime(t.last_run_at) + '</span>' +
      '<span class="task-meta-item">创建: ' + fmtTime(t.created_at) + '</span>' +
      '</div>' + err + sourceHint + '</div>';
  }

  function groupKeyOf(t) {
    if (t.trigger_type === 'cron') {
      return 'cron:' + (t.trigger_value && t.trigger_value.expr || '?');
    }
    return 'tid:' + t.id;
  }
  function renderSingleRow(t, timeLabel) {
    const src = t.source || {};
    const enabledCls = t.enabled ? '' : ' disabled';
    const jump = src.jump_url ? ' onclick="window.location=\'' + esc(src.jump_url) + '\'"' : '';
    const stopBadge = t.enabled ? '' : '<span class="task-badge badge-disabled">已停止</span>';
    const errBadge = t.last_error
      ? '<span class="task-badge badge-failed" title="' + esc(t.last_error.substring(0, 200)) + '">⚠ 失败</span>'
      : '';
    return '<div class="time-single' + enabledCls + '"' + jump + '>' +
      '<span class="time-single-time">' + esc(timeLabel) + '</span>' +
      '<span class="time-single-desc">' + esc(src.description || src.task_type || '-') + '</span>' +
      errBadge + stopBadge + '</div>';
  }
  function renderTimeGroup(g) {
    let preview = g.tasks.slice(0, 3).map((t) => (t.source && t.source.description) || '?').join(' · ');
    if (g.tasks.length > 3) preview += ' …';
    const body = g.tasks.map(renderTaskCard).join('');
    return '<div class="time-group">' +
      '<div class="time-group-head" role="button" tabindex="0" aria-expanded="false" onclick="toggleTimeGroup(this)" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){event.preventDefault();toggleTimeGroup(this)}">' +
      '<span class="time-group-arrow" aria-hidden="true">▶</span>' +
      '<span class="time-group-time">' + esc(g.label) + '</span>' +
      '<span class="time-group-count">' + g.tasks.length + ' 项</span>' +
      '<span class="time-group-preview">' + esc(preview) + '</span>' +
      '</div>' +
      '<div class="time-group-body">' + body + '</div>' +
      '</div>';
  }
  function renderSystemGrid(sysTasks, archons) {
    const byArchon = {};
    sysTasks.forEach((t) => {
      const ak = (t.source && t.source.archon) || '';
      const an = (t.source && t.source.archon_name) || '其他';
      if (!byArchon[ak]) byArchon[ak] = { key: ak, name: an, groups: {}, order: [] };
      const gk = groupKeyOf(t);
      if (!byArchon[ak].groups[gk]) {
        const label = t.trigger_type === 'cron'
          ? fmtCronZh(t.trigger_value && t.trigger_value.expr || '')
          : fmtTrigger(t);
        byArchon[ak].groups[gk] = { key: gk, label, tasks: [] };
        byArchon[ak].order.push(gk);
      }
      byArchon[ak].groups[gk].tasks.push(t);
    });
    const ordered = [];
    const seen = {};
    (archons || []).forEach((a) => {
      if (byArchon[a.key]) { ordered.push(byArchon[a.key]); seen[a.key] = true; }
    });
    Object.keys(byArchon).forEach((k) => {
      if (!seen[k]) ordered.push(byArchon[k]);
    });
    return ordered.map((arch) => {
      const totalGroups = arch.order.length;
      const totalTasks = arch.order.reduce((s, gk) => s + arch.groups[gk].tasks.length, 0);
      const bodyHtml = arch.order.map((gk) => {
        const g = arch.groups[gk];
        return g.tasks.length === 1 ? renderSingleRow(g.tasks[0], g.label) : renderTimeGroup(g);
      }).join('');
      return '<div class="archon-section">' +
        '<div class="archon-header" role="button" tabindex="0" aria-expanded="true" onclick="toggleArchon(this)" onkeydown="if(event.key===\'Enter\'||event.key===\' \'){event.preventDefault();toggleArchon(this)}">' +
        '<span class="archon-arrow" aria-hidden="true">▼</span>' +
        '<span class="archon-name">' + esc(arch.name) + '</span>' +
        '<span class="archon-stat">' + totalGroups + ' 组 / ' + totalTasks + ' 项</span>' +
        '</div>' +
        '<div class="archon-body">' + bodyHtml + '</div>' +
        '</div>';
    }).join('');
  }
  window.toggleArchon = function (el) {
    const sec = el.parentElement;
    sec.classList.toggle('collapsed');
    el.setAttribute('aria-expanded', String(!sec.classList.contains('collapsed')));
  };
  window.toggleTimeGroup = function (el) {
    const grp = el.parentElement;
    grp.classList.toggle('expanded');
    el.setAttribute('aria-expanded', String(grp.classList.contains('expanded')));
  };

  window.loadTasks = async function () {
    const userEl = document.getElementById('taskGrid');
    const sysEl = document.getElementById('systemGrid');
    try {
      const r = await fetch('/api/tasks');
      const data = await r.json();
      const tasks = data.tasks || [];
      const userTasks = tasks.filter((t) => !t.source);
      const sysTasks = tasks.filter((t) => !!t.source);

      const cu = document.getElementById('countScheduled');
      const cs = document.getElementById('countSystem');
      if (cu) cu.textContent = userTasks.length ? userTasks.length : '';
      if (cs) cs.textContent = sysTasks.length ? sysTasks.length : '';

      if (!userTasks.length) {
        userEl.innerHTML = '<div class="empty-state"><span class="empty-icon" data-icon="clock"></span>暂无定时任务<br><br>在对话中说"每小时提醒我喝水"或使用 /schedule 指令创建</div>';
      } else {
        userEl.innerHTML = '<div class="task-grid">' + userTasks.map(renderTaskCard).join('') + '</div>';
      }
      if (!sysTasks.length) {
        sysEl.innerHTML = '<div class="empty-state"><span class="empty-icon" data-icon="settings"></span>暂无系统任务<br><br>开启订阅推送（订阅面板）或红利股追踪（理财面板）后，这里会显示由系统的周期任务</div>';
      } else {
        sysEl.innerHTML = renderSystemGrid(sysTasks, data.archons || []);
      }
      window.pmIcon && window.pmIcon.enhanceAll(userEl);
      window.pmIcon && window.pmIcon.enhanceAll(sysEl);
      window._tasksLoaded = true;
    } catch (e) {
      userEl.innerHTML = '<div class="empty-state">加载失败</div>';
      if (sysEl) sysEl.innerHTML = '<div class="empty-state">加载失败</div>';
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    const refresh = document.getElementById('tasks-refresh');
    if (refresh) {
      refresh.addEventListener('click', async (e) => {
        await window.pmBtn.runAsync(e.currentTarget, async () => {
          window._tasksLoaded = false;
          await loadTasks();
        }, { loadingText: '刷新中…' });
      });
    }
    loadTasks();
  });

  // 30 秒自动刷新当前 tab
  setInterval(() => {
    const active = document.querySelector('.tab-panel.active');
    if (!active) return;
    if (active.id === 'scheduled' || active.id === 'system') {
      window._tasksLoaded = false;
      loadTasks();
    }
  }, 30000);
})();
