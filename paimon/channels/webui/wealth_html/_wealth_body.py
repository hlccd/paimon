"""WEALTH_BODY chunk · 自动切片，原始字符串拼接还原。"""

WEALTH_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>岩神 · 理财</h1>
                <div class="sub">A 股红利股追踪（评分 + 行业均衡 + 变化检测）</div>
            </div>
            <div class="actions-bar">
                <div class="btn-scan-cell">
                    <button class="btn-scan" id="btnRescore" onclick="triggerScan('rescore')">重评分</button>
                    <span class="btn-scan-hint">&nbsp;</span>
                </div>
                <div class="btn-scan-cell">
                    <button class="btn-scan" id="btnDaily" onclick="triggerScan('daily')">日更</button>
                    <span class="btn-scan-hint" id="dailyHint">候选池 -</span>
                </div>
                <div class="btn-scan-cell">
                    <button class="btn-scan primary" id="btnFull" onclick="triggerScan('full')">全扫描</button>
                    <span class="btn-scan-hint" id="fullHint">全市场 ~5500</span>
                </div>
                <div class="btn-scan-cell">
                    <button class="btn-scan" onclick="refreshAll()">刷新</button>
                    <span class="btn-scan-hint">&nbsp;</span>
                </div>
            </div>
        </div>

        <!-- 大框：head 在最顶（岩神放上面，参考风神形态），日期工具放右边。
             body 双栏：左 = 日报内容（无小 head），右 = 关注股资讯（带 📰 小 head 区分） -->
        <div id="digest" class="digest-section dt-twin">
            <div class="ds-head">
                <h2>📨 岩神 · 理财日报 <span id="zhongliBulletinHint" style="font-size:12px;color:var(--text-muted);font-weight:normal;margin-left:8px"></span></h2>
                <div class="ds-tools">
                    <button onclick="window.zhongliDayShift(-1)" title="前一天">←</button>
                    <input type="date" id="zhongliDateInput" onchange="window.zhongliDateChange()" />
                    <button onclick="window.zhongliDayShift(1)" title="后一天">→</button>
                    <button onclick="window.zhongliJumpToday()" title="跳到今天">今天</button>
                    <button onclick="window.markAllZhongliRead()">全部已读</button>
                </div>
            </div>
            <div class="dt-body">
                <div class="dt-col dt-col-bulletins">
                    <div class="dt-col-scroll">
                        <div id="zhongliRunningBar" style="display:none"></div>
                        <div id="zhongliErrorBar" style="display:none"></div>
                        <div id="zhongliBulletins">
                            <div class="digest-bulletins-empty">加载中...</div>
                        </div>
                        <div class="digest-history-toggle">
                            <button onclick="window.toggleZhongliHistory()" id="zhongliHistoryToggleBtn">
                                🔍 搜索历史 ↓
                            </button>
                        </div>
                        <div id="zhongliHistoryWrap" style="display:none;margin-top:12px">
                            <input id="zhongliDigestSearch" placeholder="搜索历史内容（Enter 应用）"
                                style="width:100%;padding:6px 10px;background:var(--paimon-bg);border:1px solid var(--paimon-border);border-radius:4px;color:var(--text-primary);font-size:12px;margin-bottom:10px" />
                            <div id="zhongliDigestList" class="digest-list">
                                <div class="push-empty">加载中...</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="dt-col dt-col-news">
                    <div class="news-col-head">
                        <span class="ncl-title">📰 关注股资讯</span>
                        <span id="newsPanelHint" class="ncl-hint">加载中</span>
                    </div>
                    <div class="dt-col-scroll">
                        <div id="newsPanelList"><div class="news-section-empty">加载中…</div></div>
                    </div>
                </div>
            </div>
        </div>

        <div class="stats-row">
            <div class="stat-card"><div class="stat-num" id="statWatchlist">-</div><div class="stat-label">推荐股池</div></div>
            <div class="stat-card"><div class="stat-num" id="statLatest">-</div><div class="stat-label">最新扫描</div></div>
            <div class="stat-card"><div class="stat-num" id="statP0P1" style="color:var(--status-warning)">-</div><div class="stat-label">近 7 天 P0+P1</div></div>
            <div class="stat-card"><div class="stat-num" id="statCronStatus">-</div><div class="stat-label">定时任务</div></div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('userWatch',this);loadUserWatchlist();">我的关注</button>
            <button class="tab-btn" onclick="switchTab('recommended',this)">推荐选股</button>
            <button class="tab-btn" onclick="switchTab('ranking',this)">评分排行</button>
            <button class="tab-btn" onclick="switchTab('changes',this)">变化事件</button>
        </div>

        <div id="userWatch" class="tab-panel active">
            <div class="uw-toolbar">
                <input id="uwCodeInput" placeholder="股票代码（如 600519）" maxlength="12" />
                <input id="uwNoteInput" placeholder="备注（可选）" maxlength="50" />
                <label>波动阈值 ±</label>
                <input type="number" id="uwAlertPctInput" value="3.0" step="0.1" min="0.1" max="50" />
                <label>%</label>
                <button class="uw-btn primary" onclick="uwAdd()">添加</button>
                <button class="uw-btn" onclick="uwRefreshAll()" title="立即抓取所有关注股最新数据">立即抓取</button>
                <button class="uw-btn" onclick="loadUserWatchlist()">刷新</button>
            </div>
            <div id="uwListEl"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="recommended" class="tab-panel">
            <div id="recEl"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="ranking" class="tab-panel">
            <div id="rankEl"><div class="empty-state">加载中...</div></div>
        </div>
        <div id="changes" class="tab-panel">
            <div id="chgEl"><div class="empty-state">加载中...</div></div>
        </div>
    </div>

    <div class="modal-backdrop" id="modal" onclick="if(event.target.id==='modal')closeModal()">
        <div class="modal">
            <div class="modal-header">
                <div>
                    <div class="modal-title" id="modalTitle">-</div>
                    <div class="modal-sub" id="modalSub">-</div>
                </div>
                <button class="btn-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="chart-wrap">
                <canvas id="histChart"></canvas>
                <div class="fallback-chart" id="fallbackChart" style="display:none"></div>
            </div>
            <div class="dim-grid" id="dimGrid"></div>
            <table class="raw-table" id="rawTable"></table>
            <div class="advice-box" id="adviceBox"></div>
            <div class="reasons-box" id="reasonsBox"></div>
        </div>
    </div>
"""
