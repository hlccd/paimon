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


KNOWLEDGE_CSS = """
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
    .tab-count {
        display: inline-block; min-width: 18px; padding: 0 6px; margin-left: 4px;
        font-size: 11px; line-height: 16px; border-radius: 8px;
        background: var(--paimon-panel-light); color: var(--text-muted); vertical-align: middle;
    }
    .tab-btn.active .tab-count { background: rgba(245,158,11,.2); color: var(--gold); }
    .tab-count:empty { display: none; }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    /* memory 二级 pill */
    .pills-row {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 16px; gap: 16px; flex-wrap: wrap;
    }
    .pills { display: flex; gap: 8px; flex: 1; flex-wrap: wrap; }
    .pill {
        padding: 6px 14px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 20px;
        cursor: pointer; font-size: 13px;
    }
    .pill:hover { color: var(--gold); }
    .pill.active { background: rgba(245,158,11,.15); color: var(--gold); border-color: var(--gold-dark); }

    /* + 新建按钮 */
    .btn-add {
        padding: 6px 14px; background: transparent; color: var(--gold);
        border: 1px solid var(--gold-dark); border-radius: 4px;
        cursor: pointer; font-size: 13px; font-weight: 500;
        transition: all .15s;
    }
    .btn-add:hover { background: rgba(245,158,11,.1); }

    /* 表单 modal */
    .modal-actions { display: flex; align-items: center; gap: 8px; }
    .form-body {
        padding: 8px 0; display: flex; flex-direction: column; gap: 14px;
    }
    .form-field { display: flex; flex-direction: column; gap: 4px; }
    .form-field label { font-size: 12px; color: var(--text-muted); }
    .form-field input[type="text"], .form-field textarea, .form-field select {
        padding: 8px 10px; background: var(--paimon-bg);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        color: var(--text-primary); font-size: 13px;
        font-family: inherit;
    }
    .form-field input[type="text"]:focus, .form-field textarea:focus, .form-field select:focus {
        outline: none; border-color: var(--gold);
    }
    .form-field input[disabled] { opacity: .6; cursor: not-allowed; }
    .form-field textarea {
        min-height: 160px; resize: vertical;
        font-family: 'SF Mono', Monaco, Consolas, monospace;
        line-height: 1.5;
    }
    .form-field .hint {
        font-size: 11px; color: var(--text-muted); font-style: italic;
    }
    .form-actions {
        display: flex; justify-content: flex-end; gap: 10px;
        margin-top: 16px; padding-top: 12px;
        border-top: 1px solid var(--paimon-border);
    }
    .btn-save {
        padding: 6px 18px; background: var(--gold); color: #000;
        border: none; border-radius: 4px; cursor: pointer;
        font-size: 13px; font-weight: 600;
    }
    .btn-save:hover { background: var(--gold-dark); }
    .btn-save:disabled { opacity: .5; cursor: not-allowed; }
    .form-error {
        margin-top: 10px; padding: 8px 12px;
        background: rgba(239,68,68,.08); border: 1px solid rgba(239,68,68,.3);
        border-radius: 4px; color: var(--status-error); font-size: 12px;
        display: none;
    }
    .form-error.active { display: block; }

    /* Flash toast（reconcile 结果 / 通用通知）*/
    .flash-bar {
        position: fixed; top: 70px; right: 24px;
        padding: 10px 14px; max-width: 420px;
        background: var(--paimon-panel);
        border: 1px solid var(--paimon-border);
        border-left-width: 3px;
        border-radius: 6px;
        color: var(--text-primary); font-size: 13px; line-height: 1.5;
        box-shadow: 0 4px 12px rgba(0,0,0,.35);
        z-index: 2000;
        opacity: 0; transform: translateX(20px);
        transition: opacity .2s, transform .2s;
        pointer-events: none;
    }
    .flash-bar.active { opacity: 1; transform: translateX(0); }
    .flash-bar.success { border-left-color: var(--status-success); }
    .flash-bar.info    { border-left-color: var(--gold); }
    .flash-bar.warn    { border-left-color: var(--status-warning); }
    .flash-bar .flash-title { font-weight: 600; margin-bottom: 4px; }
    .flash-bar .flash-reason { color: var(--text-muted); font-size: 12px; }

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

    /* 文书归档卡片 */
    .archive-card {
        margin-bottom: 12px; padding: 14px 18px;
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 8px;
    }
    .archive-header {
        display: flex; justify-content: space-between; align-items: baseline;
        margin-bottom: 10px;
    }
    .archive-title { font-size: 14px; font-weight: 500; color: var(--text-primary); }
    .archive-task-id { font-size: 11px; color: var(--text-muted); font-family: monospace; }
    .archive-artifacts { display: flex; flex-wrap: wrap; gap: 8px; }
    .archive-artifact {
        padding: 4px 10px; background: var(--paimon-panel-light);
        border: 1px solid var(--paimon-border); border-radius: 4px;
        cursor: pointer; font-size: 12px; color: var(--text-secondary);
        font-family: monospace;
    }
    .archive-artifact:hover { border-color: var(--gold); color: var(--gold); }
    .archive-artifact .count { color: var(--gold); margin-left: 4px; }

    /* 模态 */
    .modal-backdrop {
        display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 1000;
        align-items: center; justify-content: center;
    }
    .modal-backdrop.active { display: flex; }
    .modal {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 8px; max-width: 840px; width: 90%;
        max-height: 85vh; overflow: auto; padding: 24px;
    }
    .modal-header {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 16px; padding-bottom: 12px;
        border-bottom: 1px solid var(--paimon-border);
    }
    .modal-header h3 { color: var(--gold); font-size: 18px; font-weight: 600; }
    .modal-close {
        background: transparent; border: none; color: var(--text-muted); font-size: 22px;
        cursor: pointer; padding: 0 6px;
    }
    .modal-close:hover { color: var(--text-primary); }
    .modal-body {
        white-space: pre-wrap; font-size: 13px; line-height: 1.6;
        color: var(--text-primary); padding: 14px;
        background: var(--paimon-panel-light);
        border-radius: 6px; font-family: 'SF Mono', Monaco, Consolas, monospace;
        max-height: 60vh; overflow-y: auto;
    }
    .modal-meta { color: var(--text-muted); font-size: 12px; margin-top: 12px; line-height: 1.6; }
"""


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


