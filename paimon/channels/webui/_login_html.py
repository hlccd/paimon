"""登录页 HTML — 主类 _get_login_html 抽离至独立 module，不嵌业务逻辑。"""
from __future__ import annotations


def get_login_html() -> str:
    from paimon.channels.webui.theme import THEME_COLORS
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Paimon</title>
<style>"""
        + THEME_COLORS
        + """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: var(--paimon-bg);
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
        padding: 20px;
    }
    .login-container {
        background: var(--paimon-panel);
        border: 1px solid var(--paimon-border);
        border-radius: 16px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.4);
        padding: 40px;
        width: 100%;
        max-width: 400px;
        text-align: center;
    }
    .logo { font-size: 48px; margin-bottom: 20px; }
    h1 {
        font-size: 24px;
        font-weight: 700;
        margin-bottom: 10px;
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    p { color: var(--text-muted); margin-bottom: 30px; font-size: 14px; }
    .input-group { margin-bottom: 20px; text-align: left; }
    label { display: block; color: var(--text-secondary); font-size: 14px; margin-bottom: 8px; font-weight: 500; }
    input[type="password"] {
        width: 100%;
        padding: 12px 16px;
        background: var(--paimon-bg);
        border: 1px solid var(--paimon-border);
        border-radius: 8px;
        font-size: 16px;
        color: var(--text-primary);
        transition: border-color 0.2s;
    }
    input[type="password"]:focus { outline: none; border-color: var(--gold); }
    button {
        width: 100%;
        padding: 14px;
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        color: #000;
        border: none;
        border-radius: 8px;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
    }
    .error { color: var(--status-error); font-size: 14px; margin-top: 10px; display: none; }
    .error.show { display: block; }
</style>
</head>
<body>
<div class="login-container">
    <div class="logo">P</div>
    <h1>Paimon</h1>
    <p>请输入访问码以继续</p>
    <form id="loginForm">
        <div class="input-group">
            <label for="accessCode">访问码</label>
            <input type="password" id="accessCode" placeholder="输入访问码" autocomplete="off" required>
        </div>
        <button type="submit">验证并进入</button>
        <div class="error" id="error">访问码错误，请重试</div>
    </form>
</div>
<script>
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const code = document.getElementById('accessCode').value;
        const errorDiv = document.getElementById('error');
        try {
            const response = await fetch('/api/auth', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code })
            });
            const data = await response.json();
            if (data.success) {
                window.location.href = '/';
            } else {
                errorDiv.classList.add('show');
            }
        } catch (error) {
            errorDiv.textContent = '验证失败，请检查网络连接';
            errorDiv.classList.add('show');
        }
    });
</script>
</body>
</html>"""
    )
