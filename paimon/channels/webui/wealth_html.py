"""岩神 · 理财（红利股追踪）面板

3 个 tab:
- 推荐选股: watchlist JOIN 最新 snapshot
- 评分排行: 最新 snapshot top 100
- 变化事件: 近 30 天 changes 时间轴

单股详情 modal: Chart.js 画 90 天评分折线 + 维度卡片 + 原始指标。
顶部: 统计卡片 + 触发扫描按钮组。
"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)


WEALTH_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1280px; margin: 0 auto; padding: 24px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .page-header .sub { font-size: 13px; color: var(--text-muted); margin-top: 4px; }

    .actions-bar { display: flex; gap: 8px; align-items: center; }
    .btn-scan {
        padding: 8px 14px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .btn-scan:hover { border-color: var(--gold-dark); color: var(--gold); }
    .btn-scan.primary {
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        color: #000; border: none; font-weight: 600;
    }
    .btn-scan:disabled { opacity: .4; cursor: not-allowed; }

    .stats-row { display: flex; gap: 16px; margin-bottom: 24px; }
    .stat-card {
        flex: 1; background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 20px; text-align: center;
    }
    .stat-num { font-size: 26px; font-weight: 700; color: var(--gold); }
    .stat-label { font-size: 12px; color: var(--text-muted); margin-top: 6px; }

    .tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--paimon-border); }
    .tab-btn {
        padding: 10px 20px; background: transparent; border: none; color: var(--text-muted);
        cursor: pointer; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active { color: var(--gold); border-bottom-color: var(--gold); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    .stock-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .stock-table th, .stock-table td {
        padding: 10px 12px; border-bottom: 1px solid var(--paimon-border); text-align: left;
    }
    .stock-table th {
        color: var(--gold); font-weight: 600; font-size: 12px; background: var(--paimon-panel);
        position: sticky; top: 0; z-index: 1;
    }
    .stock-table tbody tr { cursor: pointer; transition: background .1s; }
    .stock-table tbody tr:hover td { background: var(--paimon-panel); }
    .stock-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .stock-table td.code { color: var(--text-muted); font-family: monospace; font-size: 12px; }
    .stock-table .score-high { color: var(--status-success); font-weight: 600; }
    .stock-table .score-mid { color: var(--gold); }
    .stock-table .score-low { color: var(--text-muted); }
    .advice { font-size: 12px; color: var(--text-secondary); }

    /* 变化事件时间轴 */
    .change-list { display: flex; flex-direction: column; gap: 10px; }
    .change-item {
        background: var(--paimon-panel); border-left: 4px solid var(--paimon-border);
        border-radius: 6px; padding: 10px 16px; font-size: 13px;
    }
    .change-item.entered { border-left-color: var(--status-success); }
    .change-item.exited { border-left-color: var(--status-error); }
    .change-item.score-up { border-left-color: var(--star); }
    .change-item.score-down { border-left-color: var(--status-warning); }
    .change-meta { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

    /* Modal */
    .modal-backdrop {
        position: fixed; top:0; left:0; width:100%; height:100%;
        background: rgba(0,0,0,0.6); z-index: 100; display: none;
        align-items: center; justify-content: center; padding: 20px;
    }
    .modal-backdrop.show { display: flex; }
    .modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 12px; max-width: 880px; width: 100%; max-height: 90vh;
        overflow-y: auto; padding: 24px;
    }
    .modal-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px; }
    .modal-title { font-size: 20px; font-weight: 600; color: var(--text-primary); }
    .modal-sub { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
    .btn-close {
        background: transparent; border: none; color: var(--text-muted);
        font-size: 24px; cursor: pointer; padding: 0 8px;
    }
    .btn-close:hover { color: var(--text-primary); }

    .chart-wrap { margin-bottom: 20px; }
    .chart-wrap canvas { max-height: 260px; }
    .fallback-chart {
        background: var(--paimon-bg); padding: 12px; border-radius: 6px;
        font-size: 12px; color: var(--text-muted); font-family: monospace;
    }

    .dim-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 16px; }
    .dim-card {
        background: var(--paimon-bg); padding: 10px 12px; border-radius: 6px;
    }
    .dim-label { font-size: 11px; color: var(--text-muted); }
    .dim-value { font-size: 18px; font-weight: 600; color: var(--gold-light); }

    .raw-table { width: 100%; font-size: 13px; }
    .raw-table td { padding: 4px 8px; }
    .raw-table td:first-child { color: var(--text-muted); width: 40%; }

    .reasons-box {
        margin-top: 16px; padding: 12px; background: var(--paimon-bg); border-radius: 6px;
        font-size: 12px; line-height: 1.6; color: var(--text-secondary); white-space: pre-wrap;
    }
    .advice-box {
        margin-top: 10px; padding: 8px 12px; background: rgba(212,175,55,.08);
        border: 1px solid var(--gold-dark); border-radius: 6px;
        font-size: 13px; color: var(--gold-light);
    }

    .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 14px; }
    .loading { display: inline-block; padding: 2px 10px; color: var(--text-muted); font-size: 12px; }

    /* 未读岩神 digest banner */
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
"""


