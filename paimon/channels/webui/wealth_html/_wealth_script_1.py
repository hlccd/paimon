"""WEALTH_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

WEALTH_SCRIPT_1 = """
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
    <script>
    (function(){
        function esc(s){return s===null||s===undefined?'':String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
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
        // 自动 fallback 跳到的日期（今天 0 条时自动找最近一篇所在日 → 跨周末也能找到）；
        // 仅用于在 hint 显示「（最近一次）」标识。用户主动 ←/→/今天 切到别的日后自然不再匹配，
        // 不需手动重置。
        var _zhongliFallbackTo = null;
        // 已被用户点关的 error.ts 集合（避免再次轮询又弹）
        var _zhongliDismissedErrors = {};
        window.dismissZhongliError = function(ts){
            _zhongliDismissedErrors[ts] = 1;
            var bar = document.getElementById('zhongliErrorBar');
            if(bar){ bar.style.display = 'none'; bar.innerHTML = ''; }
        };
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
                // 过滤掉关注股资讯推送（source 含 'stock_watch:'）—— 这些归右栏 newsPanel，不进左栏理财日报
                var records = (d.records || []).filter(function(r){
                    return (r.source || '').indexOf('stock_watch:') < 0;
                });
                var running = !!runResp.running;
                var progress = runResp.progress || null;
                var lastError = runResp.last_error || null;

                // 方案 A · fallback：今天 0 条且没在采集 → 自动跳到最近一篇所在日
                // （岩神 cron 仅工作日 19:00，周六/周一上午看会跨多天；用 limit 拿最近一条
                //  实际 created_at 决定，不需要手动算跨几天）
                if(isToday && !records.length && !running){
                    try{
                        var r2 = await fetch('/api/push_archive/list?actor='
                            + encodeURIComponent('岩神') + '&limit=10');
                        var d2 = await r2.json();
                        var fallbackRec = (d2.records || []).find(function(r){
                            return (r.source || '').indexOf('stock_watch:') < 0;
                        });
                        if(fallbackRec){
                            var dt = new Date(fallbackRec.created_at * 1000);
                            var fbDate = dt.getFullYear() + '-'
                                + String(dt.getMonth()+1).padStart(2,'0') + '-'
                                + String(dt.getDate()).padStart(2,'0');
                            if(fbDate !== dateStr){
                                var inpFb = document.getElementById('zhongliDateInput');
                                if(inpFb) inpFb.value = fbDate;
                                _zhongliFallbackTo = fbDate;
                                return loadZhongliBulletins();
                            }
                        }
                    }catch(e){ /* fallback 失败不影响主流程 */ }
                }

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

                // 错误横幅（10 分钟内，未被用户关闭过）
                var errBar = document.getElementById('zhongliErrorBar');
                if(errBar){
                    var shouldShow = lastError && !_zhongliDismissedErrors[lastError.ts];
                    if(shouldShow){
                        var ageStr = lastError.age_seconds < 60
                            ? lastError.age_seconds + ' 秒前'
                            : Math.floor(lastError.age_seconds / 60) + ' 分钟前';
                        errBar.innerHTML =
                            '<span class="err-msg">❌ <strong>' + _esc(lastError.mode) + '</strong> 扫描失败（'
                            + ageStr + '）：' + _esc(lastError.message) + '</span>'
                            + '<button class="err-close" title="关闭" onclick="window.dismissZhongliError('
                            + lastError.ts + ')">✕</button>';
                        errBar.className = 'digest-error-bar';
                        errBar.style.display = '';
                    }else{
                        errBar.style.display = 'none';
                        errBar.innerHTML = '';
                    }
                }

                var hint = document.getElementById('zhongliBulletinHint');
                if(!records.length){
                    var tip;
                    if(running){
                        tip = '采集中，请稍候…<br><small>完成后这里会自动展开当日日报</small>';
                    }else{
                        tip = isToday
                            ? '今天还没有日报<br><small>启用定时后会在 19:00 / 月初 21:00 自动生成（见顶部 stat 卡"定时任务"状态），也可随时点顶部"日更/全扫描"按钮手动触发</small>'
                            : '该日无日报<br><small>用 ← / → 切换其它日期</small>';
                    }
                    el.innerHTML = '<div class="digest-bulletins-empty">' + tip + '</div>';
                    if(hint) hint.textContent = '· ' + dateStr + (isToday?'（今天）':'');
                }else{
                    var unreadCount = records.filter(function(r){ return r.read_at == null; }).length;
                    var dateLabel = isToday ? '（今天）'
                        : (dateStr === _zhongliFallbackTo ? '（最近一次）' : '');
                    if(hint) hint.textContent = '· ' + dateStr + dateLabel
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
                            + '<span class="db-time" title="同日多次扫描会刷新此时间">最后更新 ' + _fmtTime(rec.created_at) + '</span>'
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
        // 日期切换：同时刷新左公告 + 右资讯（两面板共享同一日窗口）
        function _reloadDayPanels(){
            loadZhongliBulletins();
            if(typeof loadStockSubs === 'function') loadStockSubs();
        }
        window.zhongliDayShift = function(delta){
            var inp = document.getElementById('zhongliDateInput');
            if(!inp) return;
            inp.value = _shiftDate(inp.value || _todayStr(), delta);
            _reloadDayPanels();
        };
        window.zhongliDateChange = function(){
            _reloadDayPanels();
        };
        window.zhongliJumpToday = function(){
            var inp = document.getElementById('zhongliDateInput');
            if(!inp) return;
            inp.value = _todayStr();
            _reloadDayPanels();
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
                // 历史搜索区只显示理财日报，剔除关注股资讯（归右栏 newsPanel）
                var records=(d.records||[]).filter(function(rec){
                    return (rec.source||'').indexOf('stock_watch:') < 0;
                });
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

        // 已关注 code 的集合，渲染推荐/排名时知道哪些股票已经加入了 → "+ 关注" 按钮直接 added 态
        // 比较时统一 normalize 成纯 6 位数字（去前缀/点/空格/大小写），避免格式差异（sh.600519 vs SH.600519 vs 600519）漏判
        function _normCode(c){
            return String(c||'').toLowerCase().replace(/\\s/g, '').replace(/^(sh|sz|bj)\\.?/, '');
        }
        var _userWatchCodes = new Set();
        // normalized code → stock_name 映射（资讯面板显示名字而不是代码）
        var _userWatchCodeToName = {};

        window.refreshAll=async function(){
            loadStats();
            loadZhongliBulletins(); loadScanScope();
            // 先 await loadUserWatchlist 拿到 _userWatchCodes，再渲染推荐/排名（已关注的会标 added）
            await loadUserWatchlist();
            loadRecommended(); loadRanking(); loadChanges();
            // 历史折叠区按需加载（用户点「查看更多」时才 loadZhongliDigests）
        };

        // 加载日更/全扫描按钮下方的范围文案（候选池 N 只 / 全市场 ~5500）
        async function loadScanScope(){
            try{
                var r = await fetch('/api/wealth/scan_scope');
                var d = await r.json();
                var dailyHint = document.getElementById('dailyHint');
                var fullHint  = document.getElementById('fullHint');
                if(dailyHint){
                    var n = d.candidates_size || 0;
                    dailyHint.textContent = n > 0 ? ('候选池 ' + n + ' 只') : '候选池 -';
                }
                if(fullHint){
                    var f = d.full_market_size || 5500;
                    fullHint.textContent = '全市场 ~' + f;
                }
            }catch(e){ /* 静默：失败就显示初始 placeholder */ }
        }

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
            var added = _userWatchCodes.has(_normCode(r.stock_code));
            var btnCls = 'addw-btn' + (added ? ' added' : '');
            var btnText = added ? '已关注' : '+ 关注';
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
                + '<td class="row-actions">'
                +   '<button class="'+btnCls+'" data-code="'+esc(r.stock_code)+'" '
                +     'onclick="event.stopPropagation();addToWatchlist(this)" '
                +     (added ? 'disabled ' : '')
                +     'title="'+(added?'已在我的关注':'加到我的关注')+'">'+btnText+'</button>'
                + '</td>'
                + '</tr>';
        }

        function renderTable(rows){
            if(!rows||!rows.length){ return '<div class="empty-state">暂无数据</div>'; }
            return '<div style="overflow-x:auto"><table class="stock-table"><thead><tr>'
                + '<th>代码</th><th>股票</th><th>行业</th>'
                + '<th>评分</th><th>股息率</th><th>PE</th><th>PB</th><th>市值</th>'
                + '<th>建议</th>'
                + '<th></th>'
                + '</tr></thead><tbody>'
                + rows.map(renderRow).join('')
                + '</tbody></table></div>';
        }

        // 推荐选股 / 排名 → 一键加入"我的关注"，**严格对齐 uwAdd**（手动添加）的链路
        window.addToWatchlist = async function(btn){
            if(btn.classList.contains('added')) return;
            var code = btn.dataset.code;
            if(!code){ alert('股票代码缺失'); return; }
            btn.disabled = true;
            var old = btn.textContent;
            btn.textContent = '...';
            try{
                var r = await fetch('/api/wealth/user_watch/add', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({code: code, note: '', alert_pct: 3.0}),
                });
                var d = await r.json();
                // 严格对齐 uwAdd：所有 not-ok 都报 alert（不再 409 静默处理）
                if(!d.ok){
                    alert('添加失败: ' + (d.error || 'unknown'));
                    btn.disabled = false; btn.textContent = old;
                    return;
                }
                // 成功路径与 uwAdd 完全等价：await loadUserWatchlist + _uwPollAfterAdd
                _userWatchCodes.add(_normCode(code));
                await loadUserWatchlist();
                // 推荐 + 排名表里同股按钮也要刷成"已关注"（用户当前可能在另一 tab）
                if(typeof loadRecommended === 'function') loadRecommended();
                if(typeof loadRanking === 'function') loadRanking();
                _uwPollAfterAdd();
            }catch(e){
                alert('请求失败: ' + e);
                btn.disabled = false; btn.textContent = old;
            }
        };

        async function loadRecommended(){"""
