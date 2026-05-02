"""三月 · 任务观测面板（三 tab：定时任务 / 系统任务 / 深度任务）

# ---- 大 string const 切片 chunks（自动生成） ----

- 定时任务：用户主动创建的 cron/interval/once（task_type='user'）
- 系统任务：archon 注册的内部周期任务（方案 D，task_type != 'user'），
  如风神订阅采集 / 岩神红利股扫描
- 深度任务：四影管线复杂任务（原 "四影任务"，2026-04-29 更名为 "深度任务"）

docs/interaction.md §四 WebUI。
"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)

# ---- chunks ----
from ._tasks_css import TASKS_CSS
from ._tasks_script import TASKS_SCRIPT


TASKS_CSS = TASKS_CSS

TASKS_BODY = """
    <div class="container">
        <div class="page-header">
            <h1>任务观测</h1>
            <button class="refresh-btn" onclick="refreshAll()">刷新</button>
        </div>
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('scheduled',this)">定时任务 <span class="tab-count" id="countScheduled"></span></button>
            <button class="tab-btn" onclick="switchTab('system',this)">系统任务 <span class="tab-count" id="countSystem"></span></button>
            <button class="tab-btn" onclick="switchTab('complex',this)">深度任务 <span class="tab-count" id="countComplex"></span></button>
        </div>
        <div id="scheduled" class="tab-panel active">
            <div id="taskGrid"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="system" class="tab-panel">
            <div id="systemGrid"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="complex" class="tab-panel">
            <div id="complexGrid"><div class="empty-state">点击查看深度任务</div></div>
        </div>
    </div>

    <div id="taskModal" class="modal-mask" onclick="if(event.target===this)closeModal()">
        <div class="modal-card">
            <button class="modal-close" onclick="closeModal()">&times;</button>
            <div id="modalBody">加载中...</div>
        </div>
    </div>
"""

TASKS_SCRIPT = TASKS_SCRIPT


def build_tasks_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 任务观测</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + TASKS_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("tasks")
        + TASKS_BODY
        + TASKS_SCRIPT
        + """</body>
</html>"""
    )