WEALTH_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>岩神 · 理财</h1>
                <div class="sub">A 股红利股追踪（评分 + 行业均衡 + 变化检测）</div>
            </div>
            <div class="actions-bar">
                <button class="btn-scan" id="btnRescore" onclick="triggerScan('rescore')">重评分</button>
                <button class="btn-scan" id="btnDaily" onclick="triggerScan('daily')">日更</button>
                <button class="btn-scan primary" id="btnFull" onclick="triggerScan('full')">全扫描</button>
                <button class="btn-scan" onclick="refreshAll()">刷新</button>
            </div>
        </div>

        <div id="digest" class="digest-section" style="margin-top:0">
            <div class="ds-head">
                <h2>📨 岩神 · 理财日报 <span id="zhongliBulletinHint" style="font-size:12px;color:var(--text-muted);font-weight:normal;margin-left:8px"></span></h2>
                <div class="ds-tools">
                    <button onclick="window.zhongliDayShift(-1)" title="前一天">←</button>
                    <input type="date" id="zhongliDateInput" onchange="window.zhongliDateChange()" />
                    <button onclick="window.zhongliDayShift(1)" title="后一天">→</button>
                    <button onclick="window.zhongliJumpToday()" title="跳到今天">今天</button>
                    <button onclick="window.markAllZhongliRead()">全部已读</button>
                </div>
            </div>
            <div class="digest-scroll">
                <div id="zhongliRunningBar" style="display:none"></div>
                <div id="zhongliBulletins">
                    <div class="digest-bulletins-empty">加载中...</div>
                </div>
                <div class="digest-history-toggle">
                    <button onclick="window.toggleZhongliHistory()" id="zhongliHistoryToggleBtn">
                        🔍 搜索历史 ↓
                    </button>
                </div>
                <div id="zhongliHistoryWrap" style="display:none;margin-top:12px">
                    <input id="zhongliDigestSearch" placeholder="搜索历史内容（Enter 应用）"
                        style="width:100%;padding:6px 10px;background:var(--paimon-bg);border:1px solid var(--paimon-border);border-radius:4px;color:var(--text-primary);font-size:12px;margin-bottom:10px" />
                    <div id="zhongliDigestList" class="digest-list">
                        <div class="push-empty">加载中...</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="stats-row">
            <div class="stat-card"><div class="stat-num" id="statWatchlist">-</div><div class="stat-label">推荐股池</div></div>
            <div class="stat-card"><div class="stat-num" id="statLatest">-</div><div class="stat-label">最新扫描</div></div>
            <div class="stat-card"><div class="stat-num" id="statP0P1" style="color:var(--status-warning)">-</div><div class="stat-label">近 7 天 P0+P1</div></div>
            <div class="stat-card"><div class="stat-num" id="statCronStatus">-</div><div class="stat-label">定时任务</div></div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('recommended',this)">推荐选股</button>
            <button class="tab-btn" onclick="switchTab('ranking',this)">评分排行</button>
            <button class="tab-btn" onclick="switchTab('changes',this)">变化事件</button>
        </div>

        <div id="recommended" class="tab-panel active">
            <div id="recEl"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="ranking" class="tab-panel">
            <div id="rankEl"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="changes" class="tab-panel">
            <div id="chgEl"><div class="empty-state">加载中...</div></div>
        </div>
    </div>

    <div class="modal-backdrop" id="modal" onclick="if(event.target.id==='modal')closeModal()">
        <div class="modal">
            <div class="modal-header">
                <div>
                    <div class="modal-title" id="modalTitle">-</div>
                    <div class="modal-sub" id="modalSub">-</div>
                </div>
                <button class="btn-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="chart-wrap">
                <canvas id="histChart"></canvas>
                <div class="fallback-chart" id="fallbackChart" style="display:none"></div>
            </div>
            <div class="dim-grid" id="dimGrid"></div>
            <table class="raw-table" id="rawTable"></table>
            <div class="advice-box" id="adviceBox"></div>
            <div class="reasons-box" id="reasonsBox"></div>
        </div>
    </div>
