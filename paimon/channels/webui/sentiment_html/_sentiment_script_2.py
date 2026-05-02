"""SENTIMENT_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

SENTIMENT_SCRIPT_2 = r"""        };
        window.ventiJumpToday = function(){
            var inp = document.getElementById('ventiDateInput');
            if(!inp) return;
            inp.value = _todayStr();
            loadVentiBulletins();
        };
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
                _ventiHistoryShown ? '收起搜索 ↑' : '🔍 搜索历史 ↓';
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
                        + '<div class="push-item-body md-body">'+(window.renderMarkdown?window.renderMarkdown(rec.message_md||''):esc(rec.message_md||''))+'</div>'
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

        function _initVentiDate(){
            // 默认选中今天；用户切换后保留其选择，不被自动刷新覆盖
            var inp = document.getElementById('ventiDateInput');
            if(inp && !inp.value) inp.value = _todayStr();
        }

        window.loadAll=function(){
            loadOverview();             // 4 张统计卡：始终全局
            loadSubBanner();            // 订阅级 banner：依 filterSub 显隐
            loadEvents();               // 事件列表：跟 filterSub
            loadTimeline();             // 折线/矩阵：跟 filterSub
            loadSources();              // 信源 Top：跟 filterSub
            _initVentiDate();
            loadVentiBulletins();       // 公告区：当前选中日期（默认今天）
            // 搜索历史按需加载（用户点「搜索历史」时才 loadVentiDigests）
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
            // 仅在查看「今天」时刷新公告区（看历史日期时数据不变，免得抖）
            if(_currentDate() === _todayStr()) loadVentiBulletins();
        }, 30000);
    })();
    </script>
"""
