from paimon.tools.builtin.exec import ExecTool
from paimon.tools.builtin.schedule import ScheduleTool
from paimon.tools.builtin.skill import UseSkillTool

BUILTIN_TOOLS = [
    ExecTool(),
    UseSkillTool(),
    ScheduleTool(),
]
