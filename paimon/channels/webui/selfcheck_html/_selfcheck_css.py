"""SELFCHECK_CSS chunk · 自动切片，原始字符串拼接还原。"""

SELFCHECK_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1280px; margin: 0 auto; padding: 24px; }

    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .header-actions { display: flex; gap: 10px; align-items: center; }
    .btn {
        padding: 8px 16px; background: var(--paimon-panel-light);
        color: var(--text-secondary); border: 1px solid var(--paimon-border);
        border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .btn:hover { border-color: var(--gold-dark); color: var(--gold); }
    .btn:disabled { opacity: 0.45; cursor: not-allowed; }
    .btn-primary { background: var(--gold-dark); color: #1a1625; border-color: var(--gold); }
    .btn-primary:hover { background: var(--gold); color: #1a1625; }
    .btn-danger { color: var(--status-error); }
    .btn-danger:hover { border-color: var(--status-error); }

    .status-pill {
        display: inline-flex; align-items: center; gap: 6px;
        padding: 4px 10px; border-radius: 999px; font-size: 12px;
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
    }
    .status-ok { color: var(--status-success); }
    .status-degraded { color: var(--status-warning); }
    .status-critical { color: var(--status-error); }

    .tab-bar {
        display: flex; gap: 4px; margin-bottom: 16px;
        border-bottom: 1px solid var(--paimon-border);
    }
    .tab {
        padding: 10px 18px; color: var(--text-muted); cursor: pointer;
        font-size: 14px; border-bottom: 2px solid transparent;
        transition: all 0.15s;
    }
    .tab:hover { color: var(--text-secondary); }
    .tab.active { color: var(--gold); border-bottom-color: var(--gold); }

    .table-wrap {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 8px; overflow: hidden;
    }
    table.runs {
        width: 100%; border-collapse: collapse; font-size: 13px;
    }
    table.runs th, table.runs td {
        padding: 10px 14px; text-align: left;
        border-bottom: 1px solid var(--paimon-border);
    }
    table.runs th {
        background: var(--paimon-panel-light); color: var(--text-secondary);
        font-weight: 500; font-size: 12px; text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    table.runs tr:last-child td { border-bottom: none; }
    table.runs tbody tr:hover { background: var(--paimon-panel-light); }
    table.runs td.num { font-family: monospace; text-align: right; }
    table.runs td.id { font-family: monospace; color: var(--text-muted); }
    table.runs td.actions { text-align: right; }
    .mini-btn {
        padding: 4px 10px; margin-left: 4px; font-size: 12px;
        background: transparent; color: var(--text-muted);
        border: 1px solid var(--paimon-border); border-radius: 4px; cursor: pointer;
    }
    .mini-btn:hover { border-color: var(--gold-dark); color: var(--gold); }
    .mini-btn.danger:hover { border-color: var(--status-error); color: var(--status-error); }

    .sev-p0 { color: var(--status-error); font-weight: 600; }
    .sev-p1 { color: var(--status-warning); font-weight: 600; }
    .sev-p2 { color: var(--star); }
    .sev-p3 { color: var(--text-muted); }

    .empty-state { padding: 60px 20px; text-align: center; color: var(--text-muted); }

    /* Modal */
    .modal-mask {
        position: fixed; inset: 0; background: rgba(0,0,0,0.65);
        display: none; align-items: flex-start; justify-content: center;
        z-index: 100; overflow-y: auto; padding: 40px 20px;
    }
    .modal-mask.show { display: flex; }
    .modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; max-width: 1100px; width: 100%;
        box-shadow: 0 20px 40px rgba(0,0,0,.5);
    }
    .modal-head {
        padding: 16px 20px; border-bottom: 1px solid var(--paimon-border);
        display: flex; justify-content: space-between; align-items: center;
    }
    .modal-head h3 { font-size: 16px; color: var(--gold); }
    .modal-close {
        background: transparent; border: none; color: var(--text-muted);
        font-size: 22px; cursor: pointer;
    }
    .modal-body { padding: 20px; }
    .modal-meta {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 12px; margin-bottom: 20px;
    }
    .meta-item { background: var(--paimon-panel-light); padding: 10px 12px; border-radius: 6px; }
    .meta-label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 2px; }
    .meta-value { font-size: 13px; color: var(--text-primary); word-break: break-word; }

    .sev-bar { display: flex; gap: 10px; margin: 16px 0; }
    .sev-chip {
        padding: 8px 14px; border-radius: 6px; font-size: 13px;
        background: var(--paimon-panel-light); border: 1px solid var(--paimon-border);
    }
    .sev-chip .label { font-size: 11px; color: var(--text-muted); margin-right: 4px; }

    .findings-filter { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
    .findings-filter select, .findings-filter input {
        padding: 6px 10px; background: var(--paimon-panel-light);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        color: var(--text-primary); font-size: 13px;
    }
    .findings-list { max-height: 500px; overflow-y: auto; }
    .finding {
        padding: 12px; margin-bottom: 8px; border-radius: 6px;
        background: var(--paimon-panel-light); border-left: 3px solid var(--paimon-border);
    }
    .finding.p0 { border-left-color: var(--status-error); }
    .finding.p1 { border-left-color: var(--status-warning); }
    .finding.p2 { border-left-color: var(--star); }
    .finding.p3 { border-left-color: var(--text-muted); }
    .finding-head { display: flex; gap: 10px; align-items: center; margin-bottom: 6px; font-size: 12px; }
    .finding-loc { font-family: monospace; color: var(--star); }
    .finding-module { color: var(--text-muted); }
    .finding-desc { font-size: 13px; color: var(--text-primary); line-height: 1.5; }
    .finding-evidence { font-size: 12px; color: var(--text-muted); margin-top: 6px; padding-left: 8px; border-left: 2px solid var(--paimon-border); }

    .quick-snapshot { margin-top: 12px; }
    .comp-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 8px; }
    .comp-card {
        padding: 10px 12px; border-radius: 6px; background: var(--paimon-panel-light);
        border-left: 3px solid var(--paimon-border);
    }
    .comp-card.ok { border-left-color: var(--status-success); }
    .comp-card.degraded { border-left-color: var(--status-warning); }
    .comp-card.critical { border-left-color: var(--status-error); }
    .comp-name { font-weight: 600; font-size: 13px; }
    .comp-latency { font-size: 11px; color: var(--text-muted); }
    .comp-details { margin-top: 6px; font-size: 12px; color: var(--text-secondary); white-space: pre-wrap; word-break: break-all; max-height: 120px; overflow-y: auto; }
"""
