"""水神 · 游戏面板 — 玩家视角紧凑布局

设计哲学：
玩家日常最关心的就 3 件事 —— 树脂满没 / 委托做完没 / 今天签了没。
战报、抽卡是**偶尔**才翻的低频信息，不该和日常信息挤一起。

布局：
- 顶部状态条：绑定总数 + [+添加] + 刷新
- 每个账号一张**紧凑卡片**：只显示关键状态（一眼能判断是否要操作）
  - 树脂进度条（颜色随满额程度变）
  - 今日委托 / 派遣 / 签到状态（状态 chip）
  - 右上角：签到按钮（最常用）+ 展开按钮
- 点击"▾ 详情"展开：战报 + 抽卡（原神独占）+ 高级操作
- 扫码登录：modal 弹窗，不常驻
"""
from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)


GAME_CSS = """
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
    .tab-empty {
        text-align: center; padding: 40px 20px; color: var(--text-muted);
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


GAME_BODY = """
    <div class="container">

        <div class="status-bar">
            <div class="status-title">
                <h1>🎮 水神 · 游戏</h1>
                <div class="sub" id="statusSub">加载中...</div>
            </div>
            <div class="status-actions">
                <button class="btn" onclick="openQrModal()">+ 添加账号</button>
                <button class="btn" onclick="gameRefreshAll()">刷新数据</button>
            </div>
        </div>

        <div id="wrapperEl"><div class="empty-bind">加载中...</div></div>
    </div>

    <!-- 扫码 modal -->
    <div class="qr-modal-backdrop" id="qrModal" onclick="if(event.target.id==='qrModal')closeQrModal()">
        <div class="qr-modal">
            <div class="qr-modal-head">
                <h3>扫码绑定米游社</h3>
                <button class="qr-close" onclick="closeQrModal()">&times;</button>
            </div>
            <div class="qr-box" id="qrBox">
                <button class="btn primary" onclick="startQrLogin()">生成二维码</button>
            </div>
            <div class="qr-hint">米游社 APP → 右上扫一扫 → 确认登录</div>
            <div class="qr-hint small">一次扫码绑该账号下原神 / 星铁 / 绝区零</div>
            <div class="qr-status" id="qrStatus"></div>
        </div>
    </div>

    <!-- 抽卡 URL 导入 modal -->
    <div class="qr-modal-backdrop" id="urlImportModal" onclick="if(event.target.id==='urlImportModal')closeUrlImportModal()">
        <div class="urlimport-modal">
            <div class="qr-modal-head">
                <h3 id="urlImportTitle">导入抽卡 URL</h3>
                <button class="qr-close" onclick="closeUrlImportModal()">&times;</button>
            </div>
            <div class="tutorial" id="urlImportTutorial"></div>
            <textarea id="urlImportInput" placeholder="粘贴含 authkey=... 的完整 URL"></textarea>
            <div class="actions">
                <button class="btn tiny" onclick="closeUrlImportModal()">取消</button>
                <button class="btn primary tiny" onclick="submitUrlImport()">导入</button>
            </div>
        </div>
    </div>
