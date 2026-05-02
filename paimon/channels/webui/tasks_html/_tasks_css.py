"""TASKS_CSS chunk · 自动切片，原始字符串拼接还原。"""

TASKS_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .refresh-btn {
        padding: 8px 16px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .refresh-btn:hover { border-color: var(--gold-dark); color: var(--gold); }

    /* tabs（同 feed_html.py） */
    .tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid var(--paimon-border); }
    .tab-btn {
        padding: 10px 20px; background: transparent; border: none; color: var(--text-muted);
        cursor: pointer; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active { color: var(--gold); border-bottom-color: var(--gold); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    .tab-count {
        display: inline-block; min-width: 18px; padding: 0 6px; margin-left: 4px;
        font-size: 11px; line-height: 16px; border-radius: 8px;
        background: var(--paimon-panel-light); color: var(--text-muted);
        vertical-align: middle;
    }
    .tab-btn.active .tab-count { background: rgba(245,158,11,.2); color: var(--gold); }
    .tab-count:empty { display: none; }

    .task-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }
    .task-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 20px; transition: border-color .2s;
    }
    .task-card:hover { border-color: var(--gold-dark); }
    .task-card.disabled { opacity: .6; }
    .task-card.clickable { cursor: pointer; }

    .task-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px; }
    .task-id { font-size: 12px; color: var(--text-muted); font-family: monospace; }
    .task-badge {
        padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 500;
    }
    .badge-enabled { background: rgba(16,185,129,.15); color: var(--status-success); }
    .badge-disabled { background: rgba(239,68,68,.15); color: var(--status-error); }
    .badge-running   { background: rgba(59,130,246,.15); color: #60a5fa; }
    .badge-completed { background: rgba(16,185,129,.15); color: var(--status-success); }
    .badge-failed    { background: rgba(239,68,68,.15); color: var(--status-error); }
    .badge-pending   { background: rgba(156,163,175,.15); color: var(--text-muted); }
    .badge-rejected  { background: rgba(239,68,68,.15); color: var(--status-error); }

    .task-prompt {
        font-size: 14px; color: var(--text-primary); margin-bottom: 12px;
        line-height: 1.5; word-break: break-word;
        max-height: 60px; overflow: hidden; text-overflow: ellipsis;
    }

    .task-meta { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: var(--text-muted); }
    .task-meta-item {
        background: var(--paimon-panel-light); padding: 4px 8px; border-radius: 4px;
    }
    .task-error {
        margin-top: 8px; padding: 8px; border-radius: 6px;
        background: rgba(239,68,68,.1); border: 1px solid rgba(239,68,68,.2);
        font-size: 12px; color: var(--status-error);
    }

    /* 方案 D：内部任务（周期采集 / 红利扫描等）视觉上区分 */
    .task-card.internal {
        border-left: 3px solid var(--gold-dark);
        background: linear-gradient(90deg, rgba(245,158,11,.04), var(--paimon-panel) 40%);
    }
    .task-card.internal:hover { border-color: var(--gold); }
    .task-source-chip {
        display: inline-block; padding: 2px 8px; margin-right: 6px;
        border-radius: 10px; font-size: 11px; font-weight: 600;
        background: rgba(245,158,11,.15); color: var(--gold); border: 1px solid rgba(245,158,11,.3);
    }
    .task-source-chip.unknown {
        background: rgba(239,68,68,.1); color: var(--status-error);
        border-color: rgba(239,68,68,.3);
    }
    .task-source-hint {
        margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--paimon-border);
        font-size: 11px; color: var(--text-muted);
    }
    .task-source-hint a { color: var(--gold); text-decoration: none; }
    .task-source-hint a:hover { text-decoration: underline; }

    /* 系统任务两层分组：外层按神 / 内层按精确分钟 cron */
    .archon-section {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; margin-bottom: 16px; overflow: hidden;
    }
    .archon-header {
        padding: 12px 18px; background: var(--paimon-panel-light);
        border-bottom: 1px solid var(--paimon-border);
        display: flex; align-items: center; gap: 10px;
        cursor: pointer; user-select: none;
    }
    .archon-header:hover { background: rgba(245,158,11,.08); }
    .archon-arrow { color: var(--gold); font-size: 11px; width: 12px; transition: transform .2s; }
    .archon-section.collapsed .archon-arrow { transform: rotate(-90deg); }
    .archon-section.collapsed .archon-header { border-bottom-color: transparent; }
    .archon-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
    .archon-stat { font-size: 12px; color: var(--text-muted); margin-left: auto; }
    .archon-body { padding: 12px 18px; display: flex; flex-direction: column; gap: 10px; }
    .archon-section.collapsed .archon-body { display: none; }

    .time-group-head {
        padding: 9px 12px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 6px;
        display: flex; align-items: center; gap: 10px;
        cursor: pointer; user-select: none; transition: border-color .2s;
    }
    .time-group-head:hover { border-color: var(--gold-dark); }
    .time-group.expanded .time-group-head {
        border-bottom-left-radius: 0; border-bottom-right-radius: 0;
        border-color: var(--gold-dark);
    }
    .time-group-arrow { color: var(--text-muted); font-size: 10px; width: 10px; transition: transform .2s; }
    .time-group.expanded .time-group-arrow { transform: rotate(90deg); color: var(--gold); }
    .time-group-time { font-size: 13px; color: var(--text-primary); font-weight: 500; min-width: 140px; }
    .time-group-count {
        font-size: 11px; color: var(--gold);
        padding: 1px 7px; border-radius: 9px; background: rgba(245,158,11,.15);
    }
    .time-group-preview {
        font-size: 12px; color: var(--text-muted); flex: 1;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .time-group-body {
        display: none;
        padding: 12px;
        border: 1px solid var(--gold-dark); border-top: none;
        border-radius: 0 0 6px 6px;
        background: rgba(245,158,11,.03);
        grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
        gap: 12px;
    }
    .time-group.expanded .time-group-body { display: grid; }
    .time-group-body .task-card { background: var(--paimon-panel); }

    /* N=1 一行紧凑展示（不折叠） */
    .time-single {
        padding: 10px 14px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 6px;
        display: flex; align-items: center; gap: 12px;
        cursor: pointer; transition: border-color .2s;
    }
    .time-single:hover { border-color: var(--gold-dark); }
    .time-single.disabled { opacity: .55; }
    .time-single-time { font-size: 13px; color: var(--text-primary); font-weight: 500; min-width: 140px; }
    .time-single-desc { font-size: 13px; color: var(--text-secondary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    .empty-state { text-align: center; padding: 80px 20px; color: var(--text-muted); font-size: 14px; }
    .empty-icon { font-size: 48px; margin-bottom: 16px; opacity: .5; }

    /* modal */
    .modal-mask {
        position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 1000;
        display: none; align-items: center; justify-content: center; padding: 20px;
    }
    .modal-mask.show { display: flex; }
    .modal-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 12px; padding: 24px; max-width: 900px; width: 100%;
        max-height: 85vh; overflow-y: auto;
    }
    .modal-card h2 { font-size: 20px; color: var(--text-primary); margin-bottom: 8px; }
    .modal-card .meta-row { font-size: 13px; color: var(--text-muted); margin-bottom: 16px; }
    .modal-card .meta-row span { margin-right: 12px; }
    .modal-close {
        float: right; background: transparent; border: none; color: var(--text-muted);
        font-size: 22px; cursor: pointer; line-height: 1;
    }
    .modal-close:hover { color: var(--gold); }
    .subtask-table {
        width: 100%; border-collapse: collapse; margin: 16px 0;
        font-size: 13px;
    }
    .subtask-table th, .subtask-table td {
        text-align: left; padding: 8px 10px;
        border-bottom: 1px solid var(--paimon-border);
        vertical-align: top;
    }
    .subtask-table th { color: var(--text-muted); font-weight: 500; font-size: 12px; }
    .subtask-table td { color: var(--text-primary); }
    .subtask-table .col-icon { width: 32px; text-align: center; }
    .subtask-table .col-result { color: var(--text-muted); font-size: 12px; max-width: 360px; }
    .summary-md {
        background: var(--paimon-bg); border: 1px solid var(--paimon-border);
        border-radius: 6px; padding: 12px; margin-top: 12px;
        font-family: monospace; font-size: 12px; color: var(--text-secondary);
        white-space: pre-wrap; word-break: break-word;
        max-height: 360px; overflow-y: auto;
    }
"""
