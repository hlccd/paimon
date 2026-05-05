"""LLM_BODY chunk · 自动切片，原始字符串拼接还原。"""

LLM_BODY = """
    <div class="container">
        <div class="page-header">
            <div>
                <h1>🧠 模型</h1>
                <div class="sub">管理模型 profile · 配置每个调用点用哪个模型</div>
            </div>
            <div class="header-actions">
                <button class="btn" onclick="refreshActiveTab()">刷新</button>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" data-tab="profiles" onclick="switchTab('profiles', this)">📋 模型管理</button>
            <button class="tab-btn" data-tab="routes" onclick="switchTab('routes', this)">🗺️ 路由配置</button>
        </div>

        <div id="profiles" class="tab-panel active">
            <div style="display:flex;justify-content:flex-end;margin-bottom:16px">
                <button class="btn btn-primary" onclick="openCreate()">+ 新增 Profile</button>
            </div>
            <div id="profileList" class="profile-list">
                <div class="empty-state">加载中...</div>
            </div>
        </div>

        <div id="routes" class="tab-panel">
            <div id="routeDefaultHero" class="default-hero">加载中...</div>
            <div id="routeContainer">
                <div class="empty-state">加载中...</div>
            </div>
        </div>
    </div>

    <div id="modal" class="modal-backdrop" onclick="closeModal(event)">
        <div class="modal" onclick="event.stopPropagation()">
            <div class="modal-header">
                <h3 id="modalTitle">新增 Profile</h3>
                <button class="modal-close" onclick="closeModal()">×</button>
            </div>

            <input type="hidden" id="fld_id" value="" />

            <div class="form-row">
                <label>展示名 <span class="req">*</span></label>
                <input id="fld_name" placeholder="如：DS v4-pro (thinking high)" />
                <div class="hint">UNIQUE；给自己看的。</div>
            </div>

            <div class="form-grid-2">
                <div class="form-row">
                    <label>Provider 类型 <span class="req">*</span></label>
                    <select id="fld_provider_kind">
                        <option value="openai">openai（OpenAI / DeepSeek / mimo / 兼容 API）</option>
                        <option value="anthropic">anthropic（Claude 官方 / 代理）</option>
                    </select>
                </div>
                <div class="form-row">
                    <label>Model ID <span class="req">*</span></label>
                    <input id="fld_model" placeholder="如：deepseek-v4-pro" />
                </div>
            </div>

            <div class="form-row">
                <label>Base URL <span class="req">*</span></label>
                <input id="fld_base_url" placeholder="如：https://api.deepseek.com" />
            </div>

            <div class="form-row">
                <label>API Key <span class="req">*</span></label>
                <input id="fld_api_key" type="password" placeholder="sk-..." />
                <div class="hint">编辑时显示 *** 表示保留原值不动；想改则清空后重新粘贴。</div>
            </div>

            <div class="form-grid-2">
                <div class="form-row">
                    <label>max_tokens</label>
                    <input id="fld_max_tokens" type="number" value="64000" />
                    <div class="hint">仅 anthropic 生效</div>
                </div>
                <div class="form-row">
                    <label>reasoning_effort</label>
                    <select id="fld_reasoning_effort">
                        <option value="">（不设置）</option>
                        <option value="high">high</option>
                        <option value="max">max</option>
                    </select>
                    <div class="hint">仅 openai/deepseek 生效</div>
                </div>
            </div>

            <div class="form-row">
                <label>extra_body (JSON)</label>
                <textarea id="fld_extra_body" placeholder='{"thinking":{"type":"enabled"}}'></textarea>
                <div class="hint">透传给 SDK 的 extra_body；留空即 {}。DeepSeek thinking 模式填 <code>{"thinking":{"type":"enabled"}}</code>。</div>
            </div>

            <div class="form-row">
                <label>备注</label>
                <input id="fld_notes" placeholder="（可选）这条 profile 什么用途" />
            </div>

            <div id="testResult" class="test-result" style="display:none"></div>

            <div class="modal-footer">
                <button class="btn" id="btnTestInModal" onclick="testInModal()">测试连接</button>
                <button class="btn" onclick="closeModal()">取消</button>
                <button class="btn btn-primary" onclick="saveProfile()">保存</button>
            </div>
        </div>
    </div>
"""
