"""草神 · 偏好面板（L1 记忆管理）

按 docs/todo.md 草神增强 (2) "知识/偏好面板"：
  - 画像与偏好 (user)：列表 + 查看全文 + 删除
  - 行为规范 (feedback)：列表 + 查看全文 + 删除

MVP 不做编辑 / 改 type / 手动新增（/remember 已覆盖新增）；
project / reference 类不暴露在 UI（用户关注度低）。
"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)


PREFERENCES_CSS = """
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

    .chip {
        display: inline-block; padding: 2px 8px; margin: 2px 4px 2px 0;
        border-radius: 10px; font-size: 12px;
        background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border);
    }

    .btn-revoke {
        padding: 4px 12px; background: transparent; border: 1px solid var(--status-error);
        color: var(--status-error); border-radius: 4px; cursor: pointer; font-size: 12px;
    }
    .btn-revoke:hover { background: rgba(239,68,68,.1); }
    .btn-view {
        padding: 4px 12px; background: transparent; border: 1px solid var(--gold-dark);
        color: var(--gold); border-radius: 4px; cursor: pointer; font-size: 12px; margin-right: 4px;
    }
    .btn-view:hover { background: rgba(245,158,11,.1); }

    .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 14px; }
    .empty-state code { background: var(--paimon-panel-light); padding: 2px 6px; border-radius: 4px;
        font-family: 'SF Mono', Monaco, Consolas, monospace; color: var(--gold); }
    .desc { color: var(--text-muted); font-size: 12px; margin-top: 4px; line-height: 1.5; }
    .body-preview {
        font-size: 13px; color: var(--text-secondary); line-height: 1.5;
        max-width: 500px; word-break: break-word;
    }
    .mono { font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 12px; color: var(--text-secondary); }

    /* 模态弹窗 */
    .modal-backdrop {
        display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1000;
        align-items: center; justify-content: center;
    }
    .modal-backdrop.active { display: flex; }
    .modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border); border-radius: 8px;
        max-width: 720px; width: 90%; max-height: 80vh; overflow: auto; padding: 24px;
    }
    .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .modal-header h3 { color: var(--gold); font-size: 18px; font-weight: 600; }
    .modal-close {
        background: transparent; border: none; color: var(--text-muted); font-size: 20px;
        cursor: pointer; padding: 0 4px;
    }
    .modal-close:hover { color: var(--text-primary); }
    .modal-body {
        white-space: pre-wrap; font-size: 14px; line-height: 1.6;
        color: var(--text-primary); padding: 12px; background: var(--paimon-panel-light);
        border-radius: 4px;
    }
    .modal-meta { color: var(--text-muted); font-size: 12px; margin-top: 12px; line-height: 1.6; }
"""


PREFERENCES_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>草神 · 偏好面板</h1>
                <div class="sub">跨会话记忆管理 · 这些内容会自动注入每次对话的系统提示</div>
            </div>
            <button class="refresh-btn" onclick="refreshAll()">刷新</button>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('user',this)">画像与偏好</button>
            <button class="tab-btn" onclick="switchTab('feedback',this)">行为规范</button>
        </div>

        <div id="user" class="tab-panel active">
            <div id="userEl"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="feedback" class="tab-panel">
            <div id="feedbackEl"><div class="empty-state">加载中...</div></div>
        </div>
    </div>

    <div id="modal" class="modal-backdrop" onclick="closeModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal-header">
                <h3 id="modalTitle">记忆详情</h3>
                <button class="modal-close" onclick="closeModal()">×</button>
            </div>
            <div class="modal-body" id="modalBody"></div>
            <div class="modal-meta" id="modalMeta"></div>
        </div>
    </div>
"""


