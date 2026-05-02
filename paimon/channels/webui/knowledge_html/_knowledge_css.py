"""KNOWLEDGE_CSS chunk · 自动切片，原始字符串拼接还原。"""

KNOWLEDGE_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .page-header .sub { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
    .refresh-btn {
        padding: 8px 16px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .refresh-btn:hover { border-color: var(--gold-dark); color: var(--gold); }

    .tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid var(--paimon-border); }
    .tab-btn {
        padding: 10px 20px; background: transparent; border: none; color: var(--text-muted);
        cursor: pointer; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active { color: var(--gold); border-bottom-color: var(--gold); }
    .tab-count {
        display: inline-block; min-width: 18px; padding: 0 6px; margin-left: 4px;
        font-size: 11px; line-height: 16px; border-radius: 8px;
        background: var(--paimon-panel-light); color: var(--text-muted); vertical-align: middle;
    }
    .tab-btn.active .tab-count { background: rgba(245,158,11,.2); color: var(--gold); }
    .tab-count:empty { display: none; }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    /* memory 二级 pill */
    .pills-row {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 16px; gap: 16px; flex-wrap: wrap;
    }
    .pills { display: flex; gap: 8px; flex: 1; flex-wrap: wrap; }
    .pill {
        padding: 6px 14px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 20px;
        cursor: pointer; font-size: 13px;
    }
    .pill:hover { color: var(--gold); }
    .pill.active { background: rgba(245,158,11,.15); color: var(--gold); border-color: var(--gold-dark); }

    /* + 新建按钮 */
    .btn-add {
        padding: 6px 14px; background: transparent; color: var(--gold);
        border: 1px solid var(--gold-dark); border-radius: 4px;
        cursor: pointer; font-size: 13px; font-weight: 500;
        transition: all .15s;
    }
    .btn-add:hover { background: rgba(245,158,11,.1); }

    /* 表单 modal */
    .modal-actions { display: flex; align-items: center; gap: 8px; }
    .form-body {
        padding: 8px 0; display: flex; flex-direction: column; gap: 14px;
    }
    .form-field { display: flex; flex-direction: column; gap: 4px; }
    .form-field label { font-size: 12px; color: var(--text-muted); }
    .form-field input[type="text"], .form-field textarea, .form-field select {
        padding: 8px 10px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        color: var(--text-primary); font-size: 13px;
        font-family: inherit;
    }
    .form-field input[type="text"]:focus, .form-field textarea:focus, .form-field select:focus {
        outline: none; border-color: var(--gold);
    }
    .form-field input[disabled] { opacity: .6; cursor: not-allowed; }
    .form-field textarea {
        min-height: 160px; resize: vertical;
        font-family: 'SF Mono', Monaco, Consolas, monospace;
        line-height: 1.5;
    }
    .form-field .hint {
        font-size: 11px; color: var(--text-muted); font-style: italic;
    }
    .form-actions {
        display: flex; justify-content: flex-end; gap: 10px;
        margin-top: 16px; padding-top: 12px;
        border-top: 1px solid var(--paimon-border);
    }
    .btn-save {
        padding: 6px 18px; background: var(--gold); color: #000;
        border: none; border-radius: 4px; cursor: pointer;
        font-size: 13px; font-weight: 600;
    }
    .btn-save:hover { background: var(--gold-dark); }
    .btn-save:disabled { opacity: .5; cursor: not-allowed; }
    .form-error {
        margin-top: 10px; padding: 8px 12px;
        background: rgba(239,68,68,.08); border: 1px solid rgba(239,68,68,.3);
        border-radius: 4px; color: var(--status-error); font-size: 12px;
        display: none;
    }
    .form-error.active { display: block; }

    /* Flash toast（reconcile 结果 / 通用通知）*/
    .flash-bar {
        position: fixed; top: 70px; right: 24px;
        padding: 10px 14px; max-width: 420px;
        background: var(--paimon-panel);
        border: 1px solid var(--paimon-border);
        border-left-width: 3px;
        border-radius: 6px;
        color: var(--text-primary); font-size: 13px; line-height: 1.5;
        box-shadow: 0 4px 12px rgba(0,0,0,.35);
        z-index: 2000;
        opacity: 0; transform: translateX(20px);
        transition: opacity .2s, transform .2s;
        pointer-events: none;
    }
    .flash-bar.active { opacity: 1; transform: translateX(0); }
    .flash-bar.success { border-left-color: var(--status-success); }
    .flash-bar.info    { border-left-color: var(--gold); }
    .flash-bar.warn    { border-left-color: var(--status-warning); }
    .flash-bar .flash-title { font-weight: 600; margin-bottom: 4px; }
    .flash-bar .flash-reason { color: var(--text-muted); font-size: 12px; }

    .data-table { width: 100%; border-collapse: collapse; }
    .data-table th, .data-table td {
        padding: 12px 16px; border-bottom: 1px solid var(--paimon-border);
        font-size: 14px; text-align: left; vertical-align: top;
    }
    .data-table th { color: var(--gold); font-weight: 600; font-size: 13px; }
    .data-table tbody tr:hover td { background: var(--paimon-panel); }

    .chip {
        display: inline-block; padding: 2px 8px; margin: 2px 4px 2px 0;
        border-radius: 10px; font-size: 12px;
        background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border);
    }

    .btn-revoke {
        padding: 4px 12px; background: transparent; border: 1px solid var(--status-error);
        color: var(--status-error); border-radius: 4px; cursor: pointer; font-size: 12px;
    }
    .btn-revoke:hover { background: rgba(239,68,68,.1); }
    .btn-view {
        padding: 4px 12px; background: transparent; border: 1px solid var(--gold-dark);
        color: var(--gold); border-radius: 4px; cursor: pointer; font-size: 12px; margin-right: 4px;
    }
    .btn-view:hover { background: rgba(245,158,11,.1); }

    .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 14px; }
    .empty-state code { background: var(--paimon-panel-light); padding: 2px 6px; border-radius: 4px;
        font-family: 'SF Mono', Monaco, Consolas, monospace; color: var(--gold); }

    .desc { color: var(--text-muted); font-size: 12px; margin-top: 4px; line-height: 1.5; }
    .body-preview {
        font-size: 13px; color: var(--text-secondary); line-height: 1.5;
        max-width: 500px; word-break: break-word;
    }
    .mono { font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 12px; color: var(--text-secondary); }

    /* 文书归档卡片 */
    .archive-card {
        margin-bottom: 12px; padding: 14px 18px;
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 8px;
    }
    .archive-header {
        display: flex; justify-content: space-between; align-items: baseline;
        margin-bottom: 10px;
    }
    .archive-title { font-size: 14px; font-weight: 500; color: var(--text-primary); }
    .archive-task-id { font-size: 11px; color: var(--text-muted); font-family: monospace; }
    .archive-artifacts { display: flex; flex-wrap: wrap; gap: 8px; }
    .archive-artifact {
        padding: 4px 10px; background: var(--paimon-panel-light);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        cursor: pointer; font-size: 12px; color: var(--text-secondary);
        font-family: monospace;
    }
    .archive-artifact:hover { border-color: var(--gold); color: var(--gold); }
    .archive-artifact .count { color: var(--gold); margin-left: 4px; }

    /* 模态 */
    .modal-backdrop {
        display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1000;
        align-items: center; justify-content: center;
    }
    .modal-backdrop.active { display: flex; }
    .modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 8px; max-width: 840px; width: 90%;
        max-height: 85vh; overflow: auto; padding: 24px;
    }
    .modal-header {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 16px; padding-bottom: 12px;
        border-bottom: 1px solid var(--paimon-border);
    }
    .modal-header h3 { color: var(--gold); font-size: 18px; font-weight: 600; }
    .modal-close {
        background: transparent; border: none; color: var(--text-muted); font-size: 22px;
        cursor: pointer; padding: 0 6px;
    }
    .modal-close:hover { color: var(--text-primary); }
    .modal-body {
        white-space: pre-wrap; font-size: 13px; line-height: 1.6;
        color: var(--text-primary); padding: 14px;
        background: var(--paimon-panel-light);
        border-radius: 6px; font-family: 'SF Mono', Monaco, Consolas, monospace;
        max-height: 60vh; overflow-y: auto;
    }
    .modal-meta { color: var(--text-muted); font-size: 12px; margin-top: 12px; line-height: 1.6; }
"""
