/* chat 主入口脚本 — 对话列表 + SSE 流式聊天 + 权限询问回答 */

let currentSession = 'default';
        // 多会话并发支持：每个 session 独立的 pending 状态。
        // 之前是单一全局 isWaitingResponse 锁导致 A 在跑时不能在 B 发新消息；
        // 现在按 session id 跟踪，A/B 各自独立 streaming 互不影响。
        const waitingSessions = new Set();
        const pendingAuthzAskSessions = new Set();
        // 工具：取/创建一个 session 的 messages pane
        function getSessionPane(sid) {
            const container = document.getElementById('messagesContainer');
            let pane = container.querySelector('.session-pane[data-sid="' + sid + '"]');
            if (!pane) {
                pane = document.createElement('div');
                pane.className = 'session-pane';
                pane.dataset.sid = sid;
                container.appendChild(pane);
            }
            return pane;
        }
        function showSessionPane(sid) {
            const container = document.getElementById('messagesContainer');
            container.querySelectorAll('.session-pane').forEach(function(p) {
                p.classList.toggle('active', p.dataset.sid === sid);
            });
        }
        // 推送已迁移到顶部红点抽屉（push_archive 表 + /api/push_archive/* 路由），
        // 不再有 push 会话实体，前端 chat 不再监听 /api/push 长连接。

        document.addEventListener('DOMContentLoaded', () => {
            loadSessions();
            setupInput();
            // 启动时同步加载 default 绑定的历史消息，避免 UI 空白但后端有旧上下文
            switchSession('default');
        });

        function setupInput() {
            const input = document.getElementById('messageInput');
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
            });
            input.addEventListener('input', () => {
                input.style.height = 'auto';
                input.style.height = Math.min(input.scrollHeight, 120) + 'px';
            });
        }

        async function loadSessions() {
            try {
                const response = await fetch('/api/sessions');
                const data = await response.json();
                const list = document.getElementById('sessionsList');
                list.innerHTML = '';
                const sessions = data.sessions || [];
                sessions.forEach((s, i) => {
                    const sid = s.id || String(i);
                    const name = s.name || sid;
                    const item = document.createElement('div');
                    item.className = 'session-item' + (sid === currentSession ? ' active' : '');
                    item.style.cssText = 'display:flex;align-items:center;justify-content:space-between';

                    const info = document.createElement('div');
                    info.style.cssText = 'flex:1;min-width:0;cursor:pointer';
                    info.innerHTML = '<div class="session-name"></div><div class="session-time"></div>';
                    info.querySelector('.session-name').textContent = name;
                    info.querySelector('.session-time').textContent = '最近活动';
                    info.onclick = () => switchSession(sid);

                    item.appendChild(info);
                    const del_btn = document.createElement('span');
                    del_btn.className = 'session-delete';
                    del_btn.title = '删除会话';
                    del_btn.textContent = '\u00d7';
                    del_btn.onclick = (e) => { e.stopPropagation(); deleteSession(sid, name); };
                    item.appendChild(del_btn);
                    list.appendChild(item);
                });
            } catch (err) {
                console.error('加载会话列表失败:', err);
            }
        }

        async function switchSession(sessionId) {
            currentSession = sessionId;
            // 每个 session 独立 pane：切 session 时仅切显示，不动其他 pane 的 DOM
            const pane = getSessionPane(sessionId);
            showSessionPane(sessionId);
            loadSessions();
            updateInputMode();
            // streaming 中的 session 不重新拉历史（避免覆盖正在 stream 的 typing 气泡）
            // 仅未 streaming 时才清空 + fetch
            const isStreaming = waitingSessions.has(sessionId);
            try {
                const resp = await fetch('/api/sessions/' + sessionId + '/messages');
                const data = await resp.json();
                document.getElementById('chatTitle').textContent = data.name || sessionId;
                if (!isStreaming) {
                    pane.innerHTML = '';
                    (data.messages || []).forEach(function(m) {
                        if (m.role === 'notice') {
                            // 切回来时把持久化的 milestone/ack 渲染为小字 hint
                            // —— 不走 appendMessage 创建气泡
                            const noticeEl = document.createElement('div');
                            noticeEl.className = 'notice';
                            noticeEl.textContent = m.content;
                            pane.appendChild(noticeEl);
                        } else {
                            appendMessage(m.role, m.content, sessionId);
                        }
                    });
                }
            } catch (e) {
                document.getElementById('chatTitle').textContent = sessionId;
            }
        }

        function updateInputMode() {
            const input = document.getElementById('messageInput');
            if (!input) return;
            input.placeholder = '输入消息...';
            input.disabled = false;
            input.style.opacity = '';
        }

        async function deleteSession(sessionId, name) {
            if (!confirm('确定删除会话「' + name + '」？')) return;
            try {
                await fetch('/api/sessions/' + sessionId + '/delete', { method: 'POST', headers: {'X-Confirm': 'yes'} });
                // 清掉对应 pane（无论是否当前会话）
                const oldPane = document.querySelector('.session-pane[data-sid="' + sessionId + '"]');
                if (oldPane) oldPane.remove();
                waitingSessions.delete(sessionId);
                pendingAuthzAskSessions.delete(sessionId);
                if (currentSession === sessionId) {
                    currentSession = 'default';
                    showSessionPane('default');
                    document.getElementById('chatTitle').textContent = '新对话';
                }

                loadSessions();
            } catch (e) {
                console.error('删除会话失败:', e);
            }
        }

        async function newSession() {
            try {
                const resp = await fetch('/api/sessions/new', { method: 'POST' });
                const data = await resp.json();
                if (data.id) {
                    await switchSession(data.id);
                }
            } catch (e) {
                console.error('创建会话失败:', e);
            }
        }

        async function sendMessage() {
            const input = document.getElementById('messageInput');
            const message = input.value.trim();
            // 锁定本次请求归属的 session：发起后用户切走，DOM 操作仍要落到这个 session 的 pane
            const reqSession = currentSession;
            // /stop /cancel 类"中断当前任务"命令必须能在 streaming 期间发送
            // 否则旧任务卡住时 user 没法取消（前端 silent reject 让 user 觉得"无法发送"）
            const isStopCmd = /^\/(stop|cancel)\b/i.test(message);
            // per-session 状态：当前 session 在 streaming 且无挂起权限询问 → 拒绝；
            // 其他 session 在 streaming 不影响当前 session 发送。
            // 例外：stop 类命令要绕过此 lock。
            if (!message ||
                (waitingSessions.has(reqSession) && !pendingAuthzAskSessions.has(reqSession) && !isStopCmd)) {
                return;
            }

            // 答复权限询问走专用端点：不创建新的 typing bubble（原 SSE 流会继续写）
            if (pendingAuthzAskSessions.has(reqSession)) {
                pendingAuthzAskSessions.delete(reqSession);
                appendMessage('user', message, reqSession);
                input.value = '';
                input.style.height = 'auto';
                if (currentSession === reqSession) updateStatus('处理中…');
                try {
                    const resp = await fetch('/api/authz/answer', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ session_id: reqSession, answer: message })
                    });
                    if (!resp.ok) {
                        const err = await resp.json().catch(() => ({}));
                        appendMessage('assistant', '⚠️ ' + (err.error || '权限询问已关闭，请稍后重试'), reqSession);
                        waitingSessions.delete(reqSession);
                        if (currentSession === reqSession) updateStatus('就绪');
                    }
                } catch (e) {
                    console.error('权限答复发送失败:', e);
                    appendMessage('assistant', '⚠️ 答复发送失败: ' + e.message, reqSession);
                    waitingSessions.delete(reqSession);
                    if (currentSession === reqSession) updateStatus('就绪');
                }
                return;
            }

            appendMessage('user', message, reqSession);
            input.value = '';
            input.style.height = 'auto';

            waitingSessions.add(reqSession);
            if (currentSession === reqSession) updateStatus('思考中…');
            let typingMsg = appendMessage('assistant', '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>', reqSession);
            // 权限询问后需要另起气泡：true 时下一条 message 会新建 typingMsg + 重置 fullResponse
            let needNewBubble = false;
            // watchdog thinking 只用一个元素，后来的覆盖前面的（avoid "还在忙/还在忙/还在忙" 堆积）
            let lastThinkingEl = null;

            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message, session_id: reqSession })
                });

                if (!response.ok) throw new Error('HTTP ' + response.status);

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.type === 'message') {
                                    // 权限询问之后的首个 message chunk：新建气泡，让派蒙新回复独立显示
                                    if (needNewBubble) {
                                        typingMsg = appendMessage('assistant', '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>', reqSession);
                                        fullResponse = '';
                                        needNewBubble = false;
                                        lastThinkingEl = null;
                                    }
                                    fullResponse += (data.content || '');
                                    typingMsg.querySelector('.message-content').innerHTML = window.safeMd(fullResponse);
                                    if (currentSession === reqSession) scrollToBottom();
                                } else if (data.type === 'notice') {
                                    // 中间状态提示（ack/milestone/tool/thinking/done_recap）
                                    // 渲染为浅灰小字独立元素，插到 typing 占位气泡之前
                                    const kind = data.kind || 'milestone';
                                    const content = data.content || '';
                                    if (kind === 'thinking' && lastThinkingEl) {
                                        lastThinkingEl.textContent = content;
                                    } else {
                                        const noticeEl = document.createElement('div');
                                        noticeEl.className = 'notice' + (kind === 'thinking' ? ' thinking' : '');
                                        noticeEl.textContent = content;
                                        // 路由到 reqSession 对应的 pane（用户切走了也写在原 pane）
                                        const pane = getSessionPane(reqSession);
                                        if (typingMsg && typingMsg.parentNode === pane) {
                                            pane.insertBefore(noticeEl, typingMsg);
                                        } else {
                                            pane.appendChild(noticeEl);
                                        }
                                        if (kind === 'thinking') lastThinkingEl = noticeEl;
                                    }
                                    if (currentSession === reqSession) scrollToBottom();
                                } else if (data.type === 'question') {
                                    // 权限询问作为独立气泡。
                                    // 若当前气泡已有正文（例如已回了一段再触发权限询问），
                                    // 必须新建气泡，不能覆盖原内容。
                                    const q = '🛡️ **权限询问**\n\n' + (data.content || '') +
                                        '\n\n*直接在下方输入回复即可。默认 30 秒无答复视为拒绝。*';
                                    if (fullResponse) {
                                        // 封存已有内容的气泡，新建一个独立气泡放询问
                                        typingMsg = appendMessage('assistant', '', reqSession);
                                        fullResponse = '';
                                        lastThinkingEl = null;
                                    }
                                    typingMsg.querySelector('.message-content').innerHTML = window.safeMd(q);
                                    pendingAuthzAskSessions.add(reqSession);
                                    // 用户答复后的下一条 message 仍需新起气泡（同意后的派蒙回复独立）
                                    needNewBubble = true;
                                    if (currentSession === reqSession) updateStatus('等你答复…');
                                    if (currentSession === reqSession) scrollToBottom();
                                } else if (data.type === 'done') {
                                    waitingSessions.delete(reqSession);
                                    if (currentSession === reqSession) updateStatus('就绪');
                                    // 防御：若整个请求期间都没收到 message 事件（极端情况，
                                    // 如四影 prepare 失败 + reply_text 为空，或服务端异常），
                                    // typing 占位气泡从未被正文替换 → 移除避免底部残留空动画。
                                    if (typingMsg && !fullResponse) {
                                        const contentEl = typingMsg.querySelector('.message-content');
                                        if (contentEl && contentEl.querySelector('.typing-indicator')) {
                                            typingMsg.remove();
                                            typingMsg = null;
                                        }
                                    }
                                    loadSessions();
                                    if (currentSession === reqSession) scrollToBottom();
                                } else if (data.type === 'error') {
                                    fullResponse += '\n\n> ' + (data.content || '未知错误');
                                    typingMsg.querySelector('.message-content').innerHTML = window.safeMd(fullResponse);
                                    waitingSessions.delete(reqSession);
                                    if (currentSession === reqSession) updateStatus('就绪');
                                }
                            } catch (e) { }
                        }
                    }
                }

                if (waitingSessions.has(reqSession)) {
                    waitingSessions.delete(reqSession);
                    if (currentSession === reqSession) updateStatus('就绪');
                }
                // 流被服务端中断（/stop 取消四影 → SSE 直接关，没发 done 事件）
                // → typing 占位永远转圈。done handler 的清理逻辑这里也补一份。
                if (typingMsg && !fullResponse) {
                    const contentEl = typingMsg.querySelector('.message-content');
                    if (contentEl && contentEl.querySelector('.typing-indicator')) {
                        typingMsg.remove();
                        typingMsg = null;
                    }
                }

            } catch (err) {
                console.error('发送消息失败:', err);
                if (typingMsg) typingMsg.querySelector('.message-content').textContent = '连接失败: ' + err.message;
                waitingSessions.delete(reqSession);
                if (currentSession === reqSession) updateStatus('就绪');
            }
        }

        function appendMessage(role, content, sid) {
            // 第三参数 sid 默认 currentSession；多会话并发时，sendMessage 内部会显式传
            // 入 reqSession 让消息落到正确 pane（即便用户已切走该 session）。
            const targetSid = sid || currentSession;
            const container = getSessionPane(targetSid);
            const msgDiv = document.createElement('div');
            msgDiv.className = 'message ' + role;

            const avatar = role === 'user' ? '\u{1F60A}' : 'P';
            const sender = role === 'user' ? '旅行者' : 'Paimon';
            const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

            msgDiv.innerHTML = '<div class="message-header">'
                + '<div class="message-avatar">' + avatar + '</div>'
                + '<span class="message-sender">' + sender + '</span>'
                + '<span class="message-time">' + time + '</span>'
                + '</div>'
                + '<div class="message-content">' + (role === 'user' ? content : window.safeMd(content)) + '</div>';

            container.appendChild(msgDiv);
            // 仅当目标 session 是当前显示的才 scroll（否则 scroll 当前 session 的内容会让用户困惑）
            if (targetSid === currentSession) scrollToBottom();
            return msgDiv;
        }

        function updateStatus(text) {
            document.getElementById('chatStatus').textContent = text;
        }

        function scrollToBottom() {
            const container = document.getElementById('messagesContainer');
            container.scrollTop = container.scrollHeight;
        }
