"""GAME_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

GAME_SCRIPT_1 = """
    <script>
    (function(){
        function esc(s){return s===null||s===undefined?'':String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}

        // marked.parse 渲染 + 外部链接（http/https）改 target=_blank rel=noopener
        // 站内相对链接保持当前页跳转
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
        function fmtRelative(ts){
            if(!ts||ts<=0)return '-';
            var sec = (Date.now()/1000) - ts;
            if(sec < 60) return Math.floor(sec)+'s 前';
            if(sec < 3600) return Math.floor(sec/60)+'min 前';
            if(sec < 86400) return Math.floor(sec/3600)+'h 前';
            return Math.floor(sec/86400)+'d 前';
        }
        function fmtFuture(ts){
            if(!ts||ts<=0)return '已满';
            var sec = ts - (Date.now()/1000);
            if(sec <= 0) return '已满';
            var h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60);
            if(h >= 24) return Math.floor(h/24)+'d'+(h%24)+'h';
            if(h === 0) return m+'min 后满';
            return h+'h'+String(m).padStart(2,'0')+'m 后满';
        }

        // logo = 官方主色渐变圆 + 游戏名核心字（原/穹/零）
        var GAME_META = {
            gs:  {name:'原神',   logo:{cls:'gs',  text:'原'}, stamina:'树脂',   daily:'委托', rogueLabel:null},
            sr:  {name:'崩铁',   logo:{cls:'sr',  text:'穹'}, stamina:'开拓力', daily:'实训', rogueLabel:'模拟宇宙'},
            zzz: {name:'绝区零', logo:{cls:'zzz', text:'零'}, stamina:'电量',   daily:'活跃', rogueLabel:'悬赏'},
        };
        function renderLogo(game){
            var m = GAME_META[game];
            if(!m) return '<span class="game-logo">?</span>';
            return '<span class="game-logo '+m.logo.cls+'">'+m.logo.text+'</span>';
        }
        var ABYSS_DEFS = {
            gs: [
                {type:'spiral',  name:'深境螺旋'},
                {type:'poetry',  name:'幻想真境剧诗'},
                {type:'stygian', name:'幽境危战'},
            ],
            sr: [
                {type:'forgotten_hall', name:'忘却之庭'},
                {type:'pure_fiction',   name:'虚构叙事'},
                {type:'apocalyptic',    name:'末日幻影'},
                {type:'peak',           name:'异相仲裁'},
            ],
            zzz: [
                {type:'shiyu', name:'式舆防卫战'},
                {type:'mem',   name:'危局强袭战'},
                // TODO 临界推演 endpoint 404，待抓包修复后启用
                // {type:'void',  name:'临界推演'},
            ],
        };
        // pool key 必须跟 mihoyo_gacha 表的 gacha_type 列实际存值一致
        // 三游戏都存 db_type 英文（_gacha.py:129 入库时 gacha_type=db_type，
        // 参见 furina_game/service.py 的 _GACHA_POOLS_BY_GAME 元组第一个元素）
        // → 前端必须用相同字符串否则 stats API 查 0 条（hotfix2/3 已为 ZZZ 修过同款 bug）
        var POOL_LABELS_BY_GAME = {
            'gs':  {'character':'角色','weapon':'武器','permanent':'常驻','chronicled':'集录'},
            'sr':  {'character':'角色','lightcone':'光锥','permanent':'常驻'},
            'zzz': {'agent':'独家','wengine':'音擎','permanent':'常驻','bangboo':'邦布'},
        };
        // 显式数组保证 UP 池靠前、常驻/集录/邦布殿后；不依赖 Object.keys 顺序
        var POOL_ORDER_BY_GAME = {
            'gs':  ['character', 'weapon', 'permanent', 'chronicled'],
            'sr':  ['character', 'lightcone', 'permanent'],
            'zzz': ['agent', 'wengine', 'permanent', 'bangboo'],
        };

        var _allAccs = [];
        var _currentPool = {};  // uid -> pool id
        var _currentTab = 'overview';   // 'overview' | 'gs' | 'sr' | 'zzz'
        var _filledTabs = {};           // key -> 已填充过，避免重复 fill 战报/抽卡
        var _TABS = [
            {key:'overview', label:'总览'},
            {key:'gs',  label:'原神'},
            {key:'sr',  label:'崩铁'},
            {key:'zzz', label:'绝区零'},
        ];

        // tab button 的 label 里内嵌游戏 logo
        function _tabLabel(t){
            if(t.key === 'overview') return t.label;
            return '<span class="tab-logo '+t.key+'">'+GAME_META[t.key].logo.text+'</span>' + t.label;
        }

        function keyOf(a){ return a.game+'::'+a.uid; }

        window.loadOverview = async function(){
            var wrapper = document.getElementById('wrapperEl');
            try{
                var r = await fetch('/api/game/overview');
                var d = await r.json();
                _allAccs = d.accounts || [];
            }catch(e){
                wrapper.innerHTML = '<div class="empty-bind"><h2>加载失败</h2><p>'+esc(String(e))+'</p></div>';
                return;
            }
            _renderStatusSub();
            if(_allAccs.length === 0){
                wrapper.innerHTML = '<div class="empty-bind">'
                    +'<h2>还没绑定任何账号</h2>'
                    +'<p>扫码一次即可绑定该米游社账号下的原神 / 星铁 / 绝区零</p>'
                    +'<button class="btn primary" onclick="openQrModal()">+ 添加账号</button>'
                    +'</div>';
                return;
            }
            // 先搭 tab 骨架
            wrapper.innerHTML =
                '<div class="tabs-bar">' + _TABS.map(function(t){
                    return '<button class="tab-btn'+(t.key===_currentTab?' active':'')
                        +'" data-tab-key="'+t.key+'" onclick="switchGameTab(\\''+t.key+'\\')">'+_tabLabel(t)+'</button>';
                }).join('') + '</div>'
                + _TABS.map(function(t){
                    return '<div class="tab-pane'+(t.key===_currentTab?' active':'')+'" id="tab-'+t.key+'"></div>';
                }).join('');
            _filledTabs = {};
            _fillTab(_currentTab);
        };

        window.switchGameTab = function(key){
            _currentTab = key;
            document.querySelectorAll('.tab-btn').forEach(function(b){
                b.classList.toggle('active', b.getAttribute('data-tab-key') === key);
            });
            document.querySelectorAll('.tab-pane').forEach(function(p){ p.classList.remove('active'); });
            var pane = document.getElementById('tab-'+key);
            if(pane){ pane.classList.add('active'); }
            _fillTab(key);
            // 切 tab 时同步订阅按钮状态（新渲染的卡可能 hydrate 还没跑过）
            if(typeof _hydrateSubsBtns === 'function') _hydrateSubsBtns();
        };

        function _fillTab(key){
            var pane = document.getElementById('tab-'+key);
            if(!pane) return;
            if(_filledTabs[key]) return;
            _filledTabs[key] = true;
            if(key === 'overview'){
                pane.innerHTML = _allAccs.map(_renderSummaryCard).join('');
            } else {
                // 特定游戏 tab：过滤该 game 账号，完整卡片
                var accs = _allAccs.filter(function(a){return a.game === key;});
                if(accs.length === 0){
                    pane.innerHTML = '<div class="tab-empty">未绑定该游戏账号。'
                        +'<br><br><button class="btn primary" onclick="openQrModal()">+ 扫码绑定</button></div>';
                    return;
                }
                pane.innerHTML = accs.map(_renderFullCard).join('');
                // 异步填每个账号的战报/抽卡（模拟展开效果）
                accs.forEach(function(a){ _fillAccountDetail(a); });
            }
            // 订阅按钮 hydrate（loadGameSubs 拉完后会 hydrate 占位的 ac-subs-btn）
            if(typeof _hydrateSubsBtns === 'function') _hydrateSubsBtns();
        }

        function _renderStatusSub(){
            var el = document.getElementById('statusSub');
            if(_allAccs.length === 0){
                el.textContent = '未绑定任何账号';
                return;
            }
            var bymys = {};
            _allAccs.forEach(function(a){ bymys[a.mys_id] = (bymys[a.mys_id]||0)+1; });
            el.textContent = '已绑 ' + _allAccs.length + ' 个游戏（' + Object.keys(bymys).length + ' 个米游社账号）';
        }

        function _renderSummaryCard(a){
            // 总览 tab 用：紧凑一行，点"看详细 →"跳对应游戏 tab
            var k = keyOf(a);
            var meta = GAME_META[a.game] || {name:a.game, icon:'🎮', stamina:'体力', daily:'任务'};
            var n = a.daily_note;
            var summary = _renderSummary(a, meta, n);
            return '<div class="account-card">'
                + '<div class="ac-summary">'
                + '  <div class="ac-identity">'
                + '    '+renderLogo(a.game)
                + '    <div class="ac-names">'
                + '      <div class="ac-game-name">'+esc(meta.name)
                +        (a.note ? ' <span class="ac-note">· '+esc(a.note)+'</span>' : '')
                + '      </div>'
                + '      <div class="ac-uid">'+esc(a.uid)+'</div>'
                + '    </div>'
                + '  </div>'
                + '  '+summary
                + '  <div class="ac-ops">'
                + '    <button class="btn tiny primary" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameSignOne(this)">签到</button>'
                + '    <button class="ac-toggle" onclick="switchGameTab(\\''+esc(a.game)+'\\')">看详细 →</button>'
                + '  </div>'
                + '</div>'
                + '<div class="ac-news-line" data-news-line-for="'+esc(k)+'" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'">'
                +   '<span class="news-toggle"><span class="dot"></span>加载中</span>'
                +   '<span class="news-icon">📰</span>'
                +   '<span class="news-text"><span class="meta">资讯订阅</span></span>'
                +   '<button class="news-run" disabled>采集</button>'
                + '</div>'
                + '<div class="ac-news-pushes" data-pushes-for="'+esc(k)+'" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'"></div>'
                + '</div>';
        }

        // 总览只读汇总（_renderSummaryCard 用），游戏 tab 可展开（_renderFullCard 用，data-detailed="1"）
        function _renderFullCard(a){
            // 游戏 tab 用：顶部账号摘要 + 展开的详情区（便笺派遣 / 战报 / 抽卡 / 角色占位）
            var k = keyOf(a);
            var meta = GAME_META[a.game] || {name:a.game, icon:'🎮', stamina:'体力', daily:'任务'};
            var n = a.daily_note;
            var summary = _renderSummary(a, meta, n);
            return '<div class="account-card" id="ac-'+esc(k)+'">'
                + '<div class="ac-summary">'
                + '  <div class="ac-identity">'
                + '    '+renderLogo(a.game)
                + '    <div class="ac-names">'
                + '      <div class="ac-game-name">'+esc(meta.name)
                +        (a.note ? ' <span class="ac-note">· '+esc(a.note)+'</span>' : '')
                + '      </div>'
                + '      <div class="ac-uid">'+esc(a.uid)+'</div>'
                + '    </div>'
                + '  </div>'
                + '  '+summary
                + '  <div class="ac-ops">'
                + '    <button class="btn tiny primary" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameSignOne(this)">签到</button>'
                + '  </div>'
                + '</div>'
                + '<div class="ac-news-line" data-news-line-for="'+esc(k)+'" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'">'
                +   '<span class="news-toggle"><span class="dot"></span>加载中</span>'
                +   '<span class="news-icon">📰</span>'
                +   '<span class="news-text"><span class="meta">资讯订阅</span></span>'
                +   '<button class="news-run" disabled>采集</button>'
                + '</div>'
                + '<div class="ac-news-pushes" data-pushes-for="'+esc(k)+'" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" data-detailed="1"></div>'
                + '<div class="ac-detail open" id="detail-'+esc(k)+'">加载中...</div>'
                + '</div>';
        }

        function _renderSummary(a, meta, n){
            if(!n || !n.max_resin){
                return '<div class="ac-status">'
                    + '<div style="color:var(--text-muted);font-size:12px;">暂无便笺数据（上次签到 '+(a.last_sign_at>0?fmtRelative(a.last_sign_at):'-')+'）</div>'
                    + '</div>';
            }
            var pct = Math.min(100, n.current_resin/n.max_resin*100);
            var fillCls = pct >= 100 ? 'full' : (pct >= 85 ? 'warn' : '');
            var whenCls = pct >= 85 ? ' urgent' : '';
            var whenText = fmtFuture(n.resin_full_ts);

            // chips: 委托 / 派遣 / 签到
            var chips = [];
            // 每日任务
            var dailyDone = n.finished_tasks >= n.total_tasks;
            var dailyReward = a.game === 'gs' ? n.daily_reward : true;  // 只有原神有"奖励未领"语义
            var dailyCls = 'ok';
            var dailyText = meta.daily+' '+n.finished_tasks+'/'+n.total_tasks;
            if(!dailyDone){ dailyCls = 'bad'; dailyText += ' ✗'; }
            else if(a.game === 'gs' && !dailyReward){ dailyCls = 'warn'; dailyText += ' 奖励未领'; }
            else { dailyText += ' ✓'; }
            chips.push('<span class="chip '+dailyCls+'">'+esc(dailyText)+'</span>');

            // 派遣（原神/崩铁有）
            if(n.max_expedition > 0){
                var expReady = (n.expeditions||[]).filter(function(e){return parseInt(e.remained_time||0)<=0;}).length;
                var expTotal = n.max_expedition;
                var expCls = (a.game === 'gs' && expReady === expTotal) ? 'ok'
                           : (expReady > 0 ? 'warn' : '');
                chips.push('<span class="chip '+expCls+'">派遣 '+n.current_expedition+'/'+expTotal
                    + (expReady>0?' · '+expReady+'就绪':'')+'</span>');
            }

            // 原神参量
            if(a.game === 'gs' && n.transformer_ready){
                chips.push('<span class="chip ok">参量就绪</span>');
            }

            // 崩铁模拟宇宙周 / 绝区零悬赏
            if(a.game === 'sr' && n.remain_discount > 0){
                chips.push('<span class="chip">模拟宇宙 '+n.remain_discount+'</span>');
            }
            if(a.game === 'zzz' && n.remain_discount > 0){
                chips.push('<span class="chip">悬赏 '+n.remain_discount+'</span>');
            }

            // 签到状态（按 last_sign_at 是不是今天判断）
            var now = Date.now() / 1000;
            var signedToday = a.last_sign_at > 0 && (now - a.last_sign_at) < 20*3600;
            chips.push('<span class="chip '+(signedToday?'ok':'bad')+'">'+(signedToday?'今日已签':'未签到')+'</span>');

            return '<div class="ac-status">'
                + '<div class="ac-resin-line">'
                + '  <span class="ac-resin-label">'+esc(meta.stamina)+'</span>'
                + '  <div class="ac-resin-bar"><div class="ac-resin-fill '+fillCls+'" style="width:'+pct.toFixed(1)+'%"></div></div>'
                + '  <span class="ac-resin-num">'+n.current_resin+'/'+n.max_resin+'</span>'
                + '  <span class="ac-resin-when'+whenCls+'">'+esc(whenText)+'</span>'
                + '</div>'
                + '<div class="ac-chips">'+chips.join('')+'</div>'
                + '</div>';
        }

        async function _fillAccountDetail(a){
            var k = keyOf(a);
            var el = document.getElementById('detail-'+k);
            if(!el) return;

            var charsTitle = (a.game==='gs') ? '角色 · 养成'
                : (a.game==='sr' ? '角色 · 星魂' : '代理人 · 影画');

            var html = '<div class="ac-detail-grid">'
                +   '<div class="ac-panel h-fixed gacha-pane">'
                +     '<div class="panel-title">抽卡记录</div>'
                +     '<div class="panel-body" id="gacha-'+esc(k)+'">加载中...</div>'
                +   '</div>'
                +   '<div class="ac-panel h-fixed abyss-pane">'
                +     '<div class="panel-title">战报 · 最近 <span class="panel-hint">点击行展开看阵容</span></div>'
                +     '<div class="panel-body abyss-rows" id="abyss-'+esc(k)+'">加载中...</div>'
                +   '</div>'
                +   '<div class="ac-panel h-fixed-tall chars-pane">'
                +     '<div class="panel-title">'+esc(charsTitle)+'</div>'
                +     '<div class="panel-body" id="chars-'+esc(k)+'">加载中...</div>'
                +   '</div>'
                + '</div>'
                + '<div class="detail-ops" style="margin-top:14px">'
                +   '<button class="btn tiny" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameCollectOne(this)">刷新此账号数据</button>'
                +   '<button class="btn tiny danger" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameUnbind(this)">解绑</button>'
                + '</div>';

            el.innerHTML = html;

            // 异步填三块内容（状态条已在初始 render 直出）
            _fillAbyss(a, k);
            _fillGacha(a, k);
            _fillCharacters(a, k);
        }

        var _charFilter = {};   // uid -> 'all'|'r5'|'r4'
        var _charsCache = {};   // key='gs::uid' -> {chars, byId}（abyss + chars panel 共用）

        async function _ensureChars(a, k){
            if(_charsCache[k]) return _charsCache[k];
            try{
                // 用 _fetchT 加 10s 超时，否则 fetch 卡住时整个面板永卡"加载中"
                // _fetchT 在下方定义；此处函数提升后引用安全（async 函数体内运行时已解析）
                var fetcher = (typeof _fetchT === 'function') ? _fetchT : fetch;
                var r = await fetcher('/api/game/characters?game='+a.game+'&uid='+encodeURIComponent(a.uid), 10000);
                var d = await r.json();
                var chars = d.characters || [];
                var byId = {};
                chars.forEach(function(c){ byId[String(c.avatar_id)] = c; });
                _charsCache[k] = {chars: chars, byId: byId};
            }catch(_){
                _charsCache[k] = {chars: [], byId: {}};
            }
            return _charsCache[k];
        }

        async function _fillCharacters(a, k){
            var slot = document.getElementById('chars-'+k);
            if(!slot) return;
            var cache = await _ensureChars(a, k);
            var chars = cache.chars;
            if(chars.length === 0){
                slot.innerHTML = '<div class="coming-soon">'
                    + '  <div class="cs-title">暂无角色数据</div>'
                    + '  点底部"刷新此账号数据"抓取'
                    + '</div>';
                return;
            }
            var filter = _charFilter[a.uid] || 'all';
            var visible = chars.filter(function(c){
                if(filter === 'r5') return c.rarity >= 5;
                if(filter === 'r4') return c.rarity === 4;
                return true;
            });
            var count5 = chars.filter(function(c){return c.rarity >= 5;}).length;
            var count4 = chars.filter(function(c){return c.rarity === 4;}).length;
            var maxLv = chars.filter(function(c){return c.level >= 90;}).length;
            var filters = [
                {k:'all', label:'全部 '+chars.length},
                {k:'r5',  label:'5 星 '+count5},
                {k:'r4',  label:'4 星 '+count4},
            ];
            var filterHtml = '<div class="char-filter-bar">' + filters.map(function(f){
                return '<span class="char-filter '+(filter===f.k?'active':'')
                    + '" onclick="setCharFilter(\\''+esc(a.uid)+'\\',\\''+f.k+'\\')">'+esc(f.label)+'</span>';
            }).join('') + '</div>';

            var statHtml = '<div class="char-stat-line">'
                + '<span class="num">'+chars.length+'</span> 角色 · '
                + '5★ <span class="num">'+count5+'</span> · '
                + '满级 <span class="num">'+maxLv+'</span>'
                + '</div>';

            // 单列 list：每行 icon + 名字+lv + 命+精 + 武器名
            var rowsHtml = '<div class="char-list">' + visible.map(function(c){
                var iconStyle = c.icon_url ? 'background-image:url('+esc(c.icon_url)+')' : '';
                var ca = (c.constellation||0) + '+' + (c.weapon && c.weapon.rarity>=5 ? (c.weapon.affix||0) : 0);
                var wpName = (c.weapon && c.weapon.name) ? c.weapon.name : '';
                var wpLv = (c.weapon && c.weapon.level) ? (' L'+c.weapon.level) : '';
                var wpRarity = (c.weapon && c.weapon.rarity) || 0;
                var wpCls = wpRarity >= 5 ? 'wp5' : (wpRarity === 4 ? 'wp4' : '');
                return '<div class="char-row r'+c.rarity+'">'
                    + '<div class="char-icon-sm" style="'+iconStyle+'"></div>'
                    + '<div class="char-info">'
                    +   '<div class="char-line1"><span class="char-name">'+esc(c.name)+'</span>'
                    +   '<span class="char-lv">Lv.'+c.level+'</span>'
                    +   '<span class="char-ca">'+ca+'</span></div>'
                    +   '<div class="char-line2 '+wpCls+'">'+(wpName?esc(wpName)+esc(wpLv):'<span class="muted">无武器</span>')+'</div>'
                    + '</div>'
                    + '</div>';
            }).join('') + '</div>';

            slot.innerHTML = statHtml + filterHtml + rowsHtml;
        }

        window.setCharFilter = function(uid, key){
            _charFilter[uid] = key;
            var a = _allAccs.find(function(x){return x.uid === uid;});
            if(a) _fillCharacters(a, keyOf(a));
        };

        async function _fillAbyss(a, k){
            var defs = ABYSS_DEFS[a.game] || [];
            var slot = document.getElementById('abyss-'+k);
            if(!slot) return;
            if(defs.length === 0){ slot.innerHTML = '<div class="abyss-empty">—</div>'; return; }
            try { await _fillAbyssCore(a, k, defs, slot); }
            catch(err) {
                // 任何 JS 错误都会让 slot 永卡"加载中..."；这里兜底显示具体错误
                console.error('[战绩] _fillAbyss 异常', a.game, a.uid, err);
                slot.innerHTML = '<div class="abyss-empty">加载失败：' + esc(String(err && err.message || err)) + '</div>';
            }
        }

        // fetch + 10s 超时；防浏览器旧标签页 hold 着死 connection 让 await 永卡
        function _fetchT(url, timeoutMs){
            timeoutMs = timeoutMs || 10000;
            var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
            var t = setTimeout(function(){ if(ctrl) ctrl.abort(); }, timeoutMs);
            var p = fetch(url, ctrl ? {signal: ctrl.signal} : {});
            return p.finally(function(){ clearTimeout(t); });
        }

        async function _fillAbyssCore(a, k, defs, slot){
            // 同时拉 abyss_latest（每副本 1 个）+ characters（队伍补 name/cons/weapon）
            var charsP = _ensureChars(a, k);
            var resultsP = Promise.all(defs.map(function(def){
                return _fetchT('/api/game/abyss_latest?game='+a.game+'&uid='+encodeURIComponent(a.uid)+'&type='+def.type, 10000)
                    .then(function(r){return r.json();})
                    .catch(function(){return {abyss:null};});
            }));
            var results = await resultsP;
            var charsCache = await charsP;
            var charsById = (charsCache && charsCache.byId) || {};
            // 主力角色聚合：跨副本统计 avatar 出现次数 → top chips
"""
