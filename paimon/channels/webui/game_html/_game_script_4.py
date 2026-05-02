"""GAME_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

GAME_SCRIPT_4 = """            // 提取每条的标题（首个非空行去 md 标记）
            function _summary(md){
                var firstLine = (md || '').split('\\n').filter(function(L){return L.trim();})[0] || '';
                return firstLine.replace(/^[#*\\-\\s>]+/, '').substring(0, 80) || '(空标题)';
            }

            // 总览：只读汇总列表 + 跳详情
            if(!detailed){
                var rows = pushes.slice(0, 5).map(function(p){
                    var t = _fmtSubTime(p.created_at || p.updated_at);
                    return '<li class="news-summary-row">'
                        + '<span class="news-push-time">' + esc(t) + '</span>'
                        + '<span class="news-push-title">' + esc(_summary(p.message_md)) + '</span>'
                        + '</li>';
                }).join('');
                var more = pushes.length > 5
                    ? '<a class="news-more-link" onclick="switchGameTab(\\''+esc(game)+'\\')">查看全部 '+pushes.length+' 条 →</a>'
                    : '<a class="news-more-link" onclick="switchGameTab(\\''+esc(game)+'\\')">进游戏页看完整内容 →</a>';
                holder.innerHTML =
                    '<div class="news-pushes-head">📰 今日推送 · ' + pushes.length + ' 条</div>'
                    + '<ul class="news-pushes-list news-pushes-list-summary">' + rows + '</ul>'
                    + '<div class="news-more">' + more + '</div>';
                return;
            }

            // 详细：可展开折叠卡片（marked.parse 渲染完整 md，外部链接 target=_blank）
            var items = pushes.slice(0, 8).map(function(p){
                var t = _fmtSubTime(p.created_at || p.updated_at);
                var md = p.message_md || '';
                var bodyHtml = _renderMdSafe(md);
                return '<div class="news-push-item">'
                    +   '<div class="news-push-head" onclick="this.parentElement.classList.toggle(\\'open\\')">'
                    +     '<span class="news-push-arrow">▶</span>'
                    +     '<span class="news-push-time">' + esc(t) + '</span>'
                    +     '<span class="news-push-title">' + esc(_summary(md)) + '</span>'
                    +   '</div>'
                    +   '<div class="news-push-body markdown-body">' + bodyHtml + '</div>'
                    + '</div>';
            }).join('');
            holder.innerHTML =
                '<div class="news-pushes-head">📰 今日推送 · ' + pushes.length + ' 条 <span class="news-pushes-hint">点击单条展开</span></div>'
                + '<div class="news-pushes-list">' + items + '</div>';
        }


        window.toggleGameSub = async function(checkbox, subId){
            var enabled = checkbox.checked;
            try {
                var r = await fetch('/api/game/subscriptions/'+encodeURIComponent(subId)+'/toggle', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({enabled: enabled}),
                });
                var d = await r.json();
                if(!d.ok){
                    alert('切换失败: '+(d.error||'unknown'));
                    checkbox.checked = !enabled;
                } else {
                    loadGameSubs();
                }
            } catch(e){
                alert('请求失败: '+e.message);
                checkbox.checked = !enabled;
            }
        };

        window.runGameSub = async function(subId, btn){
            // btn 文字已由 _renderNewsLine 的 onclick 提前置为"采集中…"
            try {
                var r = await fetch('/api/game/subscriptions/'+encodeURIComponent(subId)+'/run', {method:'POST'});
                var d = await r.json();
                if(!d.ok){
                    alert('触发失败: '+(d.error||'unknown'));
                    if(btn){ btn.disabled = false; btn.textContent = '采集'; }
                    return;
                }
            } catch(e){
                alert('请求失败: '+e.message);
                if(btn){ btn.disabled = false; btn.textContent = '采集'; }
                return;
            }
            // loadGameSubs 自带递归轮询：检测到 sub.running 会 setTimeout(loadGameSubs, 2000)
            // 直到 running=false 自然停（同风神 feed_html.py 模式）
            await loadGameSubs();
        };

        // 入口：loadOverview + loadGameSubs 并行
        window.onload = function(){
            loadOverview();
            loadGameSubs();
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
