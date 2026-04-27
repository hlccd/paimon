"""神之心 · LLM Profile 管理面板 + 路由配置

M1：profile 存储 + 面板（增删改 + 测连接 + 设默认）
M2：新增路由 tab —— 按 (component, purpose) 把调用路由到 profile；点击保
存即 publish leyline 事件，Gnosis 感知后热切换 provider 缓存。

docs/todo.md §LLM 分层调度
"""

from paimon.channels.webui.theme import (
    BASE_CSS, NAV_LINKS_CSS, NAVIGATION_CSS, THEME_COLORS, navigation_html,
)


LLM_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .page-header .sub { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
    .header-actions { display: flex; gap: 10px; align-items: center; }
    .btn {
        padding: 8px 16px; background: var(--paimon-panel-light);
        color: var(--text-secondary); border: 1px solid var(--paimon-border);
        border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .btn:hover { border-color: var(--gold-dark); color: var(--gold); }
    .btn-primary {
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        color: #000; border: none; font-weight: 600;
    }
    .btn-primary:hover { opacity: .9; color: #000; }

    /* profile 卡片列表 */
    .profile-list { display: flex; flex-direction: column; gap: 12px; }
    .profile-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 16px 20px;
        display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: center;
    }
    .profile-card.is-default {
        border-color: var(--gold-dark);
        box-shadow: 0 0 0 1px rgba(255,180,80,.15);
    }
    .profile-info .name { font-size: 16px; color: var(--text-primary); font-weight: 500; margin-bottom: 4px; }
    .profile-info .meta { font-size: 12px; color: var(--text-muted); }
    .profile-info .meta span { margin-right: 12px; }
    .profile-info .notes { color: var(--text-muted); font-size: 12px; margin-top: 4px; font-style: italic; }
    .profile-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .btn-action {
        padding: 6px 12px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 4px; cursor: pointer; font-size: 12px;
    }
    .btn-action:hover { border-color: var(--gold-dark); color: var(--gold); }
    .btn-action:disabled { opacity: .6; cursor: wait; }
    .btn-action.danger { color: var(--status-error); border-color: rgba(239,68,68,.4); }
    .btn-action.danger:hover { background: rgba(239,68,68,.1); }
    .btn-action.success { color: var(--status-success); border-color: rgba(16,185,129,.4); }

    .badge {
        display: inline-block; padding: 2px 8px; border-radius: 10px;
        font-size: 11px; font-weight: 500;
        background: var(--paimon-panel-light); color: var(--text-secondary);
    }
    .badge-default { background: rgba(255,180,80,.12); color: var(--gold); border: 1px solid rgba(255,180,80,.35); }
    .badge-thinking { background: rgba(110,198,255,.12); color: var(--star); }
    .badge-kind { background: var(--paimon-panel-light); color: var(--text-secondary); }

    /* 测连接结果条 */
    .test-result {
        margin-top: 8px; padding: 8px 12px; border-radius: 4px; font-size: 12px;
        white-space: pre-wrap; word-break: break-word;
    }
    .test-result.ok { background: rgba(16,185,129,.1); color: var(--status-success); border: 1px solid rgba(16,185,129,.25); }
    .test-result.err { background: rgba(239,68,68,.08); color: var(--status-error); border: 1px solid rgba(239,68,68,.25); }

    /* Modal 表单 */
    .modal-backdrop {
        display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1000;
        align-items: center; justify-content: center;
    }
    .modal-backdrop.active { display: flex; }
    .modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border); border-radius: 8px;
        max-width: 640px; width: 90%; max-height: 90vh; overflow: auto; padding: 24px;
    }
    .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .modal-header h3 { color: var(--gold); font-size: 18px; font-weight: 600; }
    .modal-close {
        background: transparent; border: none; color: var(--text-muted); font-size: 20px;
        cursor: pointer; padding: 0 4px;
    }
    .modal-close:hover { color: var(--text-primary); }

    .form-row { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
    .form-row label { font-size: 12px; color: var(--text-muted); }
    .form-row label .req { color: var(--status-error); margin-left: 2px; }
    .form-row input, .form-row select, .form-row textarea {
        width: 100%; padding: 8px 12px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 6px;
        color: var(--text-primary); font-size: 13px; font-family: inherit;
    }
    .form-row textarea { font-family: 'SF Mono', Monaco, Consolas, monospace; min-height: 64px; resize: vertical; }
    .form-row input:focus, .form-row select:focus, .form-row textarea:focus { outline: none; border-color: var(--gold); }
    .form-row .hint { color: var(--text-muted); font-size: 11px; line-height: 1.5; }
    .form-row-inline { display: flex; gap: 8px; align-items: center; }
    .form-row-inline input[type=checkbox] { width: auto; }
    .form-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .modal-footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }

    .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 14px; }

    /* Tab 切换（模型管理 / 路由配置）*/
    .tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--paimon-border); }
    .tab-btn {
        padding: 10px 20px; background: transparent; border: none; color: var(--text-muted);
        cursor: pointer; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active { color: var(--gold); border-bottom-color: var(--gold); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    /* 路由表格 */
    .route-section { margin-bottom: 28px; }
    .route-section h3 {
        font-size: 14px; color: var(--text-primary); font-weight: 600;
        margin-bottom: 10px;
    }
    .route-section .section-hint { font-size: 12px; color: var(--text-muted); margin-bottom: 10px; }
    .route-table { width: 100%; border-collapse: collapse; }
    .route-table th, .route-table td {
        padding: 10px 12px; border-bottom: 1px solid var(--paimon-border);
        font-size: 13px; text-align: left; vertical-align: middle;
    }
    .route-table th { color: var(--gold); font-weight: 600; font-size: 12px; }
    .route-table tbody tr:hover td { background: var(--paimon-panel); }
    .route-key { font-family: 'SF Mono', Monaco, Consolas, monospace; color: var(--text-primary); }
    .route-default-hint { color: var(--text-muted); font-style: italic; font-size: 12px; }
    .route-select {
        padding: 5px 8px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        color: var(--text-primary); font-size: 12px; min-width: 200px;
    }
    .route-save-flash {
        display: inline-block; margin-left: 8px; padding: 2px 8px;
        border-radius: 10px; font-size: 11px;
        background: rgba(16,185,129,.12); color: var(--status-success);
        opacity: 0; transition: opacity .2s;
    }
    .route-save-flash.shown { opacity: 1; }
    /* 最近命中小字 */
    .hit-cell { font-size: 12px; color: var(--text-muted); }
    .hit-cell .hit-model { color: var(--text-secondary); font-family: 'SF Mono', Monaco, Consolas, monospace; }
    .hit-cell .hit-src { color: var(--text-muted); }
    .hit-cell .hit-time { color: var(--text-muted); margin-left: 4px; }
    .hit-cell .hit-none { color: var(--paimon-border); font-style: italic; }

    .default-hero {
        padding: 12px 16px; margin-bottom: 16px;
        background: rgba(255,180,80,.08); border: 1px solid rgba(255,180,80,.28);
        border-radius: 8px; font-size: 13px; color: var(--text-primary);
    }
    .default-hero strong { color: var(--gold); }
"""


LLM_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>🧠 神之心 · 模型与路由</h1>
                <div class="sub">模型条目 + 按 (component, purpose) 调度到不同模型</div>
            </div>
            <div class="header-actions">
                <button class="btn" onclick="refreshActiveTab()">刷新</button>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" data-tab="profiles" onclick="switchTab('profiles', this)">📋 模型管理</button>
            <button class="tab-btn" data-tab="routes" onclick="switchTab('routes', this)">🗺️ 路由配置</button>
        </div>

        <div id="profiles" class="tab-panel active">
            <div style="display:flex;justify-content:flex-end;margin-bottom:16px">
                <button class="btn btn-primary" onclick="openCreate()">+ 新增 Profile</button>
            </div>
            <div id="profileList" class="profile-list">
                <div class="empty-state">加载中...</div>
            </div>
        </div>

        <div id="routes" class="tab-panel">
            <div id="routeDefaultHero" class="default-hero">加载中...</div>

            <div class="route-section">
                <h3>按 component（粗粒度）</h3>
                <div class="section-hint">一条规则覆盖该 component 的所有 purpose；更细规则能单独配在下方。</div>
                <table class="route-table">
                    <thead><tr><th style="width:30%">component</th><th style="width:40%">路由到</th><th>最近命中</th></tr></thead>
                    <tbody id="routeCoarseBody"></tbody>
                </table>
            </div>

            <div class="route-section">
                <h3>按 component:purpose（细粒度）</h3>
                <div class="section-hint">细粒度优先于粗粒度；都没配则走全局默认 profile。</div>
                <table class="route-table">
                    <thead><tr><th style="width:15%">component</th><th style="width:20%">purpose</th><th style="width:35%">路由到</th><th>最近命中</th></tr></thead>
                    <tbody id="routeFineBody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <div id="modal" class="modal-backdrop" onclick="closeModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal-header">
                <h3 id="modalTitle">新增 Profile</h3>
                <button class="modal-close" onclick="closeModal()">×</button>
            </div>

            <input type="hidden" id="fld_id" value="" />

            <div class="form-row">
                <label>展示名 <span class="req">*</span></label>
                <input id="fld_name" placeholder="如：DS v4-pro (thinking high)" />
                <div class="hint">UNIQUE；给自己看的。</div>
            </div>

            <div class="form-grid-2">
                <div class="form-row">
                    <label>Provider 类型 <span class="req">*</span></label>
                    <select id="fld_provider_kind">
                        <option value="openai">openai（OpenAI / DeepSeek / mimo / 兼容 API）</option>
                        <option value="anthropic">anthropic（Claude 官方 / 代理）</option>
                    </select>
                </div>
                <div class="form-row">
                    <label>Model ID <span class="req">*</span></label>
                    <input id="fld_model" placeholder="如：deepseek-v4-pro" />
                </div>
            </div>

            <div class="form-row">
                <label>Base URL <span class="req">*</span></label>
                <input id="fld_base_url" placeholder="如：https://api.deepseek.com" />
            </div>

            <div class="form-row">
                <label>API Key <span class="req">*</span></label>
                <input id="fld_api_key" type="password" placeholder="sk-..." />
                <div class="hint">编辑时显示 *** 表示保留原值不动；想改则清空后重新粘贴。</div>
            </div>

            <div class="form-grid-2">
                <div class="form-row">
                    <label>max_tokens</label>
                    <input id="fld_max_tokens" type="number" value="64000" />
                    <div class="hint">仅 anthropic 生效</div>
                </div>
                <div class="form-row">
                    <label>reasoning_effort</label>
                    <select id="fld_reasoning_effort">
                        <option value="">（不设置）</option>
                        <option value="high">high</option>
                        <option value="max">max</option>
                    </select>
                    <div class="hint">仅 openai/deepseek 生效</div>
                </div>
            </div>

            <div class="form-row">
                <label>extra_body (JSON)</label>
                <textarea id="fld_extra_body" placeholder='{"thinking":{"type":"enabled"}}'></textarea>
                <div class="hint">透传给 SDK 的 extra_body；留空即 {}。DeepSeek thinking 模式填 <code>{"thinking":{"type":"enabled"}}</code>。</div>
            </div>

            <div class="form-row">
                <label>备注</label>
                <input id="fld_notes" placeholder="（可选）这条 profile 什么用途" />
            </div>

            <div id="testResult" class="test-result" style="display:none"></div>

            <div class="modal-footer">
                <button class="btn" id="btnTestInModal" onclick="testInModal()">测试连接</button>
                <button class="btn" onclick="closeModal()">取消</button>
                <button class="btn btn-primary" onclick="saveProfile()">保存</button>
            </div>
        </div>
    </div>
"""


LLM_SCRIPT = """
    <script>
    (function(){
        function esc(s){
            if(s===null||s===undefined) return '';
            return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
        }
        function fmtTime(ts){
            if(!ts||ts<=0)return'-';
            var d=new Date(ts*1000);
            return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+
                String(d.getDate()).padStart(2,'0')+' '+
                String(d.getHours()).padStart(2,'0')+':'+
                String(d.getMinutes()).padStart(2,'0');
        }
        function relTime(ts){
            if(!ts||ts<=0) return '-';
            var sec = Math.max(0, Math.floor(Date.now()/1000 - ts));
            if(sec < 5) return '刚刚';
            if(sec < 60) return sec+'秒前';
            if(sec < 3600) return Math.floor(sec/60)+'分钟前';
            if(sec < 86400) return Math.floor(sec/3600)+'小时前';
            return Math.floor(sec/86400)+'天前';
        }

        var currentProfiles = [];

        async function loadProfiles(){
            var el = document.getElementById('profileList');
            try {
                var r = await fetch('/api/llm/list');
                var d = await r.json();
                var list = d.profiles || [];
                currentProfiles = list;
                if(!list.length){
                    el.innerHTML = '<div class="empty-state">暂无 profile。点上方「+ 新增 Profile」添加第一条。</div>';
                    return;
                }
                el.innerHTML = list.map(function(p){
                    var thinking = false;
                    try {
                        var eb = p.extra_body || {};
                        thinking = !!(eb.thinking && eb.thinking.type === 'enabled');
                    } catch(e){}
                    var badges = '';
                    if(p.is_default) badges += '<span class="badge badge-default">默认</span> ';
                    badges += '<span class="badge badge-kind">'+esc(p.provider_kind)+'</span>';
                    if(thinking) badges += ' <span class="badge badge-thinking">thinking</span>';
                    if(p.reasoning_effort) badges += ' <span class="badge">effort='+esc(p.reasoning_effort)+'</span>';

                    return '<div class="profile-card'+(p.is_default?' is-default':'')+'">'
                        + '<div class="profile-info">'
                        +   '<div class="name">'+esc(p.name)+' &nbsp;'+badges+'</div>'
                        +   '<div class="meta">'
                        +     '<span>model: '+esc(p.model)+'</span>'
                        +     '<span>base: '+esc(p.base_url || '-')+'</span>'
                        +     '<span>key: '+(p.api_key ? esc(p.api_key) : '(空)')+'</span>'
                        +     '<span>更新: '+fmtTime(p.updated_at)+'</span>'
                        +   '</div>'
                        +   (p.notes?'<div class="notes">'+esc(p.notes)+'</div>':'')
                        +   '<div id="test-'+esc(p.id)+'"></div>'
                        + '</div>'
                        + '<div class="profile-actions">'
                        +   '<button class="btn-action" onclick="testExisting(\\''+esc(p.id)+'\\',this)">测连接</button>'
                        +   '<button class="btn-action" onclick="openEdit(\\''+esc(p.id)+'\\')">编辑</button>'
                        +   (p.is_default ? '' : '<button class="btn-action success" onclick="setDefault(\\''+esc(p.id)+'\\')">设为默认</button>')
                        +   (p.is_default ? '' : '<button class="btn-action danger" onclick="delProfile(\\''+esc(p.id)+'\\')">删除</button>')
                        + '</div>'
                        + '</div>';
                }).join('');
            } catch(e){
                el.innerHTML = '<div class="empty-state">加载失败: '+esc(String(e))+'</div>';
            }
        }

        function resetForm(){
            document.getElementById('fld_id').value = '';
            document.getElementById('fld_name').value = '';
            document.getElementById('fld_provider_kind').value = 'openai';
            document.getElementById('fld_model').value = '';
            document.getElementById('fld_base_url').value = '';
            document.getElementById('fld_api_key').value = '';
            document.getElementById('fld_max_tokens').value = '64000';
            document.getElementById('fld_reasoning_effort').value = '';
            document.getElementById('fld_extra_body').value = '';
            document.getElementById('fld_notes').value = '';
            var tr = document.getElementById('testResult');
            tr.style.display = 'none'; tr.textContent = ''; tr.className = 'test-result';
        }

        window.openCreate = function(){
            resetForm();
            document.getElementById('modalTitle').textContent = '新增 Profile';
            document.getElementById('modal').classList.add('active');
        };

        window.openEdit = function(id){
            var p = currentProfiles.find(function(x){return x.id === id;});
            if(!p) return;
            resetForm();
            document.getElementById('fld_id').value = p.id;
            document.getElementById('fld_name').value = p.name || '';
            document.getElementById('fld_provider_kind').value = p.provider_kind || 'openai';
            document.getElementById('fld_model').value = p.model || '';
            document.getElementById('fld_base_url').value = p.base_url || '';
            document.getElementById('fld_api_key').value = p.api_key || '';  // 通常是 ***
            document.getElementById('fld_max_tokens').value = p.max_tokens || 64000;
            document.getElementById('fld_reasoning_effort').value = p.reasoning_effort || '';
            var eb = (p.extra_body && Object.keys(p.extra_body).length)
                ? JSON.stringify(p.extra_body, null, 2) : '';
            document.getElementById('fld_extra_body').value = eb;
            document.getElementById('fld_notes').value = p.notes || '';
            document.getElementById('modalTitle').textContent = '编辑 Profile · ' + p.name;
            document.getElementById('modal').classList.add('active');
        };

        window.closeModal = function(e){
            if(e && e.target && e.target.id !== 'modal') return;
            document.getElementById('modal').classList.remove('active');
        };

        function collectForm(){
            var extraRaw = (document.getElementById('fld_extra_body').value || '').trim();
            var extra = {};
            if(extraRaw){
                try { extra = JSON.parse(extraRaw); }
                catch(e){ alert('extra_body 不是合法 JSON：'+e.message); return null; }
            }
            return {
                id: document.getElementById('fld_id').value,
                name: document.getElementById('fld_name').value.trim(),
                provider_kind: document.getElementById('fld_provider_kind').value,
                model: document.getElementById('fld_model').value.trim(),
                base_url: document.getElementById('fld_base_url').value.trim(),
                api_key: document.getElementById('fld_api_key').value,
                max_tokens: parseInt(document.getElementById('fld_max_tokens').value || '64000', 10),
                reasoning_effort: document.getElementById('fld_reasoning_effort').value,
                extra_body: extra,
                notes: document.getElementById('fld_notes').value.trim(),
            };
        }

        window.saveProfile = async function(){
            var data = collectForm();
            if(!data) return;
            if(!data.name || !data.model || !data.base_url){
                alert('name / model / base_url 必填'); return;
            }
            var isEdit = !!data.id;
            var url = isEdit
                ? '/api/llm/' + encodeURIComponent(data.id) + '/update'
                : '/api/llm/create';
            try {
                var r = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(data),
                });
                var d = await r.json();
                if(d.ok){
                    closeModal();
                    loadProfiles();
                } else {
                    alert((isEdit?'更新':'创建')+'失败: '+(d.error || 'unknown'));
                }
            } catch(e){ alert('请求失败: '+e.message); }
        };

        window.testInModal = async function(){
            var data = collectForm();
            if(!data) return;
            var tr = document.getElementById('testResult');
            var btn = document.getElementById('btnTestInModal');
            tr.style.display = ''; tr.className = 'test-result';
            tr.textContent = '测试中…';
            btn.disabled = true;
            try {
                var r = await fetch('/api/llm/test', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(data),
                });
                var d = await r.json();
                if(d.ok){
                    tr.className = 'test-result ok';
                    tr.textContent = '✓ 连通 · 延迟 '+d.latency_ms+' ms\\n示例回复：'+(d.sample || '(空)');
                } else {
                    tr.className = 'test-result err';
                    tr.textContent = '✗ 失败: '+(d.error || 'unknown');
                }
            } catch(e){
                tr.className = 'test-result err';
                tr.textContent = '✗ 请求异常: '+e.message;
            } finally { btn.disabled = false; }
        };

        window.testExisting = async function(id, btn){
            var row = document.getElementById('test-'+id);
            if(!row) return;
            var originalText = btn.textContent;
            btn.disabled = true; btn.textContent = '测试中…';
            row.innerHTML = '<div class="test-result">测试中…</div>';
            try {
                var r = await fetch('/api/llm/'+encodeURIComponent(id)+'/test', {method:'POST'});
                var d = await r.json();
                if(d.ok){
                    row.innerHTML = '<div class="test-result ok">✓ 连通 · 延迟 '+d.latency_ms+' ms · 示例：'+esc(d.sample || '(空)')+'</div>';
                } else {
                    row.innerHTML = '<div class="test-result err">✗ '+esc(d.error || 'unknown')+'</div>';
                }
            } catch(e){
                row.innerHTML = '<div class="test-result err">✗ 请求异常: '+esc(e.message)+'</div>';
            } finally {
                btn.disabled = false; btn.textContent = originalText;
            }
        };

        window.setDefault = async function(id){
            try {
                var r = await fetch('/api/llm/'+encodeURIComponent(id)+'/set-default', {method:'POST'});
                var d = await r.json();
                if(d.ok) loadProfiles();
                else alert('设默认失败: '+(d.error || 'unknown'));
            } catch(e){ alert('请求失败: '+e.message); }
        };

        window.delProfile = async function(id){
            var p = currentProfiles.find(function(x){return x.id === id;});
            var name = p ? p.name : id;
            if(!confirm('确定删除 profile「'+name+'」？不可恢复。')) return;
            try {
                var r = await fetch('/api/llm/'+encodeURIComponent(id)+'/delete', {method:'POST'});
                var d = await r.json();
                if(d.ok) loadProfiles();
                else alert('删除失败: '+(d.error || 'unknown'));
            } catch(e){ alert('请求失败: '+e.message); }
        };

        document.addEventListener('keydown', function(e){
            if(e.key === 'Escape'){
                var m = document.getElementById('modal');
                if(m && m.classList.contains('active')) m.classList.remove('active');
            }
        });

        // ============ Tab 切换 ============
        window.switchTab = function(id, btn){
            document.querySelectorAll('.tab-btn').forEach(function(t){t.classList.remove('active');});
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            if(btn) btn.classList.add('active');
            var el = document.getElementById(id);
            if(el) el.classList.add('active');
            if(id === 'routes') loadRoutes();
        };

        window.refreshActiveTab = function(){
            var active = document.querySelector('.tab-btn.active');
            var id = active ? active.getAttribute('data-tab') : 'profiles';
            if(id === 'routes') loadRoutes();
            else loadProfiles();
        };

        // ============ 路由配置 Tab ============
        async function loadRoutes(){
            var heroEl = document.getElementById('routeDefaultHero');
            var coarseEl = document.getElementById('routeCoarseBody');
            var fineEl = document.getElementById('routeFineBody');
            if(!heroEl || !coarseEl || !fineEl) return;
            heroEl.textContent = '加载中...';
            coarseEl.innerHTML = fineEl.innerHTML = '<tr><td colspan="3">加载中...</td></tr>';
            try {
                // 并行拉 profiles + routes
                var [profResp, routeResp] = await Promise.all([
                    fetch('/api/llm/list').then(function(r){return r.json();}),
                    fetch('/api/llm/routes').then(function(r){return r.json();}),
                ]);
                var profiles = profResp.profiles || [];
                currentProfiles = profiles;
                var routes = routeResp.routes || {};
                var callsites = routeResp.callsites || [];
                var def = routeResp.default;

                // 默认 hero：下拉直接切默认 profile（所有路由未命中的调用都走这条）
                if(profiles.length){
                    var defaultId = def ? def.id : '';
                    var opts = profiles.map(function(p){
                        var sel = (p.id === defaultId) ? ' selected' : '';
                        return '<option value="'+esc(p.id)+'"'+sel+'>'+esc(p.name)+'</option>';
                    }).join('');
                    heroEl.innerHTML = '<span style="flex-shrink:0">🎯 全局默认 profile：</span>'
                        + '<select class="route-select" id="defaultProfileSelect" onchange="setDefaultFromHero(this)" style="min-width:240px">'
                        + opts
                        + '</select>'
                        + '<span class="route-save-flash" data-flash-for="__default__">已切换 ✓</span>'
                        + '<span class="route-default-hint" style="margin-left:auto">路由未命中时回落到此。</span>';
                    heroEl.style.display = 'flex';
                    heroEl.style.gap = '10px';
                    heroEl.style.alignItems = 'center';
                } else {
                    heroEl.innerHTML = '<span style="color:var(--status-error)">⚠ 还没有 profile，请到「模型管理」tab 新增。</span>';
                    heroEl.style.display = 'block';
                }

                // 构建选项
                function profileOptionsHTML(selected){
                    var html = '<option value="">（走默认）</option>';
                    profiles.forEach(function(p){
                        var sel = (selected === p.id) ? ' selected' : '';
                        var label = p.name + (p.is_default?' · [默认]':'');
                        html += '<option value="'+esc(p.id)+'"'+sel+'>'+esc(label)+'</option>';
                    });
                    return html;
                }

                var hits = routeResp.hits || {};

                // 把 hit 渲染成一行小字："最近：xxx · 3 分钟前"
                function hitCellHTML(key){
                    var h = hits[key];
                    if(!h) return '<span class="hit-none">— 未命中</span>';
                    var ago = relTime(h.timestamp);
                    var srcTag = '';
                    if(h.provider_source === 'default') srcTag = ' <span class="hit-src">(默认)</span>';
                    else if(h.provider_source === 'env') srcTag = ' <span class="hit-src">(env)</span>';
                    return '<span class="hit-model">'+esc(h.model_name || '?')+'</span>'
                         + srcTag + ' <span class="hit-time">· '+esc(ago)+'</span>';
                }

                // 粗粒度：由 callsites 去重 components
                var componentsSet = {};
                callsites.forEach(function(c){ componentsSet[c.component] = 1; });
                var components = Object.keys(componentsSet).sort();
                coarseEl.innerHTML = components.map(function(c){
                    var key = c;
                    var cur = routes[key] || '';
                    return '<tr>'
                        + '<td><span class="route-key">'+esc(c)+'</span></td>'
                        + '<td>'
                        +   '<select class="route-select" data-key="'+esc(key)+'" onchange="saveRoute(this)">'
                        +     profileOptionsHTML(cur)
                        +   '</select>'
                        +   '<span class="route-save-flash" data-flash-for="'+esc(key)+'">已保存 ✓</span>'
                        + '</td>'
                        + '<td class="hit-cell">' + hitCellHTML(key) + '</td>'
                        + '</tr>';
                }).join('');

                // 细粒度
                fineEl.innerHTML = callsites.map(function(c){
                    var key = c.component + ':' + c.purpose;
                    var cur = routes[key] || '';
                    return '<tr>'
                        + '<td><span class="route-key">'+esc(c.component)+'</span></td>'
                        + '<td><span class="route-key">'+esc(c.purpose)+'</span></td>'
                        + '<td>'
                        +   '<select class="route-select" data-key="'+esc(key)+'" onchange="saveRoute(this)">'
                        +     profileOptionsHTML(cur)
                        +   '</select>'
                        +   '<span class="route-save-flash" data-flash-for="'+esc(key)+'">已保存 ✓</span>'
                        + '</td>'
                        + '<td class="hit-cell">' + hitCellHTML(key) + '</td>'
                        + '</tr>';
                }).join('');
            } catch(e){
                heroEl.innerHTML = '<span style="color:var(--status-error)">加载失败: '+esc(String(e))+'</span>';
            }
        }

        window.setDefaultFromHero = async function(selectEl){
            var pid = selectEl.value;
            if(!pid) return;
            var flash = document.querySelector('.route-save-flash[data-flash-for="__default__"]');
            try {
                var r = await fetch('/api/llm/' + encodeURIComponent(pid) + '/set-default', {method: 'POST'});
                var d = await r.json();
                if(d.ok){
                    if(flash){
                        flash.classList.add('shown');
                        setTimeout(function(){ flash.classList.remove('shown'); }, 1500);
                    }
                    // 重新渲染整个路由表（"[默认]" 标记要跟着移动；leyline 事件
                    // 已让 gnosis 缓存失效，下一次 chat 自动用新默认）
                    setTimeout(function(){ loadRoutes(); }, 200);
                } else {
                    alert('切换失败: ' + (d.error || 'unknown'));
                }
            } catch(e){
                alert('请求失败: ' + e.message);
            }
        };

        window.saveRoute = async function(selectEl){
            var key = selectEl.getAttribute('data-key');
            var pid = selectEl.value;
            var flash = document.querySelector('.route-save-flash[data-flash-for="'+CSS.escape(key)+'"]');
            try {
                var url = pid
                    ? '/api/llm/routes/set'
                    : '/api/llm/routes/delete';
                var body = pid ? {route_key: key, profile_id: pid} : {route_key: key};
                var r = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(body),
                });
                var d = await r.json();
                if(d.ok){
                    if(flash){
                        flash.classList.add('shown');
                        setTimeout(function(){ flash.classList.remove('shown'); }, 1500);
                    }
                } else {
                    alert('保存失败: '+(d.error || 'unknown'));
                }
            } catch(e){
                alert('请求失败: '+e.message);
            }
        };

        window.loadProfiles = loadProfiles;
        window.onload = function(){ loadProfiles(); };
    })();
    </script>
"""


def build_llm_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon · 神之心 模型管理</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + LLM_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("llm")
        + LLM_BODY
        + LLM_SCRIPT
        + """</body>
</html>"""
    )
