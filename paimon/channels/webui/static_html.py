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

        document.addEventListener('DOMContentLoaded', () => {
            loadSessions();
            setupInput();
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
                (data.sessions || []).forEach((s, i) => {
                    const sid = s.id || String(i);
                    const name = s.name || sid;
                    const item = document.createElement('div');
                    item.className = 'session-item' + (sid === currentSession ? ' active' : '');
                    item.style.cssText = 'display:flex;align-items:center;justify-content:space-between';

                    const info = document.createElement('div');
                    info.style.cssText = 'flex:1;min-width:0;cursor:pointer';
                    info.innerHTML = '<div class="session-name"></div><div class="session-time">最近活动</div>';
                    info.querySelector('.session-name').textContent = name;
                    info.onclick = () => switchSession(sid);

                    const del_btn = document.createElement('span');
                    del_btn.className = 'session-delete';
                    del_btn.title = '删除会话';
                    del_btn.textContent = '\\u00d7';
                    del_btn.onclick = (e) => { e.stopPropagation(); deleteSession(sid, name); };

                    item.appendChild(info);
                    item.appendChild(del_btn);
                    list.appendChild(item);
                });
            } catch (err) {
                console.error('加载会话列表失败:', err);
            }
        }

        async function switchSession(sessionId) {
            currentSession = sessionId;
            document.getElementById('messagesContainer').innerHTML = '';
            loadSessions();
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
            if (!message || isWaitingResponse) return;

            appendMessage('user', message);
            input.value = '';
            input.style.height = 'auto';

            isWaitingResponse = true;
            updateStatus('思考中…');
            const typingMsg = appendMessage('assistant', '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>');

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
                                    fullResponse += (data.content || '');
                                    typingMsg.querySelector('.message-content').innerHTML = marked.parse(fullResponse);
                                    scrollToBottom();
                                } else if (data.type === 'done') {
                                    isWaitingResponse = false;
                                    updateStatus('就绪');
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
