"""冰神 · 插件面板（含授权管理）

按 docs/permissions.md：
  - Skill 生态：展示全部 skill 的敏感度、allowed_tools、敏感命中项
  - 永久授权：查看 + 撤销用户永久授权记录
"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)


PLUGINS_CSS = """
    body { min-height: 100vh; }
    .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .page-header .sub { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
    .refresh-btn {
        padding: 8px 16px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .refresh-btn:hover { border-color: var(--gold-dark); color: var(--gold); }

    .tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid var(--paimon-border); }
    .tab-btn {
        padding: 10px 20px; background: transparent; border: none; color: var(--text-muted);
        cursor: pointer; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active { color: var(--gold); border-bottom-color: var(--gold); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    .data-table { width: 100%; border-collapse: collapse; }
    .data-table th, .data-table td {
        padding: 12px 16px; border-bottom: 1px solid var(--paimon-border);
        font-size: 14px; text-align: left; vertical-align: top;
    }
    .data-table th { color: var(--gold); font-weight: 600; font-size: 13px; }
    .data-table tbody tr:hover td { background: var(--paimon-panel); }

    .badge {
        display: inline-block; padding: 3px 8px; border-radius: 4px;
        font-size: 12px; font-weight: 500;
    }
    .badge-normal { background: rgba(110,198,255,.12); color: var(--star); }
    .badge-sensitive { background: rgba(245,158,11,.15); color: var(--status-warning); }
    .badge-allow { background: rgba(16,185,129,.15); color: var(--status-success); }
    .badge-deny { background: rgba(239,68,68,.15); color: var(--status-error); }

    .chip {
        display: inline-block; padding: 2px 8px; margin: 2px 4px 2px 0;
        border-radius: 10px; font-size: 12px;
        background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border);
    }
    .chip.sensitive { border-color: var(--status-warning); color: var(--status-warning); }

    .btn-revoke {
        padding: 4px 12px; background: transparent; border: 1px solid var(--status-error);
        color: var(--status-error); border-radius: 4px; cursor: pointer; font-size: 12px;
    }
    .btn-revoke:hover { background: rgba(239,68,68,.1); }

    .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 14px; }
    .desc { color: var(--text-muted); font-size: 12px; margin-top: 4px; line-height: 1.5; }
    .mono { font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 12px; color: var(--text-secondary); }
"""


PLUGINS_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>🔌 插件</h1>
                <div class="sub">Skill 生态管理 + 用户授权</div>
            </div>
            <button class="refresh-btn" onclick="refreshAll()">刷新</button>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('skills',this)">Skill 生态</button>
            <button class="tab-btn" onclick="switchTab('authz',this)">永久授权</button>
        </div>

        <div id="skills" class="tab-panel active">
            <div id="skillsEl"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="authz" class="tab-panel">
            <div id="authzEl"><div class="empty-state">加载中...</div></div>
        </div>
    </div>
"""


PLUGINS_SCRIPT = """
    <script>
    (function(){
        function esc(s){return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}
        function fmtTime(ts){
            if(!ts||ts<=0)return'-';
            var d=new Date(ts*1000);
            return (d.getFullYear())+'-'+(d.getMonth()+1).toString().padStart(2,'0')+'-'+
                d.getDate().toString().padStart(2,'0')+' '+
                d.getHours().toString().padStart(2,'0')+':'+
                d.getMinutes().toString().padStart(2,'0');
        }

        window.switchTab = function(id, btn){
            document.querySelectorAll('.tab-btn').forEach(function(t){t.classList.remove('active');});
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            if(btn) btn.classList.add('active');
            var el = document.getElementById(id);
            if(el) el.classList.add('active');
        };

        function renderSkills(data){
            var el = document.getElementById('skillsEl');
            var skills = data.skills || [];
            if(skills.length === 0){
                el.innerHTML = '<div class="empty-state">尚未加载任何 Skill</div>';
                return;
            }
            var rows = skills.map(function(s){
                var senBadge = s.sensitivity === 'sensitive'
                    ? '<span class="badge badge-sensitive">敏感</span>'
                    : '<span class="badge badge-normal">普通</span>';
                var tools = (s.allowed_tools || []).map(function(t){
                    var isSen = (s.sensitive_tools || []).indexOf(t) !== -1;
                    return '<span class="chip'+(isSen?' sensitive':'')+'">'+esc(t)+'</span>';
                }).join('');
                if(!tools) tools = '<span class="desc">（未声明）</span>';
                var authzBadge = '';
                if(s.authz === 'permanent_allow'){
                    authzBadge = '<span class="badge badge-allow">已永久放行</span>';
                } else if(s.authz === 'permanent_deny'){
                    authzBadge = '<span class="badge badge-deny">已永久禁止</span>';
                }
                return ''
                    +'<tr>'
                    +'<td><strong>'+esc(s.name)+'</strong>'
                        +'<div class="desc">'+esc(s.description || '')+'</div></td>'
                    +'<td>'+senBadge+' '+authzBadge+'</td>'
                    +'<td>'+tools+'</td>'
                    +'</tr>';
            }).join('');
            el.innerHTML = ''
                +'<table class="data-table">'
                +'<thead><tr>'
                +'<th>Skill</th><th>敏感度 / 授权</th><th>工具</th>'
                +'</tr></thead>'
                +'<tbody>'+rows+'</tbody>'
                +'</table>';
        }

        function renderAuthz(data){
            var el = document.getElementById('authzEl');
            var records = data.records || [];
            if(records.length === 0){
                el.innerHTML = '<div class="empty-state">暂无永久授权记录<br><span class="desc">当敏感 skill 被询问且用户选择「永久放行/禁止」时，记录会出现在这里</span></div>';
                return;
            }
            var rows = records.map(function(r){
                var decBadge = r.decision === 'permanent_allow'
                    ? '<span class="badge badge-allow">永久放行</span>'
                    : '<span class="badge badge-deny">永久禁止</span>';
                return ''
                    +'<tr data-type="'+esc(r.subject_type)+'" data-id="'+esc(r.subject_id)+'">'
                    +'<td><span class="mono">'+esc(r.subject_type)+'</span> · <strong>'+esc(r.subject_id)+'</strong></td>'
                    +'<td>'+decBadge+'</td>'
                    +'<td class="mono">'+fmtTime(r.updated_at)+'</td>'
                    +'<td class="desc">'+esc(r.reason || '-')+'</td>'
                    +'<td><button class="btn-revoke" onclick="revoke(\\''+esc(r.subject_type)+'\\',\\''+esc(r.subject_id)+'\\')">撤销</button></td>'
                    +'</tr>';
            }).join('');
            el.innerHTML = ''
                +'<table class="data-table">'
                +'<thead><tr>'
                +'<th>主体</th><th>决策</th><th>更新时间</th><th>原因</th><th>操作</th>'
                +'</tr></thead>'
                +'<tbody>'+rows+'</tbody>'
                +'</table>';
        }

        window.revoke = async function(subject_type, subject_id){
            if(!confirm('撤销 '+subject_type+'/'+subject_id+' 的永久授权？\\n下次调用时会重新询问。')) return;
            try {
                var resp = await fetch('/api/plugins/authz/revoke', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({subject_type: subject_type, subject_id: subject_id}),
                });
                var data = await resp.json();
                if(data.ok){
                    loadAuthz();
                    loadSkills();
                } else {
                    alert('撤销失败: ' + (data.error || '未知错误'));
                }
            } catch(e){
                alert('撤销失败: ' + e.message);
            }
        };

        async function loadSkills(){
            try {
                var r = await fetch('/api/plugins/skills');
                var d = await r.json();
                renderSkills(d);
            } catch(e){
                document.getElementById('skillsEl').innerHTML =
                    '<div class="empty-state">加载失败: '+esc(e.message)+'</div>';
            }
        }

        async function loadAuthz(){
            try {
                var r = await fetch('/api/plugins/authz');
                var d = await r.json();
                renderAuthz(d);
            } catch(e){
                document.getElementById('authzEl').innerHTML =
                    '<div class="empty-state">加载失败: '+esc(e.message)+'</div>';
            }
        }

        window.refreshAll = function(){
            loadSkills();
            loadAuthz();
        };

        window.onload = function(){ refreshAll(); };
    })();
    </script>
"""


def build_plugins_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>插件</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + PLUGINS_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("plugins")
        + PLUGINS_BODY
        + PLUGINS_SCRIPT
        + """</body>
</html>"""
    )
