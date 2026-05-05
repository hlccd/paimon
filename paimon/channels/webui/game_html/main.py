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

# ---- chunks ----
from ._game_css_1 import GAME_CSS_1
from ._game_css_2 import GAME_CSS_2
from ._game_script_1 import GAME_SCRIPT_1
from ._game_script_2 import GAME_SCRIPT_2
from ._game_script_3 import GAME_SCRIPT_3
from ._game_script_4 import GAME_SCRIPT_4



GAME_CSS = GAME_CSS_1 + GAME_CSS_2


GAME_BODY = """
    <div class="container">

        <div class="status-bar">
            <div class="status-title">
                <h1>🎮 游戏</h1>
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

    <!-- 抽卡 URL 导入 modal -->
    <div class="qr-modal-backdrop" id="urlImportModal" onclick="if(event.target.id==='urlImportModal')closeUrlImportModal()">
        <div class="urlimport-modal">
            <div class="qr-modal-head">
                <h3 id="urlImportTitle">导入抽卡 URL</h3>
                <button class="qr-close" onclick="closeUrlImportModal()">&times;</button>
            </div>
            <div class="tutorial" id="urlImportTutorial"></div>
            <textarea id="urlImportInput" placeholder="粘贴含 authkey=... 的完整 URL"></textarea>
            <div class="actions">
                <button class="btn tiny" onclick="closeUrlImportModal()">取消</button>
                <button class="btn primary tiny" onclick="submitUrlImport()">导入</button>
            </div>
        </div>
    </div>
"""


GAME_SCRIPT = GAME_SCRIPT_1 + GAME_SCRIPT_2 + GAME_SCRIPT_3 + GAME_SCRIPT_4


def build_game_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 游戏</title>
    <!-- 推送内容用 markdown 渲染（同主聊天面板） -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
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

# ---- 大 string const 切片 chunks（自动生成） ----

