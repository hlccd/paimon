"""LLM_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

LLM_SCRIPT_1 = """
    <script>
    (function(){
        function esc(s){
            if(s===null||s===undefined) return '';
            return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                .replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
        }
        function fmtTime(ts){
            if(!ts||ts<=0)return'-';
            var d=new Date(ts*1000);
            return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+
                String(d.getDate()).padStart(2,'0')+' '+
                String(d.getHours()).padStart(2,'0')+':'+
                String(d.getMinutes()).padStart(2,'0');
        }
        function relTime(ts){
            if(!ts||ts<=0) return '-';
            var sec = Math.max(0, Math.floor(Date.now()/1000 - ts));
            if(sec < 5) return '刚刚';
            if(sec < 60) return sec+'秒前';
            if(sec < 3600) return Math.floor(sec/60)+'分钟前';
            if(sec < 86400) return Math.floor(sec/3600)+'小时前';
            return Math.floor(sec/86400)+'天前';
        }

        var currentProfiles = [];

        var PROVIDER_DISPLAY = {
            anthropic: 'Anthropic',
            openai: 'OpenAI / DeepSeek / 兼容',
        };

        function shortHost(url){
            if(!url) return '-';
            try { return new URL(url).host || url; }
            catch(e){ return url; }
        }

        function renderProfileCard(p){
            var thinking = !!(p.extra_body && p.extra_body.thinking && p.extra_body.thinking.type === 'enabled');
            var badges = '';
            if(thinking) badges += ' <span class="badge badge-thinking">thinking</span>';
            if(p.reasoning_effort) badges += ' <span class="badge">effort='+esc(p.reasoning_effort)+'</span>';

            return '<div class="profile-card'+(p.is_default?' is-default':'')+'">'
                + '<div class="profile-info">'
                +   '<div class="name">'
                +     (p.is_default?'<span class="star">✰</span>':'')
                +     '<span>'+esc(p.name)+'</span>'
                +     badges
                +   '</div>'
                +   '<div class="meta">'
                +     '<span class="mono">'+esc(p.model)+'</span>'
                +     '<span title="'+esc(p.base_url || '')+'">'+esc(shortHost(p.base_url))+'</span>'
                +   '</div>'
                +   (p.notes?'<div class="notes">'+esc(p.notes)+'</div>':'')
                +   '<div id="test-'+esc(p.id)+'"></div>'
                + '</div>'
                + '<div class="profile-actions">'
                +   '<button class="btn-action" onclick="testExisting(\\''+esc(p.id)+'\\',this)">测连接</button>'
                +   '<button class="btn-action" onclick="openEdit(\\''+esc(p.id)+'\\')">编辑</button>'
                +   (p.is_default ? '' : '<button class="btn-action success" onclick="setDefault(\\''+esc(p.id)+'\\')">设默认</button>')
                +   (p.is_default ? '' : '<button class="btn-action danger" onclick="delProfile(\\''+esc(p.id)+'\\')">删除</button>')
                + '</div>'
                + '</div>';
        }

        function renderProviderSection(kind, list){
            // 默认 profile 在前；其余按 name 字典序
            list.sort(function(a, b){
                if(a.is_default !== b.is_default) return a.is_default ? -1 : 1;
                return (a.name || '').localeCompare(b.name || '');
            });
            var displayName = PROVIDER_DISPLAY[kind] || kind;
            var bodyHtml = list.map(renderProfileCard).join('');
            return '<div class="provider-section">'
                + '<div class="provider-header" onclick="toggleProvider(this)">'
                +   '<span class="provider-arrow">▼</span>'
                +   '<span class="provider-name">'+esc(displayName)+'</span>'
                +   '<span class="provider-stat">'+list.length+' 个 profile</span>'
                + '</div>'
                + '<div class="provider-body">'+bodyHtml+'</div>'
                + '</div>';
        }

        window.toggleProvider = function(el){ el.parentElement.classList.toggle('collapsed'); };

        async function loadProfiles(){
            var el = document.getElementById('profileList');
            try {
                var r = await fetch('/api/llm/list');
                var d = await r.json();
                var list = d.profiles || [];
                currentProfiles = list;
                if(!list.length){
                    el.innerHTML = '<div class="empty-state">暂无 profile。点上方「+ 新增 Profile」添加第一条。</div>';
                    return;
                }
                // 按 provider_kind 桶
                var byKind = {};
                list.forEach(function(p){
                    var k = p.provider_kind || 'openai';
                    if(!byKind[k]) byKind[k] = [];
                    byKind[k].push(p);
                });
                // 排序：anthropic 在前；未知 kind 排最后
                var order = ['anthropic', 'openai'];
                Object.keys(byKind).forEach(function(k){
                    if(order.indexOf(k) === -1) order.push(k);
                });
                el.innerHTML = order.filter(function(k){return byKind[k];}).map(function(k){
                    return renderProviderSection(k, byKind[k]);
                }).join('');
            } catch(e){
                el.innerHTML = '<div class="empty-state">加载失败: '+esc(String(e))+'</div>';
            }
        }

        function resetForm(){
            document.getElementById('fld_id').value = '';
            document.getElementById('fld_name').value = '';
            document.getElementById('fld_provider_kind').value = 'openai';
            document.getElementById('fld_model').value = '';
            document.getElementById('fld_base_url').value = '';
            document.getElementById('fld_api_key').value = '';
            document.getElementById('fld_max_tokens').value = '64000';
            document.getElementById('fld_reasoning_effort').value = '';
            document.getElementById('fld_extra_body').value = '';
            document.getElementById('fld_notes').value = '';
            var tr = document.getElementById('testResult');
            tr.style.display = 'none'; tr.textContent = ''; tr.className = 'test-result';
        }

        window.openCreate = function(){
            resetForm();
            document.getElementById('modalTitle').textContent = '新增 Profile';
            document.getElementById('modal').classList.add('active');
        };

        window.openEdit = function(id){
            var p = currentProfiles.find(function(x){return x.id === id;});
            if(!p) return;
            resetForm();
            document.getElementById('fld_id').value = p.id;
            document.getElementById('fld_name').value = p.name || '';
            document.getElementById('fld_provider_kind').value = p.provider_kind || 'openai';
            document.getElementById('fld_model').value = p.model || '';
            document.getElementById('fld_base_url').value = p.base_url || '';
            document.getElementById('fld_api_key').value = p.api_key || '';  // 通常是 ***
            document.getElementById('fld_max_tokens').value = p.max_tokens || 64000;
            document.getElementById('fld_reasoning_effort').value = p.reasoning_effort || '';
            var eb = (p.extra_body && Object.keys(p.extra_body).length)
                ? JSON.stringify(p.extra_body, null, 2) : '';
            document.getElementById('fld_extra_body').value = eb;
            document.getElementById('fld_notes').value = p.notes || '';
            document.getElementById('modalTitle').textContent = '编辑 Profile · ' + p.name;
            document.getElementById('modal').classList.add('active');
        };

        window.closeModal = function(e){
            if(e && e.target && e.target.id !== 'modal') return;
            document.getElementById('modal').classList.remove('active');
        };

        function collectForm(){
            var extraRaw = (document.getElementById('fld_extra_body').value || '').trim();
            var extra = {};
            if(extraRaw){
                try { extra = JSON.parse(extraRaw); }
                catch(e){ alert('extra_body 不是合法 JSON：'+e.message); return null; }
            }
            return {
                id: document.getElementById('fld_id').value,
                name: document.getElementById('fld_name').value.trim(),
                provider_kind: document.getElementById('fld_provider_kind').value,
                model: document.getElementById('fld_model').value.trim(),
                base_url: document.getElementById('fld_base_url').value.trim(),
                api_key: document.getElementById('fld_api_key').value,
                max_tokens: parseInt(document.getElementById('fld_max_tokens').value || '64000', 10),
                reasoning_effort: document.getElementById('fld_reasoning_effort').value,
                extra_body: extra,
                notes: document.getElementById('fld_notes').value.trim(),
            };
        }

        window.saveProfile = async function(){
            var data = collectForm();
            if(!data) return;
            if(!data.name || !data.model || !data.base_url){
                alert('name / model / base_url 必填'); return;
            }
            var isEdit = !!data.id;
            var url = isEdit
                ? '/api/llm/' + encodeURIComponent(data.id) + '/update'
                : '/api/llm/create';
            try {
                var r = await fetch(url, {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(data),
                });
                var d = await r.json();
                if(d.ok){
                    closeModal();
                    loadProfiles();
                } else {
                    alert((isEdit?'更新':'创建')+'失败: '+(d.error || 'unknown'));
                }
            } catch(e){ alert('请求失败: '+e.message); }
        };

        window.testInModal = async function(){
            var data = collectForm();
            if(!data) return;
            var tr = document.getElementById('testResult');
            var btn = document.getElementById('btnTestInModal');
            tr.style.display = ''; tr.className = 'test-result';
            tr.textContent = '测试中…';
            btn.disabled = true;
            try {
                var r = await fetch('/api/llm/test', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(data),
                });
                var d = await r.json();
                if(d.ok){
                    tr.className = 'test-result ok';
                    tr.textContent = '✓ 连通 · 延迟 '+d.latency_ms+' ms\\n示例回复：'+(d.sample || '(空)');
                } else {
                    tr.className = 'test-result err';
                    tr.textContent = '✗ 失败: '+(d.error || 'unknown');
                }
            } catch(e){
                tr.className = 'test-result err';
                tr.textContent = '✗ 请求异常: '+e.message;
            } finally { btn.disabled = false; }
        };

        window.testExisting = async function(id, btn){
            var row = document.getElementById('test-'+id);
            if(!row) return;
            var originalText = btn.textContent;
            btn.disabled = true; btn.textContent = '测试中…';
            row.innerHTML = '<div class="test-result">测试中…</div>';
            try {
                var r = await fetch('/api/llm/'+encodeURIComponent(id)+'/test', {method:'POST'});
                var d = await r.json();
                if(d.ok){
                    row.innerHTML = '<div class="test-result ok">✓ 连通 · 延迟 '+d.latency_ms+' ms · 示例：'+esc(d.sample || '(空)')+'</div>';
                } else {
                    row.innerHTML = '<div class="test-result err">✗ '+esc(d.error || 'unknown')+'</div>';
                }
            } catch(e){
                row.innerHTML = '<div class="test-result err">✗ 请求异常: '+esc(e.message)+'</div>';
            } finally {
                btn.disabled = false; btn.textContent = originalText;
            }
        };

        window.setDefault = async function(id){
            try {
                var r = await fetch('/api/llm/'+encodeURIComponent(id)+'/set-default', {method:'POST'});
                var d = await r.json();
                if(d.ok) loadProfiles();
                else alert('设默认失败: '+(d.error || 'unknown'));
            } catch(e){ alert('请求失败: '+e.message); }
        };

        window.delProfile = async function(id){
            var p = currentProfiles.find(function(x){return x.id === id;});
            var name = p ? p.name : id;
            if(!confirm('确定删除 profile「'+name+'」？不可恢复。')) return;
            try {
                var r = await fetch('/api/llm/'+encodeURIComponent(id)+'/delete', {method:'POST', headers:{'X-Confirm':'yes'}});
                var d = await r.json();
                if(d.ok) loadProfiles();
                else alert('删除失败: '+(d.error || 'unknown'));
            } catch(e){ alert('请求失败: '+e.message); }
        };

        document.addEventListener('keydown', function(e){
            if(e.key === 'Escape'){
                var m = document.getElementById('modal');
                if(m && m.classList.contains('active')) m.classList.remove('active');
            }
        });

        // ============ Tab 切换 ============
        window.switchTab = function(id, btn){
            document.querySelectorAll('.tab-btn').forEach(function(t){t.classList.remove('active');});
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            if(btn) btn.classList.add('active');
            var el = document.getElementById(id);
            if(el) el.classList.add('active');
            if(id === 'routes') loadRoutes();
        };

        window.refreshActiveTab = function(){
            var active = document.querySelector('.tab-btn.active');
            var id = active ? active.getAttribute('data-tab') : 'profiles';
            if(id === 'routes') loadRoutes();
            else loadProfiles();
        };

        // ============ 路由配置 Tab ============
        // component → 中文显示名（KNOWN_CALLSITES 见 paimon/foundation/model_router.py）
        var COMPONENT_DESC = {
            // 派蒙 · 主对话入口 / 控制
            'chat': '💬 chat · 闲聊',
            'paimon': '✨ paimon · 意图分类',
            'title': '🏷 title · 标题生成',
            '派蒙': '🎭 派蒙 · 上下文压缩',
            '派蒙·响铃': '⏰ 派蒙·响铃 · 定时任务到点',
            '派蒙·安全审': '🛡 派蒙·安全审 · 入口 / skill 审查',
            // 世界树 · 记忆 / 知识
            'remember': '📝 remember · 记忆分类',
            'reconcile': '🔄 reconcile · 记忆冲突检测 / JSON 修复',
            'hygiene': '🧹 hygiene · 记忆批量整理',
            'kb_remember': '📚 kb_remember · 知识分类',
            'kb_hygiene': '📚 kb_hygiene · 知识批量整理',
            // 三月 · 自检
            '三月·自检': '🩺 三月·自检 · code-health',
            // 四影 · 自进化提案管线
            '生执·propose_skill': '🎼 生执·propose · 凝练 skill 草案',
            '生执·revise_proposal': '🎼 生执·revise · 重写 skill 草案',
            '死执·review_proposal': '💀 死执·review · 审 skill 提案',
            '自进化触发': '🌌 自进化触发 · 浅判 should_propose',
            '空执': '🌀 空执 · skill 落盘装载',
            // 七神（按七神保留铁律全列，未接入的 disabled）
            '风神': '🌬 风神 · 订阅 / 事件聚合',
            '草神': '🌿 草神 · L1 经验提取（智慧·文书）',
            '岩神': '⛰ 岩神 · 契约·财富（红利股扫描）',
            '水神': '💧 水神 · 米哈游游戏服务',
            '火神': '🔥 火神 · 战争·冲锋',
            '雷神': '⚡ 雷神 · 永恒·造物',
            '冰神': '❄ 冰神 · 反抗·联合',
            // 晨星·协同天使
            'agents': '🌟 agents · 晨星 + 协同天使',
            // 音视频（暂未接入 router）
            'video_process': '🎥 video_process · 视频分析',
            'audio_process': '🎙 audio_process · 音频分析',
        };

        // 大类划分（顶层渲染按 CATEGORY_ORDER）
        var COMPONENT_CATEGORY = {
            // 派蒙
            'chat': 'paimon', 'paimon': 'paimon', 'title': 'paimon',
            '派蒙': 'paimon', '派蒙·响铃': 'paimon', '派蒙·安全审': 'paimon',
            // 世界树
            'remember': 'irminsul', 'reconcile': 'irminsul', 'hygiene': 'irminsul',
            'kb_remember': 'irminsul', 'kb_hygiene': 'irminsul',
            // 三月
            '三月·自检': 'march',
            // 四影
            '生执·propose_skill': 'shades',
            '生执·revise_proposal': 'shades',
            '死执·review_proposal': 'shades',
            '自进化触发': 'shades',
            '空执': 'shades',
            // 七神（草神归此，按职能定位是 archon 而非 irminsul）
            '风神': 'archons', '草神': 'archons', '岩神': 'archons',
            '水神': 'archons', '火神': 'archons', '雷神': 'archons', '冰神': 'archons',
            // 晨星·协同天使
            'agents': 'agents',
            // 音视频
            'video_process': 'audiovis', 'audio_process': 'audiovis',
        };

        // 当前未接入 ModelRouter 的 component（代码不读路由，配了也不生效）
        // 面板上 selector disabled + ⚠ 标记
        var DISABLED_COMPONENTS = {
            'video_process': '当前直连 mimo_key，未接入 router（后续支持）',
            'audio_process': '当前直连 mimo_key，未接入 router（后续支持）',
            '空执': 'skill 落盘装载，无独立 LLM 调用',
            '岩神': 'dividend-tracker skill 走 I/O，archon 本体不调 LLM',
            '水神': '米哈游游戏服务在 furina_game 子包，I/O 类不调 LLM',
            '火神': 'namespace 永久壳（新职能待挂）',
            '雷神': 'namespace 永久壳（新职能待挂）',
            '冰神': 'namespace 永久壳（skill 域职能已交空执）',
        };

        // 段名按 docs/aimon.md 的"派蒙 / 3 出口 / 七神 / 支撑层"分层对齐
        var CATEGORY_DESC = {
            paimon:   '🎭 派蒙 · 守门 / 路由 / 出口 / 全程安全闸',
            skills:   '🧩 出口·skill · 单步任务直调（空执管理的被调用资源，非天使体系）',
            agents:   '🌌 出口·/agents · 晨星 + 协同天使多视角讨论',
            shades:   '🌑 出口·/evolve · 四影自进化提案管线',
            archons:  '🌟 七神 · archon 业务接口（按七神保留铁律全列，未调 LLM 的不可配）',
            march:    '⏰ 三月女神 · 调度 / 自检 / 响铃',
            irminsul: '📝 草神·memory/知识库 LLM 调用域（写入分类 + cron 整理）',
            audiovis: '🎬 音视频处理（独立 tool，未接入 router）',
            other:    '其他',
        };
        // 顶层渲染顺序：派蒙 → 3 个出口 → 七神业务 → 支撑层
        var CATEGORY_ORDER = [
            'paimon', 'skills', 'agents', 'shades', 'archons',
            'march', 'irminsul', 'audiovis', 'other',
        ];

        // skills 段总是渲染（即便 skill 列表为空也显示空态）
        var EMPTY_PLACEHOLDERS = {};

        // skills 段头部说明：明确 skill 是"被管理的被调用资源"，不是天使
        var SKILLS_NOTE = 'ℹ skill 是被空执管理的可调用资源（不是天使多 agent 体系）；每个 skill 名 = 一个路由 component';

        function profileNameById(id){
            var p = currentProfiles.find(function(x){return x.id === id;});
            return p ? p.name : (id ? id.substring(0, 8) : '');
        }

        function profileOptionsHTML(selected, includeInheritOption, inheritLabel){
            var html = '';
            if(includeInheritOption){
                html += '<option value="">'+esc(inheritLabel || '(走全局默认)')+'</option>';
            }
            currentProfiles.forEach(function(p){
                var sel = (selected === p.id) ? ' selected' : '';
                var label = p.name + (p.is_default ? ' · [默认]' : '');
                html += '<option value="'+esc(p.id)+'"'+sel+'>'+esc(label)+'</option>';
            });
            return html;
        }

        function hitCellHTML(key, hits){
            var h = hits && hits[key];
            if(!h) return '<span class="hit-none">— 未命中</span>';
            var ago = relTime(h.timestamp);
            var srcTag = '';
            if(h.provider_source === 'default') srcTag = ' <span class="hit-src">(默认)</span>';
            else if(h.provider_source === 'env') srcTag = ' <span class="hit-src">(env)</span>';
            return '<span class="hit-model">'+esc(h.model_name || '?')+'</span>'
                 + srcTag + ' <span class="hit-time">· '+esc(ago)+'</span>';
        }

        function renderPurposeRow(component, purpose, routes, hits, componentRouteId, defaultId){
            var key = component + ':' + purpose;
            var purposeRouteId = routes[key] || '';
            var hasOverride = !!purposeRouteId;
            // 继承的目标 = 组级路由 ?? 全局默认
            var inheritTarget = componentRouteId || defaultId || '';
            var inheritName = inheritTarget ? profileNameById(inheritTarget) : '(无默认 profile)';
            var inheritLabel = '(继承组级 → ' + inheritName + ')';

            var tag = hasOverride
                ? '<span class="purpose-tag tag-override">✰ 独立</span>'
                : '<span class="purpose-tag tag-inherit">继承组级</span>';
            var actionHtml = hasOverride
                ? '<button class="btn-mini" onclick="restoreInherit(\\''+esc(key)+'\\')">恢复继承</button>'
                : '';

            return '<div class="purpose-row">'
                + '<span class="purpose-name">'+esc(purpose)+'</span>'
                + tag
                + '<select class="route-select" data-key="'+esc(key)+'" onchange="savePurposeRoute(this)">'
                +   profileOptionsHTML(purposeRouteId, true, inheritLabel)
                + '</select>'
                + '<div class="purpose-action">'+actionHtml+'</div>'
                + '<span class="purpose-hit">'+hitCellHTML(key, hits)+'</span>'
                + '</div>';
        }

        // 单 purpose 且无 purpose-level override 的组件 → 紧凑单行
        // 未接入 router 的 component 也走这个（disabled selector + ⚠ 标）
        function renderCompactComponentRow(component, purpose, routes, hits, defaultId){
            var componentRouteId = routes[component] || '';
            var displayName = COMPONENT_DESC[component] || component;
            var disabledHint = DISABLED_COMPONENTS[component];
            if(disabledHint){"""
