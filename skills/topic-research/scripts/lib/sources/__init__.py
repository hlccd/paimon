"""数据源 collector 集合。

每个简单 source 一个文件（如 bili.py / github.py / zhihu.py / tieba.py）；
未来复杂 source（需要 cookies + 多步 enrich，如 xhs / weibo）会拆成子目录：
    sources/xhs/
        __init__.py    # 暴露 collect()
        _cookies.py
        _search.py
        _note.py

每个 collector 必须暴露统一签名：
    def collect(topic: str, range_from: str, range_to: str, *, limit: int) -> list[Item]
"""
