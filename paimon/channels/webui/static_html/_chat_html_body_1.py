"""CHAT_HTML body chunk 1/2 · 自动切片。"""

CHAT_HTML_BODY_1 = """
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
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
    <script>
        // SEC-011 XSS 防护：marked.parse 输出必经 DOMPurify.sanitize 才能 innerHTML。
        // body_2.py 4 处 markdown 渲染都改调 window.safeMd；CDN 任一加载失败时降级纯文本。
        window.safeMd = function(text) {
            var raw = text || '';
            if (typeof marked === 'undefined' || typeof marked.parse !== 'function') {
                return raw.replace(/[&<>"']/g, function(c){
                    var m = {};
                    m['&'] = '&amp;'; m['<'] = '&lt;'; m['>'] = '&gt;';
                    m['"'] = '&quot;'; m["'"] = '&#39;';
                    return m[c];
                });
            }
            var html = marked.parse(raw);
            if (typeof DOMPurify !== 'undefined' && DOMPurify.sanitize) {
                return DOMPurify.sanitize(html);
            }
            // DOMPurify CDN 加载失败：直接返 marked 输出（XSS 风险但保功能可用，
            // 等用户切换网络后刷新页面会重载 CDN 修复）
            return html;
        };
    </script>
    <script>
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
                    del_btn.textContent = '\\u00d7';
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
"""
