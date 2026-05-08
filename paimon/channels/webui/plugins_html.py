"""冰神 · 插件面板（含授权管理）

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

    .btn-approve, .btn-reject, .btn-delete-prop {
        padding: 5px 14px; border-radius: 4px; cursor: pointer; font-size: 12px;
        border: 1px solid; background: transparent;
    }
    .btn-approve { border-color: var(--status-success); color: var(--status-success); }
    .btn-approve:hover:not(:disabled) { background: rgba(16,185,129,.1); }
    .btn-approve:disabled { opacity: .35; cursor: not-allowed; }
    .btn-reject { border-color: var(--status-warning); color: var(--status-warning); }
    .btn-reject:hover { background: rgba(245,158,11,.1); }
    .btn-delete-prop { border-color: var(--status-error); color: var(--status-error); }
    .btn-delete-prop:hover { background: rgba(239,68,68,.1); }
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
                var canApprove = (p.status === 'pending' && p.review_verdict !== 'needs_revise' && p.review_verdict !== 'reject');
                var canReject = (p.status === 'pending');
                var canDelete = (p.status === 'rejected');

                var tools = (p.allowed_tools || []).map(function(t){
                    return '<span class="chip">'+esc(t)+'</span>';
                }).join('');
                if(!tools) tools = '<span class="desc">（未声明工具）</span>';

                var actionBtns = '';
                if(canApprove){
                    actionBtns += '<button class="btn-approve" onclick="event.stopPropagation();approveProp(\\''+esc(p.id)+'\\')">同意</button>';
                } else if(p.status === 'pending') {
                    var reason = p.review_verdict === 'needs_revise'
                        ? '死执质量审建议修订；需要先重新产新版'
                        : '死执质量审已直拒';
                    actionBtns += '<button class="btn-approve" disabled title="'+esc(reason)+'">同意</button>';
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

                return ''
                    +'<div class="prop-card" id="card-'+esc(p.id)+'">'
                    +'  <div class="prop-head" onclick="toggleProp(\\''+esc(p.id)+'\\')">'
                    +'    <span class="arrow">▶</span>'
                    +'    <div class="prop-meta">'
                    +'      <span class="prop-name">'+esc(p.name)+'</span>'
                    +(kindLine ? ' <span class="desc" style="display:inline-block;margin-left:8px;">'+kindLine+'</span>' : '')
                    +'      <div class="prop-desc">'+esc(p.description || '（无描述）')+'</div>'
                    +'    </div>'
                    +'    <div class="prop-badges">'
                    +       badgeKind(p.kind)+' '+verdictBadge+' '+badgeStatus(p.status)
                    +'    </div>'
                    +'  </div>'
                    +'  <div class="prop-body">'
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
            } catch(e){
                document.getElementById('proposalsEl').innerHTML =
                    '<div class="empty-state">加载失败: '+esc(e.message)+'</div>';
            }
        }

        window.approveProp = async function(propId){
            if(!confirm('同意此提案？同意后冰神会落盘到 .claude/skills/ 并注册。')) return;
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
