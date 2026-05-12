/* knowledge 页脚本 — 记忆 tab + 知识库 tab + 整理 + 新建/编辑表单 modal */
(function () {
  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function fmtTime(ts) {
    if (!ts || ts <= 0) return '-';
    const d = new Date(ts * 1000);
    const pad = (n) => n.toString().padStart(2, '0');
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
      + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  window.switchTab = function (id, btn) {
    document.querySelectorAll('.tab-btn').forEach((t) => t.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
    if (btn) btn.classList.add('active');
    const el = document.getElementById(id);
    if (el) el.classList.add('active');
    if (id === 'kb' && !window._kbLoaded) loadKb();
  };

  // ───────── 记忆 tab ─────────
  let _memCache = {};
  let _currentMemType = 'user';

  window.switchMemType = function (mem_type, el) {
    _currentMemType = mem_type;
    document.querySelectorAll('.pill[data-mem]').forEach((p) => p.classList.remove('active'));
    if (el) el.classList.add('active');
    loadMem(mem_type);
  };

  function emptyMemHint(type) {
    const tips = {
      user: '还没有用户画像。用 <code>/remember 我主要用 Go</code> 或让派蒙自动提取。',
      feedback: '还没有行为规范。用 <code>/remember 不要给总结</code> 纠正派蒙回复风格。',
      project: '还没有项目事实。项目级持久事实会被时执自动提取。',
      reference: '还没有外部资源指针。像"bugs 在 Linear INGEST 项目"这类会落到这里。',
    };
    return '<div class="empty-state">' + (tips[type] || '无数据') + '</div>';
  }

  function renderMemItems(type, items) {
    const el = document.getElementById('memEl');
    if (!items || items.length === 0) {
      el.innerHTML = emptyMemHint(type);
      _memCache[type] = {};
      return;
    }
    _memCache[type] = {};
    const rows = items.map((it) => {
      _memCache[type][it.id] = it;
      const tags = (it.tags || []).map((t) => '<span class="chip">' + esc(t) + '</span>').join('');
      return '<tr data-id="' + esc(it.id) + '">' +
        '<td><strong>' + esc(it.title) + '</strong>' +
        '<div class="body-preview">' + esc(it.body_preview) + '</div>' +
        (tags ? '<div style="margin-top:6px">' + tags + '</div>' : '') + '</td>' +
        '<td class="mono">' + esc(it.subject || 'default') + '</td>' +
        '<td class="mono">' + fmtTime(it.updated_at) + '</td>' +
        '<td class="desc">' + esc(it.source || '-') + '</td>' +
        '<td>' +
        '<button class="btn-view" data-action="view" data-id="' + esc(it.id) + '">查看</button>' +
        '<button class="btn-revoke" data-action="delete" data-id="' + esc(it.id) + '">删除</button>' +
        '</td></tr>';
    }).join('');
    el.innerHTML = '<table class="data-table"><thead><tr>' +
      '<th>记忆</th><th>主题</th><th>更新</th><th>来源</th><th>操作</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table>';
    el.querySelectorAll('button[data-action]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const act = btn.getAttribute('data-action');
        const id = btn.getAttribute('data-id');
        if (act === 'view') viewMem(id);
        else if (act === 'delete') delMem(id);
      });
    });
  }

  window.viewMem = function (id) {
    const it = _memCache[_currentMemType] && _memCache[_currentMemType][id];
    if (!it) return;
    document.getElementById('modalEditBtn').style.display = 'none';
    _modalEditContext = null;
    document.getElementById('modalTitle').textContent = it.title;
    document.getElementById('modalBody').textContent = it.body || '(空)';
    document.getElementById('modalMeta').innerHTML =
      '类型: <span class="mono">' + esc(it.mem_type) + '</span> · ' +
      '主题: <span class="mono">' + esc(it.subject) + '</span><br>' +
      '来源: ' + esc(it.source || '-') + '<br>' +
      '标签: ' + ((it.tags || []).map(esc).join(', ') || '-') + '<br>' +
      '创建: ' + fmtTime(it.created_at) + ' · 更新: ' + fmtTime(it.updated_at) + '<br>' +
      'ID: <span class="mono">' + esc(it.id) + '</span>';
    document.getElementById('modal').classList.add('active');
  };

  window.delMem = async function (id) {
    const it = _memCache[_currentMemType] && _memCache[_currentMemType][id];
    const title = it ? it.title : id;
    if (!confirm('确定删除记忆「' + title + '」?\n此操作不可恢复，此记忆也将不再注入对话上下文。')) return;
    try {
      const r = await fetch('/api/knowledge/memory/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Confirm': 'yes' },
        body: JSON.stringify({ id }),
      });
      const d = await r.json();
      if (d.ok) loadMem(_currentMemType);
      else alert('删除失败: ' + (d.error || '未知错误'));
    } catch (e) { alert('删除失败: ' + e.message); }
  };

  async function loadMem(type) {
    const el = document.getElementById('memEl');
    try {
      const r = await fetch('/api/knowledge/memory/list?mem_type=' + encodeURIComponent(type));
      const d = await r.json();
      if (d.error) {
        el.innerHTML = '<div class="empty-state">加载失败: ' + esc(d.error) + '</div>';
        return;
      }
      renderMemItems(type, d.items || []);
      if (type === 'user') loadMemCount();
    } catch (e) {
      el.innerHTML = '<div class="empty-state">加载失败: ' + esc(e.message) + '</div>';
    }
  }

  async function loadMemCount() {
    try {
      let total = 0;
      for (const t of ['user', 'feedback', 'project', 'reference']) {
        const r = await fetch('/api/knowledge/memory/list?mem_type=' + t);
        const d = await r.json();
        total += (d.items || []).length;
      }
      const el = document.getElementById('countMem');
      if (el) el.textContent = total ? total : '';
    } catch (e) {}
  }

  // ───────── 记忆整理 / 知识库整理 ─────────
  let _hygienePollTimer = null;

  window.triggerHygiene = async function () {
    const btn = document.getElementById('btnHygiene');
    if (btn && btn.disabled) return;
    try {
      const r = await fetch('/api/knowledge/memory/hygiene', { method: 'POST' });
      const d = await r.json();
      if (!d.ok) { flashToast('启动整理失败', d.error || '', 'warn'); return; }
      if (d.already_running) {
        flashToast('整理中，请稍候', '', 'info');
      } else {
        flashToast('开始整理记忆…', 'LLM 扫全部记忆，批量合并/去重', 'info');
      }
      if (btn) { btn.disabled = true; btn.textContent = '🧹 整理中…'; }
      _pollHygieneStatus();
    } catch (e) { flashToast('启动整理异常', String(e), 'warn'); }
  };

  function _pollHygieneStatus() {
    if (_hygienePollTimer) clearTimeout(_hygienePollTimer);
    _hygienePollTimer = setTimeout(async () => {
      try {
        const r = await fetch('/api/knowledge/memory/hygiene/status');
        const d = await r.json();
        if (d.running) { _pollHygieneStatus(); return; }
        const btn = document.getElementById('btnHygiene');
        if (btn) { btn.disabled = false; btn.textContent = '🧹 整理'; }
        const rep = d.last_report || null;
        if (rep) {
          const merged = rep.merged || 0;
          const deleted = rep.deleted || 0;
          if (merged || deleted) {
            flashToast('整理完成：合并 ' + merged + '、删除 ' + deleted,
                       '详情见「📨 推送」收件箱的「草神」条目', 'success');
          } else {
            flashToast('整理完成：记忆已经很干净了', '', 'success');
          }
        } else {
          flashToast('整理完成', '', 'success');
        }
        loadMem(_currentMemType);
        loadMemCount();
      } catch (e) {
        const btn2 = document.getElementById('btnHygiene');
        if (btn2) { btn2.disabled = false; btn2.textContent = '🧹 整理'; }
        flashToast('整理状态查询失败', String(e), 'warn');
      }
    }, 3000);
  }

  let _kbHygienePollTimer = null;
  window.triggerKbHygiene = async function () {
    const btn = document.getElementById('btnKbHygiene');
    if (btn && btn.disabled) return;
    try {
      const r = await fetch('/api/knowledge/kb/hygiene', { method: 'POST' });
      const d = await r.json();
      if (!d.ok) { flashToast('启动整理失败', d.error || '', 'warn'); return; }
      if (d.already_running) {
        flashToast('整理中，请稍候', '', 'info');
      } else {
        flashToast('开始整理知识库…', 'LLM 按分类扫全部知识，批量合并/去重', 'info');
      }
      if (btn) { btn.disabled = true; btn.textContent = '🧹 整理中…'; }
      _pollKbHygieneStatus();
    } catch (e) { flashToast('启动整理异常', String(e), 'warn'); }
  };
  function _pollKbHygieneStatus() {
    if (_kbHygienePollTimer) clearTimeout(_kbHygienePollTimer);
    _kbHygienePollTimer = setTimeout(async () => {
      try {
        const r = await fetch('/api/knowledge/kb/hygiene/status');
        const d = await r.json();
        if (d.running) { _pollKbHygieneStatus(); return; }
        const btn = document.getElementById('btnKbHygiene');
        if (btn) { btn.disabled = false; btn.textContent = '🧹 整理'; }
        const rep = d.last_report || null;
        if (rep) {
          const merged = rep.merged || 0;
          const deleted = rep.deleted || 0;
          if (merged || deleted) {
            flashToast('整理完成：合并 ' + merged + '、删除 ' + deleted,
                       '详情见「📨 推送」收件箱的「草神」条目', 'success');
          } else {
            flashToast('整理完成：知识库已经很干净了', '', 'success');
          }
        } else {
          flashToast('整理完成', '', 'success');
        }
        window._kbLoaded = false; loadKb();
      } catch (e) {
        const btn2 = document.getElementById('btnKbHygiene');
        if (btn2) { btn2.disabled = false; btn2.textContent = '🧹 整理'; }
        flashToast('整理状态查询失败', String(e), 'warn');
      }
    }, 3000);
  }

  // ───────── 表单 modal（新建/编辑）─────────
  let _currentForm = null;

  function _showFormModal(title) {
    _hideFormError();
    document.getElementById('formTitle').textContent = title;
    document.getElementById('formModal').classList.add('active');
  }
  window.closeFormModal = function (e) {
    if (e && e.target.id !== 'formModal') return;
    document.getElementById('formModal').classList.remove('active');
    _currentForm = null;
  };
  function _showFormError(msg) {
    const el = document.getElementById('formError');
    el.textContent = msg;
    el.classList.add('active');
  }
  function _hideFormError() {
    document.getElementById('formError').classList.remove('active');
  }

  window.openMemCreate = function () {
    _currentForm = { type: 'memory_remember' };
    document.getElementById('formBody').innerHTML =
      '<div class="form-field">' +
      '<label>说一句你想让我记住的事</label>' +
      '<textarea id="fContent" placeholder="例：我主要用 Python / 不要给总结 / 项目 DB 是 PostgreSQL"></textarea>' +
      '<div class="hint">会自动判类型和标题；跟已有冲突时自动合并</div>' +
      '</div>';
    _showFormModal('新建记忆');
    setTimeout(() => document.getElementById('fContent').focus(), 50);
  };

  window.openKbCreate = function () {
    _currentForm = { type: 'kb_remember' };
    document.getElementById('formBody').innerHTML =
      '<div class="form-field">' +
      '<label>说一段你想记录的知识</label>' +
      '<textarea id="fContent" placeholder="例：Claude API 每分钟限流 50 次 / asyncio 的 gather 用法"></textarea>' +
      '<div class="hint">会自动判分类和主题；跟已有冲突时自动合并</div>' +
      '</div>';
    _showFormModal('新建知识');
    setTimeout(() => document.getElementById('fContent').focus(), 50);
  };

  window.openKbEdit = function (category, topic, body) {
    _currentForm = { type: 'kb_edit', category, topic };
    const el = document.getElementById('formBody');
    el.innerHTML =
      '<div class="form-field">' +
      '<label>分类 category</label>' +
      '<input type="text" id="fCategory" disabled value="' + esc(category) + '">' +
      '<div class="hint">分类/主题作为主键不可改；如需改名请新建 + 删除旧条目</div>' +
      '</div>' +
      '<div class="form-field">' +
      '<label>主题 topic</label>' +
      '<input type="text" id="fTopic" disabled value="' + esc(topic) + '">' +
      '</div>' +
      '<div class="form-field">' +
      '<label>内容</label>' +
      '<textarea id="fBody"></textarea>' +
      '</div>';
    document.getElementById('fBody').value = body || '';
    _showFormModal('编辑知识 · ' + category + ' / ' + topic);
    setTimeout(() => {
      const bd = document.getElementById('fBody');
      bd.focus(); bd.setSelectionRange(bd.value.length, bd.value.length);
    }, 50);
  };

  // ───────── Flash toast ─────────
  let _flashTimer = null;
  function flashToast(title, reason, kind) {
    kind = kind || 'info';
    const bar = document.getElementById('flashBar');
    if (!bar) return;
    bar.innerHTML = '<div class="flash-title">' + esc(title) + '</div>' +
      (reason ? '<div class="flash-reason">' + esc(reason) + '</div>' : '');
    bar.className = 'flash-bar active ' + kind;
    if (_flashTimer) clearTimeout(_flashTimer);
    _flashTimer = setTimeout(() => bar.classList.remove('active'), 4000);
  }

  let _submitting = false;
  window.submitForm = async function () {
    if (_submitting || !_currentForm) return;
    _hideFormError();
    const f = _currentForm;
    const saveBtn = document.querySelector('#formModal .btn-save');
    const origLabel = saveBtn ? saveBtn.textContent : '保存';
    _submitting = true;
    if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '保存中…'; }
    try {
      if (f.type === 'memory_remember') {
        const content = document.getElementById('fContent').value.trim();
        if (!content) { _showFormError('内容不能为空'); return; }
        const r = await fetch('/api/knowledge/memory/remember', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content }),
        });
        const d = await r.json();
        if (!d.ok) { _showFormError('保存失败: ' + (d.error || '未知错误')); return; }
        closeFormModal();
        const action = d.action || 'new';
        let title, kind = 'success';
        if (action === 'new') title = '已记住：' + (d.title || '');
        else if (action === 'merge') title = '已合并到原记忆「' + (d.target_title || '') + '」';
        else if (action === 'replace') { title = '已替换旧记忆「' + (d.target_title || '') + '」'; kind = 'warn'; }
        else if (action === 'duplicate') { title = '已存在相同记忆，未重复写入'; kind = 'info'; }
        else title = '完成';
        flashToast(title, d.reason || '', kind);
        const new_type = d.mem_type || _currentMemType;
        if (new_type !== _currentMemType) {
          const pillEl = document.querySelector('.pill[data-mem="' + new_type + '"]');
          if (pillEl) switchMemType(new_type, pillEl);
          else loadMem(new_type);
        } else loadMem(new_type);
        loadMemCount();
      } else if (f.type === 'kb_remember') {
        const content3 = document.getElementById('fContent').value.trim();
        if (!content3) { _showFormError('内容不能为空'); return; }
        const r3 = await fetch('/api/knowledge/kb/remember', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: content3 }),
        });
        const d3 = await r3.json();
        if (!d3.ok) { _showFormError('保存失败: ' + (d3.error || '未知错误')); return; }
        closeFormModal();
        const act = d3.action || 'new';
        let title3, kind3 = 'success';
        if (act === 'new') title3 = '已记入知识库：' + (d3.category || '') + ' / ' + (d3.topic || '');
        else if (act === 'merge') title3 = '已合并到原知识「' + (d3.target_topic || '') + '」';
        else if (act === 'replace') { title3 = '已替换旧知识「' + (d3.target_topic || '') + '」'; kind3 = 'warn'; }
        else if (act === 'duplicate') { title3 = '已存在相同知识「' + (d3.target_topic || '') + '」'; kind3 = 'info'; }
        else title3 = '完成';
        flashToast(title3, d3.reason || '', kind3);
        window._kbLoaded = false; loadKb();
      } else if (f.type === 'kb_edit') {
        const cat = document.getElementById('fCategory').value.trim();
        const topic = document.getElementById('fTopic').value.trim();
        const body2 = document.getElementById('fBody').value;
        if (!cat || !topic) { _showFormError('分类和主题不能为空'); return; }
        if (!body2.trim()) { _showFormError('内容不能为空'); return; }
        const r2 = await fetch('/api/knowledge/kb/write', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ category: cat, topic, body: body2 }),
        });
        const d2 = await r2.json();
        if (!d2.ok) { _showFormError('保存失败: ' + (d2.error || '未知错误')); return; }
        closeFormModal();
        flashToast('已更新「' + cat + ' / ' + topic + '」', '', 'success');
        window._kbLoaded = false; loadKb();
      }
    } catch (e) {
      _showFormError('保存失败: ' + e.message);
    } finally {
      _submitting = false;
      if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = origLabel; }
    }
  };

  // 详情 modal → 编辑切换（仅 kb 条目）
  let _modalEditContext = null;
  window.modalStartEdit = function () {
    if (!_modalEditContext) return;
    const ctx = _modalEditContext;
    document.getElementById('modal').classList.remove('active');
    _modalEditContext = null;
    openKbEdit(ctx.category, ctx.topic, ctx.body);
  };

  // ───────── 知识库 tab ─────────
  let _kbCache = {};

  async function loadKb() {
    const el = document.getElementById('kbEl');
    try {
      const r = await fetch('/api/knowledge/kb/list');
      const d = await r.json();
      const items = d.items || [];
      const cc = document.getElementById('countKb');
      if (cc) cc.textContent = items.length ? items.length : '';
      if (!items.length) {
        el.innerHTML = '<div class="empty-state">知识库为空。<br><br>让草神调 <code>knowledge</code> 工具写入，或在对话里说"帮我把 X 记到知识库 Y 分类下"</div>';
        window._kbLoaded = true;
        return;
      }
      _kbCache = {};
      const rows = items.map((it) => {
        const key = it.category + '/' + it.topic;
        _kbCache[key] = it;
        return '<tr data-key="' + esc(key) + '">' +
          '<td><strong>' + esc(it.topic) + '</strong>' +
          '<div class="body-preview">' + esc(it.body_preview || '') + '</div></td>' +
          '<td class="mono">' + esc(it.category) + '</td>' +
          '<td class="mono">' + fmtTime(it.updated_at) + '</td>' +
          '<td>' +
          '<button class="btn-view" data-action="view" data-key="' + esc(key) + '">查看</button>' +
          '<button class="btn-revoke" data-action="delete" data-key="' + esc(key) + '">删除</button>' +
          '</td></tr>';
      }).join('');
      el.innerHTML = '<table class="data-table"><thead><tr>' +
        '<th>知识</th><th>分类</th><th>更新</th><th>操作</th>' +
        '</tr></thead><tbody>' + rows + '</tbody></table>';
      el.querySelectorAll('button[data-action]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const act = btn.getAttribute('data-action');
          const key = btn.getAttribute('data-key');
          const it = _kbCache[key];
          if (!it) return;
          if (act === 'view') openKb(it.category, it.topic);
          else if (act === 'delete') delKb(it.category, it.topic);
        });
      });
      window._kbLoaded = true;
    } catch (e) {
      el.innerHTML = '<div class="empty-state">加载失败: ' + esc(e.message) + '</div>';
    }
  }

  window.delKb = async function (cat, topic) {
    if (!confirm('确定删除知识「' + cat + ' / ' + topic + '」?\n此操作不可恢复。')) return;
    try {
      const r = await fetch('/api/knowledge/kb/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Confirm': 'yes' },
        body: JSON.stringify({ category: cat, topic }),
      });
      const d = await r.json();
      if (d.ok) {
        flashToast('已删除「' + cat + ' / ' + topic + '」', '', 'success');
        window._kbLoaded = false; loadKb();
      } else {
        alert('删除失败: ' + (d.error || '未知错误'));
      }
    } catch (e) { alert('删除失败: ' + e.message); }
  };

  window.openKb = async function (cat, topic) {
    document.getElementById('modalTitle').textContent = cat + ' / ' + topic;
    document.getElementById('modalBody').textContent = '加载中…';
    document.getElementById('modalMeta').innerHTML =
      '分类: <span class="mono">' + esc(cat) + '</span> · ' +
      '主题: <span class="mono">' + esc(topic) + '</span>';
    document.getElementById('modalEditBtn').style.display = '';
    _modalEditContext = { category: cat, topic, body: '' };
    document.getElementById('modal').classList.add('active');
    try {
      const r = await fetch('/api/knowledge/kb/read?category=' + encodeURIComponent(cat) + '&topic=' + encodeURIComponent(topic));
      const d = await r.json();
      if (d.error) {
        document.getElementById('modalBody').textContent = '读取失败: ' + d.error;
        return;
      }
      document.getElementById('modalBody').textContent = d.body || '(空)';
      if (_modalEditContext) _modalEditContext.body = d.body || '';
    } catch (e) {
      document.getElementById('modalBody').textContent = '读取失败: ' + e.message;
    }
  };

  window.closeModal = function (e) {
    if (e && e.target.id !== 'modal') return;
    document.getElementById('modal').classList.remove('active');
  };

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const m = document.getElementById('modal');
      if (m && m.classList.contains('active')) m.classList.remove('active');
    }
  });

  window.refreshAll = function () {
    window._kbLoaded = false;
    loadMem(_currentMemType);
    const active = document.querySelector('.tab-panel.active');
    if (!active) return;
    if (active.id === 'kb') loadKb();
  };

  document.addEventListener('DOMContentLoaded', () => {
    const refresh = document.getElementById('kn-refresh');
    if (refresh) {
      refresh.addEventListener('click', async (e) => {
        await window.pmBtn.runAsync(e.currentTarget, async () => {
          window.refreshAll();
        }, { loadingText: '刷新中…' });
      });
    }
    loadMem('user');
  });
})();
