/* game 页脚本 — 水神 mihoyo 游戏面板（GS/SR/ZZZ 状态/签到/抽卡/战报） */

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
                    if(/^https?:\/\//i.test(href)){
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
                        +'" data-tab-key="'+t.key+'" onclick="switchGameTab(\''+t.key+'\')">'+_tabLabel(t)+'</button>';
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
                // pane 顶部：水神资讯 + 角色搜索（替代原账号卡内的资讯订阅栏）
                var furinaHtml = (typeof renderFurinaTabSection === 'function')
                    ? renderFurinaTabSection(key) : '';
                pane.innerHTML = furinaHtml + accs.map(_renderFullCard).join('');
                // 异步拉该 game 最新资讯 + 角色搜索历史缓存
                if(typeof loadFurinaNews === 'function') loadFurinaNews(key);
                if(typeof loadFurinaCharacterLatest === 'function') loadFurinaCharacterLatest(key);
                // 异步填每个账号的战报/抽卡（模拟展开效果）
                accs.forEach(function(a){ _fillAccountDetail(a); });
            }
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
                + '    <button class="ac-toggle" onclick="switchGameTab(\''+esc(a.game)+'\')">看详细 →</button>'
                + '  </div>'
                + '</div>'
                + '</div>';
        }

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
                + '<div class="ac-detail open" id="detail-'+esc(k)+'">加载中...</div>'
                + '</div>';
        }

        function _renderSummary(a, meta, n){
            if(!n || !n.max_resin){
                return '<div class="ac-status">'
                    + '<div style="color:var(--pm-text-muted);font-size:12px;">暂无便笺数据（上次签到 '+(a.last_sign_at>0?fmtRelative(a.last_sign_at):'-')+'）</div>'
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
                    + '" onclick="setCharFilter(\''+esc(a.uid)+'\',\''+f.k+'\')">'+esc(f.label)+'</span>';
            }).join('') + '</div>';

            var statHtml = '<div class="char-stat-line">'
                + '<span class="num">'+chars.length+'</span> 角色 · '
                + '5★ <span class="num">'+count5+'</span> · '
                + '满级 <span class="num">'+maxLv+'</span>'
                + '</div>';

            // 单列 list：每行 icon + 名字+lv + 命+精 + 武器名 + hover 角色调研按钮
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
                    + '<button class="char-research-btn" title="查 '+esc(c.name)+' 的攻略 / 配队" '
                    +     'onclick="furinaSearchFromChar(\''+esc(a.game)+'\',\''+esc(c.name)+'\')">🔍</button>'
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
            var heroCount = {};
            var rowTeams = [];   // 缓存每行的 teams 避免重复 extract
            results.forEach(function(res, i){
                var ab = res.abyss;
                if(!ab){ rowTeams.push([]); return; }
                var ts = _extractTeams(a.game, defs[i].type, ab.raw, charsById);
                rowTeams.push(ts);
                ts.forEach(function(t){
                    (t.avatars||[]).forEach(function(av){
                        if(av.name) heroCount[av.name] = (heroCount[av.name]||0) + 1;
                    });
                });
            });
            var topHeroes = Object.keys(heroCount).map(function(n){return {n:n, c:heroCount[n]};})
                .sort(function(a,b){return b.c - a.c;}).slice(0, 6);
            var topHeroesHtml = '';
            if(topHeroes.length){
                topHeroesHtml = '<div class="top-heroes-label">主力出场（跨副本队伍）</div>'
                    + '<div class="top-heroes">'
                    + topHeroes.map(function(h){
                        return '<span class="hero-chip">'+esc(h.n)+'<span class="cnt">×'+h.c+'</span></span>';
                    }).join('')
                    + '</div>';
            }

            var rows = defs.map(function(def, i){
                var ab = results[i].abyss;
                if(!ab){
                    return '<div class="abyss-row" style="cursor:default">'
                        + '<span class="abyss-name">'+esc(def.name)+'</span>'
                        + '<span class="abyss-floor">-</span>'
                        + '<span class="abyss-star">-</span>'
                        + '<span class="abyss-meta">未挑战</span>'
                        + '</div>';
                }
                // 组装展示字段
                var floorVal, starVal, metaVal;
                if(a.game === 'zzz' && def.type === 'shiyu'){
                    floorVal = '评级 ' + (ab.max_floor || '-');
                    starVal = ab.total_star + '分';
                    metaVal = ab.total_battle > 0 ? (ab.total_battle+'s') : fmtRelative(ab.scan_ts);
                }else if(def.type === 'stygian'){
                    floorVal = '难度 ' + (ab.max_floor || '-');
                    starVal = ab.total_star + 's';
                    metaVal = fmtRelative(ab.scan_ts);
                }else if(def.type === 'poetry'){
                    floorVal = '第 ' + (ab.max_floor || '-') + ' 轮';
                    starVal = ab.total_star + '★';
                    metaVal = fmtRelative(ab.scan_ts);
                }else{
                    // spiral / forgotten_hall / pure_fiction / apocalyptic / mem
                    floorVal = String(ab.max_floor || '-');
                    starVal = ab.total_star + '★';
                    if(ab.total_battle > 0){
                        metaVal = ab.total_win + '/' + ab.total_battle;
                    }else{
                        metaVal = fmtRelative(ab.scan_ts);
                    }
                }
                var teams = rowTeams[i] || [];
                var hasTeams = teams.length > 0;
                var indicator = hasTeams ? '<span class="abyss-toggle">▴</span>' : '';
                var rowHtml = '<div class="abyss-row" '+(hasTeams?'onclick="toggleAbyssTeams(\''+esc(k)+'\','+i+')"':'style="cursor:default"')+'>'
                    + '<span class="abyss-name">'+esc(def.name)+indicator+'</span>'
                    + '<span class="abyss-floor">'+esc(floorVal)+'</span>'
                    + '<span class="abyss-star">'+esc(String(starVal))+'</span>'
                    + '<span class="abyss-meta">'+esc(String(metaVal))+'</span>'
                    + '</div>';
                var teamsHtml = hasTeams
                    ? '<div class="abyss-teams" id="abyss-teams-'+esc(k)+'-'+i+'">'+_renderTeams(teams)+'</div>'
                    : '';
                return rowHtml + teamsHtml;
            });
            slot.innerHTML = topHeroesHtml + rows.join('');
        }

        // 从 abyss.raw 解析每场战斗的队伍。
        // spiral / forgotten_hall 等接口的 avatar 只有 id/level/rarity 没 name/cons/weapon
        // → 必须用 charsById（mihoyo_character 表）反查
        function _extractTeams(game, abyssType, raw, charsById){
            if(!raw || typeof raw !== 'object') return [];
            charsById = charsById || {};
            var norm = function(av){ return _normAvatar(av, charsById); };
            var teams = [];
            try{
                if(game === 'gs' && abyssType === 'spiral'){
                    (raw.floors || []).forEach(function(floor){
                        (floor.levels || []).forEach(function(level){
                            (level.battles || []).forEach(function(battle){
                                var half = battle.index === 1 ? '上' : (battle.index === 2 ? '下' : '#'+battle.index);
                                teams.push({
                                    label: (floor.index||'?')+'-'+(level.index||'?')+' '+half,
                                    stars: level.star || 0,
                                    max_star: level.max_star || 0,
                                    avatars: (battle.avatars || []).map(norm),
                                });
                            });
                        });
                    });
                }else if(game === 'gs' && abyssType === 'poetry'){
                    // 幻想真境剧诗：detail.rounds_data[]（米游社字段名是 rounds_data 不是 rounds）
                    var detail = raw.detail || raw;
                    (detail.rounds_data || raw.rounds || []).forEach(function(r, i){
                        var avs = r.avatars || r.role || [];
                        if(avs.length){
                            teams.push({
                                label: '第 '+(r.round_id || i+1)+' 轮' + (r.is_get_medal ? ' ★' : ''),
                                stars: r.is_get_medal ? 1 : 0,
                                avatars: avs.map(norm),
                            });
                        }
                    });
                }else if(game === 'gs' && abyssType === 'stygian'){
                    var chs = (raw.single && raw.single.challenge) || raw.challenge || [];
                    chs.forEach(function(c, i){
                        var avs = c.teams || c.avatars || [];
                        if(avs.length){
                            teams.push({
                                label: c.name || ('挑战 '+(i+1)),
                                stars: c.difficulty || 0,
                                avatars: avs.map(norm),
                            });
                        }
                    });
                }else if(game === 'sr' && abyssType === 'peak'){
                    // 异相仲裁：challenge_peak_records[].mob_records[].avatars + boss_record.avatars
                    (raw.challenge_peak_records || []).forEach(function(rec, ri){
                        var groupName = (rec.group && rec.group.name) || ('挑战 '+(ri+1));
                        // 普通怪战
                        (rec.mob_records || []).forEach(function(mob, mi){
                            var avs = mob.avatars || [];
                            if(avs.length){
                                teams.push({
                                    label: groupName + ' 怪 #' + (mi+1),
                                    stars: mob.star_num || 0,
                                    avatars: avs.map(norm),
                                });
                            }
                        });
                        // BOSS 战
                        var br = rec.boss_record;
                        if(br && (br.avatars || []).length){
                            teams.push({
                                label: groupName + ' BOSS',
                                stars: br.star_num || 0,
                                avatars: br.avatars.map(norm),
                            });
                        }
                    });
                }else if(game === 'sr'){
                    (raw.all_floor_detail || []).forEach(function(f){
                        var nodeKeys = Object.keys(f).filter(function(k){
                            return k.indexOf('node_') === 0 && !isNaN(parseInt(k.slice(5), 10));
                        }).sort(function(a,b){
                            return parseInt(a.replace('node_',''),10) - parseInt(b.replace('node_',''),10);
                        });
                        nodeKeys.forEach(function(nk){
                            var node = f[nk];
                            if(node && (node.avatars || []).length){
                                teams.push({
                                    label: (f.name||'层') + ' ' + nk.replace('node_','节'),
                                    stars: f.star_num || 0,
                                    avatars: node.avatars.map(norm),
                                });
                            }
                        });
                    });
                }else if(game === 'zzz' && abyssType === 'shiyu'){
                    // ZZZ 式舆防卫战：hadal_info_v2.{fitfh,fourth}_layer_detail.layer_challenge_info_list[]
                    // 每层 N 个挑战，每个 challenge 含 avatar_list
                    var v2 = raw.hadal_info_v2 || raw;
                    [['fitfh_layer_detail','第 5 层'], ['fourth_layer_detail','第 4 层']].forEach(function(pair){
                        var layer = v2[pair[0]] || {};
                        var infos = layer.layer_challenge_info_list || [];
                        infos.forEach(function(c, idx){
                            var avs = c.avatar_list || c.avatars || [];
                            if(avs.length){
                                teams.push({
                                    label: pair[1] + ' #' + (c.layer_id || idx+1),
                                    stars: c.rating || c.score || 0,
                                    avatars: avs.map(norm),
                                });
                            }
                        });
                    });
                }else if(game === 'zzz'){
                    // 危局/其他：list/floor_detail 兜底
                    var list = raw.list || raw.all_floor_detail || raw.floor_detail
                        || (raw.memory_list) || [];
                    list.forEach(function(it, idx){
                        var avs = it.avatar_list || it.avatars || [];
                        if(avs.length){
                            teams.push({
                                label: it.name || it.level_name || it.layer_name || ('节 '+(idx+1)),
                                stars: it.score || it.star || it.layer_index || 0,
                                avatars: avs.map(norm),
                            });
                        }
                    });
                }
            }catch(e){
                console.error('[战报] 队伍解析失败', game, abyssType, e);
            }
            return teams;
        }

        // raw avatar → 统一格式，name/cons/weapon 缺时从 mihoyo_character 表（charsById）补
        function _normAvatar(av, charsById){
            charsById = charsById || {};
            var id = String(av.id || av.avatar_id || '');
            var c = charsById[id] || {};
            // ZZZ rarity 是字符串 "S"/"A"/"B"，转数字便于统一渲染颜色
            var rawRarity = av.rarity != null ? av.rarity : (av.rank != null ? av.rank : c.rarity);
            var rarity;
            if(typeof rawRarity === 'string'){
                var m = {'S':5, 'A':4, 'B':3};
                rarity = m[rawRarity] || 4;
            }else{
                rarity = rawRarity || 4;
            }
            // ZZZ avatar.rank 在 raw 里是「影画/命之座」（不是 rarity），优先信 charsById.constellation
            var cons = (c.constellation != null ? c.constellation : (av.rank != null && typeof av.rank === 'number' ? av.rank : 0));
            return {
                id: id,
                name: av.name || av.full_name || c.name || '',
                level: av.level || av.cur_level || c.level || 0,
                rarity: rarity,
                cons: cons,
                weapon: c.weapon || {},
            };
        }

        // 命座+精炼格式：0+0 / 0+1 / 2+1（精炼仅 5 星武器算）
        function _consAffix(av){
            var cons = av.cons || 0;
            var affix = 0;
            if(av.weapon && av.weapon.rarity >= 5){
                affix = av.weapon.affix || 0;
            }
            return cons + '+' + affix;
        }

        function _renderTeams(teams){
            return teams.map(function(t){
                var avHtml = (t.avatars || []).map(function(av){
                    var rcls = av.rarity >= 5 ? 'r5' : (av.rarity === 4 ? 'r4' : '');
                    var ca = _consAffix(av);
                    var nameTxt = av.name || ('id:'+av.id);
                    var weaponInfo = (av.weapon && av.weapon.name) ? (av.weapon.name + (av.weapon.affix?(' 精'+av.weapon.affix):'')) : '';
                    var tip = nameTxt + ' Lv'+(av.level||'?') + (weaponInfo?(' · '+weaponInfo):'');
                    return '<span class="abyss-team-avatar '+rcls+'" title="'+esc(tip)+'">'
                        + esc(nameTxt)
                        + ' <span class="ca">'+ca+'</span>'
                        + '</span>';
                }).join('');
                var starInfo = t.stars > 0
                    ? ' <span style="color:var(--pm-primary);font-family:monospace">'+t.stars+(t.max_star?('/'+t.max_star):'')+'★</span>'
                    : '';
                return '<div class="abyss-team">'
                    + '<span class="abyss-team-label">'+esc(t.label)+starInfo+'</span>'
                    + avHtml
                    + '</div>';
            }).join('');
        }

        window.toggleAbyssTeams = function(k, i){
            var el = document.getElementById('abyss-teams-'+k+'-'+i);
            if(!el) return;
            el.classList.toggle('closed');
            var row = el.previousElementSibling;
            var toggle = row && row.querySelector('.abyss-toggle');
            if(toggle) toggle.textContent = el.classList.contains('closed') ? '▾' : '▴';
        };

        async function _fillGacha(a, k){
            var slot = document.getElementById('gacha-'+k);
            if(!slot) return;
            var labels = POOL_LABELS_BY_GAME[a.game] || {};
            var poolKeys = POOL_ORDER_BY_GAME[a.game] || [];
            if(poolKeys.length === 0){
                slot.innerHTML = '<div class="gacha-empty">暂不支持此游戏</div>';
                return;
            }
            var pool = _currentPool[k];
            if(!pool || !labels[pool]) pool = poolKeys[0];
            _currentPool[k] = pool;

            var poolsHtml = '<div class="gacha-head">'
                + poolKeys.map(function(p){
                    return '<span class="gpool '+(p===pool?'active':'')+'" onclick="gameSelectPool(\''+esc(k)+'\',\''+p+'\')">'+labels[p]+'</span>';
                }).join('') + '</div>';

            var fetcher = (typeof _fetchT === 'function') ? _fetchT : fetch;
            var r = await fetcher('/api/game/gacha/stats?game='+a.game+'&uid='+encodeURIComponent(a.uid)+'&gacha_type='+pool, 10000);
            var d = await r.json();
            var s = d.stats || {total:0};
            var syncBtn = _gachaSyncBtn(a);
            if(!s.total){
                var emptyHint = a.game === 'sr'
                    ? '暂无数据，点右下角"URL 导入"（米哈游限制 SR 不能自动同步）'
                    : '暂无数据，点右下角"同步抽卡"';
                slot.innerHTML = poolsHtml
                    + '<div class="gacha-empty">'+emptyHint+'</div>'
                    + syncBtn;
                _resumeGachaSyncIfRunning(a, slot);
                return;
            }
            var hardPity = s.hard_pity || 90;
            // 软保底 = 硬保底 × 0.8（GS 角色 73 / 武器 63；近似）
            var softThreshold = Math.floor(hardPity * 0.8);
            var pityCls = s.pity_5 >= hardPity - 10 ? 'warn' : (s.pity_5 >= softThreshold ? 'soft' : '');
            var topName = (a.game === 'zzz') ? 'S 级' : '5 星';
            var fives = (s.fives||[]).slice(0, 30);
            var fivesHtml = fives.length === 0
                ? '<div class="gacha-empty">此池暂无 '+topName+'</div>'
                : fives.map(function(f){
                    var pull = f.pull_count || 0;
                    var pullCls = pull <= 30 ? 'lucky' : (pull >= softThreshold ? 'heavy' : '');
                    var upHtml;
                    if(f.is_up === true){
                        upHtml = '<span class="gfive-up on" title="UP 出货">UP</span>';
                    }else if(f.is_up === false){
                        upHtml = '<span class="gfive-up off" title="出了常驻 = 歪了">歪</span>';
                    }else{
                        upHtml = '<span class="gfive-up none" title="此池无 UP 概念">—</span>';
                    }
                    return '<div class="gfive">'
                        + '<span class="gfive-badge">★</span>'
                        + '<span class="gfive-name">'+esc(f.name)+'</span>'
                        + '<span class="gfive-pull '+pullCls+'">'+pull+'抽</span>'
                        + upHtml
                        + '<span class="gfive-time">'+esc((f.time||'').slice(5,16))+'</span>'
                        + '</div>';
                }).join('');
            // 最欧 / 最歪 caption
            var allFives = s.fives || [];
            var luckRow = '';
            if(allFives.length){
                var pulls = allFives.map(function(f){return f.pull_count||0;}).filter(function(x){return x>0;});
                if(pulls.length){
                    var minP = Math.min.apply(null, pulls);
                    var maxP = Math.max.apply(null, pulls);
                    var luckiest = allFives.find(function(f){return f.pull_count===minP;});
                    var heaviest = allFives.find(function(f){return f.pull_count===maxP;});
                    luckRow = '<div class="gacha-luck-row">'
                        + '<span class="luck-item lucky">最欧 <span class="v">'+minP+'抽</span> '+esc(luckiest?luckiest.name:'')+'</span>'
                        + '<span class="luck-item heavy">最歪 <span class="v">'+maxP+'抽</span> '+esc(heaviest?heaviest.name:'')+'</span>'
                        + '</div>';
                }
            }
            slot.innerHTML = poolsHtml
                + '<div class="gacha-summary">总抽 <span class="pity">'+s.total
                + '</span><span class="sep">·</span>'+topName+'保底 <span class="pity '+pityCls+'">'+s.pity_5+'/'+hardPity
                + '</span><span class="sep">·</span>已出 '+topName+' <span class="pity">'+s.count_5
                + '</span><span class="sep">·</span>平均 <span class="pity">'+s.avg_pity_5+'</span></div>'
                + luckRow
                + '<div class="gacha-five-list">'+fivesHtml+'</div>'
                + syncBtn;
            _resumeGachaSyncIfRunning(a, slot);
        }

        async function _resumeGachaSyncIfRunning(a, slot){
            try{
                var sr = await fetch('/api/game/gacha/sync/status?game='+a.game+'&uid='+encodeURIComponent(a.uid));
                var sd = await sr.json();
                if(sd.state === 'running'){
                    var btn = slot.querySelector('button[onclick*="gameSyncGacha"]');
                    _pollGachaSync(a.game, a.uid, btn);
                }
            }catch(_){}
        }

        function _gachaSyncBtn(a, label){
            label = label || '同步抽卡';
            // SR 米哈游限制 stoken→authkey，必须走 URL 导入；GS/ZZZ 自动同步即可
            var btns = a.game === 'sr'
                ? '<button class="btn primary tiny" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameImportGachaUrl(this.dataset.game, this.dataset.uid)">URL 导入</button>'
                : '<button class="btn primary tiny" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameSyncGacha(this)">'+esc(label)+'</button>';
            return '<div class="gacha-sync-row">'
                + '<span class="gacha-sync-status" id="gsync-status-'+esc(keyOf(a))+'"></span>'
                + btns
                + '</div>';
        }

        // ============ 操作 ============
        window.gameSignOne = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            btn.disabled = true; var old = btn.textContent; btn.textContent = '...';
            try{
                var r = await fetch('/api/game/sign', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game, uid}),
                });
                var d = await r.json();
                btn.textContent = d.ok ? '✓' : '✗';
                if(!d.ok && d.msg) window.pmToast.error('签到失败: '+d.msg);
                setTimeout(function(){ btn.textContent = old; btn.disabled = false; loadOverview(); }, 1200);
            }catch(e){
                btn.textContent='✗'; setTimeout(function(){btn.textContent=old;btn.disabled=false;},2000);
            }
        };

        // 「刷新此账号数据」background + 轮询：完成后自动重渲该账号详情，无需手动刷新页面
        var _collectPollTimers = {};   // key='game::uid' -> interval id

        window.gameCollectOne = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            var k = game+'::'+uid;
            console.log('[水神·采集] 触发', game, uid);
            btn.disabled = true; var old = btn.textContent; btn.textContent = '启动...';
            try{
                var r = await fetch('/api/game/collect_one', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game, uid}),
                });
                var d = await r.json();
                if(!d.ok){
                    window.pmToast.error('采集启动失败: '+(d.msg||''));
                    btn.textContent = old; btn.disabled = false;
                    return;
                }
                btn.textContent = '采集中...';
                if(_collectPollTimers[k]){ clearInterval(_collectPollTimers[k]); }
                var poll = async function(){
                    try{
                        var sr = await fetch('/api/game/collect_one/status?game='+game+'&uid='+encodeURIComponent(uid));
                        var sd = await sr.json();
                        if(sd.state === 'running'){
                            return;   // 等下次 tick
                        }
                        clearInterval(_collectPollTimers[k]); delete _collectPollTimers[k];
                        if(sd.state === 'done'){
                            console.log('[水神·采集] DONE', sd.counts);
                            btn.textContent = '✓ 已更新';
                            // 数据已落库 → 清缓存 + 重渲该账号详情区（无需手动刷新）
                            delete _charsCache[k];
                            var a = _allAccs.find(function(x){return x.uid === uid && x.game === game;});
                            if(a){
                                _fillAbyss(a, k);
                                _fillCharacters(a, k);
                                // 摘要也重新拉一次（树脂/委托数据更新）
                                if(typeof loadOverview === 'function') loadOverview();
                            }
                        }else if(sd.state === 'failed'){
                            btn.textContent = '✗ 失败';
                            window.pmToast.error('采集失败: '+(sd.error||''));
                        }
                        setTimeout(function(){btn.textContent=old;btn.disabled=false;}, 3000);
                    }catch(e){
                        clearInterval(_collectPollTimers[k]); delete _collectPollTimers[k];
                        console.error('[水神·采集] poll 异常', e);                        btn.textContent = old; btn.disabled = false;
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
            var ok = await window.pmModal.confirm({
                title: '解绑账号',
                message: '解绑 '+uid+' ？便笺 / 战报 / 抽卡记录都会清掉。',
                confirmText: '解绑',
                danger: true,
            });
            if(!ok) return;
            await fetch('/api/game/unbind', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({game, uid}),
            });
            delete _openState[game+'::'+uid];
            loadOverview();
            window.pmToast.success('已解绑');
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
                            var lines = keys.map(function(p){return p+': '+errs[p];}).join('\n');
                            var firstErr = errs[keys[0]] || '';
                            var isAuthKeyErr = (allFail && firstErr.indexOf('-100') >= 0);
                            if(isAuthKeyErr && game === 'sr'){
                                // 米哈游对 SR 抽卡 authkey 限制——stoken→authkey 路径被拒。
                                // 只能让用户从游戏内复制 URL 手动导入。
                                window.gameImportGachaUrl(game, uid);
                            }else if(isAuthKeyErr){
                                // GS/ZZZ 失败更可能是账号未真实绑定 → 一键解绑重绑
                                var ok = await window.pmModal.confirm({
                                    title: game.toUpperCase()+' 抽卡同步全部失败',
                                    message: lines + '\n\n这通常意味着该 '+uid+' 账号在米游社侧未成功绑定。是否立即解绑此账号并重新扫码？（解绑会清掉该账号的便笺/战报/抽卡缓存）',
                                    confirmText: '解绑并重扫',
                                    danger: true,
                                });
                                if(ok){
                                    try{
                                        await fetch('/api/game/unbind', {
                                            method:'POST', headers:{'Content-Type':'application/json'},
                                            body: JSON.stringify({game, uid}),
                                        });
                                        if(typeof loadOverview === 'function') loadOverview();
                                        if(typeof openQrModal === 'function') openQrModal();
                                    }catch(unbindErr){
                                        window.pmToast.error('解绑失败: '+unbindErr+'，请手动展开账号详情 → 点右下角"解绑"');
                                    }
                                }
                            }else{
                                var prefix = allFail ? game.toUpperCase()+' 同步全部失败：\n' : game.toUpperCase()+' 部分池子失败：\n';
                                window.pmToast.warning(prefix + lines, {duration: 6000});
                            }
                        }
                    }else if(s.state === 'failed'){
                        _stopGachaPoll(k);
                        console.error('[水神·抽卡] '+k+' FAILED', s.error);
                        if(statusEl){ statusEl.className = 'gacha-sync-status failed'; statusEl.textContent = '✗ ' + (s.error||''); }
                        if(btn){ btn.disabled = false; btn.textContent = '同步抽卡'; }
                        window.pmToast.error('同步失败: '+(s.error||''));
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
                    window.pmToast.error('启动失败: '+(d.msg||''));
                    btn.disabled = false; btn.textContent = old;
                    return;
                }
                _pollGachaSync(game, uid, btn);
            }catch(e){
                console.error('[水神·抽卡] /sync 异常', e);
                window.pmToast.error('请求异常: '+e);
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
                + '<br><span style="color:var(--pm-text-muted)">链接 24 小时内有效；过期重新拿即可</span>',
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
                window.pmToast.error('复制失败，请手动选中复制：'+e);
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
            if(!url){ window.pmToast.warning('请粘贴 URL'); return; }
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
                    window.pmToast.error('启动失败: '+(d.msg||''));
                    return;
                }
                closeUrlImportModal();
                _pollGachaSync(ctx.game, ctx.uid, null);
            }catch(e){
                console.error('[水神·抽卡] /import_url 异常', e);
                window.pmToast.error('请求异常: '+e);
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

        // ─── 水神资讯 + 角色搜索（嵌入各 game tab 顶部，不另造 tab）─────
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
                + '          onkeydown="if(event.key===\'Enter\')furinaSearchCharacter(\''+esc(game)+'\',document.getElementById(\'fr-search-btn-'+esc(game)+'\'))" />'
                + '        <button class="btn primary tiny" id="fr-search-btn-'+esc(game)+'" onclick="furinaSearchCharacter(\''+esc(game)+'\',this)">搜索</button>'
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
                if(/^https?:\/\//i.test(href)){
                    e.preventDefault();
                    window.open(href, '_blank', 'noopener,noreferrer');
                }
            });
        };
    })();
