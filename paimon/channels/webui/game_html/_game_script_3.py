"""GAME_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

GAME_SCRIPT_3 = """                        btn.textContent = old; btn.disabled = false;
                    }
                };
                poll();   // 立即跑一次
                _collectPollTimers[k] = setInterval(poll, 3000);
            }catch(e){
                console.error('[水神·采集] 启动异常', e);
                btn.textContent='✗'; setTimeout(function(){btn.textContent=old;btn.disabled=false;},2000);
            }
        };

        window.gameUnbind = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            if(!confirm('解绑 '+uid+' ？便笺/战报/抽卡记录都会清')) return;
            await fetch('/api/game/unbind', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({game, uid}),
            });
            delete _openState[game+'::'+uid];
            loadOverview();
        };

        window.gameRefreshAll = async function(){
            await fetch('/api/game/collect_all', {method:'POST'});
            setTimeout(loadOverview, 10000);
            setTimeout(loadOverview, 25000);
        };

        window.gameSelectPool = function(k, pool){
            _currentPool[k] = pool;
            var parts = k.split('::'); var g = parts[0]; var u = parts[1];
            var a = _allAccs.find(function(x){return x.uid === u && x.game === g;});
            if(a) _fillGacha(a, k);
        };

        // 抽卡同步：异步任务 + 轮询。刷新页面不会中断后端任务。
        var _gachaPollTimers = {};   // key -> interval id

        function _formatGachaProgress(prog){
            if(!prog) return '';
            var keys = Object.keys(prog);
            if(keys.length === 0) return '准备中...';
            return keys.map(function(p){
                var v = prog[p];
                return p+':'+(v < 0 ? '✗' : v);
            }).join(' / ');
        }

        function _stopGachaPoll(k){
            if(_gachaPollTimers[k]){
                clearInterval(_gachaPollTimers[k]);
                delete _gachaPollTimers[k];
            }
        }

        async function _pollGachaSync(game, uid, btn){
            var k = game+'::'+uid;
            _stopGachaPoll(k);
            console.log('[水神·抽卡] 开始轮询 sync state', k);
            var poll = async function(){
                try{
                    var r = await fetch('/api/game/gacha/sync/status?game='+game+'&uid='+encodeURIComponent(uid));
                    var s = await r.json();
                    var statusEl = document.getElementById('gsync-status-'+k);
                    if(s.state === 'running'){
                        var progressText = _formatGachaProgress(s.progress);
                        console.log('[水神·抽卡] '+k+' running '+progressText);
                        if(statusEl){ statusEl.className = 'gacha-sync-status running'; statusEl.textContent = progressText; }
                        if(btn){ btn.disabled = true; btn.textContent = '同步中...'; }
                    }else if(s.state === 'done'){
                        _stopGachaPoll(k);
                        var res = s.result || {};
                        var sum = res.summary || {};
                        var errs = res.errors || null;
                        var added = Object.keys(sum).map(function(p){return p+':'+sum[p];}).join(' / ') || '0';
                        console.log('[水神·抽卡] '+k+' DONE  summary='+added+'  errors='+JSON.stringify(errs));
                        if(btn){ btn.disabled = false; btn.textContent = '同步抽卡'; }
                        // 先重渲卡池数据，再把完成消息写到新 statusEl（重渲会换掉旧 DOM）
                        var a = _allAccs.find(function(x){return x.uid === uid && x.game === game;});
                        if(a){
                            await _fillGacha(a, keyOf(a));
                            var newStatus = document.getElementById('gsync-status-'+k);
                            var hasErr = errs && Object.keys(errs).length > 0;
                            if(newStatus){
                                newStatus.className = 'gacha-sync-status ' + (hasErr ? 'failed' : 'done');
                                newStatus.textContent = (hasErr ? '✗ ' : '✓ ') + added;
                            }
                        }
                        // 弹窗：分级诊断
                        if(errs){
                            var keys = Object.keys(errs);
                            var allFail = Object.keys(sum).every(function(p){ return sum[p] === -1; });
                            var lines = keys.map(function(p){return p+': '+errs[p];}).join('\\n');
                            var firstErr = errs[keys[0]] || '';
                            var isAuthKeyErr = (allFail && firstErr.indexOf('-100') >= 0);
                            if(isAuthKeyErr && game === 'sr'){
                                // 米哈游对 SR 抽卡 authkey 限制——stoken→authkey 路径被拒。
                                // 只能让用户从游戏内复制 URL 手动导入。
                                window.gameImportGachaUrl(game, uid);
                            }else if(isAuthKeyErr){
                                // GS/ZZZ 失败更可能是账号未真实绑定 → 一键解绑重绑
                                var ok = confirm(
                                    game.toUpperCase()+' 抽卡同步全部失败：\\n' + lines +
                                    '\\n\\n这通常意味着该 '+uid+' 账号在米游社侧未成功绑定。\\n\\n' +
                                    '是否立即解绑此账号并重新扫码？\\n' +
                                    '（解绑会清掉该账号的便笺/战报/抽卡缓存）'
                                );
                                if(ok){
                                    try{
                                        await fetch('/api/game/unbind', {
                                            method:'POST', headers:{'Content-Type':'application/json'},
                                            body: JSON.stringify({game, uid}),
                                        });
                                        if(typeof loadOverview === 'function') loadOverview();
                                        if(typeof openQrModal === 'function') openQrModal();
                                    }catch(unbindErr){
                                        alert('解绑失败: '+unbindErr+'\\n请手动展开账号详情 → 点右下角"解绑"');
                                    }
                                }
                            }else{
                                var prefix = allFail ? game.toUpperCase()+' 同步全部失败：\\n' : game.toUpperCase()+' 部分池子失败：\\n';
                                alert(prefix + lines);
                            }
                        }
                    }else if(s.state === 'failed'){
                        _stopGachaPoll(k);
                        console.error('[水神·抽卡] '+k+' FAILED', s.error);
                        if(statusEl){ statusEl.className = 'gacha-sync-status failed'; statusEl.textContent = '✗ ' + (s.error||''); }
                        if(btn){ btn.disabled = false; btn.textContent = '同步抽卡'; }
                        alert('同步失败: '+(s.error||''));
                    }else{
                        _stopGachaPoll(k);
                        if(btn){ btn.disabled = false; btn.textContent = '同步抽卡'; }
                    }
                }catch(e){
                    console.error('[水神·抽卡] poll 异常', e);
                    _stopGachaPoll(k);
                    if(btn){ btn.disabled = false; btn.textContent = '同步抽卡'; }
                }
            };
            poll();   // 立即跑一次
            _gachaPollTimers[k] = setInterval(poll, 2500);
        }

        window.gameSyncGacha = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            console.log('[水神·抽卡] 点击同步抽卡', game, uid);
            btn.disabled = true; var old = btn.textContent; btn.textContent = '启动...';
            try{
                var r = await fetch('/api/game/gacha/sync', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game, uid}),
                });
                var d = await r.json();
                console.log('[水神·抽卡] /sync 响应', d);
                if(!d.ok){
                    alert('启动失败: '+(d.msg||''));
                    btn.disabled = false; btn.textContent = old;
                    return;
                }
                _pollGachaSync(game, uid, btn);
            }catch(e){
                console.error('[水神·抽卡] /sync 异常', e);
                alert('请求异常: '+e);
                btn.disabled = false; btn.textContent = old;
            }
        };

        // ============ 扫码 modal ============
        var _qrPollTimer = null;
        window.openQrModal = function(){
            document.getElementById('qrModal').classList.add('show');
            document.getElementById('qrBox').innerHTML = '<button class="btn primary" onclick="startQrLogin()">生成二维码</button>';
            document.getElementById('qrStatus').textContent = '';
        };
        window.closeQrModal = function(){
            document.getElementById('qrModal').classList.remove('show');
            if(_qrPollTimer){ clearInterval(_qrPollTimer); _qrPollTimer = null; }
        };

        // ============ URL 导入 modal（SR 必走，GS/ZZZ fallback）============
        var _urlImportCtx = null;   // {game, uid}

        var SR_PS_CMD = '[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12; Invoke-Expression (New-Object Net.WebClient).DownloadString("https://imgheybox.max-c.com/game/star_rail/link1.ps1")';

        var GACHA_TUTORIAL = {
            'sr': '<b>SR 抽卡链接获取教程</b>（米哈游限制，SR 必须手动导入 URL）'
                + '<br>'
                + '<br>1. <b>PC 端</b>启动星穹铁道，登录该账号'
                + '<br>2. 在游戏内打开<b>跃迁 → 跃迁记录</b>页面（确保能看到抽卡历史）'
                + '<br>3. 打开 <b>PowerShell</b>，粘贴下面整段命令并回车（来自小黑盒）：'
                + '<div class="ps-cmd-box">'
                +   '<textarea id="srPsCmd" readonly onclick="this.select()">'+SR_PS_CMD+'</textarea>'
                +   '<button class="ps-cmd-copy" id="srPsCmdCopyBtn" onclick="copyPsCommand(this)">复制</button>'
                + '</div>'
                + '4. 脚本会输出 / 复制带 <code>authkey=xxx</code> 的完整 URL，粘贴到下方'
                + '<br>'
                + '<br><span style="color:var(--text-muted)">链接 24 小时内有效；过期重新拿即可</span>',
        };

        window.copyPsCommand = async function(btn){
            try{
                if(navigator.clipboard && navigator.clipboard.writeText){
                    await navigator.clipboard.writeText(SR_PS_CMD);
                }else{
                    // fallback：选中 textarea + execCommand
                    var ta = document.getElementById('srPsCmd');
                    if(ta){ ta.select(); document.execCommand('copy'); }
                }
                btn.classList.add('done');
                btn.textContent = '✓ 已复制';
                setTimeout(function(){
                    btn.classList.remove('done');
                    btn.textContent = '复制';
                }, 2000);
            }catch(e){
                console.error('[水神·抽卡] 复制 PowerShell 命令失败', e);
                alert('复制失败，请手动选中复制：'+e);
            }
        };

        window.gameImportGachaUrl = function(game, uid){
            _urlImportCtx = {game, uid};
            document.getElementById('urlImportTitle').textContent = '导入 ' + game.toUpperCase() + ' 抽卡链接（' + uid + '）';
            document.getElementById('urlImportTutorial').innerHTML = GACHA_TUTORIAL[game] || '从游戏内复制带 authkey=... 的完整链接';
            document.getElementById('urlImportInput').value = '';
            document.getElementById('urlImportModal').classList.add('show');
            setTimeout(function(){ document.getElementById('urlImportInput').focus(); }, 50);
        };

        window.closeUrlImportModal = function(){
            document.getElementById('urlImportModal').classList.remove('show');
            _urlImportCtx = null;
        };

        window.submitUrlImport = async function(){
            if(!_urlImportCtx) return;
            var url = document.getElementById('urlImportInput').value.trim();
            if(!url){ alert('请粘贴 URL'); return; }
            var ctx = _urlImportCtx;
            console.log('[水神·抽卡] URL 导入提交', ctx.game, ctx.uid, 'url_len=', url.length);
            try{
                var r = await fetch('/api/game/gacha/import_url', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game: ctx.game, uid: ctx.uid, url: url}),
                });
                var d = await r.json();
                console.log('[水神·抽卡] /import_url 响应', d);
                if(!d.ok){
                    alert('启动失败: '+(d.msg||''));
                    return;
                }
                closeUrlImportModal();
                _pollGachaSync(ctx.game, ctx.uid, null);
            }catch(e){
                console.error('[水神·抽卡] /import_url 异常', e);
                alert('请求异常: '+e);
            }
        };
        window.startQrLogin = async function(){
            if(_qrPollTimer){ clearInterval(_qrPollTimer); _qrPollTimer = null; }
            var box = document.getElementById('qrBox');
            var status = document.getElementById('qrStatus');
            box.innerHTML = '<span style="color:#666">生成中...</span>';
            status.textContent = '请求米游社 QR...';
            var r = await fetch('/api/game/qr_create', {method:'POST'});
            var d = await r.json();
            if(!d.ok){ status.textContent='生成失败: '+(d.error||''); return; }
            box.innerHTML = '<img src="https://api.qrserver.com/v1/create-qr-code/?size=240x240&data='+encodeURIComponent(d.url)+'">';
            status.textContent = '请用米游社 APP 扫码';
            _qrPollTimer = setInterval(async function(){
                var rp = await fetch('/api/game/qr_poll?ticket='+encodeURIComponent(d.ticket)+'&device='+encodeURIComponent(d.device)+'&app_id='+d.app_id);
                var dp = await rp.json();
                if(dp.stat === 'Scanned'){ status.textContent = '已扫描，等待确认...'; }
                else if(dp.stat === 'Confirmed'){
                    clearInterval(_qrPollTimer); _qrPollTimer = null;
                    var bound = (dp.bound||[]).map(function(x){return (GAME_META[x.game]||{name:x.game}).name+'('+x.uid+')';}).join(', ');
                    status.textContent = '✅ 绑定成功：'+bound;
                    setTimeout(function(){ closeQrModal(); loadOverview(); }, 1500);
                }
                else if(dp.stat === 'Error'){
                    clearInterval(_qrPollTimer); _qrPollTimer = null;
                    status.textContent = '失败: '+(dp.msg||'');
                }
            }, 2000);
        };

        // ========= 📰 游戏资讯订阅（按钮集成进账号卡，详情区有完整控件 + 推送预览）=========
        var _subsCache = [];        // 全部 mihoyo_game 订阅
        var _pushesCache = {};      // {game: [push records]} 按游戏分桶

        function _fmtSubTime(ts){
            if(!ts) return '从未运行';
            var d = new Date(ts*1000);
            return (d.getMonth()+1)+'-'+d.getDate()+' '
                + d.getHours().toString().padStart(2,'0')+':'
                + d.getMinutes().toString().padStart(2,'0');
        }

        function _findSub(game, uid){
            for(var i=0; i<_subsCache.length; i++){
                if(_subsCache[i].game === game && _subsCache[i].uid === uid) return _subsCache[i];
            }
            return null;
        }

        // 拉订阅 + 推送数据，刷新 UI；自带递归轮询（同风神 feed_html 模式）：
        // 有 sub.running 时 2s 后自动再调一次直到全部完成
        var _subsPollTimer = null;
        async function loadGameSubs(){
            try {
                var r = await fetch('/api/game/subscriptions');
                var data = await r.json();
                _subsCache = data.subs || [];
            } catch(e){ console.error('subs fetch failed', e); _subsCache = []; }

            try {
                var rp = await fetch('/api/push_archive/list?actor=' + encodeURIComponent('水神') + '&limit=30');
                var dp = await rp.json();
                var records = dp.records || [];
                _pushesCache = { gs: [], sr: [], zzz: [] };
                records.forEach(function(rec){
                    // source 形如 '水神·mihoyo_game:gs:113975833'（archon 中文名前缀，不固定位置 0）
                    var src = rec.source || '';
                    if(src.indexOf('mihoyo_game:gs:') >= 0) _pushesCache.gs.push(rec);
                    else if(src.indexOf('mihoyo_game:sr:') >= 0) _pushesCache.sr.push(rec);
                    else if(src.indexOf('mihoyo_game:zzz:') >= 0) _pushesCache.zzz.push(rec);
                });
            } catch(e){ console.error('pushes fetch failed', e); _pushesCache = {}; }

            _hydrateSubsBtns();

            // 有采集中的订阅 → 2s 后自动再刷一次，直到全部完成
            if(_subsCache.some(function(s){return s.running;})){
                if(_subsPollTimer) clearTimeout(_subsPollTimer);
                _subsPollTimer = setTimeout(loadGameSubs, 2000);
            }
        }

        // 填充：账号卡资讯行 + 详情区推送面板
        function _hydrateSubsBtns(){
            var rows = document.querySelectorAll('.ac-news-line');
            for(var i=0; i<rows.length; i++){
                var row = rows[i];
                _renderNewsLine(row,
                    row.getAttribute('data-game'),
                    row.getAttribute('data-uid'));
            }
            // 详情卡才有 ac-news-pushes 占位（_renderFullCard 渲染的卡才有）
            var panels = document.querySelectorAll('.ac-news-pushes');
            for(var j=0; j<panels.length; j++){
                var p = panels[j];
                _renderPushesPanel(p,
                    p.getAttribute('data-game'),
                    p.getAttribute('data-uid'));
            }
        }

        // 总览资讯行（精简）：状态 toggle + 上次时间·条数 + 立即采集按钮
        // 不显示推送标题（标题留给详情卡的 ac-news-pushes 面板展示）
        function _renderNewsLine(row, game, uid){
            var sub = _findSub(game, uid);
            var pushes = (_pushesCache[game] || []).filter(function(p){
                return (p.source || '').indexOf('mihoyo_game:' + game + ':' + uid) >= 0;
            });
            row.classList.remove('on', 'err', 'busy');

            // 未就绪：占位
            if(!sub){
                row.innerHTML =
                    '<span class="news-toggle"><span class="dot"></span>加载中</span>'
                    + '<span class="news-icon">📰</span>'
                    + '<span class="news-text"><span class="meta">资讯订阅</span></span>'
                    + '<button class="news-run" disabled>采集</button>';
                return;
            }

            // 采集中：优先级最高（正在跑就是正在跑，覆盖启停/失败显示）
            if(sub.running){
                row.classList.add('busy');
                row.innerHTML =
                    '<label class="news-toggle busy">'
                    +   '<span class="dot"></span>采集中…'
                    + '</label>'
                    + '<span class="news-icon">⏳</span>'
                    + '<span class="news-text"><span class="meta">任务运行中，稍候自动刷新</span></span>'
                    + '<button class="news-run" disabled>采集中</button>';
                return;
            }

            // 状态色
            if(sub.last_error) row.classList.add('err');
            else if(sub.enabled) row.classList.add('on');

            var toggleLabel = sub.enabled ? '运行中' : '已停止';
            var toggleCls = 'news-toggle' + (sub.enabled ? ' on' : '');

            // 总览精简：仅状态摘要，不带标题
            var textHtml;
            if(sub.last_error){
                textHtml = '<span class="err-msg">⚠ ' + esc(sub.last_error.substring(0, 80)) + '</span>';
            } else if(pushes.length){
                var latest = pushes[0];
                var t = _fmtSubTime(latest.created_at || latest.updated_at);
                textHtml = '<span class="meta">上次 ' + esc(t) + ' · ' + pushes.length + ' 条今日推送</span>';
            } else {
                var stat = sub.last_run_at
                    ? '上次 ' + _fmtSubTime(sub.last_run_at) + ' · 暂无新资讯'
                    : '暂无推送 · 每天 7 点采集';
                textHtml = '<span class="meta">' + esc(stat) + '</span>';
            }

            row.innerHTML =
                '<label class="' + toggleCls + '" title="点击启停">'
                +   '<input type="checkbox" ' + (sub.enabled ? 'checked' : '') + ' '
                +     'style="display:none">'
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
                toggleGameSub(checkbox, subId);
            };
            runBtn.onclick = function(){
                runBtn.disabled = true;
                runBtn.textContent = '采集中…';
                runGameSub(subId, runBtn);
            };
        }

        // 推送面板：holder.dataset.detailed='1' = 游戏 tab 完整版（可展开看完整 md）
        // 否则 = 总览只读汇总（仅标题列表 + 跳转链接）
        function _renderPushesPanel(holder, game, uid){
            var pushes = (_pushesCache[game] || []).filter(function(p){
                return (p.source || '').indexOf('mihoyo_game:' + game + ':' + uid) >= 0;
            });
            if(!pushes.length){
                holder.innerHTML = '';  // 没推送时整段隐藏
                return;
            }
            var detailed = holder.getAttribute('data-detailed') === '1';
"""
