"""三月 · 任务观测面板（三 tab：定时任务 / 系统任务 / 深度任务）

- 定时任务：用户主动创建的 cron/interval/once（task_type='user'）
- 系统任务：archon 注册的内部周期任务（方案 D，task_type != 'user'），
  如风神订阅采集 / 岩神红利股扫描
- 深度任务：四影管线复杂任务（原 "四影任务"，2026-04-29 更名为 "深度任务"）

docs/interaction.md §四 WebUI。
"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)

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

TASKS_BODY = """
    <div class="container">
        <div class="page-header">
            <h1>任务观测</h1>
            <button class="refresh-btn" onclick="refreshAll()">刷新</button>
        </div>
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('scheduled',this)">定时任务 <span class="tab-count" id="countScheduled"></span></button>
            <button class="tab-btn" onclick="switchTab('system',this)">系统任务 <span class="tab-count" id="countSystem"></span></button>
            <button class="tab-btn" onclick="switchTab('complex',this)">深度任务 <span class="tab-count" id="countComplex"></span></button>
        </div>
        <div id="scheduled" class="tab-panel active">
            <div id="taskGrid"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="system" class="tab-panel">
            <div id="systemGrid"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="complex" class="tab-panel">
            <div id="complexGrid"><div class="empty-state">点击查看深度任务</div></div>
        </div>
    </div>

    <div id="taskModal" class="modal-mask" onclick="if(event.target===this)closeModal()">
        <div class="modal-card">
            <button class="modal-close" onclick="closeModal()">&times;</button>
            <div id="modalBody">加载中...</div>
        </div>
    </div>
