"""WEALTH_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

WEALTH_SCRIPT_2 = """            var el=document.getElementById('recEl');
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

        var _scanPollTimer = null;
        var _scanStartTs = 0;            // trigger 那一刻的时间戳，秒级

        // 用「公告 created_at 比 trigger 时刻新」作为扫描完成主信号 ——
        // 比"running 由 true→false"更稳：极快的 rescore（1-2s）也能可靠抓到。
        // 兜底信号：last_error 变新（扫描异常没写公告，需要恢复按钮 + 提示）。
        // 30 分钟硬上限防泄漏。
        function _pollScanComplete(btn, oldText){
            if(_scanPollTimer){ clearTimeout(_scanPollTimer); _scanPollTimer = null; }
            var checkCount = 0;
            var poll = async function(){
                checkCount++;
                try{
                    var [listRes, runRes] = await Promise.all([
                        fetch('/api/push_archive/list?actor=' + encodeURIComponent('岩神') + '&limit=1')
                            .then(function(r){ return r.json(); }),
                        fetch('/api/wealth/running').then(function(r){ return r.json(); }),
                    ]);
                    var latest = (listRes.records || [])[0];
                    var newDigest = latest && latest.created_at >= _scanStartTs;
                    var newError = runRes.last_error && runRes.last_error.ts >= _scanStartTs;
                    if(newDigest || newError){
                        _scanPollTimer = null;
                        btn.disabled = false; btn.textContent = oldText;
                        refreshAll();
                        return;
                    }
                }catch(e){ /* 静默 */ }
                // 30 分钟硬上限
                if(checkCount > 1800){
                    _scanPollTimer = null;
                    btn.disabled = false; btn.textContent = oldText;
                    return;
                }
                // 前 6 次 500ms 高频抓极快任务，之后 2s
                _scanPollTimer = setTimeout(poll, checkCount < 6 ? 500 : 2000);
            };
            poll();
        }

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
                    // 记录 trigger 时刻，用作「公告变新 / last_error 变新」的判定基准
                    _scanStartTs = Date.now() / 1000;
                    // 1. 立即启动状态条（让用户即刻看到"准备中"）
                    loadZhongliBulletins();
                    // 2. 轮询「公告 created_at 比 _scanStartTs 新」→ 恢复按钮 + 刷数据
                    _pollScanComplete(btn, oldText);
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
            // 全局拦截外部链接（http/https）→ 新标签页打开（兜底所有不走 _renderMdSafe 的入口）
            document.body.addEventListener('click', function(e){
                var a = e.target && e.target.closest && e.target.closest('a[href]');
                if(!a) return;
                var href = a.getAttribute('href') || '';
                if(/^https?:\\/\\//i.test(href)){
                    e.preventDefault();
                    window.open(href, '_blank', 'noopener,noreferrer');
                }
            });
        };

        // ========= 用户关注股（我的关注 tab）=========

        function _renderSparkline(points){
            if(!points || points.length < 2){
                return '<span style="color:var(--text-muted);font-size:11px">(首次抓取中)</span>';
            }
            var n = points.length;
            var minV = Math.min.apply(null, points);
            var maxV = Math.max.apply(null, points);
            var rng = maxV - minV || 1;
            var W = 88, H = 28, pad = 2;
            var pts = points.map(function(v, i){
                var x = pad + (i/(n-1)) * (W - 2*pad);
                var y = H - pad - ((v - minV)/rng) * (H - 2*pad);
                return x.toFixed(1) + ',' + y.toFixed(1);
            }).join(' ');
            var trend = points[n-1] >= points[0] ? 'up' : 'down';
            return '<svg class="uw-spark ' + trend + '" viewBox="0 0 ' + W + ' ' + H + '"><polyline points="' + pts + '"/></svg>';
        }

        function _renderPctBar(p){
            if(p == null) return '<span class="uw-pct-label">-</span>';
            var left = Math.max(0, Math.min(99, p * 100));
            var pctLabel = (p * 100).toFixed(0) + '%';
            // 分位 < 30% 估值较低（绿）/ >= 70% 较高（红）/ 中间正常（灰）
            var cls = p < 0.3 ? 'low' : (p >= 0.7 ? 'high' : '');
            return '<span class="uw-pctbar" title="估值分位：低 0~30% / 正常 30~70% / 高 70~100%">'
                 + '<span class="marker" style="left:' + left.toFixed(1) + '%"></span></span>'
                 + '<span class="uw-pct-label ' + cls + '">' + pctLabel + '</span>';
        }

        function _renderChange(pct, alert){
            if(pct == null) return '<span class="uw-change flat">-</span>';
            var cls = pct > 0 ? 'pos' : (pct < 0 ? 'neg' : 'flat');
            var sign = pct > 0 ? '+' : '';
            var warn = (Math.abs(pct) >= (alert||3)) ? ' ⚠️' : '';
            return '<span class="uw-change ' + cls + '">' + sign + pct.toFixed(2) + '%' + warn + '</span>';
        }

        window.loadUserWatchlist = async function(){
            var el = document.getElementById('uwListEl');
            if(!el) return;
            try{
                var r = await fetch('/api/wealth/user_watch');
                var d = await r.json();
                var items = d.items || [];
                // 同步 _userWatchCodes，供推荐/排名渲染时打"已关注"
                _userWatchCodes = new Set(items.map(function(it){return _normCode(it.stock_code);}));
                // 同步 normalized code → name 映射；资讯面板用名字展示
                _userWatchCodeToName = {};
                items.forEach(function(it){
                    _userWatchCodeToName[_normCode(it.stock_code)] = it.stock_name || '';
                });
                if(items.length === 0){
                    el.innerHTML = '<div class="empty-state">暂无关注股。输入股票代码添加。</div>';
                    return;
                }
                var rows = items.map(function(it){
                    var spark = _renderSparkline(it.sparkline || []);
                    var chg = _renderChange(it.change_pct, it.alert_pct);
                    var pePct = _renderPctBar(it.pe_percentile);
                    var pbPct = _renderPctBar(it.pb_percentile);
                    var nameCell = esc(it.stock_name) || '<span style="color:var(--text-muted)">(待扫描)</span>';
                    var codeAttr = esc(it.stock_code);
                    var noteAttr = esc(it.note || '');
                    var alertAttr = (+it.alert_pct || 3).toFixed(1);
                    return ''
                        + '<tr class="uw-data-row" data-stock-code="' + codeAttr + '">'
                        + '<td class="code c-c">' + esc(it.stock_code) + '</td>'
                        + '<td class="c-c">' + nameCell + '</td>'
                        + '<td class="c-c">' + (it.price && it.price > 0 ? fmt(it.price) : '-') + '</td>'
                        + '<td class="c-c">' + chg + '</td>'
                        + '<td class="c-c">' + spark + '</td>'
                        + '<td class="c-c">' + (it.pe && it.pe > 0 ? '<span class="pe-num">' + fmt(it.pe) + '</span>' + pePct : '-') + '</td>'
                        + '<td class="c-c">' + (it.pb && it.pb > 0 ? '<span class="pe-num">' + fmt(it.pb) + '</span>' + pbPct : '-') + '</td>'
                        + '<td class="note c-c" title="' + noteAttr + '">' + esc(it.note) + '</td>'
                        + '<td class="c-c">±' + alertAttr + '%</td>'
                        + '<td class="c-c">'
                        + '<button class="uw-news-toggle-btn" data-stock-code="' + codeAttr + '" onclick="toggleStockNewsRow(this)">📰 资讯</button>'
                        + '<button class="uw-btn" data-code="' + codeAttr + '" data-alert="' + alertAttr + '" data-note="' + noteAttr + '" onclick="uwEdit(this)">编辑</button>'
                        + '<button class="uw-btn danger" data-code="' + codeAttr + '" onclick="uwRemove(this)">删除</button>'
                        + '</td>'
                        + '</tr>'
                        + '<tr class="uw-news-row" data-news-row-for="' + codeAttr + '">'
                        +   '<td colspan="10">'
                        +     '<div class="uw-news-wrap">'
                        +       '<div class="stock-news-line" data-news-line-for="' + codeAttr + '" data-stock-code="' + codeAttr + '">'
                        +         '<span class="news-toggle"><span class="dot"></span>加载中</span>'
                        +         '<span class="news-icon">📰</span>'
                        +         '<span class="news-text"><span class="meta">资讯订阅</span></span>'
                        +         '<button class="news-run" disabled>采集</button>'
                        +       '</div>'
                        +       '<div class="stock-news-pushes" data-pushes-for="' + codeAttr + '" data-stock-code="' + codeAttr + '" data-detailed="1"></div>'
                        +     '</div>'
                        +   '</td>'
                        + '</tr>';
                }).join('');
                el.innerHTML = ''
                    + '<table class="stock-table uw-table">'
                    + '<thead><tr>'
                    + '<th class="c-c">代码</th><th class="c-c">名称</th>'
                    + '<th class="c-c">最新价</th><th class="c-c">日涨跌</th>'
                    + '<th class="c-c">30 日走势</th>'
                    + '<th class="c-c">PE · 分位</th><th class="c-c">PB · 分位</th>'
                    + '<th class="c-c">备注</th><th class="c-c">阈值</th>'
                    + '<th class="c-c">操作</th>'
                    + '</tr></thead>'
                    + '<tbody>' + rows + '</tbody></table>';
                // 异步拉关注股订阅 + 推送数据，hydrate 资讯行（同水神模式）
                if(typeof loadStockSubs === 'function') loadStockSubs();
            }catch(e){
                el.innerHTML = '<div class="empty-state">加载失败: ' + esc(String(e)) + '</div>';
            }
        };

        // 首次 add 后后端异步拉 5 年历史 + 股票名，10~60s 不等。
        // 先立即刷一次（显示 "待扫描"占位），再分档轮询直到拿到数据（避免用户手动刷）。
        var _uwPollTimers = [];
        function _uwPollAfterAdd(){
            _uwPollTimers.forEach(clearTimeout);
            _uwPollTimers = [10, 25, 45, 75].map(function(s){
                return setTimeout(loadUserWatchlist, s * 1000);
            });
        }
        window.uwAdd = async function(){
            var code = document.getElementById('uwCodeInput').value.trim();
            var note = document.getElementById('uwNoteInput').value.trim();
            var alertPct = parseFloat(document.getElementById('uwAlertPctInput').value) || 3.0;
            if(!code){ alert('请输入股票代码'); return; }
            try{
                var r = await fetch('/api/wealth/user_watch/add', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({code: code, note: note, alert_pct: alertPct}),
                });
                var d = await r.json();
                if(!d.ok){ alert('添加失败: ' + (d.error || 'unknown')); return; }
                document.getElementById('uwCodeInput').value = '';
                document.getElementById('uwNoteInput').value = '';
                await loadUserWatchlist();
                // 推荐 + 排名同股按钮跟着刷"已关注"
                if(typeof loadRecommended === 'function') loadRecommended();
                if(typeof loadRanking === 'function') loadRanking();
                _uwPollAfterAdd();
            }catch(e){ alert('请求失败: ' + e); }
        };

        window.uwRemove = async function(btn){
            var code = btn.dataset.code;
            if(!confirm('确定删除 ' + code + ' 的关注吗？（价格历史也会清掉）')) return;
            try{
                var r = await fetch('/api/wealth/user_watch/remove', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json', 'X-Confirm':'yes'},
                    body: JSON.stringify({code: code}),
                });
                var d = await r.json();
                if(!d.ok){ alert('删除失败'); return; }
                await loadUserWatchlist();
                // 推荐 + 排名同股按钮跟着回到"+ 关注"
                if(typeof loadRecommended === 'function') loadRecommended();
                if(typeof loadRanking === 'function') loadRanking();
            }catch(e){ alert('请求失败: ' + e); }
        };

        window.uwEdit = async function(btn){
            var code = btn.dataset.code;
            var alertPct = btn.dataset.alert;
            var note = btn.dataset.note || '';
            var newAlert = prompt('波动阈值 (%)', alertPct);
            if(newAlert === null) return;
            var newNote = prompt('备注（留空清除）', note);
            if(newNote === null) return;
            try{
                var r = await fetch('/api/wealth/user_watch/update', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({
                        code: code,
                        alert_pct: parseFloat(newAlert) || 3.0,
                        note: newNote,
                    }),
                });
                var d = await r.json();
                if(!d.ok){ alert('更新失败'); return; }
                await loadUserWatchlist();
            }catch(e){ alert('请求失败: ' + e); }
        };

        window.uwRefreshAll = async function(){
            if(!confirm('立即抓取所有关注股最新数据？（可能要 10~60s）')) return;
            try{
                var r = await fetch('/api/wealth/user_watch/refresh', {method: 'POST'});
                var d = await r.json();
                if(!d.ok){ alert('触发失败'); return; }
            }catch(e){ alert('请求失败: ' + e); return; }
            // 抓取耗时不确定（每只股 baostock 几秒），多档轮询
            _uwPollAfterAdd();
        };

        // ========= 📰 关注股资讯订阅（同游戏面板模式） =========
        var _stockSubsCache = [];        // [{id, stock_code, query, enabled, last_run_at, last_error, item_count, running}, ...]
        var _stockPushesCache = {};      // {stock_code: [push records]}
        var _stockSubsPollTimer = null;

        function _fmtPushTime(ts){
            if(!ts) return '从未运行';
            var d = new Date(ts*1000);
            return (d.getMonth()+1)+'-'+d.getDate()+' '
                + d.getHours().toString().padStart(2,'0')+':'
                + d.getMinutes().toString().padStart(2,'0');
        }

        function _findStockSub(code){
            for(var i=0; i<_stockSubsCache.length; i++){
                if(_stockSubsCache[i].stock_code === code) return _stockSubsCache[i];
            }
            return null;
        }

        // 拉关注股订阅 + 推送数据（actor=岩神，按 source 'stock_watch:CODE' 分桶）
        // 自带递归轮询：检测到 sub.running 会 setTimeout 自调直到完成（同水神 game_html 模式）
        window.loadStockSubs = async function loadStockSubs(){
            try {
                var r = await fetch('/api/wealth/stock_subscriptions');
                var data = await r.json();
                _stockSubsCache = data.subs || [];
            } catch(e){ console.error('stock-subs fetch failed', e); _stockSubsCache = []; }

            try {
                // 按当前日期拉取（与公告区同一日窗口；日期切换时同时刷新左右两边）
                var dateStr = _currentDate();
                var b = _dayBounds(dateStr) || {};"""
