THEME_COLORS = """
    :root {
        --paimon-bg: #1a1625;
        --paimon-panel: #251d35;
        --paimon-panel-light: #2f2640;
        --paimon-border: #3d3450;

        --gold: #d4af37;
        --gold-light: #f4d03f;
        --gold-dark: #b8941f;

        --star: #6ec6ff;
        --star-light: #90d5ff;
        --star-dark: #4ba3d9;

        --text-primary: #f3f4f6;
        --text-secondary: #d1d5db;
        --text-muted: #9ca3af;

        --status-success: #10b981;
        --status-warning: #f59e0b;
        --status-error: #ef4444;
    }
"""

BASE_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        background: var(--paimon-bg);
        color: var(--text-primary);
    }

    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: var(--paimon-bg); }
    ::-webkit-scrollbar-thumb { background: var(--paimon-border); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--gold-dark); }
"""

NAVIGATION_CSS = """
    .nav-bar {
        height: 60px;
        background: var(--paimon-panel);
        border-bottom: 2px solid var(--gold-dark);
        display: flex;
        align-items: center;
        padding: 0 24px;
        box-shadow: 0 4px 6px rgba(0,0,0,.3);
    }
    .nav-logo {
        font-size: 20px;
        font-weight: 700;
        background: linear-gradient(135deg, var(--gold), var(--gold-light));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-right: 40px;
    }
"""

NAVIGATION_HTML = """
    <div class="nav-bar">
        <div class="nav-logo">Paimon</div>
    </div>
"""
