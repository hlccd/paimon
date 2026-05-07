"""贴吧 collector：playwright headless + cookies + 解析搜索页 DOM。

匿名访问 `/f/search/res` 直接 HTTP 403 跳百度安全验证页（实测 2026-05-07）；
必须走 playwright + cookies。cookies 主键 BDUSS（在 .baidu.com 域生效）。

cookies 来源：~/.paimon/cookies/tieba.json（playwright storage_state 格式）
首次登录：webui /feed 面板「站点登录」tab 扫码登录百度统一登录页

⚠️ DOM selector 是基于公开知识的初始猜测——首次跑 0 条时会自动 dump 诊断信息
   （body 前 250 字 + 前 15 个 a href），从 dump 里精确改 selector。
"""
from __future__ import annotations

import re
from urllib.parse import quote

import datetime as _dt

from ..core import log
from ..core.dates import in_window
from ..core.schema import Item


# 帖子搜索：必须带 pn=1（缺 pn 会跳推荐首页而不是搜索结果）
_SEARCH_URL = "https://tieba.baidu.com/f/search/res?ie=utf-8&qw={kw}&rn=20&pn=1"
_POST_HREF_RE = re.compile(r"/p/(\d+)")
_PUBLISHED_RE = re.compile(r"发布于\s*([\d]{4}-[\d]{1,2}-[\d]{1,2})")
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _cookies_storage_path() -> str | None:
    """取 <paimon_home>/cookies/tieba.json 路径；不存在返回 None。"""
    from paimon.foundation.site_cookies import cookies_exists, cookies_path
    return str(cookies_path("tieba")) if cookies_exists("tieba") else None


def _parse_count(text: str) -> int:
    """贴吧计数文本 → int：纯数字 / 'N万' / 'N+'。"""
    t = (text or "").strip().replace(",", "")
    if not t:
        return 0
    m = re.match(r"^([0-9.]+)\s*([万Ww]?)\s*\+?$", t)
    if not m:
        try:
            return int(float(t))
        except (ValueError, TypeError):
            return 0
    num = float(m.group(1))
    suffix = m.group(2).lower()
    if suffix in ("万", "w"):
        return int(num * 10000)
    return int(num)


# DOM 提取：基于贴吧 web 实际 DOM 抓（2026-05-07 实测）
# - .threadcardclass = 帖子卡（区别 .forum-wrap 那种"吧聚合卡"，跳过）
# - .title-wrap     = 标题（含 .tb-highlight 高亮 keyword）
# - .attention-wrap = 作者名
# - .thread-forum-name = 吧名（"原神吧"）
# - .top-title 内文匹配 "发布于 YYYY-M-D" → 发布日期
# - .comment-link-zone = 评论数（语义明确，比硬数 .item-warp 排序稳）
_EXTRACT_JS = r"""
() => {
    const out = [];
    const cards = document.querySelectorAll('.threadcardclass');
    const seen = new Set();
    cards.forEach(card => {
        const link = card.querySelector('a[href*="/p/"]');
        if (!link) return;
        const href = link.getAttribute('href') || '';
        if (!href || seen.has(href)) return;
        seen.add(href);

        const titleEl = card.querySelector('.title-wrap, .title-content-wrap');
        const title = (titleEl?.innerText || '').trim();

        const forumEl = card.querySelector('.thread-forum-name .forum-name, .thread-forum-name, .forum-name');
        const forum = (forumEl?.innerText || '').trim();

        const authorEl = card.querySelector('.attention-wrap');
        const author = (authorEl?.innerText || '').trim();

        // 「发布于 2026-5-6」格式日期，从 .top-title innerText 抽
        const topTitleText = (card.querySelector('.top-title')?.innerText || '');
        const dateMatch = topTitleText.match(/发布于\s*([\d]{4}-[\d]{1,2}-[\d]{1,2})/);
        const date_str = dateMatch ? dateMatch[1] : '';

        // 评论数（最稳）
        const commentEl = card.querySelector('.comment-link-zone');
        const reply = (commentEl?.innerText || '').trim();

        out.push({ href, title, forum, author, date_str, reply });
    });
    return out;
}
"""


def _dump_diagnostics(page, log_fn) -> None:
    """0 条候选时 dump page 实际状态，定位是反爬 / cookies 失效 / DOM 结构变。"""
    try:
        title = page.title()
        body_preview = page.evaluate(
            "() => (document.body && document.body.innerText || '').slice(0, 250)"
        )
        href_samples = page.evaluate("""() => {
            const seen = new Set();
            const out = [];
            for (const a of document.querySelectorAll('a[href]')) {
                const h = a.getAttribute('href');
                if (!h || seen.has(h)) continue;
                seen.add(h);
                out.push(h);
                if (out.length >= 15) break;
            }
            return out;
        }""")
        log_fn(f"诊断·title: {title!r}")
        log_fn(f"诊断·body 前 250 字: {body_preview!r}")
        log_fn(f"诊断·a href 前 15 个独特值:")
        for h in (href_samples or []):
            log_fn(f"    {h}")
    except Exception as e:
        log_fn(f"诊断失败: {e}")


