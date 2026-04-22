"""三月 · 任务观测面板"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)

TASKS_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .refresh-btn {
        padding: 8px 16px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .refresh-btn:hover { border-color: var(--gold-dark); color: var(--gold); }

    .task-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }
    .task-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 20px; transition: border-color .2s;
    }
    .task-card:hover { border-color: var(--gold-dark); }
    .task-card.disabled { opacity: .6; }

    .task-header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px; }
    .task-id { font-size: 12px; color: var(--text-muted); font-family: monospace; }
    .task-badge {
        padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 500;
    }
    .badge-enabled { background: rgba(16,185,129,.15); color: var(--status-success); }
    .badge-disabled { background: rgba(239,68,68,.15); color: var(--status-error); }

    .task-prompt {
        font-size: 14px; color: var(--text-primary); margin-bottom: 12px;
        line-height: 1.5; word-break: break-word;
        max-height: 60px; overflow: hidden; text-overflow: ellipsis;
    }

    .task-meta { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: var(--text-muted); }
    .task-meta-item {
        background: var(--paimon-panel-light); padding: 4px 8px; border-radius: 4px;
    }
    .task-error {
        margin-top: 8px; padding: 8px; border-radius: 6px;
        background: rgba(239,68,68,.1); border: 1px solid rgba(239,68,68,.2);
        font-size: 12px; color: var(--status-error);
    }

    .empty-state { text-align: center; padding: 80px 20px; color: var(--text-muted); font-size: 14px; }
    .empty-icon { font-size: 48px; margin-bottom: 16px; opacity: .5; }
"""

TASKS_BODY = """
    <div class="container">
        <div class="page-header">
            <h1>任务观测</h1>
            <button class="refresh-btn" onclick="loadTasks()">刷新</button>
        </div>
        <div id="taskGrid"><div class="empty-state">加载中...</div></div>
    </div>
"""

TASKS_SCRIPT = """
    <script>
    (function(){
        function esc(s){return s?s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}
        function fmtTime(ts){
            if(!ts||ts<=0)return'-';
            var d=new Date(ts*1000);
            return (d.getMonth()+1)+'-'+d.getDate()+' '+d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0');
        }
        function fmtTrigger(t){
            if(t.trigger_type==='once')return '一次性';
            if(t.trigger_type==='interval'){
                var s=t.trigger_value&&t.trigger_value.seconds||0;
                if(s>=3600)return '每'+Math.round(s/3600)+'小时';
                if(s>=60)return '每'+Math.round(s/60)+'分钟';
                return '每'+s+'秒';
            }
            if(t.trigger_type==='cron')return 'cron: '+(t.trigger_value&&t.trigger_value.expr||'?');
            return t.trigger_type;
        }

        window.loadTasks=async function(){
            var el=document.getElementById('taskGrid');
            try{
                var r=await fetch('/api/tasks');
                var data=await r.json();
                var tasks=data.tasks||[];
                if(!tasks.length){
                    el.innerHTML='<div class="empty-state"><div class="empty-icon">&#128337;</div>暂无定时任务<br><br>在对话中说"每小时提醒我喝水"或使用 /tasks 命令查看</div>';
                    return;
                }
                el.innerHTML=tasks.map(function(t){
                    var cls='task-card'+(t.enabled?'':' disabled');
                    var badge=t.enabled?'<span class="task-badge badge-enabled">运行中</span>':'<span class="task-badge badge-disabled">已停止</span>';
                    var err=t.last_error?'<div class="task-error">'+esc(t.last_error.substring(0,100))+(t.consecutive_failures?' (连续'+t.consecutive_failures+'次)':'')+'</div>':'';
                    return '<div class="'+cls+'">'
                        +'<div class="task-header"><span class="task-id">'+esc(t.id)+'</span>'+badge+'</div>'
                        +'<div class="task-prompt">'+esc(t.prompt)+'</div>'
                        +'<div class="task-meta">'
                        +'<span class="task-meta-item">'+fmtTrigger(t)+'</span>'
                        +'<span class="task-meta-item">下次: '+fmtTime(t.next_run_at)+'</span>'
                        +'<span class="task-meta-item">上次: '+fmtTime(t.last_run_at)+'</span>'
                        +'<span class="task-meta-item">创建: '+fmtTime(t.created_at)+'</span>'
                        +'</div>'
                        +err
                        +'</div>';
                }).join('');
            }catch(e){
                el.innerHTML='<div class="empty-state">加载失败</div>';
            }
        };
        window.onload=function(){loadTasks();};
        setInterval(loadTasks,30000);
    })();
    </script>
"""


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
