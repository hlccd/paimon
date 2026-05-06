"""小红书 collector：playwright headless + cookies + 解析搜索页 DOM。

xhs 没有公开搜索 API（edith API 要 x-s 签名 reverse 难度极高）；
绕过路径：playwright 跑真实 chromium 加载已登录 cookies 打开 search_result 页，
让浏览器自身 JS 跑完签名 + SPA 渲染，我们从 DOM 拿 title/url/作者/点赞。

cookies 来源：~/.paimon/cookies/xhs.json（playwright storage_state 格式）
首次登录：webui /feed 面板「站点登录」tab 扫码

⚠️ 性能：每次 collect 启一次 headless chromium（~3-5s 冷启动）。
   单用户低频调研可接受；不适合高 QPS 场景。

⚠️ 日期：搜索列表卡片不带 published_at（要点进笔记详情才有）。
   MVP 阶段把 published_at 设为 range_to（今天作为占位），
   牺牲精确时效换覆盖度——后续可优化为详情页二次抓。
"""
from __future__ import annotations

import re
from urllib.parse import quote

from ..core import log
from ..core.schema import Item


_SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={kw}&type=51"   # type=51 综合
_NOTE_HREF_RE = re.compile(r"^/(?:explore|discovery/item)/([0-9a-fA-F]+)")
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _cookies_storage_path() -> str | None:
    """取 ~/.paimon/cookies/xhs.json 路径；不存在返回 None。"""
    try:
        from paimon.foundation.site_cookies import cookies_exists, cookies_path
        return str(cookies_path("xhs")) if cookies_exists("xhs") else None
    except ImportError:
        from pathlib import Path
        p = Path.home() / ".paimon" / "cookies" / "xhs.json"
        return str(p) if p.exists() else None


def _parse_count(text: str) -> int:
    """xhs 计数文本 → int：'1.2万'/'2k'/'123'/'12.3w'。"""
    t = (text or "").strip().replace(",", "")
    if not t:
        return 0
    m = re.match(r"^([0-9.]+)\s*([万Wwk千Kk]?)\s*\+?$", t)
    if not m:
        try:
            return int(float(t))
        except (ValueError, TypeError):
            return 0
    num = float(m.group(1))
    suffix = m.group(2).lower()
    if suffix in ("万", "w"):
        return int(num * 10000)
    if suffix in ("千", "k"):
        return int(num * 1000)
    return int(num)


# 在浏览器里跑的 DOM 提取脚本（page.evaluate）
# 用宽泛的 selector + 容错查找，xhs 经常改 class hash
_EXTRACT_JS = r"""
() => {
    const out = [];
    const cards = document.querySelectorAll(
        'section.note-item, div.note-item, [class*="note-item"], a[href^="/explore/"]'
    );
    const seen = new Set();
    cards.forEach(node => {
        let link = (node.tagName === 'A' && /^\/(explore|discovery\/item)\//.test(node.getAttribute('href') || ''))
            ? node
            : node.querySelector('a[href^="/explore/"], a[href^="/discovery/item/"]');
        if (!link) return;
        const href = link.getAttribute('href') || '';
        if (!href || seen.has(href)) return;
        seen.add(href);

        const card = link.closest('section.note-item, div.note-item, [class*="note-item"]') || link.parentElement || link;

        const titleEl = card.querySelector('.title, [class*="title"], a[href^="/explore/"] span');
        const title = (titleEl?.innerText || link.innerText || '').trim();

        const authorEl = card.querySelector('.author .name, .name, [class*="author"] span, .user-name');
        const author = (authorEl?.innerText || '').trim();

        let like = '';
        const likeEl = card.querySelector('.like-wrapper .count, .like-count, [class*="like"] .count, [class*="like"] span');
        if (likeEl) like = (likeEl.innerText || '').trim();
        if (!like) {
            for (const s of card.querySelectorAll('span')) {
                const t = (s.innerText || '').trim();
                if (/^[\d.]+\s*[万wk]?\+?$/i.test(t)) { like = t; break; }
            }
        }

        out.push({ href, title, author, like });
    });
    return out;
}
"""


