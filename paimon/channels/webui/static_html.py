from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)

CHAT_HTML = (
    """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon</title>
    <style>"""
    + THEME_COLORS
    + BASE_CSS
    + NAVIGATION_CSS
    + NAV_LINKS_CSS
    + """
        body { height: 100vh; overflow: hidden; }

        .app-container {
            display: flex;
            height: calc(100vh - 60px);
        }

        .sidebar {
            width: 280px;
            background: var(--paimon-panel);
            border-right: 1px solid var(--paimon-border);
            display: flex;
            flex-direction: column;
        }
        .sidebar-header {
            padding: 20px;
            border-bottom: 1px solid var(--paimon-border);
        }
        .sidebar-header h2 {
            font-size: 16px;
            color: var(--gold);
            margin-bottom: 4px;
        }
        .sidebar-header .subtitle {
            font-size: 12px;
            color: var(--text-muted);
        }
        .new-chat-btn {
            width: calc(100% - 32px);
            padding: 12px 16px;
            margin: 16px;
            background: linear-gradient(135deg, var(--star), var(--star-light));
            color: #000;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: transform .2s, box-shadow .2s;
        }
        .new-chat-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(110,198,255,.4);
        }
        .sessions-list {
            flex: 1;
            overflow-y: auto;
            padding: 12px;
        }
        .session-item {
            padding: 12px 16px;
            margin-bottom: 4px;
            border-radius: 8px;
            cursor: pointer;
            transition: all .2s;
            border: 1px solid transparent;
        }
        .session-item:hover {
            background: var(--paimon-panel-light);
            border-color: var(--paimon-border);
        }
        .session-item.active {
            background: var(--paimon-panel-light);
            color: var(--gold);
            border-color: var(--gold-dark);
        }
        .session-name { font-size: 14px; font-weight: 500; }
        .session-time { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
        .session-delete { display:none; color:var(--text-muted); font-size:18px; cursor:pointer; padding:0 4px; line-height:1; }
        .session-delete:hover { color:#e74c3c; }
        .session-item:hover .session-delete { display:inline; }

        .chat-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--paimon-bg);
        }
        .chat-header {
            padding: 16px 24px;
            background: var(--paimon-panel);
            border-bottom: 1px solid var(--paimon-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .chat-title { font-size: 16px; font-weight: 600; color: var(--text-primary); }
        .chat-status {
            font-size: 12px;
            color: var(--text-muted);
            padding: 4px 12px;
            background: var(--paimon-panel-light);
            border-radius: 12px;
        }

        .messages-container {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
        }
        .message {
            margin-bottom: 24px;
            animation: fadeIn .3s ease-in;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to   { opacity: 1; transform: translateY(0); }
        }
        .message-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }
        .message-avatar {
            width: 32px; height: 32px;
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 16px;
        }
        .message.user .message-avatar     { background: linear-gradient(135deg, var(--gold), var(--gold-light)); }
        .message.assistant .message-avatar { background: linear-gradient(135deg, var(--star), var(--star-light)); }
        .message-sender { font-size: 13px; font-weight: 600; color: var(--text-secondary); }
        .message-time   { font-size: 11px; color: var(--text-muted); }
        .message-content {
            margin-left: 40px;
            padding: 16px;
            border-radius: 12px;
            line-height: 1.6;
        }
        .message.user .message-content {
            background: var(--paimon-panel);
            border: 1px solid var(--paimon-border);
        }
        .message.assistant .message-content {
            background: var(--paimon-panel-light);
            border: 1px solid var(--paimon-border);
        }

        .message-content h1, .message-content h2, .message-content h3 { color: var(--gold); margin: 16px 0 8px; }
        .message-content code {
            background: var(--paimon-bg); padding: 2px 6px; border-radius: 4px;
            font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace; font-size: 13px; color: var(--gold-light);
        }
        .message-content pre {
            background: var(--paimon-bg); padding: 16px; border-radius: 8px;
            overflow-x: auto; border: 1px solid var(--paimon-border);
        }
        .message-content pre code { background: none; padding: 0; }
        .message-content table { width: 100%; border-collapse: collapse; margin: 16px 0; }
        .message-content table th, .message-content table td { padding: 8px 12px; border: 1px solid var(--paimon-border); }
        .message-content table th { background: var(--paimon-panel); color: var(--gold); font-weight: 600; }
        .message-content a { color: var(--star-light); text-decoration: none; }
        .message-content a:hover { text-decoration: underline; }

        /* notice：中间状态提示，无头像、浅灰小字、窄气泡，视觉上和正文气泡分开 */
        .notice {
            margin: 4px 0 4px 40px;
            padding: 6px 12px;
            font-size: 12px;
            color: var(--text-muted);
            line-height: 1.5;
            border-left: 2px solid var(--paimon-border);
            background: transparent;
            white-space: pre-wrap;
            opacity: 0.85;
            animation: fadeIn .2s ease-in;
        }
        .notice.thinking { font-style: italic; }

        .input-area {
            padding: 20px 24px;
            background: var(--paimon-panel);
            border-top: 1px solid var(--paimon-border);
        }
        .input-container { display: flex; gap: 12px; max-width: 1000px; margin: 0 auto; }
        .message-input {
            flex: 1;
            padding: 14px 18px;
            background: var(--paimon-bg);
            border: 1px solid var(--paimon-border);
            border-radius: 12px;
            color: var(--text-primary);
            font-size: 14px;
            font-family: inherit;
            resize: none;
            max-height: 120px;
            transition: border-color .2s;
        }
        .message-input:focus { outline: none; border-color: var(--gold); }
        .message-input::placeholder { color: var(--text-muted); }
        .send-btn {
            padding: 14px 24px;
            background: linear-gradient(135deg, var(--gold), var(--gold-light));
            color: #000;
            border: none;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: transform .2s, box-shadow .2s;
        }
        .send-btn:hover:not(:disabled) {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(212,175,55,.4);
        }
        .send-btn:disabled { opacity: .5; cursor: not-allowed; }

        .typing-indicator { display: inline-flex; gap: 4px; padding: 8px; }
        .typing-dot {
            width: 8px; height: 8px;
            background: var(--star);
            border-radius: 50%;
            animation: typing 1.4s infinite;
        }
        .typing-dot:nth-child(2) { animation-delay: .2s; }
        .typing-dot:nth-child(3) { animation-delay: .4s; }
        @keyframes typing {
            0%,60%,100% { transform: translateY(0); }
            30% { transform: translateY(-10px); }
        }
    </style>
</head>
<body>
"""
    + navigation_html("chat")
    + """
    <div class="app-container">
        <div class="sidebar">
            <div class="sidebar-header">
                <h2>对话列表</h2>
                <div class="subtitle">与派蒙的历史对话</div>
            </div>
            <button class="new-chat-btn" onclick="newSession()">+ 新建对话</button>
            <div class="sessions-list" id="sessionsList"></div>
        </div>

        <div class="chat-area">
            <div class="chat-header">
                <div class="chat-title" id="chatTitle">选择或创建一个会话</div>
                <div class="chat-status" id="chatStatus">就绪</div>
            </div>
            <div class="messages-container" id="messagesContainer">
                <div class="message assistant">
                    <div class="message-header">
                        <div class="message-avatar">P</div>
                        <span class="message-sender">Paimon</span>
                    </div>
                    <div class="message-content">
                        <h3>前面的区域，以后再来探索吧！</h3>
                        <p>嘿嘿，派蒙在这里哦~ 有什么要问的尽管说吧！</p>
                    </div>
                </div>
            </div>
            <div class="input-area">
                <div class="input-container">
                    <textarea id="messageInput" class="message-input"
                        placeholder="和派蒙说点什么吧… (Shift+Enter 换行)" rows="1"></textarea>
                    <button id="sendBtn" class="send-btn" onclick="sendMessage()">发送</button>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script>
        let currentSession = 'default';
        let isWaitingResponse = false;
        // 权限询问挂起标记：true 时允许输入答复，sendMessage 走 /api/authz/answer
        let pendingAuthzAsk = false;
        // 推送长连接（/api/push）与未读计数
        let pushSource = null;
        let unreadPushCount = 0;
        const PUSH_SESSION_ID = 'push';

        document.addEventListener('DOMContentLoaded', () => {
            loadSessions();
            setupInput();
            openPushStream();
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
                // 推送会话永远置顶
                const sessions = (data.sessions || []).slice().sort(function(a, b){
                    if (a.id === PUSH_SESSION_ID) return -1;
                    if (b.id === PUSH_SESSION_ID) return 1;
                    return 0;
                });
                sessions.forEach((s, i) => {
                    const sid = s.id || String(i);
                    const name = s.name || sid;
                    const isPush = (sid === PUSH_SESSION_ID);
                    const item = document.createElement('div');
                    item.className = 'session-item' + (sid === currentSession ? ' active' : '');
                    item.style.cssText = 'display:flex;align-items:center;justify-content:space-between';
                    if (isPush) {
                        item.style.borderLeft = '3px solid var(--gold)';
                        item.style.background = 'var(--paimon-panel)';
                    }

                    const info = document.createElement('div');
                    info.style.cssText = 'flex:1;min-width:0;cursor:pointer';
                    info.innerHTML = '<div class="session-name"></div><div class="session-time"></div>';
                    let displayName = name;
                    if (isPush && unreadPushCount > 0 && sid !== currentSession) {
                        displayName = name + '  (' + unreadPushCount + ')';
                    }
                    info.querySelector('.session-name').textContent = displayName;
                    info.querySelector('.session-time').textContent = isPush ? '定时任务 & 事件触发' : '最近活动';
                    info.onclick = () => switchSession(sid);

                    item.appendChild(info);
                    // 推送会话不允许删除
                    if (!isPush) {
                        const del_btn = document.createElement('span');
                        del_btn.className = 'session-delete';
                        del_btn.title = '删除会话';
                        del_btn.textContent = '\\u00d7';
                        del_btn.onclick = (e) => { e.stopPropagation(); deleteSession(sid, name); };
                        item.appendChild(del_btn);
                    }
                    list.appendChild(item);
                });
            } catch (err) {
                console.error('加载会话列表失败:', err);
            }
        }

        async function switchSession(sessionId) {
            currentSession = sessionId;
            if (sessionId === PUSH_SESSION_ID) {
                unreadPushCount = 0;
            }
            document.getElementById('messagesContainer').innerHTML = '';
            loadSessions();
            updateInputMode();
            try {
                const resp = await fetch('/api/sessions/' + sessionId + '/messages');
                const data = await resp.json();
                document.getElementById('chatTitle').textContent = data.name || sessionId;
                (data.messages || []).forEach(function(m) {
                    appendMessage(m.role, m.content);
                });
            } catch (e) {
                document.getElementById('chatTitle').textContent = sessionId;
            }
        }

        function updateInputMode() {
            const input = document.getElementById('messageInput');
            if (!input) return;
            if (currentSession === PUSH_SESSION_ID) {
                input.placeholder = '这是推送收件箱，只读。切换到其他会话以对话。';
                input.disabled = true;
                input.style.opacity = '0.6';
            } else {
                input.placeholder = '输入消息...';
                input.disabled = false;
                input.style.opacity = '';
            }
        }

        function openPushStream() {
            if (pushSource) { try { pushSource.close(); } catch(e){} }
            try {
                pushSource = new EventSource('/api/push');
                pushSource.onmessage = (ev) => {
                    if (!ev.data) return;
                    try {
                        const data = JSON.parse(ev.data);
                        if (data.type === 'push') {
                            onPushReceived(data);
                        }
                    } catch(e) { /* 忽略非法帧 */ }
                };
                pushSource.onerror = (err) => {
                    // EventSource 浏览器会自动重连，不需要手动处理
                    console.debug('推送连接异常（将自动重连）', err);
                };
            } catch(e) {
                console.error('推送长连接建立失败:', e);
            }
        }

        function onPushReceived(data) {
            const content = data.content || '';
            if (currentSession === PUSH_SESSION_ID) {
                // 正在看推送会话 → 直接追加气泡。与切换过来看到的历史保持一致（无额外前缀）
                appendMessage('assistant', content);
                scrollToBottom();
            } else {
                // 其他会话 → 未读计数 +1，刷新会话列表角标
                unreadPushCount += 1;
                loadSessions();
            }
        }

        async function deleteSession(sessionId, name) {
            if (!confirm('确定删除会话「' + name + '」？')) return;
            try {
                await fetch('/api/sessions/' + sessionId + '/delete', { method: 'POST' });
                if (currentSession === sessionId) {
                    currentSession = 'default';
                    document.getElementById('messagesContainer').innerHTML = '';
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
            // 允许在"挂起权限询问"时发送答复；否则 isWaitingResponse 阻断
            if (!message || (isWaitingResponse && !pendingAuthzAsk)) return;

            // 答复权限询问走专用端点：不创建新的 typing bubble（原 SSE 流会继续写）
            if (pendingAuthzAsk) {
                pendingAuthzAsk = false;
                appendMessage('user', message);
                input.value = '';
                input.style.height = 'auto';
                updateStatus('处理中…');
                try {
                    const resp = await fetch('/api/authz/answer', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ session_id: currentSession, answer: message })
                    });
                    if (!resp.ok) {
                        const err = await resp.json().catch(() => ({}));
                        appendMessage('assistant', '⚠️ ' + (err.error || '权限询问已关闭，请稍后重试'));
                        isWaitingResponse = false;
                        updateStatus('就绪');
                    }
                } catch (e) {
                    console.error('权限答复发送失败:', e);
                    appendMessage('assistant', '⚠️ 答复发送失败: ' + e.message);
                    isWaitingResponse = false;
                    updateStatus('就绪');
                }
                return;
            }

            appendMessage('user', message);
            input.value = '';
            input.style.height = 'auto';

            isWaitingResponse = true;
            updateStatus('思考中…');
            let typingMsg = appendMessage('assistant', '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>');
            // 权限询问后需要另起气泡：true 时下一条 message 会新建 typingMsg + 重置 fullResponse
            let needNewBubble = false;
            // watchdog thinking 只用一个元素，后来的覆盖前面的（avoid "还在忙/还在忙/还在忙" 堆积）
            let lastThinkingEl = null;

            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message, session_id: currentSession })
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
                    const lines = buffer.split('\\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.type === 'message') {
                                    // 权限询问之后的首个 message chunk：新建气泡，让派蒙新回复独立显示
                                    if (needNewBubble) {
                                        typingMsg = appendMessage('assistant', '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>');
                                        fullResponse = '';
                                        needNewBubble = false;
                                        lastThinkingEl = null;
                                    }
                                    fullResponse += (data.content || '');
                                    typingMsg.querySelector('.message-content').innerHTML = marked.parse(fullResponse);
                                    scrollToBottom();
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
                                        const container = document.getElementById('messagesContainer');
                                        if (typingMsg && typingMsg.parentNode === container) {
                                            container.insertBefore(noticeEl, typingMsg);
                                        } else {
                                            container.appendChild(noticeEl);
                                        }
                                        if (kind === 'thinking') lastThinkingEl = noticeEl;
                                    }
                                    scrollToBottom();
                                } else if (data.type === 'question') {
                                    // 权限/魔女会询问作为独立气泡。
                                    // 若当前气泡已有正文（例如天使已回了一段再触发魔女会询问），
                                    // 必须新建气泡，不能覆盖原内容。
                                    const q = '🛡️ **权限询问**\\n\\n' + (data.content || '') +
                                        '\\n\\n*直接在下方输入回复即可。默认 30 秒无答复视为拒绝。*';
                                    if (fullResponse) {
                                        // 封存已有内容的气泡，新建一个独立气泡放询问
                                        typingMsg = appendMessage('assistant', '');
                                        fullResponse = '';
                                        lastThinkingEl = null;
                                    }
                                    typingMsg.querySelector('.message-content').innerHTML = marked.parse(q);
                                    pendingAuthzAsk = true;
                                    // 用户答复后的下一条 message 仍需新起气泡（同意后的派蒙回复独立）
                                    needNewBubble = true;
                                    updateStatus('等你答复…');
                                    scrollToBottom();
                                } else if (data.type === 'done') {
                                    isWaitingResponse = false;
                                    updateStatus('就绪');
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
                                    scrollToBottom();
                                } else if (data.type === 'error') {
                                    fullResponse += '\\n\\n> ' + (data.content || '未知错误');
                                    typingMsg.querySelector('.message-content').innerHTML = marked.parse(fullResponse);
                                    isWaitingResponse = false;
                                    updateStatus('就绪');
                                }
                            } catch (e) { }
                        }
                    }
                }

                if (isWaitingResponse) { isWaitingResponse = false; updateStatus('就绪'); }

            } catch (err) {
                console.error('发送消息失败:', err);
                typingMsg.querySelector('.message-content').textContent = '连接失败: ' + err.message;
                isWaitingResponse = false;
                updateStatus('就绪');
            }
        }

        function appendMessage(role, content) {
            const container = document.getElementById('messagesContainer');
            const msgDiv = document.createElement('div');
            msgDiv.className = 'message ' + role;

            const avatar = role === 'user' ? '\\u{1F60A}' : 'P';
            const sender = role === 'user' ? '旅行者' : 'Paimon';
            const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

            msgDiv.innerHTML = '<div class="message-header">'
                + '<div class="message-avatar">' + avatar + '</div>'
                + '<span class="message-sender">' + sender + '</span>'
                + '<span class="message-time">' + time + '</span>'
                + '</div>'
                + '<div class="message-content">' + (role === 'user' ? content : marked.parse(content)) + '</div>';

            container.appendChild(msgDiv);
            scrollToBottom();
            return msgDiv;
        }

        function updateStatus(text) {
            document.getElementById('chatStatus').textContent = text;
        }

        function scrollToBottom() {
            const container = document.getElementById('messagesContainer');
            container.scrollTop = container.scrollHeight;
        }
    </script>
</body>
</html>
"""
)
