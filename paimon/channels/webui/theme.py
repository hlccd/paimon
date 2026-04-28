THEME_COLORS = """
    :root {
        --paimon-bg: #1a1625;
        --paimon-panel: #251d35;
        --paimon-panel-light: #2f2640;
        --paimon-border: #3d3450;

        --gold: #d4af37;
        --gold-light: #f4d03f;
        --gold-dark: #b8941f;

        --star: #6ec6ff;
        --star-light: #90d5ff;
        --star-dark: #4ba3d9;

        --text-primary: #f3f4f6;
        --text-secondary: #d1d5db;
        --text-muted: #9ca3af;

        --status-success: #10b981;
        --status-warning: #f59e0b;
        --status-error: #ef4444;
    }
"""

BASE_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: var(--paimon-bg);
        color: var(--text-primary);
    }

    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: var(--paimon-bg); }
    ::-webkit-scrollbar-thumb { background: var(--paimon-border); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--gold-dark); }
"""

NAVIGATION_CSS = """
    .nav-bar {
        height: 60px;
        background: var(--paimon-panel);
        border-bottom: 2px solid var(--gold-dark);
        display: flex;
        align-items: center;
        padding: 0 24px;
        box-shadow: 0 4px 6px rgba(0,0,0,.3);
    }
    .nav-logo {
        font-size: 20px;
        font-weight: 700;
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-right: 40px;
    }
"""

NAVIGATION_HTML = """
    <div class="nav-bar">
        <div class="nav-logo">Paimon</div>
    </div>
