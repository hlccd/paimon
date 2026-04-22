#!/usr/bin/env python3
"""
check skill 内部链接校验脚本

扫描 Markdown 文件中的行内链接 [text](url)，校验：
- 内部文件链接：目标文件是否存在
- 锚点链接：目标标题是否存在（支持 ATX 和 Setext 风格）
- 外部 URL：仅标记，不发起网络请求

限制：不检查引用式链接 [text][ref] / [ref]: url。

输出 JSON 对象供 Agent 消费（含 issues 和 external_links 数组）。

用法：
    python link-checker.py <docs-dir> [--base-dir <base>]

    --base-dir: 解析相对路径时的基准目录，默认与 docs-dir 相同
"""

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path


LINK_PATTERN = re.compile(
    r'\[([^\]]*)\]'
    r'\('
    r'(?:<([^>]*)>|'
    r'([^)\s]*(?:\([^)]*\)[^)\s]*)*))'
    r'(?:\s+"[^"]*")?'
    r'\)'
)

HEADING_PATTERN = re.compile(r'^#{1,6}\s+(.+)$', re.MULTILINE)
SETEXT_UNDERLINE = re.compile(r'^(?:={3,}|-{3,})\s*$')
FENCE_PATTERN = re.compile(r'^(\t| {0,3})(`{3,}|~{3,})')
INLINE_CODE_RE = re.compile(r'`[^`]+`')
HTML_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
URI_SCHEME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.-]*:')

_RE_HTML_TAG = re.compile(r'<[^>]+>')
_RE_BACKTICK = re.compile(r'`([^`]*)`')
_RE_BOLD_ITALIC = re.compile(r'[*_]+')
_RE_ATX_CLOSE = re.compile(r'\s+#+\s*$')
_RE_NON_SLUG = re.compile(r'[^\w\u2e80-\u9fff\uf900-\ufaff -]')
_RE_WHITESPACE = re.compile(r'[\s]+')

_heading_cache: dict[Path, set[str]] = {}

EXCLUDE_DIRS = {'.git', '.hg', '.svn', 'node_modules', '__pycache__', '.check'}


def slugify_heading(heading: str) -> str:
    """将 Markdown 标题转为锚点 slug（GitHub 风格）。"""
    text = heading.strip()
    text = _RE_ATX_CLOSE.sub('', text)
    text = _RE_HTML_TAG.sub('', text)
    text = _RE_BACKTICK.sub(r'\1', text)
    text = _RE_BOLD_ITALIC.sub('', text)
    text = text.lower()
    text = _RE_NON_SLUG.sub('', text)
    text = _RE_WHITESPACE.sub('-', text)
    text = text.strip('-')
    return text


def is_fence_toggle(line: str, fence_state: dict) -> bool:
    """检测围栏代码块的开启/关闭。修改 fence_state in-place。
    返回 True 表示该行是围栏标记或在围栏内。"""
    m = FENCE_PATTERN.match(line)
    if m:
        char = m.group(2)[0]
        length = len(m.group(2))
        if fence_state['char'] is None:
            fence_state['char'] = char
            fence_state['len'] = length
        elif char == fence_state['char'] and length >= fence_state['len']:
            fence_state['char'] = None
            fence_state['len'] = 0
        return True
    return fence_state['char'] is not None


def strip_fenced_blocks(content: str) -> str:
    """移除围栏代码块内的内容，保留行号对齐的空行。"""
    lines = content.splitlines(keepends=True)
    result = []
    fence_state = {'char': None, 'len': 0}
    for line in lines:
        if is_fence_toggle(line, fence_state):
            result.append('\n')
        else:
            result.append(line)
    return ''.join(result)


