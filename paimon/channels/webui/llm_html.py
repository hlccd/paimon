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

    .route-key { font-family: 'SF Mono', Monaco, Consolas, monospace; color: var(--text-primary); }
    .route-select {
        padding: 5px 8px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        color: var(--text-primary); font-size: 12px; min-width: 220px;
    }
    .route-save-flash {
        display: inline-block; margin-left: 8px; padding: 2px 8px;
        border-radius: 10px; font-size: 11px;
        background: rgba(16,185,129,.12); color: var(--status-success);
        opacity: 0; transition: opacity .2s;
    }
    .route-save-flash.shown { opacity: 1; }

    .default-hero {
        padding: 12px 16px; margin-bottom: 20px;
        background: rgba(255,180,80,.08); border: 1px solid rgba(255,180,80,.28);
        border-radius: 8px; font-size: 13px; color: var(--text-primary);
    }
    .default-hero strong { color: var(--gold); }

    /* ===== Provider 分组（profiles tab，外层按 anthropic/openai） ===== */
    .provider-section {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; overflow: hidden;
    }
    .provider-header {
        padding: 12px 18px; background: var(--paimon-panel-light);
        border-bottom: 1px solid var(--paimon-border);
        display: flex; align-items: center; gap: 10px;
        cursor: pointer; user-select: none;
    }
    .provider-header:hover { background: rgba(245,158,11,.08); }
    .provider-arrow { color: var(--gold); font-size: 11px; width: 12px; transition: transform .2s; }
    .provider-section.collapsed .provider-arrow { transform: rotate(-90deg); }
    .provider-section.collapsed .provider-header { border-bottom-color: transparent; }
    .provider-section.collapsed .provider-body { display: none; }
    .provider-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
    .provider-stat { font-size: 12px; color: var(--text-muted); margin-left: auto; }
    .provider-body { padding: 12px 18px; display: flex; flex-direction: column; gap: 10px; }

    /* profile 卡片紧凑化（取代旧 .profile-card grid 双栏） */
    .profile-card {
        display: grid; grid-template-columns: minmax(0, 1fr) auto;
        gap: 12px; align-items: center;
        padding: 12px 14px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 8px;
        transition: border-color .2s;
    }
    .profile-card:hover { border-color: var(--gold-dark); }
    .profile-card.is-default {
        border-color: var(--gold-dark);
        background: linear-gradient(90deg, rgba(245,158,11,.06), var(--paimon-bg) 30%);
    }
    .profile-info .name {
        font-size: 14px; color: var(--text-primary); font-weight: 500;
        margin-bottom: 4px;
        display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    }
    .profile-info .star { color: var(--gold); font-size: 14px; }
    .profile-info .meta {
        font-size: 12px; color: var(--text-muted);
        display: flex; gap: 14px; flex-wrap: wrap;
    }
    .profile-info .meta span.mono { font-family: 'SF Mono', Monaco, Consolas, monospace; }
    .profile-info .notes {
        color: var(--text-muted); font-size: 12px;
        margin-top: 4px; font-style: italic;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .profile-actions { display: flex; gap: 6px; flex-wrap: nowrap; }

    /* ===== Category 大类分组（routes tab 顶层：派蒙/七神/四影） ===== */
    .category-section {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 12px; margin-bottom: 16px; overflow: hidden;
    }
    .category-header {
        padding: 14px 20px;
        background: linear-gradient(90deg, rgba(245,158,11,.10), var(--paimon-panel-light) 60%);
        border-bottom: 1px solid var(--paimon-border);
        display: flex; align-items: center; gap: 12px;
        cursor: pointer; user-select: none;
    }
    .category-header:hover { background: linear-gradient(90deg, rgba(245,158,11,.16), var(--paimon-panel-light) 60%); }
    .category-arrow { color: var(--gold); font-size: 12px; width: 12px; transition: transform .2s; }
    .category-section.collapsed .category-arrow { transform: rotate(-90deg); }
    .category-section.collapsed .category-body { display: none; }
    .category-name { font-size: 16px; font-weight: 600; color: var(--gold); }
    .category-stat { font-size: 12px; color: var(--text-muted); margin-left: auto; }
    .category-stat.stat-warn {
        color: var(--status-error);
        background: rgba(239,68,68,.10);
        padding: 2px 8px; border-radius: 10px;
        border: 1px solid rgba(239,68,68,.28);
        font-weight: 500;
    }
    .category-body {
        padding: 10px 14px 14px;
        display: flex; flex-direction: column; gap: 6px;
    }

    /* 紧凑单行（单 purpose 组件，直接挂 category 下） */
    .compact-row {
        display: grid;
        grid-template-columns: minmax(200px, 1.2fr) minmax(220px, 280px) auto 1fr;
        gap: 12px; align-items: center;
        padding: 8px 12px;
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-radius: 6px;
        transition: border-color .2s;
    }
    .compact-row:hover { border-color: var(--gold-dark); }
    .compact-name { font-size: 13px; color: var(--text-primary); font-weight: 500; }

    /* 未接入 router 的紧凑行（空执 / video_process / audio_process） */
    .compact-row.disabled { opacity: .6; cursor: not-allowed; background: rgba(239,68,68,.04); }
    .compact-row.disabled:hover { border-color: var(--paimon-border); }
    .compact-row.disabled .route-select { cursor: not-allowed; color: var(--text-muted); }
    .compact-name .tag-disabled-inline {
        font-size: 10px; padding: 1px 6px; border-radius: 8px;
        background: rgba(239,68,68,.12); color: var(--status-error);
        border: 1px solid rgba(239,68,68,.28);
        margin-left: 6px; font-weight: 500;
    }
    .purpose-hit.hit-disabled {
        color: var(--status-error); font-style: italic; opacity: .85;
    }

    /* shades 内嵌「七神」子段 */
    .archons-sub {
        margin-top: 10px;
        background: rgba(245,158,11,.05);
        border: 1px dashed rgba(245,158,11,.35);
        border-radius: 8px;
        padding: 10px 12px;
    }
    .archons-sub-header {
        font-size: 13px; font-weight: 600; color: var(--gold);
        margin-bottom: 8px;
    }
    .archons-sub-header .sub-stat {
        font-size: 11px; color: var(--text-muted); font-weight: 400; margin-left: 4px;
    }
    .archons-sub-body { display: flex; flex-direction: column; gap: 6px; }

    /* 空段占位（如天使主标题，暂无 LLM 调用点） */
    .empty-placeholder {
        padding: 16px 12px; text-align: center;
        color: var(--text-muted); font-size: 13px; font-style: italic;
        background: var(--paimon-bg);
        border: 1px dashed var(--paimon-border);
        border-radius: 6px;
    }

    /* ===== Component 嵌套段（多 purpose 才用；置于 category-body 内） ===== */
    .component-section {
        background: var(--paimon-bg); border: 1px solid var(--paimon-border);
        border-radius: 8px; overflow: hidden;
    }
    .component-header {
        padding: 12px 18px; background: var(--paimon-panel-light);
        border-bottom: 1px solid var(--paimon-border);
        display: flex; align-items: center; gap: 12px;
    }
    .component-toggle { cursor: pointer; user-select: none; display: flex; align-items: center; gap: 10px; }
    .component-toggle:hover .component-name { color: var(--gold); }
    .component-arrow { color: var(--gold); font-size: 11px; width: 12px; transition: transform .2s; }
    .component-section.collapsed .component-arrow { transform: rotate(-90deg); }
    .component-section.collapsed .component-header { border-bottom-color: transparent; }
    .component-section.collapsed .component-body { display: none; }
    .component-name { font-size: 15px; font-weight: 600; color: var(--text-primary); transition: color .2s; }
    .component-stat { font-size: 12px; color: var(--text-muted); }
    .component-group-control {
        margin-left: auto; display: flex; align-items: center; gap: 8px;
        font-size: 12px; color: var(--text-muted);
    }
    .component-body { padding: 8px 18px 14px; }

    /* purpose 行紧凑布局 */
    .purpose-row {
        display: grid;
        grid-template-columns: 200px 80px minmax(220px, 1fr) 90px 1fr;
        gap: 10px; align-items: center;
        padding: 6px 4px;
        border-bottom: 1px dashed var(--paimon-border);
    }
    .purpose-row:last-child { border-bottom: none; }
    .purpose-name {
        font-size: 13px; color: var(--text-primary);
        font-family: 'SF Mono', Monaco, Consolas, monospace;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .purpose-tag {
        font-size: 11px; padding: 2px 8px; border-radius: 10px;
        text-align: center; font-weight: 500;
    }
    .tag-inherit {
        background: var(--paimon-panel-light); color: var(--text-muted);
        border: 1px solid var(--paimon-border);
    }
    .tag-override {
        background: rgba(245,158,11,.15); color: var(--gold);
        border: 1px solid rgba(245,158,11,.35);
    }
    .purpose-action { display: flex; gap: 6px; }
    .btn-mini {
        padding: 3px 8px; background: transparent;
        border: 1px solid var(--paimon-border); border-radius: 4px;
        color: var(--text-muted); font-size: 11px; cursor: pointer;
    }
    .btn-mini:hover { border-color: var(--gold-dark); color: var(--gold); }
    .purpose-hit {
        font-size: 11px; color: var(--text-muted);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .purpose-hit .hit-model { color: var(--text-secondary); font-family: 'SF Mono', Monaco, Consolas, monospace; }
    .purpose-hit .hit-src { color: var(--text-muted); }
    .purpose-hit .hit-none { color: var(--paimon-border); font-style: italic; }
"""


LLM_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>🧠 神之心 · 模型与路由</h1>
                <div class="sub">管理模型 profile · 配置每个调用点用哪个模型</div>
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
            <div id="routeContainer">
                <div class="empty-state">加载中...</div>
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

        var PROVIDER_DISPLAY = {
            anthropic: 'Anthropic',
            openai: 'OpenAI / DeepSeek / 兼容',
        };

        function shortHost(url){
            if(!url) return '-';
            try { return new URL(url).host || url; }
            catch(e){ return url; }
        }

        function renderProfileCard(p){
            var thinking = !!(p.extra_body && p.extra_body.thinking && p.extra_body.thinking.type === 'enabled');
            var badges = '';
            if(thinking) badges += ' <span class="badge badge-thinking">thinking</span>';
            if(p.reasoning_effort) badges += ' <span class="badge">effort='+esc(p.reasoning_effort)+'</span>';

            return '<div class="profile-card'+(p.is_default?' is-default':'')+'">'
                + '<div class="profile-info">'
                +   '<div class="name">'
                +     (p.is_default?'<span class="star">✰</span>':'')
                +     '<span>'+esc(p.name)+'</span>'
                +     badges
                +   '</div>'
                +   '<div class="meta">'
                +     '<span class="mono">'+esc(p.model)+'</span>'
                +     '<span title="'+esc(p.base_url || '')+'">'+esc(shortHost(p.base_url))+'</span>'
                +   '</div>'
                +   (p.notes?'<div class="notes">'+esc(p.notes)+'</div>':'')
                +   '<div id="test-'+esc(p.id)+'"></div>'
                + '</div>'
                + '<div class="profile-actions">'
                +   '<button class="btn-action" onclick="testExisting(\\''+esc(p.id)+'\\',this)">测连接</button>'
                +   '<button class="btn-action" onclick="openEdit(\\''+esc(p.id)+'\\')">编辑</button>'
                +   (p.is_default ? '' : '<button class="btn-action success" onclick="setDefault(\\''+esc(p.id)+'\\')">设默认</button>')
                +   (p.is_default ? '' : '<button class="btn-action danger" onclick="delProfile(\\''+esc(p.id)+'\\')">删除</button>')
                + '</div>'
                + '</div>';
        }

        function renderProviderSection(kind, list){
            // 默认 profile 在前；其余按 name 字典序
            list.sort(function(a, b){
                if(a.is_default !== b.is_default) return a.is_default ? -1 : 1;
                return (a.name || '').localeCompare(b.name || '');
            });
            var displayName = PROVIDER_DISPLAY[kind] || kind;
            var bodyHtml = list.map(renderProfileCard).join('');
            return '<div class="provider-section">'
                + '<div class="provider-header" onclick="toggleProvider(this)">'
                +   '<span class="provider-arrow">▼</span>'
                +   '<span class="provider-name">'+esc(displayName)+'</span>'
                +   '<span class="provider-stat">'+list.length+' 个 profile</span>'
                + '</div>'
                + '<div class="provider-body">'+bodyHtml+'</div>'
                + '</div>';
        }

        window.toggleProvider = function(el){ el.parentElement.classList.toggle('collapsed'); };

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
                // 按 provider_kind 桶
                var byKind = {};
                list.forEach(function(p){
                    var k = p.provider_kind || 'openai';
                    if(!byKind[k]) byKind[k] = [];
                    byKind[k].push(p);
                });
                // 排序：anthropic 在前；未知 kind 排最后
                var order = ['anthropic', 'openai'];
                Object.keys(byKind).forEach(function(k){
                    if(order.indexOf(k) === -1) order.push(k);
                });
                el.innerHTML = order.filter(function(k){return byKind[k];}).map(function(k){
                    return renderProviderSection(k, byKind[k]);
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
        // component → 中文显示名（KNOWN_CALLSITES 见 paimon/foundation/model_router.py）
        var COMPONENT_DESC = {
            // 派蒙 · 主对话
            'chat': '💬 chat · 日常对话',
            'paimon': '✨ paimon · 意图分类',
            'title': '🏷 title · 标题生成',
            // 三月 · 定时调度
            'march': '⏰ march · 定时任务调度',
            '三月·自检': '🩺 三月·自检 · code-health',
            // 世界树 · 记忆/知识库
            'remember': '📝 remember · 记忆分类',
            'reconcile': '🔄 reconcile · 记忆冲突检测/修复',
            'hygiene': '🧹 hygiene · 记忆批量整理',
            'kb_remember': '📚 kb_remember · 知识分类',
            'kb_hygiene': '📚 kb_hygiene · 知识批量整理',
            // 四影
            '生执': '🎼 生执 · 任务编排',
            '死执': '💀 死执 · 安全审查',
            '时执': '⏳ 时执 · 上下文压缩/L1 提取',
            '空执': '🌀 空执 · 动态路由',
            // 七神（嵌四影下）
            '水神': '💧 水神 · 评审/审核',
            '雷神': '⚡ 雷神 · 代码生成',
            '草神': '🌿 草神 · 推理/写产品',
            '风神': '🌬 风神 · 信息采集',
            '冰神': '❄ 冰神 · Skill 汇总',
            '火神': '🔥 火神 · 执行部署',
            '岩神': '⛰ 岩神 · 理财分析',
            // 音视频处理（独立 tool）
            'video_process': '🎥 video_process · 视频分析',
            'audio_process': '🎙 audio_process · 音频分析',
        };

        // 大类划分：派蒙 / 天使 / 四影(含七神嵌入子段) / 三月 / 世界树 / 音视频
        // 七神标 'shades:archons' 表示是 shades 下的 archons 子段
        var COMPONENT_CATEGORY = {
            // 派蒙
            'chat': 'paimon', 'paimon': 'paimon', 'title': 'paimon',
            // 世界树
            'remember': 'irminsul', 'reconcile': 'irminsul', 'hygiene': 'irminsul',
            'kb_remember': 'irminsul', 'kb_hygiene': 'irminsul',
            // 三月
            'march': 'march', '三月·自检': 'march',
            // 四影
            '生执': 'shades', '死执': 'shades', '时执': 'shades', '空执': 'shades',
            // 七神（嵌四影下）
            '水神': 'shades:archons', '雷神': 'shades:archons', '草神': 'shades:archons',
            '风神': 'shades:archons', '冰神': 'shades:archons',
            '火神': 'shades:archons', '岩神': 'shades:archons',
            // 音视频
            'video_process': 'audiovis', 'audio_process': 'audiovis',
        };

        // 当前未接入 ModelRouter 的 component（代码不读路由，配了也不生效）
        // 面板上 selector disabled + ⚠ 标记
        var DISABLED_COMPONENTS = {
            '空执': '当前 asmoday 仅做 DAG 路由，不发 LLM 调用',
            'video_process': '当前直连 mimo_key，未接入 router',
            'audio_process': '当前直连 mimo_key，未接入 router',
        };

        var CATEGORY_DESC = {
            paimon:   '🎭 派蒙 · 统一入口',
            angels:   '👼 天使 · Skill 体系',
            shades:   '🌌 四影 · 流程编排',
            march:    '⏰ 三月女神 · 定时调度',
            irminsul: '🌳 世界树 · 记忆/知识域',
            audiovis: '🎬 音视频处理',
            other:    '其他',
        };
        // 顶层渲染顺序（七神不在此 - 它嵌在 shades 内部）
        var CATEGORY_ORDER = ['paimon', 'angels', 'shades', 'march', 'irminsul', 'audiovis', 'other'];

        // angels 段当前不走 EMPTY_PLACEHOLDERS，由 renderAngelsSkillsSection 单独渲染
        // skill 列表（保留以备无 skill 数据时占位）
        var EMPTY_PLACEHOLDERS = {};

        // 天使段头部固定提示文案（appended 在 skill 列表上方）
        var ANGELS_NOTE = '⚠ skill 当前不直接调用 LLM，路由由触发它的 archon 决定；此处仅展示 skill 清单';

        function profileNameById(id){
            var p = currentProfiles.find(function(x){return x.id === id;});
            return p ? p.name : (id ? id.substring(0, 8) : '');
        }

        function profileOptionsHTML(selected, includeInheritOption, inheritLabel){
            var html = '';
            if(includeInheritOption){
                html += '<option value="">'+esc(inheritLabel || '(走全局默认)')+'</option>';
            }
            currentProfiles.forEach(function(p){
                var sel = (selected === p.id) ? ' selected' : '';
                var label = p.name + (p.is_default ? ' · [默认]' : '');
                html += '<option value="'+esc(p.id)+'"'+sel+'>'+esc(label)+'</option>';
            });
            return html;
        }

        function hitCellHTML(key, hits){
            var h = hits && hits[key];
            if(!h) return '<span class="hit-none">— 未命中</span>';
            var ago = relTime(h.timestamp);
            var srcTag = '';
            if(h.provider_source === 'default') srcTag = ' <span class="hit-src">(默认)</span>';
            else if(h.provider_source === 'env') srcTag = ' <span class="hit-src">(env)</span>';
            return '<span class="hit-model">'+esc(h.model_name || '?')+'</span>'
                 + srcTag + ' <span class="hit-time">· '+esc(ago)+'</span>';
        }

        function renderPurposeRow(component, purpose, routes, hits, componentRouteId, defaultId){
            var key = component + ':' + purpose;
            var purposeRouteId = routes[key] || '';
            var hasOverride = !!purposeRouteId;
            // 继承的目标 = 组级路由 ?? 全局默认
            var inheritTarget = componentRouteId || defaultId || '';
            var inheritName = inheritTarget ? profileNameById(inheritTarget) : '(无默认 profile)';
            var inheritLabel = '(继承组级 → ' + inheritName + ')';

            var tag = hasOverride
                ? '<span class="purpose-tag tag-override">✰ 独立</span>'
                : '<span class="purpose-tag tag-inherit">继承组级</span>';
            var actionHtml = hasOverride
                ? '<button class="btn-mini" onclick="restoreInherit(\\''+esc(key)+'\\')">恢复继承</button>'
                : '';

            return '<div class="purpose-row">'
                + '<span class="purpose-name">'+esc(purpose)+'</span>'
                + tag
                + '<select class="route-select" data-key="'+esc(key)+'" onchange="savePurposeRoute(this)">'
                +   profileOptionsHTML(purposeRouteId, true, inheritLabel)
                + '</select>'
                + '<div class="purpose-action">'+actionHtml+'</div>'
                + '<span class="purpose-hit">'+hitCellHTML(key, hits)+'</span>'
                + '</div>';
        }

        // 单 purpose 且无 purpose-level override 的组件 → 紧凑单行
        // 未接入 router 的 component 也走这个（disabled selector + ⚠ 标）
        function renderCompactComponentRow(component, purpose, routes, hits, defaultId){
            var componentRouteId = routes[component] || '';
            var displayName = COMPONENT_DESC[component] || component;
            var disabledHint = DISABLED_COMPONENTS[component];
            if(disabledHint){
                // 未接入路由：selector 灰显 + ⚠ 标，4 元素对齐 normal compact-row 列布局
                return '<div class="compact-row disabled" title="'+esc(disabledHint)+'">'
                    + '<span class="compact-name">'+esc(displayName)
                    +     ' <span class="tag-disabled-inline">⚠ 未接入</span></span>'
                    + '<select class="route-select" disabled>'
                    +   '<option>(未接入 router，配置不生效)</option>'
                    + '</select>'
                    + '<span></span>'
                    + '<span class="purpose-hit hit-disabled">'+esc(disabledHint)+'</span>'
                    + '</div>';
            }
            return '<div class="compact-row">'
                + '<span class="compact-name">'+esc(displayName)+'</span>'
                + '<select class="route-select" data-component="'+esc(component)+'" onchange="saveComponentRoute(this)">'
                +   profileOptionsHTML(componentRouteId, true, '(走全局默认)')
                + '</select>'
                + '<span class="route-save-flash" data-flash-for="'+esc(component)+'">已保存 ✓</span>'
                + '<span class="purpose-hit">'+hitCellHTML(component, hits)+'</span>'
                + '</div>';
        }

        // 退化条件：purpose 数 == 1 且 purpose-level 无 override；
        // 否则保留嵌套两层（用户能看到/修复异常 override）
        function shouldUseCompactRow(component, purposes, routes){
            if(purposes.length !== 1) return false;
            var purposeKey = component + ':' + purposes[0];
            return !routes[purposeKey];
        }

        // 渲染 shades 内嵌的七神子段（"组中组"）
        function renderArchonsSubSection(archons, routes, hits, defaultId){
            var componentNames = Object.keys(archons);
            if(!componentNames.length) return '';
            var totalPurposes = componentNames.reduce(function(s, c){
                return s + archons[c].length;
            }, 0);
            var bodyHtml = componentNames.map(function(comp){
                var purposes = archons[comp];
                if(shouldUseCompactRow(comp, purposes, routes)){
                    return renderCompactComponentRow(comp, purposes[0], routes, hits, defaultId);
                }
                return renderComponentSection(comp, purposes, routes, hits, defaultId);
            }).join('');
            return '<div class="archons-sub">'
                + '<div class="archons-sub-header">🌟 七神 ·' + ' <span class="sub-stat">'+componentNames.length+' 神 · '+totalPurposes+' 项</span></div>'
                + '<div class="archons-sub-body">'+bodyHtml+'</div>'
                + '</div>';
        }

        // 天使段：列出 skill 清单（disabled，纯展示）
        function renderAngelsSkillsSection(skills){
            var displayName = CATEGORY_DESC.angels;
            var note = '<div class="empty-placeholder" style="margin-bottom:8px">'+esc(ANGELS_NOTE)+'</div>';
            var bodyHtml;
            if(!skills || !skills.length){
                bodyHtml = note + '<div class="empty-placeholder">未发现 skill</div>';
            } else {
                var rows = skills.map(function(s){
                    var label = '🧩 ' + s.name + (s.description ? ' · ' + s.description : '');
                    return '<div class="compact-row disabled" title="'+esc(s.description || '')+'">'
                        + '<span class="compact-name">'+esc(label)
                        +     ' <span class="tag-disabled-inline">⚠ 不直调 LLM</span></span>'
                        + '<select class="route-select" disabled>'
                        +   '<option>(由触发它的 archon 决定路由)</option>'
                        + '</select>'
                        + '<span></span>'
                        + '<span class="purpose-hit hit-disabled">见上方说明</span>'
                        + '</div>';
                }).join('');
                bodyHtml = note + rows;
            }
            return '<div class="category-section collapsed">'
                + '<div class="category-header" onclick="toggleCategory(this)">'
                +   '<span class="category-arrow">▼</span>'
                +   '<span class="category-name">'+esc(displayName)+'</span>'
                +   '<span class="category-stat stat-warn">'+(skills ? skills.length : 0)+' skill · ⚠ 不可配</span>'
                + '</div>'
                + '<div class="category-body">'+bodyHtml+'</div>'
                + '</div>';
        }

        // cat="shades" 时 components 是 {direct: {...}, archons: {...}} 双层
        // 其他 cat 是普通 {component: [purposes]} 单层
        function renderCategorySection(cat, components, routes, hits, defaultId){
            var displayName = CATEGORY_DESC[cat] || cat;

            // 空段（如 angels 占位主标题）
            if(EMPTY_PLACEHOLDERS[cat] && (!components || !Object.keys(components).length)){
                return '<div class="category-section collapsed">'
                    + '<div class="category-header" onclick="toggleCategory(this)">'
                    +   '<span class="category-arrow">▼</span>'
                    +   '<span class="category-name">'+esc(displayName)+'</span>'
                    +   '<span class="category-stat">占位</span>'
                    + '</div>'
                    + '<div class="category-body">'
                    +   '<div class="empty-placeholder">'+esc(EMPTY_PLACEHOLDERS[cat])+'</div>'
                    + '</div>'
                    + '</div>';
            }

            // shades 特殊：内含 direct + archons 两块
            if(cat === 'shades' && components.direct){
                var direct = components.direct || {};
                var archons = components.archons || {};
                var directNames = Object.keys(direct);
                var archonNames = Object.keys(archons);
                var totalPurposes =
                      directNames.reduce(function(s, c){return s + direct[c].length;}, 0)
                    + archonNames.reduce(function(s, c){return s + archons[c].length;}, 0);
                var directHtml = directNames.map(function(comp){
                    var purposes = direct[comp];
                    if(shouldUseCompactRow(comp, purposes, routes)){
                        return renderCompactComponentRow(comp, purposes[0], routes, hits, defaultId);
                    }
                    return renderComponentSection(comp, purposes, routes, hits, defaultId);
                }).join('');
                var archonsHtml = renderArchonsSubSection(archons, routes, hits, defaultId);
                return '<div class="category-section collapsed">'
                    + '<div class="category-header" onclick="toggleCategory(this)">'
                    +   '<span class="category-arrow">▼</span>'
                    +   '<span class="category-name">'+esc(displayName)+'</span>'
                    +   '<span class="category-stat">'+(directNames.length + archonNames.length)+' 组件 · '+totalPurposes+' 项</span>'
                    + '</div>'
                    + '<div class="category-body">'+directHtml+archonsHtml+'</div>'
                    + '</div>';
            }

            // 普通 category
            var componentNames = Object.keys(components);
            var totalPurposes = componentNames.reduce(function(s, c){
                return s + components[c].length;
            }, 0);
            var bodyHtml = componentNames.map(function(comp){
                var purposes = components[comp];
                if(shouldUseCompactRow(comp, purposes, routes)){
                    return renderCompactComponentRow(comp, purposes[0], routes, hits, defaultId);
                }
                return renderComponentSection(comp, purposes, routes, hits, defaultId);
            }).join('');
            // 整段全 disabled（如 audiovis）→ stat 加红警示
            var allDisabled = componentNames.every(function(c){return DISABLED_COMPONENTS[c];});
            var statClass = allDisabled ? 'category-stat stat-warn' : 'category-stat';
            var statText = allDisabled
                ? componentNames.length+' 组件 · ⚠ 全部未接入'
                : componentNames.length+' 组件 · '+totalPurposes+' 项';
            return '<div class="category-section collapsed">'
                + '<div class="category-header" onclick="toggleCategory(this)">'
                +   '<span class="category-arrow">▼</span>'
                +   '<span class="category-name">'+esc(displayName)+'</span>'
                +   '<span class="'+statClass+'">'+statText+'</span>'
                + '</div>'
                + '<div class="category-body">'+bodyHtml+'</div>'
                + '</div>';
        }

        window.toggleCategory = function(el){
            var sec = el.closest('.category-section');
            if(sec) sec.classList.toggle('collapsed');
        };

        function renderComponentSection(component, purposes, routes, hits, defaultId){
            var componentRouteId = routes[component] || '';
            var purposeOverrideCount = purposes.filter(function(p){return routes[component + ':' + p];}).length;
            var bodyHtml = purposes.map(function(p){
                return renderPurposeRow(component, p, routes, hits, componentRouteId, defaultId);
            }).join('');
            var displayName = COMPONENT_DESC[component] || component;
            return '<div class="component-section">'
                + '<div class="component-header">'
                +   '<div class="component-toggle" onclick="toggleComponent(this)">'
                +     '<span class="component-arrow">▼</span>'
                +     '<span class="component-name">'+esc(displayName)+'</span>'
                +     '<span class="component-stat">'+purposes.length+' 项'
                +       (purposeOverrideCount?' · '+purposeOverrideCount+' 独立':'')
                +     '</span>'
                +   '</div>'
                +   '<div class="component-group-control">'
                +     '<span>组级路由:</span>'
                +     '<select class="route-select" data-component="'+esc(component)+'" onchange="saveComponentRoute(this)" style="min-width:240px">'
                +       profileOptionsHTML(componentRouteId, true, '(走全局默认)')
                +     '</select>'
                +     '<span class="route-save-flash" data-flash-for="'+esc(component)+'">已保存 ✓</span>'
                +   '</div>'
                + '</div>'
                + '<div class="component-body">'+bodyHtml+'</div>'
                + '</div>';
        }

        window.toggleComponent = function(el){
            var sec = el.closest('.component-section');
            if(sec) sec.classList.toggle('collapsed');
        };

        async function loadRoutes(){
            var heroEl = document.getElementById('routeDefaultHero');
            var container = document.getElementById('routeContainer');
            if(!heroEl || !container) return;
            heroEl.textContent = '加载中...';
            container.innerHTML = '<div class="empty-state">加载中...</div>';
            try {
                var [profResp, routeResp] = await Promise.all([
                    fetch('/api/llm/list').then(function(r){return r.json();}),
                    fetch('/api/llm/routes').then(function(r){return r.json();}),
                ]);
                var profiles = profResp.profiles || [];
                currentProfiles = profiles;
                var routes = routeResp.routes || {};
                window._lastRoutes = routes;  // saveComponentRoute 检测 cascade 用
                var callsites = routeResp.callsites || [];
                var hits = routeResp.hits || {};
                var def = routeResp.default;
                var defaultId = def ? def.id : '';
                var skills = routeResp.skills || [];  // 天使段渲染用

                // 全局默认 hero
                if(profiles.length){
                    var opts = profiles.map(function(p){
                        var sel = (p.id === defaultId) ? ' selected' : '';
                        return '<option value="'+esc(p.id)+'"'+sel+'>'+esc(p.name)+'</option>';
                    }).join('');
                    heroEl.innerHTML = '<span style="flex-shrink:0">🎯 全局默认 profile：</span>'
                        + '<select class="route-select" id="defaultProfileSelect" onchange="setDefaultFromHero(this)" style="min-width:280px">'
                        + opts + '</select>'
                        + '<span class="route-save-flash" data-flash-for="__default__">已切换 ✓</span>'
                        + '<span style="margin-left:auto;font-size:12px;color:var(--text-muted);font-style:italic">所有未命中路由回落到此</span>';
                    heroEl.style.display = 'flex';
                    heroEl.style.gap = '10px';
                    heroEl.style.alignItems = 'center';
                } else {
                    heroEl.innerHTML = '<span style="color:var(--status-error)">⚠ 还没有 profile，请到「模型管理」tab 新增。</span>';
                    heroEl.style.display = 'block';
                }

                // 桶按 category，特殊：'shades:archons' 折进 shades 内部 archons 子段
                var byCategory = {};
                callsites.forEach(function(c){
                    var raw = COMPONENT_CATEGORY[c.component] || 'other';
                    if(raw === 'shades:archons'){
                        if(!byCategory.shades) byCategory.shades = {direct: {}, archons: {}};
                        else if(!byCategory.shades.archons){
                            // 已有 direct-only 形态，升级
                            byCategory.shades = {direct: byCategory.shades, archons: {}};
                        }
                        if(!byCategory.shades.archons[c.component]) byCategory.shades.archons[c.component] = [];
                        byCategory.shades.archons[c.component].push(c.purpose);
                    } else if(raw === 'shades'){
                        if(!byCategory.shades) byCategory.shades = {direct: {}, archons: {}};
                        else if(!byCategory.shades.direct){
                            byCategory.shades = {direct: {}, archons: byCategory.shades};
                        }
                        if(!byCategory.shades.direct[c.component]) byCategory.shades.direct[c.component] = [];
                        byCategory.shades.direct[c.component].push(c.purpose);
                    } else {
                        if(!byCategory[raw]) byCategory[raw] = {};
                        if(!byCategory[raw][c.component]) byCategory[raw][c.component] = [];
                        byCategory[raw][c.component].push(c.purpose);
                    }
                });

                // 占位 category 即使无 component 也渲染（如 angels 走 skill 列表分支）
                Object.keys(EMPTY_PLACEHOLDERS).forEach(function(cat){
                    if(!byCategory[cat]) byCategory[cat] = {};
                });

                var orderedHtml = CATEGORY_ORDER
                    .filter(function(cat){
                        if(cat === 'angels') return true;  // 天使段总是渲染（skill 列表）
                        if(byCategory[cat] === undefined) return false;
                        // shades 是双层 {direct, archons}，需检查内层
                        if(cat === 'shades'){
                            var d = byCategory.shades.direct || byCategory.shades;
                            var a = byCategory.shades.archons || {};
                            return Object.keys(d).length || Object.keys(a).length;
                        }
                        return Object.keys(byCategory[cat]).length || EMPTY_PLACEHOLDERS[cat];
                    })
                    .map(function(cat){
                        if(cat === 'angels') return renderAngelsSkillsSection(skills);
                        return renderCategorySection(cat, byCategory[cat], routes, hits, defaultId);
                    }).join('');

                if(!orderedHtml){
                    container.innerHTML = '<div class="empty-state">无已知调用点</div>';
                    return;
                }
                container.innerHTML = orderedHtml;
            } catch(e){
                container.innerHTML = '<div class="empty-state">加载失败: '+esc(String(e))+'</div>';
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

        // component 段头 selector 改值：先存组级路由；若该 component 下已有
        // purpose override，弹 confirm 让用户决定是否一并清空让其继承新值。
        window.saveComponentRoute = async function(selectEl){
            var component = selectEl.getAttribute('data-component');
            var pid = selectEl.value;
            var routes = window._lastRoutes || {};
            var prefix = component + ':';
            var overrideKeys = Object.keys(routes).filter(function(k){return k.indexOf(prefix) === 0;});

            try {
                // step 1: 写组级路由（pid 空 = 删 component 路由 → 走全局默认）
                var url = pid ? '/api/llm/routes/set' : '/api/llm/routes/delete';
                var body = pid ? {route_key: component, profile_id: pid} : {route_key: component};
                var r = await fetch(url, {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(body),
                });
                var d = await r.json();
                if(!d.ok){ alert('保存组级路由失败: '+(d.error || 'unknown')); return; }

                // step 2: 检测 purpose override 并征求 cascade
                if(overrideKeys.length > 0){
                    var purposeNames = overrideKeys.map(function(k){return k.substring(prefix.length);}).join('、');
                    var msg = '该 component 下有 '+overrideKeys.length+' 个 purpose 已独立设置：\\n  '+purposeNames+'\\n\\n是否一并清空让它们继承新组级值？';
                    if(confirm(msg)){
                        var rc = await fetch('/api/llm/routes/cascade-clear', {
                            method: 'POST', headers: {'Content-Type':'application/json'},
                            body: JSON.stringify({component: component}),
                        });
                        var dc = await rc.json();
                        if(!dc.ok) alert('cascade 清空失败: '+(dc.error || 'unknown'));
                    }
                }

                var flash = document.querySelector('.route-save-flash[data-flash-for="'+CSS.escape(component)+'"]');
                if(flash){
                    flash.classList.add('shown');
                    setTimeout(function(){ flash.classList.remove('shown'); }, 1500);
                }
                loadRoutes();  // 重渲染让所有 inherit 状态更新
            } catch(e){
                alert('请求失败: '+e.message);
            }
        };

        // purpose 行 selector 改值：值为空=删 purpose 路由（恢复继承）；非空=set
        window.savePurposeRoute = async function(selectEl){
            var key = selectEl.getAttribute('data-key');
            var pid = selectEl.value;
            try {
                var url = pid ? '/api/llm/routes/set' : '/api/llm/routes/delete';
                var body = pid ? {route_key: key, profile_id: pid} : {route_key: key};
                var r = await fetch(url, {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(body),
                });
                var d = await r.json();
                if(d.ok) loadRoutes();
                else alert('保存失败: '+(d.error || 'unknown'));
            } catch(e){
                alert('请求失败: '+e.message);
            }
        };

        // 「恢复继承」按钮：删 purpose 级路由 → 该行回退到继承组级
        window.restoreInherit = async function(key){
            try {
                var r = await fetch('/api/llm/routes/delete', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({route_key: key}),
                });
                var d = await r.json();
                if(d.ok) loadRoutes();
                else alert('恢复继承失败: '+(d.error || 'unknown'));
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
