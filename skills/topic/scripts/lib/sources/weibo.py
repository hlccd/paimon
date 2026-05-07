"""微博 collector：playwright headless + cookies + 解析 s.weibo.com 搜索页 DOM。

匿名访问 s.weibo.com 大概率被风控限流；带登录 cookies 才稳定（实测后再回填具体表现）。
cookies 主键 SUB（在 .weibo.com 域生效）；首次登录走 webui /feed「站点登录」tab 扫码。

⚠️ DOM selector 是基于公开知识的初始猜测——首次跑 0 条时会自动 dump 诊断信息
   （title / body 前 250 字 / 前 15 个 a href），从 dump 里精确改 selector。
"""
from __future__ import annotations

import datetime as _dt
import re
from urllib.parse import quote

from ..core import log
from ..core.dates import in_window
from ..core.schema import Item


_SEARCH_URL = "https://s.weibo.com/weibo?q={kw}"
# 微博单条 URL 形如 /u/<uid>/<wid> 或 /<uid>/<wid> 或带 mid 参数；wid 是 base62 编码字符串
_POST_HREF_RE = re.compile(r"/(?:[a-zA-Z0-9_]+/)?([a-zA-Z0-9]{8,})\?")
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _cookies_storage_path() -> str | None:
    from paimon.foundation.site_cookies import cookies_exists, cookies_path
    return str(cookies_path("weibo")) if cookies_exists("weibo") else None


def _parse_count(text: str) -> int:
    """微博计数文本 → int：纯数字 / 'N万' / '1.2 万'。"""
    t = (text or "").strip().replace(",", "").replace(" ", "")
    if not t:
        return 0
    # 微博按钮文本经常是"转发 N" / "评论 N" / "赞 N"，先提数字部分
    m = re.search(r"([0-9.]+)\s*([万Ww]?)", t)
    if not m:
        return 0
    try:
        num = float(m.group(1))
    except ValueError:
        return 0
    suffix = m.group(2).lower()
    if suffix in ("万", "w"):
        return int(num * 10000)
    return int(num)


def _parse_weibo_date(raw: str, today: _dt.date) -> str | None:
    """微博时间格式多样，归一化到 YYYY-MM-DD：
    - 'X分钟前' / 'X小时前'        → today
    - '今天 HH:MM'                  → today
    - 'M月D日 HH:MM'                → 当年 M-D（zfill）
    - 'YYYY年M月D日 HH:MM'          → YYYY-M-D（zfill）
    无法解析返回 None。
    """
    if not raw:
        return None
    s = raw.strip()
    if "分钟前" in s or "小时前" in s or "刚刚" in s or s.startswith("今天"):
        return today.isoformat()
    # YYYY年M月D日
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    # M月D日（缺年份，假设当年；跨年场景小，可接受）
    m = re.match(r"(\d{1,2})月(\d{1,2})日", s)
    if m:
        try:
            return _dt.date(today.year, int(m.group(1)), int(m.group(2))).isoformat()
        except ValueError:
            return None
    return None


# DOM 提取：基于公开知识的初始猜测；0 条时会自动 dump 诊断
# 微博搜索结果常见结构（s.weibo.com）：
#   #pl_feedlist_index 容器
#     .card-wrap (单条)
#       .card-feed
#         .content .txt   → 正文（可能多个 .txt，full vs short）
#         .content .info .name → 用户名
#         .content .from a:first-child → 微博 URL + 时间
#         .card-act li (3 个，分别 转发 / 评论 / 赞)
_EXTRACT_JS = r"""
() => {
    const out = [];
    const cards = document.querySelectorAll(
        '.card-wrap, [class*="card-feed"], [action-type="feed_list_item"]'
    );
    const seen = new Set();
    cards.forEach(card => {
        // 过滤掉非微博条目（如"用户卡片"、"话题卡片"、"广告"等）
        const feed = card.querySelector('.card-feed, [class*="card-feed"]');
        if (!feed) return;
        // 微博 URL：.from > a 的 href（含微博 mid）
        const fromLink = feed.querySelector('.from a[href*="/"], .info a[href*="/"]');
        const href = fromLink?.getAttribute('href') || '';
        if (!href || seen.has(href)) return;
        seen.add(href);

        // 正文：取最长的 .txt（短/长版本时长版优先）
        const txts = [...feed.querySelectorAll('.txt, [class*="txt"]')];
        let title = '';
        for (const t of txts) {
            const v = (t.innerText || '').trim();
            if (v.length > title.length) title = v;
        }

        // 用户
        const userEl = feed.querySelector('.name, .info .name, [class*="user-name"]');
        const author = (userEl?.innerText || '').trim();

        // 时间（.from 第一个 a 的 text，常含"X分钟前"/"M月D日"/etc）
        const time_str = (fromLink?.innerText || '').trim();

        // 转发 / 评论 / 赞：.card-act 的 3 个 li
        const acts = [...card.querySelectorAll('.card-act li, [class*="card-act"] li')];
        const repost = (acts[0]?.innerText || '').trim();
        const comment = (acts[1]?.innerText || '').trim();
        const like = (acts[2]?.innerText || '').trim();

        out.push({ href, title, author, time_str, repost, comment, like });
    });
    return out;
}
"""


