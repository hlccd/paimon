"""岩神 · 理财（红利股追踪）面板

3 个 tab:
- 推荐选股: watchlist JOIN 最新 snapshot
- 评分排行: 最新 snapshot top 100
- 变化事件: 近 30 天 changes 时间轴

单股详情 modal: Chart.js 画 90 天评分折线 + 维度卡片 + 原始指标。
顶部: 统计卡片 + 触发扫描按钮组。
"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)


WEALTH_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1280px; margin: 0 auto; padding: 24px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .page-header .sub { font-size: 13px; color: var(--text-muted); margin-top: 4px; }

    .actions-bar { display: flex; gap: 8px; align-items: flex-start; }
    .btn-scan-cell { display: flex; flex-direction: column; align-items: center; gap: 2px; }
    .btn-scan-hint {
        font-size: 11px; color: var(--text-muted); line-height: 1.2;
        white-space: nowrap; min-height: 14px;
    }
    .btn-scan {
        padding: 8px 14px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .btn-scan:hover { border-color: var(--gold-dark); color: var(--gold); }
    .btn-scan.primary {
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        color: #000; border: none; font-weight: 600;
    }
    .btn-scan:disabled { opacity: .4; cursor: not-allowed; }

    .stats-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 24px;
    }
    .stat-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 14px 16px; text-align: center;
    }
    .stat-num { font-size: 22px; font-weight: 700; color: var(--gold); }
    .stat-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

    /* 大框 digest-section.dt-twin：内部左右双栏，各自独立 head（参考风神 ds-head 形态）。
       双栏内容比单栏多，max-height 从 theme.py 默认 35vh 提到 60vh */
    #digest.dt-twin { max-height: 60vh; }
    #digest.dt-twin > .dt-body {
        flex: 1; display: flex; gap: 16px; min-height: 0;
    }
    #digest.dt-twin > .dt-body > .dt-col {
        flex: 1; min-width: 0;
        display: flex; flex-direction: column;
    }
    /* 左栏直接是日报内容（与大框 ds-head 标题对应），不重复小 head；
       右栏关注股资讯区分于左栏，加一行小子标题 */
    .news-col-head {
        display: flex; justify-content: space-between; align-items: baseline;
        margin-bottom: 10px; flex-shrink: 0;
        padding-bottom: 6px; border-bottom: 1px solid var(--paimon-border);
    }
    .news-col-head .ncl-title { font-size: 13px; color: var(--text-primary); font-weight: 600; }
    .news-col-head .ncl-hint { font-size: 11px; color: var(--text-muted); }
    .dt-col-scroll { flex: 1; overflow-y: auto; padding-right: 4px; }

    .news-card {
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-left: 3px solid var(--gold);
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 10px;
    }
    .news-card .nc-head {
        display: flex; justify-content: space-between; align-items: center;
        gap: 8px; margin-bottom: 6px;
        padding-bottom: 6px;
        border-bottom: 1px dashed var(--paimon-border);
    }
    .news-card .nc-stock { color: var(--gold); font-weight: 600; font-size: 13px; font-family: monospace; }
    .news-card .nc-time { color: var(--text-muted); font-size: 11px; font-family: monospace; }
    .news-card .nc-body { font-size: 12px; line-height: 1.6; }
    .news-section-empty {
        color: var(--text-muted); font-size: 12px; font-style: italic;
        padding: 16px 0; text-align: center;
    }

    .tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--paimon-border); }
    .tab-btn {
        padding: 10px 20px; background: transparent; border: none; color: var(--text-muted);
        cursor: pointer; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active { color: var(--gold); border-bottom-color: var(--gold); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    .stock-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .stock-table th, .stock-table td {
        padding: 10px 12px; border-bottom: 1px solid var(--paimon-border); text-align: left;
    }
    .stock-table th {
        color: var(--gold); font-weight: 600; font-size: 12px; background: var(--paimon-panel);
        position: sticky; top: 0; z-index: 1;
    }
    .stock-table tbody tr { cursor: pointer; transition: background .1s; }
    .stock-table tbody tr:hover td { background: var(--paimon-panel); }
    .stock-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .stock-table td.code { color: var(--text-muted); font-family: monospace; font-size: 12px; }
    .stock-table .score-high { color: var(--status-success); font-weight: 600; }
    .stock-table .score-mid { color: var(--gold); }
    .stock-table .score-low { color: var(--text-muted); }
    /* hover 行才显示「+ 关注」按钮，避免视觉噪音；色调与 .uw-btn 对齐 */
    .stock-table td.row-actions { width: 72px; text-align: center; padding: 4px 6px; }
    .stock-table .addw-btn {
        opacity: 0; transition: opacity .15s, background .12s, border-color .12s;
        padding: 3px 12px; font-size: 11px; cursor: pointer;
        background: rgba(212,175,55,.08);
        color: var(--gold);
        border: 1px solid rgba(212,175,55,.4);
        border-radius: 4px;
        white-space: nowrap; line-height: 1.5;
    }
    /* 默认全部不显示，仅 row hover 时显示（已关注的也不常驻，避免视觉噪音） */
    .stock-table tbody tr:hover .addw-btn { opacity: 1; }
    .stock-table .addw-btn:hover {
        background: rgba(212,175,55,.18);
        border-color: var(--gold);
    }
    .stock-table .addw-btn.added {
        color: var(--status-success);
        border-color: rgba(76,175,80,.5);
        background: rgba(76,175,80,.1);
        cursor: default;
    }
    .stock-table .addw-btn.added:hover { background: rgba(76,175,80,.1); border-color: rgba(76,175,80,.5); }
    .stock-table .addw-btn:disabled { cursor: not-allowed; }
    .advice { font-size: 12px; color: var(--text-secondary); }

    /* 变化事件时间轴 */
    .change-list { display: flex; flex-direction: column; gap: 10px; }
    .change-item {
        background: var(--paimon-panel); border-left: 4px solid var(--paimon-border);
        border-radius: 6px; padding: 10px 16px; font-size: 13px;
    }
    .change-item.entered { border-left-color: var(--status-success); }
    .change-item.exited { border-left-color: var(--status-error); }
    .change-item.score-up { border-left-color: var(--star); }
    .change-item.score-down { border-left-color: var(--status-warning); }
    .change-meta { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

    /* Modal */
    .modal-backdrop {
        position: fixed; top:0; left:0; width:100%; height:100%;
        background: rgba(0,0,0,0.6); z-index: 100; display: none;
        align-items: center; justify-content: center; padding: 20px;
    }
    .modal-backdrop.show { display: flex; }
    .modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 12px; max-width: 880px; width: 100%; max-height: 90vh;
        overflow-y: auto; padding: 24px;
    }
    .modal-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px; }
    .modal-title { font-size: 20px; font-weight: 600; color: var(--text-primary); }
    .modal-sub { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
    .btn-close {
        background: transparent; border: none; color: var(--text-muted);
        font-size: 24px; cursor: pointer; padding: 0 8px;
    }
    .btn-close:hover { color: var(--text-primary); }

    .chart-wrap { margin-bottom: 20px; }
    .chart-wrap canvas { max-height: 260px; }
    .fallback-chart {
        background: var(--paimon-bg); padding: 12px; border-radius: 6px;
        font-size: 12px; color: var(--text-muted); font-family: monospace;
    }

    .dim-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 16px; }
    .dim-card {
        background: var(--paimon-bg); padding: 10px 12px; border-radius: 6px;
    }
    .dim-label { font-size: 11px; color: var(--text-muted); }
    .dim-value { font-size: 18px; font-weight: 600; color: var(--gold-light); }

    .raw-table { width: 100%; font-size: 13px; }
    .raw-table td { padding: 4px 8px; }
    .raw-table td:first-child { color: var(--text-muted); width: 40%; }

    .reasons-box {
        margin-top: 16px; padding: 12px; background: var(--paimon-bg); border-radius: 6px;
        font-size: 12px; line-height: 1.6; color: var(--text-secondary); white-space: pre-wrap;
    }
    .advice-box {
        margin-top: 10px; padding: 8px 12px; background: rgba(212,175,55,.08);
        border: 1px solid var(--gold-dark); border-radius: 6px;
        font-size: 13px; color: var(--gold-light);
    }

    .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 14px; }
    .loading { display: inline-block; padding: 2px 10px; color: var(--text-muted); font-size: 12px; }

    /* 未读岩神 digest banner */
    .unread-banner {
        display: none;
        background: linear-gradient(90deg, rgba(212,175,55,.12), rgba(110,198,255,.04));
        border: 1px solid var(--gold-dark);
        border-radius: 8px;
        padding: 10px 16px;
        margin-bottom: 16px;
        font-size: 13px;
        color: var(--text-primary);
        cursor: pointer;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        transition: background 0.15s;
    }
    .unread-banner.show { display: flex; }
    .unread-banner:hover { background: linear-gradient(90deg, rgba(212,175,55,.2), rgba(110,198,255,.06)); }
    .unread-banner b { color: var(--gold); font-weight: 700; }
    .unread-banner .ub-action { color: var(--gold); font-size: 12px; flex-shrink: 0; }

    /* ========= 我的关注（用户 watchlist）========= */
    .uw-toolbar {
        display: flex; gap: 8px; align-items: center;
        padding: 12px; background: var(--paimon-panel); border-radius: 8px;
        margin-bottom: 12px; flex-wrap: wrap;
    }
    .uw-toolbar input {
        background: var(--paimon-bg); border: 1px solid var(--paimon-border);
        color: var(--text-primary); border-radius: 6px; padding: 6px 10px; font-size: 13px;
    }
    .uw-toolbar input:focus { outline: none; border-color: var(--gold-dark); }
    .uw-toolbar input[type=number] { width: 80px; }
    .uw-toolbar input#uwCodeInput { width: 140px; }
    .uw-toolbar input#uwNoteInput { flex: 1; min-width: 120px; }
    .uw-toolbar label { font-size: 12px; color: var(--text-muted); }
    .uw-btn {
        padding: 6px 14px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .uw-btn:hover { border-color: var(--gold-dark); color: var(--gold); }
    .uw-btn.primary {
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        color: #000; border: none; font-weight: 600;
    }
    .uw-btn.danger:hover { color: var(--status-error); border-color: var(--status-error); }

    /* 关注股表不绑行点击，覆盖 .stock-table 的 pointer 避免"可点击"误导 */
    .uw-table tbody tr { cursor: default; }
    .uw-table td.code { font-family: monospace; color: var(--text-muted); }
    /* 列对齐：每列 th/td 方向必须一致，否则标题和内容视觉会错成两端。
       默认 .stock-table 里 th 左对齐、td.num 右对齐 → 数字列视觉错位。
       这里按列定义 3 种对齐，th 和 td 都挂同名 class。 */
    .uw-table th.c-l, .uw-table td.c-l { text-align: left; }
    .uw-table th.c-r, .uw-table td.c-r { text-align: right; }
    .uw-table th.c-c, .uw-table td.c-c { text-align: center; }
    /* PE/PB 列：数字本身在固定宽度内右对齐，跨行数字纵向对齐；
       后跟 bar + 百分比，整组靠左排列。 */
    .uw-table .pe-num {
        display: inline-block; min-width: 42px; text-align: right;
        font-variant-numeric: tabular-nums;
    }
    .uw-table td.note {
        font-size: 12px; color: var(--text-muted); max-width: 140px;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .uw-change.pos { color: var(--status-error); font-weight: 600; }  /* A 股红涨 */
    .uw-change.neg { color: var(--status-success); font-weight: 600; } /* 绿跌 */
    .uw-change.flat { color: var(--text-muted); }

    .uw-spark { width: 88px; height: 28px; vertical-align: middle; }
    .uw-spark polyline { fill: none; stroke: var(--gold); stroke-width: 1.5; }
    .uw-spark.up polyline { stroke: var(--status-error); }
    .uw-spark.down polyline { stroke: var(--status-success); }

    /* 三档分位条：0~30% 低估区（绿）/ 30~70% 正常区（灰）/ 70~100% 高估区（红）
       两条分割线标出 0.3 / 0.7 阈值，marker 是当前值位置 */
    .uw-pctbar {
        position: relative; display: inline-block;
        width: 80px; height: 10px;
        background: linear-gradient(90deg,
            var(--status-success) 0%, var(--status-success) 30%,
            var(--paimon-border) 30%, var(--paimon-border) 70%,
            var(--status-error) 70%, var(--status-error) 100%);
        border-radius: 4px; vertical-align: middle; margin-left: 6px; opacity: .55;
    }
    /* 0.3 / 0.7 两条分割线 */
    .uw-pctbar::before, .uw-pctbar::after {
        content: ''; position: absolute; top: -1px; bottom: -1px; width: 1px;
        background: var(--paimon-bg); opacity: .7;
    }
    .uw-pctbar::before { left: 30%; }
    .uw-pctbar::after  { left: 70%; }
    /* 当前值 marker：黑白双色三角，任何底色都看得清 */
    .uw-pctbar .marker {
        position: absolute; top: -3px; width: 2px; height: 16px;
        background: var(--text-primary); border-radius: 1px; opacity: 1;
        box-shadow: 0 0 2px rgba(0,0,0,.6);
    }
    .uw-pct-label { font-size: 11px; color: var(--text-muted); margin-left: 4px; font-variant-numeric: tabular-nums; }
    .uw-pct-label.low  { color: var(--status-success); }
    .uw-pct-label.high { color: var(--status-error); }

    /* ========= 📰 关注股资讯订阅（同游戏面板模式）========= */
    /* 资讯展开行（紧贴每个 stock 数据行下方，默认隐藏，点击 📰 详情展开） */
    .uw-news-row { display: none; }
    .uw-news-row.open { display: table-row; }
    .uw-news-row > td { padding: 0; background: var(--paimon-bg); }
    .uw-news-wrap { padding: 10px 14px; }

    /* 资讯紧凑行（grid: toggle | icon | text | run-btn） */
    .stock-news-line {
        display: grid;
        grid-template-columns: auto auto 1fr auto;
        gap: 10px; align-items: center;
        padding: 6px 10px;
        background: var(--paimon-panel);
        border-radius: 6px;
        border-left: 2px solid var(--paimon-border);
        font-size: 12px; color: var(--text-secondary);
        transition: border-color .15s, background .15s;
    }
    .stock-news-line.on { border-left-color: var(--status-success); }
    .stock-news-line.err { border-left-color: var(--status-error); background: rgba(239,68,68,.04); }
    .stock-news-line.busy { border-left-color: var(--gold); background: rgba(245,158,11,.06); }
    .stock-news-line.busy .news-toggle { color: var(--gold); }
    .stock-news-line.busy .news-toggle .dot { background: var(--gold); animation: news-pulse 1.2s ease-in-out infinite; }
    @keyframes news-pulse { 0%,100% { opacity:.4; } 50% { opacity:1; } }
    .stock-news-line .news-toggle {
        display: inline-flex; align-items: center; gap: 5px;
        cursor: pointer; user-select: none;
        color: var(--text-muted); font-size: 11px;
    }
    .stock-news-line .news-toggle .dot {
        width: 7px; height: 7px; border-radius: 50%;
        background: var(--text-muted); transition: background .15s;
    }
    .stock-news-line.on .news-toggle { color: var(--status-success); }
    .stock-news-line.on .news-toggle .dot { background: var(--status-success); }
    .stock-news-line .news-icon { color: var(--gold); font-size: 12px; }
    .stock-news-line .news-text {
        color: var(--text-secondary);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        min-width: 0;
    }
    .stock-news-line .news-text .meta { color: var(--text-muted); margin-right: 6px; }
    .stock-news-line .news-text .err-msg { color: var(--status-error); }
    .stock-news-line .news-run {
        padding: 3px 10px; font-size: 11px;
        background: transparent; color: var(--text-muted);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        cursor: pointer; transition: border-color .15s, color .15s;
    }
    .stock-news-line .news-run:hover { border-color: var(--gold-dark); color: var(--gold); }
    .stock-news-line .news-run:disabled { opacity: .5; cursor: progress; }

    /* 推送列表（左右两栏：左标题列表 / 右选中项 md 详情）*/
    .stock-news-pushes:empty { display: none; }
    .stock-news-pushes {
        margin-top: 10px;
        padding: 10px 14px;
        background: var(--paimon-panel);
        border: 1px solid var(--paimon-border);
        border-radius: 8px;
    }
    .news-pushes-head {
        font-size: 12px; color: var(--text-secondary); font-weight: 600;
        margin-bottom: 8px;
    }
    .news-pushes-hint { font-size: 10px; color: var(--text-muted); font-weight: 400; margin-left: 6px; }

    /* 双栏布局：左边窄（标题列表）/ 右边宽（详情） */
    .news-pushes-2col {
        display: flex;
        gap: 12px;
        align-items: stretch;
    }
    .news-pushes-titlebar {
        flex: 0 0 220px;
        list-style: none; padding: 0; margin: 0;
        max-height: 460px; overflow-y: auto;
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-radius: 6px;
    }
    .news-title-row {
        padding: 8px 10px;
        cursor: pointer; user-select: none;
        border-bottom: 1px solid var(--paimon-border);
        border-left: 2px solid transparent;
        transition: background .15s, border-color .15s;
    }
    .news-title-row:last-child { border-bottom: none; }
    .news-title-row:hover { background: var(--paimon-panel-light); }
    .news-title-row.active {
        background: rgba(245,158,11,.10);
        border-left-color: var(--gold);
    }
    .news-title-row .news-push-time {
        display: block;
        font-family: 'SF Mono', Consolas, monospace;
        font-size: 10px; color: var(--text-muted);
        margin-bottom: 3px;
    }
    .news-title-row .news-push-title {
        display: block;
        font-size: 12px; color: var(--text-primary);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .news-title-row.active .news-push-title { color: var(--gold-light); }
    .news-pushes-detail {
        flex: 1; min-width: 0;
        padding: 12px 14px;
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-radius: 6px;
        max-height: 460px; overflow-y: auto;
    }
    .news-pushes-detail-empty {
        color: var(--text-muted); font-size: 12px;
        font-style: italic; text-align: center; padding: 20px 0;
    }
    .news-push-body.markdown-body {
        font-size: 13px; color: var(--text-primary); line-height: 1.6;
        padding: 6px 4px;
    }
    .news-push-body h1, .news-push-body h2, .news-push-body h3,
    .news-push-body h4, .news-push-body h5, .news-push-body h6 {
        color: var(--gold); font-weight: 600; margin: 12px 0 6px; line-height: 1.3;
    }
    .news-push-body h1 { font-size: 16px; }
    .news-push-body h2 { font-size: 15px; }
    .news-push-body h3 { font-size: 14px; }
    .news-push-body h4, .news-push-body h5, .news-push-body h6 { font-size: 13px; }
    .news-push-body p { margin: 6px 0; }
    .news-push-body ul, .news-push-body ol { margin: 6px 0; padding-left: 22px; }
    .news-push-body li { margin: 2px 0; }
    .news-push-body a { color: var(--gold-light); text-decoration: underline; }
    .news-push-body a:hover { color: var(--gold); }
    .news-push-body code {
        background: var(--paimon-bg); padding: 1px 5px; border-radius: 3px;
        font-family: 'SF Mono', Consolas, monospace; font-size: 12px;
        color: var(--gold-light);
    }
    .news-push-body pre {
        background: var(--paimon-bg); padding: 8px 10px; border-radius: 5px;
        overflow-x: auto; margin: 6px 0;
    }
    .news-push-body pre code { background: transparent; padding: 0; color: var(--text-primary); }
    .news-push-body blockquote {
        border-left: 3px solid var(--gold-dark);
        padding: 2px 10px; margin: 6px 0; color: var(--text-muted);
    }
    .news-push-body strong { color: var(--text-primary); font-weight: 600; }
    .news-push-body hr { border: none; border-top: 1px dashed var(--paimon-border); margin: 10px 0; }

    /* 数据行的"📰 资讯"按钮：跟 .uw-btn 同大小（操作列 3 按钮视觉一致）*/
    .uw-news-toggle-btn {
        padding: 6px 14px; font-size: 13px;
        background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 6px;
        cursor: pointer; transition: border-color .15s, color .15s, background .15s;
    }
    .uw-news-toggle-btn:hover { border-color: var(--gold-dark); color: var(--gold); }
    .uw-news-toggle-btn.has-news {
        background: rgba(245,158,11,.10);
        border-color: var(--gold-dark);
        color: var(--gold);
        font-weight: 500;
    }
"""


