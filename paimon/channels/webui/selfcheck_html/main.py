"""三月·自检面板

# ---- 大 string const 切片 chunks（自动生成） ----

docs/foundation/march.md §自检体系
三档 UI：
  - 顶栏：[跑 Quick] [跑 Deep] 按钮 + 状态
  - Tab: Quick 历史 / Deep 历史
  - 点 Deep row → 详情 Modal：severity + findings 列表 + 下载
"""

from paimon.channels.webui.theme import (
    BASE_CSS,
    NAV_LINKS_CSS,
    NAVIGATION_CSS,
    THEME_COLORS,
    navigation_html,
)

# ---- chunks ----
from ._selfcheck_css import SELFCHECK_CSS
from ._selfcheck_script import SELFCHECK_SCRIPT


SELFCHECK_CSS = SELFCHECK_CSS

SELFCHECK_BODY = """
    <div class="container">
        <div class="page-header">
            <h1>🩺 自检</h1>
            <div class="header-actions">
                <span id="statusPill" class="status-pill">加载中...</span>
                <button id="btnQuick" class="btn">⚡ 跑 Quick</button>
                <button id="btnDeep" class="btn btn-primary">🔬 跑 Deep</button>
            </div>
        </div>

        <!-- 回退警示条：watchdog 自动回退过的话 / 需人工介入时显示 -->
        <div class="rollback-warning" id="rollbackWarning" style="display:none"></div>

        <!-- 自动升级区：检查远程 git 是否落后 + 一键 pull+重启（依赖 watchdog 脚本拉起） -->
        <div class="upgrade-bar" id="upgradeBar">
            <div class="upgrade-info">
                <span class="upgrade-label">📦 版本</span>
                <span id="upgradeHead">检查中...</span>
                <span id="upgradeBehind"></span>
            </div>
            <div class="upgrade-actions">
                <button id="btnUpgradeCheck" class="btn">🔄 检查更新</button>
                <button id="btnUpgradeApply" class="btn btn-primary" style="display:none">⬇️ 拉取并重启</button>
                <button id="btnRestart" class="btn">♻️ 重启</button>
            </div>
        </div>
        <div id="upgradeCommits" class="upgrade-commits" style="display:none"></div>

        <div class="tab-bar">
            <div class="tab active" data-tab="deep">Deep 历史</div>
            <div class="tab" data-tab="quick">Quick 历史</div>
        </div>

        <div id="tabPanel"><div class="empty-state">加载中...</div></div>
    </div>

    <div class="modal-mask" id="modal">
        <div class="modal">
            <div class="modal-head">
                <h3 id="modalTitle">详情</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modalBody"></div>
        </div>
    </div>
"""

SELFCHECK_SCRIPT = SELFCHECK_SCRIPT


def build_selfcheck_html(*, deep_hidden: bool = True) -> str:
    """生成面板 HTML。

    deep_hidden=True 时隐藏 Deep 按钮和 Deep Tab（底层 API 仍挂开关兜底），
    页面只保留 Quick 档位的运行和历史查看。
    docs/todo.md §三月·自检·Deep 暂缓
    """
    body = SELFCHECK_BODY
    script = SELFCHECK_SCRIPT
    if deep_hidden:
        # 隐藏"🔬 跑 Deep"按钮（其他元素保留，避免破坏 DOM 结构）
        body = body.replace(
            '<button id="btnDeep" class="btn btn-primary">🔬 跑 Deep</button>',
            '<button id="btnDeep" class="btn btn-primary" style="display:none">🔬 跑 Deep</button>',
        )
        # 隐藏 "Deep 历史" Tab；默认切到 "Quick 历史"
        body = body.replace(
            '<div class="tab active" data-tab="deep">Deep 历史</div>\n            <div class="tab" data-tab="quick">Quick 历史</div>',
            '<div class="tab active" data-tab="quick">Quick 历史</div>'
            '<div style="margin-left:auto;padding:10px 14px;color:var(--text-muted);font-size:12px" title="当前模型执行不充分，等切换 Claude Opus 级模型后启用">Deep 暂缓</div>',
        )
        # 初始 Tab 改成 quick（防御：JS 里已有 data-tab=quick 的选中逻辑）
        script = script.replace(
            "var currentTab='deep';",
            "var currentTab='quick';",
        ).replace(
            "loadRuns('deep');",
            "loadRuns('quick');",
        )
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon · 三月自检</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + SELFCHECK_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("selfcheck")
        + body
        + script
        + """</body>
</html>"""
    )
