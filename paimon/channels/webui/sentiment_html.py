"""风神 · 舆情看板（L1 事件级）

docs/archons/venti.md §L1
布局：
- 顶部 4 张统计卡（7 天事件数 / p0+p1 数 / 整体情感 / 活跃订阅数）
- 左主列 60%：事件时间线（按 last_seen_at 倒序，可按 severity / sub 过滤）
- 右上 40%：情感折线（Chart.js，按天聚合 avg_sentiment）
- 右中：严重度矩阵（7 天 × 4 级 div grid 热图）
- 右下：信源 Top（域名 + 计数）
- 事件卡片点开 → Modal 抽屉显示完整 timeline + 关联 items

数据来自 6 个 /api/sentiment/* 路由。
"""

from paimon.channels.webui.theme import (
    BASE_CSS,
    NAV_LINKS_CSS,
    NAVIGATION_CSS,
    THEME_COLORS,
    navigation_html,
)


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


SENTIMENT_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>🌬️ 风神·舆情看板</h1>
                <div class="sub">事件级聚合 / 严重度分级 / 跨批次合并</div>
            </div>
            <div class="header-actions">
                <button class="btn" onclick="loadAll()">刷新</button>
                <a href="/feed" class="btn" style="text-decoration:none">信息流原始流</a>
            </div>
        </div>

        <div id="digest" class="digest-section" style="margin-top:0">
            <div class="ds-head">
                <h2>📨 风神 · 日报公告 <span id="ventiBulletinHint" style="font-size:12px;color:var(--text-muted);font-weight:normal;margin-left:8px"></span></h2>
                <div class="ds-tools">
                    <button onclick="window.markAllVentiRead()">全部已读</button>
                </div>
            </div>
            <div id="ventiBulletins">
                <div class="digest-bulletins-empty">加载中...</div>
            </div>
            <div class="digest-history-toggle">
                <button onclick="window.toggleVentiHistory()" id="ventiHistoryToggleBtn">
                    📜 查看更多历史 ↓
                </button>
            </div>
            <div id="ventiHistoryWrap" style="display:none;margin-top:12px">
                <input id="ventiDigestSearch" placeholder="搜索历史内容（Enter 应用）"
                    style="width:100%;padding:6px 10px;background:var(--paimon-bg);border:1px solid var(--paimon-border);border-radius:4px;color:var(--text-primary);font-size:12px;margin-bottom:10px" />
                <div id="ventiDigestList" class="digest-list">
                    <div class="push-empty">加载中...</div>
                </div>
            </div>
        </div>

        <div class="stats-row" id="statsRow">
            <div class="stat-card"><div class="stat-num" id="stEvents">-</div><div class="stat-label">7 天事件数</div></div>
            <div class="stat-card"><div class="stat-num warning" id="stP01">-</div><div class="stat-label">P0+P1 数</div></div>
            <div class="stat-card"><div class="stat-num" id="stSent">-</div><div class="stat-label">整体情感</div></div>
            <div class="stat-card"><div class="stat-num" id="stSubs">-</div><div class="stat-label">活跃订阅</div></div>
        </div>

        <div class="main-grid">
            <div class="panel">
                <div class="panel-head">
                    <h2>事件时间线</h2>
                    <div class="panel-tools">
                        <select id="filterDays" onchange="loadEvents()">
                            <option value="7" selected>近 7 天</option>
                            <option value="14">近 14 天</option>
                            <option value="30">近 30 天</option>
                        </select>
                        <select id="filterSeverity" onchange="loadEvents()">
                            <option value="">所有严重度</option>
                            <option value="p0">仅 P0</option>
                            <option value="p1">仅 P1</option>
                            <option value="p2">仅 P2</option>
                            <option value="p3">仅 P3</option>
                        </select>
                        <select id="filterSub" onchange="onSubFilterChange()">
                            <option value="">所有订阅</option>
                        </select>
                    </div>
                </div>
                <div id="subBanner" class="sub-banner"></div>
                <div class="events-list" id="eventsList">
                    <div class="empty-state">加载中...</div>
                </div>
            </div>

            <div class="right-col">
                <div class="panel">
                    <div class="panel-head"><h2>情感折线 · 近 14 天</h2></div>
                    <canvas id="sentimentChart"></canvas>
                </div>
                <div class="panel">
                    <div class="panel-head"><h2>严重度矩阵 · 近 7 天</h2></div>
                    <div class="matrix-grid" id="matrixGrid">
                        <div class="empty-state" style="grid-column:1/9">加载中...</div>
                    </div>
                </div>
                <div class="panel">
                    <div class="panel-head"><h2>信源 Top · 近 7 天</h2></div>
                    <div class="sources-list" id="sourcesList">
                        <div class="empty-state">加载中...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="modal-mask" id="modal">
        <div class="modal">
            <div class="modal-head">
                <h3 id="modalTitle">事件详情</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modalBody"></div>
        </div>
    </div>