"""

NAV_LINKS_CSS = """
    .nav-links {
        display: flex;
        gap: 8px;
        align-items: center;
        flex: 1;
    }
    .nav-link {
        padding: 8px 16px;
        border-radius: 6px;
        color: var(--text-secondary);
        text-decoration: none;
        font-size: 14px;
        font-weight: 500;
        transition: all 0.2s;
        border: 1px solid transparent;
    }
    .nav-link:hover {
        color: var(--text-primary);
        background: var(--paimon-panel-light);
    }
    .nav-link.active {
        color: var(--gold);
        background: var(--paimon-panel-light);
        border-color: var(--gold-dark);
    }

    /* ===== 全局推送红点（所有面板可见）===== */
    .nav-bell {
        position: relative;
        margin-left: auto;
        margin-right: 12px;
        padding: 8px 12px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 18px;
        color: var(--text-secondary);
        transition: all 0.2s;
        background: transparent;
        border: none;
    }
    .nav-bell:hover { color: var(--gold); background: var(--paimon-panel-light); }
    .nav-bell.has-unread { color: var(--gold-light); }
    .nav-bell .badge {
        position: absolute;
        top: 2px;
        right: 2px;
        min-width: 18px;
        height: 18px;
        padding: 0 5px;
        background: var(--status-error);
        color: white;
        border-radius: 9px;
        font-size: 11px;
        font-weight: 600;
        line-height: 18px;
        text-align: center;
        display: none;
    }
    .nav-bell.has-unread .badge { display: inline-block; }

    /* ===== 业务面板内嵌日报历史样式（sentiment / wealth 复用）===== */
    .digest-section {
        background: var(--paimon-panel);
        border: 1px solid var(--paimon-border);
        border-radius: 10px;
        padding: 16px;
        margin-top: 24px;
        /* 公告区固定 max-height，内容多时内部滚动；保持页面整体节奏不被拉长。
           35vh ≈ 概览 + 行业趋势 Top5 + 1-2 行 buffer；P0/P1/新入选滚动可见 */
        display: flex; flex-direction: column;
        max-height: 35vh;
    }
    /* 公告区滚动主体：head 不动，列表 + 历史区在这里滚 */
    .digest-section > .digest-scroll {
        flex: 1; overflow-y: auto; padding-right: 4px; /* 给滚动条留点缝 */
    }
    .digest-section .ds-head {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 12px; gap: 12px;
        flex-shrink: 0;
    }
    .digest-section .ds-head h2 { font-size: 15px; color: var(--text-primary); font-weight: 600; }
    .digest-section .ds-tools { display: flex; gap: 8px; align-items: center; }
    .digest-section .ds-tools input {
        padding: 4px 10px;
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-radius: 4px;
        color: var(--text-primary);
        font-size: 12px;
        width: 200px;
    }
    .digest-section .ds-tools input:focus { outline: none; border-color: var(--gold-dark); }
    .digest-section .ds-tools button {
        padding: 4px 10px;
        background: var(--paimon-panel-light);
        color: var(--text-secondary);
        border: 1px solid var(--paimon-border);
        border-radius: 4px;
        cursor: pointer; font-size: 12px;
    }
    .digest-section .ds-tools button:hover { border-color: var(--gold-dark); color: var(--gold); }
    .digest-list {
        display: flex; flex-direction: column; gap: 8px;
        max-height: 60vh; overflow-y: auto;
    }

    /* ===== 公告卡片（最近几条直接展开式，类似聊天气泡）===== */
    .digest-bulletin {
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-left: 3px solid var(--gold);
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .digest-bulletin.read {
        border-left-color: var(--paimon-border);
        opacity: 0.85;
    }
    .digest-bulletin .db-head {
        display: flex; justify-content: space-between; align-items: center;
        gap: 8px; margin-bottom: 10px;
        padding-bottom: 8px;
        border-bottom: 1px dashed var(--paimon-border);
    }
    .digest-bulletin .db-head-left { display: flex; align-items: center; gap: 8px; }
    .digest-bulletin .db-source {
        color: var(--gold);
        font-weight: 600;
        font-size: 14px;
    }
    .digest-bulletin .db-unread-dot {
        width: 8px; height: 8px;
        border-radius: 50%;
        background: var(--status-warning);
        animation: db-pulse 2s ease-in-out infinite;
    }
    @keyframes db-pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
    }
    .digest-bulletin .db-time {
        color: var(--text-muted);
        font-size: 12px;
        font-family: monospace;
    }
    .digest-bulletin .db-mark-read {
        background: transparent;
        border: 1px solid var(--paimon-border);
        color: var(--text-muted);
        font-size: 11px;
        padding: 2px 10px;
        border-radius: 4px;
        cursor: pointer;
        margin-left: 10px;
    }
    .digest-bulletin .db-mark-read:hover {
        color: var(--gold); border-color: var(--gold-dark);
    }
    /* db-body 实际渲染由 .md-body 控制；这里只作 fallback（CDN 加载失败时仍能显示纯文本）*/
    .digest-bulletin .db-body {
        color: var(--text-primary);
        font-size: 13px;
        line-height: 1.7;
    }
    .digest-bulletins-empty {
        text-align: center; color: var(--text-muted);
        padding: 24px; font-size: 13px;
    }
    .digest-running-bar {
        display: flex; align-items: center; gap: 8px;
        padding: 10px 14px; margin-bottom: 12px;
        background: rgba(255,180,80,.08);
        border: 1px solid rgba(255,180,80,.28);
        border-radius: 8px;
        color: var(--gold);
        font-size: 12.5px;
    }
    .digest-running-bar .dot {
        width: 8px; height: 8px; border-radius: 50%;
        background: var(--gold);
        animation: paimon-pulse 1.1s ease-in-out infinite;
        flex-shrink: 0;
    }
    .digest-error-bar {
        display: flex; align-items: flex-start; gap: 8px;
        padding: 10px 14px; margin-bottom: 12px;
        background: rgba(255,80,80,.10);
        border: 1px solid rgba(255,80,80,.35);
        border-radius: 8px;
        color: #e88;
        font-size: 12.5px;
    }
    .digest-error-bar .err-msg { flex: 1; line-height: 1.5; word-break: break-all; }
    .digest-error-bar .err-close {
        background: transparent; border: none; color: #e88;
        cursor: pointer; padding: 0 4px; font-size: 16px; line-height: 1;
    }
    .digest-error-bar .err-close:hover { color: #faa; }
    .digest-bulletin .db-running {
        display: inline-flex; align-items: center; gap: 5px;
        padding: 2px 8px; font-size: 11px;
        color: var(--gold);
        background: rgba(255,180,80,.12);
        border: 1px solid rgba(255,180,80,.35);
        border-radius: 10px;
        margin-left: 6px;
    }
    .digest-bulletin .db-running::before {
        content: ''; width: 7px; height: 7px; border-radius: 50%;
        background: var(--gold);
        animation: paimon-pulse 1.1s ease-in-out infinite;
    }
    @keyframes paimon-pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: .35; transform: scale(.65); }
    }
    .digest-history-toggle {
        text-align: center;
        padding: 8px;
        margin-top: 12px;
        border-top: 1px dashed var(--paimon-border);
    }
    .digest-history-toggle button {
        background: transparent;
        border: none;
        color: var(--text-muted);
        cursor: pointer;
        font-size: 12px;
    }
    .digest-history-toggle button:hover { color: var(--gold); }
    .push-item {
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-radius: 6px;
        padding: 10px 12px;
        cursor: pointer;
        transition: border-color 0.15s;
    }
    .push-item:hover { border-color: var(--gold-dark); }
    .push-item.unread { border-left: 3px solid var(--gold); padding-left: 10px; }
    .push-item-head {
        display: flex; justify-content: space-between; align-items: center;
        gap: 8px; margin-bottom: 4px;
    }
    .push-item-source {
        color: var(--gold);
        font-weight: 600;
        font-size: 13px;
    }
    .push-item-time {
        color: var(--text-muted);
        font-size: 11px;
        font-family: monospace;
        flex-shrink: 0;
    }
    .push-item-preview {
        color: var(--text-secondary);
        font-size: 12px;
        line-height: 1.5;
        max-height: 3em;
        overflow: hidden;
        text-overflow: ellipsis;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
    }
    .push-item-body {
        margin-top: 8px;
        padding-top: 8px;
        border-top: 1px dashed var(--paimon-border);
        color: var(--text-secondary);
        font-size: 12px;
        line-height: 1.7;
        display: none;
    }
    .push-item.expanded .push-item-body { display: block; }
    .push-item.expanded .push-item-preview { display: none; }
    .push-empty {
        text-align: center;
        color: var(--text-muted);
        padding: 40px 20px;
        font-size: 13px;
    }

    /* ===== Markdown 渲染样式（公告卡 / 历史卡 通用）===== */
    .md-body {
        color: var(--text-primary);
        font-size: 13px;
        line-height: 1.7;
        word-break: break-word;
    }
    .md-body > *:first-child { margin-top: 0; }
    .md-body > *:last-child { margin-bottom: 0; }
    .md-body p { margin: 0 0 8px 0; }
    .md-body ul, .md-body ol { margin: 4px 0 8px 20px; padding: 0; }
    .md-body li { margin: 2px 0; }
    .md-body h1, .md-body h2 {
        font-size: 14px; color: var(--gold);
        margin: 12px 0 6px 0; font-weight: 600;
    }
    .md-body h3, .md-body h4 {
        font-size: 13px; color: var(--text-primary);
        margin: 10px 0 4px 0; font-weight: 600;
    }
    .md-body blockquote {
        margin: 4px 0 10px 0; padding: 8px 12px;
        border-left: 3px solid var(--gold-dark);
        background: rgba(212,175,55,.06);
        color: var(--text-secondary);
        border-radius: 0 6px 6px 0;
    }
    .md-body blockquote > *:first-child { margin-top: 0; }
    .md-body blockquote > *:last-child { margin-bottom: 0; }
    .md-body a { color: var(--star); text-decoration: none; }
    .md-body a:hover { text-decoration: underline; color: var(--star-light); }
    .md-body strong { color: var(--gold-light); font-weight: 600; }
    .md-body em { color: var(--text-secondary); font-style: italic; }
    .md-body code {
        padding: 1px 5px;
        font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
        font-size: 12px;
        background: var(--paimon-panel-light);
        border-radius: 3px;
        color: var(--gold-light);
    }
    .md-body pre {
        margin: 6px 0 10px 0;
        padding: 10px 12px;
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-radius: 6px;
        overflow-x: auto;
        font-size: 12px;
    }
    .md-body pre code { background: transparent; padding: 0; }
    .md-body hr {
        border: none; border-top: 1px dashed var(--paimon-border);
        margin: 10px 0;
    }
