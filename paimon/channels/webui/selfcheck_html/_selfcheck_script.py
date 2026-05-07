"""SELFCHECK_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

SELFCHECK_SCRIPT = """
    <script>
    (function(){
        function esc(s){if(s===null||s===undefined)return '';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
        function fmtTime(ts){
            if(!ts||ts<=0)return '-';
            var d=new Date(ts*1000);
            var pad=function(n){return n.toString().padStart(2,'0');};
            return (d.getMonth()+1)+'-'+d.getDate()+' '+pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds());
        }
        function fmtDur(s){
            if(!s||s<0)return '-';
            if(s<1)return (s*1000).toFixed(0)+'ms';
            if(s<60)return s.toFixed(1)+'s';
            var m=Math.floor(s/60); var ss=Math.floor(s%60);
            return m+'m'+(ss?ss+'s':'');
        }
        var currentTab='deep';

        async function loadLatestQuick(){
            var pill=document.getElementById('statusPill');
            try{
                var r=await fetch('/api/selfcheck/quick/latest');
                var data=await r.json();
                if(data && data.run){
                    var o=(data.run.quick_summary||{}).overall||'unknown';
                    var icon={ok:'✅',degraded:'⚠️',critical:'🚨'}[o]||'❓';
                    pill.className='status-pill status-'+o;
                    pill.textContent=icon+' '+o+' · '+fmtTime(data.run.triggered_at);
                }else{
                    pill.className='status-pill';
                    pill.textContent='尚无 Quick 记录';
                }
            }catch(e){
                pill.className='status-pill status-critical';
                pill.textContent='加载失败';
            }
        }

        async function loadRuns(kind){
            var el=document.getElementById('tabPanel');
            el.innerHTML='<div class="empty-state">加载中...</div>';
            try{
                var r=await fetch('/api/selfcheck/runs?kind='+kind+'&limit=100');
                var data=await r.json();
                var runs=data.runs||[];
                if(!runs.length){
                    el.innerHTML='<div class="empty-state">暂无 '+kind+' 历史</div>';
                    return;
                }
                if(kind==='deep'){
                    el.innerHTML=renderDeepTable(runs);
                }else{
                    el.innerHTML=renderQuickTable(runs);
                }
            }catch(e){
                el.innerHTML='<div class="empty-state">加载失败: '+esc(String(e))+'</div>';
            }
        }

        function fmtProgress(p){
            // p 是 SelfcheckRun.progress（watcher 轮 state.json 写入 DB 的快照）
            // 空 dict → 返回空；否则拼 "iter M/N · clean X/Y · 候选 C"
            if(!p || !Object.keys(p).length) return '';
            var it=p.current_iteration||0, max=p.max_iter||0;
            var cc=p.consecutive_clean||0, ci=p.clean_iter||0;
            var parts=[];
            if(max>0) parts.push('iter '+it+'/'+max);
            if(ci>0) parts.push('clean '+cc+'/'+ci);
            if(p.total_candidates!=null) parts.push('候选 '+p.total_candidates);
            return parts.join(' · ');
        }

        function renderDeepTable(runs){
            var rows=runs.map(function(r){
                var statusIcon=r.status==='completed'?'✓':(r.status==='running'?'…':'✗');
                // running 期间 P0-P3 来自 progress（watcher 实时抓）；其它状态从 DB 最终字段
                var p0, p1, p2, p3, total;
                if(r.status==='running' && r.progress && Object.keys(r.progress).length){
                    p0=r.progress.p0||0; p1=r.progress.p1||0;
                    p2=r.progress.p2||0; p3=r.progress.p3||0;
                    total=r.progress.total_confirmed!=null ? r.progress.total_confirmed : (r.progress.total_candidates||0);
                }else{
                    p0=r.p0_count; p1=r.p1_count; p2=r.p2_count; p3=r.p3_count;
                    total=r.findings_total;
                }
                var sevCells=[
                    '<td class="num sev-p0">'+p0+'</td>',
                    '<td class="num sev-p1">'+p1+'</td>',
                    '<td class="num sev-p2">'+p2+'</td>',
                    '<td class="num sev-p3">'+p3+'</td>',
                ].join('');
                // running 状态显示进度；completed/failed 不显示
                var statusCell=statusIcon+' '+esc(r.status);
                if(r.status==='running'){
                    var prog=fmtProgress(r.progress);
                    if(prog) statusCell+=' <span style="color:var(--text-muted);font-size:11px">· '+esc(prog)+'</span>';
                }
                if(r.error){
                    statusCell+=' <span style="color:var(--status-error)" title="'+esc(r.error)+'">!</span>';
                }
                var actions=r.status==='completed'
                    ? '<button class="mini-btn" onclick="viewDeep(\\''+r.id+'\\')">查看</button>'
                      +'<button class="mini-btn danger" onclick="deleteRun(\\''+r.id+'\\')">删除</button>'
                    : (r.status==='running'
                        ? '<button class="mini-btn" onclick="viewDeep(\\''+r.id+'\\')">详情</button>'
                        : '<button class="mini-btn danger" onclick="deleteRun(\\''+r.id+'\\')">删除</button>');
                return '<tr>'
                    +'<td>'+fmtTime(r.triggered_at)+'</td>'
                    +'<td class="id">'+esc(r.id.substring(0,8))+'</td>'
                    +'<td>'+esc(r.triggered_by)+'</td>'
                    +'<td>'+fmtDur(r.duration_seconds)+'</td>'
                    +sevCells
                    +'<td class="num">'+total+'</td>'
                    +'<td>'+statusCell+'</td>'
                    +'<td class="actions">'+actions+'</td>'
                    +'</tr>';
            }).join('');
            return '<div class="table-wrap"><table class="runs">'
                +'<thead><tr>'
                +'<th>时间</th><th>ID</th><th>触发</th><th>耗时</th>'
                +'<th>P0</th><th>P1</th><th>P2</th><th>P3</th>'
                +'<th>总数</th><th>状态 / 进度</th><th></th>'
                +'</tr></thead><tbody>'+rows+'</tbody></table></div>';
        }

        function renderQuickTable(runs){
            var rows=runs.map(function(r){
                var overall=(r.quick_summary||{}).overall||'?';
                var compList=((r.quick_summary||{}).components||[]);
                var compSummary=compList.map(function(c){
                    var icon={ok:'✓',degraded:'△',critical:'✗'}[c.status]||'?';
                    return '<span class="sev-'+(c.status==='critical'?'p0':c.status==='degraded'?'p1':'p3')+'">'+icon+' '+esc(c.name)+'</span>';
                }).join(' · ');
                var overallCls='status-'+overall;
                return '<tr>'
                    +'<td>'+fmtTime(r.triggered_at)+'</td>'
                    +'<td class="id">'+esc(r.id.substring(0,8))+'</td>'
                    +'<td class="'+overallCls+'">'+esc(overall)+'</td>'
                    +'<td>'+fmtDur(r.duration_seconds)+'</td>'
                    +'<td>'+compSummary+'</td>'
                    +'<td class="actions">'
                    +'<button class="mini-btn" onclick="viewQuick(\\''+r.id+'\\')">查看</button>'
                    +'<button class="mini-btn danger" onclick="deleteRun(\\''+r.id+'\\')">删除</button>'
                    +'</td>'
                    +'</tr>';
            }).join('');
            return '<div class="table-wrap"><table class="runs">'
                +'<thead><tr><th>时间</th><th>ID</th><th>整体</th><th>耗时</th><th>组件</th><th></th></tr></thead>'
                +'<tbody>'+rows+'</tbody></table></div>';
        }

        // Modal 自动刷新定时器（running 态才用）：要在 closeModal / 状态切换时清掉
        var _modalRefreshTimer=null;
        function _clearModalRefresh(){
            if(_modalRefreshTimer){
                clearInterval(_modalRefreshTimer);
                _modalRefreshTimer=null;
            }
        }

        async function _loadDeepOnce(runId){
            var metaR=await fetch('/api/selfcheck/runs/'+runId);
            var meta=(await metaR.json()).run;
            if(!meta) return null;
            if(meta.status==='running'){
                renderDeepProgress(meta);
                return 'running';
            }
            // 状态已切到 completed/failed → 清定时器、拉 findings 展示最终详情
            _clearModalRefresh();
            var findingsR=await fetch('/api/selfcheck/runs/'+runId+'/findings');
            var findings=(await findingsR.json()).findings||[];
            renderDeepDetail(runId,meta,findings);
            return meta.status;
        }

        window.viewDeep=async function(runId){
            _clearModalRefresh();  // 防重入：点不同 run 时清掉上个的定时器
            openModal('Deep 报告 · '+runId,'<div class="empty-state">加载中...</div>');
            try{
                var st=await _loadDeepOnce(runId);
                // running → 每 5s 自动刷新 Modal 内容直到状态变
                if(st==='running'){
                    _modalRefreshTimer=setInterval(function(){
                        // Modal 已关 → 停
                        if(!document.getElementById('modal').classList.contains('show')){
                            _clearModalRefresh();
                            return;
                        }
                        _loadDeepOnce(runId).catch(function(e){
                            console.warn('Modal 刷新失败', e);
                        });
                    }, 5000);
                }
            }catch(e){
                document.getElementById('modalBody').innerHTML='<div class="empty-state">加载失败</div>';
            }
        };

        function renderDeepProgress(meta){
            var p=meta.progress||{};
            var has=Object.keys(p).length>0;
            var elapsed=(Date.now()/1000 - meta.triggered_at);
            var iterBar='';
            if(p.max_iter>0){
                var pct=Math.min(100, Math.round((p.current_iteration||0)/p.max_iter*100));
                iterBar='<div style="background:var(--paimon-panel-light);height:8px;border-radius:4px;overflow:hidden;margin-top:4px">'
                    +'<div style="background:var(--gold);height:100%;width:'+pct+'%;transition:width .3s"></div></div>';
            }
            var cleanBar='';
            if(p.clean_iter>0){
                var cpct=Math.min(100, Math.round((p.consecutive_clean||0)/p.clean_iter*100));
                cleanBar='<div style="background:var(--paimon-panel-light);height:8px;border-radius:4px;overflow:hidden;margin-top:4px">'
                    +'<div style="background:var(--status-success);height:100%;width:'+cpct+'%;transition:width .3s"></div></div>';
            }
            var body=''
                +'<div class="modal-meta">'
                +'<div class="meta-item"><div class="meta-label">开始时间</div><div class="meta-value">'+fmtTime(meta.triggered_at)+'</div></div>'
                +'<div class="meta-item"><div class="meta-label">已进行</div><div class="meta-value">'+fmtDur(elapsed)+'</div></div>'
                +'<div class="meta-item"><div class="meta-label">触发</div><div class="meta-value">'+esc(meta.triggered_by)+'</div></div>'
                +'<div class="meta-item"><div class="meta-label">参数</div><div class="meta-value">'+esc(meta.check_args)+'</div></div>'
                +'</div>';
            if(!has){
                body+='<div class="empty-state">等 check skill 写第一份 state.json（通常 10~30 秒）...</div>';
            }else{
                body+=''
                    +'<div class="modal-meta">'
                    +'<div class="meta-item"><div class="meta-label">大轮次</div>'
                    +'<div class="meta-value">'+(p.current_iteration||0)+' / '+(p.max_iter||'?')+'</div>'+iterBar+'</div>'
                    +'<div class="meta-item"><div class="meta-label">连续 clean</div>'
                    +'<div class="meta-value">'+(p.consecutive_clean||0)+' / '+(p.clean_iter||'?')+'</div>'+cleanBar+'</div>'
                    +'<div class="meta-item"><div class="meta-label">候选 / 确认</div>'
                    +'<div class="meta-value">'+(p.total_candidates||0)+' / '+(p.total_confirmed||0)+'</div></div>'
                    +'<div class="meta-item"><div class="meta-label">发现 / 验证 轮次</div>'
                    +'<div class="meta-value">'+(p.discovery_rounds||'?')+' / '+(p.validation_rounds||'?')+'</div></div>'
                    +'</div>'
                    +'<div class="sev-bar">'
                    +'<div class="sev-chip"><span class="label">P0</span><span class="sev-p0">'+(p.p0||0)+'</span></div>'
                    +'<div class="sev-chip"><span class="label">P1</span><span class="sev-p1">'+(p.p1||0)+'</span></div>'
                    +'<div class="sev-chip"><span class="label">P2</span><span class="sev-p2">'+(p.p2||0)+'</span></div>'
                    +'<div class="sev-chip"><span class="label">P3</span><span class="sev-p3">'+(p.p3||0)+'</span></div>'
                    +'</div>';
                var mods=p.modules_processed||[];
                if(mods.length){
                    body+='<div style="margin-top:12px;padding:10px;background:var(--paimon-panel-light);border-radius:6px">'
                        +'<div class="meta-label">已扫 module ('+mods.length+')</div>'
                        +'<div style="margin-top:4px;color:var(--text-secondary);font-size:13px">'+mods.map(esc).join(', ')+'</div>'
                        +'</div>';
                }
                if(p.polled_at){
                    body+='<div style="margin-top:10px;color:var(--text-muted);font-size:11px">'
                        +'进度快照时间: '+fmtTime(p.polled_at)+'（watcher 每 5 秒轮询一次 state.json）</div>';
                }
            }
            body+='<div style="margin-top:16px;text-align:center;color:var(--text-muted);font-size:12px">'
                +'Modal 每 5 秒自动刷新；自检完成后会自动切换到最终详情视图</div>';
            document.getElementById('modalBody').innerHTML=body;
        }

        function renderDeepDetail(runId,meta,findings){
            var sev={P0:meta.p0_count,P1:meta.p1_count,P2:meta.p2_count,P3:meta.p3_count};
            var metaHtml=''
                +'<div class="modal-meta">'
                +'<div class="meta-item"><div class="meta-label">时间</div><div class="meta-value">'+fmtTime(meta.triggered_at)+'</div></div>'
                +'<div class="meta-item"><div class="meta-label">触发</div><div class="meta-value">'+esc(meta.triggered_by)+'</div></div>'
                +'<div class="meta-item"><div class="meta-label">耗时</div><div class="meta-value">'+fmtDur(meta.duration_seconds)+'</div></div>'
                +'<div class="meta-item"><div class="meta-label">参数</div><div class="meta-value">'+esc(meta.check_args)+'</div></div>'
                +'<div class="meta-item"><div class="meta-label">总数</div><div class="meta-value">'+meta.findings_total+'</div></div>'
                +'<div class="meta-item"><div class="meta-label">状态</div><div class="meta-value">'+esc(meta.status)+(meta.error?(' ('+esc(meta.error)+')'):'')+'</div></div>'
                +'</div>'
                +'<div class="sev-bar">'
                +Object.keys(sev).map(function(k){
                    var cls={P0:'sev-p0',P1:'sev-p1',P2:'sev-p2',P3:'sev-p3'}[k];
                    return '<div class="sev-chip"><span class="label">'+k+'</span><span class="'+cls+'">'+sev[k]+'</span></div>';
                }).join('')
                +'</div>'
                +'<div class="findings-filter">'
                +'<select id="filterSev"><option value="">全部严重度</option><option value="P0">仅 P0</option><option value="P1">仅 P1</option><option value="P2">仅 P2</option><option value="P3">仅 P3</option></select>'
                +'<input id="filterFile" placeholder="文件路径包含..."/>'
                +'<input id="filterModule" placeholder="模块包含..."/>'
                +'<button class="btn" onclick="downloadReport(\\''+runId+'\\')">下载 report.md</button>'
                +'</div>'
                +'<div class="findings-list" id="findingsList"></div>';
            document.getElementById('modalBody').innerHTML=metaHtml;

            function renderFindings(){
                var fs=document.getElementById('filterSev').value;
                var ff=(document.getElementById('filterFile').value||'').toLowerCase();
                var fm=(document.getElementById('filterModule').value||'').toLowerCase();
                var filtered=findings.filter(function(f){
                    var s=(f.severity||'P2').toUpperCase();
                    if(fs && s!==fs)return false;
                    if(ff && !((f.file||'').toLowerCase().indexOf(ff)>=0))return false;
                    if(fm && !((f.module||'').toLowerCase().indexOf(fm)>=0))return false;
                    return true;
                });
                var list=document.getElementById('findingsList');
                if(!filtered.length){
                    list.innerHTML='<div class="empty-state">无匹配 findings</div>';
                    return;
                }
                list.innerHTML=filtered.map(function(f){
                    var sev=(f.severity||'P2').toUpperCase();
                    var loc=f.file?(esc(f.file)+(f.line?':'+f.line:'')):'';
                    var icon={P0:'🔴',P1:'🟠',P2:'🔵',P3:'⚪'}[sev]||'•';
                    return '<div class="finding '+sev.toLowerCase()+'">'
                        +'<div class="finding-head">'
                        +'<span class="sev-'+sev.toLowerCase()+'">'+icon+' '+sev+'</span>'
                        +(loc?'<span class="finding-loc">'+loc+'</span>':'')
                        +(f.module?'<span class="finding-module">['+esc(f.module)+']</span>':'')
                        +'</div>'
                        +'<div class="finding-desc">'+esc(f.description||'')+'</div>'
                        +(f.evidence?'<div class="finding-evidence">'+esc(f.evidence)+'</div>':'')
                        +'</div>';
                }).join('');
            }
            document.getElementById('filterSev').onchange=renderFindings;
            document.getElementById('filterFile').oninput=renderFindings;
            document.getElementById('filterModule').oninput=renderFindings;
            renderFindings();
        }

        window.viewQuick=async function(runId){
            openModal('Quick 快照 · '+runId,'<div class="empty-state">加载中...</div>');
            try{
                var [metaR,snapR]=await Promise.all([
                    fetch('/api/selfcheck/runs/'+runId),
                    fetch('/api/selfcheck/runs/'+runId+'/quick'),
                ]);
                var meta=(await metaR.json()).run;
                var snap=(await snapR.json()).snapshot||{};
                renderQuickDetail(meta,snap);
            }catch(e){
                document.getElementById('modalBody').innerHTML='<div class="empty-state">加载失败</div>';
            }
        };

        function renderQuickDetail(meta,snap){
            var overall=snap.overall||meta.quick_summary&&meta.quick_summary.overall||'?';
            var comps=snap.components||[];
            var head=''
                +'<div class="modal-meta">'
                +'<div class="meta-item"><div class="meta-label">时间</div><div class="meta-value">'+fmtTime(meta.triggered_at)+'</div></div>'
                +'<div class="meta-item"><div class="meta-label">整体</div><div class="meta-value status-'+overall+'">'+esc(overall)+'</div></div>'
                +'<div class="meta-item"><div class="meta-label">耗时</div><div class="meta-value">'+fmtDur(meta.duration_seconds)+'</div></div>'
                +'<div class="meta-item"><div class="meta-label">触发</div><div class="meta-value">'+esc(meta.triggered_by)+'</div></div>'
                +'</div>';
            var compsHtml='<div class="quick-snapshot"><div class="comp-grid">'
                +comps.map(function(c){
                    var details=c.details?JSON.stringify(c.details,null,2):'';
                    return '<div class="comp-card '+esc(c.status||'ok')+'">'
                        +'<div class="comp-name">'+esc(c.name)+' <span class="comp-latency">'+(c.latency_ms||0).toFixed(1)+'ms</span></div>'
                        +(c.error?'<div style="color:var(--status-error);font-size:12px;margin-top:4px">'+esc(c.error)+'</div>':'')
                        +(details?'<div class="comp-details">'+esc(details)+'</div>':'')
                        +'</div>';
                }).join('')
                +'</div></div>';
            var warns=(snap.warnings||[]).length
                ? '<div style="margin-top:16px;padding:10px;background:var(--paimon-panel-light);border-radius:6px"><strong>⚠️ 告警</strong><ul style="margin-top:6px;padding-left:20px">'
                  +(snap.warnings||[]).map(function(w){return '<li>'+esc(w)+'</li>';}).join('')
                  +'</ul></div>'
                : '';
            document.getElementById('modalBody').innerHTML=head+warns+compsHtml;
        }

        window.downloadReport=function(runId){
            window.open('/api/selfcheck/runs/'+runId+'/report','_blank');
        };

        window.deleteRun=async function(runId){
            if(!confirm('确认删除 run='+runId.substring(0,8)+'？blob 文件一并删除。'))return;
            var r=await fetch('/api/selfcheck/runs/'+runId,{method:'DELETE'});
            if(r.ok){loadRuns(currentTab);loadLatestQuick();}
            else alert('删除失败');
        };

        function openModal(title,bodyHtml){
            document.getElementById('modalTitle').textContent=title;
            document.getElementById('modalBody').innerHTML=bodyHtml;
            document.getElementById('modal').classList.add('show');
        }
        window.closeModal=function(){
            _clearModalRefresh();  // 关 Modal 顺带停定时器，防止泄漏
            document.getElementById('modal').classList.remove('show');
        };
        document.getElementById('modal').addEventListener('click',function(e){
            if(e.target===this)closeModal();
        });

        // Tab 切换
        document.querySelectorAll('.tab').forEach(function(t){
            t.addEventListener('click',function(){
                document.querySelectorAll('.tab').forEach(function(x){x.classList.remove('active');});
                t.classList.add('active');
                currentTab=t.getAttribute('data-tab');
                loadRuns(currentTab);
            });
        });

        // 按钮
        document.getElementById('btnQuick').addEventListener('click',async function(){
            var b=this; b.disabled=true; b.textContent='Quick 运行中...';
            try{
                var r=await fetch('/api/selfcheck/quick/run',{method:'POST'});
                await r.json();
                await loadLatestQuick();
                if(currentTab==='quick')loadRuns('quick');
            }finally{
                b.disabled=false; b.textContent='⚡ 跑 Quick';
            }
        });
        document.getElementById('btnDeep').addEventListener('click',async function(){
            var b=this; b.disabled=true; b.textContent='Deep 启动中...';
            try{
                var r=await fetch('/api/selfcheck/deep/run',{method:'POST'});
                var data=await r.json();
                if(data.started){
                    alert('Deep 已启动 run='+data.run_id.substring(0,8)+'\\n后台运行中（几分钟到十几分钟），完成后面板自动刷新。');
                    setTimeout(function(){loadRuns('deep');},2000);
                }else{
                    alert('未启动: '+data.reason);
                }
            }catch(e){
                alert('调用失败');
            }finally{
                b.disabled=false; b.textContent='🔬 跑 Deep';
            }
        });

        // ========== 自动升级（git pull + sys.exit(100) 让 watchdog 拉起新代码）==========

        var _upgradeChecking = false;
        var _upgradeData = null;

        function escapeHtml(s){
            return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')
                .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        }

        async function loadUpgradeStatus(){
            if(_upgradeChecking) return;
            _upgradeChecking = true;
            var bar = document.getElementById('upgradeBar');
            var headEl = document.getElementById('upgradeHead');
            var behindEl = document.getElementById('upgradeBehind');
            var btnApply = document.getElementById('btnUpgradeApply');
            var commitsEl = document.getElementById('upgradeCommits');
            try{
                var r = await fetch('/api/selfcheck/upgrade/check');
                var d = await r.json();
                if(!d.ok){
                    headEl.textContent = '检查失败';
                    behindEl.textContent = '· ' + (d.error || '');
                    behindEl.className = '';
                    bar.classList.remove('has-update');
                    btnApply.style.display = 'none';
                    commitsEl.style.display = 'none';
                    return;
                }
                _upgradeData = d;
                // 显示 commit subject + 短 hash（不只是 md5）
                var sub = d.head_subject || '';
                if(sub.length > 70) sub = sub.substring(0, 70) + '…';
                headEl.textContent = sub
                    ? '当前: ' + sub + ' (' + d.head_short + ')'
                    : '当前 ' + d.head_short;
                if(d.behind > 0){
                    behindEl.textContent = '· 远程领先 ' + d.behind + ' commits';
                    behindEl.className = 'has-update';
                    bar.classList.add('has-update');
                    btnApply.style.display = '';
                    var html = '<div style="margin-bottom:6px;color:var(--gold)">📋 待拉取的 commits：</div>';
                    d.commits.forEach(function(c){
                        html += '<div class="upgrade-commit">'
                            + '<span class="h">' + c.hash + '</span> '
                            + escapeHtml(c.subject)
                            + '<span class="a">(' + c.age + ')</span>'
                            + '</div>';
                    });
                    commitsEl.innerHTML = html;
                    commitsEl.style.display = '';
                }else{
                    behindEl.textContent = '· 已是最新';
                    behindEl.className = '';
                    bar.classList.remove('has-update');
                    btnApply.style.display = 'none';
                    commitsEl.style.display = 'none';
                }
            }catch(e){
                headEl.textContent = '检查失败';
                behindEl.textContent = '· ' + e.message;
            }finally{
                _upgradeChecking = false;
            }
        }

        // 用户主动点「检查更新」：按钮 loading 状态 + 完成后 toast 反馈
        // （初始化和 5min 自动轮询走 loadUpgradeStatus 不弹 toast）
        function showToast(msg, kind){
            var t = document.getElementById('upgradeToast');
            if(t) t.remove();
            t = document.createElement('div');
            t.id = 'upgradeToast';
            t.className = 'upgrade-toast ' + (kind || 'info');
            t.textContent = msg;
            document.body.appendChild(t);
            setTimeout(function(){ if(t.parentNode) t.remove(); }, 3000);
        }

        document.getElementById('btnUpgradeCheck').addEventListener('click', async function(){
            var btn = this;
            if(btn.disabled) return;
            var origText = btn.textContent;
            btn.disabled = true;
            btn.textContent = '⏳ 检查中...';
            try{
                await loadUpgradeStatus();
                if(_upgradeData && _upgradeData.ok){
                    if(_upgradeData.behind > 0){
                        showToast('🔄 发现 ' + _upgradeData.behind + ' 个新 commit，可点击「拉取并重启」升级', 'info');
                    }else{
                        showToast('✅ 已是最新 (' + _upgradeData.head_short + ')', 'success');
                    }
                }else{
                    showToast('❌ 检查失败', 'error');
                }
            }finally{
                btn.disabled = false;
                btn.textContent = origText;
            }
        });

        document.getElementById('btnUpgradeApply').addEventListener('click', async function(){
            if(!_upgradeData || _upgradeData.behind <= 0){
                alert('当前没有可升级的内容，请先点「🔄 检查更新」');
                return;
            }
            var msg = '确认拉取并重启？\\n\\n'
                + '将拉取 ' + _upgradeData.behind + ' 个 commit 并重启进程。\\n'
                + '前端会暂时无响应（5-10 秒），重启后页面会自动刷新。';
            if(!confirm(msg)) return;

            var btn = this;
            btn.disabled = true;
            btn.textContent = '升级中...';
            try{
                var r = await fetch('/api/selfcheck/upgrade/trigger', {
                    method: 'POST',
                    headers: { 'X-Confirm': 'yes' },
                });
                var d = await r.json();
                if(!d.ok){
                    alert('升级失败：' + (d.error || '未知'));
                    btn.disabled = false;
                    btn.textContent = '⬇️ 拉取并重启';
                    return;
                }
                var html = '<div class="upgrade-status success">'
                    + '✅ ' + escapeHtml(d.message || '已触发升级') + '<br>'
                    + '<small>新 HEAD: ' + escapeHtml(d.new_head_short || '?') + '</small>';
                if(d.deps_warning){
                    html += '<br><br>⚠️ ' + escapeHtml(d.deps_warning);
                }
                html += '</div>';
                document.getElementById('upgradeCommits').innerHTML = html;
                document.getElementById('upgradeCommits').style.display = '';
                setTimeout(function(){ location.reload(); }, 10000);
            }catch(e){
                alert('请求失败：' + e.message);
                btn.disabled = false;
                btn.textContent = '⬇️ 拉取并重启';
            }
        });

        // ========== 重启按钮（不拉新代码，仅退出 100 让 watchdog 拉起当前代码）==========

        document.getElementById('btnRestart').addEventListener('click', async function(){
            if(!confirm('确认重启 paimon？\\n\\n用当前代码重启，不拉取更新。\\n前端会暂时无响应（5-10 秒），重启后页面会自动刷新。')) return;
            var btn = this;
            btn.disabled = true;
            btn.textContent = '重启中...';
            try{
                var r = await fetch('/api/selfcheck/restart', {
                    method: 'POST',
                    headers: { 'X-Confirm': 'yes' },
                });
                var d = await r.json();
                if(!d.ok){
                    alert('重启失败：' + (d.error || '未知'));
                    btn.disabled = false;
                    btn.textContent = '♻️ 重启';
                    return;
                }
                var html = '<div class="upgrade-status success">'
                    + '✅ ' + escapeHtml(d.message || '已触发重启')
                    + '</div>';
                document.getElementById('upgradeCommits').innerHTML = html;
                document.getElementById('upgradeCommits').style.display = '';
                setTimeout(function(){ location.reload(); }, 10000);
            }catch(e){
                alert('请求失败：' + e.message);
                btn.disabled = false;
                btn.textContent = '♻️ 重启';
            }
        });

        // ========== 回退警示条（watchdog 触发回退后展示，用户点「我知道了」清掉）==========

        async function loadRollbackStatus(){
            var el = document.getElementById('rollbackWarning');
            try{
                var r = await fetch('/api/selfcheck/upgrade/rollback_status');
                var d = await r.json();
                if(!d || !d.has_rollback){ el.style.display = 'none'; return; }
                var d2 = new Date((d.ts||0)*1000);
                var pad = function(n){return n.toString().padStart(2,'0');};
                var when = (d2.getMonth()+1)+'-'+d2.getDate()+' '+pad(d2.getHours())+':'+pad(d2.getMinutes());
                var before = (d.before||'').substring(0,8) || '?';
                var after = (d.after||'').substring(0,8) || '?';
                var isManual = d.kind === 'NEEDS_MANUAL';
                var title, meta;
                if(isManual){
                    el.classList.add('needs-manual');
                    title = '🚨 watchdog 回退失败 — 需要人工介入';
                    meta = 'HEAD 已等于 last_good_commit (<code>'+before+'</code>)，回退无效。'
                        + '可能 last_good 本身有问题。请 ssh 上去 <code>git log</code> 选更早稳定 commit 手动 reset。'
                        + '<br>失败次数: '+d.fail_count+' · 时间: '+when;
                }else{
                    el.classList.remove('needs-manual');
                    title = '⚠ watchdog 已自动回退';
                    meta = '从 <code>'+before+'</code> 回退到 <code>'+after+'</code>（last_good_commit）'
                        + '<br>失败次数: '+d.fail_count+' · 触发时间: '+when;
                }
                el.innerHTML = '<div class="rb-content">'
                    + '<div class="rb-title">'+title+'</div>'
                    + '<div class="rb-meta">'+meta+'</div>'
                    + '</div>'
                    + '<div class="rb-actions">'
                    + '<button class="btn" onclick="ackRollback()">我知道了</button>'
                    + '</div>';
                el.style.display = '';
            }catch(e){
                el.style.display = 'none';
            }
        }

        window.ackRollback = async function(){
            try{
                var r = await fetch('/api/selfcheck/upgrade/rollback_ack', { method: 'POST' });
                var d = await r.json();
                if(d.ok){
                    document.getElementById('rollbackWarning').style.display = 'none';
                    showToast('✅ 警示条已消除', 'success');
                }else{
                    showToast('❌ 操作失败：'+(d.error||'未知'), 'error');
                }
            }catch(e){
                showToast('❌ 请求失败', 'error');
            }
        };

        // 初始化
        loadLatestQuick();
        loadRuns('deep');
        loadUpgradeStatus();
        loadRollbackStatus();
        // 30s 自动刷新当前 tab
        setInterval(function(){
            loadLatestQuick();
            loadRuns(currentTab);
        },30000);
        // 5 分钟刷一次升级状态 + 回退警示（避免频繁 git fetch 打扰）
        setInterval(function(){
            loadUpgradeStatus();
            loadRollbackStatus();
        }, 300000);
    })();
    </script>
"""
