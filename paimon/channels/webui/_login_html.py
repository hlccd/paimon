"""登录页 HTML — 主类 _get_login_html 抽离至独立 module，不嵌业务逻辑。

风格跟主 web 一致（暖米白底 + sky 天蓝主色 + stone 暖灰文），不依赖 dash-warm
layout（不需要 sidebar 等大架构），所以 token 直接 inline。
"""
from __future__ import annotations


def get_login_html() -> str:
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Paimon</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%230EA5E9'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3C/svg%3E">
<style>
    :root {
        --pm-bg-page:    #FAF7F2;
        --pm-bg-card:    #FFFFFF;
        --pm-bg-input:   #FFFFFF;
        --pm-border:     #E7E2DA;
        --pm-text-primary:   #1C1917;
        --pm-text-secondary: #57534E;
        --pm-text-muted:     #A8A29E;
        --pm-primary:        #0EA5E9;
        --pm-primary-hover:  #0284C7;
        --pm-primary-subtle: #F0F9FF;
        --pm-primary-border: #BAE6FD;
        --pm-danger:         #DC2626;
        --pm-shadow-lg: 0 4px 12px 0 rgba(120, 80, 50, 0.08), 0 2px 4px 0 rgba(120, 80, 50, 0.04);
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
        background: var(--pm-bg-page);
        color: var(--pm-text-primary);
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
        padding: 20px;
    }
    .login-container {
        background: var(--pm-bg-card);
        border: 1px solid var(--pm-border);
        border-radius: 16px;
        box-shadow: var(--pm-shadow-lg);
        padding: 40px 36px;
        width: 100%;
        max-width: 400px;
        text-align: center;
    }
    .logo {
        width: 56px; height: 56px;
        margin: 0 auto 16px;
        border-radius: 50%;
        background: var(--pm-primary-subtle);
        color: var(--pm-primary);
        border: 1px solid var(--pm-primary-border);
        display: flex; align-items: center; justify-content: center;
        font-size: 22px; font-weight: 700;
    }
    h1 {
        font-size: 22px;
        font-weight: 600;
        color: var(--pm-text-primary);
        margin-bottom: 8px;
    }
    p { color: var(--pm-text-muted); margin-bottom: 28px; font-size: 13px; }
    .input-group { margin-bottom: 20px; text-align: left; }
    label {
        display: block; color: var(--pm-text-secondary);
        font-size: 13px; margin-bottom: 6px; font-weight: 500;
    }
    input[type="password"] {
        width: 100%;
        padding: 11px 14px;
        background: var(--pm-bg-input);
        border: 1px solid var(--pm-border);
        border-radius: 8px;
        font-size: 14px;
        color: var(--pm-text-primary);
        transition: border-color 0.15s, box-shadow 0.15s;
        font-family: inherit;
    }
    input[type="password"]:focus {
        outline: none;
        border-color: var(--pm-primary);
        box-shadow: 0 0 0 3px var(--pm-primary-subtle);
    }
    button {
        width: 100%;
        padding: 12px;
        background: var(--pm-primary);
        color: #fff;
        border: none;
        border-radius: 8px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        transition: background-color 0.15s;
    }
    button:hover { background: var(--pm-primary-hover); }
    button:focus-visible { outline: 2px solid var(--pm-primary); outline-offset: 2px; }
    .error {
        color: var(--pm-danger);
        font-size: 13px;
        margin-top: 12px;
        display: none;
    }
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
