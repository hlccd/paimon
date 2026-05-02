"""草神 · 世界树面板（/knowledge）

三大 tab（草神职责范围内的世界树数据可视化入口）：
  📖 记忆 —— L1 memory 域，4 类 pill 切换；支持新建 + 删除
  📚 知识库 —— knowledge 域（category/topic 结构化条目）；支持新建 + 编辑 + 删除
  📄 文书归档 —— 四影任务 workspace 产物（只读，由四影管线产出）

其他世界树域（授权 / skill / 任务 / 理财 / 订阅 / 自检 / token）归相应神的专属面板管。
"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)

# ---- chunks ----
from ._knowledge_css import KNOWLEDGE_CSS
from ._knowledge_script_1 import KNOWLEDGE_SCRIPT_1
from ._knowledge_script_2 import KNOWLEDGE_SCRIPT_2



KNOWLEDGE_CSS = KNOWLEDGE_CSS


KNOWLEDGE_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>草神 · 世界树</h1>
                <div class="sub">跨会话记忆 · 结构化知识库 · 四影文书产物归档</div>
            </div>
            <button class="refresh-btn" onclick="refreshAll()">刷新</button>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('memory',this)">📖 记忆 <span class="tab-count" id="countMem"></span></button>
            <button class="tab-btn" onclick="switchTab('kb',this)">📚 知识库 <span class="tab-count" id="countKb"></span></button>
            <button class="tab-btn" onclick="switchTab('archives',this)">📄 文书归档 <span class="tab-count" id="countArc"></span></button>
        </div>

        <div id="memory" class="tab-panel active">
            <div class="pills-row">
                <div class="pills">
                    <div class="pill active" data-mem="user" onclick="switchMemType('user',this)">画像与偏好</div>
                    <div class="pill" data-mem="feedback" onclick="switchMemType('feedback',this)">行为规范</div>
                    <div class="pill" data-mem="project" onclick="switchMemType('project',this)">项目事实</div>
                    <div class="pill" data-mem="reference" onclick="switchMemType('reference',this)">外部资源</div>
                </div>
                <div style="display:flex;gap:8px">
                    <button class="btn-add" onclick="triggerHygiene()" id="btnHygiene" title="LLM 扫全部记忆，批量合并/去重。周一凌晨也会自动跑。">🧹 整理</button>
                    <button class="btn-add" onclick="openMemCreate()">+ 新建</button>
                </div>
            </div>
            <div id="memEl"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="kb" class="tab-panel">
            <div class="pills-row">
                <div class="pills"></div>
                <div style="display:flex;gap:8px">
                    <button class="btn-add" onclick="triggerKbHygiene()" id="btnKbHygiene" title="LLM 按分类扫知识库，批量合并/去重。周一凌晨也会自动跑。">🧹 整理</button>
                    <button class="btn-add" onclick="openKbCreate()">+ 新建</button>
                </div>
            </div>
            <div id="kbEl"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="archives" class="tab-panel">
            <div id="archivesEl"><div class="empty-state">加载中...</div></div>
        </div>
    </div>

    <!-- 详情 modal（查看全文用，只读） -->
    <div id="modal" class="modal-backdrop" onclick="closeModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal-header">
                <h3 id="modalTitle">详情</h3>
                <div class="modal-actions">
                    <button id="modalEditBtn" class="btn-view" style="display:none" onclick="modalStartEdit()">编辑</button>
                    <button class="modal-close" onclick="closeModal()">×</button>
                </div>
            </div>
            <div class="modal-body" id="modalBody"></div>
            <div class="modal-meta" id="modalMeta"></div>
        </div>
    </div>

    <!-- Flash toast -->
    <div id="flashBar" class="flash-bar"></div>

    <!-- 表单 modal（新建/编辑用） -->
    <div id="formModal" class="modal-backdrop" onclick="closeFormModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal-header">
                <h3 id="formTitle">新建</h3>
                <button class="modal-close" onclick="closeFormModal()">×</button>
            </div>
            <div id="formBody" class="form-body"></div>
            <div class="form-actions">
                <button class="btn-revoke" onclick="closeFormModal()">取消</button>
                <button class="btn-save" onclick="submitForm()">保存</button>
            </div>
            <div id="formError" class="form-error"></div>
        </div>
    </div>
"""


KNOWLEDGE_SCRIPT = KNOWLEDGE_SCRIPT_1 + KNOWLEDGE_SCRIPT_2


def build_knowledge_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 草神·世界树</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + KNOWLEDGE_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("knowledge")
        + KNOWLEDGE_BODY
        + KNOWLEDGE_SCRIPT
        + """</body>
</html>"""
    )

# ---- 大 string const 切片 chunks（自动生成） ----