WEALTH_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>岩神 · 理财</h1>
                <div class="sub">A 股红利股追踪（评分 + 行业均衡 + 变化检测）</div>
            </div>
            <div class="actions-bar">
                <div class="btn-scan-cell">
                    <button class="btn-scan" id="btnRescore" onclick="triggerScan('rescore')">重评分</button>
                    <span class="btn-scan-hint">&nbsp;</span>
                </div>
                <div class="btn-scan-cell">
                    <button class="btn-scan" id="btnDaily" onclick="triggerScan('daily')">日更</button>
                    <span class="btn-scan-hint" id="dailyHint">候选池 -</span>
                </div>
                <div class="btn-scan-cell">
                    <button class="btn-scan primary" id="btnFull" onclick="triggerScan('full')">全扫描</button>
                    <span class="btn-scan-hint" id="fullHint">全市场 ~5500</span>
                </div>
                <div class="btn-scan-cell">
                    <button class="btn-scan" onclick="refreshAll()">刷新</button>
                    <span class="btn-scan-hint">&nbsp;</span>
                </div>
            </div>
        </div>

        <!-- 大框：head 在最顶（岩神放上面，参考风神形态），日期工具放右边。
             body 双栏：左 = 日报内容（无小 head），右 = 关注股资讯（带 📰 小 head 区分） -->
        <div id="digest" class="digest-section dt-twin">
            <div class="ds-head">
                <h2>📨 岩神 · 理财日报 <span id="zhongliBulletinHint" style="font-size:12px;color:var(--text-muted);font-weight:normal;margin-left:8px"></span></h2>
                <div class="ds-tools">
                    <button onclick="window.zhongliDayShift(-1)" title="前一天">←</button>
                    <input type="date" id="zhongliDateInput" onchange="window.zhongliDateChange()" />
                    <button onclick="window.zhongliDayShift(1)" title="后一天">→</button>
                    <button onclick="window.zhongliJumpToday()" title="跳到今天">今天</button>
                    <button onclick="window.markAllZhongliRead()">全部已读</button>
                </div>
            </div>
            <div class="dt-body">
                <div class="dt-col dt-col-bulletins">
                    <div class="dt-col-scroll">
                        <div id="zhongliRunningBar" style="display:none"></div>
                        <div id="zhongliErrorBar" style="display:none"></div>
                        <div id="zhongliBulletins">
                            <div class="digest-bulletins-empty">加载中...</div>
                        </div>
                        <div class="digest-history-toggle">
                            <button onclick="window.toggleZhongliHistory()" id="zhongliHistoryToggleBtn">
                                🔍 搜索历史 ↓
                            </button>
                        </div>
                        <div id="zhongliHistoryWrap" style="display:none;margin-top:12px">
                            <input id="zhongliDigestSearch" placeholder="搜索历史内容（Enter 应用）"
                                style="width:100%;padding:6px 10px;background:var(--paimon-bg);border:1px solid var(--paimon-border);border-radius:4px;color:var(--text-primary);font-size:12px;margin-bottom:10px" />
                            <div id="zhongliDigestList" class="digest-list">
                                <div class="push-empty">加载中...</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="dt-col dt-col-news">
                    <div class="news-col-head">
                        <span class="ncl-title">📰 关注股资讯</span>
                        <span id="newsPanelHint" class="ncl-hint">加载中</span>
                    </div>
                    <div class="dt-col-scroll">
                        <div id="newsPanelList"><div class="news-section-empty">加载中…</div></div>
                    </div>
                </div>
            </div>
        </div>

        <div class="stats-row">
            <div class="stat-card"><div class="stat-num" id="statWatchlist">-</div><div class="stat-label">推荐股池</div></div>
            <div class="stat-card"><div class="stat-num" id="statLatest">-</div><div class="stat-label">最新扫描</div></div>
            <div class="stat-card"><div class="stat-num" id="statP0P1" style="color:var(--status-warning)">-</div><div class="stat-label">近 7 天 P0+P1</div></div>
            <div class="stat-card"><div class="stat-num" id="statCronStatus">-</div><div class="stat-label">定时任务</div></div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('userWatch',this);loadUserWatchlist();">我的关注</button>
            <button class="tab-btn" onclick="switchTab('recommended',this)">推荐选股</button>
            <button class="tab-btn" onclick="switchTab('ranking',this)">评分排行</button>
            <button class="tab-btn" onclick="switchTab('changes',this)">变化事件</button>
        </div>

        <div id="userWatch" class="tab-panel active">
            <div class="uw-toolbar">
                <input id="uwCodeInput" placeholder="股票代码（如 600519）" maxlength="12" />
                <input id="uwNoteInput" placeholder="备注（可选）" maxlength="50" />
                <label>波动阈值 ±</label>
                <input type="number" id="uwAlertPctInput" value="3.0" step="0.1" min="0.1" max="50" />
                <label>%</label>
                <button class="uw-btn primary" onclick="uwAdd()">添加</button>
                <button class="uw-btn" onclick="uwRefreshAll()" title="立即抓取所有关注股最新数据">立即抓取</button>
                <button class="uw-btn" onclick="loadUserWatchlist()">刷新</button>
            </div>
            <div id="uwListEl"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="recommended" class="tab-panel">
            <div id="recEl"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="ranking" class="tab-panel">
            <div id="rankEl"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="changes" class="tab-panel">
            <div id="chgEl"><div class="empty-state">加载中...</div></div>
        </div>
    </div>

    <div class="modal-backdrop" id="modal" onclick="if(event.target.id==='modal')closeModal()">
        <div class="modal">
            <div class="modal-header">
                <div>
                    <div class="modal-title" id="modalTitle">-</div>
                    <div class="modal-sub" id="modalSub">-</div>
                </div>
                <button class="btn-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="chart-wrap">
                <canvas id="histChart"></canvas>
                <div class="fallback-chart" id="fallbackChart" style="display:none"></div>
            </div>
            <div class="dim-grid" id="dimGrid"></div>
            <table class="raw-table" id="rawTable"></table>
            <div class="advice-box" id="adviceBox"></div>
            <div class="reasons-box" id="reasonsBox"></div>
        </div>
    </div>
