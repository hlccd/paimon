/* Paimon 通用控件 JS — 配合 components.css 使用
 * 暴露全局: pmBtn / pmToast / pmModal / pmTab / pmDialog
 */
(function () {
  /* ═════ pmBtn ═════════════════════════════════════
   * 异步按钮 helper — 解决全项目 76+ 处 disable+changeText 重复
   *
   * 用法：
   *   await pmBtn.runAsync(btn, async () => {
   *     const r = await fetch('/api/foo', { method: 'POST' });
   *     return r.json();
   *   }, { loadingText: '处理中…' });
   */
  const pmBtn = {
    async runAsync(btn, fn, opts = {}) {
      const {
        loadingText = '处理中…',
        successText,
        successDelay = 800,
        suppressErrorToast = false,
      } = opts;

      const labelEl = btn.querySelector('.pm-btn__label');
      const iconEl  = btn.querySelector('.pm-btn__icon');
      const originalLabel = labelEl ? labelEl.textContent : '';
      const originalIcon  = iconEl  ? iconEl.innerHTML : '';

      btn.disabled = true;
      btn.dataset.state = 'loading';
      btn.setAttribute('aria-busy', 'true');
      if (labelEl && loadingText) labelEl.textContent = loadingText;
      if (iconEl) iconEl.innerHTML = window.pmIcon ? window.pmIcon('loader-2') : '';

      try {
        const result = await fn();
        if (successText && labelEl) {
          labelEl.textContent = successText;
          if (iconEl) iconEl.innerHTML = window.pmIcon ? window.pmIcon('check') : '';
          await new Promise(r => setTimeout(r, successDelay));
        }
        return result;
      } catch (err) {
        if (!suppressErrorToast) {
          window.pmToast && window.pmToast.error(err.message || '操作失败', { title: '错误' });
        }
        throw err;
      } finally {
        btn.disabled = false;
        btn.dataset.state = '';
        btn.removeAttribute('aria-busy');
        if (labelEl) labelEl.textContent = originalLabel;
        if (iconEl)  iconEl.innerHTML  = originalIcon;
      }
    },
  };

  /* ═════ pmToast ═════════════════════════════════════
   * 轻量 toast 通知 — 替代 alert()
   *
   * 用法: pmToast.success('已保存')
   *       pmToast.error('请求失败', { title: '错误', duration: 5000 })
   */
  const TOAST_CONTAINER_ID = 'pm-toast-container';

  function ensureContainer() {
    let c = document.getElementById(TOAST_CONTAINER_ID);
    if (!c) {
      c = document.createElement('div');
      c.id = TOAST_CONTAINER_ID;
      c.className = 'pm-toast-container';
      document.body.appendChild(c);
    }
    return c;
  }

  function showToast(variant, msg, opts = {}) {
    const { title, duration = 3500 } = opts;
    const c = ensureContainer();
    const el = document.createElement('div');
    el.className = 'pm-toast pm-toast--' + variant;
    el.setAttribute('role', variant === 'danger' ? 'alert' : 'status');

    const iconName = {
      success: 'check-circle-2',
      danger:  'alert-circle',
      warning: 'alert-triangle',
      info:    'info',
    }[variant] || 'info';

    const iconHtml = window.pmIcon ? window.pmIcon(iconName) : '';
    el.innerHTML =
      '<span class="pm-toast__icon">' + iconHtml + '</span>' +
      '<div class="pm-toast__body">' +
        (title ? '<div class="pm-toast__title">' + escapeHtml(title) + '</div>' : '') +
        '<div class="pm-toast__msg">' + escapeHtml(msg) + '</div>' +
      '</div>';

    c.appendChild(el);

    const timer = setTimeout(() => dismiss(), duration);
    function dismiss() {
      el.classList.add('pm-toast--leaving');
      el.addEventListener('animationend', () => el.remove(), { once: true });
      clearTimeout(timer);
    }
    el.addEventListener('click', dismiss);
    return { dismiss };
  }

  const pmToast = {
    success: (msg, opts) => showToast('success', msg, opts),
    error:   (msg, opts) => showToast('danger', msg, opts),
    danger:  (msg, opts) => showToast('danger', msg, opts),
    warning: (msg, opts) => showToast('warning', msg, opts),
    info:    (msg, opts) => showToast('info', msg, opts),
  };

  /* ═════ pmModal ═════════════════════════════════════
   * 基于原生 <dialog> — 自带 focus trap、ESC 关闭、a11y
   *
   * 用法: pmModal.open('myModalId') / pmModal.close('myModalId')
   *       pmModal.confirm({ title: '确认删除？', danger: true })
   */
  const pmModal = {
    open(idOrEl) {
      const el = typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl;
      if (!el || el.tagName !== 'DIALOG') return null;
      if (typeof el.showModal === 'function') el.showModal();
      else el.setAttribute('open', '');
      return el;
    },
    close(idOrEl) {
      const el = typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl;
      if (!el) return;
      if (typeof el.close === 'function') el.close();
      else el.removeAttribute('open');
    },
    /** 通用确认框 — 返回 Promise<boolean> */
    confirm(opts = {}) {
      const {
        title = '确认',
        message = '',
        confirmText = '确认',
        cancelText = '取消',
        danger = false,
      } = opts;
      return new Promise((resolve) => {
        const dlg = document.createElement('dialog');
        dlg.className = 'pm-modal';
        dlg.innerHTML =
          '<div class="pm-modal__header">' +
            '<h3 class="pm-modal__title">' + escapeHtml(title) + '</h3>' +
          '</div>' +
          '<div class="pm-modal__body">' + escapeHtml(message) + '</div>' +
          '<div class="pm-modal__footer">' +
            '<button class="pm-btn pm-btn--default" data-act="cancel">' +
              '<span class="pm-btn__label">' + escapeHtml(cancelText) + '</span></button>' +
            '<button class="pm-btn pm-btn--' + (danger ? 'danger' : 'primary') + '" data-act="ok">' +
              '<span class="pm-btn__label">' + escapeHtml(confirmText) + '</span></button>' +
          '</div>';
        document.body.appendChild(dlg);
        dlg.querySelector('[data-act=ok]').addEventListener('click', () => {
          dlg.close(); cleanup(); resolve(true);
        });
        dlg.querySelector('[data-act=cancel]').addEventListener('click', () => {
          dlg.close(); cleanup(); resolve(false);
        });
        dlg.addEventListener('cancel', () => { cleanup(); resolve(false); });
        function cleanup() { setTimeout(() => dlg.remove(), 200); }
        dlg.showModal();
      });
    },
  };

  /* ═════ pmTab ═════════════════════════════════════
   * Tab 切换 — 基于 ARIA + data-* 配置
   *
   * HTML: <div class="pm-tabs" role="tablist">
   *         <button class="pm-tab" role="tab" data-target="panel-1" aria-selected="true">
   *         <button class="pm-tab" role="tab" data-target="panel-2">
   *       </div>
   *       <div id="panel-1" role="tabpanel">...</div>
   *       <div id="panel-2" role="tabpanel" hidden>...</div>
   */
  const pmTab = {
    enhance(tablist) {
      const tabs = tablist.querySelectorAll('.pm-tab');
      tabs.forEach((tab) => {
        tab.addEventListener('click', () => pmTab.activate(tab));
        tab.addEventListener('keydown', (e) => {
          const list = Array.from(tabs);
          const i = list.indexOf(tab);
          let next;
          if (e.key === 'ArrowRight') next = list[(i + 1) % list.length];
          else if (e.key === 'ArrowLeft') next = list[(i - 1 + list.length) % list.length];
          if (next) { e.preventDefault(); pmTab.activate(next); next.focus(); }
        });
      });
    },
    activate(tab) {
      const tablist = tab.closest('.pm-tabs');
      if (!tablist) return;
      tablist.querySelectorAll('.pm-tab').forEach((t) => {
        const isThis = t === tab;
        t.setAttribute('aria-selected', isThis);
        t.classList.toggle('is-active', isThis);
        t.tabIndex = isThis ? 0 : -1;
        const target = document.getElementById(t.dataset.target);
        if (target) target.hidden = !isThis;
      });
      tab.dispatchEvent(new CustomEvent('pm-tab:change', { bubbles: true, detail: { tab } }));
    },
    enhanceAll(root = document) {
      root.querySelectorAll('.pm-tabs').forEach(pmTab.enhance);
    },
  };

  /* ═════ utils ═════════════════════════════════════ */
  function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /* ═════ safeMd ═════════════════════════════════════
   * marked.parse 包装：缺 marked 时退回 escape <pre>，外链强制 target=_blank rel=noopener
   * chat / feed / knowledge 等共用；page handler 需自行注入 marked.min.js
   */
  function safeMd(md) {
    const src = md == null ? '' : String(md);
    if (typeof window.marked === 'undefined' || !window.marked.parse) {
      return '<pre>' + escapeHtml(src) + '</pre>';
    }
    let raw;
    try {
      raw = window.marked.parse(src);
    } catch (e) {
      return '<pre>' + escapeHtml(src) + '</pre>';
    }
    const div = document.createElement('div');
    div.innerHTML = raw;
    div.querySelectorAll('a[href]').forEach((a) => {
      const href = a.getAttribute('href') || '';
      if (/^https?:\/\//i.test(href)) {
        a.setAttribute('target', '_blank');
        a.setAttribute('rel', 'noopener noreferrer');
      }
    });
    return div.innerHTML;
  }

  /* 暴露到全局 */
  window.pmBtn = pmBtn;
  window.pmToast = pmToast;
  window.pmModal = pmModal;
  window.pmTab = pmTab;
  window.safeMd = safeMd;

  document.addEventListener('DOMContentLoaded', () => {
    pmTab.enhanceAll();
  });
})();
