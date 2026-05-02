"""SENTIMENT_CSS chunk · 自动切片，原始字符串拼接还原。"""

SENTIMENT_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1400px; margin: 0 auto; padding: 24px; }

    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .page-header .sub { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
    .header-actions { display: flex; gap: 10px; }
    .btn {
        padding: 8px 16px; background: var(--paimon-panel-light);
        color: var(--text-secondary); border: 1px solid var(--paimon-border);
        border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .btn:hover { border-color: var(--gold-dark); color: var(--gold); }

    /* 未读 digest banner（actor 有未读归档时顶部提示） */
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

    /* 订阅级 banner（filterSub 选中时显示） */
    .sub-banner {
        display: none;
        background: linear-gradient(90deg, rgba(110,198,255,.06), rgba(212,175,55,.04));
        border: 1px solid var(--paimon-border);
        border-left: 3px solid var(--star);
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 16px;
        font-size: 13px;
        color: var(--text-secondary);
        line-height: 1.7;
    }
    .sub-banner.show { display: block; }
    .sub-banner .b-row { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; }
    .sub-banner .b-row + .b-row { margin-top: 4px; color: var(--text-muted); font-size: 12px; }
    .sub-banner b { color: var(--gold); }
    .sub-banner .sev-mini { padding: 1px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; }
    .sub-banner .sent-strong { color: var(--status-error); font-weight: 600; }
    .sub-banner .sent-pos { color: var(--status-success); font-weight: 600; }
    .sub-banner .sent-neutral { color: var(--text-secondary); }

    .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
    .stat-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 20px; text-align: center;
    }
    .stat-num { font-size: 28px; font-weight: 700; color: var(--gold); }
    .stat-num.negative { color: var(--status-error); }
    .stat-num.positive { color: var(--status-success); }
    .stat-num.warning { color: var(--status-warning); }
    .stat-label { font-size: 13px; color: var(--text-muted); margin-top: 4px; }

    .main-grid { display: grid; grid-template-columns: 3fr 2fr; gap: 16px; }

    /* 左主列：事件时间线 */
    .panel {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 16px;
    }
    .panel-head {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 12px;
    }
    .panel-head h2 { font-size: 15px; color: var(--text-primary); font-weight: 600; }
    .panel-tools { display: flex; gap: 8px; }
    .panel-tools select {
        padding: 4px 8px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        color: var(--text-primary); font-size: 12px;
    }

    .events-list { display: flex; flex-direction: column; gap: 10px; max-height: 70vh; overflow-y: auto; }
    .event-card {
        background: var(--paimon-bg); border: 1px solid var(--paimon-border);
        border-radius: 8px; padding: 14px; cursor: pointer;
        transition: border-color .15s;
    }
    .event-card:hover { border-color: var(--gold-dark); }
    .event-head { display: flex; gap: 8px; align-items: flex-start; margin-bottom: 6px; }
    .sev-badge {
        padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;
        flex-shrink: 0;
    }
    .sev-p0 { background: rgba(239,68,68,.18); color: var(--status-error); }
    .sev-p1 { background: rgba(245,158,11,.18); color: var(--status-warning); }
    .sev-p2 { background: rgba(110,198,255,.18); color: var(--star); }
    .sev-p3 { background: rgba(156,163,175,.18); color: var(--text-muted); }

    .sentiment-chip {
        padding: 2px 8px; border-radius: 4px; font-size: 11px;
        background: var(--paimon-panel-light); color: var(--text-secondary);
        flex-shrink: 0;
    }
    .sentiment-chip.negative { color: var(--status-error); }
    .sentiment-chip.positive { color: var(--status-success); }
    .sentiment-chip.mixed { color: var(--status-warning); }

    .event-title { font-size: 14px; color: var(--text-primary); font-weight: 500; flex: 1; line-height: 1.4; }
    .event-summary { font-size: 12px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 8px; }
    .event-meta { display: flex; flex-wrap: wrap; gap: 6px; font-size: 11px; }
    .meta-tag {
        padding: 2px 6px; background: var(--paimon-panel-light);
        border-radius: 4px; color: var(--text-muted);
    }
    .meta-tag.entity { color: var(--gold-dark); }
    .meta-tag.source { color: var(--star-dark); }

    /* 右栏 */
    .right-col { display: flex; flex-direction: column; gap: 16px; }
    #sentimentChart { max-height: 220px; }

    /* 严重度矩阵 */
    .matrix-grid {
        display: grid; gap: 4px;
        grid-template-rows: auto repeat(4, 1fr);
        grid-template-columns: 60px repeat(7, 1fr);
        font-size: 11px;
    }
    .matrix-cell-header {
        text-align: center; color: var(--text-muted);
        padding: 2px 0;
    }
    .matrix-row-label {
        display: flex; align-items: center; justify-content: flex-end;
        padding-right: 8px; color: var(--text-muted);
    }
    .matrix-cell {
        height: 28px; border-radius: 3px;
        display: flex; align-items: center; justify-content: center;
        background: var(--paimon-bg); color: var(--text-muted);
        font-size: 11px; font-weight: 500;
    }
    .matrix-cell[data-count="0"] { color: var(--paimon-border); }

    /* 信源 Top */
    .sources-list { display: flex; flex-direction: column; gap: 6px; }
    .source-row {
        display: flex; justify-content: space-between; align-items: center;
        padding: 6px 10px; background: var(--paimon-bg); border-radius: 4px;
        font-size: 12px;
    }
    .source-domain { color: var(--text-primary); font-family: monospace; }
    .source-count { color: var(--gold); font-weight: 600; }

    /* Modal */
    .modal-mask {
        position: fixed; inset: 0; background: rgba(0,0,0,.65);
        display: none; align-items: flex-start; justify-content: center;
        z-index: 100; overflow-y: auto; padding: 40px 20px;
    }
    .modal-mask.show { display: flex; }
    .modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; max-width: 900px; width: 100%;
    }
    .modal-head {
        padding: 16px 20px; border-bottom: 1px solid var(--paimon-border);
        display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
    }
    .modal-head h3 { font-size: 16px; color: var(--gold); flex: 1; }
    .modal-close {
        background: transparent; border: none; color: var(--text-muted);
        font-size: 22px; cursor: pointer;
    }
    .modal-body { padding: 20px; }
    .modal-meta { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 16px; }
    .meta-item { background: var(--paimon-panel-light); padding: 8px 12px; border-radius: 6px; }
    .meta-label { font-size: 11px; color: var(--text-muted); margin-bottom: 2px; }
    .meta-value { font-size: 13px; color: var(--text-primary); word-break: break-word; }

    .timeline-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px; }
    .timeline-row {
        display: flex; gap: 10px; font-size: 12px;
        padding: 6px 10px; background: var(--paimon-bg); border-radius: 4px;
    }
    .timeline-ts { color: var(--text-muted); font-family: monospace; flex-shrink: 0; }
    .timeline-point { color: var(--text-secondary); }

    .items-list { display: flex; flex-direction: column; gap: 6px; max-height: 300px; overflow-y: auto; }
    .item-row {
        font-size: 12px; padding: 6px 10px;
        background: var(--paimon-bg); border-radius: 4px;
    }
    .item-title { color: var(--text-primary); display: block; text-decoration: none; }
    .item-title:hover { color: var(--gold); }
    .item-meta { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

    .empty-state { text-align: center; padding: 40px 20px; color: var(--text-muted); font-size: 13px; }

    @media (max-width: 1100px) {
        .main-grid { grid-template-columns: 1fr; }
        .stats-row { grid-template-columns: repeat(2, 1fr); }
    }
"""
