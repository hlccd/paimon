"""KNOWLEDGE_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

KNOWLEDGE_SCRIPT_1 = """
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
                    saveBtn.textContent = origLabel;"""
