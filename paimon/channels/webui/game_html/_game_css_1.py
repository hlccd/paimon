"""GAME_CSS chunk · 自动切片，原始字符串拼接还原。"""

GAME_CSS_1 = """
    body { min-height: 100vh; }
    .container { max-width: 1100px; margin: 0 auto; padding: 24px; }

    /* ========= 顶部状态条 ========= */
    .status-bar {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 20px;
    }
    .status-title h1 { font-size: 22px; color: var(--text-primary); font-weight: 600; }
    .status-title .sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
    .status-actions { display: flex; gap: 8px; }

    /* ========= 按钮 ========= */
    .btn {
        padding: 7px 14px; font-size: 13px; border-radius: 6px;
        background: var(--paimon-panel); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); cursor: pointer;
        transition: border-color .15s, color .15s, background .15s;
    }
    .btn:hover { border-color: var(--gold-dark); color: var(--gold); }
    .btn.primary {
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        color: #000; border: none; font-weight: 600;
    }
    .btn.primary:hover { filter: brightness(1.08); }
    .btn.danger:hover { color: var(--status-error); border-color: var(--status-error); }
    .btn.tiny { padding: 4px 10px; font-size: 12px; }
    .btn:disabled { opacity: .5; cursor: not-allowed; }

    /* ========= 账号卡 ========= */
    .account-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 12px; margin-bottom: 14px; overflow: hidden;
        transition: border-color .2s;
    }
    .account-card:hover { border-color: var(--gold-dark); }

    /* ---- 紧凑摘要行 ---- */
    .ac-summary {
        display: grid;
        grid-template-columns: 200px 1fr auto;
        gap: 18px; align-items: center;
        padding: 14px 18px;
    }
    .ac-identity { display: flex; align-items: center; gap: 12px; min-width: 0; }
    /* 游戏 logo：汉字核心 + 官方主色渐变圆，不依赖外链图片 */
    .game-logo {
        display: inline-flex; align-items: center; justify-content: center;
        width: 36px; height: 36px; border-radius: 50%;
        font-size: 18px; font-weight: 700; color: #fff;
        font-family: "Noto Sans CJK SC", "Microsoft YaHei", serif;
        flex-shrink: 0; letter-spacing: 0;
        box-shadow: 0 2px 6px rgba(0,0,0,.35);
        text-shadow: 0 1px 2px rgba(0,0,0,.4);
    }
    .game-logo.gs  { background: linear-gradient(135deg, #d4af37 0%, #8b7530 100%); }  /* 原神金 */
    .game-logo.sr  { background: linear-gradient(135deg, #b084f0 0%, #5a3a8c 100%); }  /* 星穹紫 */
    .game-logo.zzz { background: linear-gradient(135deg, #f0d530 0%, #a08010 100%); color: #2a2000; }  /* 绝区零黄 */
    .ac-names { min-width: 0; }
    .ac-game-name {
        color: var(--gold); font-weight: 600; font-size: 14px;
        display: flex; align-items: baseline; gap: 6px;
    }
    .ac-note {
        color: var(--text-primary); font-weight: 500;
    }
    .ac-uid {
        font-family: monospace; color: var(--text-muted); font-size: 11px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }

    /* 中间状态区：树脂条 + 状态 chips */
    .ac-status { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
    .ac-resin-line {
        display: flex; align-items: center; gap: 10px;
    }
    .ac-resin-label {
        font-size: 11px; color: var(--text-muted);
        min-width: 40px; text-align: right;
    }
    .ac-resin-bar {
        flex: 1; height: 8px; background: var(--paimon-border);
        border-radius: 4px; overflow: hidden; position: relative;
        max-width: 260px;
    }
    .ac-resin-fill {
        height: 100%; border-radius: 4px; transition: width .3s;
        background: linear-gradient(90deg, #6ec6ff, #bb86fc);
    }
    .ac-resin-fill.warn  { background: linear-gradient(90deg, var(--gold), #f4c430); }
    .ac-resin-fill.full  { background: linear-gradient(90deg, var(--status-error), var(--gold)); }
    .ac-resin-num {
        font-family: monospace; font-size: 12px; color: var(--text-primary);
        min-width: 68px; text-align: right;
    }
    .ac-resin-when {
        font-size: 11px; color: var(--text-muted); min-width: 88px;
    }
    .ac-resin-when.urgent { color: var(--status-error); font-weight: 600; }

    .ac-chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
        padding: 2px 10px; border-radius: 12px;
        font-size: 11px; background: var(--paimon-bg);
        color: var(--text-secondary); white-space: nowrap;
    }
    .chip.ok   { color: var(--status-success); }
    .chip.warn { color: var(--gold); }
    .chip.bad  { color: var(--status-error); }

    /* 右侧操作 */
    .ac-ops { display: flex; gap: 6px; align-items: center; }
    .ac-toggle {
        background: transparent; border: 1px solid var(--paimon-border);
        color: var(--text-muted); cursor: pointer; padding: 6px 10px;
        border-radius: 6px; font-size: 12px; transition: color .15s, transform .15s;
    }
    .ac-toggle:hover { color: var(--gold); }
    .ac-toggle .arrow { display: inline-block; transition: transform .2s; margin-left: 2px; }
    .ac-toggle.open .arrow { transform: rotate(180deg); }

    /* ---- 展开详情区 ---- */
    .ac-detail {
        display: none;
        border-top: 1px solid var(--paimon-border);
        padding: 16px 18px;
        background: rgba(0,0,0,.15);
    }
    .ac-detail.open { display: block; }
    /* 详情页 grid：左中两 panel（抽卡上 / 深渊下） + 右栏（角色，跨两行） */
    /* 状态条已在外层 ac-summary 里显示树脂+chips，detail 内不重复 */
    .ac-detail-grid {
        display: grid;
        grid-template-columns: 1fr;
        grid-template-rows: auto auto;
        gap: 12px;
    }
    @media (min-width: 980px) {
        .ac-detail-grid { grid-template-columns: minmax(0,1fr) 340px; }
    }
    .ac-detail-grid > .gacha-pane { grid-column: 1; grid-row: 1; }
    .ac-detail-grid > .abyss-pane { grid-column: 1; grid-row: 2; }
    @media (min-width: 980px) {
        .ac-detail-grid > .chars-pane { grid-column: 2; grid-row: 1 / span 2; align-self: start; }
    }
    .ac-panel {
        background: rgba(0,0,0,.18); border: 1px solid var(--paimon-border);
        border-radius: 8px; padding: 12px 14px; min-width: 0;
        display: flex; flex-direction: column;
    }
    .ac-panel.h-fixed { height: 360px; }
    .ac-panel.h-fixed > .panel-body { flex: 1; min-height: 0; overflow-y: auto; position: relative; }
    .ac-panel.h-fixed-tall { height: calc(360px * 2 + 12px); max-height: 80vh; }
    .ac-panel.h-fixed-tall > .panel-body { flex: 1; min-height: 0; overflow-y: auto; }
    .panel-title {
        font-size: 11px; color: var(--text-muted); text-transform: uppercase;
        letter-spacing: .6px; margin-bottom: 10px;
        display: flex; justify-content: space-between; align-items: center;
        flex-shrink: 0;
    }
    .panel-hint { font-size: 10px; color: var(--text-muted); text-transform: none; letter-spacing: 0; font-weight: normal; }
    /* 抽卡同步按钮粘底 */
    .gacha-pane .gacha-sync-row {
        position: sticky; bottom: 0; margin-top: 8px;
        padding: 8px 0 4px; background: rgba(0,0,0,.18);
        border-top: 1px solid var(--paimon-border);
        z-index: 2;
    }
    /* 角色 filter 粘顶（滚动时永远可见） */
    .chars-pane .char-filter-bar, .chars-pane .char-stat-line {
        position: sticky; background: rgba(0,0,0,.18); z-index: 2;
        padding: 4px 0;
    }
    .chars-pane .char-stat-line { top: 0; }
    .chars-pane .char-filter-bar { top: 28px; border-bottom: 1px solid var(--paimon-border); margin-bottom: 6px; }
    /* "最欧/最歪/平均"小标签 */
    .gacha-luck-row {
        display: flex; gap: 8px; padding: 6px 8px; margin-top: 6px;
        background: rgba(0,0,0,.2); border-radius: 4px;
        font-size: 11px; flex-wrap: wrap;
    }
    .gacha-luck-row .luck-item { color: var(--text-muted); }
    .gacha-luck-row .luck-item .v { color: var(--text-primary); font-family: monospace; font-weight: 600; margin-left: 4px; }
    .gacha-luck-row .luck-item.lucky .v { color: var(--status-ok, #4caf50); }
    .gacha-luck-row .luck-item.heavy .v { color: var(--status-error); }
    /* 主力角色 chips（深渊出场频次） */
    .top-heroes {
        display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0 10px;
    }
    .top-heroes .hero-chip {
        padding: 2px 8px; border-radius: 10px; font-size: 11px;
        background: var(--paimon-bg); color: var(--text-secondary);
    }
    .top-heroes .hero-chip .cnt { color: var(--gold); font-family: monospace; margin-left: 3px; }
    .top-heroes-label { font-size: 10px; color: var(--text-muted); margin-bottom: 4px; }
    .detail-section { margin-bottom: 18px; }
    .detail-section:last-child { margin-bottom: 0; }
    .detail-title {
        font-size: 11px; color: var(--text-muted); text-transform: uppercase;
        letter-spacing: .6px; margin-bottom: 10px;
        display: flex; justify-content: space-between; align-items: center;
    }
    /* 顶部状态条：树脂/体力/电量 + 委托/派遣 chips */
    .status-bar {
        display: flex; flex-wrap: wrap; align-items: center; gap: 16px;
        padding: 12px 14px; border-radius: 8px;
        background: linear-gradient(90deg, rgba(212,175,55,.06), rgba(0,0,0,.18));
        border: 1px solid var(--paimon-border);
    }
    .status-stamina {
        display: flex; align-items: center; gap: 8px; min-width: 220px;
    }
    .status-stamina .label { color: var(--text-muted); font-size: 12px; }
    .status-stamina .num { color: var(--gold); font-family: monospace; font-weight: 600; font-size: 14px; }
    .status-stamina .full { color: var(--status-error); }
    .status-stamina .when { color: var(--text-muted); font-size: 11px; }
    .status-bar-bar {
        flex: 1; height: 6px; background: var(--paimon-bg); border-radius: 3px;
        overflow: hidden; min-width: 100px; max-width: 240px;
    }
    .status-bar-fill { height: 100%; background: var(--gold); transition: width .3s; }
    .status-bar-fill.full { background: var(--status-error); }
    .status-chip {
        padding: 4px 10px; border-radius: 12px; font-size: 11px;
        background: var(--paimon-bg); color: var(--text-secondary);
    }
    .status-chip.done { color: var(--status-success); border: 1px solid rgba(76,175,80,.3); }
    .status-chip .num { color: var(--text-primary); font-family: monospace; font-weight: 600; }

    /* 深渊行 + 队伍展开 */
    .abyss-row { cursor: pointer; }
    .abyss-row:hover { background: rgba(255,255,255,.03); }
    .abyss-teams {
        display: block;       /* 默认展开看队伍，点击行可收起 */
        padding: 6px 0 4px 12px; margin: 0 0 6px 0;
        border-left: 2px solid var(--paimon-border);
    }
    .abyss-teams.closed { display: none; }
    .abyss-team {
        display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
        padding: 4px 0;
        font-size: 11px; color: var(--text-muted);
    }
    .abyss-team-label { min-width: 64px; color: var(--text-muted); font-family: monospace; }
    .abyss-team-avatar {
        display: inline-flex; align-items: center; gap: 3px;
        padding: 2px 6px; background: var(--paimon-bg); border-radius: 10px;
        font-size: 11px;
    }
    .abyss-team-avatar.r5 { color: #f4d03f; border: 1px solid rgba(244,208,63,.3); }
    .abyss-team-avatar.r4 { color: #b46cff; border: 1px solid rgba(180,108,255,.3); }
    .abyss-team-avatar .lv { color: var(--text-muted); font-size: 10px; }
    .abyss-toggle { color: var(--text-muted); font-size: 10px; margin-left: 6px; }

    /* 战报表格 */
    .abyss-rows { }
    .abyss-row {
        display: grid; grid-template-columns: 140px 1fr 80px 100px;
        align-items: center; gap: 10px;
        padding: 7px 0; border-bottom: 1px dashed var(--paimon-border);
        font-size: 13px;
    }
    .abyss-row:last-child { border-bottom: none; }
    .abyss-name  { color: var(--text-secondary); }
    .abyss-floor { color: var(--text-primary); font-family: monospace; font-size: 12px; }
    .abyss-star  { color: var(--gold); text-align: right; font-family: monospace; font-weight: 600; }
    .abyss-meta  { color: var(--text-muted); text-align: right; font-size: 11px; }
    .abyss-empty { color: var(--text-muted); font-size: 12px; text-align: center; padding: 12px 0; }

    /* 派遣 chips（展开后完整列表） */
    .exp-detail { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
    .exp-chip {
        padding: 2px 8px; background: var(--paimon-bg); border-radius: 10px;
        font-size: 11px; color: var(--text-muted);
    }
    .exp-chip.ready { color: var(--status-success); border: 1px solid var(--status-success); }

    /* 抽卡 */
    .gacha-head {
        display: flex; gap: 4px; margin-bottom: 10px; flex-wrap: wrap;
    }
    .gpool {
        padding: 3px 10px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 10px;
        font-size: 11px; cursor: pointer; color: var(--text-muted);
    }
    .gpool.active { border-color: var(--gold); color: var(--gold); }
    .gacha-summary {
        font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;
        padding: 8px 12px; background: var(--paimon-bg); border-radius: 6px;
    }
    .gacha-summary .pity { color: var(--gold); font-weight: 600; font-family: monospace; }
    .gacha-summary .pity.warn { color: var(--status-error); }
    .gacha-summary .pity.soft { color: #f4d03f; }     /* ≥软保底但未到硬保底 */
    .gacha-summary .sep { color: var(--text-muted); margin: 0 8px; }
    .gacha-five-list { max-height: 260px; overflow-y: auto; }
    .gfive {
        display: grid; grid-template-columns: 28px 1fr 56px 56px 92px;
        gap: 6px; align-items: center; padding: 6px 4px;
        font-size: 12px; border-bottom: 1px dashed var(--paimon-border);
    }
    .gfive:last-child { border-bottom: none; }
    .gfive-badge { color: #f4d03f; font-weight: 700; text-align: center; }
    .gfive-name  { color: var(--text-primary); }
    .gfive-pull  { color: var(--gold); font-family: monospace; text-align: center; }
    .gfive-pull.lucky { color: var(--status-ok, #4caf50); }     /* ≤30 抽欧皇 */
    .gfive-pull.heavy { color: var(--status-error); }            /* ≥80 抽接近硬保底 */
    .gfive-up { font-size: 10px; padding: 1px 0; border-radius: 3px; text-align: center; font-weight: 600; }
    .gfive-up.on  { background: rgba(76,175,80,.15); color: var(--status-ok, #4caf50); border: 1px solid rgba(76,175,80,.4); }
    .gfive-up.off { background: rgba(255,152,0,.15); color: #ff9800; border: 1px solid rgba(255,152,0,.4); }
    .gfive-up.none{ color: var(--text-muted); border: 1px solid var(--paimon-border); }
    .gfive-time  { color: var(--text-muted); font-family: monospace; font-size: 11px; text-align: right; }
    .gacha-sync-row {
        display: flex; justify-content: flex-end; align-items: center;
        gap: 8px; margin-top: 10px;
    }
    .gacha-sync-status {
        font-size: 11px; color: var(--text-muted); font-family: monospace;
    }
    .gacha-sync-status.running { color: var(--gold); }
    .gacha-sync-status.failed  { color: var(--status-error); }
    .gacha-sync-status.done    { color: var(--status-ok, #4caf50); }

    /* ========= URL 导入 modal ========= */
    .urlimport-modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 12px; padding: 24px; max-width: 600px; width: 92%;
    }
    .urlimport-modal h3 { color: var(--gold); font-size: 15px; margin-bottom: 12px; }
    .urlimport-modal .tutorial {
        background: var(--paimon-bg); border-left: 3px solid var(--gold);
        padding: 10px 14px; border-radius: 4px; margin-bottom: 12px;
        font-size: 12px; color: var(--text-secondary); line-height: 1.7;
    }
    .urlimport-modal .tutorial b { color: var(--text-primary); }
    .urlimport-modal .tutorial code {
        background: rgba(0,0,0,.25); padding: 1px 6px; border-radius: 3px;
        font-family: monospace; font-size: 11px;
    }
    .urlimport-modal textarea {
        width: 100%; min-height: 90px; padding: 8px 10px; box-sizing: border-box;
        background: var(--paimon-bg); color: var(--text-primary);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        font-family: monospace; font-size: 11px; resize: vertical;
    }
    .urlimport-modal .actions {
        display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px;
    }
    /* 教程里的 PowerShell 命令块 */
    .ps-cmd-box { position: relative; margin-top: 4px; }
    .ps-cmd-box textarea {
        width: 100%; height: 64px; box-sizing: border-box;
        padding: 6px 70px 6px 8px; font-size: 10px; font-family: monospace;
        background: rgba(0,0,0,.35); color: var(--text-primary);
        border: 1px solid var(--paimon-border); border-radius: 4px; resize: none;
    }
    .ps-cmd-copy {
        position: absolute; top: 4px; right: 4px;
        padding: 3px 10px; font-size: 11px; cursor: pointer;
        background: var(--paimon-panel); color: var(--gold);
        border: 1px solid var(--gold); border-radius: 4px;
    }
    .ps-cmd-copy:hover { background: var(--gold); color: var(--paimon-panel); }
    .ps-cmd-copy.done { color: var(--status-ok, #4caf50); border-color: var(--status-ok, #4caf50); }
    .gacha-empty {
        color: var(--text-muted); font-size: 12px; text-align: center; padding: 16px 0;
    }

    /* 高级操作 */
    .detail-ops {
        display: flex; justify-content: flex-end; gap: 6px;
        padding-top: 12px; border-top: 1px dashed var(--paimon-border);
    }

    /* ========= 空状态（未绑定） ========= */
    .empty-bind {
        text-align: center; padding: 60px 20px;
        background: var(--paimon-panel); border: 1px dashed var(--paimon-border);
        border-radius: 12px;
    }
    .empty-bind h2 { font-size: 16px; color: var(--text-secondary); margin-bottom: 8px; font-weight: 500; }
    .empty-bind p  { font-size: 13px; color: var(--text-muted); margin-bottom: 18px; }

    /* ========= 扫码 modal ========= */
    .qr-modal-backdrop {
        display: none; position: fixed; inset: 0;
        background: rgba(0,0,0,.65); backdrop-filter: blur(4px);
        z-index: 1000; align-items: center; justify-content: center;
    }
    .qr-modal-backdrop.show { display: flex; }
    .qr-modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 12px; padding: 24px; max-width: 360px; width: 92%;
    }
    .qr-modal-head {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 14px;
    }
    .qr-modal-head h3 { color: var(--gold); font-size: 15px; }
    .qr-close {
        background: transparent; border: none; color: var(--text-muted);
        font-size: 22px; cursor: pointer; line-height: 1; padding: 0 6px;
    }
    .qr-close:hover { color: var(--status-error); }
    .qr-box {
        width: 240px; height: 240px; background: #fff; border-radius: 8px;
        margin: 0 auto; display: flex; align-items: center; justify-content: center;
    }
    .qr-box img { width: 100%; height: 100%; }
    .qr-hint { text-align: center; font-size: 12px; color: var(--text-secondary); margin-top: 12px; }
    .qr-hint.small { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
    .qr-status { text-align: center; font-size: 12px; color: var(--text-muted); margin-top: 8px; min-height: 16px; }

    /* ========= 响应式（窄屏） ========= */
    @media (max-width: 720px) {
        .ac-summary { grid-template-columns: 1fr; gap: 10px; }
        .ac-ops { justify-content: flex-end; }
    }

    /* ========= Tab 切换（总览 / 原神 / 崩铁 / 绝区零） ========= */
    .tabs-bar {
        display: flex; gap: 2px; margin-bottom: 18px;
        border-bottom: 1px solid var(--paimon-border);
    }
    .tab-btn {
        padding: 10px 18px; background: transparent; border: none;
        color: var(--text-muted); font-size: 14px; cursor: pointer;
        border-bottom: 2px solid transparent;
        transition: color .15s, border-color .15s;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active {
        color: var(--gold); border-bottom-color: var(--gold); font-weight: 500;
    }
    /* tab 里的小 logo 球（比 ac-icon 那个小一号） */
    .tab-logo {
        display: inline-flex; align-items: center; justify-content: center;
        width: 20px; height: 20px; border-radius: 50%; margin-right: 6px;
        font-size: 11px; font-weight: 700; color: #fff;
        vertical-align: -4px;
    }
    .tab-logo.gs  { background: linear-gradient(135deg, #d4af37, #8b7530); }
    .tab-logo.sr  { background: linear-gradient(135deg, #b084f0, #5a3a8c); }
    .tab-logo.zzz { background: linear-gradient(135deg, #f0d530, #a08010); color: #2a2000; }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }

    /* 单游戏 tab 内的"该游戏无账号"提示 */
    .tab-empty {"""
