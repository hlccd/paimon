"""GAME_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

GAME_SCRIPT_4 = """        // ─── 水神资讯 + 角色搜索（嵌入各 game tab 顶部，不另造 tab）─────
        // 由 _fillTab(gs/sr/zzz) 调 renderFurinaTabSection(game) 拼到 pane 头部
        window.renderFurinaTabSection = function(game){
            return ''
                + '<div class="fr-section" data-game="'+esc(game)+'">'
                + '  <div class="fr-body">'
                + '    <div class="fr-col fr-col-news">'
                + '      <div class="fr-col-title">📰 最新资讯<span class="fr-col-hint" id="fr-news-meta-'+esc(game)+'"></span></div>'
                + '      <div class="fr-col-scroll markdown-body" id="fr-news-'+esc(game)+'">加载中...</div>'
                + '    </div>'
                + '    <div class="fr-col fr-col-search">'
                + '      <div class="fr-col-title">🔍 角色搜索<span class="fr-col-hint">仅缓存最近一次</span></div>'
                + '      <div class="fr-search-bar">'
                + '        <input class="fr-search-input" id="fr-search-input-'+esc(game)+'" placeholder="输入角色名" '
                + '          onkeydown="if(event.key===\\'Enter\\')furinaSearchCharacter(\\''+esc(game)+'\\',document.getElementById(\\'fr-search-btn-'+esc(game)+'\\'))" />'
                + '        <button class="btn primary tiny" id="fr-search-btn-'+esc(game)+'" onclick="furinaSearchCharacter(\\''+esc(game)+'\\',this)">搜索</button>'
                + '      </div>'
                + '      <div class="fr-col-scroll markdown-body" id="fr-search-result-'+esc(game)+'">'
                + '        <div class="fr-empty">'
                + '          <i class="fr-empty-icon">🎯</i>'
                + '          搜任意角色 / 从下方角色列表点 🔍 一键查<br>'
                + '          <span style="font-size:11px;opacity:.75">B 站 + 小红书近 30 天 UGC · 30~120 秒</span>'
                + '        </div>'
                + '      </div>'
                + '    </div>'
                + '  </div>'
                + '</div>';
        };

        // 由 _fillTab 在拼好 HTML 之后调一次，异步拉取该 game 的最近一次角色搜索缓存
        // 没缓存就保持 fr-empty 空态；有就直接 render，让用户刷新/重启后还能看
        window.loadFurinaCharacterLatest = async function(game){
            var resultEl = document.getElementById('fr-search-result-'+game);
            var input = document.getElementById('fr-search-input-'+game);
            if(!resultEl) return;
            try {
                var r = await _fetchT('/api/game/character_research/latest?game='+encodeURIComponent(game), 6000);
                var d = await r.json();
                var rec = d.research;
                if(!rec || !rec.markdown) return;  // 空就保持原 fr-empty 引导态
                if(input && rec.query) input.value = rec.query;
                var ts = rec.updated_at ? fmtRelative(rec.updated_at) : '';
                var dur = rec.duration_s ? ' · '+rec.duration_s+'s' : '';
                resultEl.innerHTML =
                    '<div class="fr-result-meta">查询：'+esc(rec.query||'')+dur+(ts?' · '+ts:'')+'</div>'
                    + _renderMdSafe(rec.markdown);
            } catch(_){ /* 静默：失败保持空态 */ }
        };

        // 由 _fillTab 在拼好 HTML 之后调一次，异步拉取该 game 的最新资讯
        window.loadFurinaNews = async function(game){
            var slot = document.getElementById('fr-news-'+game);
            var meta = document.getElementById('fr-news-meta-'+game);
            if(!slot) return;
            slot.innerHTML = '<div class="fr-empty">加载中...</div>';
            if(meta) meta.textContent = '';
            try {
                var r = await _fetchT('/api/game/news/latest?game='+encodeURIComponent(game), 8000);
                var d = await r.json();
                var rec = d.news;
                if(!rec || !rec.markdown){
                    slot.innerHTML = '<div class="fr-empty">'
                        + '<i class="fr-empty-icon">📭</i>'
                        + '暂无资讯<br>'
                        + '<span style="font-size:11px;opacity:.75">每天早 7 点 cron 自动拉取</span>'
                        + '</div>';
                    return;
                }
                slot.innerHTML = _renderMdSafe(rec.markdown);
                if(meta){
                    var ts = rec.updated_at ? fmtRelative(rec.updated_at) : '';
                    var dur = rec.duration_s ? ' · 跑了 '+rec.duration_s+'s' : '';
                    meta.textContent = ts ? ts+dur : '';
                }
            } catch(e){
                slot.innerHTML = '<div class="fr-empty">⚠ 加载失败：'+esc(String(e && e.message || e))+'</div>';
            }
        };

        // char-row 🔍 按钮：切到该 game tab → 填值 → 搜
        window.furinaSearchFromChar = function(game, charName){
            if(_currentTab !== game){
                switchGameTab(game);  // _fillTab 会把 fr-section 渲染好
            }
            // _fillTab 是同步的，DOM 已存在
            var input = document.getElementById('fr-search-input-'+game);
            if(input) input.value = charName;
            var btn = document.getElementById('fr-search-btn-'+game);
            if(btn){
                btn.scrollIntoView({behavior:'smooth', block:'nearest'});
                furinaSearchCharacter(game, btn);
            }
        };

        window.furinaSearchCharacter = async function(game, btn){
            var input = document.getElementById('fr-search-input-'+game);
            var resultEl = document.getElementById('fr-search-result-'+game);
            if(!input || !resultEl) return;
            var query = (input.value || '').trim();
            if(!query){
                resultEl.innerHTML = '<div class="fr-empty">请输入角色名再搜索。</div>';
                return;
            }
            btn.disabled = true;
            var origLabel = btn.textContent;
            btn.textContent = '搜索中…';
            var t0 = Date.now();
            var timerId = setInterval(function(){
                var elapsed = Math.floor((Date.now() - t0) / 1000);
                resultEl.innerHTML = '<div class="fr-empty">'
                    + '<i class="fr-empty-icon">⏳</i>'
                    + '调研中… 已用 '+elapsed+' 秒<br>'
                    + '<span style="font-size:11px;opacity:.75">一般 30~120 秒</span>'
                    + '</div>';
            }, 1000);
            try {
                var r = await fetch('/api/game/character_research', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({game: game, query: query}),
                });
                var d = await r.json();
                clearInterval(timerId);
                if(d.error){
                    resultEl.innerHTML = '<div class="fr-empty">⚠ 失败：'+esc(d.error)+'</div>';
                    return;
                }
                var dur = d.duration_s ? ' · '+d.duration_s+'s' : '';
                resultEl.innerHTML =
                    '<div class="fr-result-meta">查询：'+esc(d.query||query)+dur+'</div>'
                    + _renderMdSafe(d.markdown || '(空)');
            } catch(e){
                clearInterval(timerId);
                resultEl.innerHTML = '<div class="fr-empty">⚠ 请求异常：'+esc(String(e && e.message || e))+'</div>';
            } finally {
                btn.disabled = false;
                btn.textContent = origLabel;
            }
        };

        // 入口
        window.onload = function(){
            loadOverview();
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
    })();
    </script>
"""