"""

TASKS_SCRIPT = """
    <script>
    (function(){
        function esc(s){return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}
        function fmtTime(ts){
            if(!ts||ts<=0)return'-';
            var d=new Date(ts*1000);
            return (d.getMonth()+1)+'-'+d.getDate()+' '+d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0');
        }
        function fmtTimeFull(ts){
            if(!ts||ts<=0)return'-';
            var d=new Date(ts*1000);
            return d.getFullYear()+'-'+(d.getMonth()+1).toString().padStart(2,'0')+'-'+d.getDate().toString().padStart(2,'0')
                +' '+d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0');
        }
        function fmtDuration(s){
            s=Math.max(0,Math.floor(s||0));
            if(s<60)return s+'秒';
            if(s<3600)return Math.floor(s/60)+'分'+(s%60)+'秒';
            var h=Math.floor(s/3600), rem=s%3600;
            return h+'时'+Math.floor(rem/60)+'分';
        }
        function fmtTrigger(t){
            if(t.trigger_type==='once')return '一次性';
            if(t.trigger_type==='interval'){
                var s=t.trigger_value&&t.trigger_value.seconds||0;
                if(s>=3600)return '每'+Math.round(s/3600)+'小时';
                if(s>=60)return '每'+Math.round(s/60)+'分钟';
                return '每'+s+'秒';
            }
            if(t.trigger_type==='cron')return fmtCronZh(t.trigger_value&&t.trigger_value.expr||'');
            return t.trigger_type;
        }
        // 系统任务时间组用的中文化 cron（仅常见模式；不匹配则透出原 expr）
        function fmtCronZh(expr){
            if(!expr) return 'cron: ?';
            var p=String(expr).trim().split(/\\s+/);
            if(p.length!==5) return 'cron: '+expr;
            var m=p[0], h=p[1], dom=p[2], mon=p[3], dow=p[4];
            if(!/^\\d+$/.test(m) || !/^\\d+$/.test(h)) return 'cron: '+expr;
            var hh=h.padStart(2,'0'), mm=m.padStart(2,'0'), time=hh+':'+mm;
            if(dom==='*' && mon==='*' && dow==='*') return '每日 '+time;
            if(dom==='*' && mon==='*' && dow==='1-5') return '每工作日 '+time;
            var DOW=['日','一','二','三','四','五','六'];
            if(dom==='*' && mon==='*' && /^[0-6]$/.test(dow)) return '每周'+DOW[parseInt(dow)]+' '+time;
            if(/^\\d+$/.test(dom) && mon==='*' && dow==='*') return '每月 '+dom+' 号 '+time;
            return 'cron: '+expr;
        }
        var STATUS_LABEL={pending:'待处理',running:'进行中',completed:'完成',failed:'失败',rejected:'已拒绝',skipped:'已跳过'};
        var STATUS_BADGE={pending:'badge-pending',running:'badge-running',completed:'badge-completed',failed:'badge-failed',rejected:'badge-rejected',skipped:'badge-pending'};
        var SUB_ICON={completed:'✅',failed:'❌',skipped:'⏭️',running:'🔄',pending:'⏳',superseded:'♻️'};

        window.switchTab=function(key,btn){
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
            document.getElementById(key).classList.add('active');
            btn.classList.add('active');
            if(key==='complex')loadComplex();
            // scheduled / system 共用 /api/tasks 一次拉完；切过去不用重拉
            if((key==='scheduled'||key==='system') && !window._tasksLoaded) loadTasks();
        };
        window.refreshAll=function(){
            window._tasksLoaded=false;
            loadTasks();
            if(document.getElementById('complex').classList.contains('active')) loadComplex();
        };

        // 渲染单张卡（user / system 共用）
        function renderTaskCard(t){
            var src=t.source||null;  // 方案 D：非 user 类型带 source 元信息
            var cls='task-card'+(t.enabled?'':' disabled')+(src?' internal clickable':'');
            var badge=t.enabled?'<span class="task-badge badge-enabled">运行中</span>':'<span class="task-badge badge-disabled">已停止</span>';
            var err=t.last_error?'<div class="task-error">'+esc(t.last_error.substring(0,100))+(t.consecutive_failures?' (连续'+t.consecutive_failures+'次)':'')+'</div>':'';

            var headLeft='<span class="task-id">'+esc(t.id)+'</span>';
            var displayText='';
            var sourceHint='';
            if(src){
                var chipCls='task-source-chip'+(src.task_type && !src.jump_url?' unknown':'');
                headLeft='<span class="'+chipCls+'">'+esc(src.label||'?')+'</span>'+headLeft;
                displayText=esc(src.description||src.task_type||'-');
                if(src.jump_url){
                    sourceHint='<div class="task-source-hint">💡 此任务由 <a href="'+esc(src.jump_url)+'">'+esc(src.manager_panel||src.jump_url)+'</a> 面板创建，启停/删除请到对应面板管理</div>';
                }else if(src.task_type){
                    sourceHint='<div class="task-source-hint">⚠️ 未知任务类型 '+esc(src.task_type)+'（对应 archon 可能未注册或已移除）</div>';
                }
            }else{
                displayText=esc(t.prompt);
            }

            var onClick=src&&src.jump_url
                ? ' onclick="window.location=\\''+esc(src.jump_url)+'\\'"'
                : '';

            return '<div class="'+cls+'"'+onClick+'>'
                +'<div class="task-header"><span>'+headLeft+'</span>'+badge+'</div>'
                +'<div class="task-prompt">'+displayText+'</div>'
                +'<div class="task-meta">'
                +'<span class="task-meta-item">'+fmtTrigger(t)+'</span>'
                +'<span class="task-meta-item">下次: '+fmtTime(t.next_run_at)+'</span>'
                +'<span class="task-meta-item">上次: '+fmtTime(t.last_run_at)+'</span>'
                +'<span class="task-meta-item">创建: '+fmtTime(t.created_at)+'</span>'
                +'</div>'
                +err
                +sourceHint
                +'</div>';
        }

        // ===== 系统任务两层分组（外层按神 / 内层按精确分钟 cron） =====
        function groupKeyOf(t){
            if(t.trigger_type==='cron'){
                return 'cron:'+(t.trigger_value && t.trigger_value.expr || '?');
            }
            return 'tid:'+t.id;  // 非 cron 一任务一组
        }
        function renderSingleRow(t, timeLabel){
            var src=t.source||{};
            var enabledCls=t.enabled?'':' disabled';
            var jump=src.jump_url ? ' onclick="window.location=\\''+esc(src.jump_url)+'\\'"' : '';
            var stopBadge=t.enabled?'':'<span class="task-badge badge-disabled">已停止</span>';
            var errBadge=t.last_error?'<span class="task-badge badge-failed" title="'+esc(t.last_error.substring(0,200))+'">⚠ 失败</span>':'';
            return '<div class="time-single'+enabledCls+'"'+jump+'>'
                +'<span class="time-single-time">'+esc(timeLabel)+'</span>'
                +'<span class="time-single-desc">'+esc(src.description||src.task_type||'-')+'</span>'
                +errBadge+stopBadge
                +'</div>';
        }
        function renderTimeGroup(g){
            var preview=g.tasks.slice(0,3).map(function(t){return (t.source && t.source.description) || '?';}).join(' · ');
            if(g.tasks.length>3) preview+=' …';
            var body=g.tasks.map(renderTaskCard).join('');
            return '<div class="time-group">'
                +'<div class="time-group-head" onclick="toggleTimeGroup(this)">'
                +  '<span class="time-group-arrow">▶</span>'
                +  '<span class="time-group-time">'+esc(g.label)+'</span>'
                +  '<span class="time-group-count">'+g.tasks.length+' 项</span>'
                +  '<span class="time-group-preview">'+esc(preview)+'</span>'
                +'</div>'
                +'<div class="time-group-body">'+body+'</div>'
                +'</div>';
        }
        function renderSystemGrid(sysTasks, archons){
            // 1. 桶：archonKey → {name, groups{groupKey→{label,tasks}}, order[groupKey]}
            var byArchon={};
            sysTasks.forEach(function(t){
                var ak=(t.source && t.source.archon)||'';
                var an=(t.source && t.source.archon_name)||'其他';
                if(!byArchon[ak]) byArchon[ak]={key:ak, name:an, groups:{}, order:[]};
                var gk=groupKeyOf(t);
                if(!byArchon[ak].groups[gk]){
                    var label=t.trigger_type==='cron'
                        ? fmtCronZh(t.trigger_value && t.trigger_value.expr || '')
                        : fmtTrigger(t);
                    byArchon[ak].groups[gk]={key:gk, label:label, tasks:[]};
                    byArchon[ak].order.push(gk);
                }
                byArchon[ak].groups[gk].tasks.push(t);
            });
            // 2. 排序：先按 archons[] 顺序，未登记的归到末尾
            var ordered=[], seen={};
            (archons||[]).forEach(function(a){
                if(byArchon[a.key]){ ordered.push(byArchon[a.key]); seen[a.key]=true; }
            });
            Object.keys(byArchon).forEach(function(k){
                if(!seen[k]) ordered.push(byArchon[k]);
            });
            // 3. 渲染
            return ordered.map(function(arch){
                var totalGroups=arch.order.length;
                var totalTasks=arch.order.reduce(function(s,gk){return s+arch.groups[gk].tasks.length;},0);
                var bodyHtml=arch.order.map(function(gk){
                    var g=arch.groups[gk];
                    return g.tasks.length===1 ? renderSingleRow(g.tasks[0], g.label) : renderTimeGroup(g);
                }).join('');
                return '<div class="archon-section">'
                    +'<div class="archon-header" onclick="toggleArchon(this)">'
                    +  '<span class="archon-arrow">▼</span>'
                    +  '<span class="archon-name">'+esc(arch.name)+'</span>'
                    +  '<span class="archon-stat">'+totalGroups+' 组 / '+totalTasks+' 项</span>'
                    +'</div>'
                    +'<div class="archon-body">'+bodyHtml+'</div>'
                    +'</div>';
            }).join('');
        }
        window.toggleArchon=function(el){ el.parentElement.classList.toggle('collapsed'); };
        window.toggleTimeGroup=function(el){ el.parentElement.classList.toggle('expanded'); };

        window.loadTasks=async function(){
            var userEl=document.getElementById('taskGrid');
            var sysEl=document.getElementById('systemGrid');
            try{
                var r=await fetch('/api/tasks');
                var data=await r.json();
                var tasks=data.tasks||[];

                // 按 source 字段分流：有 source = 系统任务（archon 注册），无 source = 用户定时任务
                var userTasks=tasks.filter(function(t){ return !t.source; });
                var sysTasks =tasks.filter(function(t){ return !!t.source; });

                // 计数 chip
                var cu=document.getElementById('countScheduled');
                var cs=document.getElementById('countSystem');
                if(cu) cu.textContent=userTasks.length?userTasks.length:'';
                if(cs) cs.textContent=sysTasks.length?sysTasks.length:'';

                if(!userTasks.length){
                    userEl.innerHTML='<div class="empty-state"><div class="empty-icon">&#128337;</div>暂无定时任务<br><br>在对话中说"每小时提醒我喝水"或使用 /schedule 指令创建</div>';
                }else{
                    userEl.innerHTML=userTasks.map(renderTaskCard).join('');
                }

                if(!sysTasks.length){
                    sysEl.innerHTML='<div class="empty-state"><div class="empty-icon">&#9881;&#65039;</div>暂无系统任务<br><br>开启订阅推送（/feed 面板）或红利股追踪（/wealth 面板）后，这里会显示由系统代管的周期任务</div>';
                }else{
                    sysEl.innerHTML=renderSystemGrid(sysTasks, data.archons||[]);
                }

                window._tasksLoaded=true;
            }catch(e){
                userEl.innerHTML='<div class="empty-state">加载失败</div>';
                if(sysEl) sysEl.innerHTML='<div class="empty-state">加载失败</div>';
            }
        };

        window.loadComplex=async function(){
            var el=document.getElementById('complexGrid');
            el.innerHTML='<div class="empty-state">加载中...</div>';
            try{
                var r=await fetch('/api/tasks/complex');
                var data=await r.json();
                var tasks=data.tasks||[];
                var cc=document.getElementById('countComplex');
                if(cc) cc.textContent=tasks.length?tasks.length:'';
                if(!tasks.length){
                    el.innerHTML='<div class="empty-state"><div class="empty-icon">&#128221;</div>最近 7 天暂无深度任务<br><br>用 /task &lt;描述&gt; 或自然语言描述复杂任务，派蒙会路由到四影管线</div>';
                    return;
                }
                el.innerHTML=tasks.map(function(t){
                    var label=STATUS_LABEL[t.status]||t.status||'?';
                    var badgeCls=STATUS_BADGE[t.status]||'badge-pending';
                    var badge='<span class="task-badge '+badgeCls+'">'+esc(label)+'</span>';
                    var subInfo=t.subtask_total?(t.subtask_completed+'/'+t.subtask_total+' 子任务'+(t.subtask_failed?(' · '+t.subtask_failed+' 失败'):'')):'无子任务';
                    return '<div class="task-card clickable" onclick="openComplex(\\''+esc(t.id)+'\\')">'
                        +'<div class="task-header"><span class="task-id">'+esc(t.id.substring(0,12))+'</span>'+badge+'</div>'
                        +'<div class="task-prompt">'+esc(t.title||'(无标题)')+'</div>'
                        +'<div class="task-meta">'
                        +'<span class="task-meta-item">'+esc(t.creator||'-')+'</span>'
                        +'<span class="task-meta-item">'+esc(subInfo)+'</span>'
                        +'<span class="task-meta-item">耗时 '+fmtDuration(t.duration_seconds)+'</span>'
                        +'<span class="task-meta-item">'+fmtTime(t.created_at)+'</span>'
                        +'</div>'
                        +'</div>';
                }).join('');
            }catch(e){
                el.innerHTML='<div class="empty-state">加载失败: '+esc(e.message||e)+'</div>';
            }
        };

        window.openComplex=async function(id){
            var modal=document.getElementById('taskModal');
            var body=document.getElementById('modalBody');
            modal.classList.add('show');
            body.innerHTML='<div class="empty-state">加载中...</div>';
            try{
                var r=await fetch('/api/tasks/complex/'+encodeURIComponent(id));
                if(!r.ok){ body.innerHTML='<div class="empty-state">加载失败 (HTTP '+r.status+')</div>'; return; }
                var data=await r.json();
                var t=data.task||{};
                var subs=data.subtasks||[];
                var label=STATUS_LABEL[t.status]||t.status||'?';
                var badgeCls=STATUS_BADGE[t.status]||'badge-pending';
                var head='<h2>📌 '+esc(t.title||'(无标题)')+'</h2>'
                    +'<div class="meta-row">'
                    +'<span class="task-badge '+badgeCls+'">'+esc(label)+'</span>'
                    +'<span>创建：'+fmtTimeFull(t.created_at)+'</span>'
                    +'<span>耗时：'+fmtDuration(t.duration_seconds)+'</span>'
                    +'<span>创建者：'+esc(t.creator||'-')+'</span>'
                    +'<span>id: '+esc((t.id||'').substring(0,12))+'</span>'
                    +'</div>';
                if(t.description && t.description!==t.title){
                    head+='<div class="task-prompt" style="margin-bottom:16px">'+esc(t.description.substring(0,500))+'</div>';
                }
                var subsHtml='';
                if(subs.length){
                    subsHtml='<table class="subtask-table">'
                        +'<thead><tr><th class="col-icon"></th><th>负责</th><th>描述</th><th>裁决</th><th>round</th><th class="col-result">结果摘录</th></tr></thead><tbody>';
                    subs.forEach(function(s){
                        subsHtml+='<tr>'
                            +'<td class="col-icon">'+(SUB_ICON[s.status]||'·')+'</td>'
                            +'<td>'+esc(s.assignee||'-')+'</td>'
                            +'<td>'+esc(s.description||'').substring(0,80)+'</td>'
                            +'<td>'+esc(s.verdict_status||'-')+'</td>'
                            +'<td>'+s.round+'</td>'
                            +'<td class="col-result">'+esc((s.result||'').substring(0,200))+'</td>'
                            +'</tr>';
                    });
                    subsHtml+='</tbody></table>';
                }else{
                    subsHtml='<div class="empty-state" style="padding:20px">无子任务</div>';
                }
                var summary='';
                if(data.summary_md){
                    summary='<h3 style="font-size:14px;color:var(--text-muted);margin-top:16px">摘要 (summary.md)</h3>'
                        +'<div class="summary-md">'+esc(data.summary_md)+'</div>';
                }
                body.innerHTML=head+'<h3 style="font-size:14px;color:var(--text-muted)">子任务 ('+subs.length+')</h3>'+subsHtml+summary;
            }catch(e){
                body.innerHTML='<div class="empty-state">加载失败: '+esc(e.message||e)+'</div>';
            }
        };

        window.closeModal=function(){
            document.getElementById('taskModal').classList.remove('show');
        };

        window.onload=function(){
            loadTasks();   // 渲染 scheduled + system 两 grid + 更新双计数
            loadComplex(); // 提前拉一次只为更新 complex 计数 chip；渲染会被下次 switch 覆盖
        };
        setInterval(function(){
            // 仅刷新当前 tab，避免不必要的请求；system / scheduled 共享同一 API
            var active=document.querySelector('.tab-panel.active');
            if(!active) return;
            if(active.id==='scheduled'||active.id==='system'){
                window._tasksLoaded=false;
                loadTasks();
            }else if(active.id==='complex'){
                loadComplex();
            }
        },30000);
    })();
    </script>
"""


def build_tasks_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 任务观测</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + TASKS_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("tasks")
        + TASKS_BODY
        + TASKS_SCRIPT
        + """</body>
</html>"""
    )