PREFERENCES_SCRIPT = """
    <script>
    (function(){
        // 完整 HTML 转义（包括引号）—— 修复 P1 XSS：
        // 原 esc() 仅处理 &<>，不转义 "'，攻击者可用 title='"><script>...' 闭合属性注入。
        function esc(s){
            if(!s) return '';
            return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
        }
        function fmtTime(ts){
            if(!ts||ts<=0)return'-';
            var d=new Date(ts*1000);
            return (d.getFullYear())+'-'+(d.getMonth()+1).toString().padStart(2,'0')+'-'+
                d.getDate().toString().padStart(2,'0')+' '+
                d.getHours().toString().padStart(2,'0')+':'+
                d.getMinutes().toString().padStart(2,'0');
        }

        // 缓存每个 tab 已加载的 items，供"查看全文"弹窗快速取 body
        var cache = { user: {}, feedback: {} };

        window.switchTab = function(id, btn){
            document.querySelectorAll('.tab-btn').forEach(function(t){t.classList.remove('active');});
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            if(btn) btn.classList.add('active');
            var el = document.getElementById(id);
            if(el) el.classList.add('active');
        };

        function emptyHint(type){
            var hint = (type === 'user')
                ? '还没有用户画像。用 <code>/remember 我主要用 Go</code> 记录偏好，或在长对话里让派蒙自动提取。'
                : '还没有行为规范。用 <code>/remember 不要给总结</code> 纠正派蒙的回复风格。';
            return '<div class="empty-state">'+hint+'</div>';
        }

        function renderItems(type, items){
            var el = document.getElementById(type + 'El');
            if(!items || items.length === 0){
                el.innerHTML = emptyHint(type);
                cache[type] = {};
                return;
            }
            cache[type] = {};
            var rows = items.map(function(it){
                cache[type][it.id] = it;
                var tags = (it.tags || []).map(function(t){
                    return '<span class="chip">'+esc(t)+'</span>';
                }).join('');
                // 不用 inline onclick 传 title —— 避免单/双引号闭合属性导致 XSS。
                // 用 data-* 属性 + 统一事件委托（下面在 el 上 addEventListener）
                return ''
                    +'<tr data-id="'+esc(it.id)+'">'
                    +'<td><strong>'+esc(it.title)+'</strong>'
                        +'<div class="body-preview">'+esc(it.body_preview)+'</div>'
                        +(tags?'<div style="margin-top:6px">'+tags+'</div>':'')+'</td>'
                    +'<td class="mono">'+esc(it.subject||'default')+'</td>'
                    +'<td class="mono">'+fmtTime(it.updated_at)+'</td>'
                    +'<td class="desc">'+esc(it.source||'-')+'</td>'
                    +'<td>'
                        +'<button class="btn-view" data-action="view" data-type="'+esc(type)+'" data-id="'+esc(it.id)+'">查看全文</button>'
                        +'<button class="btn-revoke" data-action="delete" data-type="'+esc(type)+'" data-id="'+esc(it.id)+'">删除</button>'
                    +'</td>'
                    +'</tr>';
            }).join('');
            el.innerHTML = ''
                +'<table class="data-table">'
                +'<thead><tr>'
                +'<th>记忆</th><th>主题</th><th>更新时间</th><th>来源</th><th>操作</th>'
                +'</tr></thead>'
                +'<tbody>'+rows+'</tbody>'
                +'</table>';

            // 事件委托：点击表格内 button 按 data-action 分派
            el.querySelectorAll('button[data-action]').forEach(function(btn){
                btn.addEventListener('click', function(){
                    var action = btn.getAttribute('data-action');
                    var btype = btn.getAttribute('data-type');
                    var bid = btn.getAttribute('data-id');
                    if(action === 'view'){
                        viewMem(btype, bid);
                    } else if(action === 'delete'){
                        delMem(btype, bid);
                    }
                });
            });
        }

        window.viewMem = function(type, id){
            var it = cache[type][id];
            if(!it) return;
            document.getElementById('modalTitle').textContent = it.title;
            document.getElementById('modalBody').textContent = it.body || '(空)';
            document.getElementById('modalMeta').innerHTML =
                '类型: <span class="mono">'+esc(it.mem_type)+'</span> · '
                +'主题: <span class="mono">'+esc(it.subject)+'</span><br>'
                +'来源: '+esc(it.source || '-')+'<br>'
                +'标签: '+((it.tags||[]).map(esc).join(', ') || '-')+'<br>'
                +'创建: '+fmtTime(it.created_at)+' · 更新: '+fmtTime(it.updated_at)+'<br>'
                +'ID: <span class="mono">'+esc(it.id)+'</span>';
            document.getElementById('modal').classList.add('active');
        };

        window.closeModal = function(e){
            if(e && e.target.id !== 'modal') return;
            document.getElementById('modal').classList.remove('active');
        };

        window.delMem = async function(type, id){
            var it = cache[type] && cache[type][id];
            // title 仅用于 confirm() 文案；confirm 是纯文本弹窗不会渲染 HTML，但还是用 esc 后的
            var title = it ? it.title : id;
            if(!confirm('确定删除记忆「'+title+'」?\\n此操作不可恢复，此记忆也将不再注入对话上下文。')) return;
            try {
                var resp = await fetch('/api/preferences/delete', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({id: id}),
                });
                var data = await resp.json();
                if(data.ok){
                    loadTab(type);
                } else {
                    alert('删除失败: ' + (data.error || '未知错误'));
                }
            } catch(e){
                alert('删除失败: ' + e.message);
            }
        };

        async function loadTab(type){
            try {
                var r = await fetch('/api/preferences/list?mem_type=' + encodeURIComponent(type));
                var d = await r.json();
                if(d.error){
                    document.getElementById(type+'El').innerHTML =
                        '<div class="empty-state">加载失败: '+esc(d.error)+'</div>';
                    return;
                }
                renderItems(type, d.items || []);
            } catch(e){
                document.getElementById(type+'El').innerHTML =
                    '<div class="empty-state">加载失败: '+esc(e.message)+'</div>';
            }
        }

        window.refreshAll = function(){
            loadTab('user');
            loadTab('feedback');
        };

        // ESC 关闭模态
        document.addEventListener('keydown', function(e){
            if(e.key === 'Escape'){
                var m = document.getElementById('modal');
                if(m && m.classList.contains('active')){
                    m.classList.remove('active');
                }
            }
        });

        window.onload = function(){ refreshAll(); };
    })();
    </script>
"""


def build_preferences_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 偏好面板</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + PREFERENCES_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("preferences")
        + PREFERENCES_BODY
        + PREFERENCES_SCRIPT
        + """</body>
</html>"""
    )