"""

GLOBAL_PUSH_BELL_HTML = """
    <button id="navBell" class="nav-bell" onclick="window.gotoLatestDigests()" title="未读日报（点击跳转）">
        📨<span class="badge" id="navBellBadge"></span>
    </button>
    <!-- Markdown 渲染：marked.js (parse) + DOMPurify (XSS sanitize)，公告卡 + 历史卡共用 -->
    <script src="https://cdn.jsdelivr.net/npm/marked@13.0.3/marked.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js"></script>
"""

# 全局只剩两个职责：
# 1. 30s 轮询 /api/push_archive/unread_count 刷新红点徽章
# 2. 点击红点 → 按未读最多的 actor 跳到对应面板的 digest 区
#    （/sentiment#digest 或 /wealth#digest；hash 由各面板的 JS 自动滚动 + 高亮）
GLOBAL_PUSH_BELL_SCRIPT = r"""
<script>
(function(){
    // Markdown 渲染（marked + DOMPurify CDN 加载好后注册到 window）
    // 兜底：若 CDN 加载失败 / 还没就绪，退化为纯文本（HTML escape）
    function _escFallback(s){
        return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')
            .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
    window.renderMarkdown = function(text){
        if(typeof window.marked === 'undefined' || typeof window.DOMPurify === 'undefined'){
            // CDN 没加载好就退到 pre-wrap 纯文本
            return '<div style="white-space:pre-wrap">' + _escFallback(text) + '</div>';
        }
        try{
            // marked options: GFM 风格 + 自动换行（单换行 = <br>，更贴近聊天气泡）
            var html = window.marked.parse(text || '', { breaks: true, gfm: true });
            return window.DOMPurify.sanitize(html, {
                // 只允许标准 markdown 产物的标签 + 链接 target=_blank
                ADD_ATTR: ['target', 'rel'],
            });
        }catch(e){
            return _escFallback(text);
        }
    };

    var _grouped = {};

    async function refreshUnreadBadge(){
        try{
            var r=await fetch('/api/push_archive/unread_count');
            var d=await r.json();
            _grouped = d.by_actor || {};
            var bell=document.getElementById('navBell');
            var badge=document.getElementById('navBellBadge');
            if(!bell||!badge)return;
            var total=Number(d.total||0);
            if(total>0){
                bell.classList.add('has-unread');
                badge.textContent=total>99?'99+':String(total);
                // tooltip 提示分组（"风神 3 / 岩神 1"）
                var parts=[];
                Object.keys(_grouped).sort().forEach(function(a){
                    if(_grouped[a]>0) parts.push(a+' '+_grouped[a]);
                });
                bell.title = parts.length ? parts.join(' / ')+'，点击查看' : '点击查看';
            }else{
                bell.classList.remove('has-unread');
                badge.textContent='';
                bell.title = '暂无未读';
            }
        }catch(e){}
    }

    // 点击红点 → 按未读最多的 actor 跳转对应面板（沉淀到业务页面，而非全局抽屉）
    window.gotoLatestDigests = function(){
        var venti = Number(_grouped['风神']||0);
        var zhongli = Number(_grouped['岩神']||0);
        var target = '/sentiment';   // 默认风神
        if(venti===0 && zhongli>0) target = '/wealth';
        // hash 让目标面板的 JS 自动滚动 + 展开未读
        location.href = target + '#digest';
    };

    // 暴露给面板：标记已读后立即刷新红点（无需等 30s 轮询）
    window.refreshNavBadge = refreshUnreadBadge;

    refreshUnreadBadge();
    setInterval(refreshUnreadBadge, 30000);
})();
</script>
"""


def navigation_html(active: str = "chat") -> str:
    items = [
        ("chat", "/", "对话"),
        ("dashboard", "/dashboard", "仪表盘"),
        ("tasks", "/tasks", "任务"),
        ("feed", "/feed", "信息流"),
        ("sentiment", "/sentiment", "🌬️ 舆情"),
        ("wealth", "/wealth", "理财"),
        ("preferences", "/preferences", "偏好"),
        ("plugins", "/plugins", "插件"),
        ("selfcheck", "/selfcheck", "🩺 自检"),
        ("llm", "/llm", "🧠 模型"),
    ]
    links = "".join(
        f'<a href="{href}" class="nav-link{" active" if key == active else ""}">{label}</a>'
        for key, href, label in items
    )
    # 全局推送红点 + 抽屉 + 脚本一起返回（所有面板 zero-change 接入）
    return f"""
    <div class="nav-bar">
        <div class="nav-logo">Paimon</div>
        <div class="nav-links">{links}</div>
        {GLOBAL_PUSH_BELL_HTML}
    </div>
    {GLOBAL_PUSH_BELL_SCRIPT}
    """
