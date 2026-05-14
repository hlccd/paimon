/* feed 页脚本 — 风神订阅 + 今日热点 + 近期回顾 + 订阅管理 + 站点登录 */

(function(){
        function esc(s){return s?s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}
        function fmtTime(ts){
            if(!ts||ts<=0)return'-';
            var d=new Date(ts*1000);
            var y=d.getFullYear(), mo=('0'+(d.getMonth()+1)).slice(-2), da=('0'+d.getDate()).slice(-2);
            var hh=('0'+d.getHours()).slice(-2), mm=('0'+d.getMinutes()).slice(-2);
            return y+'-'+mo+'-'+da+' '+hh+':'+mm;
        }
        window.switchTab=function(key,btn){
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.remove('active');});
            document.getElementById(key).classList.add('active');
            btn.classList.add('active');
            // 按需 lazy load 各 tab 数据（避免一开始就把所有 API 都打一遍）
            if(key==='hotspot') loadHotspot();
            if(key==='weekly') loadWeekly();
            if(key==='subs') loadSubs();
            if(key==='login') loadLoginOverview();
        };

        // 刷新当前 active tab
        window.refreshAll=function(){
            var active = document.querySelector('.tab-panel.active');
            if(!active) return;
            var key = active.id;
            if(key==='hotspot') loadHotspot();
            else if(key==='weekly') loadWeekly();
            else if(key==='subs') loadSubs();
            else if(key==='login') loadLoginOverview();
        };

        // ── 每日热点 ──（单条覆盖式：整张表只 1 条最新，无历史 picker）
        var _hotspotCurrent = null;
        var _hotspotRunning = false;  // 后端 inflight 状态（API running 字段，render 据此设按钮）
        var _hotspotPollTimer = null;

        async function loadHotspot(){
            try{
                var todayResp = await fetch('/api/feed/hotspot/today');
                var td = await todayResp.json();
                _hotspotCurrent = td.hotspot || null;
                _hotspotRunning = !!td.running;
                renderHotspot();
                // 后端在跑 → 2s 后自动 reload；崩溃恢复后下次 reload 拿到 false 自然停
                if(_hotspotPollTimer){ clearTimeout(_hotspotPollTimer); _hotspotPollTimer=null; }
                if(_hotspotRunning){
                    _hotspotPollTimer = setTimeout(loadHotspot, 2000);
                }
            }catch(e){
                document.getElementById('hotspotBody').innerHTML =
                    '<div class="sub-err">加载失败: '+esc(String(e))+'</div>';
            }
        }

        function renderHotspot(){
            var meta = document.getElementById('hotspotMeta');
            var body = document.getElementById('hotspotBody');
            var btn = document.getElementById('hotspotRunBtn');

            // 按钮 = 后端 running 的镜像（参考订阅卡 sub.running 模式）：
            // - 刷新页面 / 切 tab 时 loadHotspot 拿到最新 running → 按钮立即正确
            // - paimon 崩溃重启 inflight 默认 false → 按钮"立即跑"
            if(_hotspotRunning){
                btn.disabled = true;
                btn.textContent = '采集中… 约 1-2 分钟';
            } else {
                btn.disabled = false;
                btn.textContent = '▶ 立即跑';
            }

            if(!_hotspotCurrent){
                meta.textContent = _hotspotRunning ? '首次采集中…' : '尚未跑过';
                body.innerHTML = '<div class="empty-state" style="padding:24px;font-size:13px">'
                    + (_hotspotRunning ? '正在跑 6 源 + LLM 综合，约 1-2 分钟…' : '点 ▶ 立即跑 看看 6 源热榜综合（约 1-2 分钟）')
                    + '<br><span style="font-size:11px;opacity:.6">每天 11:00 / 17:00 cron 自动跑</span>'
                    + '</div>';
                return;
            }

            var ts = fmtTime(_hotspotCurrent.captured_at);
            var sourcesOk = _hotspotCurrent.sources_ok || '-';
            var sourcesFail = _hotspotCurrent.sources_fail
                ? ' · 失败: '+_hotspotCurrent.sources_fail : '';
            meta.innerHTML = esc(_hotspotCurrent.capture_date)
                + '<span style="margin-left:8px;color:var(--pm-text-muted);font-size:11px">'
                + esc('上次更新 '+ts+' · 源: '+sourcesOk+sourcesFail) + '</span>';

            var md = _hotspotCurrent.markdown || '';
            var html = '';
            if(md){
                if(typeof marked!=='undefined' && marked.parse){
                    try { html = marked.parse(md); }
                    catch(e){ html = '<pre>'+esc(md)+'</pre>'; }
                } else {
                    html = '<pre>'+esc(md)+'</pre>';
                }
            }
            body.innerHTML = '<div class="topic-md-body markdown-body">'+html+'</div>';
            body.querySelectorAll('a[href^="http"]').forEach(function(a){
                a.setAttribute('target','_blank');
                a.setAttribute('rel','noopener noreferrer');
            });
        }

        window.runHotspot = async function(){
            // 立即视觉反馈，不等后端 race（同订阅卡的 runSub 模式）
            var btn = document.getElementById('hotspotRunBtn');
            btn.disabled = true;
            btn.textContent = '采集中… 约 1-2 分钟';
            _hotspotRunning = true;
            try{
                // 不论 ok（新触发）还是 fail（"已在采集中"）—— loadHotspot 拿到 running=true 都正确
                await fetch('/api/feed/hotspot/run', {method:'POST'});
                await loadHotspot();  // 自带 2s 续 poll，跑完拿到 running=false 自动恢复
            }catch(e){
                _hotspotRunning = false;
                btn.disabled=false; btn.textContent='▶ 立即跑';
                window.pmToast.error('请求失败: '+e);
            }
        };


        // markdown 缓存：sub_id → {at: last_run_at, html: rendered}
        // loadSubs 重建 DOM 时同步注入缓存的 HTML，避免「加载中 → 有内容」闪烁；
        // 仅当 last_run_at 变了才重新 fetch 拉新内容
        var _mdCache = {};

        async function loadSubs(){
            var el=document.getElementById('subListEl');
            // 保存滚动位置：轮询期间整段 innerHTML 重写会让浏览器把滚动位置重置回顶
            var prevScrollY = window.scrollY;
            // 同时记下每张卡 markdown 区内部的 scrollTop（DOM 重建后 .topic-research-md 是新元素，scrollTop 默认 0）
            var prevMdScrolls = {};
            document.querySelectorAll('.topic-research-md').forEach(function(node){
                var sid = node.id.replace('topic-md-', '');
                if(sid && node.scrollTop > 0) prevMdScrolls[sid] = node.scrollTop;
            });
            try{
                var r=await fetch('/api/feed/subs'); var d=await r.json();
                var subs=d.subs||[];
                if(!subs.length){
                    el.innerHTML='<div class="empty-state">暂无订阅。在上方新增一条吧。</div>';
                    _mdCache = {};
                    return;
                }
                el.innerHTML=subs.map(function(s){
                    // 同步注入：cache hit 就直接渲染缓存的 markdown HTML；否则放占位
                    var cached = _mdCache[s.id];
                    var mdInner = (cached && cached.at === s.last_run_at && cached.html)
                        ? cached.html
                        : '<div class="empty-state" style="padding:18px;font-size:12px">加载中...</div>';
                    var cls='sub-card'+(s.enabled?'':' disabled');
                    var badge=s.enabled?'<span class="badge badge-enabled">启用</span>':'<span class="badge badge-disabled">停用</span>';
                    var runBadge=s.running?'<span class="badge badge-running">采集中</span>':'';
                    var err=s.last_error?'<div class="sub-err">⚠ '+esc(s.last_error.substring(0,160))+'</div>':'';
                    var runBtn=s.running
                        ? '<button class="btn-action" disabled>采集中…</button>'
                        : '<button class="btn-action" onclick="runSub(\''+s.id+'\')">▶ 运行</button>';
                    var actions = '<div class="sub-actions">'
                        + runBtn
                        + (s.enabled
                              ? '<button class="btn-action" onclick="toggleSub(\''+s.id+'\',false)">⏸ 停用</button>'
                              : '<button class="btn-action" onclick="toggleSub(\''+s.id+'\',true)">▶ 启用</button>')
                        + '<button class="btn-action danger" onclick="delSub(\''+s.id+'\')">✕ 删除</button>'
                        + '<button class="btn-action" onclick="toggleMdFold(\''+s.id+'\',this)" title="折叠/展开内容">▼</button>'
                        + '</div>';
                    return '<div class="'+cls+'" id="sub-'+esc(s.id)+'" data-sub-id="'+esc(s.id)+'">'
                        + '<div class="sub-info">'
                        +   '<div class="sub-query">'+esc(s.query)+' '+badge+' '+runBadge+'</div>'
                        +   '<div class="sub-meta">'
                        +     '<span>cron: '+esc(s.schedule_cron)+'</span>'
                        +     '<span>上次: '+fmtTime(s.last_run_at)+'</span>'
                        +   '</div>'
                        +   err
                        +   '<div class="topic-research-md" id="topic-md-'+esc(s.id)+'">'
                        +     mdInner
                        +   '</div>'
                        + '</div>'
                        + actions
                        + '</div>';
                }).join('');
                // 恢复外部页面滚动位置（用 instant 避免动画干扰）
                window.scrollTo({top: prevScrollY, behavior: 'instant'});
                // 恢复每张卡 markdown 区内部 scrollTop（cache HTML 已同步注入，scrollTop 数值有效）
                Object.keys(prevMdScrolls).forEach(function(sid){
                    var node = document.getElementById('topic-md-' + sid);
                    if(node) node.scrollTop = prevMdScrolls[sid];
                });
                // 异步拉每张卡 markdown：仅当 last_run_at 变了或没拉过才拉
                subs.forEach(function(s){
                    var cached = _mdCache[s.id];
                    if(!cached || cached.at !== s.last_run_at){
                        loadTopicResearchMd(s.id, s.last_run_at);
                    }
                    // 给链接外部跳转处理（缓存渲染过的也要重做，因为 DOM 是新建的）
                    if(cached && cached.html){
                        var slot = document.getElementById('topic-md-'+s.id);
                        if(slot) slot.querySelectorAll('a[href^="http"]').forEach(function(a){
                            a.setAttribute('target','_blank');
                            a.setAttribute('rel','noopener noreferrer');
                        });
                    }
                });
                // 清掉已不存在订阅的缓存项
                Object.keys(_mdCache).forEach(function(id){
                    if(!subs.some(function(s){return s.id===id;})) delete _mdCache[id];
                });
                // 有采集中 → 2s 自动再刷
                if(subs.some(function(s){return s.running;})){
                    if(_subsPollTimer) clearTimeout(_subsPollTimer);
                    _subsPollTimer=setTimeout(loadSubs, 2000);
                }
            }catch(e){ el.innerHTML='<div class="empty-state">加载失败: '+esc(String(e))+'</div>'; }
        }
        var _subsPollTimer=null;

        // 折叠/展开订阅卡的 markdown 内容
        window.toggleMdFold=function(subId, btn){
            var slot=document.getElementById('topic-md-'+subId);
            if(!slot) return;
            var folded=slot.classList.toggle('folded');
            btn.textContent = folded ? '▶' : '▼';
        };

        // 拉 GET /api/feed/topic_research/{sub_id} 渲染 markdown，结果写进 _mdCache
        async function loadTopicResearchMd(subId, lastRunAt){
            var slot=document.getElementById('topic-md-'+subId);
            if(!slot) return;
            try{
                var r=await fetch('/api/feed/topic_research/'+encodeURIComponent(subId));
                var d=await r.json();
                var rec=d.research;
                if(!rec || !rec.markdown){
                    var emptyHtml='<div class="empty-state" style="padding:14px;font-size:12px">'
                        + '暂无内容（cron 还没跑过 / 首次创建可点 ▶ 运行）</div>';
                    slot.innerHTML=emptyHtml;
                    _mdCache[subId]={at: lastRunAt, html: emptyHtml};
                    return;
                }
                var html='';
                if(typeof marked!=='undefined' && marked.parse){
                    try { html=marked.parse(rec.markdown); }
                    catch(e){ html='<pre>'+esc(rec.markdown)+'</pre>'; }
                } else {
                    html='<pre>'+esc(rec.markdown)+'</pre>';
                }
                var bodyHtml='<div class="topic-md-body markdown-body">'+html+'</div>';
                slot.innerHTML=bodyHtml;
                _mdCache[subId]={at: lastRunAt, html: bodyHtml};
                // 外部链接新窗口打开
                slot.querySelectorAll('a[href^="http"]').forEach(function(a){
                    a.setAttribute('target','_blank');
                    a.setAttribute('rel','noopener noreferrer');
                });
            }catch(e){
                slot.innerHTML='<div class="sub-err">加载失败: '+esc(String(e))+'</div>';
                // 失败不写 cache，下次会重试
            }
        }

        // 触发频率模式切换 → 显示对应输入控件
        window.onCronModeChange=function(){
            var mode=document.getElementById('formCronMode').value;
            document.getElementById('formCronTimeWrap').style.display = (mode==='daily'||mode==='weekday') ? '' : 'none';
            document.getElementById('formCronCustomWrap').style.display = mode==='custom' ? '' : 'none';
        };

        // 把 UI 模式 + 时间组合成 cron 表达式
        function buildCronExpr(){
            var mode=document.getElementById('formCronMode').value;
            if(mode==='custom') return document.getElementById('formCron').value.trim();
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
            if(!q){window.pmToast.warning('请填关键词');return;}
            try{
                var r=await fetch('/api/feed/subs',{
                    method:'POST',headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({query:q, cron:c})
                });
                var d=await r.json();
                if(d.ok){
                    document.getElementById('formQuery').value='';
                    var customEl=document.getElementById('formCron');
                    if(customEl) customEl.value='';
                    refreshAll();
                    window.pmToast.success('订阅已创建');
                }else{
                    window.pmToast.error('创建失败: '+(d.error||'unknown'));
                }
            }catch(e){window.pmToast.error('请求失败: '+e);}
        };

        window.toggleSub=async function(id,enable){
            try{
                await fetch('/api/feed/subs/'+encodeURIComponent(id),{
                    method:'PATCH',headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({enabled:enable})
                });
                refreshAll();
            }catch(e){window.pmToast.error('失败: '+e);}
        };

        window.delSub=async function(id){
            var ok = await window.pmModal.confirm({
                title: '删除订阅',
                message: '确认删除订阅？最近一份调研结果也会一起清掉。',
                confirmText: '删除',
                danger: true,
            });
            if(!ok) return;
            try{
                await fetch('/api/feed/subs/'+encodeURIComponent(id),{method:'DELETE'});
                refreshAll();
                window.pmToast.success('订阅已删除');
            }catch(e){window.pmToast.error('失败: '+e);}
        };

        window.runSub=async function(id){
            try{
                var r=await fetch('/api/feed/subs/'+encodeURIComponent(id)+'/run',{method:'POST'});
                var d=await r.json();
                if(d.ok){
                    loadSubs();
                }
                else window.pmToast.error('触发失败: '+(d.error||'unknown'));
            }catch(e){window.pmToast.error('失败: '+e);}
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
            // 默认 active tab = 今日热点；其他 tab 切到时再 lazy load
            loadHotspot();
            _scrollToSubFromHash();
        };

        // ── 近期回顾（整张表只 1 条，不展示历史）──
        var _weeklyCurrent = null;
        var _weeklyRunning = false;
        var _weeklyPollTimer = null;

        // 计算"今天往前 7 天"的范围（兜底，没数据时 meta 也能展示）
        function _defaultRange(){
            var today = new Date();
            var pad = function(n){ return ('0'+n).slice(-2); };
            var fmt = function(d){
                return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
            };
            var start = new Date(today.getTime() - 6*86400000);
            return {start: fmt(start), end: fmt(today)};
        }

        async function loadWeekly(){
            try{
                var r = await fetch('/api/feed/weekly/latest');
                var d = await r.json();
                _weeklyCurrent = d.weekly || null;
                _weeklyRunning = !!d.running;
                renderWeekly();
                if(_weeklyPollTimer){ clearTimeout(_weeklyPollTimer); _weeklyPollTimer=null; }
                if(_weeklyRunning){
                    _weeklyPollTimer = setTimeout(loadWeekly, 2000);
                }
            }catch(e){
                document.getElementById('weeklyBody').innerHTML =
                    '<div class="sub-err">加载失败: '+esc(String(e))+'</div>';
            }
        }

        function renderWeekly(){
            var meta = document.getElementById('weeklyMeta');
            var body = document.getElementById('weeklyBody');
            var btn = document.getElementById('weeklyRunBtn');

            if(_weeklyRunning){
                btn.disabled = true;
                btn.textContent = '生成中… 1-2 分钟';
            } else {
                btn.disabled = false;
                btn.textContent = '▶ 立即跑';
            }

            if(!_weeklyCurrent){
                var dr = _defaultRange();
                meta.textContent = '近期回顾 · '+dr.start+' ~ '+dr.end + (_weeklyRunning ? '（生成中…）' : '（还没跑过）');
                body.innerHTML = '<div class="empty-state" style="padding:24px;font-size:13px">'
                    + (_weeklyRunning ? '正在汇总过去 7 天 daily 数据，约 1-2 分钟…' : '点 ▶ 立即跑 综合过去 7 天已采集的 daily 数据')
                    + '<br><span style="font-size:11px;opacity:.6">每周六 10:00 cron 自动跑</span>'
                    + '</div>';
                return;
            }

            // 数据范围：优先用 range_start/end；老数据没字段时用前端默认
            var rs = _weeklyCurrent.range_start || _defaultRange().start;
            var re = _weeklyCurrent.range_end || _defaultRange().end;
            var dailyN = _weeklyCurrent.daily_count || 0;
            meta.innerHTML = esc('近期回顾 · '+rs+' ~ '+re)
                + '<span style="margin-left:8px;color:var(--pm-text-muted);font-size:11px">'
                + esc('已合 '+dailyN+'/14 次 daily · '+fmtTime(_weeklyCurrent.updated_at))
                + '</span>';

            var md = _weeklyCurrent.markdown || '';
            var html = '';
            if(md){
                if(typeof marked!=='undefined' && marked.parse){
                    try { html = marked.parse(md); }
                    catch(e){ html = '<pre>'+esc(md)+'</pre>'; }
                } else {
                    html = '<pre>'+esc(md)+'</pre>';
                }
            }
            body.innerHTML = '<div class="topic-md-body markdown-body">'+html+'</div>';
            body.querySelectorAll('a[href^="http"]').forEach(function(a){
                a.setAttribute('target','_blank');
                a.setAttribute('rel','noopener noreferrer');
            });
        }

        window.runWeekly = async function(){
            var btn = document.getElementById('weeklyRunBtn');
            btn.disabled = true;
            btn.textContent = '生成中… 1-2 分钟';
            _weeklyRunning = true;
            try{
                await fetch('/api/feed/weekly/run', {method:'POST'});
                await loadWeekly();
            }catch(e){
                _weeklyRunning = false;
                btn.disabled=false; btn.textContent='▶ 立即跑';
                window.pmToast.error('请求失败: '+e);
            }
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
                    var statusHtml, actionHtml;
                    if(s.requires_login === false){
                        // 免登录站点（B 站走官方 search API 不需要 cookies）
                        statusHtml = '<span class="site-status ok">🌐 无需 cookies（公开 API）</span>';
                        actionHtml = '<span style="color:var(--pm-text-muted);font-size:12px">已支持</span>';
                    } else if(s.configured){
                        var age = s.age_days != null ? s.age_days : '?';
                        statusHtml = '<span class="site-status ok">✅ 已配置　<small>' + age + ' 天前</small></span>';
                        actionHtml = '<button onclick="startSiteLogin(\'' + s.site + '\',\'' + esc(s.display_name) + '\')">续期</button>';
                    } else {
                        statusHtml = '<span class="site-status warn">⚪ 未配置</span>';
                        actionHtml = '<button onclick="startSiteLogin(\'' + s.site + '\',\'' + esc(s.display_name) + '\')">扫码登录</button>';
                    }
                    return '<div class="site-row">' +
                        '<div class="site-name">' + esc(s.display_name) + '</div>' +
                        '<div class="site-status">' + statusHtml + '</div>' +
                        '<div class="site-action">' + actionHtml + '</div>' +
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
            var _lastSt = null;   // 跟踪状态切换；仅在跨态边沿时重渲染 body 避免抹掉用户输入
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
            var renderSmsForm = function(){
                // 截图 + 验证码输入框 + 提交按钮；用户按提交后调 submitSms() POST 到后端
                var sid = _currentLoginSession;
                document.getElementById('qrModalBody').innerHTML =
                    '<div style="display:flex;flex-direction:column;gap:10px;width:100%">' +
                        '<img src="/api/feed/login/sms-form/' + sid + '?t=' + Date.now() +
                            '" style="max-width:100%;max-height:280px;border-radius:6px" />' +
                        '<div style="font-size:13px;color:#444">扫码后被站点要求短信验证。如未自动发送，请在手机端等待或在小红书 app 内重试；收到验证码后填入下方框：</div>' +
                        '<input id="smsCodeInput" type="text" inputmode="numeric" maxlength="8" placeholder="短信验证码" ' +
                            'style="padding:8px 10px;border:1px solid #bbb;border-radius:6px;font-size:15px" />' +
                        '<button id="smsSubmitBtn" onclick="submitSms()" ' +
                            'style="padding:8px 12px;border:0;border-radius:6px;background:var(--pm-primary);color:#000;cursor:pointer;font-weight:600">' +
                            '提交验证码</button>' +
                    '</div>';
                setTimeout(function(){
                    var inp = document.getElementById('smsCodeInput');
                    if(inp) inp.focus();
                }, 50);
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
                    } else if(st === 'awaiting_sms'){
                        // 仅在跨态边沿（首次进入 awaiting_sms 或从 sms_submitting 失败回退）重渲染，避免抹掉用户输入
                        if(_lastSt !== 'awaiting_sms') {
                            // 进 SMS 流程后必须停掉 QR 刷新 timer：refreshQr 守卫只看 _qrReady（已 true 不归零）不看 status，
                            // 5s 一次的 refreshQr 会把 SMS 表单 innerHTML 直接覆盖成 QR img，用户体验上像「弹窗消失」没法填
                            if(_qrRefreshTimer){ clearInterval(_qrRefreshTimer); _qrRefreshTimer = null; }
                            renderSmsForm();
                        }
                    } else if(st === 'sms_submitting'){
                        if(_lastSt !== 'sms_submitting'){
                            document.getElementById('qrModalBody').innerHTML =
                                '<div class="empty-state">正在提交验证码…后端 fill+click 后等 5s 看登录态</div>';
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
                    _lastSt = st;
                } catch(e){
                    // 暂忽略，继续轮询
                }
            };
            // SMS 提交：暴露到 window 给 onclick 用；session 关闭后失效
            window.submitSms = async function(){
                var sid = _currentLoginSession;
                if(!sid) return;
                var inp = document.getElementById('smsCodeInput');
                var btn = document.getElementById('smsSubmitBtn');
                var code = (inp && inp.value || '').trim();
                if(!code){ if(inp) inp.focus(); return; }
                if(btn){ btn.disabled = true; btn.textContent = '提交中…'; }
                try {
                    var res = await fetch('/api/feed/login/sms/' + sid, {
                        method:'POST',
                        headers:{'Content-Type':'application/json'},
                        body: JSON.stringify({code: code}),
                    });
                    var data = await res.json();
                    if(!data.ok){
                        if(btn){ btn.disabled = false; btn.textContent = '提交验证码'; }
                        window.pmToast.error('提交失败：' + (data.error || '未知'));
                    }
                    // 成功后状态会切到 sms_submitting，由 pollStatus 接管 UI
                } catch(e){
                    if(btn){ btn.disabled = false; btn.textContent = '提交验证码'; }
                    window.pmToast.error('提交失败：' + e.message);
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
