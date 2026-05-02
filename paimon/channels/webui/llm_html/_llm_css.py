"""LLM_CSS chunk · 自动切片，原始字符串拼接还原。"""

LLM_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .page-header .sub { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
    .header-actions { display: flex; gap: 10px; align-items: center; }
    .btn {
        padding: 8px 16px; background: var(--paimon-panel-light);
        color: var(--text-secondary); border: 1px solid var(--paimon-border);
        border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .btn:hover { border-color: var(--gold-dark); color: var(--gold); }
    .btn-primary {
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        color: #000; border: none; font-weight: 600;
    }
    .btn-primary:hover { opacity: .9; color: #000; }

    /* profile 卡片列表 */
    .profile-list { display: flex; flex-direction: column; gap: 12px; }
    .profile-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 16px 20px;
        display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: center;
    }
    .profile-card.is-default {
        border-color: var(--gold-dark);
        box-shadow: 0 0 0 1px rgba(255,180,80,.15);
    }
    .profile-info .name { font-size: 16px; color: var(--text-primary); font-weight: 500; margin-bottom: 4px; }
    .profile-info .meta { font-size: 12px; color: var(--text-muted); }
    .profile-info .meta span { margin-right: 12px; }
    .profile-info .notes { color: var(--text-muted); font-size: 12px; margin-top: 4px; font-style: italic; }
    .profile-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .btn-action {
        padding: 6px 12px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 4px; cursor: pointer; font-size: 12px;
    }
    .btn-action:hover { border-color: var(--gold-dark); color: var(--gold); }
    .btn-action:disabled { opacity: .6; cursor: wait; }
    .btn-action.danger { color: var(--status-error); border-color: rgba(239,68,68,.4); }
    .btn-action.danger:hover { background: rgba(239,68,68,.1); }
    .btn-action.success { color: var(--status-success); border-color: rgba(16,185,129,.4); }

    .badge {
        display: inline-block; padding: 2px 8px; border-radius: 10px;
        font-size: 11px; font-weight: 500;
        background: var(--paimon-panel-light); color: var(--text-secondary);
    }
    .badge-default { background: rgba(255,180,80,.12); color: var(--gold); border: 1px solid rgba(255,180,80,.35); }
    .badge-thinking { background: rgba(110,198,255,.12); color: var(--star); }
    .badge-kind { background: var(--paimon-panel-light); color: var(--text-secondary); }

    /* 测连接结果条 */
    .test-result {
        margin-top: 8px; padding: 8px 12px; border-radius: 4px; font-size: 12px;
        white-space: pre-wrap; word-break: break-word;
    }
    .test-result.ok { background: rgba(16,185,129,.1); color: var(--status-success); border: 1px solid rgba(16,185,129,.25); }
    .test-result.err { background: rgba(239,68,68,.08); color: var(--status-error); border: 1px solid rgba(239,68,68,.25); }

    /* Modal 表单 */
    .modal-backdrop {
        display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1000;
        align-items: center; justify-content: center;
    }
    .modal-backdrop.active { display: flex; }
    .modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border); border-radius: 8px;
        max-width: 640px; width: 90%; max-height: 90vh; overflow: auto; padding: 24px;
    }
    .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .modal-header h3 { color: var(--gold); font-size: 18px; font-weight: 600; }
    .modal-close {
        background: transparent; border: none; color: var(--text-muted); font-size: 20px;
        cursor: pointer; padding: 0 4px;
    }
    .modal-close:hover { color: var(--text-primary); }

    .form-row { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
    .form-row label { font-size: 12px; color: var(--text-muted); }
    .form-row label .req { color: var(--status-error); margin-left: 2px; }
    .form-row input, .form-row select, .form-row textarea {
        width: 100%; padding: 8px 12px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 6px;
        color: var(--text-primary); font-size: 13px; font-family: inherit;
    }
    .form-row textarea { font-family: 'SF Mono', Monaco, Consolas, monospace; min-height: 64px; resize: vertical; }
    .form-row input:focus, .form-row select:focus, .form-row textarea:focus { outline: none; border-color: var(--gold); }
    .form-row .hint { color: var(--text-muted); font-size: 11px; line-height: 1.5; }
    .form-row-inline { display: flex; gap: 8px; align-items: center; }
    .form-row-inline input[type=checkbox] { width: auto; }
    .form-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .modal-footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }

    .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 14px; }

    /* Tab 切换（模型管理 / 路由配置）*/
    .tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--paimon-border); }
    .tab-btn {
        padding: 10px 20px; background: transparent; border: none; color: var(--text-muted);
        cursor: pointer; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active { color: var(--gold); border-bottom-color: var(--gold); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    .route-key { font-family: 'SF Mono', Monaco, Consolas, monospace; color: var(--text-primary); }
    .route-select {
        padding: 5px 8px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        color: var(--text-primary); font-size: 12px; min-width: 220px;
    }
    .route-save-flash {
        display: inline-block; margin-left: 8px; padding: 2px 8px;
        border-radius: 10px; font-size: 11px;
        background: rgba(16,185,129,.12); color: var(--status-success);
        opacity: 0; transition: opacity .2s;
    }
    .route-save-flash.shown { opacity: 1; }

    .default-hero {
        padding: 12px 16px; margin-bottom: 20px;
        background: rgba(255,180,80,.08); border: 1px solid rgba(255,180,80,.28);
        border-radius: 8px; font-size: 13px; color: var(--text-primary);
    }
    .default-hero strong { color: var(--gold); }

    /* ===== Provider 分组（profiles tab，外层按 anthropic/openai） ===== */
    .provider-section {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; overflow: hidden;
    }
    .provider-header {
        padding: 12px 18px; background: var(--paimon-panel-light);
        border-bottom: 1px solid var(--paimon-border);
        display: flex; align-items: center; gap: 10px;
        cursor: pointer; user-select: none;
    }
    .provider-header:hover { background: rgba(245,158,11,.08); }
    .provider-arrow { color: var(--gold); font-size: 11px; width: 12px; transition: transform .2s; }
    .provider-section.collapsed .provider-arrow { transform: rotate(-90deg); }
    .provider-section.collapsed .provider-header { border-bottom-color: transparent; }
    .provider-section.collapsed .provider-body { display: none; }
    .provider-name { font-size: 15px; font-weight: 600; color: var(--text-primary); }
    .provider-stat { font-size: 12px; color: var(--text-muted); margin-left: auto; }
    .provider-body { padding: 12px 18px; display: flex; flex-direction: column; gap: 10px; }

    /* profile 卡片紧凑化（取代旧 .profile-card grid 双栏） */
    .profile-card {
        display: grid; grid-template-columns: minmax(0, 1fr) auto;
        gap: 12px; align-items: center;
        padding: 12px 14px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 8px;
        transition: border-color .2s;
    }
    .profile-card:hover { border-color: var(--gold-dark); }
    .profile-card.is-default {
        border-color: var(--gold-dark);
        background: linear-gradient(90deg, rgba(245,158,11,.06), var(--paimon-bg) 30%);
    }
    .profile-info .name {
        font-size: 14px; color: var(--text-primary); font-weight: 500;
        margin-bottom: 4px;
        display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
    }
    .profile-info .star { color: var(--gold); font-size: 14px; }
    .profile-info .meta {
        font-size: 12px; color: var(--text-muted);
        display: flex; gap: 14px; flex-wrap: wrap;
    }
    .profile-info .meta span.mono { font-family: 'SF Mono', Monaco, Consolas, monospace; }
    .profile-info .notes {
        color: var(--text-muted); font-size: 12px;
        margin-top: 4px; font-style: italic;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .profile-actions { display: flex; gap: 6px; flex-wrap: nowrap; }

    /* ===== Category 大类分组（routes tab 顶层：派蒙/七神/四影） ===== */
    .category-section {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 12px; margin-bottom: 16px; overflow: hidden;
    }
    .category-header {
        padding: 14px 20px;
        background: linear-gradient(90deg, rgba(245,158,11,.10), var(--paimon-panel-light) 60%);
        border-bottom: 1px solid var(--paimon-border);
        display: flex; align-items: center; gap: 12px;
        cursor: pointer; user-select: none;
    }
    .category-header:hover { background: linear-gradient(90deg, rgba(245,158,11,.16), var(--paimon-panel-light) 60%); }
    .category-arrow { color: var(--gold); font-size: 12px; width: 12px; transition: transform .2s; }
    .category-section.collapsed .category-arrow { transform: rotate(-90deg); }
    .category-section.collapsed .category-body { display: none; }
    .category-name { font-size: 16px; font-weight: 600; color: var(--gold); }
    .category-stat { font-size: 12px; color: var(--text-muted); margin-left: auto; }
    .category-stat.stat-warn {
        color: var(--status-error);
        background: rgba(239,68,68,.10);
        padding: 2px 8px; border-radius: 10px;
        border: 1px solid rgba(239,68,68,.28);
        font-weight: 500;
    }
    .category-body {
        padding: 10px 14px 14px;
        display: flex; flex-direction: column; gap: 6px;
    }

    /* 紧凑单行（单 purpose 组件，直接挂 category 下） */
    .compact-row {
        display: grid;
        grid-template-columns: minmax(200px, 1.2fr) minmax(220px, 280px) auto 1fr;
        gap: 12px; align-items: center;
        padding: 8px 12px;
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-radius: 6px;
        transition: border-color .2s;
    }
    .compact-row:hover { border-color: var(--gold-dark); }
    .compact-name { font-size: 13px; color: var(--text-primary); font-weight: 500; }

    /* 未接入 router 的紧凑行（空执 / video_process / audio_process） */
    .compact-row.disabled { opacity: .6; cursor: not-allowed; background: rgba(239,68,68,.04); }
    .compact-row.disabled:hover { border-color: var(--paimon-border); }
    .compact-row.disabled .route-select { cursor: not-allowed; color: var(--text-muted); }
    .compact-name .tag-disabled-inline {
        font-size: 10px; padding: 1px 6px; border-radius: 8px;
        background: rgba(239,68,68,.12); color: var(--status-error);
        border: 1px solid rgba(239,68,68,.28);
        margin-left: 6px; font-weight: 500;
    }
    .purpose-hit.hit-disabled {
        color: var(--status-error); font-style: italic; opacity: .85;
    }

    /* shades 内嵌「七神」子段 */
    .archons-sub {
        margin-top: 10px;
        background: rgba(245,158,11,.05);
        border: 1px dashed rgba(245,158,11,.35);
        border-radius: 8px;
        padding: 10px 12px;
    }
    .archons-sub-header {
        font-size: 13px; font-weight: 600; color: var(--gold);
        margin-bottom: 8px;
    }
    .archons-sub-header .sub-stat {
        font-size: 11px; color: var(--text-muted); font-weight: 400; margin-left: 4px;
    }
    .archons-sub-body { display: flex; flex-direction: column; gap: 6px; }

    /* 空段占位（如天使主标题，暂无 LLM 调用点） */
    .empty-placeholder {
        padding: 16px 12px; text-align: center;
        color: var(--text-muted); font-size: 13px; font-style: italic;
        background: var(--paimon-bg);
        border: 1px dashed var(--paimon-border);
        border-radius: 6px;
    }

    /* ===== Component 嵌套段（多 purpose 才用；置于 category-body 内） ===== */
    .component-section {
        background: var(--paimon-bg); border: 1px solid var(--paimon-border);
        border-radius: 8px; overflow: hidden;
    }
    .component-header {
        padding: 12px 18px; background: var(--paimon-panel-light);
        border-bottom: 1px solid var(--paimon-border);
        display: flex; align-items: center; gap: 12px;
    }
    .component-toggle { cursor: pointer; user-select: none; display: flex; align-items: center; gap: 10px; }
    .component-toggle:hover .component-name { color: var(--gold); }
    .component-arrow { color: var(--gold); font-size: 11px; width: 12px; transition: transform .2s; }
    .component-section.collapsed .component-arrow { transform: rotate(-90deg); }
    .component-section.collapsed .component-header { border-bottom-color: transparent; }
    .component-section.collapsed .component-body { display: none; }
    .component-name { font-size: 15px; font-weight: 600; color: var(--text-primary); transition: color .2s; }
    .component-stat { font-size: 12px; color: var(--text-muted); }
    .component-group-control {
        margin-left: auto; display: flex; align-items: center; gap: 8px;
        font-size: 12px; color: var(--text-muted);
    }
    .component-body { padding: 8px 18px 14px; }

    /* purpose 行紧凑布局 */
    .purpose-row {
        display: grid;
        grid-template-columns: 200px 80px minmax(220px, 1fr) 90px 1fr;
        gap: 10px; align-items: center;
        padding: 6px 4px;
        border-bottom: 1px dashed var(--paimon-border);
    }
    .purpose-row:last-child { border-bottom: none; }
    .purpose-name {
        font-size: 13px; color: var(--text-primary);
        font-family: 'SF Mono', Monaco, Consolas, monospace;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .purpose-tag {
        font-size: 11px; padding: 2px 8px; border-radius: 10px;
        text-align: center; font-weight: 500;
    }
    .tag-inherit {
        background: var(--paimon-panel-light); color: var(--text-muted);
        border: 1px solid var(--paimon-border);
    }
    .tag-override {
        background: rgba(245,158,11,.15); color: var(--gold);
        border: 1px solid rgba(245,158,11,.35);
    }
    .purpose-action { display: flex; gap: 6px; }
    .btn-mini {
        padding: 3px 8px; background: transparent;
        border: 1px solid var(--paimon-border); border-radius: 4px;
        color: var(--text-muted); font-size: 11px; cursor: pointer;
    }
    .btn-mini:hover { border-color: var(--gold-dark); color: var(--gold); }
    .purpose-hit {
        font-size: 11px; color: var(--text-muted);
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .purpose-hit .hit-model { color: var(--text-secondary); font-family: 'SF Mono', Monaco, Consolas, monospace; }
    .purpose-hit .hit-src { color: var(--text-muted); }
    .purpose-hit .hit-none { color: var(--paimon-border); font-style: italic; }
"""
