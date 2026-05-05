"""主题色 / 基础 CSS / 导航 / 推送红点 HTML+JS / navigation_html 函数。"""
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

from ._nav_links_css import NAV_LINKS_CSS  # noqa: E402,F401  re-export 给老 callsite


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
    # 11 个 tab 命名风格统一：emoji + 2 字中文。
    # 「世界树」改「知识」修概念错位（世界树 = 底层存储 irminsul，不是用户面板）；
    # 「仪表盘」改「总览」更贴近用户视角；「信息流」改「订阅」更贴近用户操作语义。
    # 右侧推送红点用 📨（信封），跟左侧 🔔（订阅）emoji 不冲突。
    items = [
        ("chat", "/", "💬 对话"),
        ("dashboard", "/dashboard", "📊 总览"),
        ("tasks", "/tasks", "📋 任务"),
        ("feed", "/feed", "🔔 订阅"),
        ("sentiment", "/sentiment", "🌪️ 舆情"),
        ("wealth", "/wealth", "💰 理财"),
        ("game", "/game", "🎮 游戏"),
        ("knowledge", "/knowledge", "📚 知识"),
        ("plugins", "/plugins", "🔌 插件"),
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

