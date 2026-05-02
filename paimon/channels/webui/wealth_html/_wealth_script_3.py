"""WEALTH_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

WEALTH_SCRIPT_3 = """                var qs = 'actor=' + encodeURIComponent('岩神') + '&limit=200';
                if(b.since != null) qs += '&since=' + b.since + '&until=' + b.until;
                var rp = await fetch('/api/push_archive/list?' + qs);
                var dp = await rp.json();
                var records = dp.records || [];
                _stockPushesCache = {};
                records.forEach(function(rec){
                    // source 形如 '岩神·stock_watch:600519' —— 包含 'stock_watch:CODE'
                    var src = rec.source || '';
                    var marker = 'stock_watch:';
                    var idx = src.indexOf(marker);
                    if(idx < 0) return;
                    var code = src.substring(idx + marker.length).trim();
                    if(!code) return;
                    if(!_stockPushesCache[code]) _stockPushesCache[code] = [];
                    _stockPushesCache[code].push(rec);
                });
            } catch(e){ console.error('stock-pushes fetch failed', e); _stockPushesCache = {}; }

            _hydrateStockNewsLines();
            _renderStockNewsPanel();

            // 有采集中的订阅 → 2s 后自动再刷一次（递归轮询直到全部完成）
            if(_stockSubsCache.some(function(s){return s.running;})){
                if(_stockSubsPollTimer) clearTimeout(_stockSubsPollTimer);
                _stockSubsPollTimer = setTimeout(loadStockSubs, 2000);
            }
        };

        // 渲染右栏「关注股资讯」面板（与左侧公告独立的兄弟面板，单列卡片堆叠）
        // _stockPushesCache 已按当前日期窗口拉取，这里只做平铺 + 倒序渲染
        function _renderStockNewsPanel(){
            var listEl = document.getElementById('newsPanelList');
            var hintEl = document.getElementById('newsPanelHint');
            if(!listEl) return;
            var dateStr = _currentDate();
            var isToday = dateStr === _todayStr();
            var all = [];
            Object.keys(_stockPushesCache || {}).forEach(function(code){
                (_stockPushesCache[code] || []).forEach(function(p){
                    all.push({code: code, push: p});
                });
            });
            all.sort(function(a, b){
                return (b.push.created_at || 0) - (a.push.created_at || 0);
            });
            if(hintEl){
                hintEl.textContent = '· ' + dateStr + (isToday?'（今天）':'')
                    + ' · ' + (all.length ? all.length + ' 条' : '无');
            }
            if(!all.length){
                var tip = isToday
                    ? '今天关注股暂无资讯推送<br><small>每天 7:30 自动拉取；也可在「我的关注」行点 📰 资讯 手动采集</small>'
                    : '该日无资讯推送<br><small>用 ← / → 切换其它日期</small>';
                listEl.innerHTML = '<div class="news-section-empty">' + tip + '</div>';
                return;
            }
            listEl.innerHTML = all.map(function(item){
                var t = _fmtTime(item.push.created_at || item.push.updated_at);
                var body = window.renderMarkdown ? window.renderMarkdown(item.push.message_md || '') : _esc(item.push.message_md || '');
                // 显示名字优先，code 作 title 兜底；map 缺失时退回 code
                var name = _userWatchCodeToName[_normCode(item.code)] || '';
                var label = name || item.code;
                return '<div class="news-card">'
                    +   '<div class="nc-head">'
                    +     '<span class="nc-stock" title="' + _esc(item.code) + '">' + _esc(label) + '</span>'
                    +     '<span class="nc-time">' + t + '</span>'
                    +   '</div>'
                    +   '<div class="nc-body md-body">' + body + '</div>'
                    + '</div>';
            }).join('');
        }

        function _hydrateStockNewsLines(){
            var rows = document.querySelectorAll('.stock-news-line');
            for(var i=0; i<rows.length; i++){
                var row = rows[i];
                _renderStockNewsLine(row, row.getAttribute('data-stock-code'));
            }
            var panels = document.querySelectorAll('.stock-news-pushes');
            for(var j=0; j<panels.length; j++){
                _renderStockPushesPanel(panels[j], panels[j].getAttribute('data-stock-code'));
            }
            // 同步数据行的"📰 资讯"按钮：有推送时高亮
            var btns = document.querySelectorAll('.uw-news-toggle-btn');
            for(var b=0; b<btns.length; b++){
                var code = btns[b].getAttribute('data-stock-code');
                var pushes = _stockPushesCache[code] || [];
                btns[b].classList.toggle('has-news', pushes.length > 0);
                btns[b].textContent = pushes.length
                    ? '📰 ' + pushes.length + ' 条'
                    : '📰 资讯';
            }
        }

        function _renderStockNewsLine(row, code){
            var sub = _findStockSub(code);
            var pushes = _stockPushesCache[code] || [];
            row.classList.remove('on', 'err', 'busy');

            if(!sub){
                row.innerHTML = '<span class="news-toggle"><span class="dot"></span>未就绪</span>'
                    + '<span class="news-icon">📰</span>'
                    + '<span class="news-text"><span class="meta">订阅尚未建立（重启服务后自动 ensure）</span></span>'
                    + '<button class="news-run" disabled>采集</button>';
                return;
            }

            if(sub.running){
                row.classList.add('busy');
                row.innerHTML = '<label class="news-toggle busy"><span class="dot"></span>采集中…</label>'
                    + '<span class="news-icon">⏳</span>'
                    + '<span class="news-text"><span class="meta">任务运行中，稍候自动刷新</span></span>'
                    + '<button class="news-run" disabled>采集中</button>';
                return;
            }

            if(sub.last_error) row.classList.add('err');
            else if(sub.enabled) row.classList.add('on');

            var toggleLabel = sub.enabled ? '运行中' : '已停止';
            var toggleCls = 'news-toggle' + (sub.enabled ? ' on' : '');

            var textHtml;
            if(sub.last_error){
                textHtml = '<span class="err-msg">⚠ ' + esc(sub.last_error.substring(0, 80)) + '</span>';
            } else if(pushes.length){
                var latest = pushes[0];
                var t = _fmtPushTime(latest.created_at || latest.updated_at);
                textHtml = '<span class="meta">上次 ' + esc(t) + ' · ' + pushes.length + ' 条今日推送</span>';
            } else {
                var stat = sub.last_run_at
                    ? '上次 ' + _fmtPushTime(sub.last_run_at) + ' · 暂无新资讯'
                    : '暂无推送 · 每天 8 点采集';
                textHtml = '<span class="meta">' + esc(stat) + '</span>';
            }

            row.innerHTML = '<label class="' + toggleCls + '" title="点击启停">'
                +   '<input type="checkbox" ' + (sub.enabled ? 'checked' : '') + ' style="display:none">'
                +   '<span class="dot"></span>' + toggleLabel
                + '</label>'
                + '<span class="news-icon">📰</span>'
                + '<span class="news-text">' + textHtml + '</span>'
                + '<button class="news-run" title="立即采集一次">采集</button>';

            var subId = sub.id;
            var label = row.querySelector('.news-toggle');
            var checkbox = label.querySelector('input');
            var runBtn = row.querySelector('.news-run');
            label.onclick = function(e){
                if(e.target === checkbox) return;
                checkbox.checked = !checkbox.checked;
                toggleStockSub(checkbox, subId);
            };
            runBtn.onclick = function(){
                runBtn.disabled = true; runBtn.textContent = '采集中…';
                runStockSub(subId, runBtn);
            };
        }

        // marked.parse 渲染 + 外部链接 target=_blank rel=noopener（同 game_html）
        function _renderMdSafe(md){
            if(typeof marked === 'undefined' || !marked || typeof marked.parse !== 'function'){
                return '<pre>' + esc(md || '') + '</pre>';
            }
            try {
                var raw = marked.parse(md || '');
                var div = document.createElement('div');
                div.innerHTML = raw;
                var links = div.querySelectorAll('a[href]');
                for(var i=0; i<links.length; i++){
                    var href = links[i].getAttribute('href') || '';
                    if(/^https?:\\/\\//i.test(href)){
                        links[i].setAttribute('target', '_blank');
                        links[i].setAttribute('rel', 'noopener noreferrer');
                    }
                }
                return div.innerHTML;
            } catch(e){
                return '<pre>' + esc(md || '') + '</pre>';
            }
        }

        function _renderStockPushesPanel(holder, code){
            var pushes = _stockPushesCache[code] || [];
            if(!pushes.length){ holder.innerHTML = ''; return; }
            // 限制显示数量，避免太长
            var shown = pushes.slice(0, 12);
            var titles = shown.map(function(p, idx){
                var t = _fmtPushTime(p.created_at || p.updated_at);
                var md = p.message_md || '';
                var firstLine = md.split('\\n').filter(function(L){return L.trim();})[0] || '';
                var summary = firstLine.replace(/^[#*\\-\\s>]+/, '').substring(0, 60) || '(空标题)';
                return '<li class="news-title-row' + (idx === 0 ? ' active' : '') + '" data-idx="' + idx + '">'
                    +   '<span class="news-push-time">' + esc(t) + '</span>'
                    +   '<span class="news-push-title">' + esc(summary) + '</span>'
                    + '</li>';
            }).join('');
            // 默认显示第一条 md
            var firstHtml = _renderMdSafe(shown[0].message_md || '');
            holder.innerHTML =
                '<div class="news-pushes-head">📰 今日推送 · ' + pushes.length + ' 条 <span class="news-pushes-hint">点击左侧标题切换内容</span></div>'
                + '<div class="news-pushes-2col">'
                +   '<ul class="news-pushes-titlebar">' + titles + '</ul>'
                +   '<div class="news-pushes-detail markdown-body">' + firstHtml + '</div>'
                + '</div>';
            // 缓存 md 列表给点击切换用
            holder._pushMds = shown.map(function(p){return p.message_md || '';});
            // 绑点击切换
            var rows = holder.querySelectorAll('.news-title-row');
            var detail = holder.querySelector('.news-pushes-detail');
            for(var i=0; i<rows.length; i++){
                (function(li){
                    li.onclick = function(){
                        for(var j=0; j<rows.length; j++) rows[j].classList.remove('active');
                        li.classList.add('active');
                        var idx = parseInt(li.getAttribute('data-idx'), 10);
                        if(detail) detail.innerHTML = _renderMdSafe(holder._pushMds[idx] || '');
                    };
                })(rows[i]);
            }
        }

        window.toggleStockNewsRow = function(btn){
            var code = btn.getAttribute('data-stock-code');
            var newsRow = document.querySelector('.uw-news-row[data-news-row-for="' + code + '"]');
            if(newsRow) newsRow.classList.toggle('open');
        };

        window.toggleStockSub = async function(checkbox, subId){
            var enabled = checkbox.checked;
            try {
                var r = await fetch('/api/wealth/stock_subscriptions/' + encodeURIComponent(subId) + '/toggle', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({enabled: enabled}),
                });
                var d = await r.json();
                if(!d.ok){
                    alert('切换失败: ' + (d.error || 'unknown'));
                    checkbox.checked = !enabled;
                } else {
                    loadStockSubs();
                }
            } catch(e){
                alert('请求失败: ' + e.message);
                checkbox.checked = !enabled;
            }
        };

        window.runStockSub = async function(subId, btn){
            try {
                var r = await fetch('/api/wealth/stock_subscriptions/' + encodeURIComponent(subId) + '/run', {method:'POST'});
                var d = await r.json();
                if(!d.ok){
                    alert('触发失败: ' + (d.error || 'unknown'));
                    if(btn){ btn.disabled = false; btn.textContent = '采集'; }
                    return;
                }
            } catch(e){
                alert('请求失败: ' + e.message);
                if(btn){ btn.disabled = false; btn.textContent = '采集'; }
                return;
            }
            // loadStockSubs 自带递归轮询：sub.running=true → 2s 后自调直到完成
            await loadStockSubs();
        };
    })();
    </script>
"""
