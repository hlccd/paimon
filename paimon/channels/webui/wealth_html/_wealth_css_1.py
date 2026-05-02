"""WEALTH_CSS chunk · 自动切片，原始字符串拼接还原。"""

WEALTH_CSS_1 = """
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
    .news-push-body strong { color: var(--text-primary); font-weight: 600; }"""