"""


WEALTH_SCRIPT = """
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script>
    (function(){
        function esc(s){return s===null||s===undefined?'':String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
        function scoreCls(s){
            if(s>=75)return 'score-high';
            if(s>=60)return 'score-mid';
            return 'score-low';
        }
        function fmt(n, d){ if(n===null||n===undefined)return '-'; return Number(n).toFixed(d||2); }
        function fmtCap(v){ return v>0?(v/1e8).toFixed(0)+'亿':'-'; }

        window.switchTab=function(key,btn){
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
            document.getElementById(key).classList.add('active');
            btn.classList.add('active');
        };

        // 顶部红点跳转到本面板时滚动到公告区（公告区已上移到顶部，等价于到顶）
        window.openZhongliDigests=function(){
            var sec=document.getElementById('digest');
            if(sec) sec.scrollIntoView({behavior:'smooth', block:'start'});
        };

        // ===== 岩神推送公告区 + 历史折叠区 =====
        function _esc(s){if(s==null)return '';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
        function _fmtTime(ts){
            if(!ts||ts<=0)return '-';
            var d=new Date(ts*1000);
            var mm=(d.getMonth()+1).toString().padStart(2,'0');
            var dd=d.getDate().toString().padStart(2,'0');
            var hh=d.getHours().toString().padStart(2,'0');
            var mi=d.getMinutes().toString().padStart(2,'0');
            return mm+'-'+dd+' '+hh+':'+mi;
        }
        var _zhongliDigestSearch = '';
        var _zhongliHistoryShown = false;

        function _todayStr(){
            var d = new Date();
            return d.getFullYear() + '-'
                + String(d.getMonth()+1).padStart(2,'0') + '-'
                + String(d.getDate()).padStart(2,'0');
        }
        function _dayBounds(dateStr){
            var p = (dateStr||'').split('-');
            if(p.length !== 3) return null;
            var since = new Date(+p[0], +p[1]-1, +p[2], 0, 0, 0).getTime() / 1000;
            return { since: since, until: since + 86400 };
        }
        function _shiftDate(dateStr, delta){
            var p = (dateStr||_todayStr()).split('-');
            var d = new Date(+p[0], +p[1]-1, +p[2], 0, 0, 0);
            d.setDate(d.getDate() + delta);
            return d.getFullYear() + '-'
                + String(d.getMonth()+1).padStart(2,'0') + '-'
                + String(d.getDate()).padStart(2,'0');
        }
        function _currentDate(){
            var inp = document.getElementById('zhongliDateInput');
            return (inp && inp.value) || _todayStr();
        }
        // 把 /api/wealth/running 返回的 progress dict 拼成中文文案。
        // progress 字段：stage/cur/total/mode + 各 stage 特有（valid/passed/success 等）
        function _formatScanProgress(p){
            if(!p) return '正在采集红利股数据…';
            var stage = p.stage || '';
            var mode = p.mode || '';
            var cur = p.cur || 0;
            var total = p.total || 0;
            var pct = (total > 0) ? ((cur / total * 100).toFixed(1) + '%') : '';
            // init 没有 cur/total，按 mode 给写实文案（fetch_board 第一步是拉全市场行业分类）
            if(stage === 'init'){
                if(mode === 'full')    return '获取全市场行业分类…';
                if(mode === 'daily')   return '准备 watchlist 数据…';
                if(mode === 'rescore') return '读取缓存…';
                return '准备中…';
            }
            var stageLabel = {
                'board': '全市场行情扫描',
                'board_codes': 'watchlist 行情扫描',
                'dividend': '股息数据抓取',
                'financial': '财务数据抓取',
                'scoring_dividend': '股息评分',
                'scoring_financial': '财务评分',
                'scoring_rescore': '重评分',
            }[stage] || stage;
            if(total <= 0) return stageLabel + '…';
            var extra = '';
            if(p.valid != null)   extra = '，已获取 ' + p.valid + ' 只';
            else if(p.success != null) extra = '，成功 ' + p.success + ' 只';
            else if(p.passed != null)  extra = '，通过 ' + p.passed + ' 只';
            return stageLabel + ' ' + cur + '/' + total + '（' + pct + '）' + extra;
        }

        var _zhongliBulletinsPollTimer = null;
        // 已被用户点关的 error.ts 集合（避免再次轮询又弹）
        var _zhongliDismissedErrors = {};
        window.dismissZhongliError = function(ts){
            _zhongliDismissedErrors[ts] = 1;
            var bar = document.getElementById('zhongliErrorBar');
            if(bar){ bar.style.display = 'none'; bar.innerHTML = ''; }
        };
        async function loadZhongliBulletins(){
            // 公告区：渲染当前选中日期的所有日报（对齐风神 sentiment 形态）
            var el = document.getElementById('zhongliBulletins');
            var runBar = document.getElementById('zhongliRunningBar');
            if(!el) return;
            var dateStr = _currentDate();
            var b = _dayBounds(dateStr);
            if(!b){
                el.innerHTML = '<div class="digest-bulletins-empty">日期格式错误</div>';
                return;
            }
            var isToday = dateStr === _todayStr();
            try{
                var qs = 'actor=' + encodeURIComponent('岩神')
                    + '&since=' + b.since + '&until=' + b.until + '&limit=50';
                // 并行拉公告 + 采集 running 状态（只在查看今天时有意义）
                var reqs = [fetch('/api/push_archive/list?' + qs).then(function(r){return r.json();})];
                if(isToday){
                    reqs.push(fetch('/api/wealth/running').then(function(r){return r.json();}).catch(function(){return {running:false};}));
                }
                var results = await Promise.all(reqs);
                var d = results[0];
                var runResp = results[1] || {running: false};
                // 过滤掉关注股资讯推送（source 含 'stock_watch:'）—— 这些归右栏 newsPanel，不进左栏理财日报
                var records = (d.records || []).filter(function(r){
                    return (r.source || '').indexOf('stock_watch:') < 0;
                });
                var running = !!runResp.running;
                var progress = runResp.progress || null;
                var lastError = runResp.last_error || null;

                // 顶部采集状态条
                if(runBar){
                    if(running){
                        var progressText = _formatScanProgress(progress);
                        runBar.innerHTML = '<span class="dot"></span><span>岩神·' + progressText + '</span>';
                        runBar.className = 'digest-running-bar';
                        runBar.style.display = '';
                    }else{
                        runBar.style.display = 'none';
                        runBar.innerHTML = '';
                    }
                }

                // 错误横幅（10 分钟内，未被用户关闭过）
                var errBar = document.getElementById('zhongliErrorBar');
                if(errBar){
                    var shouldShow = lastError && !_zhongliDismissedErrors[lastError.ts];
                    if(shouldShow){
                        var ageStr = lastError.age_seconds < 60
                            ? lastError.age_seconds + ' 秒前'
                            : Math.floor(lastError.age_seconds / 60) + ' 分钟前';
                        errBar.innerHTML =
                            '<span class="err-msg">❌ <strong>' + _esc(lastError.mode) + '</strong> 扫描失败（'
                            + ageStr + '）：' + _esc(lastError.message) + '</span>'
                            + '<button class="err-close" title="关闭" onclick="window.dismissZhongliError('
                            + lastError.ts + ')">✕</button>';
                        errBar.className = 'digest-error-bar';
                        errBar.style.display = '';
                    }else{
                        errBar.style.display = 'none';
                        errBar.innerHTML = '';
                    }
                }

                var hint = document.getElementById('zhongliBulletinHint');
                if(!records.length){
                    var tip;
                    if(running){
                        tip = '采集中，请稍候…<br><small>完成后这里会自动展开当日日报</small>';
                    }else{
                        tip = isToday
                            ? '今天还没有日报<br><small>启用定时后会在 19:00 / 月初 21:00 自动生成（见顶部 stat 卡"定时任务"状态），也可随时点顶部"日更/全扫描"按钮手动触发</small>'
                            : '该日无日报<br><small>用 ← / → 切换其它日期</small>';
                    }
                    el.innerHTML = '<div class="digest-bulletins-empty">' + tip + '</div>';
                    if(hint) hint.textContent = '· ' + dateStr + (isToday?'（今天）':'');
                }else{
                    var unreadCount = records.filter(function(r){ return r.read_at == null; }).length;
                    if(hint) hint.textContent = '· ' + dateStr + (isToday?'（今天）':'')
                        + ' · ' + records.length + ' 篇'
                        + (unreadCount > 0 ? ('，' + unreadCount + ' 未读') : '');
                    el.innerHTML = records.map(function(rec){
                        var unread = rec.read_at == null;
                        var cls = unread ? 'digest-bulletin' : 'digest-bulletin read';
                        var dot = unread ? '<span class="db-unread-dot" title="未读"></span>' : '';
                        var markBtn = unread
                            ? '<button class="db-mark-read" onclick="event.stopPropagation();window.markZhongliBulletinRead(\\''+_esc(rec.id)+'\\')">标记已读</button>'
                            : '';
                        var runningChip = (running && isToday)
                            ? '<span class="db-running">采集中</span>' : '';
                        return '<div class="' + cls + '" data-id="' + _esc(rec.id) + '">'
                            + '<div class="db-head">'
                            + '<div class="db-head-left">'
                            + dot
                            + '<span class="db-source">' + _esc(rec.source) + '</span>'
                            + runningChip
                            + '<span class="db-time" title="同日多次扫描会刷新此时间">最后更新 ' + _fmtTime(rec.created_at) + '</span>'
                            + '</div>'
                            + markBtn
                            + '</div>'
                            + '<div class="db-body md-body">' + (window.renderMarkdown ? window.renderMarkdown(rec.message_md || '') : _esc(rec.message_md || '')) + '</div>'
                            + '</div>';
                    }).join('');
                }

                // running 时 2s 后自动再刷（采集完成时自然出现日报）
                if(_zhongliBulletinsPollTimer){ clearTimeout(_zhongliBulletinsPollTimer); _zhongliBulletinsPollTimer = null; }
                if(running){
                    _zhongliBulletinsPollTimer = setTimeout(loadZhongliBulletins, 2000);
                }
            }catch(e){
                el.innerHTML = '<div class="digest-bulletins-empty">加载失败: ' + _esc(String(e)) + '</div>';
            }
        }
        // 日期切换：同时刷新左公告 + 右资讯（两面板共享同一日窗口）
        function _reloadDayPanels(){
            loadZhongliBulletins();
            if(typeof loadStockSubs === 'function') loadStockSubs();
        }
        window.zhongliDayShift = function(delta){
            var inp = document.getElementById('zhongliDateInput');
            if(!inp) return;
            inp.value = _shiftDate(inp.value || _todayStr(), delta);
            _reloadDayPanels();
        };
        window.zhongliDateChange = function(){
            _reloadDayPanels();
        };
        window.zhongliJumpToday = function(){
            var inp = document.getElementById('zhongliDateInput');
            if(!inp) return;
            inp.value = _todayStr();
            _reloadDayPanels();
        };
        window.markZhongliBulletinRead = async function(id){
            try{
                await fetch('/api/push_archive/' + encodeURIComponent(id) + '/read', {method: 'POST'});
                await loadZhongliBulletins();
                if(typeof window.refreshNavBadge === 'function') window.refreshNavBadge();
            }catch(e){}
        };
        window.toggleZhongliHistory = function(){
            _zhongliHistoryShown = !_zhongliHistoryShown;
            document.getElementById('zhongliHistoryWrap').style.display = _zhongliHistoryShown ? 'block' : 'none';
            document.getElementById('zhongliHistoryToggleBtn').textContent =
                _zhongliHistoryShown ? '收起历史 ↑' : '📜 查看更多历史 ↓';
            if(_zhongliHistoryShown) loadZhongliDigests();
        };

        async function loadZhongliDigests(){
            var listEl=document.getElementById('zhongliDigestList');
            if(!listEl)return;
            listEl.innerHTML='<div class="push-empty">加载中...</div>';
            try{
                var qs='actor='+encodeURIComponent('岩神')+'&limit=100';
                if(_zhongliDigestSearch) qs+='&q='+encodeURIComponent(_zhongliDigestSearch);
                var r=await fetch('/api/push_archive/list?'+qs);
                var d=await r.json();
                // 历史搜索区只显示理财日报，剔除关注股资讯（归右栏 newsPanel）
                var records=(d.records||[]).filter(function(rec){
                    return (rec.source||'').indexOf('stock_watch:') < 0;
                });
                if(!records.length){
                    listEl.innerHTML='<div class="push-empty">暂无岩神推送'+(_zhongliDigestSearch?'（搜索无结果）':'')+'</div>';
                    return;
                }
                listEl.innerHTML=records.map(function(rec){
                    var unread = rec.read_at == null;
                    var preview = (rec.message_md||'').slice(0,200);
                    return '<div class="push-item '+(unread?'unread':'')+'" data-id="'+_esc(rec.id)+'" onclick="window.toggleZhongliDigest(this)">'
                        + '<div class="push-item-head">'
                        + '<span class="push-item-source">'+_esc(rec.source)+'</span>'
                        + '<span class="push-item-time">'+_fmtTime(rec.created_at)+'</span>'
                        + '</div>'
                        + '<div class="push-item-preview">'+_esc(preview)+'</div>'
                        + '<div class="push-item-body md-body">'+(window.renderMarkdown?window.renderMarkdown(rec.message_md||''):_esc(rec.message_md||''))+'</div>'
                        + '</div>';
                }).join('');
            }catch(e){
                listEl.innerHTML='<div class="push-empty">加载失败: '+_esc(String(e))+'</div>';
            }
        }
        window.toggleZhongliDigest = async function(el){
            var wasExpanded = el.classList.contains('expanded');
            document.querySelectorAll('#zhongliDigestList .push-item.expanded').forEach(function(x){
                if(x!==el) x.classList.remove('expanded');
            });
            if(wasExpanded){ el.classList.remove('expanded'); return; }
            el.classList.add('expanded');
            if(el.classList.contains('unread')){
                var id = el.getAttribute('data-id');
                try{
                    await fetch('/api/push_archive/'+encodeURIComponent(id)+'/read', {method:'POST'});
                    el.classList.remove('unread');
                    if(typeof window.refreshNavBadge==='function') window.refreshNavBadge();
                }catch(e){}
            }
        };
        window.markAllZhongliRead = async function(){
            try{
                await fetch('/api/push_archive/read_all?actor='+encodeURIComponent('岩神'),
                    {method:'POST'});
                document.querySelectorAll('#zhongliDigestList .push-item.unread').forEach(function(el){
                    el.classList.remove('unread');
                });
                // 公告区也刷新
                await loadZhongliBulletins();
                if(typeof window.refreshNavBadge==='function') window.refreshNavBadge();
            }catch(e){}
        };
        document.addEventListener('keydown', function(e){
            if(e.key==='Enter' && document.activeElement && document.activeElement.id==='zhongliDigestSearch'){
                _zhongliDigestSearch = document.activeElement.value.trim();
                loadZhongliDigests();
            }
        });
        window.addEventListener('load', function(){
            if(location.hash === '#digest'){
                setTimeout(function(){
                    var sec=document.getElementById('digest');
                    if(sec) sec.scrollIntoView({behavior:'smooth', block:'start'});
                }, 200);
            }
        });

        // 已关注 code 的集合，渲染推荐/排名时知道哪些股票已经加入了 → "+ 关注" 按钮直接 added 态
        // 比较时统一 normalize 成纯 6 位数字（去前缀/点/空格/大小写），避免格式差异（sh.600519 vs SH.600519 vs 600519）漏判
        function _normCode(c){
            return String(c||'').toLowerCase().replace(/\s/g, '').replace(/^(sh|sz|bj)\.?/, '');
        }
        var _userWatchCodes = new Set();
        // normalized code → stock_name 映射（资讯面板显示名字而不是代码）
        var _userWatchCodeToName = {};

        window.refreshAll=async function(){
            loadStats();
            loadZhongliBulletins(); loadScanScope();
            // 先 await loadUserWatchlist 拿到 _userWatchCodes，再渲染推荐/排名（已关注的会标 added）
            await loadUserWatchlist();
            loadRecommended(); loadRanking(); loadChanges();
            // 历史折叠区按需加载（用户点「查看更多」时才 loadZhongliDigests）
        };

        // 加载日更/全扫描按钮下方的范围文案（候选池 N 只 / 全市场 ~5500）
        async function loadScanScope(){
            try{
                var r = await fetch('/api/wealth/scan_scope');
                var d = await r.json();
                var dailyHint = document.getElementById('dailyHint');
                var fullHint  = document.getElementById('fullHint');
                if(dailyHint){
                    var n = d.candidates_size || 0;
                    dailyHint.textContent = n > 0 ? ('候选池 ' + n + ' 只') : '候选池 -';
                }
                if(fullHint){
                    var f = d.full_market_size || 5500;
                    fullHint.textContent = '全市场 ~' + f;
                }
            }catch(e){ /* 静默：失败就显示初始 placeholder */ }
        }

        async function loadStats(){
            try{
                var r=await fetch('/api/wealth/stats'); var d=await r.json();
                document.getElementById('statWatchlist').textContent=d.watchlist_count||0;
                document.getElementById('statLatest').textContent=d.latest_scan_date||'-';
                var p0 = d.p0_count_7d||0, p1 = d.p1_count_7d||0;
                var p0p1El = document.getElementById('statP0P1');
                p0p1El.textContent = (p0 + p1) > 0 ? (p0 + '/' + p1) : '0';
                p0p1El.style.color = p0 > 0 ? 'var(--status-error)' : (p1 > 0 ? 'var(--status-warning)' : 'var(--text-muted)');
                document.getElementById('statCronStatus').textContent=d.cron_enabled?'已启用':'未启用';
            }catch(e){}
        }

        function renderRow(r){
            var dy=(r.dividend_yield||0)*100;
            var added = _userWatchCodes.has(_normCode(r.stock_code));
            var btnCls = 'addw-btn' + (added ? ' added' : '');
            var btnText = added ? '已关注' : '+ 关注';
            return '<tr onclick="openStock(\\''+esc(r.stock_code)+'\\',\\''+esc(r.stock_name)+'\\')">'
                + '<td class="code">'+esc(r.stock_code)+'</td>'
                + '<td>'+esc(r.stock_name)+'</td>'
                + '<td>'+esc(r.industry)+'</td>'
                + '<td class="num '+scoreCls(r.total_score)+'">'+fmt(r.total_score,1)+'</td>'
                + '<td class="num">'+fmt(dy,2)+'%</td>'
                + '<td class="num">'+fmt(r.pe,1)+'</td>'
                + '<td class="num">'+fmt(r.pb,2)+'</td>'
                + '<td class="num">'+fmtCap(r.market_cap)+'</td>'
                + '<td class="advice">'+esc(r.advice||'')+'</td>'
                + '<td class="row-actions">'
                +   '<button class="'+btnCls+'" data-code="'+esc(r.stock_code)+'" '
                +     'onclick="event.stopPropagation();addToWatchlist(this)" '
                +     (added ? 'disabled ' : '')
                +     'title="'+(added?'已在我的关注':'加到我的关注')+'">'+btnText+'</button>'
                + '</td>'
                + '</tr>';
        }

        function renderTable(rows){
            if(!rows||!rows.length){ return '<div class="empty-state">暂无数据</div>'; }
            return '<div style="overflow-x:auto"><table class="stock-table"><thead><tr>'
                + '<th>代码</th><th>股票</th><th>行业</th>'
                + '<th>评分</th><th>股息率</th><th>PE</th><th>PB</th><th>市值</th>'
                + '<th>建议</th>'
                + '<th></th>'
                + '</tr></thead><tbody>'
                + rows.map(renderRow).join('')
                + '</tbody></table></div>';
        }

        // 推荐选股 / 排名 → 一键加入"我的关注"，**严格对齐 uwAdd**（手动添加）的链路
        window.addToWatchlist = async function(btn){
            if(btn.classList.contains('added')) return;
            var code = btn.dataset.code;
            if(!code){ alert('股票代码缺失'); return; }
            btn.disabled = true;
            var old = btn.textContent;
            btn.textContent = '...';
            try{
                var r = await fetch('/api/wealth/user_watch/add', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({code: code, note: '', alert_pct: 3.0}),
                });
                var d = await r.json();
                // 严格对齐 uwAdd：所有 not-ok 都报 alert（不再 409 静默处理）
                if(!d.ok){
                    alert('添加失败: ' + (d.error || 'unknown'));
                    btn.disabled = false; btn.textContent = old;
                    return;
                }
                // 成功路径与 uwAdd 完全等价：await loadUserWatchlist + _uwPollAfterAdd
                _userWatchCodes.add(_normCode(code));
                await loadUserWatchlist();
                // 推荐 + 排名表里同股按钮也要刷成"已关注"（用户当前可能在另一 tab）
                if(typeof loadRecommended === 'function') loadRecommended();
                if(typeof loadRanking === 'function') loadRanking();
                _uwPollAfterAdd();
            }catch(e){
                alert('请求失败: ' + e);
                btn.disabled = false; btn.textContent = old;
            }
        };

        async function loadRecommended(){
            var el=document.getElementById('recEl');
            try{
                var r=await fetch('/api/wealth/recommended'); var d=await r.json();
                el.innerHTML=renderTable(d.stocks||[]);
            }catch(e){ el.innerHTML='<div class="empty-state">加载失败: '+esc(String(e))+'</div>'; }
        }

        async function loadRanking(){
            var el=document.getElementById('rankEl');
            try{
                var r=await fetch('/api/wealth/ranking?n=100'); var d=await r.json();
                el.innerHTML=renderTable(d.stocks||[]);
            }catch(e){ el.innerHTML='<div class="empty-state">加载失败</div>'; }
        }

        async function loadChanges(){
            var el=document.getElementById('chgEl');
            try{
                var r=await fetch('/api/wealth/changes?days=30'); var d=await r.json();
                var items=d.changes||[];
                if(!items.length){ el.innerHTML='<div class="empty-state">近 30 天无变化</div>'; return; }
                el.innerHTML='<div class="change-list">'
                    + items.map(function(c){
                        var cls='change-item';
                        if(c.event_type==='entered')cls+=' entered';
                        else if(c.event_type==='exited')cls+=' exited';
                        else if(c.event_type==='score_change'){
                            var diff=(c.new_value||0)-(c.old_value||0);
                            cls += diff>=0 ? ' score-up' : ' score-down';
                        }
                        var labelMap={'entered':'新入选','exited':'退出','score_change':'评分变化'};
                        return '<div class="'+cls+'" onclick="openStock(\\''+esc(c.stock_code)+'\\',\\''+esc(c.stock_name)+'\\')">'
                            + '<b>'+esc(labelMap[c.event_type]||c.event_type)+'</b>&nbsp;'
                            + esc(c.stock_name)+' ('+esc(c.stock_code)+')'
                            + '<div class="change-meta">'+esc(c.event_date)+' · '+esc(c.description||'')+'</div>'
                            + '</div>';
                    }).join('')
                    + '</div>';
            }catch(e){ el.innerHTML='<div class="empty-state">加载失败</div>'; }
        }

        var _histChart=null;

        window.openStock=async function(code, name){
            document.getElementById('modalTitle').textContent=name+' ('+code+')';
            document.getElementById('modalSub').textContent='加载中...';
            document.getElementById('modal').classList.add('show');
            try{
                var r=await fetch('/api/wealth/stock/'+encodeURIComponent(code)+'?days=90');
                var d=await r.json();
                var history=d.history||[];
                var current=d.current||null;

                if(current){
                    document.getElementById('modalSub').textContent=
                        current.industry+' · '+current.scan_date+' · '+fmt(current.total_score,1)+' 分';
                    // 维度卡片
                    document.getElementById('dimGrid').innerHTML=[
                        ['可持续性', current.sustainability_score, 30],
                        ['财务堡垒', current.fortress_score, 25],
                        ['估值安全', current.valuation_score, 20],
                        ['分红记录', current.track_record_score, 18],
                        ['盈利动能', current.momentum_score, 10],
                        ['惩罚', current.penalty, ''],
                    ].map(function(x){
                        return '<div class="dim-card"><div class="dim-label">'+x[0]+'</div>'
                            +'<div class="dim-value">'+fmt(x[1],0)+(x[2]?' / '+x[2]:'')+'</div></div>';
                    }).join('');
                    // 原始指标
                    var dy=(current.dividend_yield||0)*100;
                    document.getElementById('rawTable').innerHTML=[
                        ['股息率', fmt(dy,2)+'%'],
                        ['PE', fmt(current.pe,2)],
                        ['PB', fmt(current.pb,2)],
                        ['ROE', fmt(current.roe,2)+'%'],
                        ['市值', fmtCap(current.market_cap)],
                    ].map(function(x){ return '<tr><td>'+x[0]+'</td><td>'+x[1]+'</td></tr>'; }).join('');
                    document.getElementById('adviceBox').textContent=current.advice||'';
                    document.getElementById('reasonsBox').textContent=current.reasons||'';
                } else {
                    document.getElementById('modalSub').textContent='暂无快照';
                    document.getElementById('dimGrid').innerHTML='';
                    document.getElementById('rawTable').innerHTML='';
                    document.getElementById('adviceBox').textContent='';
                    document.getElementById('reasonsBox').textContent='';
                }

                // Chart.js 折线图
                var ctx=document.getElementById('histChart').getContext('2d');
                if(_histChart){ _histChart.destroy(); }
                if(history.length && typeof Chart !== 'undefined'){
                    document.getElementById('histChart').style.display='';
                    document.getElementById('fallbackChart').style.display='none';
                    _histChart=new Chart(ctx,{
                        type:'line',
                        data:{
                            labels:history.map(function(h){return h.scan_date;}),
                            datasets:[{
                                label:'总分',
                                data:history.map(function(h){return h.total_score;}),
                                borderColor:'#d4af37', backgroundColor:'rgba(212,175,55,.1)',
                                tension:.2, fill:true,
                            }]
                        },
                        options:{
                            responsive:true, maintainAspectRatio:false,
                            plugins:{legend:{labels:{color:'#d1d5db'}}},
                            scales:{
                                y:{beginAtZero:false, ticks:{color:'#9ca3af'}, grid:{color:'#3d3450'}},
                                x:{ticks:{color:'#9ca3af'}, grid:{color:'#3d3450'}},
                            },
                        },
                    });
                } else if(history.length){
                    // Chart.js 没加载到：降级文本
                    document.getElementById('histChart').style.display='none';
                    var fc=document.getElementById('fallbackChart');
                    fc.style.display='';
                    fc.textContent=history.map(function(h){return h.scan_date+' — '+fmt(h.total_score,1);}).join('\\n');
                } else {
                    document.getElementById('histChart').style.display='none';
                    document.getElementById('fallbackChart').style.display='';
                    document.getElementById('fallbackChart').textContent='无历史数据';
                }
            }catch(e){ document.getElementById('modalSub').textContent='加载失败: '+e; }
        };

        window.closeModal=function(){
            document.getElementById('modal').classList.remove('show');
            if(_histChart){ _histChart.destroy(); _histChart=null; }
        };

        var _scanPollTimer = null;
        var _scanStartTs = 0;            // trigger 那一刻的时间戳，秒级

        // 用「公告 created_at 比 trigger 时刻新」作为扫描完成主信号 ——
        // 比"running 由 true→false"更稳：极快的 rescore（1-2s）也能可靠抓到。
        // 兜底信号：last_error 变新（扫描异常没写公告，需要恢复按钮 + 提示）。
        // 30 分钟硬上限防泄漏。
        function _pollScanComplete(btn, oldText){
            if(_scanPollTimer){ clearTimeout(_scanPollTimer); _scanPollTimer = null; }
            var checkCount = 0;
            var poll = async function(){
                checkCount++;
                try{
                    var [listRes, runRes] = await Promise.all([
                        fetch('/api/push_archive/list?actor=' + encodeURIComponent('岩神') + '&limit=1')
                            .then(function(r){ return r.json(); }),
                        fetch('/api/wealth/running').then(function(r){ return r.json(); }),
                    ]);
                    var latest = (listRes.records || [])[0];
                    var newDigest = latest && latest.created_at >= _scanStartTs;
                    var newError = runRes.last_error && runRes.last_error.ts >= _scanStartTs;
                    if(newDigest || newError){
                        _scanPollTimer = null;
                        btn.disabled = false; btn.textContent = oldText;
                        refreshAll();
                        return;
                    }
                }catch(e){ /* 静默 */ }
                // 30 分钟硬上限
                if(checkCount > 1800){
                    _scanPollTimer = null;
                    btn.disabled = false; btn.textContent = oldText;
                    return;
                }
                // 前 6 次 500ms 高频抓极快任务，之后 2s
                _scanPollTimer = setTimeout(poll, checkCount < 6 ? 500 : 2000);
            };
            poll();
        }

        window.triggerScan=async function(mode){
            var btnMap={rescore:'btnRescore', daily:'btnDaily', full:'btnFull'};
            var btn=document.getElementById(btnMap[mode]);
            if(!btn)return;
            if(mode==='full' && !confirm('全市场扫描耗时 15-20 分钟，确认启动？'))return;
            btn.disabled=true;
            var oldText=btn.textContent;
            btn.textContent='已触发...';
            try{
                var r=await fetch('/api/wealth/trigger', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({mode: mode}),
                });
                var d=await r.json();
                if(d.ok){
                    btn.textContent='运行中';
                    // 记录 trigger 时刻，用作「公告变新 / last_error 变新」的判定基准
                    _scanStartTs = Date.now() / 1000;
                    // 1. 立即启动状态条（让用户即刻看到"准备中"）
                    loadZhongliBulletins();
                    // 2. 轮询「公告 created_at 比 _scanStartTs 新」→ 恢复按钮 + 刷数据
                    _pollScanComplete(btn, oldText);
                } else {
                    alert('触发失败: '+(d.error||'unknown'));
                    btn.disabled=false; btn.textContent=oldText;
                }
            }catch(e){
                alert('触发失败: '+e);
                btn.disabled=false; btn.textContent=oldText;
            }
        };

        window.onload=function(){
            var inp = document.getElementById('zhongliDateInput');
            if(inp && !inp.value) inp.value = _todayStr();
            refreshAll();
            // 全局拦截外部链接（http/https）→ 新标签页打开（兜底所有不走 _renderMdSafe 的入口）
            document.body.addEventListener('click', function(e){
                var a = e.target && e.target.closest && e.target.closest('a[href]');
                if(!a) return;
                var href = a.getAttribute('href') || '';
                if(/^https?:\\/\\//i.test(href)){
                    e.preventDefault();
                    window.open(href, '_blank', 'noopener,noreferrer');
                }
            });
        };

        // ========= 用户关注股（我的关注 tab）=========

        function _renderSparkline(points){
            if(!points || points.length < 2){
                return '<span style="color:var(--text-muted);font-size:11px">(首次抓取中)</span>';
            }
            var n = points.length;
            var minV = Math.min.apply(null, points);
            var maxV = Math.max.apply(null, points);
            var rng = maxV - minV || 1;
            var W = 88, H = 28, pad = 2;
            var pts = points.map(function(v, i){
                var x = pad + (i/(n-1)) * (W - 2*pad);
                var y = H - pad - ((v - minV)/rng) * (H - 2*pad);
                return x.toFixed(1) + ',' + y.toFixed(1);
            }).join(' ');
            var trend = points[n-1] >= points[0] ? 'up' : 'down';
            return '<svg class="uw-spark ' + trend + '" viewBox="0 0 ' + W + ' ' + H + '"><polyline points="' + pts + '"/></svg>';
        }

        function _renderPctBar(p){
            if(p == null) return '<span class="uw-pct-label">-</span>';
            var left = Math.max(0, Math.min(99, p * 100));
            var pctLabel = (p * 100).toFixed(0) + '%';
            // 分位 < 30% 估值较低（绿）/ >= 70% 较高（红）/ 中间正常（灰）
            var cls = p < 0.3 ? 'low' : (p >= 0.7 ? 'high' : '');
            return '<span class="uw-pctbar" title="估值分位：低 0~30% / 正常 30~70% / 高 70~100%">'
                 + '<span class="marker" style="left:' + left.toFixed(1) + '%"></span></span>'
                 + '<span class="uw-pct-label ' + cls + '">' + pctLabel + '</span>';
        }

        function _renderChange(pct, alert){
            if(pct == null) return '<span class="uw-change flat">-</span>';
            var cls = pct > 0 ? 'pos' : (pct < 0 ? 'neg' : 'flat');
            var sign = pct > 0 ? '+' : '';
            var warn = (Math.abs(pct) >= (alert||3)) ? ' ⚠️' : '';
            return '<span class="uw-change ' + cls + '">' + sign + pct.toFixed(2) + '%' + warn + '</span>';
        }

        window.loadUserWatchlist = async function(){
            var el = document.getElementById('uwListEl');
            if(!el) return;
            try{
                var r = await fetch('/api/wealth/user_watch');
                var d = await r.json();
                var items = d.items || [];
                // 同步 _userWatchCodes，供推荐/排名渲染时打"已关注"
                _userWatchCodes = new Set(items.map(function(it){return _normCode(it.stock_code);}));
                // 同步 normalized code → name 映射；资讯面板用名字展示
                _userWatchCodeToName = {};
                items.forEach(function(it){
                    _userWatchCodeToName[_normCode(it.stock_code)] = it.stock_name || '';
                });
                if(items.length === 0){
                    el.innerHTML = '<div class="empty-state">暂无关注股。输入股票代码添加。</div>';
                    return;
                }
                var rows = items.map(function(it){
                    var spark = _renderSparkline(it.sparkline || []);
                    var chg = _renderChange(it.change_pct, it.alert_pct);
                    var pePct = _renderPctBar(it.pe_percentile);
                    var pbPct = _renderPctBar(it.pb_percentile);
                    var nameCell = esc(it.stock_name) || '<span style="color:var(--text-muted)">(待扫描)</span>';
                    var codeAttr = esc(it.stock_code);
                    var noteAttr = esc(it.note || '');
                    var alertAttr = (+it.alert_pct || 3).toFixed(1);
                    return ''
                        + '<tr class="uw-data-row" data-stock-code="' + codeAttr + '">'
                        + '<td class="code c-c">' + esc(it.stock_code) + '</td>'
                        + '<td class="c-c">' + nameCell + '</td>'
                        + '<td class="c-c">' + (it.price && it.price > 0 ? fmt(it.price) : '-') + '</td>'
                        + '<td class="c-c">' + chg + '</td>'
                        + '<td class="c-c">' + spark + '</td>'
                        + '<td class="c-c">' + (it.pe && it.pe > 0 ? '<span class="pe-num">' + fmt(it.pe) + '</span>' + pePct : '-') + '</td>'
                        + '<td class="c-c">' + (it.pb && it.pb > 0 ? '<span class="pe-num">' + fmt(it.pb) + '</span>' + pbPct : '-') + '</td>'
                        + '<td class="note c-c" title="' + noteAttr + '">' + esc(it.note) + '</td>'
                        + '<td class="c-c">±' + alertAttr + '%</td>'
                        + '<td class="c-c">'
                        + '<button class="uw-news-toggle-btn" data-stock-code="' + codeAttr + '" onclick="toggleStockNewsRow(this)">📰 资讯</button>'
                        + '<button class="uw-btn" data-code="' + codeAttr + '" data-alert="' + alertAttr + '" data-note="' + noteAttr + '" onclick="uwEdit(this)">编辑</button>'
                        + '<button class="uw-btn danger" data-code="' + codeAttr + '" onclick="uwRemove(this)">删除</button>'
                        + '</td>'
                        + '</tr>'
                        + '<tr class="uw-news-row" data-news-row-for="' + codeAttr + '">'
                        +   '<td colspan="10">'
                        +     '<div class="uw-news-wrap">'
                        +       '<div class="stock-news-line" data-news-line-for="' + codeAttr + '" data-stock-code="' + codeAttr + '">'
                        +         '<span class="news-toggle"><span class="dot"></span>加载中</span>'
                        +         '<span class="news-icon">📰</span>'
                        +         '<span class="news-text"><span class="meta">资讯订阅</span></span>'
                        +         '<button class="news-run" disabled>采集</button>'
                        +       '</div>'
                        +       '<div class="stock-news-pushes" data-pushes-for="' + codeAttr + '" data-stock-code="' + codeAttr + '" data-detailed="1"></div>'
                        +     '</div>'
                        +   '</td>'
                        + '</tr>';
                }).join('');
                el.innerHTML = ''
                    + '<table class="stock-table uw-table">'
                    + '<thead><tr>'
                    + '<th class="c-c">代码</th><th class="c-c">名称</th>'
                    + '<th class="c-c">最新价</th><th class="c-c">日涨跌</th>'
                    + '<th class="c-c">30 日走势</th>'
                    + '<th class="c-c">PE · 分位</th><th class="c-c">PB · 分位</th>'
                    + '<th class="c-c">备注</th><th class="c-c">阈值</th>'
                    + '<th class="c-c">操作</th>'
                    + '</tr></thead>'
                    + '<tbody>' + rows + '</tbody></table>';
                // 异步拉关注股订阅 + 推送数据，hydrate 资讯行（同水神模式）
                if(typeof loadStockSubs === 'function') loadStockSubs();
            }catch(e){
                el.innerHTML = '<div class="empty-state">加载失败: ' + esc(String(e)) + '</div>';
            }
        };

        // 首次 add 后后端异步拉 5 年历史 + 股票名，10~60s 不等。
        // 先立即刷一次（显示 "待扫描"占位），再分档轮询直到拿到数据（避免用户手动刷）。
        var _uwPollTimers = [];
        function _uwPollAfterAdd(){
            _uwPollTimers.forEach(clearTimeout);
            _uwPollTimers = [10, 25, 45, 75].map(function(s){
                return setTimeout(loadUserWatchlist, s * 1000);
            });
        }
        window.uwAdd = async function(){
            var code = document.getElementById('uwCodeInput').value.trim();
            var note = document.getElementById('uwNoteInput').value.trim();
            var alertPct = parseFloat(document.getElementById('uwAlertPctInput').value) || 3.0;
            if(!code){ alert('请输入股票代码'); return; }
            try{
                var r = await fetch('/api/wealth/user_watch/add', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({code: code, note: note, alert_pct: alertPct}),
                });
                var d = await r.json();
                if(!d.ok){ alert('添加失败: ' + (d.error || 'unknown')); return; }
                document.getElementById('uwCodeInput').value = '';
                document.getElementById('uwNoteInput').value = '';
                await loadUserWatchlist();
                // 推荐 + 排名同股按钮跟着刷"已关注"
                if(typeof loadRecommended === 'function') loadRecommended();
                if(typeof loadRanking === 'function') loadRanking();
                _uwPollAfterAdd();
            }catch(e){ alert('请求失败: ' + e); }
        };

        window.uwRemove = async function(btn){
            var code = btn.dataset.code;
            if(!confirm('确定删除 ' + code + ' 的关注吗？（价格历史也会清掉）')) return;
            try{
                var r = await fetch('/api/wealth/user_watch/remove', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({code: code}),
                });
                var d = await r.json();
                if(!d.ok){ alert('删除失败'); return; }
                await loadUserWatchlist();
                // 推荐 + 排名同股按钮跟着回到"+ 关注"
                if(typeof loadRecommended === 'function') loadRecommended();
                if(typeof loadRanking === 'function') loadRanking();
            }catch(e){ alert('请求失败: ' + e); }
        };

        window.uwEdit = async function(btn){
            var code = btn.dataset.code;
            var alertPct = btn.dataset.alert;
            var note = btn.dataset.note || '';
            var newAlert = prompt('波动阈值 (%)', alertPct);
            if(newAlert === null) return;
            var newNote = prompt('备注（留空清除）', note);
            if(newNote === null) return;
            try{
                var r = await fetch('/api/wealth/user_watch/update', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({
                        code: code,
                        alert_pct: parseFloat(newAlert) || 3.0,
                        note: newNote,
                    }),
                });
                var d = await r.json();
                if(!d.ok){ alert('更新失败'); return; }
                await loadUserWatchlist();
            }catch(e){ alert('请求失败: ' + e); }
        };

        window.uwRefreshAll = async function(){
            if(!confirm('立即抓取所有关注股最新数据？（可能要 10~60s）')) return;
            try{
                var r = await fetch('/api/wealth/user_watch/refresh', {method: 'POST'});
                var d = await r.json();
                if(!d.ok){ alert('触发失败'); return; }
            }catch(e){ alert('请求失败: ' + e); return; }
            // 抓取耗时不确定（每只股 baostock 几秒），多档轮询
            _uwPollAfterAdd();
        };

        // ========= 📰 关注股资讯订阅（同游戏面板模式） =========
        var _stockSubsCache = [];        // [{id, stock_code, query, enabled, last_run_at, last_error, item_count, running}, ...]
        var _stockPushesCache = {};      // {stock_code: [push records]}
        var _stockSubsPollTimer = null;

        function _fmtPushTime(ts){
            if(!ts) return '从未运行';
            var d = new Date(ts*1000);
            return (d.getMonth()+1)+'-'+d.getDate()+' '
                + d.getHours().toString().padStart(2,'0')+':'
                + d.getMinutes().toString().padStart(2,'0');
        }

        function _findStockSub(code){
            for(var i=0; i<_stockSubsCache.length; i++){
                if(_stockSubsCache[i].stock_code === code) return _stockSubsCache[i];
            }
            return null;
        }

        // 拉关注股订阅 + 推送数据（actor=岩神，按 source 'stock_watch:CODE' 分桶）
        // 自带递归轮询：检测到 sub.running 会 setTimeout 自调直到完成（同水神 game_html 模式）
        window.loadStockSubs = async function loadStockSubs(){
            try {
                var r = await fetch('/api/wealth/stock_subscriptions');
                var data = await r.json();
                _stockSubsCache = data.subs || [];
            } catch(e){ console.error('stock-subs fetch failed', e); _stockSubsCache = []; }

            try {
                // 按当前日期拉取（与公告区同一日窗口；日期切换时同时刷新左右两边）
                var dateStr = _currentDate();
                var b = _dayBounds(dateStr) || {};
                var qs = 'actor=' + encodeURIComponent('岩神') + '&limit=200';
                if(b.since != null) qs += '&since=' + b.since + '&until=' + b.until;
                var rp = await fetch('/api/push_archive/list?' + qs);
                var dp = await rp.json();
                var records = dp.records || [];
                _stockPushesCache = {};
                records.forEach(function(rec){
                    // source 形如 '岩神·stock_watch:600519' —— 包含 'stock_watch:CODE'
                    var src = rec.source || '';
                    var marker = 'stock_watch:';
                    var idx = src.indexOf(marker);
                    if(idx < 0) return;
                    var code = src.substring(idx + marker.length).trim();
                    if(!code) return;
                    if(!_stockPushesCache[code]) _stockPushesCache[code] = [];
                    _stockPushesCache[code].push(rec);
                });
            } catch(e){ console.error('stock-pushes fetch failed', e); _stockPushesCache = {}; }

            _hydrateStockNewsLines();
            _renderStockNewsPanel();

            // 有采集中的订阅 → 2s 后自动再刷一次（递归轮询直到全部完成）
            if(_stockSubsCache.some(function(s){return s.running;})){
                if(_stockSubsPollTimer) clearTimeout(_stockSubsPollTimer);
                _stockSubsPollTimer = setTimeout(loadStockSubs, 2000);
            }
        };

        // 渲染右栏「关注股资讯」面板（与左侧公告独立的兄弟面板，单列卡片堆叠）
        // _stockPushesCache 已按当前日期窗口拉取，这里只做平铺 + 倒序渲染
        function _renderStockNewsPanel(){
            var listEl = document.getElementById('newsPanelList');
            var hintEl = document.getElementById('newsPanelHint');
            if(!listEl) return;
            var dateStr = _currentDate();
            var isToday = dateStr === _todayStr();
            var all = [];
            Object.keys(_stockPushesCache || {}).forEach(function(code){
                (_stockPushesCache[code] || []).forEach(function(p){
                    all.push({code: code, push: p});
                });
            });
            all.sort(function(a, b){
                return (b.push.created_at || 0) - (a.push.created_at || 0);
            });
            if(hintEl){
                hintEl.textContent = '· ' + dateStr + (isToday?'（今天）':'')
                    + ' · ' + (all.length ? all.length + ' 条' : '无');
            }
            if(!all.length){
                var tip = isToday
                    ? '今天关注股暂无资讯推送<br><small>每天 7:30 自动拉取；也可在「我的关注」行点 📰 资讯 手动采集</small>'
                    : '该日无资讯推送<br><small>用 ← / → 切换其它日期</small>';
                listEl.innerHTML = '<div class="news-section-empty">' + tip + '</div>';
                return;
            }
            listEl.innerHTML = all.map(function(item){
                var t = _fmtTime(item.push.created_at || item.push.updated_at);
                var body = window.renderMarkdown ? window.renderMarkdown(item.push.message_md || '') : _esc(item.push.message_md || '');
                // 显示名字优先，code 作 title 兜底；map 缺失时退回 code
                var name = _userWatchCodeToName[_normCode(item.code)] || '';
                var label = name || item.code;
                return '<div class="news-card">'
                    +   '<div class="nc-head">'
                    +     '<span class="nc-stock" title="' + _esc(item.code) + '">' + _esc(label) + '</span>'
                    +     '<span class="nc-time">' + t + '</span>'
                    +   '</div>'
                    +   '<div class="nc-body md-body">' + body + '</div>'
                    + '</div>';
            }).join('');
        }

        function _hydrateStockNewsLines(){
            var rows = document.querySelectorAll('.stock-news-line');
            for(var i=0; i<rows.length; i++){
                var row = rows[i];
                _renderStockNewsLine(row, row.getAttribute('data-stock-code'));
            }
            var panels = document.querySelectorAll('.stock-news-pushes');
            for(var j=0; j<panels.length; j++){
                _renderStockPushesPanel(panels[j], panels[j].getAttribute('data-stock-code'));
            }
            // 同步数据行的"📰 资讯"按钮：有推送时高亮
            var btns = document.querySelectorAll('.uw-news-toggle-btn');
            for(var b=0; b<btns.length; b++){
                var code = btns[b].getAttribute('data-stock-code');
                var pushes = _stockPushesCache[code] || [];
                btns[b].classList.toggle('has-news', pushes.length > 0);
                btns[b].textContent = pushes.length
                    ? '📰 ' + pushes.length + ' 条'
                    : '📰 资讯';
            }
        }

        function _renderStockNewsLine(row, code){
            var sub = _findStockSub(code);
            var pushes = _stockPushesCache[code] || [];
            row.classList.remove('on', 'err', 'busy');

            if(!sub){
                row.innerHTML = '<span class="news-toggle"><span class="dot"></span>未就绪</span>'
                    + '<span class="news-icon">📰</span>'
                    + '<span class="news-text"><span class="meta">订阅尚未建立（重启服务后自动 ensure）</span></span>'
                    + '<button class="news-run" disabled>采集</button>';
                return;
            }

            if(sub.running){
                row.classList.add('busy');
                row.innerHTML = '<label class="news-toggle busy"><span class="dot"></span>采集中…</label>'
                    + '<span class="news-icon">⏳</span>'
                    + '<span class="news-text"><span class="meta">任务运行中，稍候自动刷新</span></span>'
                    + '<button class="news-run" disabled>采集中</button>';
                return;
            }

            if(sub.last_error) row.classList.add('err');
            else if(sub.enabled) row.classList.add('on');

            var toggleLabel = sub.enabled ? '运行中' : '已停止';
            var toggleCls = 'news-toggle' + (sub.enabled ? ' on' : '');

            var textHtml;
            if(sub.last_error){
                textHtml = '<span class="err-msg">⚠ ' + esc(sub.last_error.substring(0, 80)) + '</span>';
            } else if(pushes.length){
                var latest = pushes[0];
                var t = _fmtPushTime(latest.created_at || latest.updated_at);
                textHtml = '<span class="meta">上次 ' + esc(t) + ' · ' + pushes.length + ' 条今日推送</span>';
            } else {
                var stat = sub.last_run_at
                    ? '上次 ' + _fmtPushTime(sub.last_run_at) + ' · 暂无新资讯'
                    : '暂无推送 · 每天 8 点采集';
                textHtml = '<span class="meta">' + esc(stat) + '</span>';
            }

            row.innerHTML = '<label class="' + toggleCls + '" title="点击启停">'
                +   '<input type="checkbox" ' + (sub.enabled ? 'checked' : '') + ' style="display:none">'
                +   '<span class="dot"></span>' + toggleLabel
                + '</label>'
                + '<span class="news-icon">📰</span>'
                + '<span class="news-text">' + textHtml + '</span>'
                + '<button class="news-run" title="立即采集一次">采集</button>';

            var subId = sub.id;
            var label = row.querySelector('.news-toggle');
            var checkbox = label.querySelector('input');
            var runBtn = row.querySelector('.news-run');
            label.onclick = function(e){
                if(e.target === checkbox) return;
                checkbox.checked = !checkbox.checked;
                toggleStockSub(checkbox, subId);
            };
            runBtn.onclick = function(){
                runBtn.disabled = true; runBtn.textContent = '采集中…';
                runStockSub(subId, runBtn);
            };
        }

        // marked.parse 渲染 + 外部链接 target=_blank rel=noopener（同 game_html）
        function _renderMdSafe(md){
            if(typeof marked === 'undefined' || !marked || typeof marked.parse !== 'function'){
                return '<pre>' + esc(md || '') + '</pre>';
            }
            try {
                var raw = marked.parse(md || '');
                var div = document.createElement('div');
                div.innerHTML = raw;
                var links = div.querySelectorAll('a[href]');
                for(var i=0; i<links.length; i++){
                    var href = links[i].getAttribute('href') || '';
                    if(/^https?:\\/\\//i.test(href)){
                        links[i].setAttribute('target', '_blank');
                        links[i].setAttribute('rel', 'noopener noreferrer');
                    }
                }
                return div.innerHTML;
            } catch(e){
                return '<pre>' + esc(md || '') + '</pre>';
            }
        }

        function _renderStockPushesPanel(holder, code){
            var pushes = _stockPushesCache[code] || [];
            if(!pushes.length){ holder.innerHTML = ''; return; }
            // 限制显示数量，避免太长
            var shown = pushes.slice(0, 12);
            var titles = shown.map(function(p, idx){
                var t = _fmtPushTime(p.created_at || p.updated_at);
                var md = p.message_md || '';
                var firstLine = md.split('\\n').filter(function(L){return L.trim();})[0] || '';
                var summary = firstLine.replace(/^[#*\\-\\s>]+/, '').substring(0, 60) || '(空标题)';
                return '<li class="news-title-row' + (idx === 0 ? ' active' : '') + '" data-idx="' + idx + '">'
                    +   '<span class="news-push-time">' + esc(t) + '</span>'
                    +   '<span class="news-push-title">' + esc(summary) + '</span>'
                    + '</li>';
            }).join('');
            // 默认显示第一条 md
            var firstHtml = _renderMdSafe(shown[0].message_md || '');
            holder.innerHTML =
                '<div class="news-pushes-head">📰 今日推送 · ' + pushes.length + ' 条 <span class="news-pushes-hint">点击左侧标题切换内容</span></div>'
                + '<div class="news-pushes-2col">'
                +   '<ul class="news-pushes-titlebar">' + titles + '</ul>'
                +   '<div class="news-pushes-detail markdown-body">' + firstHtml + '</div>'
                + '</div>';
            // 缓存 md 列表给点击切换用
            holder._pushMds = shown.map(function(p){return p.message_md || '';});
            // 绑点击切换
            var rows = holder.querySelectorAll('.news-title-row');
            var detail = holder.querySelector('.news-pushes-detail');
            for(var i=0; i<rows.length; i++){
                (function(li){
                    li.onclick = function(){
                        for(var j=0; j<rows.length; j++) rows[j].classList.remove('active');
                        li.classList.add('active');
                        var idx = parseInt(li.getAttribute('data-idx'), 10);
                        if(detail) detail.innerHTML = _renderMdSafe(holder._pushMds[idx] || '');
                    };
                })(rows[i]);
            }
        }

        window.toggleStockNewsRow = function(btn){
            var code = btn.getAttribute('data-stock-code');
            var newsRow = document.querySelector('.uw-news-row[data-news-row-for="' + code + '"]');
            if(newsRow) newsRow.classList.toggle('open');
        };

        window.toggleStockSub = async function(checkbox, subId){
            var enabled = checkbox.checked;
            try {
                var r = await fetch('/api/wealth/stock_subscriptions/' + encodeURIComponent(subId) + '/toggle', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({enabled: enabled}),
                });
                var d = await r.json();
                if(!d.ok){
                    alert('切换失败: ' + (d.error || 'unknown'));
                    checkbox.checked = !enabled;
                } else {
                    loadStockSubs();
                }
            } catch(e){
                alert('请求失败: ' + e.message);
                checkbox.checked = !enabled;
            }
        };

        window.runStockSub = async function(subId, btn){
            try {
                var r = await fetch('/api/wealth/stock_subscriptions/' + encodeURIComponent(subId) + '/run', {method:'POST'});
                var d = await r.json();
                if(!d.ok){
                    alert('触发失败: ' + (d.error || 'unknown'));
                    if(btn){ btn.disabled = false; btn.textContent = '采集'; }
                    return;
                }
            } catch(e){
                alert('请求失败: ' + e.message);
                if(btn){ btn.disabled = false; btn.textContent = '采集'; }
                return;
            }
            // loadStockSubs 自带递归轮询：sub.running=true → 2s 后自调直到完成
            await loadStockSubs();
        };
    })();
    </script>
"""


def build_wealth_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 理财</title>
    <!-- 关注股资讯推送内容用 markdown 渲染（同游戏面板）-->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + WEALTH_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("wealth")
        + WEALTH_BODY
        + WEALTH_SCRIPT
        + """</body>
</html>"""
    )
