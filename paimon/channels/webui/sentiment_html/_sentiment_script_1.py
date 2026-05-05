"""SENTIMENT_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

SENTIMENT_SCRIPT_1 = r"""
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

        // ===== 风神日报公告区（按日期切换 · 默认今天）+ 搜索历史折叠区 =====
        var _ventiDigestSearch = '';
        var _ventiHistoryShown = false;

        function _todayStr(){
            var d = new Date();
            return d.getFullYear() + '-'
                + String(d.getMonth()+1).padStart(2,'0') + '-'
                + String(d.getDate()).padStart(2,'0');
        }
        function _dayBounds(dateStr){
            // 'YYYY-MM-DD' → 当地午夜起到次日午夜（不含），unix 秒
            var p = (dateStr||'').split('-');
            if(p.length!==3) return null;
            var since = new Date(+p[0], +p[1]-1, +p[2], 0, 0, 0).getTime()/1000;
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
            var inp = document.getElementById('ventiDateInput');
            return (inp && inp.value) || _todayStr();
        }

        var _ventiBulletinsPollTimer = null;
        // 自动 fallback 跳到的日期（今天 0 条时自动找最近一篇所在日）；用于 hint 显示「（最近一次）」标识。
        // 用户主动 ←/→/今天 切到别的日后自然不再匹配，不需手动重置。
        var _ventiFallbackTo = null;
        async function loadVentiBulletins(){
            // 公告区：渲染当前选中日期的所有 digest（一日多篇也展开）
            var el = document.getElementById('ventiBulletins');
            var runBar = document.getElementById('ventiRunningBar');
            if(!el) return;
            var dateStr = _currentDate();
            var b = _dayBounds(dateStr);
            if(!b){
                el.innerHTML = '<div class="digest-bulletins-empty">日期格式错误</div>';
                return;
            }
            var isToday = dateStr === _todayStr();
            try{
                var qs = 'actor=' + encodeURIComponent('风神')
                    + '&since=' + b.since + '&until=' + b.until + '&limit=50';
                // 并行拉公告 + 订阅 running 状态（只在查看今天时 running 有意义）
                var reqs = [fetch('/api/push_archive/list?' + qs).then(function(r){return r.json();})];
                if(isToday){
                    reqs.push(fetch('/api/feed/subs').then(function(r){return r.json();}).catch(function(){return {subs:[]};}));
                }
                var results = await Promise.all(reqs);
                var d = results[0];
                var subsResp = results[1] || {subs:[]};
                var records = d.records || [];
                var runningSubs = (subsResp.subs || []).filter(function(s){return s.running;});
                var runningIds = {};
                runningSubs.forEach(function(s){ runningIds[s.id] = s.query; });

                // 方案 A · fallback：今天 0 条且没在采集 → 自动跳到最近一篇所在日
                // （应对 cron 触发前看面板的空白窗口）
                if(isToday && !records.length && !runningSubs.length){
                    try{
                        var r2 = await fetch('/api/push_archive/list?actor='
                            + encodeURIComponent('风神') + '&limit=1');
                        var d2 = await r2.json();
                        if(d2.records && d2.records.length){
                            var dt = new Date(d2.records[0].created_at * 1000);
                            var fbDate = dt.getFullYear() + '-'
                                + String(dt.getMonth()+1).padStart(2,'0') + '-'
                                + String(dt.getDate()).padStart(2,'0');
                            if(fbDate !== dateStr){
                                var inpFb = document.getElementById('ventiDateInput');
                                if(inpFb) inpFb.value = fbDate;
                                _ventiFallbackTo = fbDate;
                                return loadVentiBulletins();
                            }
                        }
                    }catch(e){ /* fallback 失败不影响主流程 */ }
                }

                // 渲染顶部采集状态条
                if(runBar){
                    if(runningSubs.length){
                        var names = runningSubs.map(function(s){return esc(s.query);}).join('、');
                        runBar.innerHTML = '<span class="dot"></span>'
                            + '<span>正在采集：' + names + '（'+runningSubs.length+' 个订阅）</span>';
                        runBar.style.display = '';
                    }else{
                        runBar.style.display = 'none';
                        runBar.innerHTML = '';
                    }
                }

                var hint = document.getElementById('ventiBulletinHint');
                if(!records.length){
                    var tip;
                    if(runningSubs.length){
                        // 有正在跑的订阅：跑完自然会出现公告，不用再提示「没日报」
                        tip = '采集中，请稍候…<br><small>完成后这里会自动展开当日日报</small>';
                    }else{
                        tip = isToday
                            ? '今天还没有日报<br><small>每日 07:00 cron 会自动生成，也可在订阅卡片点「运行」</small>'
                            : '该日无日报<br><small>用 ← / → 切换其它日期</small>';
                    }
                    el.innerHTML = '<div class="digest-bulletins-empty">'+tip+'</div>';
                    if(hint) hint.textContent = '· ' + dateStr + (isToday?'（今天）':'');
                }else{
                    var unreadCount = records.filter(function(r){ return r.read_at == null; }).length;
                    var dateLabel = isToday ? '（今天）'
                        : (dateStr === _ventiFallbackTo ? '（最近一次）' : '');
                    if(hint) hint.textContent = '· ' + dateStr + dateLabel
                        + ' · ' + records.length + ' 篇'
                        + (unreadCount > 0 ? ('，' + unreadCount + ' 未读') : '');
                    el.innerHTML = records.map(function(rec){
                        var unread = rec.read_at == null;
                        var cls = unread ? 'digest-bulletin' : 'digest-bulletin read';
                        var dot = unread ? '<span class="db-unread-dot" title="未读"></span>' : '';
                        var markBtn = unread
                            ? '<button class="db-mark-read" onclick="event.stopPropagation();window.markVentiBulletinRead(\'' + esc(rec.id) + '\')">标记已读</button>'
                            : '';
                        var subId = rec.extra && rec.extra.sub_id;
                        var running = subId && runningIds[subId]
                            ? '<span class="db-running">采集中</span>' : '';
                        return '<div class="' + cls + '" data-id="' + esc(rec.id) + '">'
                            + '<div class="db-head">'
                            + '<div class="db-head-left">'
                            + dot
                            + '<span class="db-source">' + esc(rec.source) + '</span>'
                            + running
                            + '<span class="db-time">' + fmtTime(rec.created_at) + '</span>'
                            + '</div>'
                            + markBtn
                            + '</div>'
                            + '<div class="db-body md-body">' + (window.renderMarkdown ? window.renderMarkdown(rec.message_md || '') : esc(rec.message_md || '')) + '</div>'
                            + '</div>';
                    }).join('');
                }

                // 有正在采集的订阅 → 2s 后自动再刷一次
                if(_ventiBulletinsPollTimer){ clearTimeout(_ventiBulletinsPollTimer); _ventiBulletinsPollTimer = null; }
                if(runningSubs.length){
                    _ventiBulletinsPollTimer = setTimeout(loadVentiBulletins, 2000);
                }
            }catch(e){
                el.innerHTML = '<div class="digest-bulletins-empty">加载失败: ' + esc(String(e)) + '</div>';
            }
        }
        window.ventiDayShift = function(delta){
            var inp = document.getElementById('ventiDateInput');
            if(!inp) return;
            inp.value = _shiftDate(inp.value || _todayStr(), delta);
            loadVentiBulletins();
        };
        window.ventiDateChange = function(){
            loadVentiBulletins();"""
