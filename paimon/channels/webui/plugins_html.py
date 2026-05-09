"""空执 · 插件面板（skill 生态 + 授权管理 + 自进化提案）

按 docs/permissions.md：
  - Skill 生态：展示全部 skill 的敏感度、allowed_tools、敏感命中项
  - 永久授权：查看 + 撤销用户永久授权记录
"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)


PLUGINS_CSS = """
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
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    .data-table { width: 100%; border-collapse: collapse; }
    .data-table th, .data-table td {
        padding: 12px 16px; border-bottom: 1px solid var(--paimon-border);
        font-size: 14px; text-align: left; vertical-align: top;
    }
    .data-table th { color: var(--gold); font-weight: 600; font-size: 13px; }
    .data-table tbody tr:hover td { background: var(--paimon-panel); }

    .badge {
        display: inline-block; padding: 3px 8px; border-radius: 4px;
        font-size: 12px; font-weight: 500;
    }
    .badge-normal { background: rgba(110,198,255,.12); color: var(--star); }
    .badge-sensitive { background: rgba(245,158,11,.15); color: var(--status-warning); }
    .badge-allow { background: rgba(16,185,129,.15); color: var(--status-success); }
    .badge-deny { background: rgba(239,68,68,.15); color: var(--status-error); }

    .chip {
        display: inline-block; padding: 2px 8px; margin: 2px 4px 2px 0;
        border-radius: 10px; font-size: 12px;
        background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border);
    }
    .chip.sensitive { border-color: var(--status-warning); color: var(--status-warning); }

    .btn-revoke {
        padding: 4px 12px; background: transparent; border: 1px solid var(--status-error);
        color: var(--status-error); border-radius: 4px; cursor: pointer; font-size: 12px;
    }
    .btn-revoke:hover { background: rgba(239,68,68,.1); }

    .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 14px; }
    .desc { color: var(--text-muted); font-size: 12px; margin-top: 4px; line-height: 1.5; }
    .mono { font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 12px; color: var(--text-secondary); }

    /* tab badge（pending 数量提示） */
    .tab-badge {
        display: inline-block; min-width: 18px; padding: 0 6px; margin-left: 6px;
        border-radius: 9px; font-size: 11px; line-height: 18px; text-align: center;
        background: var(--status-warning); color: #1a1a1a; font-weight: 600;
    }
    .tab-badge.zero { background: var(--paimon-panel-light); color: var(--text-muted); }

    /* sub-tab 行（pending / approved / rejected / applied 切换）*/
    .sub-tabs { display: flex; gap: 8px; margin-bottom: 16px; }
    .sub-tab {
        padding: 6px 14px; border: 1px solid var(--paimon-border); border-radius: 16px;
        background: transparent; color: var(--text-muted); cursor: pointer; font-size: 12px;
    }
    .sub-tab:hover { border-color: var(--gold-dark); color: var(--text-secondary); }
    .sub-tab.active { background: var(--gold); color: #1a1a1a; border-color: var(--gold); }

    /* 提案 card */
    .prop-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 8px; margin-bottom: 12px; overflow: hidden;
        transition: border-color .15s;
    }
    .prop-card:hover { border-color: var(--gold-dark); }
    .prop-head {
        display: flex; align-items: center; padding: 14px 16px; gap: 12px;
        cursor: pointer; user-select: none;
    }
    .prop-head .arrow {
        color: var(--text-muted); font-size: 12px; transition: transform .15s;
        transform: rotate(90deg);  /* 默认展开 → 朝下 */
    }
    .prop-name { font-weight: 600; color: var(--text-primary); font-size: 14px; }
    .prop-meta { flex: 1; min-width: 0; }
    .prop-desc { color: var(--text-muted); font-size: 12px; margin-top: 3px;
                 white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .prop-badges { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
    .prop-actions {
        padding: 0 16px 14px 36px;  /* 跟 prop-name 对齐 */
        display: flex; gap: 8px;
    }

    .badge-kind-new { background: rgba(110,198,255,.12); color: var(--star); }
    .badge-kind-improve { background: rgba(168,85,247,.15); color: #c084fc; }

    .badge-status-pending { background: rgba(245,158,11,.15); color: var(--status-warning); }
    .badge-status-approved { background: rgba(16,185,129,.15); color: var(--status-success); }
    .badge-status-rejected { background: rgba(115,115,115,.15); color: var(--text-muted); }
    .badge-status-applied { background: rgba(110,198,255,.18); color: var(--star); }

    .badge-verdict-pass { background: rgba(16,185,129,.12); color: var(--status-success); }
    .badge-verdict-revise { background: rgba(245,158,11,.15); color: var(--status-warning); }
    .badge-verdict-reject { background: rgba(239,68,68,.15); color: var(--status-error); }
    .badge-verdict-empty { background: var(--paimon-panel-light); color: var(--text-muted); }

    /* 默认展开（提案信息密度高，折叠会埋掉关键信息）；点 head 可折叠 */
    .prop-body { display: block; padding: 0 16px 16px 36px; border-top: 1px dashed var(--paimon-border); padding-top: 14px; }
    .prop-card.collapsed .prop-body { display: none; }
    .prop-card.collapsed .arrow { transform: rotate(0deg); }
    .prop-section { margin-bottom: 12px; }
    .prop-section-label {
        font-size: 11px; color: var(--gold); text-transform: uppercase;
        letter-spacing: .5px; margin-bottom: 4px; font-weight: 600;
    }
    .prop-section-content { font-size: 13px; color: var(--text-secondary); line-height: 1.6; }
    .prop-section-content.code {
        background: var(--paimon-panel-light); padding: 10px 12px; border-radius: 4px;
        font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 12px;
        white-space: pre-wrap; word-break: break-word; max-height: 240px; overflow-y: auto;
    }

    .btn-approve, .btn-reject, .btn-revise, .btn-delete-prop {
        padding: 5px 14px; border-radius: 4px; cursor: pointer; font-size: 12px;
        border: 1px solid; background: transparent;
    }
    .btn-approve { border-color: var(--status-success); color: var(--status-success); }
    .btn-approve:hover:not(:disabled) { background: rgba(16,185,129,.1); }
    .btn-approve:disabled { opacity: .35; cursor: not-allowed; }
    .btn-reject { border-color: var(--status-warning); color: var(--status-warning); }
    .btn-reject:hover { background: rgba(245,158,11,.1); }
    .btn-revise { border-color: var(--gold-dark); color: var(--gold); }
    .btn-revise:hover:not(:disabled) { background: rgba(245,200,80,.1); }
    .btn-revise:disabled { opacity: .35; cursor: not-allowed; }
    .btn-reject:disabled { opacity: .35; cursor: not-allowed; }
    .btn-delete-prop { border-color: var(--status-error); color: var(--status-error); }
    .btn-delete-prop:hover { background: rgba(239,68,68,.1); }

    /* 重写中状态条 */
    .revising-banner {
        display: flex; align-items: center; gap: 10px;
        padding: 8px 14px; margin-bottom: 12px;
        background: rgba(245,200,80,.08); border: 1px solid rgba(245,200,80,.3);
        border-radius: 6px;
        color: var(--gold); font-size: 12px;
    }
    .revising-banner .pulse {
        width: 8px; height: 8px; border-radius: 50%;
        background: var(--gold);
        animation: revising-pulse 1.4s ease-in-out infinite;
    }
    @keyframes revising-pulse {
        0%, 100% { opacity: .3; transform: scale(1); }
        50% { opacity: 1; transform: scale(1.4); }
    }

    /* 提建议改写 modal —— 风格对齐 /knowledge 的 form modal */
    .modal-backdrop {
        display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1000;
        align-items: center; justify-content: center;
    }
    .modal-backdrop.active { display: flex; }
    .modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 8px; max-width: 640px; width: 90%;
        max-height: 85vh; overflow: auto; padding: 24px;
    }
    .modal-header {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 16px; padding-bottom: 12px;
        border-bottom: 1px solid var(--paimon-border);
    }
    .modal-header h3 { color: var(--gold); font-size: 18px; font-weight: 600; }
    .modal-header .modal-sub {
        font-size: 12px; color: var(--text-muted); margin-top: 4px;
        font-family: 'SF Mono', Monaco, Consolas, monospace;
    }
    .modal-close {
        background: transparent; border: none; color: var(--text-muted); font-size: 22px;
        cursor: pointer; padding: 0 6px;
    }
    .modal-close:hover { color: var(--text-primary); }
    .form-body { padding: 8px 0; display: flex; flex-direction: column; gap: 14px; }
    .form-field { display: flex; flex-direction: column; gap: 4px; }
    .form-field label { font-size: 12px; color: var(--text-muted); }
    .form-field textarea {
        padding: 10px 12px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        color: var(--text-primary); font-size: 13px;
        font-family: inherit; line-height: 1.6;
        min-height: 140px; resize: vertical;
    }
    .form-field textarea:focus { outline: none; border-color: var(--gold); }
    .form-field .hint { font-size: 11px; color: var(--text-muted); font-style: italic; }
    .form-tips {
        background: var(--paimon-panel-light); border: 1px solid var(--paimon-border);
        border-radius: 4px; padding: 10px 12px;
        font-size: 12px; color: var(--text-secondary); line-height: 1.7;
    }
    .form-tips .tip-label { color: var(--gold); font-weight: 600; }
    .form-tips ul { margin: 4px 0 0 18px; }
    .form-actions {
        display: flex; justify-content: flex-end; gap: 10px;
        margin-top: 16px; padding-top: 12px;
        border-top: 1px solid var(--paimon-border);
    }
    .btn-cancel {
        padding: 6px 18px; background: transparent; border: 1px solid var(--paimon-border);
        color: var(--text-secondary); border-radius: 4px; cursor: pointer; font-size: 13px;
    }
    .btn-cancel:hover { border-color: var(--text-secondary); color: var(--text-primary); }
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
"""


PLUGINS_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>🔌 插件</h1>
                <div class="sub">Skill 生态管理 + 用户授权</div>
            </div>
            <button class="refresh-btn" onclick="refreshAll()">刷新</button>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('skills',this)">Skill 生态</button>
            <button class="tab-btn" onclick="switchTab('authz',this)">永久授权</button>
            <button class="tab-btn" onclick="switchTab('proposals',this)">
                自进化提案<span id="propBadge" class="tab-badge zero">0</span>
            </button>
        </div>

        <div id="skills" class="tab-panel active">
            <div id="skillsEl"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="authz" class="tab-panel">
            <div id="authzEl"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="proposals" class="tab-panel">
            <div class="sub-tabs" id="propSubTabs">
                <button class="sub-tab active" data-status="pending" onclick="switchProp('pending',this)">待审 <span id="propCntPending"></span></button>
                <button class="sub-tab" data-status="approved" onclick="switchProp('approved',this)">已同意 <span id="propCntApproved"></span></button>
                <button class="sub-tab" data-status="applied" onclick="switchProp('applied',this)">已落盘 <span id="propCntApplied"></span></button>
                <button class="sub-tab" data-status="rejected" onclick="switchProp('rejected',this)">已拒 <span id="propCntRejected"></span></button>
            </div>
            <div id="proposalsEl"><div class="empty-state">加载中...</div></div>
        </div>
    </div>

    <!-- 提建议改写 modal -->
    <div id="reviseModal" class="modal-backdrop" onclick="closeReviseModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal-header">
                <div>
                    <h3>提建议改写草案</h3>
                    <div class="modal-sub" id="reviseModalSub"></div>
                </div>
                <button class="modal-close" onclick="closeReviseModal()">×</button>
            </div>
            <div class="form-body">
                <div class="form-field">
                    <label for="reviseFeedback">你的建议（可留空仅触发重审）</label>
                    <textarea id="reviseFeedback" placeholder="例如：&#10;- 应该支持非米哈游游戏，比如英雄联盟、永劫无间&#10;- 步骤 3 写得不够具体，要展开下数据来源&#10;- triggers 描述太含糊，应该列出具体场景&#10;&#10;留空 → 退化为「按原内容重审」（适合挽救 verdict 不准的提案）"></textarea>
                </div>
                <div class="form-tips">
                    <span class="tip-label">提交后会发生什么：</span>
                    <ul>
                        <li>生执根据你的建议重写完整草案（in-place 覆盖 system_prompt / triggers / 工具列表）</li>
                        <li>死执自动重审一道，verdict 刷新</li>
                        <li>revision_count +1，原建议留痕显示在卡片上</li>
                    </ul>
                </div>
            </div>
            <div class="form-actions">
                <button class="btn-cancel" onclick="closeReviseModal()">取消</button>
                <button class="btn-save" id="reviseSubmitBtn" onclick="submitRevise()">提交重写</button>
            </div>
            <div id="reviseError" class="form-error"></div>
        </div>
    </div>
"""


PLUGINS_SCRIPT = """
    <script>
    (function(){
        function esc(s){return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}
        function fmtTime(ts){
            if(!ts||ts<=0)return'-';
            var d=new Date(ts*1000);
            return (d.getFullYear())+'-'+(d.getMonth()+1).toString().padStart(2,'0')+'-'+
                d.getDate().toString().padStart(2,'0')+' '+
                d.getHours().toString().padStart(2,'0')+':'+
                d.getMinutes().toString().padStart(2,'0');
        }

        window.switchTab = function(id, btn){
            document.querySelectorAll('.tab-btn').forEach(function(t){t.classList.remove('active');});
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            if(btn) btn.classList.add('active');
            var el = document.getElementById(id);
            if(el) el.classList.add('active');
        };

        function renderSkills(data){
            var el = document.getElementById('skillsEl');
            var skills = data.skills || [];
            if(skills.length === 0){
                el.innerHTML = '<div class="empty-state">尚未加载任何 Skill</div>';
                return;
            }
            var rows = skills.map(function(s){
                var senBadge = s.sensitivity === 'sensitive'
                    ? '<span class="badge badge-sensitive">敏感</span>'
                    : '<span class="badge badge-normal">普通</span>';
                var tools = (s.allowed_tools || []).map(function(t){
                    var isSen = (s.sensitive_tools || []).indexOf(t) !== -1;
                    return '<span class="chip'+(isSen?' sensitive':'')+'">'+esc(t)+'</span>';
                }).join('');
                if(!tools) tools = '<span class="desc">（未声明）</span>';
                var authzBadge = '';
                if(s.authz === 'permanent_allow'){
                    authzBadge = '<span class="badge badge-allow">已永久放行</span>';
                } else if(s.authz === 'permanent_deny'){
                    authzBadge = '<span class="badge badge-deny">已永久禁止</span>';
                }
                return ''
                    +'<tr>'
                    +'<td><strong>'+esc(s.name)+'</strong>'
                        +'<div class="desc">'+esc(s.description || '')+'</div></td>'
                    +'<td>'+senBadge+' '+authzBadge+'</td>'
                    +'<td>'+tools+'</td>'
                    +'</tr>';
            }).join('');
            el.innerHTML = ''
                +'<table class="data-table">'
                +'<thead><tr>'
                +'<th>Skill</th><th>敏感度 / 授权</th><th>工具</th>'
                +'</tr></thead>'
                +'<tbody>'+rows+'</tbody>'
                +'</table>';
        }

        function renderAuthz(data){
            var el = document.getElementById('authzEl');
            var records = data.records || [];
            if(records.length === 0){
                el.innerHTML = '<div class="empty-state">暂无永久授权记录<br><span class="desc">当敏感 skill 被询问且用户选择「永久放行/禁止」时，记录会出现在这里</span></div>';
                return;
            }
            var rows = records.map(function(r){
                var decBadge = r.decision === 'permanent_allow'
                    ? '<span class="badge badge-allow">永久放行</span>'
                    : '<span class="badge badge-deny">永久禁止</span>';
                return ''
                    +'<tr data-type="'+esc(r.subject_type)+'" data-id="'+esc(r.subject_id)+'">'
                    +'<td><span class="mono">'+esc(r.subject_type)+'</span> · <strong>'+esc(r.subject_id)+'</strong></td>'
                    +'<td>'+decBadge+'</td>'
                    +'<td class="mono">'+fmtTime(r.updated_at)+'</td>'
                    +'<td class="desc">'+esc(r.reason || '-')+'</td>'
                    +'<td><button class="btn-revoke" onclick="revoke(\\''+esc(r.subject_type)+'\\',\\''+esc(r.subject_id)+'\\')">撤销</button></td>'
                    +'</tr>';
            }).join('');
            el.innerHTML = ''
                +'<table class="data-table">'
                +'<thead><tr>'
                +'<th>主体</th><th>决策</th><th>更新时间</th><th>原因</th><th>操作</th>'
                +'</tr></thead>'
                +'<tbody>'+rows+'</tbody>'
                +'</table>';
        }

        window.revoke = async function(subject_type, subject_id){
            if(!confirm('撤销 '+subject_type+'/'+subject_id+' 的永久授权？\\n下次调用时会重新询问。')) return;
            try {
                var resp = await fetch('/api/plugins/authz/revoke', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({subject_type: subject_type, subject_id: subject_id}),
                });
                var data = await resp.json();
                if(data.ok){
                    loadAuthz();
                    loadSkills();
                } else {
                    alert('撤销失败: ' + (data.error || '未知错误'));
                }
            } catch(e){
                alert('撤销失败: ' + e.message);
            }
        };

        async function loadSkills(){
            try {
                var r = await fetch('/api/plugins/skills');
                var d = await r.json();
                renderSkills(d);
            } catch(e){
                document.getElementById('skillsEl').innerHTML =
                    '<div class="empty-state">加载失败: '+esc(e.message)+'</div>';
            }
        }

        async function loadAuthz(){
            try {
                var r = await fetch('/api/plugins/authz');
                var d = await r.json();
                renderAuthz(d);
            } catch(e){
                document.getElementById('authzEl').innerHTML =
                    '<div class="empty-state">加载失败: '+esc(e.message)+'</div>';
            }
        }

        // ─── 自进化提案 ───
        function _initPropStatus(){
            // URL 含 ?status=X (X ∈ pending/approved/applied/rejected) 用作初始 sub-tab
            var m = (location.search || '').match(/[?&]status=(pending|approved|applied|rejected)\b/);
            return m ? m[1] : 'pending';
        }
        var _propCurrentStatus = _initPropStatus();

        function badgeKind(kind){
            if(kind === 'improve') return '<span class="badge badge-kind-improve">改进</span>';
            return '<span class="badge badge-kind-new">新建</span>';
        }
        function badgeStatus(status){
            var label = {pending:'待审', approved:'已同意', rejected:'已拒', applied:'已落盘'}[status] || status;
            return '<span class="badge badge-status-'+esc(status)+'">'+label+'</span>';
        }
        function badgeVerdict(v){
            if(v === 'pass') return '<span class="badge badge-verdict-pass">死执·通过</span>';
            if(v === 'needs_revise') return '<span class="badge badge-verdict-revise">死执·要修</span>';
            if(v === 'reject') return '<span class="badge badge-verdict-reject">死执·拒</span>';
            return '<span class="badge badge-verdict-empty">死执·待审</span>';
        }

        function renderProposals(list, status){
            var el = document.getElementById('proposalsEl');
            if(!list || list.length === 0){
                var msg = {
                    pending: '当前没有待审的 skill 提案<br><span class="desc">四影 propose 阶段产出后会落到这里等你审</span>',
                    approved: '没有已同意待落盘的提案',
                    applied: '尚无落盘的自进化 skill',
                    rejected: '没有被拒提案'
                }[status] || '空';
                el.innerHTML = '<div class="empty-state">'+msg+'</div>';
                return;
            }
            var html = list.map(function(p){
                var verdictBadge = badgeVerdict(p.review_verdict);
                var isRevising = !!p.revising_at;
                // 重写中：同意 / 提建议 → 锁；拒绝 → 仍可点（用户中止意图）；删除 → 不冲突
                var canApprove = (p.status === 'pending' && p.review_verdict !== 'needs_revise' && p.review_verdict !== 'reject' && !isRevising);
                var canReject = (p.status === 'pending');
                var canRevise = (p.status === 'pending' && !isRevising);
                var canDelete = (p.status === 'rejected');

                var tools = (p.allowed_tools || []).map(function(t){
                    return '<span class="chip">'+esc(t)+'</span>';
                }).join('');
                if(!tools) tools = '<span class="desc">（未声明工具）</span>';

                var actionBtns = '';
                if(canApprove){
                    actionBtns += '<button class="btn-approve" onclick="event.stopPropagation();approveProp(\\''+esc(p.id)+'\\')">同意</button>';
                } else if(p.status === 'pending') {
                    var reason = isRevising
                        ? '正在生执重写中，等重写完才能 approve'
                        : (p.review_verdict === 'needs_revise'
                            ? '死执质量审建议修订；需要先重新产新版'
                            : '死执质量审已直拒');
                    actionBtns += '<button class="btn-approve" disabled title="'+esc(reason)+'">同意</button>';
                }
                if(p.status === 'pending'){
                    var reviseLabel = (p.review_verdict === 'needs_revise')
                        ? '提建议改写 / 重审'
                        : '提建议改写';
                    if(canRevise){
                        actionBtns += '<button class="btn-revise" onclick="event.stopPropagation();reviseProp(\\''+esc(p.id)+'\\')">'+reviseLabel+'</button>';
                    } else {
                        actionBtns += '<button class="btn-revise" disabled title="正在重写中，等链路完成">'+reviseLabel+'</button>';
                    }
                }
                if(canReject){
                    actionBtns += '<button class="btn-reject" onclick="event.stopPropagation();rejectProp(\\''+esc(p.id)+'\\')">拒绝</button>';
                }
                if(canDelete){
                    actionBtns += '<button class="btn-delete-prop" onclick="event.stopPropagation();deleteProp(\\''+esc(p.id)+'\\')">删除</button>';
                }

                var kindLine = p.kind === 'improve' && p.target_skill
                    ? '改进：<span class="mono">'+esc(p.target_skill)+'</span>'
                    : '';

                var reviewNotes = p.review_notes
                    ? '<div class="prop-section"><div class="prop-section-label">死执评语</div><div class="prop-section-content">'+esc(p.review_notes)+'</div></div>'
                    : '';
                var decisionNotes = p.decision_notes
                    ? '<div class="prop-section"><div class="prop-section-label">用户决策理由</div><div class="prop-section-content">'+esc(p.decision_notes)+'</div></div>'
                    : '';
                var userFeedback = p.user_feedback
                    ? '<div class="prop-section"><div class="prop-section-label">用户上次建议（已并入新版）</div><div class="prop-section-content">'+esc(p.user_feedback)+'</div></div>'
                    : '';
                var revisionMark = (p.revision_count && p.revision_count > 0)
                    ? ' <span class="desc" style="font-size:11px;">· 已重写 '+p.revision_count+' 次</span>'
                    : '';

                var revisingBanner = isRevising
                    ? '<div class="revising-banner"><span class="pulse"></span>'
                      + '生执正在按建议重写 → 死执重审中，完成立即解锁'
                      + '</div>'
                    : '';

                return ''
                    +'<div class="prop-card" id="card-'+esc(p.id)+'">'
                    +'  <div class="prop-head" onclick="toggleProp(\\''+esc(p.id)+'\\')">'
                    +'    <span class="arrow">▶</span>'
                    +'    <div class="prop-meta">'
                    +'      <span class="prop-name">'+esc(p.name)+'</span>'
                    +(kindLine ? ' <span class="desc" style="display:inline-block;margin-left:8px;">'+kindLine+'</span>' : '')
                    + revisionMark
                    +'      <div class="prop-desc">'+esc(p.description || '（无描述）')+'</div>'
                    +'    </div>'
                    +'    <div class="prop-badges">'
                    +       badgeKind(p.kind)+' '+verdictBadge+' '+badgeStatus(p.status)
                    +'    </div>'
                    +'  </div>'
                    +'  <div class="prop-body">'
                    +    revisingBanner
                    +'    <div class="prop-section">'
                    +'      <div class="prop-section-label">触发线索</div>'
                    +'      <div class="prop-section-content">'+esc(p.triggers || '（未填）')+'</div>'
                    +'    </div>'
                    +'    <div class="prop-section">'
                    +'      <div class="prop-section-label">允许工具</div>'
                    +'      <div class="prop-section-content">'+tools+'</div>'
                    +'    </div>'
                    +'    <div class="prop-section">'
                    +'      <div class="prop-section-label">提议理由（rationale）</div>'
                    +'      <div class="prop-section-content">'+esc(p.rationale || '（未填）')+'</div>'
                    +'    </div>'
                    +    reviewNotes
                    +    decisionNotes
                    +    userFeedback
                    +'    <div class="prop-section">'
                    +'      <div class="prop-section-label">SKILL 草案（system_prompt）</div>'
                    +'      <div class="prop-section-content code">'+esc(p.system_prompt || '（空）')+'</div>'
                    +'    </div>'
                    +'    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px;">'
                    +       actionBtns
                    +'    </div>'
                    +'  </div>'
                    +'</div>';
            }).join('');
            el.innerHTML = html;
        }

        window.toggleProp = function(propId){
            var card = document.getElementById('card-' + propId);
            if(card) card.classList.toggle('collapsed');
        };

        window.switchProp = function(status, btn){
            _propCurrentStatus = status;
            document.querySelectorAll('#propSubTabs .sub-tab').forEach(function(t){t.classList.remove('active');});
            if(btn) btn.classList.add('active');
            loadProposals();
        };

        var _revisingPollTimer = null;

        function _hasRevising(list){
            if(!list) return false;
            for(var i = 0; i < list.length; i++){
                if(list[i].revising_at) return true;
            }
            return false;
        }

        function _ensureRevisingPoll(active){
            // 任意提案 revising 中 → 500ms 短间隔 polling，几乎实时；解锁后立即停 timer
            // 链路 ~50s 内完成，期间 ~100 次请求；切走 tab 暂停（节省请求）
            if(active && !_revisingPollTimer){
                _revisingPollTimer = setInterval(function(){
                    var panel = document.getElementById('proposals');
                    if(panel && panel.classList.contains('active')){
                        loadProposals();
                    }
                }, 500);
            } else if(!active && _revisingPollTimer){
                clearInterval(_revisingPollTimer);
                _revisingPollTimer = null;
            }
        }

        async function loadProposals(){
            try {
                var r = await fetch('/api/plugins/proposals?status=' + encodeURIComponent(_propCurrentStatus));
                var d = await r.json();
                renderProposals(d.proposals, _propCurrentStatus);
                // 角标 + sub-tab 计数
                var counts = d.counts || {};
                var pendCnt = counts.pending || 0;
                var badge = document.getElementById('propBadge');
                if(badge){
                    badge.textContent = pendCnt;
                    if(pendCnt === 0) badge.classList.add('zero');
                    else badge.classList.remove('zero');
                }
                function setCnt(id, n){
                    var el = document.getElementById(id);
                    if(el) el.textContent = n > 0 ? '('+n+')' : '';
                }
                setCnt('propCntPending', counts.pending || 0);
                setCnt('propCntApproved', counts.approved || 0);
                setCnt('propCntApplied', counts.applied || 0);
                setCnt('propCntRejected', counts.rejected || 0);
                // 检测是否有提案处于 revising 状态，决定是否需要 polling 实时刷新
                _ensureRevisingPoll(_hasRevising(d.proposals));
            } catch(e){
                document.getElementById('proposalsEl').innerHTML =
                    '<div class="empty-state">加载失败: '+esc(e.message)+'</div>';
            }
        }

        window.approveProp = async function(propId){
            if(!confirm('同意此提案？同意后空执会落盘到 skills/ 并注册。')) return;
            try {
                var r = await fetch('/api/plugins/proposals/'+propId+'/approve', {method:'POST'});
                var d = await r.json();
                if(d.ok){ loadProposals(); } else { alert('同意失败: ' + (d.error || '未知')); }
            } catch(e){ alert('同意失败: ' + e.message); }
        };

        window.rejectProp = async function(propId){
            var notes = prompt('拒绝理由（可选）：');
            if(notes === null) return;  // 取消
            try {
                var r = await fetch('/api/plugins/proposals/'+propId+'/reject', {
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({notes: notes}),
                });
                var d = await r.json();
                if(d.ok){ loadProposals(); } else { alert('拒绝失败: ' + (d.error || '未知')); }
            } catch(e){ alert('拒绝失败: ' + e.message); }
        };

        var _reviseTargetProp = null;

        window.reviseProp = function(propId){
            _reviseTargetProp = propId;
            // 找到提案信息填到副标题，方便用户确认
            var card = document.getElementById('card-' + propId);
            var nameEl = card ? card.querySelector('.prop-name') : null;
            var name = nameEl ? nameEl.textContent : propId;
            document.getElementById('reviseModalSub').textContent =
                'prop_id=' + propId + ' · ' + name;
            document.getElementById('reviseFeedback').value = '';
            document.getElementById('reviseError').classList.remove('active');
            var btn = document.getElementById('reviseSubmitBtn');
            btn.disabled = false;
            btn.textContent = '提交重写';
            document.getElementById('reviseModal').classList.add('active');
            // 自动 focus 到 textarea，体验更连贯
            setTimeout(function(){
                document.getElementById('reviseFeedback').focus();
            }, 50);
        };

        window.closeReviseModal = function(e){
            if(e && e.target.id !== 'reviseModal') return;
            document.getElementById('reviseModal').classList.remove('active');
            _reviseTargetProp = null;
        };

        window.submitRevise = async function(){
            if(!_reviseTargetProp) return;
            var feedback = document.getElementById('reviseFeedback').value;
            var btn = document.getElementById('reviseSubmitBtn');
            var errEl = document.getElementById('reviseError');
            errEl.classList.remove('active');
            btn.disabled = true;
            btn.textContent = '提交中...';
            try {
                var r = await fetch('/api/plugins/proposals/'+_reviseTargetProp+'/revise', {
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({feedback: feedback}),
                });
                var d = await r.json();
                if(d.ok){
                    closeReviseModal();
                    setTimeout(loadProposals, 500);
                } else {
                    errEl.textContent = '提交失败: ' + (d.error || '未知');
                    errEl.classList.add('active');
                    btn.disabled = false;
                    btn.textContent = '提交重写';
                }
            } catch(e){
                errEl.textContent = '提交失败: ' + e.message;
                errEl.classList.add('active');
                btn.disabled = false;
                btn.textContent = '提交重写';
            }
        };

        window.deleteProp = async function(propId){
            if(!confirm('彻底删除此提案？仅 rejected 提案可删。')) return;
            try {
                var r = await fetch('/api/plugins/proposals/'+propId+'/delete', {method:'POST'});
                var d = await r.json();
                if(d.ok){ loadProposals(); } else { alert('删除失败: ' + (d.error || '未知')); }
            } catch(e){ alert('删除失败: ' + e.message); }
        };

        window.refreshAll = function(){
            loadSkills();
            loadAuthz();
            loadProposals();
        };

        function applyHashRoute(){
            // /plugins#proposals|skills|authz 直达对应 tab；不识别则保持默认
            var h = (location.hash || '').replace('#','');
            if(!h) return;
            var btns = document.querySelectorAll('.tab-btn');
            for(var i=0; i<btns.length; i++){
                var oc = btns[i].getAttribute('onclick') || '';
                if(oc.indexOf("'"+h+"'") !== -1){
                    switchTab(h, btns[i]);
                    return;
                }
            }
        }

        window.onload = function(){
            // URL 带 status=X 时 sync sub-tab active 状态
            var btns = document.querySelectorAll('#propSubTabs .sub-tab');
            for(var i=0; i<btns.length; i++){
                var s = btns[i].getAttribute('data-status');
                if(s === _propCurrentStatus){
                    btns[i].classList.add('active');
                } else {
                    btns[i].classList.remove('active');
                }
            }
            refreshAll();
            applyHashRoute();
        };
        window.addEventListener('hashchange', applyHashRoute);
    })();
    </script>
"""


def build_plugins_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>插件</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + PLUGINS_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("plugins")
        + PLUGINS_BODY
        + PLUGINS_SCRIPT
        + """</body>
</html>"""
    )
