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
        display: grid; grid-template-columns: 36px 1fr auto; gap: 8px; padding: 6px 8px;
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

    /* markdown body 样式（通用 — 水神资讯 / 角色搜索 共用）*/
    .markdown-body {
        font-size: 13px; color: var(--text-primary); line-height: 1.6;
        padding: 6px 4px;
    }
    .markdown-body h1, .markdown-body h2, .markdown-body h3,
    .markdown-body h4, .markdown-body h5, .markdown-body h6 {
        color: var(--gold); font-weight: 600;
        margin: 12px 0 6px; line-height: 1.3;
    }
    .markdown-body h1 { font-size: 16px; }
    .markdown-body h2 { font-size: 15px; }
    .markdown-body h3 { font-size: 14px; }
    .markdown-body h4, .markdown-body h5, .markdown-body h6 { font-size: 13px; }
    .markdown-body p { margin: 6px 0; }
    .markdown-body ul, .markdown-body ol { margin: 6px 0; padding-left: 22px; }
    .markdown-body li { margin: 2px 0; }
    .markdown-body a { color: var(--gold-light); text-decoration: underline; }
    .markdown-body a:hover { color: var(--gold); }
    .markdown-body code {
        background: var(--paimon-bg); padding: 1px 5px; border-radius: 3px;
        font-family: 'SF Mono', Consolas, monospace; font-size: 12px;
        color: var(--gold-light);
    }
    .markdown-body pre {
        background: var(--paimon-bg); padding: 8px 10px; border-radius: 5px;
        overflow-x: auto; margin: 6px 0;
    }
    .markdown-body pre code {
        background: transparent; padding: 0; color: var(--text-primary);
    }
    .markdown-body blockquote {
        border-left: 3px solid var(--gold-dark);
        padding: 2px 10px; margin: 6px 0;
        color: var(--text-muted);
    }
    .markdown-body strong { color: var(--text-primary); font-weight: 600; }
    .markdown-body hr { border: none; border-top: 1px dashed var(--paimon-border); margin: 10px 0; }

    /* ========= 水神·游戏资讯 + 角色搜索（嵌入各 game tab 顶部）========= */
    .fr-section {
        margin: 0 0 12px;
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-radius: 8px;
        padding: 8px 12px;
    }
    .fr-body { display: flex; gap: 0; min-height: 140px; }
    .fr-col { flex: 1; min-width: 0; display: flex; flex-direction: column; padding: 0 10px; }
    .fr-col-news { padding-left: 0; }
    .fr-col-search {
        padding-right: 0;
        border-left: 1px dashed var(--paimon-border);
    }
    .fr-col-title {
        font-size: 12px; font-weight: 600; color: var(--text-primary);
        margin-bottom: 4px; padding-bottom: 3px;
        border-bottom: 1px dashed var(--paimon-border);
        display: flex; align-items: baseline;
    }
    .fr-col-hint {
        font-weight: 400; color: var(--text-muted); margin-left: auto; font-size: 10px;
    }
    .fr-col-scroll {
        flex: 1; overflow-y: auto; max-height: 28vh;
        padding: 2px 4px 2px 0;
        font-size: 12px; line-height: 1.5; color: var(--text-secondary);
    }
    .fr-col-scroll.markdown-body { padding: 2px 4px 2px 0; }
    .fr-col-scroll .markdown-body { padding: 0; }
    .fr-empty {
        padding: 14px 10px; text-align: center;
        color: var(--text-muted); font-style: italic;
        line-height: 1.55; font-size: 12px;
    }
    .fr-empty-icon {
        display: block; font-size: 20px; opacity: .55;
        margin-bottom: 4px; font-style: normal;
    }
    .fr-search-bar { display: flex; gap: 6px; margin-bottom: 6px; }
    .fr-search-input {
        flex: 1; min-width: 0; padding: 5px 9px;
        background: var(--paimon-bg-deep); color: var(--text-primary);
        border: 1px solid var(--paimon-border); border-radius: 5px;
        font-size: 12px;
    }
    .fr-search-input:focus { outline: none; border-color: var(--gold-dark); }
    .fr-search-input::placeholder { color: var(--text-muted); }
    .fr-result-meta {
        font-size: 10px; color: var(--text-muted); font-style: italic;
        margin-bottom: 6px; padding-bottom: 4px;
        border-bottom: 1px dashed var(--paimon-border);
    }

    /* char-row 永久显示的 🔍 按钮（grid 第三列 auto） */
    .char-research-btn {
        background: transparent;
        border: 1px solid var(--paimon-border);
        border-radius: 4px;
        width: 26px; height: 26px;
        font-size: 13px; line-height: 1;
        cursor: pointer;
        color: var(--text-muted);
        transition: all .15s;
    }
    .char-research-btn:hover {
        background: var(--gold-dark); color: var(--paimon-bg);
        border-color: var(--gold);
    }
    .char-row:hover .char-research-btn {
        color: var(--gold);
        border-color: var(--gold-dark);
    }

"""
