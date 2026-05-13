/* plugins 页脚本 — Skill 生态 + 永久授权 + 自进化提案管理 */

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
                    +'<td><button class="btn-revoke" onclick="revoke(\''+esc(r.subject_type)+'\',\''+esc(r.subject_id)+'\')">撤销</button></td>'
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
            var ok = await window.pmModal.confirm({
                title: '撤销永久授权',
                message: '撤销 '+subject_type+'/'+subject_id+' 的永久授权？下次调用时会重新询问。',
                confirmText: '撤销',
                danger: true,
            });
            if(!ok) return;
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
                    window.pmToast.success('已撤销');
                } else {
                    window.pmToast.error('撤销失败: ' + (data.error || '未知错误'));
                }
            } catch(e){
                window.pmToast.error('撤销失败: ' + e.message);
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
            var m = (location.search || '').match(/[?&]status=(pending|approved|applied|rejected)/);
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
            if(v === 'pass') return '<span class="badge badge-verdict-pass">审查·通过</span>';
            if(v === 'needs_revise') return '<span class="badge badge-verdict-revise">审查·要修</span>';
            if(v === 'reject') return '<span class="badge badge-verdict-reject">审查·拒</span>';
            return '<span class="badge badge-verdict-empty">审查·待审</span>';
        }

        function renderProposals(list, status){
            var el = document.getElementById('proposalsEl');
            if(!list || list.length === 0){
                var msg = {
                    pending: '当前没有待审的 skill 提案<br><span class="desc">自进化 propose 阶段产出后会落到这里等你审</span>',
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
                    actionBtns += '<button class="btn-approve" onclick="event.stopPropagation();approveProp(\''+esc(p.id)+'\')">同意</button>';
                } else if(p.status === 'pending') {
                    var reason = isRevising
                        ? '正在重写中，等重写完才能 approve'
                        : (p.review_verdict === 'needs_revise'
                            ? '审查建议修订；需要先重新产新版'
                            : '审查已直拒');
                    actionBtns += '<button class="btn-approve" disabled title="'+esc(reason)+'">同意</button>';
                }
                if(p.status === 'pending'){
                    var reviseLabel = (p.review_verdict === 'needs_revise')
                        ? '提建议改写 / 重审'
                        : '提建议改写';
                    if(canRevise){
                        actionBtns += '<button class="btn-revise" onclick="event.stopPropagation();reviseProp(\''+esc(p.id)+'\')">'+reviseLabel+'</button>';
                    } else {
                        actionBtns += '<button class="btn-revise" disabled title="正在重写中，等链路完成">'+reviseLabel+'</button>';
                    }
                }
                if(canReject){
                    actionBtns += '<button class="btn-reject" onclick="event.stopPropagation();rejectProp(\''+esc(p.id)+'\')">拒绝</button>';
                }
                if(canDelete){
                    actionBtns += '<button class="btn-delete-prop" onclick="event.stopPropagation();deleteProp(\''+esc(p.id)+'\')">删除</button>';
                }

                var kindLine = p.kind === 'improve' && p.target_skill
                    ? '改进：<span class="mono">'+esc(p.target_skill)+'</span>'
                    : '';

                var reviewNotes = p.review_notes
                    ? '<div class="prop-section"><div class="prop-section-label">审查评语</div><div class="prop-section-content">'+esc(p.review_notes)+'</div></div>'
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
                      + '正在按建议重写 → 审查中，完成立即解锁'
                      + '</div>'
                    : '';

                return ''
                    +'<div class="prop-card" id="card-'+esc(p.id)+'">'
                    +'  <div class="prop-head" onclick="toggleProp(\''+esc(p.id)+'\')">'
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
            var ok = await window.pmModal.confirm({
                title: '同意提案',
                message: '同意此提案？同意后会立即落盘到 skills/ 并注册。',
                confirmText: '同意',
            });
            if(!ok) return;
            try {
                var r = await fetch('/api/plugins/proposals/'+propId+'/approve', {method:'POST'});
                var d = await r.json();
                if(d.ok){ loadProposals(); window.pmToast.success('已同意'); } else { window.pmToast.error('同意失败: ' + (d.error || '未知')); }
            } catch(e){ window.pmToast.error('同意失败: ' + e.message); }
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
                if(d.ok){ loadProposals(); window.pmToast.success('已拒绝'); } else { window.pmToast.error('拒绝失败: ' + (d.error || '未知')); }
            } catch(e){ window.pmToast.error('拒绝失败: ' + e.message); }
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
            var ok = await window.pmModal.confirm({
                title: '彻底删除提案',
                message: '彻底删除此提案？仅 rejected 提案可删。',
                confirmText: '删除',
                danger: true,
            });
            if(!ok) return;
            try {
                var r = await fetch('/api/plugins/proposals/'+propId+'/delete', {method:'POST'});
                var d = await r.json();
                if(d.ok){ loadProposals(); window.pmToast.success('已删除'); } else { window.pmToast.error('删除失败: ' + (d.error || '未知')); }
            } catch(e){ window.pmToast.error('删除失败: ' + e.message); }
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