"""


GAME_SCRIPT = """
    <script>
    (function(){
        function esc(s){return s===null||s===undefined?'':String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}

        // marked.parse 渲染 + 外部链接（http/https）改 target=_blank rel=noopener
        // 站内相对链接保持当前页跳转
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
        function fmtRelative(ts){
            if(!ts||ts<=0)return '-';
            var sec = (Date.now()/1000) - ts;
            if(sec < 60) return Math.floor(sec)+'s 前';
            if(sec < 3600) return Math.floor(sec/60)+'min 前';
            if(sec < 86400) return Math.floor(sec/3600)+'h 前';
            return Math.floor(sec/86400)+'d 前';
        }
        function fmtFuture(ts){
            if(!ts||ts<=0)return '已满';
            var sec = ts - (Date.now()/1000);
            if(sec <= 0) return '已满';
            var h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60);
            if(h >= 24) return Math.floor(h/24)+'d'+(h%24)+'h';
            if(h === 0) return m+'min 后满';
            return h+'h'+String(m).padStart(2,'0')+'m 后满';
        }

        // logo = 官方主色渐变圆 + 游戏名核心字（原/穹/零）
        var GAME_META = {
            gs:  {name:'原神',   logo:{cls:'gs',  text:'原'}, stamina:'树脂',   daily:'委托', rogueLabel:null},
            sr:  {name:'崩铁',   logo:{cls:'sr',  text:'穹'}, stamina:'开拓力', daily:'实训', rogueLabel:'模拟宇宙'},
            zzz: {name:'绝区零', logo:{cls:'zzz', text:'零'}, stamina:'电量',   daily:'活跃', rogueLabel:'悬赏'},
        };
        function renderLogo(game){
            var m = GAME_META[game];
            if(!m) return '<span class="game-logo">?</span>';
            return '<span class="game-logo '+m.logo.cls+'">'+m.logo.text+'</span>';
        }
        var ABYSS_DEFS = {
            gs: [
                {type:'spiral',  name:'深境螺旋'},
                {type:'poetry',  name:'幻想真境剧诗'},
                {type:'stygian', name:'幽境危战'},
            ],
            sr: [
                {type:'forgotten_hall', name:'忘却之庭'},
                {type:'pure_fiction',   name:'虚构叙事'},
                {type:'apocalyptic',    name:'末日幻影'},
                {type:'peak',           name:'异相仲裁'},
            ],
            zzz: [
                {type:'shiyu', name:'式舆防卫战'},
                {type:'mem',   name:'危局强袭战'},
                // TODO 临界推演 endpoint 404，待抓包修复后启用
                // {type:'void',  name:'临界推演'},
            ],
        };
        var POOL_LABELS_BY_GAME = {
            'gs':  {'301':'角色','302':'武器','200':'常驻','500':'集录'},
            'sr':  {'11':'角色','12':'光锥','1':'常驻','2':'新手'},
            'zzz': {'2':'独家','3':'音擎','1':'常驻','5':'邦布'},
        };
        // 单独维护顺序：JS 对纯数字字符串 key 会按数值升序排，Object.keys 拿不到插入顺序
        // → 渲染必须用这个数组而不是 Object.keys(POOL_LABELS_BY_GAME[a.game])
        var POOL_ORDER_BY_GAME = {
            'gs':  ['301', '302', '200', '500'],
            'sr':  ['11', '12', '1', '2'],
            'zzz': ['2', '3', '1', '5'],
        };

        var _allAccs = [];
        var _currentPool = {};  // uid -> pool id
        var _currentTab = 'overview';   // 'overview' | 'gs' | 'sr' | 'zzz'
        var _filledTabs = {};           // key -> 已填充过，避免重复 fill 战报/抽卡
        var _TABS = [
            {key:'overview', label:'总览'},
            {key:'gs',  label:'原神'},
            {key:'sr',  label:'崩铁'},
            {key:'zzz', label:'绝区零'},
        ];

        // tab button 的 label 里内嵌游戏 logo
        function _tabLabel(t){
            if(t.key === 'overview') return t.label;
            return '<span class="tab-logo '+t.key+'">'+GAME_META[t.key].logo.text+'</span>' + t.label;
        }

        function keyOf(a){ return a.game+'::'+a.uid; }

        window.loadOverview = async function(){
            var wrapper = document.getElementById('wrapperEl');
            try{
                var r = await fetch('/api/game/overview');
                var d = await r.json();
                _allAccs = d.accounts || [];
            }catch(e){
                wrapper.innerHTML = '<div class="empty-bind"><h2>加载失败</h2><p>'+esc(String(e))+'</p></div>';
                return;
            }
            _renderStatusSub();
            if(_allAccs.length === 0){
                wrapper.innerHTML = '<div class="empty-bind">'
                    +'<h2>还没绑定任何账号</h2>'
                    +'<p>扫码一次即可绑定该米游社账号下的原神 / 星铁 / 绝区零</p>'
                    +'<button class="btn primary" onclick="openQrModal()">+ 添加账号</button>'
                    +'</div>';
                return;
            }
            // 先搭 tab 骨架
            wrapper.innerHTML =
                '<div class="tabs-bar">' + _TABS.map(function(t){
                    return '<button class="tab-btn'+(t.key===_currentTab?' active':'')
                        +'" data-tab-key="'+t.key+'" onclick="switchGameTab(\\''+t.key+'\\')">'+_tabLabel(t)+'</button>';
                }).join('') + '</div>'
                + _TABS.map(function(t){
                    return '<div class="tab-pane'+(t.key===_currentTab?' active':'')+'" id="tab-'+t.key+'"></div>';
                }).join('');
            _filledTabs = {};
            _fillTab(_currentTab);
        };

        window.switchGameTab = function(key){
            _currentTab = key;
            document.querySelectorAll('.tab-btn').forEach(function(b){
                b.classList.toggle('active', b.getAttribute('data-tab-key') === key);
            });
            document.querySelectorAll('.tab-pane').forEach(function(p){ p.classList.remove('active'); });
            var pane = document.getElementById('tab-'+key);
            if(pane){ pane.classList.add('active'); }
            _fillTab(key);
            // 切 tab 时同步订阅按钮状态（新渲染的卡可能 hydrate 还没跑过）
            if(typeof _hydrateSubsBtns === 'function') _hydrateSubsBtns();
        };

        function _fillTab(key){
            var pane = document.getElementById('tab-'+key);
            if(!pane) return;
            if(_filledTabs[key]) return;
            _filledTabs[key] = true;
            if(key === 'overview'){
                pane.innerHTML = _allAccs.map(_renderSummaryCard).join('');
            } else {
                // 特定游戏 tab：过滤该 game 账号，完整卡片
                var accs = _allAccs.filter(function(a){return a.game === key;});
                if(accs.length === 0){
                    pane.innerHTML = '<div class="tab-empty">未绑定该游戏账号。'
                        +'<br><br><button class="btn primary" onclick="openQrModal()">+ 扫码绑定</button></div>';
                    return;
                }
                pane.innerHTML = accs.map(_renderFullCard).join('');
                // 异步填每个账号的战报/抽卡（模拟展开效果）
                accs.forEach(function(a){ _fillAccountDetail(a); });
            }
            // 订阅按钮 hydrate（loadGameSubs 拉完后会 hydrate 占位的 ac-subs-btn）
            if(typeof _hydrateSubsBtns === 'function') _hydrateSubsBtns();
        }

        function _renderStatusSub(){
            var el = document.getElementById('statusSub');
            if(_allAccs.length === 0){
                el.textContent = '未绑定任何账号';
                return;
            }
            var bymys = {};
            _allAccs.forEach(function(a){ bymys[a.mys_id] = (bymys[a.mys_id]||0)+1; });
            el.textContent = '已绑 ' + _allAccs.length + ' 个游戏（' + Object.keys(bymys).length + ' 个米游社账号）';
        }

        function _renderSummaryCard(a){
            // 总览 tab 用：紧凑一行，点"看详细 →"跳对应游戏 tab
            var k = keyOf(a);
            var meta = GAME_META[a.game] || {name:a.game, icon:'🎮', stamina:'体力', daily:'任务'};
            var n = a.daily_note;
            var summary = _renderSummary(a, meta, n);
            return '<div class="account-card">'
                + '<div class="ac-summary">'
                + '  <div class="ac-identity">'
                + '    '+renderLogo(a.game)
                + '    <div class="ac-names">'
                + '      <div class="ac-game-name">'+esc(meta.name)
                +        (a.note ? ' <span class="ac-note">· '+esc(a.note)+'</span>' : '')
                + '      </div>'
                + '      <div class="ac-uid">'+esc(a.uid)+'</div>'
                + '    </div>'
                + '  </div>'
                + '  '+summary
                + '  <div class="ac-ops">'
                + '    <button class="btn tiny primary" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameSignOne(this)">签到</button>'
                + '    <button class="ac-toggle" onclick="switchGameTab(\\''+esc(a.game)+'\\')">看详细 →</button>'
                + '  </div>'
                + '</div>'
                + '<div class="ac-news-line" data-news-line-for="'+esc(k)+'" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'">'
                +   '<span class="news-toggle"><span class="dot"></span>加载中</span>'
                +   '<span class="news-icon">📰</span>'
                +   '<span class="news-text"><span class="meta">资讯订阅</span></span>'
                +   '<button class="news-run" disabled>采集</button>'
                + '</div>'
                + '<div class="ac-news-pushes" data-pushes-for="'+esc(k)+'" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'"></div>'
                + '</div>';
        }

        // 总览只读汇总（_renderSummaryCard 用），游戏 tab 可展开（_renderFullCard 用，data-detailed="1"）
        function _renderFullCard(a){
            // 游戏 tab 用：顶部账号摘要 + 展开的详情区（便笺派遣 / 战报 / 抽卡 / 角色占位）
            var k = keyOf(a);
            var meta = GAME_META[a.game] || {name:a.game, icon:'🎮', stamina:'体力', daily:'任务'};
            var n = a.daily_note;
            var summary = _renderSummary(a, meta, n);
            return '<div class="account-card" id="ac-'+esc(k)+'">'
                + '<div class="ac-summary">'
                + '  <div class="ac-identity">'
                + '    '+renderLogo(a.game)
                + '    <div class="ac-names">'
                + '      <div class="ac-game-name">'+esc(meta.name)
                +        (a.note ? ' <span class="ac-note">· '+esc(a.note)+'</span>' : '')
                + '      </div>'
                + '      <div class="ac-uid">'+esc(a.uid)+'</div>'
                + '    </div>'
                + '  </div>'
                + '  '+summary
                + '  <div class="ac-ops">'
                + '    <button class="btn tiny primary" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameSignOne(this)">签到</button>'
                + '  </div>'
                + '</div>'
                + '<div class="ac-news-line" data-news-line-for="'+esc(k)+'" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'">'
                +   '<span class="news-toggle"><span class="dot"></span>加载中</span>'
                +   '<span class="news-icon">📰</span>'
                +   '<span class="news-text"><span class="meta">资讯订阅</span></span>'
                +   '<button class="news-run" disabled>采集</button>'
                + '</div>'
                + '<div class="ac-news-pushes" data-pushes-for="'+esc(k)+'" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" data-detailed="1"></div>'
                + '<div class="ac-detail open" id="detail-'+esc(k)+'">加载中...</div>'
                + '</div>';
        }

        function _renderSummary(a, meta, n){
            if(!n || !n.max_resin){
                return '<div class="ac-status">'
                    + '<div style="color:var(--text-muted);font-size:12px;">暂无便笺数据（上次签到 '+(a.last_sign_at>0?fmtRelative(a.last_sign_at):'-')+'）</div>'
                    + '</div>';
            }
            var pct = Math.min(100, n.current_resin/n.max_resin*100);
            var fillCls = pct >= 100 ? 'full' : (pct >= 85 ? 'warn' : '');
            var whenCls = pct >= 85 ? ' urgent' : '';
            var whenText = fmtFuture(n.resin_full_ts);

            // chips: 委托 / 派遣 / 签到
            var chips = [];
            // 每日任务
            var dailyDone = n.finished_tasks >= n.total_tasks;
            var dailyReward = a.game === 'gs' ? n.daily_reward : true;  // 只有原神有"奖励未领"语义
            var dailyCls = 'ok';
            var dailyText = meta.daily+' '+n.finished_tasks+'/'+n.total_tasks;
            if(!dailyDone){ dailyCls = 'bad'; dailyText += ' ✗'; }
            else if(a.game === 'gs' && !dailyReward){ dailyCls = 'warn'; dailyText += ' 奖励未领'; }
            else { dailyText += ' ✓'; }
            chips.push('<span class="chip '+dailyCls+'">'+esc(dailyText)+'</span>');

            // 派遣（原神/崩铁有）
            if(n.max_expedition > 0){
                var expReady = (n.expeditions||[]).filter(function(e){return parseInt(e.remained_time||0)<=0;}).length;
                var expTotal = n.max_expedition;
                var expCls = (a.game === 'gs' && expReady === expTotal) ? 'ok'
                           : (expReady > 0 ? 'warn' : '');
                chips.push('<span class="chip '+expCls+'">派遣 '+n.current_expedition+'/'+expTotal
                    + (expReady>0?' · '+expReady+'就绪':'')+'</span>');
            }

            // 原神参量
            if(a.game === 'gs' && n.transformer_ready){
                chips.push('<span class="chip ok">参量就绪</span>');
            }

            // 崩铁模拟宇宙周 / 绝区零悬赏
            if(a.game === 'sr' && n.remain_discount > 0){
                chips.push('<span class="chip">模拟宇宙 '+n.remain_discount+'</span>');
            }
            if(a.game === 'zzz' && n.remain_discount > 0){
                chips.push('<span class="chip">悬赏 '+n.remain_discount+'</span>');
            }

            // 签到状态（按 last_sign_at 是不是今天判断）
            var now = Date.now() / 1000;
            var signedToday = a.last_sign_at > 0 && (now - a.last_sign_at) < 20*3600;
            chips.push('<span class="chip '+(signedToday?'ok':'bad')+'">'+(signedToday?'今日已签':'未签到')+'</span>');

            return '<div class="ac-status">'
                + '<div class="ac-resin-line">'
                + '  <span class="ac-resin-label">'+esc(meta.stamina)+'</span>'
                + '  <div class="ac-resin-bar"><div class="ac-resin-fill '+fillCls+'" style="width:'+pct.toFixed(1)+'%"></div></div>'
                + '  <span class="ac-resin-num">'+n.current_resin+'/'+n.max_resin+'</span>'
                + '  <span class="ac-resin-when'+whenCls+'">'+esc(whenText)+'</span>'
                + '</div>'
                + '<div class="ac-chips">'+chips.join('')+'</div>'
                + '</div>';
        }

        async function _fillAccountDetail(a){
            var k = keyOf(a);
            var el = document.getElementById('detail-'+k);
            if(!el) return;

            var charsTitle = (a.game==='gs') ? '角色 · 养成'
                : (a.game==='sr' ? '角色 · 星魂' : '代理人 · 影画');

            var html = '<div class="ac-detail-grid">'
                +   '<div class="ac-panel h-fixed gacha-pane">'
                +     '<div class="panel-title">抽卡记录</div>'
                +     '<div class="panel-body" id="gacha-'+esc(k)+'">加载中...</div>'
                +   '</div>'
                +   '<div class="ac-panel h-fixed abyss-pane">'
                +     '<div class="panel-title">战报 · 最近 <span class="panel-hint">点击行展开看阵容</span></div>'
                +     '<div class="panel-body abyss-rows" id="abyss-'+esc(k)+'">加载中...</div>'
                +   '</div>'
                +   '<div class="ac-panel h-fixed-tall chars-pane">'
                +     '<div class="panel-title">'+esc(charsTitle)+'</div>'
                +     '<div class="panel-body" id="chars-'+esc(k)+'">加载中...</div>'
                +   '</div>'
                + '</div>'
                + '<div class="detail-ops" style="margin-top:14px">'
                +   '<button class="btn tiny" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameCollectOne(this)">刷新此账号数据</button>'
                +   '<button class="btn tiny danger" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameUnbind(this)">解绑</button>'
                + '</div>';

            el.innerHTML = html;

            // 异步填三块内容（状态条已在初始 render 直出）
            _fillAbyss(a, k);
            _fillGacha(a, k);
            _fillCharacters(a, k);
        }

        var _charFilter = {};   // uid -> 'all'|'r5'|'r4'
        var _charsCache = {};   // key='gs::uid' -> {chars, byId}（abyss + chars panel 共用）

        async function _ensureChars(a, k){
            if(_charsCache[k]) return _charsCache[k];
            try{
                var r = await fetch('/api/game/characters?game='+a.game+'&uid='+encodeURIComponent(a.uid));
                var d = await r.json();
                var chars = d.characters || [];
                var byId = {};
                chars.forEach(function(c){ byId[String(c.avatar_id)] = c; });
                _charsCache[k] = {chars: chars, byId: byId};
            }catch(_){
                _charsCache[k] = {chars: [], byId: {}};
            }
            return _charsCache[k];
        }

        async function _fillCharacters(a, k){
            var slot = document.getElementById('chars-'+k);
            if(!slot) return;
            var cache = await _ensureChars(a, k);
            var chars = cache.chars;
            if(chars.length === 0){
                slot.innerHTML = '<div class="coming-soon">'
                    + '  <div class="cs-title">暂无角色数据</div>'
                    + '  点底部"刷新此账号数据"抓取'
                    + '</div>';
                return;
            }
            var filter = _charFilter[a.uid] || 'all';
            var visible = chars.filter(function(c){
                if(filter === 'r5') return c.rarity >= 5;
                if(filter === 'r4') return c.rarity === 4;
                return true;
            });
            var count5 = chars.filter(function(c){return c.rarity >= 5;}).length;
            var count4 = chars.filter(function(c){return c.rarity === 4;}).length;
            var maxLv = chars.filter(function(c){return c.level >= 90;}).length;
            var filters = [
                {k:'all', label:'全部 '+chars.length},
                {k:'r5',  label:'5 星 '+count5},
                {k:'r4',  label:'4 星 '+count4},
            ];
            var filterHtml = '<div class="char-filter-bar">' + filters.map(function(f){
                return '<span class="char-filter '+(filter===f.k?'active':'')
                    + '" onclick="setCharFilter(\\''+esc(a.uid)+'\\',\\''+f.k+'\\')">'+esc(f.label)+'</span>';
            }).join('') + '</div>';

            var statHtml = '<div class="char-stat-line">'
                + '<span class="num">'+chars.length+'</span> 角色 · '
                + '5★ <span class="num">'+count5+'</span> · '
                + '满级 <span class="num">'+maxLv+'</span>'
                + '</div>';

            // 单列 list：每行 icon + 名字+lv + 命+精 + 武器名
            var rowsHtml = '<div class="char-list">' + visible.map(function(c){
                var iconStyle = c.icon_url ? 'background-image:url('+esc(c.icon_url)+')' : '';
                var ca = (c.constellation||0) + '+' + (c.weapon && c.weapon.rarity>=5 ? (c.weapon.affix||0) : 0);
                var wpName = (c.weapon && c.weapon.name) ? c.weapon.name : '';
                var wpLv = (c.weapon && c.weapon.level) ? (' L'+c.weapon.level) : '';
                var wpRarity = (c.weapon && c.weapon.rarity) || 0;
                var wpCls = wpRarity >= 5 ? 'wp5' : (wpRarity === 4 ? 'wp4' : '');
                return '<div class="char-row r'+c.rarity+'">'
                    + '<div class="char-icon-sm" style="'+iconStyle+'"></div>'
                    + '<div class="char-info">'
                    +   '<div class="char-line1"><span class="char-name">'+esc(c.name)+'</span>'
                    +   '<span class="char-lv">Lv.'+c.level+'</span>'
                    +   '<span class="char-ca">'+ca+'</span></div>'
                    +   '<div class="char-line2 '+wpCls+'">'+(wpName?esc(wpName)+esc(wpLv):'<span class="muted">无武器</span>')+'</div>'
                    + '</div>'
                    + '</div>';
            }).join('') + '</div>';

            slot.innerHTML = statHtml + filterHtml + rowsHtml;
        }

        window.setCharFilter = function(uid, key){
            _charFilter[uid] = key;
            var a = _allAccs.find(function(x){return x.uid === uid;});
            if(a) _fillCharacters(a, keyOf(a));
        };

        async function _fillAbyss(a, k){
            var defs = ABYSS_DEFS[a.game] || [];
            var slot = document.getElementById('abyss-'+k);
            if(!slot) return;
            if(defs.length === 0){ slot.innerHTML = '<div class="abyss-empty">—</div>'; return; }
            // 同时拉 abyss_latest（每副本 1 个）+ characters（队伍补 name/cons/weapon）
            var charsP = _ensureChars(a, k);
            var resultsP = Promise.all(defs.map(function(def){
                return fetch('/api/game/abyss_latest?game='+a.game+'&uid='+encodeURIComponent(a.uid)+'&type='+def.type)
                    .then(function(r){return r.json();})
                    .catch(function(){return {abyss:null};});
            }));
            var results = await resultsP;
            var charsCache = await charsP;
            var charsById = charsCache.byId;
            // 主力角色聚合：跨副本统计 avatar 出现次数 → top chips
            var heroCount = {};
            var rowTeams = [];   // 缓存每行的 teams 避免重复 extract
            results.forEach(function(res, i){
                var ab = res.abyss;
                if(!ab){ rowTeams.push([]); return; }
                var ts = _extractTeams(a.game, defs[i].type, ab.raw, charsById);
                rowTeams.push(ts);
                ts.forEach(function(t){
                    (t.avatars||[]).forEach(function(av){
                        if(av.name) heroCount[av.name] = (heroCount[av.name]||0) + 1;
                    });
                });
            });
            var topHeroes = Object.keys(heroCount).map(function(n){return {n:n, c:heroCount[n]};})
                .sort(function(a,b){return b.c - a.c;}).slice(0, 6);
            var topHeroesHtml = '';
            if(topHeroes.length){
                topHeroesHtml = '<div class="top-heroes-label">主力出场（跨副本队伍）</div>'
                    + '<div class="top-heroes">'
                    + topHeroes.map(function(h){
                        return '<span class="hero-chip">'+esc(h.n)+'<span class="cnt">×'+h.c+'</span></span>';
                    }).join('')
                    + '</div>';
            }

            var rows = defs.map(function(def, i){
                var ab = results[i].abyss;
                if(!ab){
                    return '<div class="abyss-row" style="cursor:default">'
                        + '<span class="abyss-name">'+esc(def.name)+'</span>'
                        + '<span class="abyss-floor">-</span>'
                        + '<span class="abyss-star">-</span>'
                        + '<span class="abyss-meta">未挑战</span>'
                        + '</div>';
                }
                // 组装展示字段
                var floorVal, starVal, metaVal;
                if(a.game === 'zzz' && def.type === 'shiyu'){
                    floorVal = '评级 ' + (ab.max_floor || '-');
                    starVal = ab.total_star + '分';
                    metaVal = ab.total_battle > 0 ? (ab.total_battle+'s') : fmtRelative(ab.scan_ts);
                }else if(def.type === 'stygian'){
                    floorVal = '难度 ' + (ab.max_floor || '-');
                    starVal = ab.total_star + 's';
                    metaVal = fmtRelative(ab.scan_ts);
                }else if(def.type === 'poetry'){
                    floorVal = '第 ' + (ab.max_floor || '-') + ' 轮';
                    starVal = ab.total_star + '★';
                    metaVal = fmtRelative(ab.scan_ts);
                }else{
                    // spiral / forgotten_hall / pure_fiction / apocalyptic / mem
                    floorVal = String(ab.max_floor || '-');
                    starVal = ab.total_star + '★';
                    if(ab.total_battle > 0){
                        metaVal = ab.total_win + '/' + ab.total_battle;
                    }else{
                        metaVal = fmtRelative(ab.scan_ts);
                    }
                }
                var teams = rowTeams[i] || [];
                var hasTeams = teams.length > 0;
                var indicator = hasTeams ? '<span class="abyss-toggle">▴</span>' : '';
                var rowHtml = '<div class="abyss-row" '+(hasTeams?'onclick="toggleAbyssTeams(\\''+esc(k)+'\\','+i+')"':'style="cursor:default"')+'>'
                    + '<span class="abyss-name">'+esc(def.name)+indicator+'</span>'
                    + '<span class="abyss-floor">'+esc(floorVal)+'</span>'
                    + '<span class="abyss-star">'+esc(String(starVal))+'</span>'
                    + '<span class="abyss-meta">'+esc(String(metaVal))+'</span>'
                    + '</div>';
                var teamsHtml = hasTeams
                    ? '<div class="abyss-teams" id="abyss-teams-'+esc(k)+'-'+i+'">'+_renderTeams(teams)+'</div>'
                    : '';
                return rowHtml + teamsHtml;
            });
            slot.innerHTML = topHeroesHtml + rows.join('');
        }

        // 从 abyss.raw 解析每场战斗的队伍。
        // spiral / forgotten_hall 等接口的 avatar 只有 id/level/rarity 没 name/cons/weapon
        // → 必须用 charsById（mihoyo_character 表）反查
        function _extractTeams(game, abyssType, raw, charsById){
            if(!raw || typeof raw !== 'object') return [];
            charsById = charsById || {};
            var norm = function(av){ return _normAvatar(av, charsById); };
            var teams = [];
            try{
                if(game === 'gs' && abyssType === 'spiral'){
                    (raw.floors || []).forEach(function(floor){
                        (floor.levels || []).forEach(function(level){
                            (level.battles || []).forEach(function(battle){
                                var half = battle.index === 1 ? '上' : (battle.index === 2 ? '下' : '#'+battle.index);
                                teams.push({
                                    label: (floor.index||'?')+'-'+(level.index||'?')+' '+half,
                                    stars: level.star || 0,
                                    max_star: level.max_star || 0,
                                    avatars: (battle.avatars || []).map(norm),
                                });
                            });
                        });
                    });
                }else if(game === 'gs' && abyssType === 'poetry'){
                    // 幻想真境剧诗：detail.rounds_data[]（米游社字段名是 rounds_data 不是 rounds）
                    var detail = raw.detail || raw;
                    (detail.rounds_data || raw.rounds || []).forEach(function(r, i){
                        var avs = r.avatars || r.role || [];
                        if(avs.length){
                            teams.push({
                                label: '第 '+(r.round_id || i+1)+' 轮' + (r.is_get_medal ? ' ★' : ''),
                                stars: r.is_get_medal ? 1 : 0,
                                avatars: avs.map(norm),
                            });
                        }
                    });
                }else if(game === 'gs' && abyssType === 'stygian'){
                    var chs = (raw.single && raw.single.challenge) || raw.challenge || [];
                    chs.forEach(function(c, i){
                        var avs = c.teams || c.avatars || [];
                        if(avs.length){
                            teams.push({
                                label: c.name || ('挑战 '+(i+1)),
                                stars: c.difficulty || 0,
                                avatars: avs.map(norm),
                            });
                        }
                    });
                }else if(game === 'sr' && abyssType === 'peak'){
                    // 异相仲裁：challenge_peak_records[].mob_records[].avatars + boss_record.avatars
                    (raw.challenge_peak_records || []).forEach(function(rec, ri){
                        var groupName = (rec.group && rec.group.name) || ('挑战 '+(ri+1));
                        // 普通怪战
                        (rec.mob_records || []).forEach(function(mob, mi){
                            var avs = mob.avatars || [];
                            if(avs.length){
                                teams.push({
                                    label: groupName + ' 怪 #' + (mi+1),
                                    stars: mob.star_num || 0,
                                    avatars: avs.map(norm),
                                });
                            }
                        });
                        // BOSS 战
                        var br = rec.boss_record;
                        if(br && (br.avatars || []).length){
                            teams.push({
                                label: groupName + ' BOSS',
                                stars: br.star_num || 0,
                                avatars: br.avatars.map(norm),
                            });
                        }
                    });
                }else if(game === 'sr'){
                    (raw.all_floor_detail || []).forEach(function(f){
                        var nodeKeys = Object.keys(f).filter(function(k){
                            return k.indexOf('node_') === 0 && !isNaN(parseInt(k.slice(5), 10));
                        }).sort(function(a,b){
                            return parseInt(a.replace('node_',''),10) - parseInt(b.replace('node_',''),10);
                        });
                        nodeKeys.forEach(function(nk){
                            var node = f[nk];
                            if(node && (node.avatars || []).length){
                                teams.push({
                                    label: (f.name||'层') + ' ' + nk.replace('node_','节'),
                                    stars: f.star_num || 0,
                                    avatars: node.avatars.map(norm),
                                });
                            }
                        });
                    });
                }else if(game === 'zzz' && abyssType === 'shiyu'){
                    // ZZZ 式舆防卫战：hadal_info_v2.{fitfh,fourth}_layer_detail.layer_challenge_info_list[]
                    // 每层 N 个挑战，每个 challenge 含 avatar_list
                    var v2 = raw.hadal_info_v2 || raw;
                    [['fitfh_layer_detail','第 5 层'], ['fourth_layer_detail','第 4 层']].forEach(function(pair){
                        var layer = v2[pair[0]] || {};
                        var infos = layer.layer_challenge_info_list || [];
                        infos.forEach(function(c, idx){
                            var avs = c.avatar_list || c.avatars || [];
                            if(avs.length){
                                teams.push({
                                    label: pair[1] + ' #' + (c.layer_id || idx+1),
                                    stars: c.rating || c.score || 0,
                                    avatars: avs.map(norm),
                                });
                            }
                        });
                    });
                }else if(game === 'zzz'){
                    // 危局/其他：list/floor_detail 兜底
                    var list = raw.list || raw.all_floor_detail || raw.floor_detail
                        || (raw.memory_list) || [];
                    list.forEach(function(it, idx){
                        var avs = it.avatar_list || it.avatars || [];
                        if(avs.length){
                            teams.push({
                                label: it.name || it.level_name || it.layer_name || ('节 '+(idx+1)),
                                stars: it.score || it.star || it.layer_index || 0,
                                avatars: avs.map(norm),
                            });
                        }
                    });
                }
            }catch(e){
                console.error('[战报] 队伍解析失败', game, abyssType, e);
            }
            return teams;
        }

        // raw avatar → 统一格式，name/cons/weapon 缺时从 mihoyo_character 表（charsById）补
        function _normAvatar(av, charsById){
            charsById = charsById || {};
            var id = String(av.id || av.avatar_id || '');
            var c = charsById[id] || {};
            // ZZZ rarity 是字符串 "S"/"A"/"B"，转数字便于统一渲染颜色
            var rawRarity = av.rarity != null ? av.rarity : (av.rank != null ? av.rank : c.rarity);
            var rarity;
            if(typeof rawRarity === 'string'){
                var m = {'S':5, 'A':4, 'B':3};
                rarity = m[rawRarity] || 4;
            }else{
                rarity = rawRarity || 4;
            }
            // ZZZ avatar.rank 在 raw 里是「影画/命之座」（不是 rarity），优先信 charsById.constellation
            var cons = (c.constellation != null ? c.constellation : (av.rank != null && typeof av.rank === 'number' ? av.rank : 0));
            return {
                id: id,
                name: av.name || av.full_name || c.name || '',
                level: av.level || av.cur_level || c.level || 0,
                rarity: rarity,
                cons: cons,
                weapon: c.weapon || {},
            };
        }

        // 命座+精炼格式：0+0 / 0+1 / 2+1（精炼仅 5 星武器算）
        function _consAffix(av){
            var cons = av.cons || 0;
            var affix = 0;
            if(av.weapon && av.weapon.rarity >= 5){
                affix = av.weapon.affix || 0;
            }
            return cons + '+' + affix;
        }

        function _renderTeams(teams){
            return teams.map(function(t){
                var avHtml = (t.avatars || []).map(function(av){
                    var rcls = av.rarity >= 5 ? 'r5' : (av.rarity === 4 ? 'r4' : '');
                    var ca = _consAffix(av);
                    var nameTxt = av.name || ('id:'+av.id);
                    var weaponInfo = (av.weapon && av.weapon.name) ? (av.weapon.name + (av.weapon.affix?(' 精'+av.weapon.affix):'')) : '';
                    var tip = nameTxt + ' Lv'+(av.level||'?') + (weaponInfo?(' · '+weaponInfo):'');
                    return '<span class="abyss-team-avatar '+rcls+'" title="'+esc(tip)+'">'
                        + esc(nameTxt)
                        + ' <span class="ca">'+ca+'</span>'
                        + '</span>';
                }).join('');
                var starInfo = t.stars > 0
                    ? ' <span style="color:var(--gold);font-family:monospace">'+t.stars+(t.max_star?('/'+t.max_star):'')+'★</span>'
                    : '';
                return '<div class="abyss-team">'
                    + '<span class="abyss-team-label">'+esc(t.label)+starInfo+'</span>'
                    + avHtml
                    + '</div>';
            }).join('');
        }

        window.toggleAbyssTeams = function(k, i){
            var el = document.getElementById('abyss-teams-'+k+'-'+i);
            if(!el) return;
            el.classList.toggle('closed');
            var row = el.previousElementSibling;
            var toggle = row && row.querySelector('.abyss-toggle');
            if(toggle) toggle.textContent = el.classList.contains('closed') ? '▾' : '▴';
        };

        async function _fillGacha(a, k){
            var slot = document.getElementById('gacha-'+k);
            if(!slot) return;
            var labels = POOL_LABELS_BY_GAME[a.game] || {};
            var poolKeys = POOL_ORDER_BY_GAME[a.game] || [];
            if(poolKeys.length === 0){
                slot.innerHTML = '<div class="gacha-empty">暂不支持此游戏</div>';
                return;
            }
            var pool = _currentPool[k];
            if(!pool || !labels[pool]) pool = poolKeys[0];
            _currentPool[k] = pool;

            var poolsHtml = '<div class="gacha-head">'
                + poolKeys.map(function(p){
                    return '<span class="gpool '+(p===pool?'active':'')+'" onclick="gameSelectPool(\\''+esc(k)+'\\',\\''+p+'\\')">'+labels[p]+'</span>';
                }).join('') + '</div>';

            var r = await fetch('/api/game/gacha/stats?game='+a.game+'&uid='+encodeURIComponent(a.uid)+'&gacha_type='+pool);
            var d = await r.json();
            var s = d.stats || {total:0};
            var syncBtn = _gachaSyncBtn(a);
            if(!s.total){
                var emptyHint = a.game === 'sr'
                    ? '暂无数据，点右下角"URL 导入"（米哈游限制 SR 不能自动同步）'
                    : '暂无数据，点右下角"同步抽卡"';
                slot.innerHTML = poolsHtml
                    + '<div class="gacha-empty">'+emptyHint+'</div>'
                    + syncBtn;
                _resumeGachaSyncIfRunning(a, slot);
                return;
            }
            var hardPity = s.hard_pity || 90;
            // 软保底 = 硬保底 × 0.8（GS 角色 73 / 武器 63；近似）
            var softThreshold = Math.floor(hardPity * 0.8);
            var pityCls = s.pity_5 >= hardPity - 10 ? 'warn' : (s.pity_5 >= softThreshold ? 'soft' : '');
            var topName = (a.game === 'zzz') ? 'S 级' : '5 星';
            var fives = (s.fives||[]).slice(0, 30);
            var fivesHtml = fives.length === 0
                ? '<div class="gacha-empty">此池暂无 '+topName+'</div>'
                : fives.map(function(f){
                    var pull = f.pull_count || 0;
                    var pullCls = pull <= 30 ? 'lucky' : (pull >= softThreshold ? 'heavy' : '');
                    var upHtml;
                    if(f.is_up === true){
                        upHtml = '<span class="gfive-up on" title="UP 出货">UP</span>';
                    }else if(f.is_up === false){
                        upHtml = '<span class="gfive-up off" title="出了常驻 = 歪了">歪</span>';
                    }else{
                        upHtml = '<span class="gfive-up none" title="此池无 UP 概念">—</span>';
                    }
                    return '<div class="gfive">'
                        + '<span class="gfive-badge">★</span>'
                        + '<span class="gfive-name">'+esc(f.name)+'</span>'
                        + '<span class="gfive-pull '+pullCls+'">'+pull+'抽</span>'
                        + upHtml
                        + '<span class="gfive-time">'+esc((f.time||'').slice(5,16))+'</span>'
                        + '</div>';
                }).join('');
            // 最欧 / 最歪 caption
            var allFives = s.fives || [];
            var luckRow = '';
            if(allFives.length){
                var pulls = allFives.map(function(f){return f.pull_count||0;}).filter(function(x){return x>0;});
                if(pulls.length){
                    var minP = Math.min.apply(null, pulls);
                    var maxP = Math.max.apply(null, pulls);
                    var luckiest = allFives.find(function(f){return f.pull_count===minP;});
                    var heaviest = allFives.find(function(f){return f.pull_count===maxP;});
                    luckRow = '<div class="gacha-luck-row">'
                        + '<span class="luck-item lucky">最欧 <span class="v">'+minP+'抽</span> '+esc(luckiest?luckiest.name:'')+'</span>'
                        + '<span class="luck-item heavy">最歪 <span class="v">'+maxP+'抽</span> '+esc(heaviest?heaviest.name:'')+'</span>'
                        + '</div>';
                }
            }
            slot.innerHTML = poolsHtml
                + '<div class="gacha-summary">总抽 <span class="pity">'+s.total
                + '</span><span class="sep">·</span>'+topName+'保底 <span class="pity '+pityCls+'">'+s.pity_5+'/'+hardPity
                + '</span><span class="sep">·</span>已出 '+topName+' <span class="pity">'+s.count_5
                + '</span><span class="sep">·</span>平均 <span class="pity">'+s.avg_pity_5+'</span></div>'
                + luckRow
                + '<div class="gacha-five-list">'+fivesHtml+'</div>'
                + syncBtn;
            _resumeGachaSyncIfRunning(a, slot);
        }

        async function _resumeGachaSyncIfRunning(a, slot){
            try{
                var sr = await fetch('/api/game/gacha/sync/status?game='+a.game+'&uid='+encodeURIComponent(a.uid));
                var sd = await sr.json();
                if(sd.state === 'running'){
                    var btn = slot.querySelector('button[onclick*="gameSyncGacha"]');
                    _pollGachaSync(a.game, a.uid, btn);
                }
            }catch(_){}
        }

        function _gachaSyncBtn(a, label){
            label = label || '同步抽卡';
            // SR 米哈游限制 stoken→authkey，必须走 URL 导入；GS/ZZZ 自动同步即可
            var btns = a.game === 'sr'
                ? '<button class="btn primary tiny" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameImportGachaUrl(this.dataset.game, this.dataset.uid)">URL 导入</button>'
                : '<button class="btn primary tiny" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameSyncGacha(this)">'+esc(label)+'</button>';
            return '<div class="gacha-sync-row">'
                + '<span class="gacha-sync-status" id="gsync-status-'+esc(keyOf(a))+'"></span>'
                + btns
                + '</div>';
        }

        // ============ 操作 ============
        window.gameSignOne = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            btn.disabled = true; var old = btn.textContent; btn.textContent = '...';
            try{
                var r = await fetch('/api/game/sign', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game, uid}),
                });
                var d = await r.json();
                btn.textContent = d.ok ? '✓' : '✗';
                if(!d.ok && d.msg) alert('签到失败: '+d.msg);
                setTimeout(function(){ btn.textContent = old; btn.disabled = false; loadOverview(); }, 1200);
            }catch(e){
                btn.textContent='✗'; setTimeout(function(){btn.textContent=old;btn.disabled=false;},2000);
            }
        };

        // 「刷新此账号数据」background + 轮询：完成后自动重渲该账号详情，无需手动刷新页面
        var _collectPollTimers = {};   // key='game::uid' -> interval id

        window.gameCollectOne = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            var k = game+'::'+uid;
            console.log('[水神·采集] 触发', game, uid);
            btn.disabled = true; var old = btn.textContent; btn.textContent = '启动...';
            try{
                var r = await fetch('/api/game/collect_one', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game, uid}),
                });
                var d = await r.json();
                if(!d.ok){
                    alert('采集启动失败: '+(d.msg||''));
                    btn.textContent = old; btn.disabled = false;
                    return;
                }
                btn.textContent = '采集中...';
                if(_collectPollTimers[k]){ clearInterval(_collectPollTimers[k]); }
                var poll = async function(){
                    try{
                        var sr = await fetch('/api/game/collect_one/status?game='+game+'&uid='+encodeURIComponent(uid));
                        var sd = await sr.json();
                        if(sd.state === 'running'){
                            return;   // 等下次 tick
                        }
                        clearInterval(_collectPollTimers[k]); delete _collectPollTimers[k];
                        if(sd.state === 'done'){
                            console.log('[水神·采集] DONE', sd.counts);
                            btn.textContent = '✓ 已更新';
                            // 数据已落库 → 清缓存 + 重渲该账号详情区（无需手动刷新）
                            delete _charsCache[k];
                            var a = _allAccs.find(function(x){return x.uid === uid && x.game === game;});
                            if(a){
                                _fillAbyss(a, k);
                                _fillCharacters(a, k);
                                // 摘要也重新拉一次（树脂/委托数据更新）
                                if(typeof loadOverview === 'function') loadOverview();
                            }
                        }else if(sd.state === 'failed'){
                            btn.textContent = '✗ 失败';
                            alert('采集失败: '+(sd.error||''));
                        }
                        setTimeout(function(){btn.textContent=old;btn.disabled=false;}, 3000);
                    }catch(e){
                        clearInterval(_collectPollTimers[k]); delete _collectPollTimers[k];
                        console.error('[水神·采集] poll 异常', e);
                        btn.textContent = old; btn.disabled = false;
                    }
                };
                poll();   // 立即跑一次
                _collectPollTimers[k] = setInterval(poll, 3000);
            }catch(e){
                console.error('[水神·采集] 启动异常', e);
                btn.textContent='✗'; setTimeout(function(){btn.textContent=old;btn.disabled=false;},2000);
            }
        };

        window.gameUnbind = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            if(!confirm('解绑 '+uid+' ？便笺/战报/抽卡记录都会清')) return;
            await fetch('/api/game/unbind', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({game, uid}),
            });
            delete _openState[game+'::'+uid];
            loadOverview();
        };

        window.gameRefreshAll = async function(){
            await fetch('/api/game/collect_all', {method:'POST'});
            setTimeout(loadOverview, 10000);
            setTimeout(loadOverview, 25000);
        };

        window.gameSelectPool = function(k, pool){
            _currentPool[k] = pool;
            var parts = k.split('::'); var g = parts[0]; var u = parts[1];
            var a = _allAccs.find(function(x){return x.uid === u && x.game === g;});
            if(a) _fillGacha(a, k);
        };

        // 抽卡同步：异步任务 + 轮询。刷新页面不会中断后端任务。
        var _gachaPollTimers = {};   // key -> interval id

        function _formatGachaProgress(prog){
            if(!prog) return '';
            var keys = Object.keys(prog);
            if(keys.length === 0) return '准备中...';
            return keys.map(function(p){
                var v = prog[p];
                return p+':'+(v < 0 ? '✗' : v);
            }).join(' / ');
        }

        function _stopGachaPoll(k){
            if(_gachaPollTimers[k]){
                clearInterval(_gachaPollTimers[k]);
                delete _gachaPollTimers[k];
            }
        }

        async function _pollGachaSync(game, uid, btn){
            var k = game+'::'+uid;
            _stopGachaPoll(k);
            console.log('[水神·抽卡] 开始轮询 sync state', k);
            var poll = async function(){
                try{
                    var r = await fetch('/api/game/gacha/sync/status?game='+game+'&uid='+encodeURIComponent(uid));
                    var s = await r.json();
                    var statusEl = document.getElementById('gsync-status-'+k);
                    if(s.state === 'running'){
                        var progressText = _formatGachaProgress(s.progress);
                        console.log('[水神·抽卡] '+k+' running '+progressText);
                        if(statusEl){ statusEl.className = 'gacha-sync-status running'; statusEl.textContent = progressText; }
                        if(btn){ btn.disabled = true; btn.textContent = '同步中...'; }
                    }else if(s.state === 'done'){
                        _stopGachaPoll(k);
                        var res = s.result || {};
                        var sum = res.summary || {};
                        var errs = res.errors || null;
                        var added = Object.keys(sum).map(function(p){return p+':'+sum[p];}).join(' / ') || '0';
                        console.log('[水神·抽卡] '+k+' DONE  summary='+added+'  errors='+JSON.stringify(errs));
                        if(btn){ btn.disabled = false; btn.textContent = '同步抽卡'; }
                        // 先重渲卡池数据，再把完成消息写到新 statusEl（重渲会换掉旧 DOM）
                        var a = _allAccs.find(function(x){return x.uid === uid && x.game === game;});
                        if(a){
                            await _fillGacha(a, keyOf(a));
                            var newStatus = document.getElementById('gsync-status-'+k);
                            var hasErr = errs && Object.keys(errs).length > 0;
                            if(newStatus){
                                newStatus.className = 'gacha-sync-status ' + (hasErr ? 'failed' : 'done');
                                newStatus.textContent = (hasErr ? '✗ ' : '✓ ') + added;
                            }
                        }
                        // 弹窗：分级诊断
                        if(errs){
                            var keys = Object.keys(errs);
                            var allFail = Object.keys(sum).every(function(p){ return sum[p] === -1; });
                            var lines = keys.map(function(p){return p+': '+errs[p];}).join('\\n');
                            var firstErr = errs[keys[0]] || '';
                            var isAuthKeyErr = (allFail && firstErr.indexOf('-100') >= 0);
                            if(isAuthKeyErr && game === 'sr'){
                                // 米哈游对 SR 抽卡 authkey 限制——stoken→authkey 路径被拒。
                                // 只能让用户从游戏内复制 URL 手动导入。
                                window.gameImportGachaUrl(game, uid);
                            }else if(isAuthKeyErr){
                                // GS/ZZZ 失败更可能是账号未真实绑定 → 一键解绑重绑
                                var ok = confirm(
                                    game.toUpperCase()+' 抽卡同步全部失败：\\n' + lines +
                                    '\\n\\n这通常意味着该 '+uid+' 账号在米游社侧未成功绑定。\\n\\n' +
                                    '是否立即解绑此账号并重新扫码？\\n' +
                                    '（解绑会清掉该账号的便笺/战报/抽卡缓存）'
                                );
                                if(ok){
                                    try{
                                        await fetch('/api/game/unbind', {
                                            method:'POST', headers:{'Content-Type':'application/json'},
                                            body: JSON.stringify({game, uid}),
                                        });
                                        if(typeof loadOverview === 'function') loadOverview();
                                        if(typeof openQrModal === 'function') openQrModal();
                                    }catch(unbindErr){
                                        alert('解绑失败: '+unbindErr+'\\n请手动展开账号详情 → 点右下角"解绑"');
                                    }
                                }
                            }else{
                                var prefix = allFail ? game.toUpperCase()+' 同步全部失败：\\n' : game.toUpperCase()+' 部分池子失败：\\n';
                                alert(prefix + lines);
                            }
                        }
                    }else if(s.state === 'failed'){
                        _stopGachaPoll(k);
                        console.error('[水神·抽卡] '+k+' FAILED', s.error);
                        if(statusEl){ statusEl.className = 'gacha-sync-status failed'; statusEl.textContent = '✗ ' + (s.error||''); }
                        if(btn){ btn.disabled = false; btn.textContent = '同步抽卡'; }
                        alert('同步失败: '+(s.error||''));
                    }else{
                        _stopGachaPoll(k);
                        if(btn){ btn.disabled = false; btn.textContent = '同步抽卡'; }
                    }
                }catch(e){
                    console.error('[水神·抽卡] poll 异常', e);
                    _stopGachaPoll(k);
                    if(btn){ btn.disabled = false; btn.textContent = '同步抽卡'; }
                }
            };
            poll();   // 立即跑一次
            _gachaPollTimers[k] = setInterval(poll, 2500);
        }

        window.gameSyncGacha = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            console.log('[水神·抽卡] 点击同步抽卡', game, uid);
            btn.disabled = true; var old = btn.textContent; btn.textContent = '启动...';
            try{
                var r = await fetch('/api/game/gacha/sync', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game, uid}),
                });
                var d = await r.json();
                console.log('[水神·抽卡] /sync 响应', d);
                if(!d.ok){
                    alert('启动失败: '+(d.msg||''));
                    btn.disabled = false; btn.textContent = old;
                    return;
                }
                _pollGachaSync(game, uid, btn);
            }catch(e){
                console.error('[水神·抽卡] /sync 异常', e);
                alert('请求异常: '+e);
                btn.disabled = false; btn.textContent = old;
            }
        };

        // ============ 扫码 modal ============
        var _qrPollTimer = null;
        window.openQrModal = function(){
            document.getElementById('qrModal').classList.add('show');
            document.getElementById('qrBox').innerHTML = '<button class="btn primary" onclick="startQrLogin()">生成二维码</button>';
            document.getElementById('qrStatus').textContent = '';
        };
        window.closeQrModal = function(){
            document.getElementById('qrModal').classList.remove('show');
            if(_qrPollTimer){ clearInterval(_qrPollTimer); _qrPollTimer = null; }
        };

        // ============ URL 导入 modal（SR 必走，GS/ZZZ fallback）============
        var _urlImportCtx = null;   // {game, uid}

        var SR_PS_CMD = '[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12; Invoke-Expression (New-Object Net.WebClient).DownloadString("https://imgheybox.max-c.com/game/star_rail/link1.ps1")';

        var GACHA_TUTORIAL = {
            'sr': '<b>SR 抽卡链接获取教程</b>（米哈游限制，SR 必须手动导入 URL）'
                + '<br>'
                + '<br>1. <b>PC 端</b>启动星穹铁道，登录该账号'
                + '<br>2. 在游戏内打开<b>跃迁 → 跃迁记录</b>页面（确保能看到抽卡历史）'
                + '<br>3. 打开 <b>PowerShell</b>，粘贴下面整段命令并回车（来自小黑盒）：'
                + '<div class="ps-cmd-box">'
                +   '<textarea id="srPsCmd" readonly onclick="this.select()">'+SR_PS_CMD+'</textarea>'
                +   '<button class="ps-cmd-copy" id="srPsCmdCopyBtn" onclick="copyPsCommand(this)">复制</button>'
                + '</div>'
                + '4. 脚本会输出 / 复制带 <code>authkey=xxx</code> 的完整 URL，粘贴到下方'
                + '<br>'
                + '<br><span style="color:var(--text-muted)">链接 24 小时内有效；过期重新拿即可</span>',
        };

        window.copyPsCommand = async function(btn){
            try{
                if(navigator.clipboard && navigator.clipboard.writeText){
                    await navigator.clipboard.writeText(SR_PS_CMD);
                }else{
                    // fallback：选中 textarea + execCommand
                    var ta = document.getElementById('srPsCmd');
                    if(ta){ ta.select(); document.execCommand('copy'); }
                }
                btn.classList.add('done');
                btn.textContent = '✓ 已复制';
                setTimeout(function(){
                    btn.classList.remove('done');
                    btn.textContent = '复制';
                }, 2000);
            }catch(e){
                console.error('[水神·抽卡] 复制 PowerShell 命令失败', e);
                alert('复制失败，请手动选中复制：'+e);
            }
        };

        window.gameImportGachaUrl = function(game, uid){
            _urlImportCtx = {game, uid};
            document.getElementById('urlImportTitle').textContent = '导入 ' + game.toUpperCase() + ' 抽卡链接（' + uid + '）';
            document.getElementById('urlImportTutorial').innerHTML = GACHA_TUTORIAL[game] || '从游戏内复制带 authkey=... 的完整链接';
            document.getElementById('urlImportInput').value = '';
            document.getElementById('urlImportModal').classList.add('show');
            setTimeout(function(){ document.getElementById('urlImportInput').focus(); }, 50);
        };

        window.closeUrlImportModal = function(){
            document.getElementById('urlImportModal').classList.remove('show');
            _urlImportCtx = null;
        };

        window.submitUrlImport = async function(){
            if(!_urlImportCtx) return;
            var url = document.getElementById('urlImportInput').value.trim();
            if(!url){ alert('请粘贴 URL'); return; }
            var ctx = _urlImportCtx;
            console.log('[水神·抽卡] URL 导入提交', ctx.game, ctx.uid, 'url_len=', url.length);
            try{
                var r = await fetch('/api/game/gacha/import_url', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game: ctx.game, uid: ctx.uid, url: url}),
                });
                var d = await r.json();
                console.log('[水神·抽卡] /import_url 响应', d);
                if(!d.ok){
                    alert('启动失败: '+(d.msg||''));
                    return;
                }
                closeUrlImportModal();
                _pollGachaSync(ctx.game, ctx.uid, null);
            }catch(e){
                console.error('[水神·抽卡] /import_url 异常', e);
                alert('请求异常: '+e);
            }
        };
        window.startQrLogin = async function(){
            if(_qrPollTimer){ clearInterval(_qrPollTimer); _qrPollTimer = null; }
            var box = document.getElementById('qrBox');
            var status = document.getElementById('qrStatus');
            box.innerHTML = '<span style="color:#666">生成中...</span>';
            status.textContent = '请求米游社 QR...';
            var r = await fetch('/api/game/qr_create', {method:'POST'});
            var d = await r.json();
            if(!d.ok){ status.textContent='生成失败: '+(d.error||''); return; }
            box.innerHTML = '<img src="https://api.qrserver.com/v1/create-qr-code/?size=240x240&data='+encodeURIComponent(d.url)+'">';
            status.textContent = '请用米游社 APP 扫码';
            _qrPollTimer = setInterval(async function(){
                var rp = await fetch('/api/game/qr_poll?ticket='+encodeURIComponent(d.ticket)+'&device='+encodeURIComponent(d.device)+'&app_id='+d.app_id);
                var dp = await rp.json();
                if(dp.stat === 'Scanned'){ status.textContent = '已扫描，等待确认...'; }
                else if(dp.stat === 'Confirmed'){
                    clearInterval(_qrPollTimer); _qrPollTimer = null;
                    var bound = (dp.bound||[]).map(function(x){return (GAME_META[x.game]||{name:x.game}).name+'('+x.uid+')';}).join(', ');
                    status.textContent = '✅ 绑定成功：'+bound;
                    setTimeout(function(){ closeQrModal(); loadOverview(); }, 1500);
                }
                else if(dp.stat === 'Error'){
                    clearInterval(_qrPollTimer); _qrPollTimer = null;
                    status.textContent = '失败: '+(dp.msg||'');
                }
            }, 2000);
        };

        // ========= 📰 游戏资讯订阅（按钮集成进账号卡，详情区有完整控件 + 推送预览）=========
        var _subsCache = [];        // 全部 mihoyo_game 订阅
        var _pushesCache = {};      // {game: [push records]} 按游戏分桶

        function _fmtSubTime(ts){
            if(!ts) return '从未运行';
            var d = new Date(ts*1000);
            return (d.getMonth()+1)+'-'+d.getDate()+' '
                + d.getHours().toString().padStart(2,'0')+':'
                + d.getMinutes().toString().padStart(2,'0');
        }

        function _findSub(game, uid){
            for(var i=0; i<_subsCache.length; i++){
                if(_subsCache[i].game === game && _subsCache[i].uid === uid) return _subsCache[i];
            }
            return null;
        }

        // 拉订阅 + 推送数据，刷新 UI；自带递归轮询（同风神 feed_html 模式）：
        // 有 sub.running 时 2s 后自动再调一次直到全部完成
        var _subsPollTimer = null;
        async function loadGameSubs(){
            try {
                var r = await fetch('/api/game/subscriptions');
                var data = await r.json();
                _subsCache = data.subs || [];
            } catch(e){ console.error('subs fetch failed', e); _subsCache = []; }

            try {
                var rp = await fetch('/api/push_archive/list?actor=' + encodeURIComponent('水神') + '&limit=30');
                var dp = await rp.json();
                var records = dp.records || [];
                _pushesCache = { gs: [], sr: [], zzz: [] };
                records.forEach(function(rec){
                    // source 形如 '水神·mihoyo_game:gs:113975833'（archon 中文名前缀，不固定位置 0）
                    var src = rec.source || '';
                    if(src.indexOf('mihoyo_game:gs:') >= 0) _pushesCache.gs.push(rec);
                    else if(src.indexOf('mihoyo_game:sr:') >= 0) _pushesCache.sr.push(rec);
                    else if(src.indexOf('mihoyo_game:zzz:') >= 0) _pushesCache.zzz.push(rec);
                });
            } catch(e){ console.error('pushes fetch failed', e); _pushesCache = {}; }

            _hydrateSubsBtns();

            // 有采集中的订阅 → 2s 后自动再刷一次，直到全部完成
            if(_subsCache.some(function(s){return s.running;})){
                if(_subsPollTimer) clearTimeout(_subsPollTimer);
                _subsPollTimer = setTimeout(loadGameSubs, 2000);
            }
        }

        // 填充：账号卡资讯行 + 详情区推送面板
        function _hydrateSubsBtns(){
            var rows = document.querySelectorAll('.ac-news-line');
            for(var i=0; i<rows.length; i++){
                var row = rows[i];
                _renderNewsLine(row,
                    row.getAttribute('data-game'),
                    row.getAttribute('data-uid'));
            }
            // 详情卡才有 ac-news-pushes 占位（_renderFullCard 渲染的卡才有）
            var panels = document.querySelectorAll('.ac-news-pushes');
            for(var j=0; j<panels.length; j++){
                var p = panels[j];
                _renderPushesPanel(p,
                    p.getAttribute('data-game'),
                    p.getAttribute('data-uid'));
            }
        }

        // 总览资讯行（精简）：状态 toggle + 上次时间·条数 + 立即采集按钮
        // 不显示推送标题（标题留给详情卡的 ac-news-pushes 面板展示）
        function _renderNewsLine(row, game, uid){
            var sub = _findSub(game, uid);
            var pushes = (_pushesCache[game] || []).filter(function(p){
                return (p.source || '').indexOf('mihoyo_game:' + game + ':' + uid) >= 0;
            });
            row.classList.remove('on', 'err', 'busy');

            // 未就绪：占位
            if(!sub){
                row.innerHTML =
                    '<span class="news-toggle"><span class="dot"></span>加载中</span>'
                    + '<span class="news-icon">📰</span>'
                    + '<span class="news-text"><span class="meta">资讯订阅</span></span>'
                    + '<button class="news-run" disabled>采集</button>';
                return;
            }

            // 采集中：优先级最高（正在跑就是正在跑，覆盖启停/失败显示）
            if(sub.running){
                row.classList.add('busy');
                row.innerHTML =
                    '<label class="news-toggle busy">'
                    +   '<span class="dot"></span>采集中…'
                    + '</label>'
                    + '<span class="news-icon">⏳</span>'
                    + '<span class="news-text"><span class="meta">任务运行中，稍候自动刷新</span></span>'
                    + '<button class="news-run" disabled>采集中</button>';
                return;
            }

            // 状态色
            if(sub.last_error) row.classList.add('err');
            else if(sub.enabled) row.classList.add('on');

            var toggleLabel = sub.enabled ? '运行中' : '已停止';
            var toggleCls = 'news-toggle' + (sub.enabled ? ' on' : '');

            // 总览精简：仅状态摘要，不带标题
            var textHtml;
            if(sub.last_error){
                textHtml = '<span class="err-msg">⚠ ' + esc(sub.last_error.substring(0, 80)) + '</span>';
            } else if(pushes.length){
                var latest = pushes[0];
                var t = _fmtSubTime(latest.created_at || latest.updated_at);
                textHtml = '<span class="meta">上次 ' + esc(t) + ' · ' + pushes.length + ' 条今日推送</span>';
            } else {
                var stat = sub.last_run_at
                    ? '上次 ' + _fmtSubTime(sub.last_run_at) + ' · 暂无新资讯'
                    : '暂无推送 · 每天 7 点采集';
                textHtml = '<span class="meta">' + esc(stat) + '</span>';
            }

            row.innerHTML =
                '<label class="' + toggleCls + '" title="点击启停">'
                +   '<input type="checkbox" ' + (sub.enabled ? 'checked' : '') + ' '
                +     'style="display:none">'
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
                toggleGameSub(checkbox, subId);
            };
            runBtn.onclick = function(){
                runBtn.disabled = true;
                runBtn.textContent = '采集中…';
                runGameSub(subId, runBtn);
            };
        }

        // 推送面板：holder.dataset.detailed='1' = 游戏 tab 完整版（可展开看完整 md）
        // 否则 = 总览只读汇总（仅标题列表 + 跳转链接）
        function _renderPushesPanel(holder, game, uid){
            var pushes = (_pushesCache[game] || []).filter(function(p){
                return (p.source || '').indexOf('mihoyo_game:' + game + ':' + uid) >= 0;
            });
            if(!pushes.length){
                holder.innerHTML = '';  // 没推送时整段隐藏
                return;
            }
            var detailed = holder.getAttribute('data-detailed') === '1';

            // 提取每条的标题（首个非空行去 md 标记）
            function _summary(md){
                var firstLine = (md || '').split('\\n').filter(function(L){return L.trim();})[0] || '';
                return firstLine.replace(/^[#*\\-\\s>]+/, '').substring(0, 80) || '(空标题)';
            }

            // 总览：只读汇总列表 + 跳详情
            if(!detailed){
                var rows = pushes.slice(0, 5).map(function(p){
                    var t = _fmtSubTime(p.created_at || p.updated_at);
                    return '<li class="news-summary-row">'
                        + '<span class="news-push-time">' + esc(t) + '</span>'
                        + '<span class="news-push-title">' + esc(_summary(p.message_md)) + '</span>'
                        + '</li>';
                }).join('');
                var more = pushes.length > 5
                    ? '<a class="news-more-link" onclick="switchGameTab(\\''+esc(game)+'\\')">查看全部 '+pushes.length+' 条 →</a>'
                    : '<a class="news-more-link" onclick="switchGameTab(\\''+esc(game)+'\\')">进游戏页看完整内容 →</a>';
                holder.innerHTML =
                    '<div class="news-pushes-head">📰 今日推送 · ' + pushes.length + ' 条</div>'
                    + '<ul class="news-pushes-list news-pushes-list-summary">' + rows + '</ul>'
                    + '<div class="news-more">' + more + '</div>';
                return;
            }

            // 详细：可展开折叠卡片（marked.parse 渲染完整 md，外部链接 target=_blank）
            var items = pushes.slice(0, 8).map(function(p){
                var t = _fmtSubTime(p.created_at || p.updated_at);
                var md = p.message_md || '';
                var bodyHtml = _renderMdSafe(md);
                return '<div class="news-push-item">'
                    +   '<div class="news-push-head" onclick="this.parentElement.classList.toggle(\\'open\\')">'
                    +     '<span class="news-push-arrow">▶</span>'
                    +     '<span class="news-push-time">' + esc(t) + '</span>'
                    +     '<span class="news-push-title">' + esc(_summary(md)) + '</span>'
                    +   '</div>'
                    +   '<div class="news-push-body markdown-body">' + bodyHtml + '</div>'
                    + '</div>';
            }).join('');
            holder.innerHTML =
                '<div class="news-pushes-head">📰 今日推送 · ' + pushes.length + ' 条 <span class="news-pushes-hint">点击单条展开</span></div>'
                + '<div class="news-pushes-list">' + items + '</div>';
        }


        window.toggleGameSub = async function(checkbox, subId){
            var enabled = checkbox.checked;
            try {
                var r = await fetch('/api/game/subscriptions/'+encodeURIComponent(subId)+'/toggle', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({enabled: enabled}),
                });
                var d = await r.json();
                if(!d.ok){
                    alert('切换失败: '+(d.error||'unknown'));
                    checkbox.checked = !enabled;
                } else {
                    loadGameSubs();
                }
            } catch(e){
                alert('请求失败: '+e.message);
                checkbox.checked = !enabled;
            }
        };

        window.runGameSub = async function(subId, btn){
            // btn 文字已由 _renderNewsLine 的 onclick 提前置为"采集中…"
            try {
                var r = await fetch('/api/game/subscriptions/'+encodeURIComponent(subId)+'/run', {method:'POST'});
                var d = await r.json();
                if(!d.ok){
                    alert('触发失败: '+(d.error||'unknown'));
                    if(btn){ btn.disabled = false; btn.textContent = '采集'; }
                    return;
                }
            } catch(e){
                alert('请求失败: '+e.message);
                if(btn){ btn.disabled = false; btn.textContent = '采集'; }
                return;
            }
            // loadGameSubs 自带递归轮询：检测到 sub.running 会 setTimeout(loadGameSubs, 2000)
            // 直到 running=false 自然停（同风神 feed_html.py 模式）
            await loadGameSubs();
        };

        // 入口：loadOverview + loadGameSubs 并行
        window.onload = function(){
            loadOverview();
            loadGameSubs();
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
    })();
    </script>
"""


def build_game_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 游戏</title>
    <!-- 推送内容用 markdown 渲染（同主聊天面板） -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + GAME_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("game")
        + GAME_BODY
        + GAME_SCRIPT
        + """</body>
</html>"""
    )
