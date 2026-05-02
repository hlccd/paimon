"""GAME_SCRIPT chunk · 自动切片，原始字符串拼接还原。"""

GAME_SCRIPT_2 = """            var heroCount = {};
            var rowTeams = [];   // 缓存每行的 teams 避免重复 extract
            results.forEach(function(res, i){
                var ab = res.abyss;
                if(!ab){ rowTeams.push([]); return; }
                var ts = _extractTeams(a.game, defs[i].type, ab.raw, charsById);
                rowTeams.push(ts);
                ts.forEach(function(t){
                    (t.avatars||[]).forEach(function(av){
                        if(av.name) heroCount[av.name] = (heroCount[av.name]||0) + 1;
                    });
                });
            });
            var topHeroes = Object.keys(heroCount).map(function(n){return {n:n, c:heroCount[n]};})
                .sort(function(a,b){return b.c - a.c;}).slice(0, 6);
            var topHeroesHtml = '';
            if(topHeroes.length){
                topHeroesHtml = '<div class="top-heroes-label">主力出场（跨副本队伍）</div>'
                    + '<div class="top-heroes">'
                    + topHeroes.map(function(h){
                        return '<span class="hero-chip">'+esc(h.n)+'<span class="cnt">×'+h.c+'</span></span>';
                    }).join('')
                    + '</div>';
            }

            var rows = defs.map(function(def, i){
                var ab = results[i].abyss;
                if(!ab){
                    return '<div class="abyss-row" style="cursor:default">'
                        + '<span class="abyss-name">'+esc(def.name)+'</span>'
                        + '<span class="abyss-floor">-</span>'
                        + '<span class="abyss-star">-</span>'
                        + '<span class="abyss-meta">未挑战</span>'
                        + '</div>';
                }
                // 组装展示字段
                var floorVal, starVal, metaVal;
                if(a.game === 'zzz' && def.type === 'shiyu'){
                    floorVal = '评级 ' + (ab.max_floor || '-');
                    starVal = ab.total_star + '分';
                    metaVal = ab.total_battle > 0 ? (ab.total_battle+'s') : fmtRelative(ab.scan_ts);
                }else if(def.type === 'stygian'){
                    floorVal = '难度 ' + (ab.max_floor || '-');
                    starVal = ab.total_star + 's';
                    metaVal = fmtRelative(ab.scan_ts);
                }else if(def.type === 'poetry'){
                    floorVal = '第 ' + (ab.max_floor || '-') + ' 轮';
                    starVal = ab.total_star + '★';
                    metaVal = fmtRelative(ab.scan_ts);
                }else{
                    // spiral / forgotten_hall / pure_fiction / apocalyptic / mem
                    floorVal = String(ab.max_floor || '-');
                    starVal = ab.total_star + '★';
                    if(ab.total_battle > 0){
                        metaVal = ab.total_win + '/' + ab.total_battle;
                    }else{
                        metaVal = fmtRelative(ab.scan_ts);
                    }
                }
                var teams = rowTeams[i] || [];
                var hasTeams = teams.length > 0;
                var indicator = hasTeams ? '<span class="abyss-toggle">▴</span>' : '';
                var rowHtml = '<div class="abyss-row" '+(hasTeams?'onclick="toggleAbyssTeams(\\''+esc(k)+'\\','+i+')"':'style="cursor:default"')+'>'
                    + '<span class="abyss-name">'+esc(def.name)+indicator+'</span>'
                    + '<span class="abyss-floor">'+esc(floorVal)+'</span>'
                    + '<span class="abyss-star">'+esc(String(starVal))+'</span>'
                    + '<span class="abyss-meta">'+esc(String(metaVal))+'</span>'
                    + '</div>';
                var teamsHtml = hasTeams
                    ? '<div class="abyss-teams" id="abyss-teams-'+esc(k)+'-'+i+'">'+_renderTeams(teams)+'</div>'
                    : '';
                return rowHtml + teamsHtml;
            });
            slot.innerHTML = topHeroesHtml + rows.join('');
        }

        // 从 abyss.raw 解析每场战斗的队伍。
        // spiral / forgotten_hall 等接口的 avatar 只有 id/level/rarity 没 name/cons/weapon
        // → 必须用 charsById（mihoyo_character 表）反查
        function _extractTeams(game, abyssType, raw, charsById){
            if(!raw || typeof raw !== 'object') return [];
            charsById = charsById || {};
            var norm = function(av){ return _normAvatar(av, charsById); };
            var teams = [];
            try{
                if(game === 'gs' && abyssType === 'spiral'){
                    (raw.floors || []).forEach(function(floor){
                        (floor.levels || []).forEach(function(level){
                            (level.battles || []).forEach(function(battle){
                                var half = battle.index === 1 ? '上' : (battle.index === 2 ? '下' : '#'+battle.index);
                                teams.push({
                                    label: (floor.index||'?')+'-'+(level.index||'?')+' '+half,
                                    stars: level.star || 0,
                                    max_star: level.max_star || 0,
                                    avatars: (battle.avatars || []).map(norm),
                                });
                            });
                        });
                    });
                }else if(game === 'gs' && abyssType === 'poetry'){
                    // 幻想真境剧诗：detail.rounds_data[]（米游社字段名是 rounds_data 不是 rounds）
                    var detail = raw.detail || raw;
                    (detail.rounds_data || raw.rounds || []).forEach(function(r, i){
                        var avs = r.avatars || r.role || [];
                        if(avs.length){
                            teams.push({
                                label: '第 '+(r.round_id || i+1)+' 轮' + (r.is_get_medal ? ' ★' : ''),
                                stars: r.is_get_medal ? 1 : 0,
                                avatars: avs.map(norm),
                            });
                        }
                    });
                }else if(game === 'gs' && abyssType === 'stygian'){
                    var chs = (raw.single && raw.single.challenge) || raw.challenge || [];
                    chs.forEach(function(c, i){
                        var avs = c.teams || c.avatars || [];
                        if(avs.length){
                            teams.push({
                                label: c.name || ('挑战 '+(i+1)),
                                stars: c.difficulty || 0,
                                avatars: avs.map(norm),
                            });
                        }
                    });
                }else if(game === 'sr' && abyssType === 'peak'){
                    // 异相仲裁：challenge_peak_records[].mob_records[].avatars + boss_record.avatars
                    (raw.challenge_peak_records || []).forEach(function(rec, ri){
                        var groupName = (rec.group && rec.group.name) || ('挑战 '+(ri+1));
                        // 普通怪战
                        (rec.mob_records || []).forEach(function(mob, mi){
                            var avs = mob.avatars || [];
                            if(avs.length){
                                teams.push({
                                    label: groupName + ' 怪 #' + (mi+1),
                                    stars: mob.star_num || 0,
                                    avatars: avs.map(norm),
                                });
                            }
                        });
                        // BOSS 战
                        var br = rec.boss_record;
                        if(br && (br.avatars || []).length){
                            teams.push({
                                label: groupName + ' BOSS',
                                stars: br.star_num || 0,
                                avatars: br.avatars.map(norm),
                            });
                        }
                    });
                }else if(game === 'sr'){
                    (raw.all_floor_detail || []).forEach(function(f){
                        var nodeKeys = Object.keys(f).filter(function(k){
                            return k.indexOf('node_') === 0 && !isNaN(parseInt(k.slice(5), 10));
                        }).sort(function(a,b){
                            return parseInt(a.replace('node_',''),10) - parseInt(b.replace('node_',''),10);
                        });
                        nodeKeys.forEach(function(nk){
                            var node = f[nk];
                            if(node && (node.avatars || []).length){
                                teams.push({
                                    label: (f.name||'层') + ' ' + nk.replace('node_','节'),
                                    stars: f.star_num || 0,
                                    avatars: node.avatars.map(norm),
                                });
                            }
                        });
                    });
                }else if(game === 'zzz' && abyssType === 'shiyu'){
                    // ZZZ 式舆防卫战：hadal_info_v2.{fitfh,fourth}_layer_detail.layer_challenge_info_list[]
                    // 每层 N 个挑战，每个 challenge 含 avatar_list
                    var v2 = raw.hadal_info_v2 || raw;
                    [['fitfh_layer_detail','第 5 层'], ['fourth_layer_detail','第 4 层']].forEach(function(pair){
                        var layer = v2[pair[0]] || {};
                        var infos = layer.layer_challenge_info_list || [];
                        infos.forEach(function(c, idx){
                            var avs = c.avatar_list || c.avatars || [];
                            if(avs.length){
                                teams.push({
                                    label: pair[1] + ' #' + (c.layer_id || idx+1),
                                    stars: c.rating || c.score || 0,
                                    avatars: avs.map(norm),
                                });
                            }
                        });
                    });
                }else if(game === 'zzz'){
                    // 危局/其他：list/floor_detail 兜底
                    var list = raw.list || raw.all_floor_detail || raw.floor_detail
                        || (raw.memory_list) || [];
                    list.forEach(function(it, idx){
                        var avs = it.avatar_list || it.avatars || [];
                        if(avs.length){
                            teams.push({
                                label: it.name || it.level_name || it.layer_name || ('节 '+(idx+1)),
                                stars: it.score || it.star || it.layer_index || 0,
                                avatars: avs.map(norm),
                            });
                        }
                    });
                }
            }catch(e){
                console.error('[战报] 队伍解析失败', game, abyssType, e);
            }
            return teams;
        }

        // raw avatar → 统一格式，name/cons/weapon 缺时从 mihoyo_character 表（charsById）补
        function _normAvatar(av, charsById){
            charsById = charsById || {};
            var id = String(av.id || av.avatar_id || '');
            var c = charsById[id] || {};
            // ZZZ rarity 是字符串 "S"/"A"/"B"，转数字便于统一渲染颜色
            var rawRarity = av.rarity != null ? av.rarity : (av.rank != null ? av.rank : c.rarity);
            var rarity;
            if(typeof rawRarity === 'string'){
                var m = {'S':5, 'A':4, 'B':3};
                rarity = m[rawRarity] || 4;
            }else{
                rarity = rawRarity || 4;
            }
            // ZZZ avatar.rank 在 raw 里是「影画/命之座」（不是 rarity），优先信 charsById.constellation
            var cons = (c.constellation != null ? c.constellation : (av.rank != null && typeof av.rank === 'number' ? av.rank : 0));
            return {
                id: id,
                name: av.name || av.full_name || c.name || '',
                level: av.level || av.cur_level || c.level || 0,
                rarity: rarity,
                cons: cons,
                weapon: c.weapon || {},
            };
        }

        // 命座+精炼格式：0+0 / 0+1 / 2+1（精炼仅 5 星武器算）
        function _consAffix(av){
            var cons = av.cons || 0;
            var affix = 0;
            if(av.weapon && av.weapon.rarity >= 5){
                affix = av.weapon.affix || 0;
            }
            return cons + '+' + affix;
        }

        function _renderTeams(teams){
            return teams.map(function(t){
                var avHtml = (t.avatars || []).map(function(av){
                    var rcls = av.rarity >= 5 ? 'r5' : (av.rarity === 4 ? 'r4' : '');
                    var ca = _consAffix(av);
                    var nameTxt = av.name || ('id:'+av.id);
                    var weaponInfo = (av.weapon && av.weapon.name) ? (av.weapon.name + (av.weapon.affix?(' 精'+av.weapon.affix):'')) : '';
                    var tip = nameTxt + ' Lv'+(av.level||'?') + (weaponInfo?(' · '+weaponInfo):'');
                    return '<span class="abyss-team-avatar '+rcls+'" title="'+esc(tip)+'">'
                        + esc(nameTxt)
                        + ' <span class="ca">'+ca+'</span>'
                        + '</span>';
                }).join('');
                var starInfo = t.stars > 0
                    ? ' <span style="color:var(--gold);font-family:monospace">'+t.stars+(t.max_star?('/'+t.max_star):'')+'★</span>'
                    : '';
                return '<div class="abyss-team">'
                    + '<span class="abyss-team-label">'+esc(t.label)+starInfo+'</span>'
                    + avHtml
                    + '</div>';
            }).join('');
        }

        window.toggleAbyssTeams = function(k, i){
            var el = document.getElementById('abyss-teams-'+k+'-'+i);
            if(!el) return;
            el.classList.toggle('closed');
            var row = el.previousElementSibling;
            var toggle = row && row.querySelector('.abyss-toggle');
            if(toggle) toggle.textContent = el.classList.contains('closed') ? '▾' : '▴';
        };

        async function _fillGacha(a, k){
            var slot = document.getElementById('gacha-'+k);
            if(!slot) return;
            var labels = POOL_LABELS_BY_GAME[a.game] || {};
            var poolKeys = POOL_ORDER_BY_GAME[a.game] || [];
            if(poolKeys.length === 0){
                slot.innerHTML = '<div class="gacha-empty">暂不支持此游戏</div>';
                return;
            }
            var pool = _currentPool[k];
            if(!pool || !labels[pool]) pool = poolKeys[0];
            _currentPool[k] = pool;

            var poolsHtml = '<div class="gacha-head">'
                + poolKeys.map(function(p){
                    return '<span class="gpool '+(p===pool?'active':'')+'" onclick="gameSelectPool(\\''+esc(k)+'\\',\\''+p+'\\')">'+labels[p]+'</span>';
                }).join('') + '</div>';

            var r = await fetch('/api/game/gacha/stats?game='+a.game+'&uid='+encodeURIComponent(a.uid)+'&gacha_type='+pool);
            var d = await r.json();
            var s = d.stats || {total:0};
            var syncBtn = _gachaSyncBtn(a);
            if(!s.total){
                var emptyHint = a.game === 'sr'
                    ? '暂无数据，点右下角"URL 导入"（米哈游限制 SR 不能自动同步）'
                    : '暂无数据，点右下角"同步抽卡"';
                slot.innerHTML = poolsHtml
                    + '<div class="gacha-empty">'+emptyHint+'</div>'
                    + syncBtn;
                _resumeGachaSyncIfRunning(a, slot);
                return;
            }
            var hardPity = s.hard_pity || 90;
            // 软保底 = 硬保底 × 0.8（GS 角色 73 / 武器 63；近似）
            var softThreshold = Math.floor(hardPity * 0.8);
            var pityCls = s.pity_5 >= hardPity - 10 ? 'warn' : (s.pity_5 >= softThreshold ? 'soft' : '');
            var topName = (a.game === 'zzz') ? 'S 级' : '5 星';
            var fives = (s.fives||[]).slice(0, 30);
            var fivesHtml = fives.length === 0
                ? '<div class="gacha-empty">此池暂无 '+topName+'</div>'
                : fives.map(function(f){
                    var pull = f.pull_count || 0;
                    var pullCls = pull <= 30 ? 'lucky' : (pull >= softThreshold ? 'heavy' : '');
                    var upHtml;
                    if(f.is_up === true){
                        upHtml = '<span class="gfive-up on" title="UP 出货">UP</span>';
                    }else if(f.is_up === false){
                        upHtml = '<span class="gfive-up off" title="出了常驻 = 歪了">歪</span>';
                    }else{
                        upHtml = '<span class="gfive-up none" title="此池无 UP 概念">—</span>';
                    }
                    return '<div class="gfive">'
                        + '<span class="gfive-badge">★</span>'
                        + '<span class="gfive-name">'+esc(f.name)+'</span>'
                        + '<span class="gfive-pull '+pullCls+'">'+pull+'抽</span>'
                        + upHtml
                        + '<span class="gfive-time">'+esc((f.time||'').slice(5,16))+'</span>'
                        + '</div>';
                }).join('');
            // 最欧 / 最歪 caption
            var allFives = s.fives || [];
            var luckRow = '';
            if(allFives.length){
                var pulls = allFives.map(function(f){return f.pull_count||0;}).filter(function(x){return x>0;});
                if(pulls.length){
                    var minP = Math.min.apply(null, pulls);
                    var maxP = Math.max.apply(null, pulls);
                    var luckiest = allFives.find(function(f){return f.pull_count===minP;});
                    var heaviest = allFives.find(function(f){return f.pull_count===maxP;});
                    luckRow = '<div class="gacha-luck-row">'
                        + '<span class="luck-item lucky">最欧 <span class="v">'+minP+'抽</span> '+esc(luckiest?luckiest.name:'')+'</span>'
                        + '<span class="luck-item heavy">最歪 <span class="v">'+maxP+'抽</span> '+esc(heaviest?heaviest.name:'')+'</span>'
                        + '</div>';
                }
            }
            slot.innerHTML = poolsHtml
                + '<div class="gacha-summary">总抽 <span class="pity">'+s.total
                + '</span><span class="sep">·</span>'+topName+'保底 <span class="pity '+pityCls+'">'+s.pity_5+'/'+hardPity
                + '</span><span class="sep">·</span>已出 '+topName+' <span class="pity">'+s.count_5
                + '</span><span class="sep">·</span>平均 <span class="pity">'+s.avg_pity_5+'</span></div>'
                + luckRow
                + '<div class="gacha-five-list">'+fivesHtml+'</div>'
                + syncBtn;
            _resumeGachaSyncIfRunning(a, slot);
        }

        async function _resumeGachaSyncIfRunning(a, slot){
            try{
                var sr = await fetch('/api/game/gacha/sync/status?game='+a.game+'&uid='+encodeURIComponent(a.uid));
                var sd = await sr.json();
                if(sd.state === 'running'){
                    var btn = slot.querySelector('button[onclick*="gameSyncGacha"]');
                    _pollGachaSync(a.game, a.uid, btn);
                }
            }catch(_){}
        }

        function _gachaSyncBtn(a, label){
            label = label || '同步抽卡';
            // SR 米哈游限制 stoken→authkey，必须走 URL 导入；GS/ZZZ 自动同步即可
            var btns = a.game === 'sr'
                ? '<button class="btn primary tiny" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameImportGachaUrl(this.dataset.game, this.dataset.uid)">URL 导入</button>'
                : '<button class="btn primary tiny" data-game="'+esc(a.game)+'" data-uid="'+esc(a.uid)+'" onclick="gameSyncGacha(this)">'+esc(label)+'</button>';
            return '<div class="gacha-sync-row">'
                + '<span class="gacha-sync-status" id="gsync-status-'+esc(keyOf(a))+'"></span>'
                + btns
                + '</div>';
        }

        // ============ 操作 ============
        window.gameSignOne = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            btn.disabled = true; var old = btn.textContent; btn.textContent = '...';
            try{
                var r = await fetch('/api/game/sign', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game, uid}),
                });
                var d = await r.json();
                btn.textContent = d.ok ? '✓' : '✗';
                if(!d.ok && d.msg) alert('签到失败: '+d.msg);
                setTimeout(function(){ btn.textContent = old; btn.disabled = false; loadOverview(); }, 1200);
            }catch(e){
                btn.textContent='✗'; setTimeout(function(){btn.textContent=old;btn.disabled=false;},2000);
            }
        };

        // 「刷新此账号数据」background + 轮询：完成后自动重渲该账号详情，无需手动刷新页面
        var _collectPollTimers = {};   // key='game::uid' -> interval id

        window.gameCollectOne = async function(btn){
            var game = btn.dataset.game, uid = btn.dataset.uid;
            var k = game+'::'+uid;
            console.log('[水神·采集] 触发', game, uid);
            btn.disabled = true; var old = btn.textContent; btn.textContent = '启动...';
            try{
                var r = await fetch('/api/game/collect_one', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body: JSON.stringify({game, uid}),
                });
                var d = await r.json();
                if(!d.ok){
                    alert('采集启动失败: '+(d.msg||''));
                    btn.textContent = old; btn.disabled = false;
                    return;
                }
                btn.textContent = '采集中...';
                if(_collectPollTimers[k]){ clearInterval(_collectPollTimers[k]); }
                var poll = async function(){
                    try{
                        var sr = await fetch('/api/game/collect_one/status?game='+game+'&uid='+encodeURIComponent(uid));
                        var sd = await sr.json();
                        if(sd.state === 'running'){
                            return;   // 等下次 tick
                        }
                        clearInterval(_collectPollTimers[k]); delete _collectPollTimers[k];
                        if(sd.state === 'done'){
                            console.log('[水神·采集] DONE', sd.counts);
                            btn.textContent = '✓ 已更新';
                            // 数据已落库 → 清缓存 + 重渲该账号详情区（无需手动刷新）
                            delete _charsCache[k];
                            var a = _allAccs.find(function(x){return x.uid === uid && x.game === game;});
                            if(a){
                                _fillAbyss(a, k);
                                _fillCharacters(a, k);
                                // 摘要也重新拉一次（树脂/委托数据更新）
                                if(typeof loadOverview === 'function') loadOverview();
                            }
                        }else if(sd.state === 'failed'){
                            btn.textContent = '✗ 失败';
                            alert('采集失败: '+(sd.error||''));
                        }
                        setTimeout(function(){btn.textContent=old;btn.disabled=false;}, 3000);
                    }catch(e){
                        clearInterval(_collectPollTimers[k]); delete _collectPollTimers[k];
                        console.error('[水神·采集] poll 异常', e);"""
