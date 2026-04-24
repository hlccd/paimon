from paimon.tools.builtin.dividend import DividendTool
from paimon.tools.builtin.exec import ExecTool
from paimon.tools.builtin.file_ops import FileOpsTool
from paimon.tools.builtin.glob_tool import GlobTool
from paimon.tools.builtin.knowledge import KnowledgeTool
from paimon.tools.builtin.memory_tool import MemoryTool
from paimon.tools.builtin.schedule import ScheduleTool
from paimon.tools.builtin.skill import UseSkillTool
from paimon.tools.builtin.skill_manage import SkillManageTool
from paimon.tools.builtin.subscribe import SubscribeTool
from paimon.tools.builtin.web_fetch import WebFetchTool

BUILTIN_TOOLS = [
    ExecTool(),
    UseSkillTool(),
    ScheduleTool(),
    SubscribeTool(),
    DividendTool(),
    KnowledgeTool(),
    MemoryTool(),
    FileOpsTool(),
    GlobTool(),
    WebFetchTool(),
    SkillManageTool(),
]