def extract_headings(content: str) -> set[str]:
    """从 Markdown 内容中提取所有标题的 slug（ATX + Setext），排除围栏代码块。"""
    filtered = strip_fenced_blocks(content)
    slugs = set()
    slug_counts: dict[str, int] = {}

    def _add_slug(text: str):
        base_slug = slugify_heading(text)
        if not base_slug:
            return
        if base_slug in slug_counts:
            slug_counts[base_slug] += 1
            slugs.add(f"{base_slug}-{slug_counts[base_slug]}")
        else:
            slug_counts[base_slug] = 0
            slugs.add(base_slug)

    for match in HEADING_PATTERN.finditer(filtered):
        _add_slug(match.group(1))

    lines = filtered.splitlines()
    for i in range(len(lines) - 1):
        if lines[i].strip() and SETEXT_UNDERLINE.match(lines[i + 1]):
            _add_slug(lines[i].strip())

    return slugs


def get_headings(file_path: Path) -> set[str]:
    """带缓存的标题提取。"""
    resolved = file_path.resolve()
    if resolved not in _heading_cache:
        try:
            content = resolved.read_text(encoding='utf-8-sig')
            content_clean = HTML_COMMENT_RE.sub(lambda m: '\n' * m.group(0).count('\n'), content)
            _heading_cache[resolved] = extract_headings(content_clean)
        except (OSError, UnicodeDecodeError):
            _heading_cache[resolved] = set()
    return _heading_cache[resolved]


def _make_finding(file_path: Path, line_num: int, link_text: str,
                   link_target: str, issue: str, issue_type: str) -> dict:
    return {
        'file': str(file_path),
        'line': line_num,
        'link_text': link_text,
        'link_target': link_target,
        'issue': issue,
        'type': issue_type,
    }


def _resolve_link_target(path_part: str, file_path: Path, base_dir: Path) -> Path:
    if path_part.startswith('/'):
        return (base_dir / path_part.lstrip('/')).resolve()
    return (file_path.parent / path_part).resolve()


def _check_anchor(anchor_part: str, target_path: Path, headings: set[str],
                   file_path: Path, line_num: int, link_text: str,
                   link_target: str, is_self: bool) -> dict | None:
    if anchor_part is None:
        return None
    if anchor_part == '':
        if target_path.suffix in ('.md', '.markdown'):
            return _make_finding(file_path, line_num, link_text, link_target,
                                 f'尾随空锚点 {link_target}，可能为损坏链接', 'WARNING')
        return None
    anchor_slug = slugify_heading(urllib.parse.unquote(anchor_part))
    if not anchor_slug:
        return None
    if anchor_slug not in headings:
        where = '当前文件' if is_self else '目标文件'
        return _make_finding(file_path, line_num, link_text, link_target,
                             f'锚点 "#{anchor_part}" 在{where}中未找到匹配标题',
                             'BROKEN_ANCHOR')
    return None