"""


SENTIMENT_SCRIPT = r"""
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script>
    (function(){
        function esc(s){if(s==null)return '';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
        function fmtTime(ts){
            if(!ts||ts<=0)return '-';
            var d=new Date(ts*1000);
            return (d.getMonth()+1)+'-'+d.getDate()+' '+d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0');
        }
        function fmtSentScore(score){
            if(score==null) return '-';
            var s=Number(score);
            return (s>=0?'+':'')+s.toFixed(2);
        }
        var _chart=null;

        async function loadOverview(){
            // 顶部 4 张卡始终是全局视图，与订阅过滤器无关
            try{
                var r=await fetch('/api/sentiment/overview');
                var d=await r.json();
                document.getElementById('stEvents').textContent=d.events_7d||0;
                document.getElementById('stP01').textContent=d.p0_p1_count||0;
                var sentEl=document.getElementById('stSent');
                var s=Number(d.avg_sentiment||0);
                sentEl.textContent=fmtSentScore(s);
                sentEl.classList.remove('negative','positive','warning');
                if(s<-0.2) sentEl.classList.add('negative');
                else if(s>0.2) sentEl.classList.add('positive');
                else sentEl.classList.add('warning');
                document.getElementById('stSubs').textContent=d.sub_count||0;
            }catch(e){console.warn('overview 加载失败', e);}
        }

        async function loadSubBanner(){
            // 订阅级子统计 banner —— 仅在 filterSub 选中具体订阅时显示
            var subId=document.getElementById('filterSub').value||'';
            var el=document.getElementById('subBanner');
            if(!subId){ el.classList.remove('show'); el.innerHTML=''; return; }
            try{
                var r=await fetch('/api/sentiment/overview?sub_id='+encodeURIComponent(subId));
                var d=await r.json();
                var sent=Number(d.avg_sentiment||0);
                var sentClass=sent<-0.2?'sent-strong':(sent>0.2?'sent-pos':'sent-neutral');
                var sentLabel=sent<-0.2?'偏负面':(sent>0.2?'偏正面':'中性');
                var lastRun=d.last_run_at? fmtTime(d.last_run_at):'未跑';
                var nextRun=d.next_run_at? fmtTime(d.next_run_at):'-';
                var errBlock=d.last_error?
                    '<span style="color:var(--status-error)">⚠ 上次错误: '+esc(String(d.last_error).slice(0,80))+'</span>':'';
                var enabledTag=d.sub_enabled===false?
                    '<span style="color:var(--status-warning)">⏸ 已禁用</span>':'';
                el.innerHTML=
                    '<div class="b-row">'
                    + '<span>📊 当前订阅: <b>'+esc(d.sub_query||'-')+'</b></span>'
                    + '<span><b>'+(d.events_7d||0)+'</b> 个事件</span>'
                    + '<span><b>'+(d.feed_items_total||0)+'</b> 条原始</span>'
                    + '<span>平均情感 <span class="'+sentClass+'">'+fmtSentScore(sent)+' '+sentLabel+'</span></span>'
                    + '<span><span class="sev-mini sev-p0">P0×'+(d.p0_count||0)+'</span> '
                    + '<span class="sev-mini sev-p1">P1×'+(d.p1_count||0)+'</span> '
                    + '<span class="sev-mini sev-p2">P2×'+(d.p2_count||0)+'</span> '
                    + '<span class="sev-mini sev-p3">P3×'+(d.p3_count||0)+'</span></span>'
                    + (enabledTag?(' '+enabledTag):'')
                    + '</div>'
                    + '<div class="b-row">'
                    + '<span>📅 上次采集 '+lastRun+'</span>'
                    + '<span>下次 '+nextRun+'</span>'
                    + '<span>cron <code>'+esc(d.sub_cron||'-')+'</code></span>'
                    + '<span>累计推送 '+(d.pushed_total||0)+' 次</span>'
                    + (d.sub_engine?('<span>引擎 '+esc(d.sub_engine)+'</span>'):'')
                    + (errBlock?(' '+errBlock):'')
                    + '</div>';
                el.classList.add('show');
            }catch(e){
                el.innerHTML='<div class="b-row" style="color:var(--status-error)">订阅汇总加载失败</div>';
                el.classList.add('show');
            }
        }

        async function loadSubsForFilter(){
            try{
                var r=await fetch('/api/feed/subs');
                var d=await r.json();
                var sel=document.getElementById('filterSub');
                while(sel.options.length>1)sel.remove(1);
                (d.subs||[]).forEach(function(s){
                    var op=document.createElement('option');
                    op.value=s.id;op.textContent=s.query;
                    sel.appendChild(op);
                });
            }catch(e){}
        }

        async function loadEvents(){
            var days=document.getElementById('filterDays').value||'7';
            var sev=document.getElementById('filterSeverity').value||'';
            var sub=document.getElementById('filterSub').value||'';
            var qs='days='+days+(sev?'&severity='+sev:'')+(sub?'&sub_id='+sub:'')+'&limit=100';
            var el=document.getElementById('eventsList');
            el.innerHTML='<div class="empty-state">加载中...</div>';
            try{
                var r=await fetch('/api/sentiment/events?'+qs);
                var d=await r.json();
                var evs=d.events||[];
                if(!evs.length){
                    el.innerHTML='<div class="empty-state">暂无事件<br><small>跑一次订阅采集后会出现</small></div>';
                    return;
                }
                el.innerHTML=evs.map(renderEventCard).join('');
            }catch(e){
                el.innerHTML='<div class="empty-state">加载失败: '+esc(String(e))+'</div>';
            }
        }

        function renderEventCard(ev){
            var sentLabel=ev.sentiment_label||'neutral';
            var entitiesHtml=(ev.entities||[]).slice(0,4).map(function(e){
                return '<span class="meta-tag entity">'+esc(e)+'</span>';
            }).join('');
            var sourcesHtml=(ev.sources||[]).slice(0,3).map(function(s){
                return '<span class="meta-tag source">'+esc(s)+'</span>';
            }).join('');
            var lastSeen=fmtTime(ev.last_seen_at);
            var pushedTag=ev.pushed_count>0
                ? '<span class="meta-tag" title="已推送 '+ev.pushed_count+' 次">📨×'+ev.pushed_count+'</span>'
                : '';
            return '<div class="event-card" onclick="openEvent(\''+esc(ev.id)+'\')">'
                + '<div class="event-head">'
                + '<span class="sev-badge sev-'+esc(ev.severity||'p3')+'">'+(ev.severity||'p3').toUpperCase()+'</span>'
                + '<span class="sentiment-chip '+esc(sentLabel)+'">'+esc(sentLabel)+' '+fmtSentScore(ev.sentiment_score)+'</span>'
                + '<div class="event-title">'+esc(ev.title||'(无标题)')+'</div>'
                + '</div>'
                + '<div class="event-summary">'+esc(ev.summary||'')+'</div>'
                + '<div class="event-meta">'
                + '<span class="meta-tag">'+lastSeen+'</span>'
                + '<span class="meta-tag">'+ev.item_count+' 条来源</span>'
                + entitiesHtml + sourcesHtml + pushedTag
                + '</div>'
                + '</div>';
        }

        async function loadTimeline(){
            // 跟订阅过滤器联动：选了某订阅时只看该订阅折线/矩阵
            var subId=document.getElementById('filterSub').value||'';
            var qs='days=14'+(subId?'&sub_id='+encodeURIComponent(subId):'');
            try{
                var r=await fetch('/api/sentiment/timeline?'+qs);
                var d=await r.json();
                var days=d.days||[];
                renderChart(days);
                renderMatrix(days.slice(-7));
            }catch(e){console.warn('timeline 加载失败', e);}
        }

        function renderChart(days){
            var labels=days.map(function(d){return d.date.slice(5);});
            var sentiment=days.map(function(d){return d.avg_sentiment;});
            var ctx=document.getElementById('sentimentChart').getContext('2d');
            if(_chart){_chart.destroy();}
            _chart=new Chart(ctx,{
                type:'line',
                data:{
                    labels:labels,
                    datasets:[{
                        label:'avg_sentiment',
                        data:sentiment,
                        borderColor:'#d4af37',
                        backgroundColor:'rgba(212,175,55,.1)',
                        tension:0.3, fill:true,
                        pointRadius:3, pointBackgroundColor:'#d4af37',
                    }]
                },
                options:{
                    responsive:true, maintainAspectRatio:false,
                    plugins:{legend:{display:false}},
                    scales:{
                        y:{min:-1, max:1, ticks:{color:'#9ca3af', stepSize:0.5}, grid:{color:'rgba(255,255,255,.05)'}},
                        x:{ticks:{color:'#9ca3af'}, grid:{display:false}},
                    }
                }
            });
        }

        function renderMatrix(days){
            var grid=document.getElementById('matrixGrid');
            var html='<div class="matrix-cell-header"></div>';
            days.forEach(function(d){
                html+='<div class="matrix-cell-header">'+d.date.slice(5)+'</div>';
            });
            ['p0','p1','p2','p3'].forEach(function(sev){
                html+='<div class="matrix-row-label">'+sev.toUpperCase()+'</div>';
                days.forEach(function(d){
                    var n=d[sev]||0;
                    var bg=sev==='p0'?'rgba(239,68,68,'+Math.min(0.7, 0.18+n*0.18)+')'
                         :sev==='p1'?'rgba(245,158,11,'+Math.min(0.7, 0.18+n*0.18)+')'
                         :sev==='p2'?'rgba(110,198,255,'+Math.min(0.7, 0.10+n*0.12)+')'
                         :'rgba(156,163,175,'+Math.min(0.5, 0.10+n*0.08)+')';
                    if(n===0) bg='var(--paimon-bg)';
                    html+='<div class="matrix-cell" data-count="'+n+'" style="background:'+bg+'">'+(n||'')+'</div>';
                });
            });
            grid.innerHTML=html;
        }

        async function loadSources(){
            // 跟订阅过滤器联动：选了某订阅时只看该订阅信源
            var subId=document.getElementById('filterSub').value||'';
            var qs='days=7&limit=10'+(subId?'&sub_id='+encodeURIComponent(subId):'');
            try{
                var r=await fetch('/api/sentiment/sources?'+qs);
                var d=await r.json();
                var sources=d.sources||[];
                var el=document.getElementById('sourcesList');
                if(!sources.length){
                    el.innerHTML='<div class="empty-state">暂无信源数据</div>';
                    return;
                }
                el.innerHTML=sources.map(function(s){
                    return '<div class="source-row">'
                        + '<span class="source-domain">'+esc(s.domain)+'</span>'
                        + '<span class="source-count">'+s.count+'</span>'
                        + '</div>';
                }).join('');
            }catch(e){}
        }

        window.openEvent=async function(eventId){
            document.getElementById('modalTitle').textContent='事件详情 · '+eventId.substring(0,8);
            document.getElementById('modalBody').innerHTML='<div class="empty-state">加载中...</div>';
            document.getElementById('modal').classList.add('show');
            try{
                var r=await fetch('/api/sentiment/events/'+encodeURIComponent(eventId));
                if(!r.ok){
                    var err=await r.json();
                    document.getElementById('modalBody').innerHTML='<div class="empty-state">'+esc(err.error||'加载失败')+'</div>';
                    return;
                }
                var d=await r.json();
                renderEventDetail(d);
            }catch(e){
                document.getElementById('modalBody').innerHTML='<div class="empty-state">加载失败: '+esc(String(e))+'</div>';
            }
        };
        window.closeModal=function(){
            document.getElementById('modal').classList.remove('show');
        };
        document.getElementById('modal').addEventListener('click',function(e){
            if(e.target===this)closeModal();
        });

        function renderEventDetail(d){
            var ev=d.event||{};
            var items=d.items||[];
            document.getElementById('modalTitle').textContent=ev.title||'(无标题)';

            var metaHtml=''
                + '<div class="meta-item"><div class="meta-label">严重度</div><div class="meta-value"><span class="sev-badge sev-'+esc(ev.severity)+'">'+(ev.severity||'p3').toUpperCase()+'</span></div></div>'
                + '<div class="meta-item"><div class="meta-label">情感</div><div class="meta-value">'+esc(ev.sentiment_label)+' '+fmtSentScore(ev.sentiment_score)+'</div></div>'
                + '<div class="meta-item"><div class="meta-label">首次发现</div><div class="meta-value">'+fmtTime(ev.first_seen_at)+'</div></div>'
                + '<div class="meta-item"><div class="meta-label">最近更新</div><div class="meta-value">'+fmtTime(ev.last_seen_at)+'</div></div>'
                + '<div class="meta-item"><div class="meta-label">关联条目</div><div class="meta-value">'+ev.item_count+' 条</div></div>'
                + '<div class="meta-item"><div class="meta-label">已推送</div><div class="meta-value">'+(ev.pushed_count||0)+' 次</div></div>';

            var summaryHtml=ev.summary ? '<p style="color:var(--text-secondary);line-height:1.6;margin-bottom:16px">'+esc(ev.summary)+'</p>' : '';

            var entitiesHtml='';
            if(ev.entities && ev.entities.length){
                entitiesHtml='<div style="margin-bottom:12px"><div class="meta-label">关联实体</div><div style="margin-top:4px">'
                    + ev.entities.map(function(e){return '<span class="meta-tag entity">'+esc(e)+'</span>';}).join(' ')
                    + '</div></div>';
            }

            var sourcesHtml='';
            if(ev.sources && ev.sources.length){
                sourcesHtml='<div style="margin-bottom:12px"><div class="meta-label">信源</div><div style="margin-top:4px">'
                    + ev.sources.map(function(s){return '<span class="meta-tag source">'+esc(s)+'</span>';}).join(' ')
                    + '</div></div>';
            }

            var timelineHtml='';
            if(ev.timeline && ev.timeline.length){
                timelineHtml='<div style="margin-bottom:12px"><div class="meta-label" style="margin-bottom:6px">时间线</div><div class="timeline-list">'
                    + ev.timeline.map(function(t){
                        var ts=t.ts ? fmtTime(t.ts) : '—';
                        return '<div class="timeline-row"><span class="timeline-ts">'+ts+'</span><span class="timeline-point">'+esc(t.point||'')+'</span></div>';
                    }).join('')
                    + '</div></div>';
            }

            var itemsHtml='<div class="meta-label" style="margin-bottom:6px">关联条目（'+items.length+'）</div>';
            if(items.length){
                itemsHtml+='<div class="items-list">'
                    + items.map(function(it){
                        return '<div class="item-row">'
                            + '<a class="item-title" href="'+esc(it.url)+'" target="_blank">'+esc(it.title||'(无标题)')+'</a>'
                            + '<div class="item-meta">'+fmtTime(it.captured_at)+' · '+esc(it.engine||'')+'</div>'
                            + '</div>';
                    }).join('')
                    + '</div>';
            }else{
                itemsHtml+='<div class="empty-state">暂无关联条目</div>';
            }

            document.getElementById('modalBody').innerHTML=''
                + '<div class="modal-meta">'+metaHtml+'</div>'
                + summaryHtml
                + entitiesHtml
                + sourcesHtml
                + timelineHtml
                + itemsHtml;
        }

        // 顶部红点跳转到本面板时滚动到公告区（公告区已上移到顶部，等价于到顶）
        window.openVentiDigests=function(){
            var sec=document.getElementById('digest');
            if(sec) sec.scrollIntoView({behavior:'smooth', block:'start'});
        };

        // ===== 风神日报公告区（最近 3 条展开式）+ 历史折叠区 =====
        var _ventiDigestSearch = '';
        var _ventiBulletinLimit = 3;        // 顶部公告显示最近 N 条
        var _ventiHistoryShown = false;

        async function loadVentiBulletins(){
            // 顶部公告区：最近 N 条 digest 直接展开式渲染（类似聊天气泡）
            var el = document.getElementById('ventiBulletins');
            if(!el) return;
            try{
                var qs = 'actor=' + encodeURIComponent('风神') + '&limit=' + _ventiBulletinLimit;
                var r = await fetch('/api/push_archive/list?' + qs);
                var d = await r.json();
                var records = d.records || [];
                var hint = document.getElementById('ventiBulletinHint');
                if(!records.length){
                    el.innerHTML = '<div class="digest-bulletins-empty">暂无风神日报<br><small>明早 7:00 cron 跑过后会出现，或在订阅卡片点「运行」</small></div>';
                    if(hint) hint.textContent = '';
                    return;
                }
                var unreadCount = records.filter(function(r){ return r.read_at == null; }).length;
                if(hint) hint.textContent = '· 最近 ' + records.length + ' 条' + (unreadCount > 0 ? ('，' + unreadCount + ' 未读') : '');
                el.innerHTML = records.map(function(rec){
                    var unread = rec.read_at == null;
                    var cls = unread ? 'digest-bulletin' : 'digest-bulletin read';
                    var dot = unread ? '<span class="db-unread-dot" title="未读"></span>' : '';
                    var markBtn = unread
                        ? '<button class="db-mark-read" onclick="event.stopPropagation();window.markVentiBulletinRead(\'' + esc(rec.id) + '\')">标记已读</button>'
                        : '';
                    return '<div class="' + cls + '" data-id="' + esc(rec.id) + '">'
                        + '<div class="db-head">'
                        + '<div class="db-head-left">'
                        + dot
                        + '<span class="db-source">' + esc(rec.source) + '</span>'
                        + '<span class="db-time">' + fmtTime(rec.created_at) + '</span>'
                        + '</div>'
                        + markBtn
                        + '</div>'
                        + '<div class="db-body">' + esc(rec.message_md || '') + '</div>'
                        + '</div>';
                }).join('');
            }catch(e){
                el.innerHTML = '<div class="digest-bulletins-empty">加载失败: ' + esc(String(e)) + '</div>';
            }
        }
        window.markVentiBulletinRead = async function(id){
            try{
                await fetch('/api/push_archive/' + encodeURIComponent(id) + '/read', {method: 'POST'});
                // 重新拉公告区（更新 read 样式 + 数字提示）
                await loadVentiBulletins();
                if(typeof window.refreshNavBadge === 'function') window.refreshNavBadge();
            }catch(e){}
        };
        window.toggleVentiHistory = function(){
            _ventiHistoryShown = !_ventiHistoryShown;
            document.getElementById('ventiHistoryWrap').style.display = _ventiHistoryShown ? 'block' : 'none';
            document.getElementById('ventiHistoryToggleBtn').textContent =
                _ventiHistoryShown ? '收起历史 ↑' : '📜 查看更多历史 ↓';
            if(_ventiHistoryShown) loadVentiDigests();
        };

        async function loadVentiDigests(){
            var listEl=document.getElementById('ventiDigestList');
            if(!listEl)return;
            listEl.innerHTML='<div class="push-empty">加载中...</div>';
            try{
                var qs='actor='+encodeURIComponent('风神')+'&limit=100';
                if(_ventiDigestSearch) qs+='&q='+encodeURIComponent(_ventiDigestSearch);
                var r=await fetch('/api/push_archive/list?'+qs);
                var d=await r.json();
                var records=d.records||[];
                if(!records.length){
                    listEl.innerHTML='<div class="push-empty">暂无风神日报'+(_ventiDigestSearch?'（搜索无结果）':'')+'</div>';
                    return;
                }
                listEl.innerHTML=records.map(function(rec){
                    var unread = rec.read_at == null;
                    var preview = (rec.message_md||'').slice(0,200);
                    return '<div class="push-item '+(unread?'unread':'')+'" data-id="'+esc(rec.id)+'" onclick="window.toggleVentiDigest(this)">'
                        + '<div class="push-item-head">'
                        + '<span class="push-item-source">'+esc(rec.source)+'</span>'
                        + '<span class="push-item-time">'+fmtTime(rec.created_at)+'</span>'
                        + '</div>'
                        + '<div class="push-item-preview">'+esc(preview)+'</div>'
                        + '<div class="push-item-body">'+esc(rec.message_md||'')+'</div>'
                        + '</div>';
                }).join('');
            }catch(e){
                listEl.innerHTML='<div class="push-empty">加载失败: '+esc(String(e))+'</div>';
            }
        }
        window.toggleVentiDigest = async function(el){
            var wasExpanded = el.classList.contains('expanded');
            // 收起其它已展开的（同 section 内只展开一条）
            document.querySelectorAll('#ventiDigestList .push-item.expanded').forEach(function(x){
                if(x!==el) x.classList.remove('expanded');
            });
            if(wasExpanded){ el.classList.remove('expanded'); return; }
            el.classList.add('expanded');
            if(el.classList.contains('unread')){
                var id = el.getAttribute('data-id');
                try{
                    await fetch('/api/push_archive/'+encodeURIComponent(id)+'/read', {method:'POST'});
                    el.classList.remove('unread');
                    // 更新 banner + 全局红点（refreshUnreadBadge 在 theme 里 30s 一刷，这里手动触发一次）
                    if(typeof window.refreshNavBadge==='function') window.refreshNavBadge();
                }catch(e){}
            }
        };
        window.markAllVentiRead = async function(){
            try{
                await fetch('/api/push_archive/read_all?actor='+encodeURIComponent('风神'),
                    {method:'POST'});
                document.querySelectorAll('#ventiDigestList .push-item.unread').forEach(function(el){
                    el.classList.remove('unread');
                });
                // 公告区也刷新（已读样式生效）
                await loadVentiBulletins();
                if(typeof window.refreshNavBadge==='function') window.refreshNavBadge();
            }catch(e){}
        };
        // 搜索框 Enter 触发
        document.addEventListener('keydown', function(e){
            if(e.key==='Enter' && document.activeElement && document.activeElement.id==='ventiDigestSearch'){
                _ventiDigestSearch = document.activeElement.value.trim();
                loadVentiDigests();
            }
        });
        // hash=#digest 时自动滚动到日报区（红点 / banner 跳转入口）
        window.addEventListener('load', function(){
            if(location.hash === '#digest'){
                setTimeout(function(){
                    var sec=document.getElementById('digest');
                    if(sec) sec.scrollIntoView({behavior:'smooth', block:'start'});
                }, 200);
            }
        });

        window.loadAll=function(){
            loadOverview();             // 4 张统计卡：始终全局
            loadSubBanner();            // 订阅级 banner：依 filterSub 显隐
            loadEvents();               // 事件列表：跟 filterSub
            loadTimeline();             // 折线/矩阵：跟 filterSub
            loadSources();              // 信源 Top：跟 filterSub
            loadVentiBulletins();       // 公告区：最近 3 篇展开卡片
            // 历史折叠区按需加载（用户点「查看更多」时才 loadVentiDigests）
        };
        // inline onchange 走 window 全局，IIFE 内函数必须显式挂出去
        window.loadEvents=loadEvents;
        // 切订阅时联动右栏 + banner（不刷新顶部 4 卡）
        window.onSubFilterChange=function(){
            loadEvents();
            loadTimeline();
            loadSources();
            loadSubBanner();
        };

        loadSubsForFilter().then(loadAll);
        // 30 秒自动刷新（不刷新事件列表，避免用户阅读时跳动）
        setInterval(function(){
            loadOverview();
            loadSubBanner();   // banner 含上次/下次跑时间，需要刷新
            loadTimeline();
            loadSources();
        }, 30000);
    })();
    </script>
"""


def build_sentiment_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon · 风神舆情看板</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + SENTIMENT_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("sentiment")
        + SENTIMENT_BODY
        + SENTIMENT_SCRIPT
        + """</body>
</html>"""
    )