def collect(
    topic: str,
    range_from: str,
    range_to: str,
    *,
    limit: int = 20,
) -> list[Item]:
    """贴吧 collector 入口：playwright 跑搜索页拿帖子列表。"""
    cookies_path = _cookies_storage_path()
    if not cookies_path:
        log.source_log("tieba", "无 cookies；请到 webui /feed 面板「站点登录」tab 扫码")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.source_log("tieba", "playwright 未装；pip install -e . 后还需 playwright install chromium")
        return []

    log.source_log("tieba", f"启 headless chromium 跑搜索 topic={topic!r}（首次冷启动 3-5s）")
    items: list[Item] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            try:
                context = browser.new_context(
                    storage_state=cookies_path,
                    viewport={"width": 1280, "height": 900},
                    user_agent=_UA,
                    locale="zh-CN",
                )
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )
                page = context.new_page()
                url = _SEARCH_URL.format(kw=quote(topic))
                page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(4_000)   # 等首屏渲染

                final_url = page.url
                title = page.title()

                # 早退检测：百度安全验证 / cookies 失效
                if "安全验证" in title or "verify" in final_url.lower():
                    log.source_log("tieba", f"被百度安全验证拦截（cookies 失效或反爬触发）：{title}")
                    return []
                if "passport.baidu.com" in final_url:
                    log.source_log("tieba", f"被跳到百度登录页（cookies 失效，请到 webui 重扫）：{final_url[:120]}")
                    return []

                # 贴吧搜索是 Vue 虚拟列表——已滚出视口的 card 会被 detach。
                # 单次 querySelectorAll 只能看到当前视口的 card（3-5 个）。
                # 解决：滚动中**持续累积**——每次滚一段后 extract 一次，按 href 去重攒到 dict。
                collected: dict[str, dict] = {}
                scroll_steps = 6
                for step in range(scroll_steps):
                    batch = page.evaluate(_EXTRACT_JS) or []
                    for d in batch:
                        href = (d.get("href") or "").strip()
                        if href and href not in collected:
                            collected[href] = d
                    # 已经够数就提早退出
                    if len(collected) >= limit * 2:
                        break
                    page.evaluate("() => window.scrollBy(0, window.innerHeight * 0.85)")
                    page.wait_for_timeout(1_500)
                raw = list(collected.values())
                log.source_log("tieba", f"DOM 提取 {len(raw)} 条候选（滚动 {step+1} 轮）(url={final_url[:80]})")

                if not raw:
                    # 0 条候选 → dump 诊断信息（title / body / 前 15 个 a href）
                    _dump_diagnostics(page, lambda msg: log.source_log("tieba", msg))
                    return []

                seen: set[str] = set()
                skipped_window = 0
                for d in raw[:limit * 2]:
                    href = (d.get("href") or "").strip()
                    if not href:
                        continue
                    m = _POST_HREF_RE.search(href)
                    if not m:
                        continue
                    pid = m.group(1)
                    if pid in seen:
                        continue
                    seen.add(pid)
                    # 贴吧 .title-wrap 的 innerText 可能跨行（标题 + 正文摘要拼一起）
                    # 截首行作为标题，其余作为 body
                    raw_title = (d.get("title") or "").strip()
                    if not raw_title:
                        continue
                    lines = [ln.strip() for ln in raw_title.split("\n") if ln.strip()]
                    title_s = lines[0] if lines else raw_title
                    body_s = "\n".join(lines[1:])[:300] if len(lines) > 1 else ""

                    # 解析"2026-5-6" → "2026-05-06"（zfill 月份/日；保证字典序与 range_from/to 兼容）
                    date_str = (d.get("date_str") or "").strip()
                    pub_date = ""
                    if date_str:
                        try:
                            pub_date = _dt.datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y-%m-%d")
                        except ValueError:
                            pub_date = ""

                    # 30 天窗过滤：贴吧帖子日期是真实的，可以用 in_window
                    if pub_date and not in_window(pub_date, range_from, range_to):
                        skipped_window += 1
                        continue

                    items.append(Item(
                        source="tieba",
                        item_id=pid,
                        title=title_s[:200],
                        url=href if href.startswith("http") else f"https://tieba.baidu.com{href}",
                        body=body_s,
                        author=(d.get("author") or "").strip(),
                        published_at=pub_date or range_to,   # 无日期时占位 today（极少见）
                        engagement={"reply": _parse_count(d.get("reply") or "")},
                        metadata={
                            "forum": (d.get("forum") or "").strip(),
                            "date_uncertain": not pub_date,
                        },
                    ))
                    if len(items) >= limit:
                        break
                if skipped_window:
                    log.source_log("tieba", f"跳过 {skipped_window} 个 30 天窗外帖子")
            finally:
                browser.close()
    except Exception as e:
        log.source_log("tieba", f"playwright 异常: {type(e).__name__}: {e}")
        return []

    log.source_log("tieba", f"采集 {len(items)} 条")
    return items