def check_file(file_path: Path, base_dir: Path) -> list[dict]:
    """校验单个文件中的所有链接。"""
    findings = []
    try:
        content = file_path.read_text(encoding='utf-8-sig')
    except (OSError, UnicodeDecodeError) as e:
        return [_make_finding(file_path, 0, '', '', f'无法读取文件: {e}', 'ERROR')]

    content_no_comments = HTML_COMMENT_RE.sub(lambda m: '\n' * m.group(0).count('\n'), content)
    self_headings = extract_headings(content_no_comments)
    resolved_self = file_path.resolve()
    if resolved_self not in _heading_cache:
        _heading_cache[resolved_self] = self_headings
    fence_state = {'char': None, 'len': 0}

    for line_num, line in enumerate(content_no_comments.splitlines(), start=1):
        if is_fence_toggle(line, fence_state):
            continue

        scan_line = INLINE_CODE_RE.sub('', line)

        for match in LINK_PATTERN.finditer(scan_line):
            link_text = match.group(1)
            link_target = match.group(2) or match.group(3)
            if not link_target:
                continue

            if URI_SCHEME_RE.match(link_target):
                findings.append(_make_finding(file_path, line_num, link_text,
                                              link_target, '外部链接（未校验）', 'EXTERNAL'))
                continue

            path_part, anchor_part = (link_target.split('#', 1) if '#' in link_target
                                      else (link_target, None))
            path_part = urllib.parse.unquote(path_part)
            if '?' in path_part:
                path_part = path_part.split('?', 1)[0]

            if not path_part:
                if anchor_part:
                    finding = _check_anchor(anchor_part, file_path, self_headings,
                                            file_path, line_num, link_text, link_target, True)
                    if finding:
                        findings.append(finding)
                elif link_target == '#':
                    findings.append(_make_finding(file_path, line_num, link_text,
                                                  link_target, '空锚点链接 [text](#)，可能为损坏链接', 'WARNING'))
                continue

            target_path = _resolve_link_target(path_part, file_path, base_dir)

            if not target_path.is_relative_to(base_dir):
                findings.append(_make_finding(file_path, line_num, link_text,
                                              link_target, '链接目标超出基准目录范围', 'SECURITY'))
                continue

            if not target_path.exists() or target_path.is_dir():
                issue_msg = (f'目标是目录而非文件: {target_path}' if target_path.exists()
                             else f'目标文件不存在: {target_path}')
                findings.append(_make_finding(file_path, line_num, link_text,
                                              link_target, issue_msg, 'BROKEN_LINK'))
                continue

            if anchor_part is not None and target_path.suffix in ('.md', '.markdown'):
                target_headings = get_headings(target_path) if anchor_part else set()
                finding = _check_anchor(anchor_part, target_path, target_headings,
                                        file_path, line_num, link_text, link_target, False)
                if finding:
                    findings.append(finding)

    return findings


def main():
    parser = argparse.ArgumentParser(description='Markdown 内部链接校验')
    parser.add_argument('docs_dir', help='文档目录路径')
    parser.add_argument('--base-dir', default=None, help='相对路径基准目录（默认同 docs_dir）')
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir).resolve()
    base_dir = Path(args.base_dir).resolve() if args.base_dir else docs_dir

    if not docs_dir.is_dir():
        print(json.dumps({
            'total_issues': 1,
            'total_external_links': 0,
            'issues': [{
                'file': str(docs_dir),
                'line': 0,
                'link_text': '',
                'link_target': '',
                'issue': f'目录不存在: {docs_dir}',
                'type': 'ERROR',
            }],
            'external_links': [],
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    if args.base_dir and not base_dir.is_dir():
        print(json.dumps({
            'total_issues': 1,
            'total_external_links': 0,
            'issues': [{
                'file': str(base_dir),
                'line': 0,
                'link_text': '',
                'link_target': '',
                'issue': f'基准目录不存在: {base_dir}',
                'type': 'ERROR',
            }],
            'external_links': [],
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    try:
        all_findings = []
        md_files = []
        for md_file in docs_dir.rglob('*.md'):
            try:
                rel_parts = md_file.relative_to(docs_dir).parts[:-1]
            except ValueError:
                continue
            if any(part in EXCLUDE_DIRS or part.startswith('.') for part in rel_parts):
                continue
            if md_file.is_symlink():
                continue
            md_files.append(md_file)
        for md_file in sorted(md_files):
            all_findings.extend(check_file(md_file, base_dir))

        issues = [f for f in all_findings if f['type'] != 'EXTERNAL']
        externals = [f for f in all_findings if f['type'] == 'EXTERNAL']

        output = {
            'total_issues': len(issues),
            'total_external_links': len(externals),
            'issues': issues,
            'external_links': externals,
        }

        print(json.dumps(output, ensure_ascii=False, indent=2))
        sys.exit(1 if issues else 0)
    except Exception as e:
        print(json.dumps({
            'total_issues': 1,
            'total_external_links': 0,
            'issues': [{'file': str(docs_dir), 'line': 0, 'link_text': '',
                        'link_target': '', 'issue': f'内部错误: {e}', 'type': 'ERROR'}],
            'external_links': [],
        }, ensure_ascii=False, indent=2))
        sys.exit(2)


if __name__ == '__main__':
    main()
