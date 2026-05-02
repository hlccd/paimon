"""KNOWLEDGE_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

KNOWLEDGE_SCRIPT_2 = """                }
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