"""


WEALTH_SCRIPT = """
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script>
    (function(){
        function esc(s){return s===null||s===undefined?'':String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
        function scoreCls(s){
            if(s>=75)return 'score-high';
            if(s>=60)return 'score-mid';
            return 'score-low';
        }
        function fmt(n, d){ if(n===null||n===undefined)return '-'; return Number(n).toFixed(d||2); }
        function fmtCap(v){ return v>0?(v/1e8).toFixed(0)+'亿':'-'; }

        window.switchTab=function(key,btn){
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
            document.getElementById(key).classList.add('active');
            btn.classList.add('active');
        };

        // 顶部红点跳转到本面板时滚动到公告区（公告区已上移到顶部，等价于到顶）
        window.openZhongliDigests=function(){
            var sec=document.getElementById('digest');
            if(sec) sec.scrollIntoView({behavior:'smooth', block:'start'});
        };

        // ===== 岩神推送公告区 + 历史折叠区 =====
        function _esc(s){if(s==null)return '';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
        function _fmtTime(ts){
            if(!ts||ts<=0)return '-';
            var d=new Date(ts*1000);
            var mm=(d.getMonth()+1).toString().padStart(2,'0');
            var dd=d.getDate().toString().padStart(2,'0');
            var hh=d.getHours().toString().padStart(2,'0');
            var mi=d.getMinutes().toString().padStart(2,'0');
            return mm+'-'+dd+' '+hh+':'+mi;
        }
        var _zhongliDigestSearch = '';
        var _zhongliHistoryShown = false;

        function _todayStr(){
            var d = new Date();
            return d.getFullYear() + '-'
                + String(d.getMonth()+1).padStart(2,'0') + '-'
                + String(d.getDate()).padStart(2,'0');
        }
        function _dayBounds(dateStr){
            var p = (dateStr||'').split('-');
            if(p.length !== 3) return null;
            var since = new Date(+p[0], +p[1]-1, +p[2], 0, 0, 0).getTime() / 1000;
            return { since: since, until: since + 86400 };
        }
        function _shiftDate(dateStr, delta){
            var p = (dateStr||_todayStr()).split('-');
            var d = new Date(+p[0], +p[1]-1, +p[2], 0, 0, 0);
            d.setDate(d.getDate() + delta);
            return d.getFullYear() + '-'
                + String(d.getMonth()+1).padStart(2,'0') + '-'
                + String(d.getDate()).padStart(2,'0');
        }
        function _currentDate(){
            var inp = document.getElementById('zhongliDateInput');
            return (inp && inp.value) || _todayStr();
        }
        // 把 /api/wealth/running 返回的 progress dict 拼成中文文案。
        // progress 字段：stage/cur/total/mode + 各 stage 特有（valid/passed/success 等）
        function _formatScanProgress(p){
            if(!p) return '正在采集红利股数据…';
            var stage = p.stage || '';
            var mode = p.mode || '';
            var cur = p.cur || 0;
            var total = p.total || 0;
            var pct = (total > 0) ? ((cur / total * 100).toFixed(1) + '%') : '';
            // init 没有 cur/total，按 mode 给写实文案（fetch_board 第一步是拉全市场行业分类）
            if(stage === 'init'){
                if(mode === 'full')    return '获取全市场行业分类…';
                if(mode === 'daily')   return '准备 watchlist 数据…';
                if(mode === 'rescore') return '读取缓存…';
                return '准备中…';
            }
            var stageLabel = {
                'board': '全市场行情扫描',
                'board_codes': 'watchlist 行情扫描',
                'dividend': '股息数据抓取',
                'financial': '财务数据抓取',
                'scoring_dividend': '股息评分',
                'scoring_financial': '财务评分',
                'scoring_rescore': '重评分',
            }[stage] || stage;
            if(total <= 0) return stageLabel + '…';
            var extra = '';
            if(p.valid != null)   extra = '，已获取 ' + p.valid + ' 只';
            else if(p.success != null) extra = '，成功 ' + p.success + ' 只';
            else if(p.passed != null)  extra = '，通过 ' + p.passed + ' 只';
            return stageLabel + ' ' + cur + '/' + total + '（' + pct + '）' + extra;
        }

        var _zhongliBulletinsPollTimer = null;
        async function loadZhongliBulletins(){
            // 公告区：渲染当前选中日期的所有日报（对齐风神 sentiment 形态）
            var el = document.getElementById('zhongliBulletins');
            var runBar = document.getElementById('zhongliRunningBar');
            if(!el) return;
            var dateStr = _currentDate();
            var b = _dayBounds(dateStr);
            if(!b){
                el.innerHTML = '<div class="digest-bulletins-empty">日期格式错误</div>';
                return;
            }
            var isToday = dateStr === _todayStr();
            try{
                var qs = 'actor=' + encodeURIComponent('岩神')
                    + '&since=' + b.since + '&until=' + b.until + '&limit=50';
                // 并行拉公告 + 采集 running 状态（只在查看今天时有意义）
                var reqs = [fetch('/api/push_archive/list?' + qs).then(function(r){return r.json();})];
                if(isToday){
                    reqs.push(fetch('/api/wealth/running').then(function(r){return r.json();}).catch(function(){return {running:false};}));
                }
                var results = await Promise.all(reqs);
                var d = results[0];
                var runResp = results[1] || {running: false};
                var records = d.records || [];
                var running = !!runResp.running;
                var progress = runResp.progress || null;

                // 顶部采集状态条
                if(runBar){
                    if(running){
                        var progressText = _formatScanProgress(progress);
                        runBar.innerHTML = '<span class="dot"></span><span>岩神·' + progressText + '</span>';
                        runBar.className = 'digest-running-bar';
                        runBar.style.display = '';
                    }else{
                        runBar.style.display = 'none';
                        runBar.innerHTML = '';
                    }
                }

                var hint = document.getElementById('zhongliBulletinHint');
                if(!records.length){
                    var tip;
                    if(running){
                        tip = '采集中，请稍候…<br><small>完成后这里会自动展开当日日报</small>';
                    }else{
                        tip = isToday
                            ? '今天还没有日报<br><small>定时任务会在 19:00 / 月初 21:00 生成，也可点顶部"日更/全扫描"按钮手动触发</small>'
                            : '该日无日报<br><small>用 ← / → 切换其它日期</small>';
                    }
                    el.innerHTML = '<div class="digest-bulletins-empty">' + tip + '</div>';
                    if(hint) hint.textContent = '· ' + dateStr + (isToday?'（今天）':'');
                }else{
                    var unreadCount = records.filter(function(r){ return r.read_at == null; }).length;
                    if(hint) hint.textContent = '· ' + dateStr + (isToday?'（今天）':'')
                        + ' · ' + records.length + ' 篇'
                        + (unreadCount > 0 ? ('，' + unreadCount + ' 未读') : '');
                    el.innerHTML = records.map(function(rec){
                        var unread = rec.read_at == null;
                        var cls = unread ? 'digest-bulletin' : 'digest-bulletin read';
                        var dot = unread ? '<span class="db-unread-dot" title="未读"></span>' : '';
                        var markBtn = unread
                            ? '<button class="db-mark-read" onclick="event.stopPropagation();window.markZhongliBulletinRead(\\''+_esc(rec.id)+'\\')">标记已读</button>'
                            : '';
                        var runningChip = (running && isToday)
                            ? '<span class="db-running">采集中</span>' : '';
                        return '<div class="' + cls + '" data-id="' + _esc(rec.id) + '">'
                            + '<div class="db-head">'
                            + '<div class="db-head-left">'
                            + dot
                            + '<span class="db-source">' + _esc(rec.source) + '</span>'
                            + runningChip
                            + '<span class="db-time">' + _fmtTime(rec.created_at) + '</span>'
                            + '</div>'
                            + markBtn
                            + '</div>'
                            + '<div class="db-body md-body">' + (window.renderMarkdown ? window.renderMarkdown(rec.message_md || '') : _esc(rec.message_md || '')) + '</div>'
                            + '</div>';
                    }).join('');
                }

                // running 时 2s 后自动再刷（采集完成时自然出现日报）
                if(_zhongliBulletinsPollTimer){ clearTimeout(_zhongliBulletinsPollTimer); _zhongliBulletinsPollTimer = null; }
                if(running){
                    _zhongliBulletinsPollTimer = setTimeout(loadZhongliBulletins, 2000);
                }
            }catch(e){
                el.innerHTML = '<div class="digest-bulletins-empty">加载失败: ' + _esc(String(e)) + '</div>';
            }
        }
        window.zhongliDayShift = function(delta){
            var inp = document.getElementById('zhongliDateInput');
            if(!inp) return;
            inp.value = _shiftDate(inp.value || _todayStr(), delta);
            loadZhongliBulletins();
        };
        window.zhongliDateChange = function(){
            loadZhongliBulletins();
        };
        window.zhongliJumpToday = function(){
            var inp = document.getElementById('zhongliDateInput');
            if(!inp) return;
            inp.value = _todayStr();
            loadZhongliBulletins();
        };
        window.markZhongliBulletinRead = async function(id){
            try{
                await fetch('/api/push_archive/' + encodeURIComponent(id) + '/read', {method: 'POST'});
                await loadZhongliBulletins();
                if(typeof window.refreshNavBadge === 'function') window.refreshNavBadge();
            }catch(e){}
        };
        window.toggleZhongliHistory = function(){
            _zhongliHistoryShown = !_zhongliHistoryShown;
            document.getElementById('zhongliHistoryWrap').style.display = _zhongliHistoryShown ? 'block' : 'none';
            document.getElementById('zhongliHistoryToggleBtn').textContent =
                _zhongliHistoryShown ? '收起历史 ↑' : '📜 查看更多历史 ↓';
            if(_zhongliHistoryShown) loadZhongliDigests();
        };

        async function loadZhongliDigests(){
            var listEl=document.getElementById('zhongliDigestList');
            if(!listEl)return;
            listEl.innerHTML='<div class="push-empty">加载中...</div>';
            try{
                var qs='actor='+encodeURIComponent('岩神')+'&limit=100';
                if(_zhongliDigestSearch) qs+='&q='+encodeURIComponent(_zhongliDigestSearch);
                var r=await fetch('/api/push_archive/list?'+qs);
                var d=await r.json();
                var records=d.records||[];
                if(!records.length){
                    listEl.innerHTML='<div class="push-empty">暂无岩神推送'+(_zhongliDigestSearch?'（搜索无结果）':'')+'</div>';
                    return;
                }
                listEl.innerHTML=records.map(function(rec){
                    var unread = rec.read_at == null;
                    var preview = (rec.message_md||'').slice(0,200);
                    return '<div class="push-item '+(unread?'unread':'')+'" data-id="'+_esc(rec.id)+'" onclick="window.toggleZhongliDigest(this)">'
                        + '<div class="push-item-head">'
                        + '<span class="push-item-source">'+_esc(rec.source)+'</span>'
                        + '<span class="push-item-time">'+_fmtTime(rec.created_at)+'</span>'
                        + '</div>'
                        + '<div class="push-item-preview">'+_esc(preview)+'</div>'
                        + '<div class="push-item-body md-body">'+(window.renderMarkdown?window.renderMarkdown(rec.message_md||''):_esc(rec.message_md||''))+'</div>'
                        + '</div>';
                }).join('');
            }catch(e){
                listEl.innerHTML='<div class="push-empty">加载失败: '+_esc(String(e))+'</div>';
            }
        }
        window.toggleZhongliDigest = async function(el){
            var wasExpanded = el.classList.contains('expanded');
            document.querySelectorAll('#zhongliDigestList .push-item.expanded').forEach(function(x){
                if(x!==el) x.classList.remove('expanded');
            });
            if(wasExpanded){ el.classList.remove('expanded'); return; }
            el.classList.add('expanded');
            if(el.classList.contains('unread')){
                var id = el.getAttribute('data-id');
                try{
                    await fetch('/api/push_archive/'+encodeURIComponent(id)+'/read', {method:'POST'});
                    el.classList.remove('unread');
                    if(typeof window.refreshNavBadge==='function') window.refreshNavBadge();
                }catch(e){}
            }
        };
        window.markAllZhongliRead = async function(){
            try{
                await fetch('/api/push_archive/read_all?actor='+encodeURIComponent('岩神'),
                    {method:'POST'});
                document.querySelectorAll('#zhongliDigestList .push-item.unread').forEach(function(el){
                    el.classList.remove('unread');
                });
                // 公告区也刷新
                await loadZhongliBulletins();
                if(typeof window.refreshNavBadge==='function') window.refreshNavBadge();
            }catch(e){}
        };
        document.addEventListener('keydown', function(e){
            if(e.key==='Enter' && document.activeElement && document.activeElement.id==='zhongliDigestSearch'){
                _zhongliDigestSearch = document.activeElement.value.trim();
                loadZhongliDigests();
            }
        });
        window.addEventListener('load', function(){
            if(location.hash === '#digest'){
                setTimeout(function(){
                    var sec=document.getElementById('digest');
                    if(sec) sec.scrollIntoView({behavior:'smooth', block:'start'});
                }, 200);
            }
        });

        window.refreshAll=function(){
            loadStats(); loadRecommended(); loadRanking(); loadChanges();
            loadZhongliBulletins();
            // 历史折叠区按需加载（用户点「查看更多」时才 loadZhongliDigests）
        };

        async function loadStats(){
            try{
                var r=await fetch('/api/wealth/stats'); var d=await r.json();
                document.getElementById('statWatchlist').textContent=d.watchlist_count||0;
                document.getElementById('statLatest').textContent=d.latest_scan_date||'-';
                var p0 = d.p0_count_7d||0, p1 = d.p1_count_7d||0;
                var p0p1El = document.getElementById('statP0P1');
                p0p1El.textContent = (p0 + p1) > 0 ? (p0 + '/' + p1) : '0';
                p0p1El.style.color = p0 > 0 ? 'var(--status-error)' : (p1 > 0 ? 'var(--status-warning)' : 'var(--text-muted)');
                document.getElementById('statCronStatus').textContent=d.cron_enabled?'已启用':'未启用';
            }catch(e){}
        }

        function renderRow(r){
            var dy=(r.dividend_yield||0)*100;
            return '<tr onclick="openStock(\\''+esc(r.stock_code)+'\\',\\''+esc(r.stock_name)+'\\')">'
                + '<td class="code">'+esc(r.stock_code)+'</td>'
                + '<td>'+esc(r.stock_name)+'</td>'
                + '<td>'+esc(r.industry)+'</td>'
                + '<td class="num '+scoreCls(r.total_score)+'">'+fmt(r.total_score,1)+'</td>'
                + '<td class="num">'+fmt(dy,2)+'%</td>'
                + '<td class="num">'+fmt(r.pe,1)+'</td>'
                + '<td class="num">'+fmt(r.pb,2)+'</td>'
                + '<td class="num">'+fmtCap(r.market_cap)+'</td>'
                + '<td class="advice">'+esc(r.advice||'')+'</td>'
                + '</tr>';
        }

        function renderTable(rows){
            if(!rows||!rows.length){ return '<div class="empty-state">暂无数据</div>'; }
            return '<div style="overflow-x:auto"><table class="stock-table"><thead><tr>'
                + '<th>代码</th><th>股票</th><th>行业</th>'
                + '<th>评分</th><th>股息率</th><th>PE</th><th>PB</th><th>市值</th>'
                + '<th>建议</th>'
                + '</tr></thead><tbody>'
                + rows.map(renderRow).join('')
                + '</tbody></table></div>';
        }

        async function loadRecommended(){
            var el=document.getElementById('recEl');
            try{
                var r=await fetch('/api/wealth/recommended'); var d=await r.json();
                el.innerHTML=renderTable(d.stocks||[]);
            }catch(e){ el.innerHTML='<div class="empty-state">加载失败: '+esc(String(e))+'</div>'; }
        }

        async function loadRanking(){
            var el=document.getElementById('rankEl');
            try{
                var r=await fetch('/api/wealth/ranking?n=100'); var d=await r.json();
                el.innerHTML=renderTable(d.stocks||[]);
            }catch(e){ el.innerHTML='<div class="empty-state">加载失败</div>'; }
        }

        async function loadChanges(){
            var el=document.getElementById('chgEl');
            try{
                var r=await fetch('/api/wealth/changes?days=30'); var d=await r.json();
                var items=d.changes||[];
                if(!items.length){ el.innerHTML='<div class="empty-state">近 30 天无变化</div>'; return; }
                el.innerHTML='<div class="change-list">'
                    + items.map(function(c){
                        var cls='change-item';
                        if(c.event_type==='entered')cls+=' entered';
                        else if(c.event_type==='exited')cls+=' exited';
                        else if(c.event_type==='score_change'){
                            var diff=(c.new_value||0)-(c.old_value||0);
                            cls += diff>=0 ? ' score-up' : ' score-down';
                        }
                        var labelMap={'entered':'新入选','exited':'退出','score_change':'评分变化'};
                        return '<div class="'+cls+'" onclick="openStock(\\''+esc(c.stock_code)+'\\',\\''+esc(c.stock_name)+'\\')">'
                            + '<b>'+esc(labelMap[c.event_type]||c.event_type)+'</b>&nbsp;'
                            + esc(c.stock_name)+' ('+esc(c.stock_code)+')'
                            + '<div class="change-meta">'+esc(c.event_date)+' · '+esc(c.description||'')+'</div>'
                            + '</div>';
                    }).join('')
                    + '</div>';
            }catch(e){ el.innerHTML='<div class="empty-state">加载失败</div>'; }
        }

        var _histChart=null;

        window.openStock=async function(code, name){
            document.getElementById('modalTitle').textContent=name+' ('+code+')';
            document.getElementById('modalSub').textContent='加载中...';
            document.getElementById('modal').classList.add('show');
            try{
                var r=await fetch('/api/wealth/stock/'+encodeURIComponent(code)+'?days=90');
                var d=await r.json();
                var history=d.history||[];
                var current=d.current||null;

                if(current){
                    document.getElementById('modalSub').textContent=
                        current.industry+' · '+current.scan_date+' · '+fmt(current.total_score,1)+' 分';
                    // 维度卡片
                    document.getElementById('dimGrid').innerHTML=[
                        ['可持续性', current.sustainability_score, 30],
                        ['财务堡垒', current.fortress_score, 25],
                        ['估值安全', current.valuation_score, 20],
                        ['分红记录', current.track_record_score, 18],
                        ['盈利动能', current.momentum_score, 10],
                        ['惩罚', current.penalty, ''],
                    ].map(function(x){
                        return '<div class="dim-card"><div class="dim-label">'+x[0]+'</div>'
                            +'<div class="dim-value">'+fmt(x[1],0)+(x[2]?' / '+x[2]:'')+'</div></div>';
                    }).join('');
                    // 原始指标
                    var dy=(current.dividend_yield||0)*100;
                    document.getElementById('rawTable').innerHTML=[
                        ['股息率', fmt(dy,2)+'%'],
                        ['PE', fmt(current.pe,2)],
                        ['PB', fmt(current.pb,2)],
                        ['ROE', fmt(current.roe,2)+'%'],
                        ['市值', fmtCap(current.market_cap)],
                    ].map(function(x){ return '<tr><td>'+x[0]+'</td><td>'+x[1]+'</td></tr>'; }).join('');
                    document.getElementById('adviceBox').textContent=current.advice||'';
                    document.getElementById('reasonsBox').textContent=current.reasons||'';
                } else {
                    document.getElementById('modalSub').textContent='暂无快照';
                    document.getElementById('dimGrid').innerHTML='';
                    document.getElementById('rawTable').innerHTML='';
                    document.getElementById('adviceBox').textContent='';
                    document.getElementById('reasonsBox').textContent='';
                }

                // Chart.js 折线图
                var ctx=document.getElementById('histChart').getContext('2d');
                if(_histChart){ _histChart.destroy(); }
                if(history.length && typeof Chart !== 'undefined'){
                    document.getElementById('histChart').style.display='';
                    document.getElementById('fallbackChart').style.display='none';
                    _histChart=new Chart(ctx,{
                        type:'line',
                        data:{
                            labels:history.map(function(h){return h.scan_date;}),
                            datasets:[{
                                label:'总分',
                                data:history.map(function(h){return h.total_score;}),
                                borderColor:'#d4af37', backgroundColor:'rgba(212,175,55,.1)',
                                tension:.2, fill:true,
                            }]
                        },
                        options:{
                            responsive:true, maintainAspectRatio:false,
                            plugins:{legend:{labels:{color:'#d1d5db'}}},
                            scales:{
                                y:{beginAtZero:false, ticks:{color:'#9ca3af'}, grid:{color:'#3d3450'}},
                                x:{ticks:{color:'#9ca3af'}, grid:{color:'#3d3450'}},
                            },
                        },
                    });
                } else if(history.length){
                    // Chart.js 没加载到：降级文本
                    document.getElementById('histChart').style.display='none';
                    var fc=document.getElementById('fallbackChart');
                    fc.style.display='';
                    fc.textContent=history.map(function(h){return h.scan_date+' — '+fmt(h.total_score,1);}).join('\\n');
                } else {
                    document.getElementById('histChart').style.display='none';
                    document.getElementById('fallbackChart').style.display='';
                    document.getElementById('fallbackChart').textContent='无历史数据';
                }
            }catch(e){ document.getElementById('modalSub').textContent='加载失败: '+e; }
        };

        window.closeModal=function(){
            document.getElementById('modal').classList.remove('show');
            if(_histChart){ _histChart.destroy(); _histChart=null; }
        };

        window.triggerScan=async function(mode){
            var btnMap={rescore:'btnRescore', daily:'btnDaily', full:'btnFull'};
            var btn=document.getElementById(btnMap[mode]);
            if(!btn)return;
            if(mode==='full' && !confirm('全市场扫描耗时 15-20 分钟，确认启动？'))return;
            btn.disabled=true;
            var oldText=btn.textContent;
            btn.textContent='已触发...';
            try{
                var r=await fetch('/api/wealth/trigger', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({mode: mode}),
                });
                var d=await r.json();
                if(d.ok){
                    btn.textContent='运行中';
                    // 10 秒后刷新数据（rescore 足够完成；daily/full 要更久）
                    setTimeout(function(){
                        btn.disabled=false; btn.textContent=oldText;
                        refreshAll();
                    }, mode==='rescore'?8000:30000);
                } else {
                    alert('触发失败: '+(d.error||'unknown'));
                    btn.disabled=false; btn.textContent=oldText;
                }
            }catch(e){
                alert('触发失败: '+e);
                btn.disabled=false; btn.textContent=oldText;
            }
        };

        window.onload=function(){
            var inp = document.getElementById('zhongliDateInput');
            if(inp && !inp.value) inp.value = _todayStr();
            refreshAll();
        };
    })();
    </script>
"""


def build_wealth_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 理财</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + WEALTH_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("wealth")
        + WEALTH_BODY
        + WEALTH_SCRIPT
        + """</body>
</html>"""
    )