def collect(
    topic: str,
    range_from: str,
    range_to: str,
    *,
    limit: int = 20,
) -> list[Item]:
    """xhs collector 入口：playwright 跑搜索页拿笔记列表。

    无 cookies / playwright 未装 / chromium 未装 / 反爬阻挡 → 返回 [] + 清晰 log。
    """
    cookies_path = _cookies_storage_path()
    if not cookies_path:
        log.source_log("xhs", "无 cookies；请到 webui /feed 面板「站点登录」tab 扫码")
        return []

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.source_log("xhs", "playwright 未装；pip install -e . 后还需 playwright install chromium")
        return []

    log.source_log("xhs", f"启 headless chromium 跑搜索 topic={topic!r}（首次冷启动 3-5s）")
    items: list[Item] = []
    final_url = ""
    try:
        with sync_playwright() as p:
            # xhs 反爬严，必须用强反检测：启动参数 + init script 同时上
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=AutomationControlled,IsolateOrigins,site-per-process",
                    "--no-sandbox",
                ],
            )
            try:
                context = browser.new_context(
                    storage_state=cookies_path,
                    viewport={"width": 1440, "height": 900},
                    user_agent=_UA,
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                )
                # 反检测组合拳：去掉 navigator.webdriver 之外的常见自动化特征
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                    window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
                    const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
                    if (originalQuery) {
                        window.navigator.permissions.query = (p) =>
                            p.name === 'notifications'
                                ? Promise.resolve({ state: Notification.permission })
                                : originalQuery(p);
                    }
                """)
                page = context.new_page()
                url = _SEARCH_URL.format(kw=quote(topic))
                page.goto(url, wait_until="domcontentloaded", timeout=20_000)

                # 不用 wait_for_selector / wait_for_load_state(networkidle)
                # ——xhs SPA 有 keep-alive 请求，networkidle 永远等不到；
                # wait_for_selector 在这种 SPA 上行为也异常。
                # 实测：固定等 8 秒后 DOM 里有 22+ 条 /explore/<id> 笔记 link。
                page.wait_for_timeout(8_000)
                # 滚动触发更多笔记懒加载
                try:
                    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2_500)
                    page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2_500)
                except Exception:
                    pass

                # 早退检测：如果还是没笔记 link，可能被跳到登录页或反爬阻挡
                final_url = page.url
                explore_count = page.evaluate(
                    '() => document.querySelectorAll(\'a[href^="/explore/"]\').length'
                )
                if explore_count == 0:
                    if "login" in final_url or "sign" in final_url:
                        log.source_log("xhs", f"被跳到登录页（cookies 失效，回 webui 扫码续期）：{final_url[:120]}")
                    else:
                        log.source_log("xhs", f"页面无笔记 link（可能反爬）：{final_url[:120]}")
                    return []

                final_url = page.url
                raw = page.evaluate(_EXTRACT_JS) or []
                log.source_log("xhs", f"DOM 提取 {len(raw)} 条候选 (url={final_url[:80]})")

                seen: set[str] = set()
                for d in raw[:limit * 2]:
                    href = (d.get("href") or "").strip()
                    if not href:
                        continue
                    m = _NOTE_HREF_RE.match(href)
                    nid = m.group(1) if m else href.rsplit("/", 1)[-1].split("?")[0][:32]
                    if not nid or nid in seen:
                        continue
                    seen.add(nid)
                    title = (d.get("title") or "").strip()
                    if not title:
                        continue
                    items.append(Item(
                        source="xhs",
                        item_id=nid,
                        title=title[:200],
                        url=f"https://www.xiaohongshu.com{href}" if href.startswith("/") else href,
                        body="",
                        author=(d.get("author") or "").strip(),
                        # MVP：搜索列表无日期，假设近期，published_at=range_to 让 recency=1
                        # 详情页二次抓真实日期是 P2 优化项
                        published_at=range_to,
                        engagement={
                            "like": _parse_count(d.get("like") or ""),
                        },
                        metadata={"date_uncertain": True},
                    ))
                    if len(items) >= limit:
                        break
            finally:
                browser.close()
    except Exception as e:
        log.source_log("xhs", f"playwright 异常: {type(e).__name__}: {e}")
        return []

    log.source_log("xhs", f"采集 {len(items)} 条")
    return items