KNOWLEDGE_SCRIPT = """
    <script>
    (function(){
        function esc(s){
            if(s==null) return '';
            return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
        }
        function fmtTime(ts){
            if(!ts||ts<=0) return '-';
            var d=new Date(ts*1000);
            var pad=function(n){return n.toString().padStart(2,'0');};
            return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())
                + ' '+pad(d.getHours())+':'+pad(d.getMinutes());
        }
        function fmtSize(n){
            if(!n) return '0';
            if(n<1024) return n+'B';
            if(n<1024*1024) return (n/1024).toFixed(1)+'KB';
            return (n/1024/1024).toFixed(1)+'MB';
        }

        // ---------- 公共 tab 切换 ----------
        window.switchTab = function(id, btn){
            document.querySelectorAll('.tab-btn').forEach(function(t){t.classList.remove('active');});
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            if(btn) btn.classList.add('active');
            var el=document.getElementById(id); if(el) el.classList.add('active');
            if(id==='kb' && !window._kbLoaded) loadKb();
            if(id==='archives' && !window._arcLoaded) loadArchives();
        };

        // ---------- 记忆 tab ----------
        var _memCache = {};  // mem_type -> { id: item }
        var _currentMemType = 'user';

        window.switchMemType = function(mem_type, el){
            _currentMemType = mem_type;
            document.querySelectorAll('.pill[data-mem]').forEach(function(p){p.classList.remove('active');});
            if(el) el.classList.add('active');
            loadMem(mem_type);
        };

        function emptyMemHint(type){
            var tips = {
                user:      '还没有用户画像。用 <code>/remember 我主要用 Go</code> 或让派蒙自动提取。',
                feedback:  '还没有行为规范。用 <code>/remember 不要给总结</code> 纠正派蒙回复风格。',
                project:   '还没有项目事实。项目级持久事实会被时执自动提取。',
                reference: '还没有外部资源指针。像"bugs 在 Linear INGEST 项目"这类会落到这里。',
            };
            return '<div class="empty-state">'+(tips[type]||'无数据')+'</div>';
        }

        function renderMemItems(type, items){
            var el = document.getElementById('memEl');
            if(!items || items.length === 0){
                el.innerHTML = emptyMemHint(type);
                _memCache[type] = {};
                return;
            }
            _memCache[type] = {};
            var rows = items.map(function(it){
                _memCache[type][it.id] = it;
                var tags = (it.tags || []).map(function(t){
                    return '<span class="chip">'+esc(t)+'</span>';
                }).join('');
                return ''
                    +'<tr data-id="'+esc(it.id)+'">'
                    +'<td><strong>'+esc(it.title)+'</strong>'
                        +'<div class="body-preview">'+esc(it.body_preview)+'</div>'
                        +(tags?'<div style="margin-top:6px">'+tags+'</div>':'')+'</td>'
                    +'<td class="mono">'+esc(it.subject||'default')+'</td>'
                    +'<td class="mono">'+fmtTime(it.updated_at)+'</td>'
                    +'<td class="desc">'+esc(it.source||'-')+'</td>'
                    +'<td>'
                        +'<button class="btn-view" data-action="view" data-id="'+esc(it.id)+'">查看</button>'
                        +'<button class="btn-revoke" data-action="delete" data-id="'+esc(it.id)+'">删除</button>'
                    +'</td>'
                    +'</tr>';
            }).join('');
            el.innerHTML = '<table class="data-table">'
                + '<thead><tr><th>记忆</th><th>主题</th><th>更新</th><th>来源</th><th>操作</th></tr></thead>'
                + '<tbody>'+rows+'</tbody></table>';
            el.querySelectorAll('button[data-action]').forEach(function(btn){
                btn.addEventListener('click', function(){
                    var act = btn.getAttribute('data-action');
                    var id = btn.getAttribute('data-id');
                    if(act==='view') viewMem(id);
                    else if(act==='delete') delMem(id);
                });
            });
        }

        window.viewMem = function(id){
            var it = _memCache[_currentMemType] && _memCache[_currentMemType][id];
            if(!it) return;
            // 记忆条目当前只读（走 /remember 或"+ 新建"写入）；不显示编辑按钮
            document.getElementById('modalEditBtn').style.display = 'none';
            _modalEditContext = null;
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

        window.delMem = async function(id){
            var it = _memCache[_currentMemType] && _memCache[_currentMemType][id];
            var title = it ? it.title : id;
            if(!confirm('确定删除记忆「'+title+'」?\\n此操作不可恢复，此记忆也将不再注入对话上下文。')) return;
            try{
                var r = await fetch('/api/knowledge/memory/delete', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({id: id}),
                });
                var d = await r.json();
                if(d.ok) loadMem(_currentMemType);
                else alert('删除失败: ' + (d.error || '未知错误'));
            }catch(e){ alert('删除失败: ' + e.message); }
        };

        async function loadMem(type){
            var el = document.getElementById('memEl');
            try{
                var r = await fetch('/api/knowledge/memory/list?mem_type='+encodeURIComponent(type));
                var d = await r.json();
                if(d.error){
                    el.innerHTML = '<div class="empty-state">加载失败: '+esc(d.error)+'</div>';
                    return;
                }
                renderMemItems(type, d.items || []);
                // 更新记忆总计数（拉一次 user+feedback+project+reference 的简单相加——首加载后值大致稳定）
                if(type === 'user') loadMemCount();
            }catch(e){
                el.innerHTML = '<div class="empty-state">加载失败: '+esc(e.message)+'</div>';
            }
        }

        async function loadMemCount(){
            try{
                var total = 0;
                for(var t of ['user','feedback','project','reference']){
                    var r = await fetch('/api/knowledge/memory/list?mem_type='+t);
                    var d = await r.json();
                    total += (d.items || []).length;
                }
                var el = document.getElementById('countMem');
                if(el) el.textContent = total ? total : '';
            }catch(e){}
        }

        // ---------- 记忆整理（批量 LLM 聚合/去重）----------
        var _hygienePollTimer = null;

        window.triggerHygiene = async function(){
            var btn = document.getElementById('btnHygiene');
            if(btn && btn.disabled) return;
            try{
                var r = await fetch('/api/knowledge/memory/hygiene', {method:'POST'});
                var d = await r.json();
                if(!d.ok){ flashToast('启动整理失败', d.error || '', 'warn'); return; }
                if(d.already_running){
                    flashToast('整理中，请稍候', '', 'info');
                }else{
                    flashToast('开始整理记忆…', 'LLM 扫全部记忆，批量合并/去重', 'info');
                }
                if(btn){ btn.disabled = true; btn.textContent = '🧹 整理中…'; }
                _pollHygieneStatus();
            }catch(e){
                flashToast('启动整理异常', String(e), 'warn');
            }
        };

        function _pollHygieneStatus(){
            if(_hygienePollTimer) clearTimeout(_hygienePollTimer);
            _hygienePollTimer = setTimeout(async function(){
                try{
                    var r = await fetch('/api/knowledge/memory/hygiene/status');
                    var d = await r.json();
                    if(d.running){
                        _pollHygieneStatus();   // 继续轮询
                        return;
                    }
                    // 跑完了
                    var btn = document.getElementById('btnHygiene');
                    if(btn){ btn.disabled = false; btn.textContent = '🧹 整理'; }
                    var rep = d.last_report || null;
                    if(rep){
                        var merged = rep.merged || 0;
                        var deleted = rep.deleted || 0;
                        if(merged || deleted){
                            flashToast(
                                '整理完成：合并 ' + merged + '、删除 ' + deleted,
                                '详情见「📨 推送」收件箱的「草神」条目',
                                'success',
                            );
                        }else{
                            flashToast('整理完成：记忆已经很干净了', '', 'success');
                        }
                    }else{
                        flashToast('整理完成', '', 'success');
                    }
                    // 刷新当前 pill
                    loadMem(_currentMemType);
                    loadMemCount();
                }catch(e){
                    var btn2 = document.getElementById('btnHygiene');
                    if(btn2){ btn2.disabled = false; btn2.textContent = '🧹 整理'; }
                    flashToast('整理状态查询失败', String(e), 'warn');
                }
            }, 3000);
        }

        // ---------- 新建/编辑表单 modal（记忆 + 知识库共享）----------
        // _currentForm.type: 'memory_remember' | 'kb_remember' | 'kb_edit'
        // （新建统一走 LLM 分类 + 冲突检测；编辑走已知 category/topic 改 body）
        var _currentForm = null;

        var _MEM_TYPE_LABELS = {
            user:      '画像与偏好 (user)',
            feedback:  '行为规范 (feedback)',
            project:   '项目事实 (project)',
            reference: '外部资源 (reference)',
        };

        function _showFormModal(title){
            _hideFormError();
            document.getElementById('formTitle').textContent = title;
            document.getElementById('formModal').classList.add('active');
        }
        window.closeFormModal = function(e){
            if(e && e.target.id !== 'formModal') return;
            document.getElementById('formModal').classList.remove('active');
            _currentForm = null;
        };
        function _showFormError(msg){
            var el = document.getElementById('formError');
            el.textContent = msg;
            el.classList.add('active');
        }
        function _hideFormError(){
            document.getElementById('formError').classList.remove('active');
        }

        // 记忆新建：单 textarea + 轻量引导
        window.openMemCreate = function(){
            _currentForm = {type: 'memory_remember'};
            document.getElementById('formBody').innerHTML = ''
                + '<div class="form-field">'
                +   '<label>说一句你想让我记住的事</label>'
                +   '<textarea id="fContent" placeholder="例：我主要用 Python / 不要给总结 / 项目 DB 是 PostgreSQL"></textarea>'
                +   '<div class="hint">会自动判类型和标题；跟已有冲突时自动合并</div>'
                + '</div>';
            _showFormModal('新建记忆');
            setTimeout(function(){ document.getElementById('fContent').focus(); }, 50);
        };

        // 知识库新建：同记忆对称（label + 示例 + 同样简短 hint）
        window.openKbCreate = function(){
            _currentForm = {type: 'kb_remember'};
            document.getElementById('formBody').innerHTML = ''
                + '<div class="form-field">'
                +   '<label>说一段你想记录的知识</label>'
                +   '<textarea id="fContent" placeholder="例：Claude API 每分钟限流 50 次 / asyncio 的 gather 用法"></textarea>'
                +   '<div class="hint">会自动判分类和主题；跟已有冲突时自动合并</div>'
                + '</div>';
            _showFormModal('新建知识');
            setTimeout(function(){ document.getElementById('fContent').focus(); }, 50);
        };

        // 知识库整理：按钮 + 轮询状态（跟记忆整理同样的交互）
        var _kbHygienePollTimer = null;
        window.triggerKbHygiene = async function(){
            var btn = document.getElementById('btnKbHygiene');
            if(btn && btn.disabled) return;
            try{
                var r = await fetch('/api/knowledge/kb/hygiene', {method:'POST'});
                var d = await r.json();
                if(!d.ok){ flashToast('启动整理失败', d.error || '', 'warn'); return; }
                if(d.already_running){
                    flashToast('整理中，请稍候', '', 'info');
                }else{
                    flashToast('开始整理知识库…', 'LLM 按分类扫全部知识，批量合并/去重', 'info');
                }
                if(btn){ btn.disabled = true; btn.textContent = '🧹 整理中…'; }
                _pollKbHygieneStatus();
            }catch(e){
                flashToast('启动整理异常', String(e), 'warn');
            }
        };
        function _pollKbHygieneStatus(){
            if(_kbHygienePollTimer) clearTimeout(_kbHygienePollTimer);
            _kbHygienePollTimer = setTimeout(async function(){
                try{
                    var r = await fetch('/api/knowledge/kb/hygiene/status');
                    var d = await r.json();
                    if(d.running){ _pollKbHygieneStatus(); return; }
                    var btn = document.getElementById('btnKbHygiene');
                    if(btn){ btn.disabled = false; btn.textContent = '🧹 整理'; }
                    var rep = d.last_report || null;
                    if(rep){
                        var merged = rep.merged || 0, deleted = rep.deleted || 0;
                        if(merged || deleted){
                            flashToast('整理完成：合并 ' + merged + '、删除 ' + deleted,
                                       '详情见「📨 推送」收件箱的「草神」条目', 'success');
                        }else{
                            flashToast('整理完成：知识库已经很干净了', '', 'success');
                        }
                    }else{
                        flashToast('整理完成', '', 'success');
                    }
                    window._kbLoaded = false; loadKb();
                }catch(e){
                    var btn2 = document.getElementById('btnKbHygiene');
                    if(btn2){ btn2.disabled = false; btn2.textContent = '🧹 整理'; }
                    flashToast('整理状态查询失败', String(e), 'warn');
                }
            }, 3000);
        }

        window.openKbEdit = function(category, topic, body){
            _currentForm = {type: 'kb_edit', category: category, topic: topic};
            var el = document.getElementById('formBody');
            el.innerHTML = ''
                + '<div class="form-field">'
                +   '<label>分类 category</label>'
                +   '<input type="text" id="fCategory" disabled value="'+esc(category)+'">'
                +   '<div class="hint">分类/主题作为主键不可改；如需改名请新建 + 删除旧条目</div>'
                + '</div>'
                + '<div class="form-field">'
                +   '<label>主题 topic</label>'
                +   '<input type="text" id="fTopic" disabled value="'+esc(topic)+'">'
                + '</div>'
                + '<div class="form-field">'
                +   '<label>内容</label>'
                +   '<textarea id="fBody"></textarea>'
                + '</div>';
            document.getElementById('fBody').value = body || '';
            _showFormModal('编辑知识 · ' + category + ' / ' + topic);
            setTimeout(function(){
                var bd = document.getElementById('fBody');
                bd.focus(); bd.setSelectionRange(bd.value.length, bd.value.length);
            }, 50);
        };

        // Flash toast —— 显示 reconcile action 结果等短消息
        var _flashTimer = null;
        function flashToast(title, reason, kind){
            kind = kind || 'info';
            var bar = document.getElementById('flashBar');
            if(!bar) return;
            bar.innerHTML = '<div class="flash-title">'+esc(title)+'</div>'
                + (reason ? '<div class="flash-reason">'+esc(reason)+'</div>' : '');
            bar.className = 'flash-bar active ' + kind;
            if(_flashTimer) clearTimeout(_flashTimer);
            _flashTimer = setTimeout(function(){
                bar.classList.remove('active');
            }, 4000);
        }

        // 防重入 flag：记忆 LLM 分类 1-5s，用户容易在等待期重复点击保存
        var _submitting = false;

        window.submitForm = async function(){
            if(_submitting) return;       // 已在提交中：忽略
            if(!_currentForm) return;
            _hideFormError();
            var f = _currentForm;
            var saveBtn = document.querySelector('#formModal .btn-save');
            var origLabel = saveBtn ? saveBtn.textContent : '保存';
            _submitting = true;
            if(saveBtn){ saveBtn.disabled = true; saveBtn.textContent = '保存中…'; }
            try{
                if(f.type === 'memory_remember'){
                    var content = document.getElementById('fContent').value.trim();
                    if(!content){ _showFormError('内容不能为空'); return; }
                    var r = await fetch('/api/knowledge/memory/remember', {
                        method: 'POST',
                        headers: {'Content-Type':'application/json'},
                        body: JSON.stringify({content: content}),
                    });
                    var d = await r.json();
                    if(!d.ok){ _showFormError('保存失败: ' + (d.error || '未知错误')); return; }
                    closeFormModal();
                    var action = d.action || 'new';
                    var title, kind = 'success';
                    if(action === 'new'){ title = '已记住：' + (d.title || ''); }
                    else if(action === 'merge'){ title = '已合并到原记忆「' + (d.target_title || '') + '」'; }
                    else if(action === 'replace'){ title = '已替换旧记忆「' + (d.target_title || '') + '」'; kind = 'warn'; }
                    else if(action === 'duplicate'){ title = '已存在相同记忆，未重复写入'; kind = 'info'; }
                    else{ title = '完成'; }
                    flashToast(title, d.reason || '', kind);
                    var new_type = d.mem_type || _currentMemType;
                    if(new_type !== _currentMemType){
                        var pillEl = document.querySelector('.pill[data-mem="'+new_type+'"]');
                        if(pillEl) switchMemType(new_type, pillEl);
                        else loadMem(new_type);
                    }else{ loadMem(new_type); }
                    loadMemCount();
                }else if(f.type === 'kb_remember'){
                    var content3 = document.getElementById('fContent').value.trim();
                    if(!content3){ _showFormError('内容不能为空'); return; }
                    var r3 = await fetch('/api/knowledge/kb/remember', {
                        method: 'POST',
                        headers: {'Content-Type':'application/json'},
                        body: JSON.stringify({content: content3}),
                    });
                    var d3 = await r3.json();
                    if(!d3.ok){ _showFormError('保存失败: ' + (d3.error || '未知错误')); return; }
                    closeFormModal();
                    var act = d3.action || 'new';
                    var title3, kind3 = 'success';
                    if(act === 'new'){ title3 = '已记入知识库：' + (d3.category||'') + ' / ' + (d3.topic||''); }
                    else if(act === 'merge'){ title3 = '已合并到原知识「' + (d3.target_topic||'') + '」'; }
                    else if(act === 'replace'){ title3 = '已替换旧知识「' + (d3.target_topic||'') + '」'; kind3 = 'warn'; }
                    else if(act === 'duplicate'){ title3 = '已存在相同知识「' + (d3.target_topic||'') + '」'; kind3 = 'info'; }
                    else{ title3 = '完成'; }
                    flashToast(title3, d3.reason || '', kind3);
                    window._kbLoaded = false; loadKb();
                }else if(f.type === 'kb_edit'){
                    // 编辑：已知 category/topic 改 body（走原 kb_write）
                    var cat = document.getElementById('fCategory').value.trim();
                    var topic = document.getElementById('fTopic').value.trim();
                    var body2 = document.getElementById('fBody').value;
                    if(!cat || !topic){ _showFormError('分类和主题不能为空'); return; }
                    if(!body2.trim()){ _showFormError('内容不能为空'); return; }
                    var r2 = await fetch('/api/knowledge/kb/write', {
                        method: 'POST',
                        headers: {'Content-Type':'application/json'},
                        body: JSON.stringify({category: cat, topic: topic, body: body2}),
                    });
                    var d2 = await r2.json();
                    if(!d2.ok){ _showFormError('保存失败: ' + (d2.error || '未知错误')); return; }
                    closeFormModal();
                    flashToast('已更新「' + cat + ' / ' + topic + '」', '', 'success');
                    window._kbLoaded = false; loadKb();
                }
            }catch(e){
                _showFormError('保存失败: ' + e.message);
            }finally{
                _submitting = false;
                if(saveBtn){
                    saveBtn.disabled = false;
                    saveBtn.textContent = origLabel;
                }
            }
        };

        // 详情 modal → 点"编辑"切换到表单 modal（仅知识库条目有此按钮）
        var _modalEditContext = null;  // {category, topic, body}
        window.modalStartEdit = function(){
            if(!_modalEditContext) return;
            var ctx = _modalEditContext;
            document.getElementById('modal').classList.remove('active');
            _modalEditContext = null;
            openKbEdit(ctx.category, ctx.topic, ctx.body);
        };

        // ---------- 知识库 tab ----------
        var _kbCache = {};  // key = "cat/topic" → {category, topic, body_preview, updated_at}

        async function loadKb(){
            var el = document.getElementById('kbEl');
            try{
                var r = await fetch('/api/knowledge/kb/list');
                var d = await r.json();
                var items = d.items || [];
                var cc = document.getElementById('countKb');
                if(cc) cc.textContent = items.length ? items.length : '';
                if(!items.length){
                    el.innerHTML = '<div class="empty-state">知识库为空。<br><br>让草神调 <code>knowledge</code> 工具写入，或在对话里说"帮我把 X 记到知识库 Y 分类下"</div>';
                    window._kbLoaded = true;
                    return;
                }
                _kbCache = {};
                var rows = items.map(function(it){
                    var key = it.category + '/' + it.topic;
                    _kbCache[key] = it;
                    return ''
                        +'<tr data-key="'+esc(key)+'">'
                        +'<td><strong>'+esc(it.topic)+'</strong>'
                            +'<div class="body-preview">'+esc(it.body_preview || '')+'</div></td>'
                        +'<td class="mono">'+esc(it.category)+'</td>'
                        +'<td class="mono">'+fmtTime(it.updated_at)+'</td>'
                        +'<td>'
                            +'<button class="btn-view" data-action="view" data-key="'+esc(key)+'">查看</button>'
                            +'<button class="btn-revoke" data-action="delete" data-key="'+esc(key)+'">删除</button>'
                        +'</td>'
                        +'</tr>';
                }).join('');
                el.innerHTML = '<table class="data-table">'
                    + '<thead><tr><th>知识</th><th>分类</th><th>更新</th><th>操作</th></tr></thead>'
                    + '<tbody>'+rows+'</tbody></table>';
                el.querySelectorAll('button[data-action]').forEach(function(btn){
                    btn.addEventListener('click', function(){
                        var act = btn.getAttribute('data-action');
                        var key = btn.getAttribute('data-key');
                        var it = _kbCache[key];
                        if(!it) return;
                        if(act==='view') openKb(it.category, it.topic);
                        else if(act==='delete') delKb(it.category, it.topic);
                    });
                });
                window._kbLoaded = true;
            }catch(e){
                el.innerHTML = '<div class="empty-state">加载失败: '+esc(e.message)+'</div>';
            }
        }

        window.delKb = async function(cat, topic){
            if(!confirm('确定删除知识「'+cat+' / '+topic+'」?\\n此操作不可恢复。')) return;
            try{
                var r = await fetch('/api/knowledge/kb/delete', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({category: cat, topic: topic}),
                });
                var d = await r.json();
                if(d.ok){
                    flashToast('已删除「' + cat + ' / ' + topic + '」', '', 'success');
                    window._kbLoaded = false; loadKb();
                }else{
                    alert('删除失败: ' + (d.error || '未知错误'));
                }
            }catch(e){ alert('删除失败: ' + e.message); }
        };

        window.openKb = async function(cat, topic){
            document.getElementById('modalTitle').textContent = cat + ' / ' + topic;
            document.getElementById('modalBody').textContent = '加载中...';
            document.getElementById('modalMeta').innerHTML =
                '分类: <span class="mono">'+esc(cat)+'</span> · '
                +'主题: <span class="mono">'+esc(topic)+'</span>';
            // 知识库条目支持编辑：显示"编辑"按钮 + 保存 body 供编辑时预填
            document.getElementById('modalEditBtn').style.display = '';
            _modalEditContext = {category: cat, topic: topic, body: ''};
            document.getElementById('modal').classList.add('active');
            try{
                var r = await fetch('/api/knowledge/kb/read?category='+encodeURIComponent(cat)+'&topic='+encodeURIComponent(topic));
                var d = await r.json();
                if(d.error){
                    document.getElementById('modalBody').textContent = '读取失败: ' + d.error;
                    return;
                }
                document.getElementById('modalBody').textContent = d.body || '(空)';
                if(_modalEditContext) _modalEditContext.body = d.body || '';
            }catch(e){
                document.getElementById('modalBody').textContent = '读取失败: ' + e.message;
            }
        };

        // ---------- 文书归档 tab ----------
        async function loadArchives(){
            var el = document.getElementById('archivesEl');
            try{
                var r = await fetch('/api/knowledge/archives/list');
                var d = await r.json();
                var items = d.items || [];
                var cc = document.getElementById('countArc');
                if(cc) cc.textContent = items.length ? items.length : '';
                if(!items.length){
                    el.innerHTML = '<div class="empty-state">暂无文书归档。<br><br>四影管线产出的 spec/design/code 产物会自动归档在这里；用 <code>/task &lt;需求&gt;</code> 触发一次复杂任务就能看到</div>';
                    window._arcLoaded = true;
                    return;
                }
                el.innerHTML = items.map(function(it){
                    var artifacts = it.artifacts.map(function(a){
                        var label = a.name;
                        if(a.file_count) label += ' <span class="count">('+a.file_count+')</span>';
                        else label += ' <span class="count">'+fmtSize(a.size)+'</span>';
                        return '<div class="archive-artifact" onclick="openArchive(\\''+esc(it.task_id)+'\\',\\''+esc(a.name)+'\\')">' + label + '</div>';
                    }).join('');
                    return '<div class="archive-card">'
                        + '<div class="archive-header">'
                        +   '<div class="archive-title">'+esc(it.title || '(未命名任务)')+'</div>'
                        +   '<div class="archive-task-id">'+esc(it.task_id)+' · '+fmtTime(it.created_at)+'</div>'
                        + '</div>'
                        + '<div class="archive-artifacts">'+artifacts+'</div>'
                        + '</div>';
                }).join('');
                window._arcLoaded = true;
            }catch(e){
                el.innerHTML = '<div class="empty-state">加载失败: '+esc(e.message)+'</div>';
            }
        }

        window.openArchive = async function(task_id, artifact){
            // code/ 目录没法展开看单文件，点击时给个提示
            if(artifact === 'code/'){
                document.getElementById('modalTitle').textContent = task_id + ' · code/';
                document.getElementById('modalBody').textContent = '此任务的 code/ 目录含多个文件，请用 /task-merge 命令合并到当前工作目录查看。';
                document.getElementById('modalMeta').innerHTML = '';
                document.getElementById('modal').classList.add('active');
                return;
            }
            document.getElementById('modalTitle').textContent = task_id + ' · ' + artifact;
            document.getElementById('modalBody').textContent = '加载中...';
            document.getElementById('modalMeta').innerHTML = '';
            document.getElementById('modal').classList.add('active');
            try{
                var r = await fetch('/api/knowledge/archives/read?task_id='+encodeURIComponent(task_id)+'&artifact='+encodeURIComponent(artifact));
                var d = await r.json();
                if(d.error){
                    document.getElementById('modalBody').textContent = '读取失败: ' + d.error;
                    return;
                }
                document.getElementById('modalBody').textContent = d.body || '(空)';
            }catch(e){
                document.getElementById('modalBody').textContent = '读取失败: ' + e.message;
            }
        };

        window.closeModal = function(e){
            if(e && e.target.id !== 'modal') return;
            document.getElementById('modal').classList.remove('active');
        };
        document.addEventListener('keydown', function(e){
            if(e.key === 'Escape'){
                var m = document.getElementById('modal');
                if(m && m.classList.contains('active')) m.classList.remove('active');
            }
        });

        window.refreshAll = function(){
            window._kbLoaded = false;
            window._arcLoaded = false;
            loadMem(_currentMemType);
            var active = document.querySelector('.tab-panel.active');
            if(!active) return;
            if(active.id==='kb') loadKb();
            else if(active.id==='archives') loadArchives();
        };

        window.onload = function(){ loadMem('user'); };
    })();
    </script>
"""


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
