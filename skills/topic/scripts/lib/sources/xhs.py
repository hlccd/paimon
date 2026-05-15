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

⚠️ 摘要补抓（fetch_detail，默认开）：搜索卡片只有 title/like，没正文。
   补抓阶段对每条 item 串行打开详情页 → 拿 .desc/.note-content 截 200 字填 body。
   代价：N=15 条 × ~3-5s ≈ 45-75s。不愿等可调用方传 fetch_detail=False。
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
    """取 <paimon_home>/cookies/xhs.json 路径；不存在返回 None。"""
    from paimon.foundation.site_cookies import cookies_exists, cookies_path
    return str(cookies_path("xhs")) if cookies_exists("xhs") else None


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


# 详情页正文提取脚本：xhs SSR + SPA 混合，常见正文容器多种命名都试一遍。
# 多 selector fallback 防 hash class 改名；最差返空（保 body="" 跟现状一致）。
_DETAIL_BODY_JS = r"""
() => {
    const candidates = [
        '#detail-desc', '.note-content .desc', '.note-content #detail-desc',
        '.desc', '.note-content', '[class*="note-content"] [class*="desc"]',
        '[class*="desc"]', '[class*="note-content"]',
    ];
    for (const sel of candidates) {
        const el = document.querySelector(sel);
        if (el) {
            const txt = (el.innerText || '').trim();
            // 排除明显非正文（< 10 字 / 是按钮文案）
            if (txt && txt.length >= 10) return txt;
        }
    }
    return '';
}
"""

# 详情页 timeout（每条独立，超时跳过该条不阻塞批次）
_DETAIL_GOTO_TIMEOUT_MS = 10_000
# DOM 渲染等待（SSR 1.5-2s 应该有 .desc）
_DETAIL_WAIT_MS = 2_000
# 单条间隔（模拟人操作，降低风控概率）
_DETAIL_BETWEEN_S = 0.5
# body 截断长度（render._summarize 默认 80~120 字，多截一点给 score 用）
_BODY_MAX_CHARS = 200


def _enrich_body(context, items: list[Item], log_fn) -> None:
    """串行打开每个 item 的详情页拿 body 填回 item.body。

    复用搜索阶段的 browser context（cookies + 反检测脚本就位）。
    单条 try/except + timeout cap：拿不到就保留 body=""，不阻塞批次。
    """
    import time as _t
    ok = 0
    fail = 0
    for it in items:
        if not it.url:
            continue
        page = None
        try:
            page = context.new_page()
            page.goto(it.url, wait_until="domcontentloaded",
                      timeout=_DETAIL_GOTO_TIMEOUT_MS)
            page.wait_for_timeout(_DETAIL_WAIT_MS)
            body_raw = page.evaluate(_DETAIL_BODY_JS) or ""
            body = body_raw.strip()
            if body:
                it.body = body[:_BODY_MAX_CHARS]
                ok += 1
            else:
                fail += 1
        except Exception as e:
            fail += 1
            log_fn(f"详情页拿 body 失败 nid={it.item_id[:12]}: {type(e).__name__}")
        finally:
            if page is not None:
                try: page.close()
                except Exception: pass
        _t.sleep(_DETAIL_BETWEEN_S)
    log_fn(f"摘要补抓完成 ok={ok} fail={fail}")


def collect(
    topic: str,
    range_from: str,
    range_to: str,
    *,
    limit: int = 20,
    fetch_detail: bool = True,
) -> list[Item]:
    """xhs collector 入口：playwright 跑搜索页拿笔记列表。

    无 cookies / playwright 未装 / chromium 未装 / 反爬阻挡 → 返回 [] + 清晰 log。

    fetch_detail=True（默认）：search 拿到 items 后串行打开每个详情页拿正文摘要填
    item.body（耗时 +30~60s）；False 则只拿搜索列表数据，body 保持空。
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

                # 摘要补抓：复用 context 串行 goto 详情页填 body
                # 单条失败不阻塞批次；不愿等的调用方传 fetch_detail=False
                if fetch_detail and items:
                    log.source_log(
                        "xhs",
                        f"开始详情页摘要补抓 N={len(items)}（预计 +{len(items)*4}s）",
                    )
                    _enrich_body(
                        context, items,
                        log_fn=lambda m: log.source_log("xhs", m),
                    )
            finally:
                browser.close()
    except Exception as e:
        log.source_log("xhs", f"playwright 异常: {type(e).__name__}: {e}")
        return []

    log.source_log("xhs", f"采集 {len(items)} 条")
    return items
