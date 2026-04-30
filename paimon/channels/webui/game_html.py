"""水神 · 游戏面板 — 米哈游账号 + 便笺 + 战报 + 抽卡

4 tab：
- 账号：扫码绑定 + 列表（显示 UID / 上次签到 / 解绑）
- 便笺：树脂条 + 委托 + 派遣（只对原神账号）
- 战报：深渊 / 剧诗最新一期
- 抽卡：URL 导入 + 小保底统计 + 五星时间轴
"""
from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)


GAME_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1280px; margin: 0 auto; padding: 24px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .page-header .sub { font-size: 13px; color: var(--text-muted); margin-top: 4px; }

    .tabs { display: flex; gap: 4px; margin-bottom: 20px; border-bottom: 1px solid var(--paimon-border); }
    .tab-btn {
        padding: 10px 20px; background: transparent; border: none; color: var(--text-muted);
        cursor: pointer; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active { color: var(--gold); border-bottom-color: var(--gold); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    /* 表格：所有列 th/td 居中对齐（按 UI 记忆规则） */
    .game-table-wrap { overflow-x: auto; }
    .game-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 12px; }
    .game-table th, .game-table td {
        padding: 10px 12px; border-bottom: 1px solid var(--paimon-border);
        text-align: center; vertical-align: middle; white-space: nowrap;
    }
    .game-table th {
        color: var(--gold); font-weight: 600; font-size: 12px; background: var(--paimon-panel);
    }
    .game-table tbody tr:hover td { background: var(--paimon-panel); }
    .game-table td.code { font-family: monospace; color: var(--text-muted); }
    .game-table td.note { font-size: 12px; color: var(--text-muted); }
    /* 操作列：按钮之间空一点 */
    .game-table td.actions { white-space: nowrap; }
    .game-table td.actions .btn-action { margin: 0 4px; padding: 5px 12px; font-size: 12px; }

    .empty-state { padding: 32px; text-align: center; color: var(--text-muted); }

    /* 账号绑定区 */
    .bind-row { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
    .bind-card {
        flex: 1; min-width: 320px;
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 20px;
    }
    .bind-card h3 { color: var(--gold); font-size: 15px; margin-bottom: 12px; }
    .bind-card p { font-size: 13px; color: var(--text-secondary); line-height: 1.6; }
    .qr-box {
        width: 240px; height: 240px; background: #fff; border-radius: 8px;
        margin: 12px auto; display: flex; align-items: center; justify-content: center;
    }
    .qr-box img { width: 100%; height: 100%; }
    .qr-status { text-align: center; font-size: 13px; color: var(--text-muted); margin-top: 8px; }

    .btn-action {
        padding: 8px 16px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .btn-action:hover { border-color: var(--gold-dark); color: var(--gold); }
    .btn-action.primary {
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        color: #000; border: none; font-weight: 600;
    }
    .btn-action.danger:hover { color: var(--status-error); border-color: var(--status-error); }
    .btn-action:disabled { opacity: .5; cursor: not-allowed; }

    /* 便笺卡片 */
    .note-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 20px; margin-bottom: 16px;
    }
    .note-head {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 16px;
    }
    .note-head h3 { color: var(--gold); font-size: 15px; }
    .note-head .uid { font-family: monospace; font-size: 12px; color: var(--text-muted); }
    .resin-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
    .resin-label {
        font-size: 13px; color: var(--text-secondary); min-width: 80px;
    }
    .resin-bar {
        flex: 1; height: 14px; background: var(--paimon-border);
        border-radius: 7px; overflow: hidden; position: relative;
    }
    .resin-fill {
        height: 100%; background: linear-gradient(90deg, #6ec6ff, #bb86fc);
        border-radius: 7px; transition: width .3s;
    }
    .resin-fill.full { background: linear-gradient(90deg, var(--status-error), var(--gold)); }
    .resin-text {
        min-width: 90px; text-align: right;
        font-family: monospace; font-size: 13px; color: var(--text-primary);
    }
    .note-grid {
        display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 12px;
    }
    .note-mini {
        padding: 10px; background: var(--paimon-bg); border-radius: 6px; text-align: center;
    }
    .note-mini-num { font-size: 18px; font-weight: 600; color: var(--gold); }
    .note-mini-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
    .expeditions { margin-top: 16px; }
    .expeditions h4 { font-size: 13px; color: var(--text-secondary); margin-bottom: 8px; }
    .exp-item {
        display: inline-block; margin-right: 12px; margin-bottom: 6px;
        padding: 4px 10px; background: var(--paimon-bg); border-radius: 12px; font-size: 12px;
    }
    .exp-item.ready { color: var(--status-success); border: 1px solid var(--status-success); }

    /* 战报卡片 */
    .abyss-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 20px; margin-bottom: 16px;
    }
    .abyss-head {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--paimon-border);
    }
    .abyss-title { color: var(--gold); font-size: 15px; }
    .abyss-period { font-size: 11px; color: var(--text-muted); font-family: monospace; }
    .abyss-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
    .abyss-stat { text-align: center; }
    .abyss-stat-num { font-size: 26px; font-weight: 700; color: var(--gold); }
    .abyss-stat-label { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

    /* 抽卡 */
    .gacha-tools {
        background: var(--paimon-panel); padding: 16px; border-radius: 8px; margin-bottom: 16px;
    }
    .gacha-tools input[type=text] {
        flex: 1; padding: 8px 12px; background: var(--paimon-bg);
        color: var(--text-primary); border: 1px solid var(--paimon-border); border-radius: 6px;
        font-size: 13px; font-family: monospace;
    }
    .gacha-tools input[type=text]:focus { outline: none; border-color: var(--gold-dark); }
    .gacha-row { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
    .gacha-hint { font-size: 12px; color: var(--text-muted); line-height: 1.5; }

    .gacha-pool-tabs { display: flex; gap: 8px; margin-bottom: 12px; }
    .gacha-pool {
        padding: 6px 14px; background: var(--paimon-panel-light);
        border: 1px solid var(--paimon-border); border-radius: 20px;
        font-size: 12px; cursor: pointer; color: var(--text-muted);
    }
    .gacha-pool.active {
        border-color: var(--gold); color: var(--gold);
        background: rgba(212,175,55,.08);
    }

    .pity-row {
        display: flex; gap: 12px; align-items: center;
        background: var(--paimon-panel); padding: 16px; border-radius: 8px;
        margin-bottom: 16px; flex-wrap: wrap;
    }
    .pity-card {
        flex: 1; min-width: 140px; padding: 12px; text-align: center;
        background: var(--paimon-bg); border-radius: 6px;
    }
    .pity-num { font-size: 22px; font-weight: 700; color: var(--gold); }
    .pity-num.warning { color: var(--status-error); }   /* 抽到 70+ */
    .pity-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

    /* 五星记录：四列全部水平居中（对齐"表格 th/td 居中"规则） */
    .five-star-row {
        padding: 10px 12px; background: var(--paimon-panel); border-radius: 6px;
        margin-bottom: 6px;
        display: grid; grid-template-columns: 60px 1fr 120px 180px; gap: 12px;
        align-items: center; text-align: center;
    }
    .five-star-badge {
        color: #f4d03f; font-size: 14px; font-weight: 700;
    }
    .five-star-name { color: var(--text-primary); font-weight: 600; font-size: 13px; }
    .five-star-pity { font-family: monospace; font-size: 12px; color: var(--text-secondary); }
    .five-star-time { font-family: monospace; font-size: 11px; color: var(--text-muted); }
"""


GAME_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>🎮 水神 · 游戏</h1>
                <div class="sub">米哈游账号（原神 / 星铁 / 绝区零）· 签到 · 便笺 · 战报 · 抽卡</div>
            </div>
            <div>
                <button class="btn-action" onclick="gameRefresh()">刷新</button>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="gameSwitchTab('account',this)">账号</button>
            <button class="tab-btn" onclick="gameSwitchTab('note',this)">便笺</button>
            <button class="tab-btn" onclick="gameSwitchTab('abyss',this)">战报</button>
            <button class="tab-btn" onclick="gameSwitchTab('gacha',this);gameLoadGacha();">抽卡</button>
        </div>

        <div id="account" class="tab-panel active">
            <div class="bind-row">
                <div class="bind-card">
                    <h3>扫码绑定</h3>
                    <p>米游社 APP → 右上角扫一扫 → 确认登录。一次扫码绑定该账号下的全部游戏（原神/星铁/绝区零）。</p>
                    <div class="qr-box" id="qrBox">
                        <span style="color:#666">点下方按钮生成 QR</span>
                    </div>
                    <div class="qr-status" id="qrStatus">-</div>
                    <div style="text-align:center;margin-top:10px">
                        <button class="btn-action primary" onclick="startQrLogin()">生成二维码</button>
                    </div>
                </div>
                <div class="bind-card">
                    <h3>手动操作</h3>
                    <p>已绑定账号时可以手动触发：</p>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">
                        <button class="btn-action" onclick="gameSignAll()">全部签到</button>
                        <button class="btn-action" onclick="gameCollectAll()">抓便笺 + 深渊</button>
                    </div>
                    <p style="margin-top:12px"><span style="color:var(--text-muted);font-size:12px">系统每天 8:05 自动跑一次（树脂满时推送）</span></p>
                </div>
            </div>
            <div id="accountListEl"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="note" class="tab-panel">
            <div id="noteListEl"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="abyss" class="tab-panel">
            <div id="abyssListEl"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="gacha" class="tab-panel">
            <div class="gacha-tools">
                <div class="gacha-row">
                    <input type="text" id="gachaUrlInput" placeholder="粘贴原神内'祈愿历史'完整 URL（包含 authkey=...）" />
                    <button class="btn-action primary" onclick="gameImportGacha(this)">导入</button>
                </div>
                <div class="gacha-hint">
                    从米游社 APP → 工具 → 祈愿历史，或从游戏日志（<code>Genshin Impact/webCaches/*/Cache/Cache_Data/data_2</code>）抓到 URL 复制过来。authkey 约 24h 过期。
                </div>
            </div>

            <div class="gacha-pool-tabs">
                <span class="gacha-pool active" onclick="gameSelectPool('301',this)">角色活动</span>
                <span class="gacha-pool" onclick="gameSelectPool('302',this)">武器活动</span>
                <span class="gacha-pool" onclick="gameSelectPool('200',this)">常驻</span>
                <span class="gacha-pool" onclick="gameSelectPool('500',this)">集录</span>
            </div>

            <div id="gachaStatsEl"><div class="empty-state">导入抽卡记录后展示</div></div>
        </div>
    </div>
"""


GAME_SCRIPT = """
    <script>
    (function(){
        function esc(s){return s===null||s===undefined?'':String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
        function fmt(n, d){ if(n===null||n===undefined)return '-'; return Number(n).toFixed(d||2); }
        function fmtDate(ts){
            if(!ts||ts<=0)return '-';
            var d=new Date(ts*1000);
            return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')
                +' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
        }
        function fmtRelative(ts){
            if(!ts||ts<=0)return '-';
            var sec = (Date.now()/1000) - ts;
            if(sec < 60) return Math.floor(sec)+'s 前';
            if(sec < 3600) return Math.floor(sec/60)+'min 前';
            if(sec < 86400) return Math.floor(sec/3600)+'h 前';
            return Math.floor(sec/86400)+'d 前';
        }
        function fmtFutureHours(ts){
            if(!ts||ts<=0)return '已满';
            var sec = ts - (Date.now()/1000);
            if(sec <= 0) return '已满';
            var h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60);
            return h+'h'+String(m).padStart(2,'0')+'m 后满';
        }
        var _gameGameLabels = {gs:'原神', sr:'星铁', zzz:'绝区零'};
        var _currentPool = '301';

        window.gameSwitchTab = function(key, btn){
            document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
            document.getElementById(key).classList.add('active');
            btn.classList.add('active');
        };

        window.loadOverview = async function loadOverview(){
            var r = await fetch('/api/game/overview');
            var d = await r.json();
            var accs = d.accounts || [];
            _renderAccountList(accs);
            _renderNoteList(accs);
            _renderAbyssList(accs);
        }

        function _renderAccountList(accs){
            var el = document.getElementById('accountListEl');
            if(accs.length === 0){
                el.innerHTML = '<div class="empty-state">未绑定任何账号，请先扫码绑定。</div>';
                return;
            }
            var rows = accs.map(function(a){
                return '<tr>'
                    + '<td>'+(_gameGameLabels[a.game] || a.game)+'</td>'
                    + '<td class="code">'+esc(a.uid)+'</td>'
                    + '<td class="note">'+esc(a.note||'-')+'</td>'
                    + '<td class="code">'+esc(a.mys_id)+'</td>'
                    + '<td>'+esc(a.added_date)+'</td>'
                    + '<td>'+(a.last_sign_at>0 ? fmtRelative(a.last_sign_at) : '-')+'</td>'
                    + '<td>'+(a.has_cookie ? '✓' : '✗')+'</td>'
                    + '<td>'+(a.has_authkey ? (a.authkey_age_hours+'h 前') : '-')+'</td>'
                    + '<td class="actions">'
                    + '<button class="btn-action" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameSignOne(this)">签到</button>'
                    + '<button class="btn-action danger" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameUnbind(this)">解绑</button>'
                    + '</td>'
                    + '</tr>';
            }).join('');
            el.innerHTML = '<div class="game-table-wrap"><table class="game-table">'
                + '<thead><tr><th>游戏</th><th>UID</th><th>备注</th><th>MysID</th><th>添加日期</th>'
                + '<th>上次签到</th><th>Cookie</th><th>Authkey 新鲜度</th><th>操作</th></tr></thead>'
                + '<tbody>'+rows+'</tbody></table></div>';
        }

        // 三游戏字段标签映射（MihoyoNote 字段沿用原神命名，这里按 game 换显示文案）
        var _NOTE_LABELS = {
            gs:  {stamina:'原粹树脂', daily:'每日委托',   sub1:'周本减半剩余', sub2:'探索派遣', sub3:'参量质变仪'},
            sr:  {stamina:'开拓力',   daily:'每日实训',   sub1:'模拟宇宙周',   sub2:'委托派遣', sub3:null},
            zzz: {stamina:'电量',     daily:'每日活跃',   sub1:'悬赏已完成',   sub2:null,        sub3:null},
        };
        function _renderNoteList(accs){
            var el = document.getElementById('noteListEl');
            if(accs.length === 0){
                el.innerHTML = '<div class="empty-state">未绑定任何账号。</div>';
                return;
            }
            el.innerHTML = accs.map(function(a){
                var labels = _NOTE_LABELS[a.game] || _NOTE_LABELS.gs;
                var n = a.daily_note;
                var gameLabel = _gameGameLabels[a.game] || a.game;
                if(!n || n.max_resin <= 0){
                    return '<div class="note-card">'
                        + '<div class="note-head"><h3>'+esc(gameLabel)+' · '+esc(a.note||'')+'</h3><span class="uid">'+esc(a.uid)+'</span></div>'
                        + '<div class="empty-state">暂无便笺数据，点"抓便笺 + 深渊"手动同步</div>'
                        + '</div>';
                }
                var pct = Math.min(100, (n.current_resin/n.max_resin*100));
                var fullCls = pct >= 100 ? 'full' : '';
                // 原神独有：派遣倒计时
                var expHtml = '';
                if(a.game === 'gs'){
                    expHtml = (n.expeditions||[]).map(function(e){
                        var remain = parseInt(e.remained_time||0);
                        var ready = remain <= 0;
                        var label = ready ? '就绪' : (Math.floor(remain/3600)+'h'+String(Math.floor((remain%3600)/60)).padStart(2,'0')+'m');
                        return '<span class="exp-item '+(ready?'ready':'')+'">'+esc(label)+'</span>';
                    }).join('');
                }
                // mini 卡片：按 game 显示
                var minis = [];
                // 委托/实训/活跃
                var dailyReward = (a.game==='gs' && n.daily_reward) ? '（奖励已领）' :
                                  (a.game==='gs' && !n.daily_reward ? '（奖励未领）' : '');
                minis.push('<div class="note-mini"><div class="note-mini-num">'+n.finished_tasks+'/'+n.total_tasks+'</div><div class="note-mini-label">'+labels.daily+dailyReward+'</div></div>');
                if(labels.sub1){
                    minis.push('<div class="note-mini"><div class="note-mini-num">'+n.remain_discount+'</div><div class="note-mini-label">'+labels.sub1+'</div></div>');
                }
                if(labels.sub2 && (n.current_expedition>0 || n.max_expedition>0)){
                    minis.push('<div class="note-mini"><div class="note-mini-num">'+n.current_expedition+'/'+n.max_expedition+'</div><div class="note-mini-label">'+labels.sub2+'</div></div>');
                }
                if(labels.sub3){
                    minis.push('<div class="note-mini"><div class="note-mini-num">'+(n.transformer_ready?'✅':'—')+'</div><div class="note-mini-label">'+labels.sub3+'</div></div>');
                }
                return '<div class="note-card">'
                    + '<div class="note-head"><h3>'+esc(gameLabel)+' · '+esc(a.note||'')+'</h3><span class="uid">'+esc(a.uid)+' · '+fmtRelative(n.scan_ts)+'</span></div>'
                    + '<div class="resin-row">'
                    + '<span class="resin-label">'+labels.stamina+'</span>'
                    + '<div class="resin-bar"><div class="resin-fill '+fullCls+'" style="width:'+pct.toFixed(1)+'%"></div></div>'
                    + '<span class="resin-text">'+n.current_resin+' / '+n.max_resin+'</span>'
                    + '<span class="resin-text" style="font-size:11px;color:var(--text-muted)">'+fmtFutureHours(n.resin_full_ts)+'</span>'
                    + '</div>'
                    + '<div class="note-grid">'+minis.join('')+'</div>'
                    + (expHtml ? '<div class="expeditions"><h4>派遣倒计时</h4>'+expHtml+'</div>' : '')
                    + '</div>';
            }).join('');
        }

        // 副本定义（title / floor label / star label）按 abyss_type
        var _ABYSS_DEFS = {
            gs: [
                {type:'spiral',   title:'🌀 深境螺旋',       floorLabel:'最深抵达', starLabel:'总星数', starSuffix:'/36', showBattle:true},
                {type:'poetry',   title:'🎭 幻想真境剧诗',   floorLabel:'最高轮次', starLabel:'总梦藏', starSuffix:'',    showBattle:false},
                {type:'stygian',  title:'⚔️ 幽境危战',        floorLabel:'难度',     starLabel:'最快通关',starSuffix:'s',   showBattle:false},
            ],
            sr: [
                {type:'forgotten_hall', title:'🏛 忘却之庭',   floorLabel:'最高层', starLabel:'总星数', starSuffix:'', showBattle:true},
                {type:'pure_fiction',   title:'📖 虚构叙事',   floorLabel:'最高层', starLabel:'总星数', starSuffix:'', showBattle:true},
                {type:'apocalyptic',    title:'💀 末日幻影',   floorLabel:'最高层', starLabel:'总星数', starSuffix:'', showBattle:true},
            ],
            zzz: [
                // 式舆/第五防线指标是评级+得分（max_floor 存 rating 字母 S/A/B，total_star 存 score）
                {type:'shiyu', title:'🛡 式舆防卫战',        floorLabel:'评级',     starLabel:'得分',   starSuffix:'',   showBattle:false},
                {type:'mem',   title:'💥 危局强袭战',        floorLabel:'挑战数',   starLabel:'总星',   starSuffix:'',   showBattle:false},
            ],
        };

        async function _renderAbyssList(accs){
            var el = document.getElementById('abyssListEl');
            if(accs.length === 0){
                el.innerHTML = '<div class="empty-state">未绑定任何账号。</div>';
                return;
            }
            var parts = [];
            for(var a of accs){
                var defs = _ABYSS_DEFS[a.game] || [];
                if(defs.length === 0) continue;
                var gameLabel = _gameGameLabels[a.game] || a.game;
                // 并发拉该账号所有副本
                var results = await Promise.all(defs.map(function(def){
                    return fetch('/api/game/abyss_latest?game='+a.game+'&uid='+encodeURIComponent(a.uid)+'&type='+def.type)
                        .then(function(r){return r.json();})
                        .catch(function(){return {abyss:null};});
                }));
                for(var i = 0; i < defs.length; i++){
                    var def = defs[i];
                    var d = results[i];
                    var ab = d.abyss;
                    var columns = def.showBattle ? 3 : 2;
                    var stats = '';
                    if(ab){
                        stats = '<div class="abyss-stat"><div class="abyss-stat-num">'+esc(String(ab.max_floor||'-'))+'</div><div class="abyss-stat-label">'+def.floorLabel+'</div></div>'
                            +'<div class="abyss-stat"><div class="abyss-stat-num">'+ab.total_star+esc(def.starSuffix)+'</div><div class="abyss-stat-label">'+def.starLabel+'</div></div>';
                        if(def.showBattle){
                            stats += '<div class="abyss-stat"><div class="abyss-stat-num">'+ab.total_win+'/'+ab.total_battle+'</div><div class="abyss-stat-label">战斗胜率</div></div>';
                        }
                    }
                    parts.push('<div class="abyss-card">'
                        +'<div class="abyss-head"><span class="abyss-title">'+def.title+' · '+esc(gameLabel)+' · '+esc(a.note||a.uid)+'</span>'
                        +'<span class="abyss-period">'+(ab ? esc(String(ab.schedule_id||''))+' · '+fmtRelative(ab.scan_ts) : '暂无数据')+'</span></div>'
                        + (ab
                            ? '<div class="abyss-stats" style="grid-template-columns:repeat('+columns+',1fr)">'+stats+'</div>'
                            : '<div class="empty-state">暂无数据</div>')
                        +'</div>');
                }
            }
            el.innerHTML = parts.join('') || '<div class="empty-state">未绑定任何账号。</div>';
        }

        // ============ 账号操作 ============
        var _qrPollTimer = null;
        window.startQrLogin = async function(){
            clearInterval(_qrPollTimer);
            var box = document.getElementById('qrBox');
            var status = document.getElementById('qrStatus');
            box.innerHTML = '生成中...'; status.textContent = '请求米游社 QR...';
            var r = await fetch('/api/game/qr_create', {method:'POST'});
            var d = await r.json();
            if(!d.ok){ status.textContent='生成失败: '+(d.error||''); return; }
            // 用 QR 生成服务把 URL 转成图片（用 api.qrserver.com 免费接口）
            box.innerHTML = '<img src="https://api.qrserver.com/v1/create-qr-code/?size=240x240&data='+encodeURIComponent(d.url)+'">';
            status.textContent = '请用米游社 APP 扫码';
            // 开始轮询
            _qrPollTimer = setInterval(async function(){
                var rp = await fetch('/api/game/qr_poll?ticket='+encodeURIComponent(d.ticket)+'&device='+encodeURIComponent(d.device)+'&app_id='+d.app_id);
                var dp = await rp.json();
                if(dp.stat === 'Scanned'){ status.textContent = '已扫描，等待确认...'; }
                else if(dp.stat === 'Confirmed'){
                    clearInterval(_qrPollTimer);
                    status.textContent = '✅ 绑定成功：'+((dp.bound||[]).map(x=>_gameGameLabels[x.game]+'('+x.uid+')').join(', '));
                    box.innerHTML = '<span style="color:#4a5">✅</span>';
                    setTimeout(loadOverview, 500);
                }
                else if(dp.stat === 'Error'){
                    clearInterval(_qrPollTimer);
                    status.textContent = '失败: '+(dp.msg||'');
                }
            }, 2000);
        };

        window.gameUnbind = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            if(!confirm('解绑 '+uid+'？账号 + 便笺 + 深渊 + 抽卡记录都会清掉')) return;
            var r = await fetch('/api/game/unbind', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({game, uid}),
            });
            var d = await r.json();
            if(d.ok) loadOverview();
            else alert('失败: '+(d.error||''));
        };

        window.gameSignOne = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            var r = await fetch('/api/game/sign', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({game, uid}),
            });
            var d = await r.json();
            alert(d.ok ? ('签到成功: '+(d.msg||'')) : ('失败: '+(d.msg||'')));
            loadOverview();
        };

        window.gameSignAll = async function(){
            if(!confirm('给所有账号签到？')) return;
            var r = await fetch('/api/game/sign_all', {method:'POST'});
            var d = await r.json();
            alert('签到完成: '+(d.results||[]).length+' 个账号');
            loadOverview();
        };

        window.gameCollectAll = async function(){
            if(!confirm('抓所有启用账号的便笺 + 深渊（耗时 10~30s）')) return;
            await fetch('/api/game/collect_all', {method:'POST'});
            setTimeout(loadOverview, 2000);
            setTimeout(loadOverview, 10000);
        };

        window.gameRefresh = function(){ loadOverview(); };

        // ============ 抽卡 ============
        var _gachaUid = null;
        window.gameImportGacha = async function(btn){
            var url = document.getElementById('gachaUrlInput').value.trim();
            if(!url){ alert('请粘贴祈愿历史 URL'); return; }
            if(btn){ btn.disabled = true; btn.textContent = '导入中...'; }
            try{
                var r = await fetch('/api/game/gacha/import', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({url}),
                });
                var d = await r.json();
                if(!d.ok){ alert('导入失败: '+(d.msg||'')); return; }
                _gachaUid = d.uid;
                alert('导入成功 UID='+d.uid+' 各池新增: '+JSON.stringify(d.summary));
                gameLoadGacha();
            }finally{ if(btn){ btn.disabled = false; btn.textContent = '导入'; } }
        };

        window.gameSelectPool = function(pool, el){
            document.querySelectorAll('.gacha-pool').forEach(p=>p.classList.remove('active'));
            el.classList.add('active');
            _currentPool = pool;
            gameLoadGacha();
        };

        window.gameLoadGacha = async function(){
            var el = document.getElementById('gachaStatsEl');
            // uid 未定，先从 overview 选第一个原神账号
            if(!_gachaUid){
                var r = await fetch('/api/game/overview');
                var d = await r.json();
                var gs = (d.accounts||[]).find(a => a.game === 'gs' && a.has_authkey);
                if(!gs){
                    el.innerHTML = '<div class="empty-state">还没有抽卡数据，请先粘贴 URL 导入。</div>';
                    return;
                }
                _gachaUid = gs.uid;
            }
            var rs = await fetch('/api/game/gacha/stats?uid='+encodeURIComponent(_gachaUid)+'&gacha_type='+_currentPool);
            var ds = await rs.json();
            var s = ds.stats || {};
            if(!s.total){
                el.innerHTML = '<div class="empty-state">当前池暂无数据</div>';
                return;
            }
            var pity5Cls = s.pity_5 >= 70 ? 'warning' : '';
            var fives = (s.fives||[]).slice(0, 100);
            var fivesHtml = fives.length === 0
                ? '<div class="empty-state">还没有五星</div>'
                : fives.map(function(f, i){
                    // 小保底计数：相邻两个 5 星之间的抽数差（近似，详细要回头算）
                    return '<div class="five-star-row">'
                        + '<span class="five-star-badge">★5</span>'
                        + '<span class="five-star-name">'+esc(f.name)+'</span>'
                        + '<span class="five-star-pity">'+esc(f.item_type||'-')+'</span>'
                        + '<span class="five-star-time">'+esc(f.time||'-')+'</span>'
                        + '</div>';
                }).join('');

            el.innerHTML = '<div class="pity-row">'
                + '<div class="pity-card"><div class="pity-num">'+s.total+'</div><div class="pity-label">总抽数</div></div>'
                + '<div class="pity-card"><div class="pity-num '+pity5Cls+'">'+s.pity_5+'</div><div class="pity-label">5 星保底已抽</div></div>'
                + '<div class="pity-card"><div class="pity-num">'+s.pity_4+'</div><div class="pity-label">4 星保底已抽</div></div>'
                + '<div class="pity-card"><div class="pity-num">'+s.count_5+'</div><div class="pity-label">已出 5 星</div></div>'
                + '<div class="pity-card"><div class="pity-num">'+s.count_4+'</div><div class="pity-label">已出 4 星</div></div>'
                + '<div class="pity-card"><div class="pity-num">'+s.avg_pity_5+'</div><div class="pity-label">平均出金抽数</div></div>'
                + '</div>'
                + '<h3 style="color:var(--gold);font-size:14px;margin:16px 0 8px">5 星记录（新→旧）</h3>'
                + fivesHtml;
        };

        window.onload = loadOverview;
    })();
    </script>
"""


def build_game_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 游戏</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + GAME_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("game")
        + GAME_BODY
        + GAME_SCRIPT
        + """</body>
</html>"""
    )
