from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)

# ---- JS chunks（自动切片）----
from ._chat_html_body_1 import CHAT_HTML_BODY_1
from ._chat_html_body_2 import CHAT_HTML_BODY_2

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
        /* 每个 session 一个独立的 pane，currentSession 的 display=block，
           其他 display=none。让 A 在 streaming 时切到 B 不会丢 A 的 typing chunk。 */
        .session-pane { display: none; }
        .session-pane.active { display: block; }
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
    + CHAT_HTML_BODY_1
    + CHAT_HTML_BODY_2
)
