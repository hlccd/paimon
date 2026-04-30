"""水神 · 游戏面板 — 玩家视角紧凑布局

设计哲学：
玩家日常最关心的就 3 件事 —— 树脂满没 / 委托做完没 / 今天签了没。
战报、抽卡是**偶尔**才翻的低频信息，不该和日常信息挤一起。

布局：
- 顶部状态条：绑定总数 + [+添加] + 刷新
- 每个账号一张**紧凑卡片**：只显示关键状态（一眼能判断是否要操作）
  - 树脂进度条（颜色随满额程度变）
  - 今日委托 / 派遣 / 签到状态（状态 chip）
  - 右上角：签到按钮（最常用）+ 展开按钮
- 点击"▾ 详情"展开：战报 + 抽卡（原神独占）+ 高级操作
- 扫码登录：modal 弹窗，不常驻
"""
from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)


GAME_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1100px; margin: 0 auto; padding: 24px; }

    /* ========= 顶部状态条 ========= */
    .status-bar {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 20px;
    }
    .status-title h1 { font-size: 22px; color: var(--text-primary); font-weight: 600; }
    .status-title .sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
    .status-actions { display: flex; gap: 8px; }

    /* ========= 按钮 ========= */
    .btn {
        padding: 7px 14px; font-size: 13px; border-radius: 6px;
        background: var(--paimon-panel); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); cursor: pointer;
        transition: border-color .15s, color .15s, background .15s;
    }
    .btn:hover { border-color: var(--gold-dark); color: var(--gold); }
    .btn.primary {
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        color: #000; border: none; font-weight: 600;
    }
    .btn.primary:hover { filter: brightness(1.08); }
    .btn.danger:hover { color: var(--status-error); border-color: var(--status-error); }
    .btn.tiny { padding: 4px 10px; font-size: 12px; }
    .btn:disabled { opacity: .5; cursor: not-allowed; }

    /* ========= 账号卡 ========= */
    .account-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 12px; margin-bottom: 14px; overflow: hidden;
        transition: border-color .2s;
    }
    .account-card:hover { border-color: var(--gold-dark); }

    /* ---- 紧凑摘要行 ---- */
    .ac-summary {
        display: grid;
        grid-template-columns: 200px 1fr auto;
        gap: 18px; align-items: center;
        padding: 14px 18px;
    }
    .ac-identity { display: flex; align-items: center; gap: 12px; min-width: 0; }
    /* 游戏 logo：汉字核心 + 官方主色渐变圆，不依赖外链图片 */
    .game-logo {
        display: inline-flex; align-items: center; justify-content: center;
        width: 36px; height: 36px; border-radius: 50%;
        font-size: 18px; font-weight: 700; color: #fff;
        font-family: "Noto Sans CJK SC", "Microsoft YaHei", serif;
        flex-shrink: 0; letter-spacing: 0;
        box-shadow: 0 2px 6px rgba(0,0,0,.35);
        text-shadow: 0 1px 2px rgba(0,0,0,.4);
    }
    .game-logo.gs  { background: linear-gradient(135deg, #d4af37 0%, #8b7530 100%); }  /* 原神金 */
    .game-logo.sr  { background: linear-gradient(135deg, #b084f0 0%, #5a3a8c 100%); }  /* 星穹紫 */
    .game-logo.zzz { background: linear-gradient(135deg, #f0d530 0%, #a08010 100%); color: #2a2000; }  /* 绝区零黄 */
    .ac-names { min-width: 0; }
    .ac-game-name {
        color: var(--gold); font-weight: 600; font-size: 14px;
        display: flex; align-items: baseline; gap: 6px;
    }
    .ac-note {
        color: var(--text-primary); font-weight: 500;
    }
    .ac-uid {
        font-family: monospace; color: var(--text-muted); font-size: 11px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }

    /* 中间状态区：树脂条 + 状态 chips */
    .ac-status { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
    .ac-resin-line {
        display: flex; align-items: center; gap: 10px;
    }
    .ac-resin-label {
        font-size: 11px; color: var(--text-muted);
        min-width: 40px; text-align: right;
    }
    .ac-resin-bar {
        flex: 1; height: 8px; background: var(--paimon-border);
        border-radius: 4px; overflow: hidden; position: relative;
        max-width: 260px;
    }
    .ac-resin-fill {
        height: 100%; border-radius: 4px; transition: width .3s;
        background: linear-gradient(90deg, #6ec6ff, #bb86fc);
    }
    .ac-resin-fill.warn  { background: linear-gradient(90deg, var(--gold), #f4c430); }
    .ac-resin-fill.full  { background: linear-gradient(90deg, var(--status-error), var(--gold)); }
    .ac-resin-num {
        font-family: monospace; font-size: 12px; color: var(--text-primary);
        min-width: 68px; text-align: right;
    }
    .ac-resin-when {
        font-size: 11px; color: var(--text-muted); min-width: 88px;
    }
    .ac-resin-when.urgent { color: var(--status-error); font-weight: 600; }

    .ac-chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
        padding: 2px 10px; border-radius: 12px;
        font-size: 11px; background: var(--paimon-bg);
        color: var(--text-secondary); white-space: nowrap;
    }
    .chip.ok   { color: var(--status-success); }
    .chip.warn { color: var(--gold); }
    .chip.bad  { color: var(--status-error); }

    /* 右侧操作 */
    .ac-ops { display: flex; gap: 6px; align-items: center; }
    .ac-toggle {
        background: transparent; border: 1px solid var(--paimon-border);
        color: var(--text-muted); cursor: pointer; padding: 6px 10px;
        border-radius: 6px; font-size: 12px; transition: color .15s, transform .15s;
    }
    .ac-toggle:hover { color: var(--gold); }
    .ac-toggle .arrow { display: inline-block; transition: transform .2s; margin-left: 2px; }
    .ac-toggle.open .arrow { transform: rotate(180deg); }

    /* ---- 展开详情区 ---- */
    .ac-detail {
        display: none;
        border-top: 1px solid var(--paimon-border);
        padding: 16px 18px;
        background: rgba(0,0,0,.15);
    }
    .ac-detail.open { display: block; }
    .detail-section { margin-bottom: 18px; }
    .detail-section:last-child { margin-bottom: 0; }
    .detail-title {
        font-size: 11px; color: var(--text-muted); text-transform: uppercase;
        letter-spacing: .6px; margin-bottom: 10px;
        display: flex; justify-content: space-between; align-items: center;
    }

    /* 战报表格 */
    .abyss-rows { }
    .abyss-row {
        display: grid; grid-template-columns: 140px 1fr 80px 100px;
        align-items: center; gap: 10px;
        padding: 7px 0; border-bottom: 1px dashed var(--paimon-border);
        font-size: 13px;
    }
    .abyss-row:last-child { border-bottom: none; }
    .abyss-name  { color: var(--text-secondary); }
    .abyss-floor { color: var(--text-primary); font-family: monospace; font-size: 12px; }
    .abyss-star  { color: var(--gold); text-align: right; font-family: monospace; font-weight: 600; }
    .abyss-meta  { color: var(--text-muted); text-align: right; font-size: 11px; }
    .abyss-empty { color: var(--text-muted); font-size: 12px; text-align: center; padding: 12px 0; }

    /* 派遣 chips（展开后完整列表） */
    .exp-detail { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
    .exp-chip {
        padding: 2px 8px; background: var(--paimon-bg); border-radius: 10px;
        font-size: 11px; color: var(--text-muted);
    }
    .exp-chip.ready { color: var(--status-success); border: 1px solid var(--status-success); }

    /* 抽卡 */
    .gacha-head {
        display: flex; gap: 4px; margin-bottom: 10px; flex-wrap: wrap;
    }
    .gpool {
        padding: 3px 10px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 10px;
        font-size: 11px; cursor: pointer; color: var(--text-muted);
    }
    .gpool.active { border-color: var(--gold); color: var(--gold); }
    .gacha-summary {
        font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;
        padding: 8px 12px; background: var(--paimon-bg); border-radius: 6px;
    }
    .gacha-summary .pity { color: var(--gold); font-weight: 600; font-family: monospace; }
    .gacha-summary .pity.warn { color: var(--status-error); }
    .gacha-summary .sep { color: var(--text-muted); margin: 0 8px; }
    .gacha-five-list { max-height: 220px; overflow-y: auto; }
    .gfive {
        display: grid; grid-template-columns: 30px 1fr 70px 100px;
        gap: 8px; align-items: center; padding: 5px 4px;
        font-size: 12px; border-bottom: 1px dashed var(--paimon-border);
    }
    .gfive:last-child { border-bottom: none; }
    .gfive-badge { color: #f4d03f; font-weight: 700; text-align: center; }
    .gfive-name  { color: var(--text-primary); }
    .gfive-type  { color: var(--text-muted); font-size: 11px; text-align: center; }
    .gfive-time  { color: var(--text-muted); font-family: monospace; font-size: 11px; text-align: right; }
    .gacha-url-row {
        display: flex; gap: 6px; margin-top: 10px;
    }
    .gacha-url-row input {
        flex: 1; padding: 6px 10px; background: var(--paimon-bg);
        color: var(--text-primary); border: 1px solid var(--paimon-border);
        border-radius: 4px; font-size: 11px; font-family: monospace;
    }
    .gacha-empty {
        color: var(--text-muted); font-size: 12px; text-align: center; padding: 16px 0;
    }

    /* 高级操作 */
    .detail-ops {
        display: flex; justify-content: flex-end; gap: 6px;
        padding-top: 12px; border-top: 1px dashed var(--paimon-border);
    }

    /* ========= 空状态（未绑定） ========= */
    .empty-bind {
        text-align: center; padding: 60px 20px;
        background: var(--paimon-panel); border: 1px dashed var(--paimon-border);
        border-radius: 12px;
    }
    .empty-bind h2 { font-size: 16px; color: var(--text-secondary); margin-bottom: 8px; font-weight: 500; }
    .empty-bind p  { font-size: 13px; color: var(--text-muted); margin-bottom: 18px; }

    /* ========= 扫码 modal ========= */
    .qr-modal-backdrop {
        display: none; position: fixed; inset: 0;
        background: rgba(0,0,0,.65); backdrop-filter: blur(4px);
        z-index: 1000; align-items: center; justify-content: center;
    }
    .qr-modal-backdrop.show { display: flex; }
    .qr-modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 12px; padding: 24px; max-width: 360px; width: 92%;
    }
    .qr-modal-head {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 14px;
    }
    .qr-modal-head h3 { color: var(--gold); font-size: 15px; }
    .qr-close {
        background: transparent; border: none; color: var(--text-muted);
        font-size: 22px; cursor: pointer; line-height: 1; padding: 0 6px;
    }
    .qr-close:hover { color: var(--status-error); }
    .qr-box {
        width: 240px; height: 240px; background: #fff; border-radius: 8px;
        margin: 0 auto; display: flex; align-items: center; justify-content: center;
    }
    .qr-box img { width: 100%; height: 100%; }
    .qr-hint { text-align: center; font-size: 12px; color: var(--text-secondary); margin-top: 12px; }
    .qr-hint.small { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
    .qr-status { text-align: center; font-size: 12px; color: var(--text-muted); margin-top: 8px; min-height: 16px; }

    /* ========= 响应式（窄屏） ========= */
    @media (max-width: 720px) {
        .ac-summary { grid-template-columns: 1fr; gap: 10px; }
        .ac-ops { justify-content: flex-end; }
    }

    /* ========= Tab 切换（总览 / 原神 / 崩铁 / 绝区零） ========= */
    .tabs-bar {
        display: flex; gap: 2px; margin-bottom: 18px;
        border-bottom: 1px solid var(--paimon-border);
    }
    .tab-btn {
        padding: 10px 18px; background: transparent; border: none;
        color: var(--text-muted); font-size: 14px; cursor: pointer;
        border-bottom: 2px solid transparent;
        transition: color .15s, border-color .15s;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active {
        color: var(--gold); border-bottom-color: var(--gold); font-weight: 500;
    }
    /* tab 里的小 logo 球（比 ac-icon 那个小一号） */
    .tab-logo {
        display: inline-flex; align-items: center; justify-content: center;
        width: 20px; height: 20px; border-radius: 50%; margin-right: 6px;
        font-size: 11px; font-weight: 700; color: #fff;
        vertical-align: -4px;
    }
    .tab-logo.gs  { background: linear-gradient(135deg, #d4af37, #8b7530); }
    .tab-logo.sr  { background: linear-gradient(135deg, #b084f0, #5a3a8c); }
    .tab-logo.zzz { background: linear-gradient(135deg, #f0d530, #a08010); color: #2a2000; }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }

    /* 单游戏 tab 内的"该游戏无账号"提示 */
    .tab-empty {
        text-align: center; padding: 40px 20px; color: var(--text-muted);
        background: var(--paimon-panel); border: 1px dashed var(--paimon-border);
        border-radius: 10px;
    }

    /* ========= 角色养成网格 ========= */
    .char-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
        gap: 10px;
    }
    .char-card {
        background: var(--paimon-bg); border: 1px solid var(--paimon-border);
        border-radius: 8px; padding: 10px; display: flex; gap: 10px; align-items: center;
        transition: border-color .15s;
    }
    .char-card:hover { border-color: var(--gold-dark); }
    .char-card.r5 { border-color: #c88a3a; background: linear-gradient(135deg, rgba(200,138,58,.08), var(--paimon-bg)); }
    .char-card.r4 { border-color: #8a5fc8; background: linear-gradient(135deg, rgba(138,95,200,.08), var(--paimon-bg)); }
    .char-icon {
        width: 44px; height: 44px; border-radius: 6px; flex-shrink: 0;
        background: var(--paimon-border) center/cover no-repeat;
    }
    .char-main { min-width: 0; flex: 1; }
    .char-name {
        font-size: 13px; font-weight: 600; color: var(--text-primary);
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .char-meta {
        font-size: 11px; color: var(--text-muted); margin-top: 2px;
        display: flex; gap: 6px; flex-wrap: wrap;
    }
    .char-lv { color: var(--gold); font-family: monospace; font-weight: 500; }
    .char-cons {
        display: inline-flex; gap: 2px;
    }
    .cons-dot {
        width: 6px; height: 6px; border-radius: 50%;
        background: var(--paimon-border);
    }
    .cons-dot.on { background: var(--gold); }
    .cons-dot.r5.on { background: #e5b255; }
    .char-filter-bar {
        display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap;
    }
    .char-filter {
        padding: 3px 10px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 10px;
        font-size: 11px; cursor: pointer; color: var(--text-muted);
    }
    .char-filter.active { border-color: var(--gold); color: var(--gold); }
    .char-stat-line {
        font-size: 11px; color: var(--text-muted); margin-bottom: 10px;
    }
    .char-stat-line .num { color: var(--gold); font-family: monospace; font-weight: 600; }

    /* 占位（用于尚未接入的 sr/zzz 角色 tab） */
    .coming-soon {
        padding: 24px; text-align: center; color: var(--text-muted);
        background: var(--paimon-bg); border-radius: 8px; font-size: 13px;
        border: 1px dashed var(--paimon-border);
    }
    .coming-soon .cs-title { color: var(--gold); font-size: 13px; margin-bottom: 6px; }
"""


GAME_BODY = """
    <div class="container">

        <div class="status-bar">
            <div class="status-title">
                <h1>🎮 水神 · 游戏</h1>
                <div class="sub" id="statusSub">加载中...</div>
            </div>
            <div class="status-actions">
                <button class="btn" onclick="openQrModal()">+ 添加账号</button>
                <button class="btn" onclick="gameRefreshAll()">刷新数据</button>
            </div>
        </div>

        <div id="wrapperEl"><div class="empty-bind">加载中...</div></div>
    </div>

    <!-- 扫码 modal -->
    <div class="qr-modal-backdrop" id="qrModal" onclick="if(event.target.id==='qrModal')closeQrModal()">
        <div class="qr-modal">
            <div class="qr-modal-head">
                <h3>扫码绑定米游社</h3>
                <button class="qr-close" onclick="closeQrModal()">&times;</button>
            </div>
            <div class="qr-box" id="qrBox">
                <button class="btn primary" onclick="startQrLogin()">生成二维码</button>
            </div>
            <div class="qr-hint">米游社 APP → 右上扫一扫 → 确认登录</div>
            <div class="qr-hint small">一次扫码绑该账号下原神 / 星铁 / 绝区零</div>
            <div class="qr-status" id="qrStatus"></div>
        </div>
    </div>
"""


GAME_SCRIPT = """
    <script>
    (function(){
        function esc(s){return s===null||s===undefined?'':String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}
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
            ],
            zzz: [
                {type:'shiyu', name:'式舆防卫战'},
                {type:'mem',   name:'危局强袭战'},
            ],
        };
        var POOL_LABELS = {'301':'角色','302':'武器','200':'常驻','500':'集录'};

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
            var n = a.daily_note;
            var parts = [];

            // 派遣完整（原神才有视觉价值）
            if(a.game === 'gs' && (n && (n.expeditions||[]).length)){
                var chips = n.expeditions.map(function(e){
                    var remain = parseInt(e.remained_time||0);
                    var ready = remain <= 0;
                    var label = ready ? '就绪' : (Math.floor(remain/3600)+'h'+String(Math.floor((remain%3600)/60)).padStart(2,'0')+'m');
                    return '<span class="exp-chip '+(ready?'ready':'')+'">'+esc(label)+'</span>';
                }).join('');
                parts.push('<div class="detail-section">'
                    + '<div class="detail-title">探索派遣</div>'
                    + '<div class="exp-detail">'+chips+'</div>'
                    + '</div>');
            }

            // 战报
            parts.push('<div class="detail-section">'
                + '<div class="detail-title">战报 · 最近</div>'
                + '<div class="abyss-rows" id="abyss-'+esc(k)+'">加载中...</div>'
                + '</div>');

            // 抽卡（仅原神）
            if(a.game === 'gs'){
                parts.push('<div class="detail-section">'
                    + '<div class="detail-title">抽卡记录</div>'
                    + '<div id="gacha-'+esc(k)+'">加载中...</div>'
                    + '</div>');
            }

            // 角色 / 养成（三游戏统一渲染，字段映射在后端 collect 时已归一到 MihoyoCharacter）
            parts.push('<div class="detail-section">'
                + '<div class="detail-title">'
                +   (a.game==='gs'?'角色 · 养成' : (a.game==='sr'?'角色 · 星魂':'代理人 · 影画'))
                + '</div>'
                + '<div id="chars-'+esc(k)+'">加载中...</div>'
                + '</div>');

            // 高级操作
            parts.push('<div class="detail-ops">'
                + '<button class="btn tiny" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameCollectOne(this)">刷新此账号数据</button>'
                + '<button class="btn tiny danger" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameUnbind(this)">解绑</button>'
                + '</div>');

            el.innerHTML = parts.join('');

            // 异步填战报 + 抽卡 + 角色
            _fillAbyss(a, k);
            if(a.game === 'gs') _fillGacha(a, k);
            _fillCharacters(a, k);
        }

        var _charFilter = {};   // uid -> 'all'|'r5'|'r4'

        async function _fillCharacters(a, k){
            var slot = document.getElementById('chars-'+k);
            if(!slot) return;
            var r = await fetch('/api/game/characters?game='+a.game+'&uid='+encodeURIComponent(a.uid));
            var d = await r.json();
            var chars = d.characters || [];
            if(chars.length === 0){
                slot.innerHTML = '<div class="coming-soon">'
                    + '  <div class="cs-title">暂无角色数据</div>'
                    + '  点右下角"刷新此账号数据"抓取，或等每日 8:05 cron'
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
            // 统计满级数
            var maxLv = chars.filter(function(c){return c.level >= 90;}).length;
            // avg fetter for 5 stars
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
                + '拥有 <span class="num">'+chars.length+'</span> 个角色 · '
                + '5 星 <span class="num">'+count5+'</span> · '
                + '满级（Lv.90）<span class="num">'+maxLv+'</span>'
                + '</div>';

            var cardsHtml = '<div class="char-grid">' + visible.map(function(c){
                var consDots = '';
                for(var i = 0; i < 6; i++){
                    consDots += '<span class="cons-dot'+(i < c.constellation ? ' on' : '')+(c.rarity>=5?' r5':'')+'"></span>';
                }
                var iconStyle = c.icon_url ? 'background-image:url('+esc(c.icon_url)+')' : '';
                var weaponBadge = (c.weapon && c.weapon.name)
                    ? '<span title="'+esc(c.weapon.name)+'">⚔Lv'+(c.weapon.level||0)+(c.weapon.affix?('·精'+c.weapon.affix):'')+'</span>'
                    : '';
                return '<div class="char-card r'+c.rarity+'">'
                    + '<div class="char-icon" style="'+iconStyle+'"></div>'
                    + '<div class="char-main">'
                    + '  <div class="char-name">'+esc(c.name)+'</div>'
                    + '  <div class="char-meta">'
                    + '    <span class="char-lv">Lv.'+c.level+'</span>'
                    + '    <span class="char-cons">'+consDots+'</span>'
                    + '  </div>'
                    + (weaponBadge ? '<div class="char-meta">'+weaponBadge+'</div>' : '')
                    + '</div>'
                    + '</div>';
            }).join('') + '</div>';

            slot.innerHTML = statHtml + filterHtml + cardsHtml;
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
            var results = await Promise.all(defs.map(function(def){
                return fetch('/api/game/abyss_latest?game='+a.game+'&uid='+encodeURIComponent(a.uid)+'&type='+def.type)
                    .then(function(r){return r.json();})
                    .catch(function(){return {abyss:null};});
            }));
            var rows = defs.map(function(def, i){
                var ab = results[i].abyss;
                if(!ab){
                    return '<div class="abyss-row">'
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
                return '<div class="abyss-row">'
                    + '<span class="abyss-name">'+esc(def.name)+'</span>'
                    + '<span class="abyss-floor">'+esc(floorVal)+'</span>'
                    + '<span class="abyss-star">'+esc(String(starVal))+'</span>'
                    + '<span class="abyss-meta">'+esc(String(metaVal))+'</span>'
                    + '</div>';
            });
            slot.innerHTML = rows.join('');
        }

        async function _fillGacha(a, k){
            var slot = document.getElementById('gacha-'+k);
            if(!slot) return;
            var pool = _currentPool[a.uid] || '301';
            var poolsHtml = '<div class="gacha-head">'
                + Object.keys(POOL_LABELS).map(function(p){
                    return '<span class="gpool '+(p===pool?'active':'')+'" onclick="gameSelectPool(\\''+esc(a.uid)+'\\',\\''+p+'\\')">'+POOL_LABELS[p]+'</span>';
                }).join('') + '</div>';

            var r = await fetch('/api/game/gacha/stats?uid='+encodeURIComponent(a.uid)+'&gacha_type='+pool);
            var d = await r.json();
            var s = d.stats || {total:0};
            if(!s.total){
                slot.innerHTML = poolsHtml
                    + '<div class="gacha-empty">暂无数据</div>'
                    + _gachaUrlInput();
                return;
            }
            var pityCls = s.pity_5 >= 70 ? 'warn' : '';
            var fives = (s.fives||[]).slice(0, 30);
            var fivesHtml = fives.length === 0
                ? '<div class="gacha-empty">此池暂无 5 星</div>'
                : fives.map(function(f){
                    return '<div class="gfive">'
                        + '<span class="gfive-badge">★5</span>'
                        + '<span class="gfive-name">'+esc(f.name)+'</span>'
                        + '<span class="gfive-type">'+esc(f.item_type||'-')+'</span>'
                        + '<span class="gfive-time">'+esc((f.time||'').slice(5,16))+'</span>'
                        + '</div>';
                }).join('');
            slot.innerHTML = poolsHtml
                + '<div class="gacha-summary">总抽 <span class="pity">'+s.total
                + '</span><span class="sep">·</span>保底 <span class="pity '+pityCls+'">'+s.pity_5
                + '</span><span class="sep">·</span>5 星 <span class="pity">'+s.count_5
                + '</span><span class="sep">·</span>平均 <span class="pity">'+s.avg_pity_5+'</span></div>'
                + '<div class="gacha-five-list">'+fivesHtml+'</div>'
                + _gachaUrlInput();
        }

        function _gachaUrlInput(){
            return '<div class="gacha-url-row">'
                + '<input type="text" placeholder="粘贴祈愿历史 URL 增量导入" />'
                + '<button class="btn tiny" onclick="gameImportGacha(this)">导入</button>'
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
                if(!d.ok && d.msg) alert('签到失败: '+d.msg);
                setTimeout(function(){ btn.textContent = old; btn.disabled = false; loadOverview(); }, 1200);
            }catch(e){
                btn.textContent='✗'; setTimeout(function(){btn.textContent=old;btn.disabled=false;},2000);
            }
        };

        window.gameCollectOne = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            btn.disabled = true; var old = btn.textContent; btn.textContent = '抓取中...';
            try{
                await fetch('/api/game/collect_one', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game, uid}),
                });
                setTimeout(loadOverview, 6000);
                setTimeout(loadOverview, 20000);
                btn.textContent = '已触发';
                setTimeout(function(){btn.textContent=old;btn.disabled=false;}, 3000);
            }catch(e){
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

        window.gameSelectPool = function(uid, pool){
            _currentPool[uid] = pool;
            var a = _allAccs.find(function(x){return x.uid === uid;});
            if(a) _fillGacha(a, keyOf(a));
        };

        window.gameImportGacha = async function(btn){
            var input = btn.parentElement.querySelector('input');
            if(!input){ alert('未找到输入框'); return; }
            var url = input.value.trim();
            if(!url){ alert('请粘贴 URL'); return; }
            btn.disabled = true; var old = btn.textContent; btn.textContent = '导入中...';
            try{
                var r = await fetch('/api/game/gacha/import', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({url}),
                });
                var d = await r.json();
                if(!d.ok){ alert('导入失败: '+(d.msg||'')); return; }
                input.value = '';
                alert('导入成功: '+JSON.stringify(d.summary));
                loadOverview();
            }finally{ btn.textContent = old; btn.disabled = false; }
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
