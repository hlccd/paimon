"""LLM_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

LLM_SCRIPT_2 = """                // 未接入路由：selector 灰显 + ⚠ 标，4 元素对齐 normal compact-row 列布局
                return '<div class="compact-row disabled" title="'+esc(disabledHint)+'">'
                    + '<span class="compact-name">'+esc(displayName)
                    +     ' <span class="tag-disabled-inline">⚠ 未接入</span></span>'
                    + '<select class="route-select" disabled>'
                    +   '<option>(未接入 router，配置不生效)</option>'
                    + '</select>'
                    + '<span></span>'
                    + '<span class="purpose-hit hit-disabled">'+esc(disabledHint)+'</span>'
                    + '</div>';
            }
            return '<div class="compact-row">'
                + '<span class="compact-name">'+esc(displayName)+'</span>'
                + '<select class="route-select" data-component="'+esc(component)+'" onchange="saveComponentRoute(this)">'
                +   profileOptionsHTML(componentRouteId, true, '(走全局默认)')
                + '</select>'
                + '<span class="route-save-flash" data-flash-for="'+esc(component)+'">已保存 ✓</span>'
                + '<span class="purpose-hit">'+hitCellHTML(component, hits)+'</span>'
                + '</div>';
        }

        // 退化条件：purpose 数 == 1 且 purpose-level 无 override；
        // 否则保留嵌套两层（用户能看到/修复异常 override）
        function shouldUseCompactRow(component, purposes, routes){
            if(purposes.length !== 1) return false;
            var purposeKey = component + ':' + purposes[0];
            return !routes[purposeKey];
        }

        // skills 段：每个 skill 名 = 一个 component，按 component 级路由可配
        // （_handler.py:41-42 处 component=skill_name, purpose=skill_name；
        //  细粒度路由 key = "{skill_name}:{skill_name}"，但 purpose 与 component 同名
        //  所以走 component 级 compact 行即可，不展开 purpose 子行）
        function renderSkillsSection(skills, routes, hits, defaultId){
            var displayName = CATEGORY_DESC.skills;
            var note = '<div class="empty-placeholder" style="margin-bottom:8px">'+esc(SKILLS_NOTE)+'</div>';
            var bodyHtml;
            if(!skills || !skills.length){
                bodyHtml = note + '<div class="empty-placeholder">未发现 skill</div>';
            } else {
                var rows = skills.map(function(s){
                    var componentRouteId = routes[s.name] || '';
                    var label = '🧩 ' + s.name + (s.description ? ' · ' + s.description : '');
                    return '<div class="compact-row" title="'+esc(s.description || '')+'">'
                        + '<span class="compact-name">'+esc(label)+'</span>'
                        + '<select class="route-select" data-component="'+esc(s.name)+'" onchange="saveComponentRoute(this)">'
                        +   profileOptionsHTML(componentRouteId, true, '(走全局默认)')
                        + '</select>'
                        + '<span class="route-save-flash" data-flash-for="'+esc(s.name)+'">已保存 ✓</span>'
                        + '<span class="purpose-hit">'+hitCellHTML(s.name, hits)+'</span>'
                        + '</div>';
                }).join('');
                bodyHtml = note + rows;
            }
            return '<div class="category-section collapsed">'
                + '<div class="category-header" onclick="toggleCategory(this)">'
                +   '<span class="category-arrow">▼</span>'
                +   '<span class="category-name">'+esc(displayName)+'</span>'
                +   '<span class="category-stat">'+(skills ? skills.length : 0)+' skill</span>'
                + '</div>'
                + '<div class="category-body">'+bodyHtml+'</div>'
                + '</div>';
        }

        // 普通 category：components 形态为 {component: [purposes]}
        function renderCategorySection(cat, components, routes, hits, defaultId){
            var displayName = CATEGORY_DESC[cat] || cat;

            // 空段（占位）
            if(EMPTY_PLACEHOLDERS[cat] && (!components || !Object.keys(components).length)){
                return '<div class="category-section collapsed">'
                    + '<div class="category-header" onclick="toggleCategory(this)">'
                    +   '<span class="category-arrow">▼</span>'
                    +   '<span class="category-name">'+esc(displayName)+'</span>'
                    +   '<span class="category-stat">占位</span>'
                    + '</div>'
                    + '<div class="category-body">'
                    +   '<div class="empty-placeholder">'+esc(EMPTY_PLACEHOLDERS[cat])+'</div>'
                    + '</div>'
                    + '</div>';
            }

            var componentNames = Object.keys(components);
            var totalPurposes = componentNames.reduce(function(s, c){
                return s + components[c].length;
            }, 0);
            var bodyHtml = componentNames.map(function(comp){
                var purposes = components[comp];
                if(shouldUseCompactRow(comp, purposes, routes)){
                    return renderCompactComponentRow(comp, purposes[0], routes, hits, defaultId);
                }
                return renderComponentSection(comp, purposes, routes, hits, defaultId);
            }).join('');
            // 整段全 disabled（如 audiovis）→ stat 加红警示
            var allDisabled = componentNames.every(function(c){return DISABLED_COMPONENTS[c];});
            var statClass = allDisabled ? 'category-stat stat-warn' : 'category-stat';
            var statText = allDisabled
                ? componentNames.length+' 组件 · ⚠ 全部未接入'
                : componentNames.length+' 组件 · '+totalPurposes+' 项';
            return '<div class="category-section collapsed">'
                + '<div class="category-header" onclick="toggleCategory(this)">'
                +   '<span class="category-arrow">▼</span>'
                +   '<span class="category-name">'+esc(displayName)+'</span>'
                +   '<span class="'+statClass+'">'+statText+'</span>'
                + '</div>'
                + '<div class="category-body">'+bodyHtml+'</div>'
                + '</div>';
        }

        window.toggleCategory = function(el){
            var sec = el.closest('.category-section');
            if(sec) sec.classList.toggle('collapsed');
        };

        function renderComponentSection(component, purposes, routes, hits, defaultId){
            var componentRouteId = routes[component] || '';
            var purposeOverrideCount = purposes.filter(function(p){return routes[component + ':' + p];}).length;
            var bodyHtml = purposes.map(function(p){
                return renderPurposeRow(component, p, routes, hits, componentRouteId, defaultId);
            }).join('');
            var displayName = COMPONENT_DESC[component] || component;
            return '<div class="component-section">'
                + '<div class="component-header">'
                +   '<div class="component-toggle" onclick="toggleComponent(this)">'
                +     '<span class="component-arrow">▼</span>'
                +     '<span class="component-name">'+esc(displayName)+'</span>'
                +     '<span class="component-stat">'+purposes.length+' 项'
                +       (purposeOverrideCount?' · '+purposeOverrideCount+' 独立':'')
                +     '</span>'
                +   '</div>'
                +   '<div class="component-group-control">'
                +     '<span>组级路由:</span>'
                +     '<select class="route-select" data-component="'+esc(component)+'" onchange="saveComponentRoute(this)" style="min-width:240px">'
                +       profileOptionsHTML(componentRouteId, true, '(走全局默认)')
                +     '</select>'
                +     '<span class="route-save-flash" data-flash-for="'+esc(component)+'">已保存 ✓</span>'
                +   '</div>'
                + '</div>'
                + '<div class="component-body">'+bodyHtml+'</div>'
                + '</div>';
        }

        window.toggleComponent = function(el){
            var sec = el.closest('.component-section');
            if(sec) sec.classList.toggle('collapsed');
        };

        async function loadRoutes(){
            var heroEl = document.getElementById('routeDefaultHero');
            var container = document.getElementById('routeContainer');
            if(!heroEl || !container) return;
            heroEl.textContent = '加载中...';
            container.innerHTML = '<div class="empty-state">加载中...</div>';
            try {
                var [profResp, routeResp] = await Promise.all([
                    fetch('/api/llm/list').then(function(r){return r.json();}),
                    fetch('/api/llm/routes').then(function(r){return r.json();}),
                ]);
                var profiles = profResp.profiles || [];
                currentProfiles = profiles;
                var routes = routeResp.routes || {};
                window._lastRoutes = routes;  // saveComponentRoute 检测 cascade 用
                var callsites = routeResp.callsites || [];
                var hits = routeResp.hits || {};
                var def = routeResp.default;
                var defaultId = def ? def.id : '';
                var skills = routeResp.skills || [];  // 天使段渲染用

                // 全局默认 hero
                if(profiles.length){
                    var opts = profiles.map(function(p){
                        var sel = (p.id === defaultId) ? ' selected' : '';
                        return '<option value="'+esc(p.id)+'"'+sel+'>'+esc(p.name)+'</option>';
                    }).join('');
                    heroEl.innerHTML = '<span style="flex-shrink:0">🎯 全局默认 profile：</span>'
                        + '<select class="route-select" id="defaultProfileSelect" onchange="setDefaultFromHero(this)" style="min-width:280px">'
                        + opts + '</select>'
                        + '<span class="route-save-flash" data-flash-for="__default__">已切换 ✓</span>'
                        + '<span style="margin-left:auto;font-size:12px;color:var(--text-muted);font-style:italic">所有未命中路由回落到此</span>';
                    heroEl.style.display = 'flex';
                    heroEl.style.gap = '10px';
                    heroEl.style.alignItems = 'center';
                } else {
                    heroEl.innerHTML = '<span style="color:var(--status-error)">⚠ 还没有 profile，请到「模型管理」tab 新增。</span>';
                    heroEl.style.display = 'block';
                }

                // 桶按 category（七神 archons 现在独立顶层段，不再嵌四影下）
                var byCategory = {};
                callsites.forEach(function(c){
                    var cat = COMPONENT_CATEGORY[c.component] || 'other';
                    if(!byCategory[cat]) byCategory[cat] = {};
                    if(!byCategory[cat][c.component]) byCategory[cat][c.component] = [];
                    byCategory[cat][c.component].push(c.purpose);
                });

                // 占位 category 即使无 component 也渲染
                Object.keys(EMPTY_PLACEHOLDERS).forEach(function(cat){
                    if(!byCategory[cat]) byCategory[cat] = {};
                });

                var orderedHtml = CATEGORY_ORDER
                    .filter(function(cat){
                        if(cat === 'skills') return true;  // skills 段总是渲染（即便 skill 数为 0 也显示空态）
                        if(byCategory[cat] === undefined) return false;
                        return Object.keys(byCategory[cat]).length || EMPTY_PLACEHOLDERS[cat];
                    })
                    .map(function(cat){
                        if(cat === 'skills') return renderSkillsSection(skills, routes, hits, defaultId);
                        return renderCategorySection(cat, byCategory[cat], routes, hits, defaultId);
                    }).join('');

                if(!orderedHtml){
                    container.innerHTML = '<div class="empty-state">无已知调用点</div>';
                    return;
                }
                container.innerHTML = orderedHtml;
            } catch(e){
                container.innerHTML = '<div class="empty-state">加载失败: '+esc(String(e))+'</div>';
            }
        }

        window.setDefaultFromHero = async function(selectEl){
            var pid = selectEl.value;
            if(!pid) return;
            var flash = document.querySelector('.route-save-flash[data-flash-for="__default__"]');
            try {
                var r = await fetch('/api/llm/' + encodeURIComponent(pid) + '/set-default', {method: 'POST'});
                var d = await r.json();
                if(d.ok){
                    if(flash){
                        flash.classList.add('shown');
                        setTimeout(function(){ flash.classList.remove('shown'); }, 1500);
                    }
                    // 重新渲染整个路由表（"[默认]" 标记要跟着移动；leyline 事件
                    // 已让 gnosis 缓存失效，下一次 chat 自动用新默认）
                    setTimeout(function(){ loadRoutes(); }, 200);
                } else {
                    alert('切换失败: ' + (d.error || 'unknown'));
                }
            } catch(e){
                alert('请求失败: ' + e.message);
            }
        };

        // component 段头 selector 改值：先存组级路由；若该 component 下已有
        // purpose override，弹 confirm 让用户决定是否一并清空让其继承新值。
        window.saveComponentRoute = async function(selectEl){
            var component = selectEl.getAttribute('data-component');
            var pid = selectEl.value;
            var routes = window._lastRoutes || {};
            var prefix = component + ':';
            var overrideKeys = Object.keys(routes).filter(function(k){return k.indexOf(prefix) === 0;});

            try {
                // step 1: 写组级路由（pid 空 = 删 component 路由 → 走全局默认）
                var url = pid ? '/api/llm/routes/set' : '/api/llm/routes/delete';
                var body = pid ? {route_key: component, profile_id: pid} : {route_key: component};
                var r = await fetch(url, {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(body),
                });
                var d = await r.json();
                if(!d.ok){ alert('保存组级路由失败: '+(d.error || 'unknown')); return; }

                // step 2: 检测 purpose override 并征求 cascade
                if(overrideKeys.length > 0){
                    var purposeNames = overrideKeys.map(function(k){return k.substring(prefix.length);}).join('、');
                    var msg = '该 component 下有 '+overrideKeys.length+' 个 purpose 已独立设置：\\n  '+purposeNames+'\\n\\n是否一并清空让它们继承新组级值？';
                    if(confirm(msg)){
                        var rc = await fetch('/api/llm/routes/cascade-clear', {
                            method: 'POST', headers: {'Content-Type':'application/json'},
                            body: JSON.stringify({component: component}),
                        });
                        var dc = await rc.json();
                        if(!dc.ok) alert('cascade 清空失败: '+(dc.error || 'unknown'));
                    }
                }

                var flash = document.querySelector('.route-save-flash[data-flash-for="'+CSS.escape(component)+'"]');
                if(flash){
                    flash.classList.add('shown');
                    setTimeout(function(){ flash.classList.remove('shown'); }, 1500);
                }
                loadRoutes();  // 重渲染让所有 inherit 状态更新
            } catch(e){
                alert('请求失败: '+e.message);
            }
        };

        // purpose 行 selector 改值：值为空=删 purpose 路由（恢复继承）；非空=set
        window.savePurposeRoute = async function(selectEl){
            var key = selectEl.getAttribute('data-key');
            var pid = selectEl.value;
            try {
                var url = pid ? '/api/llm/routes/set' : '/api/llm/routes/delete';
                var body = pid ? {route_key: key, profile_id: pid} : {route_key: key};
                var r = await fetch(url, {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(body),
                });
                var d = await r.json();
                if(d.ok) loadRoutes();
                else alert('保存失败: '+(d.error || 'unknown'));
            } catch(e){
                alert('请求失败: '+e.message);
            }
        };

        // 「恢复继承」按钮：删 purpose 级路由 → 该行回退到继承组级
        window.restoreInherit = async function(key){
            try {
                var r = await fetch('/api/llm/routes/delete', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json', 'X-Confirm':'yes'},
                    body: JSON.stringify({route_key: key}),
                });
                var d = await r.json();
                if(d.ok) loadRoutes();
                else alert('恢复继承失败: '+(d.error || 'unknown'));
            } catch(e){
                alert('请求失败: '+e.message);
            }
        };

        window.loadProfiles = loadProfiles;
        window.onload = function(){ loadProfiles(); };
    })();
    </script>
"""
