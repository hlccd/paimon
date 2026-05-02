"""SENTIMENT_BODY chunk · 自动切片，原始字符串拼接还原。"""

SENTIMENT_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>🌬️ 风神·舆情看板</h1>
                <div class="sub">事件级聚合 / 严重度分级 / 跨批次合并</div>
            </div>
            <div class="header-actions">
                <button class="btn" onclick="loadAll()">刷新</button>
                <a href="/feed" class="btn" style="text-decoration:none">信息流原始流</a>
            </div>
        </div>

        <div id="digest" class="digest-section" style="margin-top:0">
            <div class="ds-head">
                <h2>📨 风神 · 日报公告 <span id="ventiBulletinHint" style="font-size:12px;color:var(--text-muted);font-weight:normal;margin-left:8px"></span></h2>
                <div class="ds-tools">
                    <button onclick="window.ventiDayShift(-1)" title="前一天">←</button>
                    <input type="date" id="ventiDateInput" onchange="window.ventiDateChange()" />
                    <button onclick="window.ventiDayShift(1)" title="后一天">→</button>
                    <button onclick="window.ventiJumpToday()" title="跳到今天">今天</button>
                    <button onclick="window.markAllVentiRead()">全部已读</button>
                </div>
            </div>
            <div class="digest-scroll">
                <div id="ventiRunningBar" style="display:none"></div>
                <div id="ventiBulletins">
                    <div class="digest-bulletins-empty">加载中...</div>
                </div>
                <div class="digest-history-toggle">
                    <button onclick="window.toggleVentiHistory()" id="ventiHistoryToggleBtn">
                        🔍 搜索历史 ↓
                    </button>
                </div>
                <div id="ventiHistoryWrap" style="display:none;margin-top:12px">
                    <input id="ventiDigestSearch" placeholder="搜索历史内容（Enter 应用）"
                        style="width:100%;padding:6px 10px;background:var(--paimon-bg);border:1px solid var(--paimon-border);border-radius:4px;color:var(--text-primary);font-size:12px;margin-bottom:10px" />
                    <div id="ventiDigestList" class="digest-list">
                        <div class="push-empty">加载中...</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="stats-row" id="statsRow">
            <div class="stat-card"><div class="stat-num" id="stEvents">-</div><div class="stat-label">7 天事件数</div></div>
            <div class="stat-card"><div class="stat-num warning" id="stP01">-</div><div class="stat-label">P0+P1 数</div></div>
            <div class="stat-card"><div class="stat-num" id="stSent">-</div><div class="stat-label">整体情感</div></div>
            <div class="stat-card"><div class="stat-num" id="stSubs">-</div><div class="stat-label">活跃订阅</div></div>
        </div>

        <div class="main-grid">
            <div class="panel">
                <div class="panel-head">
                    <h2>事件时间线</h2>
                    <div class="panel-tools">
                        <select id="filterDays" onchange="loadEvents()">
                            <option value="7" selected>近 7 天</option>
                            <option value="14">近 14 天</option>
                            <option value="30">近 30 天</option>
                        </select>
                        <select id="filterSeverity" onchange="loadEvents()">
                            <option value="">所有严重度</option>
                            <option value="p0">仅 P0</option>
                            <option value="p1">仅 P1</option>
                            <option value="p2">仅 P2</option>
                            <option value="p3">仅 P3</option>
                        </select>
                        <select id="filterSub" onchange="onSubFilterChange()">
                            <option value="">所有订阅</option>
                        </select>
                    </div>
                </div>
                <div id="subBanner" class="sub-banner"></div>
                <div class="events-list" id="eventsList">
                    <div class="empty-state">加载中...</div>
                </div>
            </div>

            <div class="right-col">
                <div class="panel">
                    <div class="panel-head"><h2>情感折线 · 近 14 天</h2></div>
                    <canvas id="sentimentChart"></canvas>
                </div>
                <div class="panel">
                    <div class="panel-head"><h2>严重度矩阵 · 近 7 天</h2></div>
                    <div class="matrix-grid" id="matrixGrid">
                        <div class="empty-state" style="grid-column:1/9">加载中...</div>
                    </div>
                </div>
                <div class="panel">
                    <div class="panel-head"><h2>信源 Top · 近 7 天</h2></div>
                    <div class="sources-list" id="sourcesList">
                        <div class="empty-state">加载中...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="modal-mask" id="modal">
        <div class="modal">
            <div class="modal-head">
                <h3 id="modalTitle">事件详情</h3>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body" id="modalBody"></div>
        </div>
    </div>
"""
