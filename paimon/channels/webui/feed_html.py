"""风神 · 信息流面板

两个 tab:
- 订阅管理：订阅列表 + 新增表单 + 启停/删/手动运行
- 信息流：feed_items 时间倒序，可按订阅过滤
"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)


FEED_CSS = """
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

    .stats-row { display: flex; gap: 16px; margin-bottom: 24px; }
    .stat-card {
        flex: 1; background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 20px; text-align: center;
    }
    .stat-num { font-size: 28px; font-weight: 700; color: var(--gold); }
    .stat-label { font-size: 13px; color: var(--text-muted); margin-top: 4px; }

    .tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid var(--paimon-border); }
    .tab-btn {
        padding: 10px 20px; background: transparent; border: none; color: var(--text-muted);
        cursor: pointer; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active { color: var(--gold); border-bottom-color: var(--gold); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    /* 订阅管理 tab */
    .sub-form {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 20px; margin-bottom: 24px;
    }
    .sub-form h3 { font-size: 16px; color: var(--text-primary); margin-bottom: 12px; }
    .form-row { display: grid; grid-template-columns: 2fr 1fr 120px auto; gap: 12px; align-items: end; }
    .form-field label { display: block; color: var(--text-muted); font-size: 12px; margin-bottom: 4px; }
    .form-field input, .form-field select {
        width: 100%; padding: 8px 12px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 6px;
        color: var(--text-primary); font-size: 14px;
    }
    .form-field input:focus, .form-field select:focus { outline: none; border-color: var(--gold); }
    .btn-primary {
        padding: 9px 20px; background: linear-gradient(135deg, var(--gold), var(--gold-light));
        color: #000; border: none; border-radius: 6px; cursor: pointer;
        font-size: 14px; font-weight: 600;
    }
    .form-hint { font-size: 12px; color: var(--text-muted); margin-top: 8px; }

    .sub-list { display: flex; flex-direction: column; gap: 12px; }
    .sub-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 16px 20px;
        display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: center;
    }
    .sub-card.disabled { opacity: .5; }
    /* 方案 D：从 /tasks 面板跳来时高亮对应订阅卡 2 秒 */
    .sub-card.highlight-flash {
        animation: sub-flash 2s ease-out;
        border-color: var(--gold);
    }
    @keyframes sub-flash {
        0%   { background: rgba(245,158,11,.18); box-shadow: 0 0 0 3px rgba(245,158,11,.35); }
        100% { background: var(--paimon-panel); box-shadow: none; }
    }
    .sub-info .sub-query { font-size: 16px; color: var(--text-primary); font-weight: 500; margin-bottom: 4px; }
    .sub-info .sub-meta { font-size: 12px; color: var(--text-muted); }
    .sub-info .sub-meta span { margin-right: 12px; }
    .sub-info .sub-err { color: var(--status-error); font-size: 12px; margin-top: 4px; }

    .sub-actions { display: flex; gap: 8px; }
    .btn-action {
        padding: 6px 12px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 4px; cursor: pointer; font-size: 12px;
    }
    .btn-action:hover { color: var(--gold); border-color: var(--gold-dark); }
    .btn-action.danger:hover { color: var(--status-error); border-color: var(--status-error); }

    /* 信息流 tab */
    .filter-bar {
        display: flex; gap: 12px; align-items: center; margin-bottom: 16px;
        padding: 12px 16px; background: var(--paimon-panel); border-radius: 8px;
    }
    .filter-bar label { color: var(--text-muted); font-size: 13px; }
    .filter-bar select {
        padding: 6px 12px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        color: var(--text-primary); font-size: 13px;
    }

    .feed-list { display: flex; flex-direction: column; gap: 10px; }
    .feed-item {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 8px; padding: 14px 18px;
        transition: border-color .15s;
    }
    .feed-item:hover { border-color: var(--gold-dark); }
    .feed-item .feed-title { font-size: 15px; margin-bottom: 4px; }
    .feed-item .feed-title a { color: var(--star-light); text-decoration: none; }
    .feed-item .feed-title a:hover { color: var(--gold); text-decoration: underline; }
    .feed-item .feed-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.5; margin: 6px 0; }
    .feed-item .feed-meta { font-size: 12px; color: var(--text-muted); }
    .feed-item .feed-meta span { margin-right: 12px; }

    .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 14px; }
    .badge {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 11px; font-weight: 500;
    }
    .badge-engine-bing { background: rgba(110,198,255,.12); color: var(--star); }
    .badge-engine-baidu { background: rgba(245,158,11,.15); color: var(--status-warning); }
    .badge-engine-other { background: var(--paimon-panel-light); color: var(--text-secondary); }
    .badge-enabled { background: rgba(16,185,129,.15); color: var(--status-success); }
    .badge-disabled { background: rgba(239,68,68,.15); color: var(--status-error); }
    .badge-running {
        background: rgba(255,180,80,.12); color: var(--gold);
        border: 1px solid rgba(255,180,80,.35);
        display: inline-flex; align-items: center; gap: 5px;
    }
    .badge-running::before {
        content: ''; width: 7px; height: 7px; border-radius: 50%;
        background: var(--gold);
        animation: paimon-pulse 1.1s ease-in-out infinite;
    }
    @keyframes paimon-pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: .35; transform: scale(.65); }
    }
    .btn-action:disabled { opacity: .6; cursor: wait; }

    /* 站点登录区 */
    .site-row { display:flex; align-items:center; padding:12px 16px; border-radius:10px; background:var(--paimon-panel); margin-bottom:8px; border:1px solid var(--paimon-border); }
    .site-row .site-name { flex: 0 0 120px; font-weight:600; color:var(--text-primary); }
    .site-row .site-status { flex:1; color:var(--text-secondary); font-size:13px; }
    .site-row .site-status.ok { color:var(--status-success); }
    .site-row .site-status.warn { color:var(--status-warning); }
    .site-row .site-action button { padding:6px 14px; border-radius:6px; cursor:pointer; border:1px solid var(--paimon-border); background:transparent; color:var(--gold); font-size:13px; }
    .site-row .site-action button:hover { background:var(--gold); color:var(--paimon-bg); }

    /* 登录扫码 modal */
    .qr-modal-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.65); display:flex; align-items:center; justify-content:center; z-index:9999; }
    .qr-modal-box { background:var(--paimon-panel); border:1px solid var(--paimon-border); border-radius:12px; min-width:340px; max-width:520px; padding:0; box-shadow:0 8px 32px rgba(0,0,0,.5); }
    .qr-modal-header { padding:14px 18px; border-bottom:1px solid var(--paimon-border); display:flex; justify-content:space-between; align-items:center; font-weight:600; color:var(--text-primary); }
    .qr-modal-close { background:none; border:0; font-size:22px; line-height:1; color:var(--text-secondary); cursor:pointer; }
    .qr-modal-close:hover { color:var(--text-primary); }
    .qr-modal-body { padding:18px; min-height:280px; display:flex; align-items:center; justify-content:center; color:var(--text-secondary); background:#fff; }
    .qr-modal-body img { max-width:100%; max-height:480px; border-radius:6px; image-rendering: crisp-edges; }
    .qr-modal-footer { padding:10px 18px; border-top:1px solid var(--paimon-border); font-size:13px; color:var(--text-muted); text-align:center; }
"""


FEED_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>🔔 订阅</h1>
                <div class="sub">话题订阅 + 定时采集 + 自动推送 · 想看事件聚合？<a href="/sentiment" style="color:var(--gold)">舆情看板 →</a></div>
            </div>
            <button class="refresh-btn" onclick="refreshAll()">刷新</button>
        </div>

        <div class="stats-row" id="statsRow">
            <div class="stat-card"><div class="stat-num" id="statSubs">-</div><div class="stat-label">订阅数</div></div>
            <div class="stat-card"><div class="stat-num" id="statToday">-</div><div class="stat-label">今日新增</div></div>
            <div class="stat-card"><div class="stat-num" id="statWeek">-</div><div class="stat-label">近 7 天</div></div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('subs',this)">订阅管理</button>
            <button class="tab-btn" onclick="switchTab('feed',this)">信息流</button>
            <button class="tab-btn" onclick="switchTab('login',this)">站点登录</button>
        </div>

        <div id="subs" class="tab-panel active">
            <div class="sub-form">
                <h3>新增订阅</h3>
                <div class="form-row">
                    <div class="form-field">
                        <label>关键词</label>
                        <input id="formQuery" placeholder="例: Claude 4.7 新特性" />
                    </div>
                    <div class="form-field">
                        <label>触发频率</label>
                        <select id="formCronMode" onchange="onCronModeChange()">
                            <option value="daily" selected>每天</option>
                            <option value="weekday">工作日</option>
                            <option value="hourly">每隔 N 小时</option>
                            <option value="custom">自定义 cron</option>
                        </select>
                    </div>
                    <div class="form-field" id="formCronTimeWrap">
                        <label>具体时间</label>
                        <input id="formCronTime" type="time" value="07:00" step="60" />
                    </div>
                    <div class="form-field" id="formCronHourlyWrap" style="display:none">
                        <label>间隔（小时）</label>
                        <input id="formCronHourly" type="number" min="1" max="24" value="6" />
                    </div>
                    <div class="form-field" id="formCronCustomWrap" style="display:none">
                        <label>cron 表达式</label>
                        <input id="formCron" placeholder="0 7 * * *" />
                    </div>
                    <div class="form-field">
                        <label>引擎</label>
                        <select id="formEngine">
                            <option value="">双引擎</option>
                            <option value="bing">Bing</option>
                            <option value="baidu">Baidu</option>
                        </select>
                    </div>
                    <button class="btn-primary" onclick="createSub()">创建订阅</button>
                </div>
                <div class="form-hint">默认每天上午 7:00 触发；推送会落到本面板和舆情看板的「日报公告」区</div>
            </div>
            <div id="subListEl" class="sub-list"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="feed" class="tab-panel">
            <div class="filter-bar">
                <label>订阅：</label>
                <select id="filterSub" onchange="loadFeed()">
                    <option value="">全部</option>
                </select>
                <label style="margin-left:16px">时间：</label>
                <select id="filterSince" onchange="loadFeed()">
                    <option value="0">全部</option>
                    <option value="86400">24 小时内</option>
                    <option value="604800">7 天内</option>
                    <option value="2592000">30 天内</option>
                </select>
            </div>
            <div id="feedListEl" class="feed-list"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="login" class="tab-panel">
            <div class="form-hint" style="margin-bottom:12px">
                各登录态爬虫（topic 知乎/微博/贴吧/虎扑/TapTap/小红书 等）需要的 cookies 在这里扫码取得。
                cookies 落到 <code>~/.paimon/cookies/&lt;site&gt;.json</code>，3-12 个月失效后回这里重扫。
            </div>
            <div id="loginListEl" class="sub-list"><div class="empty-state">加载中...</div></div>
        </div>
    </div>

    <!-- 扫码登录 modal -->
    <div id="qrModal" class="qr-modal-backdrop" style="display:none" onclick="if(event.target.id==='qrModal')closeQrModal()">
        <div class="qr-modal-box">
            <div class="qr-modal-header">
                <span id="qrModalTitle">扫码登录</span>
                <button class="qr-modal-close" onclick="closeQrModal()">×</button>
            </div>
            <div class="qr-modal-body" id="qrModalBody">
                <div class="empty-state">启动浏览器中...</div>
            </div>
            <div class="qr-modal-footer" id="qrModalFooter">
                <span id="qrModalStatus">pending</span>
            </div>
        </div>
    </div>
"""


FEED_SCRIPT = """
    <script>
    (function(){
        function esc(s){return s?s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}
        function fmtTime(ts){
            if(!ts||ts<=0)return'-';
            var d=new Date(ts*1000);
            var y=d.getFullYear(), mo=('0'+(d.getMonth()+1)).slice(-2), da=('0'+d.getDate()).slice(-2);
            var hh=('0'+d.getHours()).slice(-2), mm=('0'+d.getMinutes()).slice(-2);
            return y+'-'+mo+'-'+da+' '+hh+':'+mm;
        }
        function engineBadge(e){
            if(e==='bing')return '<span class="badge badge-engine-bing">Bing</span>';
            if(e==='baidu')return '<span class="badge badge-engine-baidu">百度</span>';
            return '<span class="badge badge-engine-other">'+esc(e||'?')+'</span>';
        }

        var currentSubs = [];

        window.switchTab=function(key,btn){
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
            document.getElementById(key).classList.add('active');
            btn.classList.add('active');
            if(key==='feed')loadFeed();
            if(key==='login')loadLoginOverview();
        };

        window.refreshAll=function(){ loadSubs(); loadStats(); if(document.getElementById('feed').classList.contains('active')) loadFeed(); };

        async function loadStats(){
            try{
                var r=await fetch('/api/feed/stats'); var d=await r.json();
                document.getElementById('statSubs').textContent=d.sub_count||0;
                document.getElementById('statToday').textContent=d.items_today||0;
                document.getElementById('statWeek').textContent=d.items_week||0;
            }catch(e){}
        }

        async function loadSubs(){
            var el=document.getElementById('subListEl');
            try{
                var r=await fetch('/api/feed/subs'); var d=await r.json();
                var subs=d.subs||[]; currentSubs=subs;
                // 同步过滤下拉
                var sel=document.getElementById('filterSub');
                sel.innerHTML='<option value="">全部</option>'+subs.map(function(s){return '<option value="'+esc(s.id)+'">'+esc(s.query)+'</option>';}).join('');
                if(!subs.length){ el.innerHTML='<div class="empty-state">暂无订阅。在上方新增，或用 /subscribe 指令创建</div>'; return; }
                el.innerHTML=subs.map(function(s){
                    var cls='sub-card'+(s.enabled?'':' disabled');
                    var badge=s.enabled?'<span class="badge badge-enabled">启用</span>':'<span class="badge badge-disabled">停用</span>';
                    var runBadge=s.running?'<span class="badge badge-running">采集中</span>':'';
                    var err=s.last_error?'<div class="sub-err">错: '+esc(s.last_error.substring(0,120))+'</div>':'';
                    var engine=s.engine||'双引擎';
                    var runBtn=s.running
                        ? '<button class="btn-action" disabled>采集中…</button>'
                        : '<button class="btn-action" onclick="runSub(\\''+s.id+'\\')">运行</button>';
                    return '<div class="'+cls+'" id="sub-'+esc(s.id)+'" data-sub-id="'+esc(s.id)+'">'
                        + '<div class="sub-info">'
                        +   '<div class="sub-query">'+esc(s.query)+' '+badge+' '+runBadge+'</div>'
                        +   '<div class="sub-meta">'
                        +     '<span>ID: '+esc(s.id.substring(0,8))+'</span>'
                        +     '<span>cron: '+esc(s.schedule_cron)+'</span>'
                        +     '<span>引擎: '+esc(engine)+'</span>'
                        +     '<span title="每次最多抓取条数">每次抓 '+(s.max_items||10)+' 条</span>'
                        +     '<span title="累计原始新闻 / 聚类后事件">累计 '+s.item_count+' 条 / '+(s.event_count||0)+' 个事件</span>'
                        +     '<span>上次: '+fmtTime(s.last_run_at)+'</span>'
                        +   '</div>'
                        +   err
                        + '</div>'
                        + '<div class="sub-actions">'
                        +   runBtn
                        +   (s.enabled
                              ? '<button class="btn-action" onclick="toggleSub(\\''+s.id+'\\',false)">停用</button>'
                              : '<button class="btn-action" onclick="toggleSub(\\''+s.id+'\\',true)">启用</button>')
                        +   '<button class="btn-action danger" onclick="delSub(\\''+s.id+'\\')">删除</button>'
                        + '</div>'
                        + '</div>';
                }).join('');
                // 有采集中的订阅 → 2s 后自动再刷一次，直到全部完成
                if(subs.some(function(s){return s.running;})){
                    if(_subsPollTimer) clearTimeout(_subsPollTimer);
                    _subsPollTimer=setTimeout(loadSubs, 2000);
                }
            }catch(e){ el.innerHTML='<div class="empty-state">加载失败: '+esc(String(e))+'</div>'; }
        }
        var _subsPollTimer=null;

        // 触发频率模式切换 → 显示对应输入控件
        window.onCronModeChange=function(){
            var mode=document.getElementById('formCronMode').value;
            document.getElementById('formCronTimeWrap').style.display = (mode==='daily'||mode==='weekday') ? '' : 'none';
            document.getElementById('formCronHourlyWrap').style.display = mode==='hourly' ? '' : 'none';
            document.getElementById('formCronCustomWrap').style.display = mode==='custom' ? '' : 'none';
        };

        // 把 UI 模式 + 时间组合成 cron 表达式
        function buildCronExpr(){
            var mode=document.getElementById('formCronMode').value;
            if(mode==='custom') return document.getElementById('formCron').value.trim();
            if(mode==='hourly'){
                var n=parseInt(document.getElementById('formCronHourly').value || '6', 10);
                if(isNaN(n)||n<1||n>24) n=6;
                return '0 */'+n+' * * *';
            }
            var t=document.getElementById('formCronTime').value || '07:00';
            var parts=t.split(':');
            var hh=parseInt(parts[0]||'7', 10);
            var mm=parseInt(parts[1]||'0', 10);
            if(isNaN(hh)) hh=7;
            if(isNaN(mm)) mm=0;
            if(mode==='weekday') return mm+' '+hh+' * * 1-5';
            return mm+' '+hh+' * * *';   // daily
        }

        window.createSub=async function(){
            var q=document.getElementById('formQuery').value.trim();
            var c=buildCronExpr();
            var eng=document.getElementById('formEngine').value;
            if(!q){alert('请填关键词');return;}
            try{
                var r=await fetch('/api/feed/subs',{
                    method:'POST',headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({query:q, cron:c, engine:eng})
                });
                var d=await r.json();
                if(d.ok){
                    document.getElementById('formQuery').value='';
                    // 自定义 cron 框清空，模式 + time 保留默认
                    var customEl=document.getElementById('formCron');
                    if(customEl) customEl.value='';
                    refreshAll();
                }else{
                    alert('创建失败: '+(d.error||'unknown'));
                }
            }catch(e){alert('请求失败: '+e);}
        };

        window.toggleSub=async function(id,enable){
            try{
                await fetch('/api/feed/subs/'+encodeURIComponent(id),{
                    method:'PATCH',headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({enabled:enable})
                });
                refreshAll();
            }catch(e){alert('失败: '+e);}
        };

        window.delSub=async function(id){
            if(!confirm('确认删除订阅？累计的信息流条目会一起清除。'))return;
            try{
                await fetch('/api/feed/subs/'+encodeURIComponent(id),{method:'DELETE'});
                refreshAll();
            }catch(e){alert('失败: '+e);}
        };

        window.runSub=async function(id){
            try{
                var r=await fetch('/api/feed/subs/'+encodeURIComponent(id)+'/run',{method:'POST'});
                var d=await r.json();
                if(d.ok){
                    // 卡片切「采集中」角标 + 按钮禁用；loadSubs 检测 running 会自动轮询
                    loadSubs();
                }
                else alert('触发失败: '+(d.error||'unknown'));
            }catch(e){alert('失败: '+e);}
        };

        window.loadFeed=async function(){
            var el=document.getElementById('feedListEl');
            var subId=document.getElementById('filterSub').value;
            var since=parseInt(document.getElementById('filterSince').value)||0;
            var qs=[]; if(subId)qs.push('sub_id='+encodeURIComponent(subId));
            if(since>0)qs.push('since='+since);
            try{
                var r=await fetch('/api/feed/items'+(qs.length?'?'+qs.join('&'):''));
                var d=await r.json();
                var items=d.items||[];
                if(!items.length){ el.innerHTML='<div class="empty-state">暂无条目</div>'; return; }
                var subMap={};currentSubs.forEach(function(s){subMap[s.id]=s.query;});
                el.innerHTML=items.map(function(it){
                    var title=it.title||'(无标题)';
                    var url=it.url||'';
                    var desc=it.description||'';
                    var subQuery=subMap[it.subscription_id]||'-';
                    var pushed=it.pushed_at?('已推 '+fmtTime(it.pushed_at)):'未推送';
                    return '<div class="feed-item">'
                        + '<div class="feed-title"><a href="'+esc(url)+'" target="_blank" rel="noopener">'+esc(title)+'</a></div>'
                        + (desc?'<div class="feed-desc">'+esc(desc.substring(0,300))+'</div>':'')
                        + '<div class="feed-meta">'
                        +   engineBadge(it.engine)
                        +   '<span>订阅: '+esc(subQuery)+'</span>'
                        +   '<span>采集: '+fmtTime(it.captured_at)+'</span>'
                        +   '<span>'+pushed+'</span>'
                        + '</div>'
                        + '</div>';
                }).join('');
            }catch(e){ el.innerHTML='<div class="empty-state">加载失败: '+esc(String(e))+'</div>'; }
        };

        // 方案 D：从 /tasks 点内部任务跳过来时 URL 带 #sub-<id>，定位到对应订阅卡
        function _scrollToSubFromHash(){
            var m=location.hash.match(/^#sub-(.+)$/);
            if(!m) return;
            var id=m[1];
            var tryScroll=function(retriesLeft){
                var card=document.getElementById('sub-'+id);
                if(card){
                    card.scrollIntoView({behavior:'smooth',block:'center'});
                    card.classList.add('highlight-flash');
                    setTimeout(function(){ card.classList.remove('highlight-flash'); }, 2000);
                }else if(retriesLeft>0){
                    // loadSubs 异步，render 未完成前再试
                    setTimeout(function(){ tryScroll(retriesLeft-1); }, 250);
                }
            };
            tryScroll(8);  // 最多等 2s
        }
        window.onload=function(){
            loadStats();
            loadSubs();
            _scrollToSubFromHash();
        };
        window.addEventListener('hashchange', _scrollToSubFromHash);

        // ─────── 站点登录区 ───────
        var _qrPollTimer = null;
        var _qrRefreshTimer = null;
        var _currentLoginSession = null;

        async function loadLoginOverview(){
            var el = document.getElementById('loginListEl');
            try {
                var res = await fetch('/api/feed/login/overview');
                if(!res.ok){ el.innerHTML='<div class="empty-state">加载失败 ('+res.status+')</div>'; return; }
                var data = await res.json();
                var sites = data.sites || [];
                if(!sites.length){ el.innerHTML='<div class="empty-state">无站点</div>'; return; }
                el.innerHTML = sites.map(function(s){
                    var statusHtml;
                    if(s.configured){
                        var age = s.age_days != null ? s.age_days : '?';
                        statusHtml = '<span class="site-status ok">✅ 已配置　<small>' + age + ' 天前</small></span>';
                    } else {
                        statusHtml = '<span class="site-status warn">⚪ 未配置</span>';
                    }
                    var btnText = s.configured ? '续期' : '扫码登录';
                    return '<div class="site-row">' +
                        '<div class="site-name">' + esc(s.display_name) + '</div>' +
                        '<div class="site-status">' + statusHtml + '</div>' +
                        '<div class="site-action"><button onclick="startSiteLogin(\\'' + s.site + '\\',\\'' + esc(s.display_name) + '\\')">' + btnText + '</button></div>' +
                        '</div>';
                }).join('');
            } catch(e){
                el.innerHTML = '<div class="empty-state">加载失败：' + esc(e.message) + '</div>';
            }
        }

        window.startSiteLogin = async function(site, displayName){
            // 打开 modal
            document.getElementById('qrModalTitle').textContent = '扫码登录 — ' + displayName;
            document.getElementById('qrModalBody').innerHTML = '<div class="empty-state">启动浏览器中（首次冷启动慢，约 5-10s）...</div>';
            document.getElementById('qrModalStatus').textContent = '初始化';
            document.getElementById('qrModal').style.display = 'flex';

            // 启会话
            try {
                var res = await fetch('/api/feed/login/start', {
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({site: site}),
                });
                var data = await res.json();
                if(!data.ok){
                    document.getElementById('qrModalBody').innerHTML = '<div class="empty-state">启动失败：' + esc(data.error || '未知') + '</div>';
                    return;
                }
                _currentLoginSession = data.session_id;
                _startQrLoop();
            } catch(e){
                document.getElementById('qrModalBody').innerHTML = '<div class="empty-state">启动失败：' + esc(e.message) + '</div>';
            }
        };

        function _startQrLoop(){
            _stopQrLoop();
            // baseline 阶段后端还没拍 QR，前端别提前 fetch /api/feed/login/qr/ 拿 404
            // 等 status='qr_ready' 后由 pollStatus 触发首次 refreshQr 并把 _qrReady 置 true
            var _qrReady = false;
            var refreshQr = function(){
                if(!_currentLoginSession || !_qrReady) return;
                var img = document.getElementById('qrImg');
                if(!img){
                    document.getElementById('qrModalBody').innerHTML =
                        '<img id="qrImg" src="/api/feed/login/qr/' + _currentLoginSession + '?t=' + Date.now() + '" />';
                } else {
                    img.src = '/api/feed/login/qr/' + _currentLoginSession + '?t=' + Date.now();
                }
            };
            // status：每 2s 一次
            var pollStatus = async function(){
                if(!_currentLoginSession) return;
                try {
                    var res = await fetch('/api/feed/login/status/' + _currentLoginSession);
                    var data = await res.json();
                    var st = data.status || 'unknown';
                    document.getElementById('qrModalStatus').textContent =
                        st + (data.elapsed != null ? '　(' + data.elapsed + 's / ' + data.timeout + 's)' : '');
                    if(st === 'baseline'){
                        // baseline 中：等匿名 cookies 名集合稳定，避免抢扫码把登录后 cookie 吃进 baseline
                        if(!_qrReady && !document.getElementById('qrImg')){
                            document.getElementById('qrModalBody').innerHTML =
                                '<div class="empty-state">等待页面状态稳定中…二维码即将出现（请勿提前扫码）</div>';
                        }
                    } else if(st === 'qr_ready'){
                        // 第一次进 qr_ready 时显示图
                        if(!_qrReady){
                            _qrReady = true;
                            refreshQr();
                        }
                    } else if(st === 'success'){
                        document.getElementById('qrModalBody').innerHTML = '<div class="empty-state" style="color:#7fcf7f">✅ 登录成功，cookies 已保存</div>';
                        _stopQrLoop();
                        setTimeout(function(){ closeQrModal(); loadLoginOverview(); }, 1500);
                    } else if(st === 'timeout'){
                        document.getElementById('qrModalBody').innerHTML = '<div class="empty-state" style="color:#e0b96a">⏱ 登录超时，请重试</div>';
                        _stopQrLoop();
                    } else if(st === 'failed' || st === 'not_found'){
                        document.getElementById('qrModalBody').innerHTML = '<div class="empty-state" style="color:#e57373">❌ ' + esc(data.error || st) + '</div>';
                        _stopQrLoop();
                    }
                } catch(e){
                    // 暂忽略，继续轮询
                }
            };
            _qrPollTimer = setInterval(pollStatus, 2000);
            _qrRefreshTimer = setInterval(refreshQr, 5000);   // _qrReady 守卫，baseline 阶段是 no-op
            pollStatus();
        }

        function _stopQrLoop(){
            if(_qrPollTimer){ clearInterval(_qrPollTimer); _qrPollTimer=null; }
            if(_qrRefreshTimer){ clearInterval(_qrRefreshTimer); _qrRefreshTimer=null; }
        }

        window.closeQrModal = function(){
            _stopQrLoop();
            _currentLoginSession = null;
            document.getElementById('qrModal').style.display = 'none';
        };

        window.loadLoginOverview = loadLoginOverview;
    })();
    </script>
"""


def build_feed_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 信息流</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + FEED_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("feed")
        + FEED_BODY
        + FEED_SCRIPT
        + """</body>
</html>"""
    )
