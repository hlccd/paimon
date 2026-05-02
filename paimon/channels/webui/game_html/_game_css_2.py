"""GAME_CSS chunk · 自动切片，原始字符串拼接还原。"""

GAME_CSS_2 = """        text-align: center; padding: 40px 20px; color: var(--text-muted);
        background: var(--paimon-panel); border: 1px dashed var(--paimon-border);
        border-radius: 10px;
    }

    /* ========= 角色养成网格 ========= */
    .char-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
        gap: 10px;
    }
    .char-card {
        background: var(--paimon-bg); border: 1px solid var(--paimon-border);
        border-radius: 8px; padding: 10px; display: flex; gap: 10px; align-items: center;
        transition: border-color .15s;
    }
    .char-card:hover { border-color: var(--gold-dark); }
    .char-card.r5 { border-color: #c88a3a; background: linear-gradient(135deg, rgba(200,138,58,.08), var(--paimon-bg)); }
    .char-card.r4 { border-color: #8a5fc8; background: linear-gradient(135deg, rgba(138,95,200,.08), var(--paimon-bg)); }
    .char-icon {
        width: 44px; height: 44px; border-radius: 6px; flex-shrink: 0;
        background: var(--paimon-border) center/cover no-repeat;
    }
    .char-main { min-width: 0; flex: 1; }
    .char-name {
        font-size: 13px; font-weight: 600; color: var(--text-primary);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .char-meta {
        font-size: 11px; color: var(--text-muted); margin-top: 2px;
        display: flex; gap: 6px; flex-wrap: wrap;
    }
    .char-lv { color: var(--gold); font-family: monospace; font-weight: 500; }
    .char-cons {
        display: inline-flex; gap: 2px;
    }
    .cons-dot {
        width: 6px; height: 6px; border-radius: 50%;
        background: var(--paimon-border);
    }
    .cons-dot.on { background: var(--gold); }
    .cons-dot.r5.on { background: #e5b255; }
    .char-filter-bar {
        display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap;
    }
    .char-filter {
        padding: 3px 10px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 10px;
        font-size: 11px; cursor: pointer; color: var(--text-muted);
    }
    .char-filter.active { border-color: var(--gold); color: var(--gold); }
    .char-stat-line {
        font-size: 11px; color: var(--text-muted); margin-bottom: 10px;
    }
    .char-stat-line .num { color: var(--gold); font-family: monospace; font-weight: 600; }

    /* 单列角色 list（每行一个，含武器名） */
    .char-list { display: flex; flex-direction: column; gap: 4px; }
    .char-row {
        display: grid; grid-template-columns: 36px 1fr; gap: 8px; padding: 6px 8px;
        align-items: center; border-radius: 6px;
        background: rgba(0,0,0,.15); border-left: 2px solid var(--paimon-border);
    }
    .char-row.r5 { border-left-color: var(--gold); background: linear-gradient(90deg, rgba(212,175,55,.06), rgba(0,0,0,.15)); }
    .char-row.r4 { border-left-color: #8a5fc8; background: linear-gradient(90deg, rgba(138,95,200,.06), rgba(0,0,0,.15)); }
    .char-icon-sm {
        width: 36px; height: 36px; border-radius: 50%;
        background: var(--paimon-border) center/cover no-repeat;
    }
    .char-info { min-width: 0; }
    .char-line1 { display: flex; align-items: baseline; gap: 8px; line-height: 1.3; }
    .char-line1 .char-name { font-size: 13px; color: var(--text-primary); font-weight: 500; }
    .char-line1 .char-lv { font-size: 11px; color: var(--text-muted); font-family: monospace; }
    .char-line1 .char-ca {
        font-size: 11px; color: var(--gold); font-family: monospace; font-weight: 600;
        margin-left: auto; padding: 1px 6px; border: 1px solid rgba(212,175,55,.3); border-radius: 8px;
    }
    .char-line2 { font-size: 11px; color: var(--text-muted); margin-top: 1px; }
    .char-line2.wp5 { color: #f4d03f; }
    .char-line2.wp4 { color: #b46cff; }
    .char-line2 .muted { color: var(--text-muted); opacity: .6; }

    /* 占位（用于尚未接入的 sr/zzz 角色 tab） */
    .coming-soon {
        padding: 24px; text-align: center; color: var(--text-muted);
        background: var(--paimon-bg); border-radius: 8px; font-size: 13px;
        border: 1px dashed var(--paimon-border);
    }
    .coming-soon .cs-title { color: var(--gold); font-size: 13px; margin-bottom: 6px; }

    /* ========= 📰 游戏资讯订阅（总览卡资讯行 + 详情区完整控件）========= */
    /* 总览卡资讯行：紧贴账号卡内部，单行显示状态+预览+立即采集 */
    .ac-news-line {
        display: grid;
        grid-template-columns: auto auto 1fr auto;
        gap: 10px; align-items: center;
        margin: 0 18px 12px;
        padding: 6px 10px;
        background: var(--paimon-bg);
        border-radius: 6px;
        border-left: 2px solid var(--paimon-border);
        font-size: 12px; color: var(--text-secondary);
        transition: border-color .15s, background .15s;
    }
    .ac-news-line.on { border-left-color: var(--status-success); }
    .ac-news-line.err { border-left-color: var(--status-error); background: rgba(239,68,68,.04); }
    .ac-news-line.busy {
        border-left-color: var(--gold);
        background: rgba(245,158,11,.06);
    }
    .ac-news-line.busy .news-toggle {
        color: var(--gold);
    }
    .ac-news-line.busy .news-toggle .dot {
        background: var(--gold);
        animation: news-pulse 1.2s ease-in-out infinite;
    }
    @keyframes news-pulse {
        0%, 100% { opacity: 0.4; }
        50% { opacity: 1; }
    }
    .ac-news-line .news-toggle {
        display: inline-flex; align-items: center; gap: 5px;
        cursor: pointer; user-select: none;
        color: var(--text-muted); font-size: 11px;
    }
    .ac-news-line .news-toggle .dot {
        width: 7px; height: 7px; border-radius: 50%;
        background: var(--text-muted); transition: background .15s;
    }
    .ac-news-line.on .news-toggle { color: var(--status-success); }
    .ac-news-line.on .news-toggle .dot { background: var(--status-success); }
    .ac-news-line .news-icon { color: var(--gold); font-size: 12px; }
    .ac-news-line .news-text {
        color: var(--text-secondary);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        min-width: 0;
    }
    .ac-news-line .news-text .meta { color: var(--text-muted); margin-right: 6px; }
    .ac-news-line .news-text .title { color: var(--text-primary); }
    .ac-news-line .news-text .err-msg { color: var(--status-error); }
    .ac-news-line .news-run {
        padding: 3px 10px; font-size: 11px;
        background: transparent; color: var(--text-muted);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        cursor: pointer; transition: border-color .15s, color .15s;
    }
    .ac-news-line .news-run:hover {
        border-color: var(--gold-dark); color: var(--gold);
    }
    .ac-news-line .news-run:disabled { opacity: .5; cursor: progress; }

    /* 详情卡专属：推送列表面板（仅游戏 tab 完整卡有，紧贴 ac-news-line 下方）*/
    .ac-news-pushes:empty { display: none; }
    .ac-news-pushes {
        margin: 0 18px 14px;
        padding: 10px 14px;
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-radius: 8px;
    }
    .news-pushes-head {
        font-size: 12px; color: var(--text-secondary); font-weight: 600;
        margin-bottom: 8px;
    }
    .news-pushes-list {
        list-style: none; padding: 0; margin: 0;
        display: flex; flex-direction: column; gap: 6px;
    }
    .news-push-item {
        padding: 7px 10px;
        background: var(--paimon-panel);
        border-left: 2px solid var(--gold-dark);
        border-radius: 0 4px 4px 0;
    }
    .news-push-head {
        display: flex; align-items: baseline; gap: 8px;
        margin-bottom: 3px;
        overflow: hidden;
    }
    .news-push-time {
        font-size: 11px; color: var(--text-muted);
        font-family: 'SF Mono', Consolas, monospace; flex-shrink: 0;
    }
    .news-push-title {
        font-size: 13px; color: var(--text-primary); font-weight: 500;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        flex: 1; min-width: 0;
    }
    /* 折叠交互（div + class.open，不用 native details 避免 md 内容污染） */
    .news-pushes-hint {
        font-size: 10px; color: var(--text-muted); font-weight: 400;
        margin-left: 6px;
    }
    .news-push-item .news-push-body { display: none; }
    .news-push-item.open .news-push-body { display: block; }
    .news-push-item.open .news-push-head {
        border-bottom: 1px solid var(--paimon-border);
        padding-bottom: 6px; margin-bottom: 8px;
    }
    .news-push-head {
        cursor: pointer; user-select: none;
        display: flex; align-items: baseline; gap: 8px;
    }
    .news-push-arrow {
        color: var(--gold); font-size: 10px;
        transition: transform .15s;
        flex-shrink: 0;
    }
    .news-push-item.open .news-push-arrow { transform: rotate(90deg); }

    /* 总览汇总形态：极简列表 + 跳详情链接 */
    .news-pushes-list-summary {
        list-style: none; padding: 0; margin: 0;
    }
    .news-summary-row {
        display: flex; gap: 10px; align-items: baseline;
        padding: 4px 0;
        font-size: 12px;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .news-summary-row .news-push-time {
        color: var(--text-muted); flex-shrink: 0;
        font-family: 'SF Mono', Consolas, monospace;
    }
    .news-summary-row .news-push-title {
        color: var(--text-primary);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        flex: 1; min-width: 0;
    }
    .news-more {
        margin-top: 6px; padding-top: 6px;
        border-top: 1px dashed var(--paimon-border);
        text-align: right;
    }
    .news-more-link {
        font-size: 11px; color: var(--gold); cursor: pointer;
        user-select: none;
    }
    .news-more-link:hover { color: var(--gold-light); text-decoration: underline; }

    /* markdown body 样式（同主聊天面板渲染风格）*/
    .news-push-body.markdown-body {
        font-size: 13px; color: var(--text-primary); line-height: 1.6;
        padding: 6px 4px;
    }
    .news-push-body h1, .news-push-body h2, .news-push-body h3,
    .news-push-body h4, .news-push-body h5, .news-push-body h6 {
        color: var(--gold); font-weight: 600;
        margin: 12px 0 6px; line-height: 1.3;
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
    .news-push-body pre code {
        background: transparent; padding: 0; color: var(--text-primary);
    }
    .news-push-body blockquote {
        border-left: 3px solid var(--gold-dark);
        padding: 2px 10px; margin: 6px 0;
        color: var(--text-muted);
    }
    .news-push-body strong { color: var(--text-primary); font-weight: 600; }
    .news-push-body hr { border: none; border-top: 1px dashed var(--paimon-border); margin: 10px 0; }

"""