def _dump_diagnostics(page, log_fn) -> None:
    """0 条候选时 dump page 状态——仿 tieba 同款诊断。"""
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
    """微博 collector 入口：playwright 跑 s.weibo.com 搜索拿微博列表。"""
    cookies_path = _cookies_storage_path()
    if not cookies_path:
        log.source_log("weibo", "无 cookies；请到 webui /feed 面板「站点登录」tab 扫码")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.source_log("weibo", "playwright 未装；pip install -e . 后还需 playwright install chromium")
        return []

    log.source_log("weibo", f"启 headless chromium 跑搜索 topic={topic!r}（首次冷启动 3-5s）")
    items: list[Item] = []
    today = _dt.date.fromisoformat(range_to)
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
                page.wait_for_timeout(4_000)

                final_url = page.url
                # 早退检测：cookies 失效跳登录页 / 风控验证页
                if "passport.weibo.com" in final_url or "login" in final_url.lower():
                    log.source_log("weibo", f"被跳到登录页（cookies 失效，请回 webui 扫码）：{final_url[:120]}")
                    return []
                if "visitor" in final_url.lower():
                    log.source_log("weibo", f"被跳到游客页（cookies 不够）：{final_url[:120]}")
                    return []

                # 滚动累积（微博搜索是 SSR 但有懒加载，滚一下让更多 card 渲染）
                collected: dict[str, dict] = {}
                for step in range(5):
                    batch = page.evaluate(_EXTRACT_JS) or []
                    for d in batch:
                        href = (d.get("href") or "").strip()
                        if href and href not in collected:
                            collected[href] = d
                    if len(collected) >= limit * 2:
                        break
                    page.evaluate("() => window.scrollBy(0, window.innerHeight * 0.85)")
                    page.wait_for_timeout(1_500)
                raw = list(collected.values())
                log.source_log("weibo", f"DOM 提取 {len(raw)} 条候选（滚动 {step+1} 轮）(url={final_url[:80]})")

                if not raw:
                    _dump_diagnostics(page, lambda msg: log.source_log("weibo", msg))
                    return []

                seen: set[str] = set()
                skipped_window = 0
                for d in raw[:limit * 2]:
                    href = (d.get("href") or "").strip()
                    if not href:
                        continue
                    # 标准化 URL
                    if href.startswith("//"):
                        href = "https:" + href
                    elif href.startswith("/"):
                        href = f"https://weibo.com{href}"
                    # 提 mid 作为 item_id（href 末段的 base62）
                    m = _POST_HREF_RE.search(href)
                    mid = m.group(1) if m else href.rstrip("/").rsplit("/", 1)[-1].split("?")[0][:32]
                    if not mid or mid in seen:
                        continue
                    seen.add(mid)

                    title_s = (d.get("title") or "").strip()
                    if not title_s:
                        continue
                    # 截首行作标题，其余作 body（微博正文常多段）
                    lines = [ln.strip() for ln in title_s.split("\n") if ln.strip()]
                    title_one = lines[0] if lines else title_s
                    body_s = "\n".join(lines[1:])[:300] if len(lines) > 1 else ""

                    # 解析日期 → 30 天窗过滤
                    pub_date = _parse_weibo_date(d.get("time_str") or "", today)
                    if pub_date and not in_window(pub_date, range_from, range_to):
                        skipped_window += 1
                        continue

                    items.append(Item(
                        source="weibo",
                        item_id=mid,
                        title=title_one[:200],
                        url=href,
                        body=body_s,
                        author=(d.get("author") or "").strip(),
                        published_at=pub_date or range_to,
                        engagement={
                            "repost": _parse_count(d.get("repost") or ""),
                            "comment": _parse_count(d.get("comment") or ""),
                            "like": _parse_count(d.get("like") or ""),
                        },
                        metadata={
                            "raw_time": (d.get("time_str") or "").strip(),
                            "date_uncertain": not pub_date,
                        },
                    ))
                    if len(items) >= limit:
                        break
                if skipped_window:
                    log.source_log("weibo", f"跳过 {skipped_window} 个 30 天窗外微博")
            finally:
                browser.close()
    except Exception as e:
        log.source_log("weibo", f"playwright 异常: {type(e).__name__}: {e}")
        return []

    log.source_log("weibo", f"采集 {len(items)} 条")
    return items
