(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const ROLE_DATA = {
    editor: { label: 'リサーチャー', name: '佐藤 美咲', initials: 'MS', email: 'editor@rihrp.example' },
    reviewer: { label: 'レビュアー', name: '田中 健', initials: 'TK', email: 'reviewer@rihrp.example' },
    admin: { label: '管理者', name: '山本 修', initials: 'YS', email: 'admin@rihrp.example' }
  };

  const STATUS = {
    verified: { label: '検証済み', icon: 'i-check-circle' },
    unverified: { label: '未検証', icon: 'i-clock' },
    contradicted: { label: '矛盾', icon: 'i-x-circle' },
    insufficient: { label: '根拠不足', icon: 'i-minus-circle' },
    inprogress: { label: '進行中', icon: 'i-play' }
  };

  const SOURCE_NAMES = {
    'SRC-031': 'IEA, Renewables 2024',
    'SRC-030': '資源エネルギー庁, エネルギー白書 2024',
    'SRC-029': 'IPCC, AR6 Climate Change 2022: Mitigation',
    'SRC-028': 'NREL, 2023 Cost of Wind Energy Review',
    'SRC-027': '環境省, 2050 年カーボンニュートラル政策',
    'SRC-026': 'OECD, Effective Carbon Rates 2023',
    'SRC-025': '経済産業省, 2050 年エネルギー政策の長期展望'
  };

  let CLAIMS = [
    {
      id: 'CLM-014',
      title: '洋上風力発電は 2030 年までに導入量が大幅に拡大する',
      status: 'verified',
      evidence: 4,
      owner: '佐藤 美咲',
      updated: '11-02 14:18',
      source: 'IEA, Renewables 2024',
      location: '第 2 章 / p.78',
      quote: '世界の洋上風力発電容量は、2030 年までに現在の約 3 倍に拡大する見通しである。',
      verdict: '支持',
      verdictDesc: '一次資料の導入見通しと、国内目標の水準が整合している。',
      reason: '',
      refs: ['SRC-031', 'SRC-028']
    },
    {
      id: 'CLM-013',
      title: '太陽光発電は多くの地域で最も低廉な新規電源の一つ',
      status: 'verified',
      evidence: 3,
      owner: '佐藤 美咲',
      updated: '11-02 14:02',
      source: 'IPCC, AR6 Climate Change 2022: Mitigation',
      location: '第 6 章 / p.1,246',
      quote: '太陽光発電は、多くの地域で最も低廉な新規発電源の一つとなっている。',
      verdict: '支持',
      verdictDesc: '複数地域のコスト比較が、主張を直接支持している。',
      reason: '',
      refs: ['SRC-029', 'SRC-030']
    },
    {
      id: 'CLM-012',
      title: '日本の再エネ比率は 2030 年に 40% を超える',
      status: 'unverified',
      evidence: 0,
      owner: '佐藤 美咲',
      updated: '11-02 13:44',
      source: '未登録',
      location: '引用箇所未特定',
      quote: '',
      verdict: '未検証',
      verdictDesc: '根拠の確認が完了していません。',
      reason: '一次資料の該当箇所を特定できていません。',
      refs: []
    },
    {
      id: 'CLM-011',
      title: '洋上風力は地域経済に大きな波及効果をもたらす',
      status: 'insufficient',
      evidence: 1,
      owner: '田中 健',
      updated: '11-02 12:58',
      source: 'NREL, 2023 Cost of Wind Energy Review',
      location: '第 4 章 / p.41',
      quote: '地域経済効果の定量評価は、地域・事業規模による差が大きく、現時点では一般化できない。',
      verdict: '根拠不足',
      verdictDesc: '引用は一般的な留意事項にとどまり、主張を直接支持していない。',
      reason: '国内の地域経済効果を直接示す一次資料が不足しています。',
      refs: ['SRC-028']
    },
    {
      id: 'CLM-010',
      title: 'カーボンプライシングの効果は価格のみで比較できる',
      status: 'contradicted',
      evidence: 2,
      owner: '田中 健',
      updated: '11-02 12:20',
      source: 'OECD, Effective Carbon Rates 2023',
      location: '第 1 章 / p.19',
      quote: 'カーボンプライシングの導入効果は制度設計により大きく異なり、単純比較はできない。',
      verdict: '矛盾',
      verdictDesc: '引用箇所は、価格のみで比較できるという主張を否定している。',
      reason: '本文の「価格のみで比較可能」という記述は、引用箇所と矛盾しています。',
      refs: ['SRC-026']
    },
    {
      id: 'CLM-009',
      title: '洋上風力のコストは 2010 年以降大幅に低下した',
      status: 'verified',
      evidence: 5,
      owner: '鈴木 葵',
      updated: '11-02 09:48',
      source: 'NREL, 2023 Cost of Wind Energy Review',
      location: '第 3 章 / p.27',
      quote: '洋上風力の平準化発電コストは 2010 年以降大幅に低下した。',
      verdict: '支持',
      verdictDesc: 'コスト推移の時系列データが主張を支持している。',
      reason: '',
      refs: ['SRC-028']
    },
    {
      id: 'CLM-008',
      title: '系統接続の制約は太陽光導入の主要な障壁である',
      status: 'unverified',
      evidence: 0,
      owner: '鈴木 葵',
      updated: '11-01 16:10',
      source: '未登録',
      location: '引用箇所未特定',
      quote: '',
      verdict: '未検証',
      verdictDesc: '系統接続コストに関する一次資料を確認中です。',
      reason: '一次資料の確認が完了していません。',
      refs: []
    }
  ];

  let REVIEW_ITEMS = [
    {
      id: 'RPT-020',
      title: '洋上風力の地域経済効果',
      theme: '再生可能エネルギー政策の根拠調査',
      author: '鈴木 葵',
      submitted: '2026-11-02 11:05',
      status: 'pending',
      verified: 12,
      total: 12,
      insufficient: 0,
      summary: '洋上風力の導入が地域経済に与える影響を、雇用・税収・産業連関の三点から整理したレポート。',
      excerpt: '洋上風力の地域経済効果は、事業規模と地域の産業構造に依存する。本稿では、国内の先行事例と欧州の比較を通じて、政策支援の優先順位を整理する。',
      comments: [
        { author: '鈴木 葵', role: 'リサーチャー', time: '11:12', text: '第 2 版で地域経済効果の根拠を更新しました。' }
      ]
    },
    {
      id: 'RPT-016',
      title: '太陽光発電の系統接続コスト',
      theme: '再生可能エネルギー政策の根拠調査',
      author: '鈴木 葵',
      submitted: '2026-11-01 16:40',
      status: 'pending',
      verified: 13,
      total: 15,
      insufficient: 2,
      summary: '太陽光発電の系統接続に伴う費用を、地域別の接続可能量と増強コストから比較したレポート。',
      excerpt: '系統接続の制約は、太陽光発電の導入速度を左右する。接続可能量の地域差と、増強費用の負担方法を整理する。',
      comments: []
    },
    {
      id: 'RPT-019',
      title: '水素サプライチェーンの実現可能性',
      theme: '再生可能エネルギー政策の根拠調査',
      author: '佐藤 美咲',
      submitted: '2026-11-01 18:40',
      status: 'returned',
      verified: 9,
      total: 12,
      insufficient: 3,
      summary: '水素の製造・輸送・利用にわたるサプライチェーンの実現可能性を、コストと技術成熟度から検討したレポート。',
      excerpt: '水素サプライチェーンの実現には、製造コストの低減と輸送インフラの整備が不可欠である。現時点では、大規模導入の前提が十分に示されていない。',
      comments: [
        { author: '田中 健', role: 'レビュアー', time: '11-01 19:05', text: '地域経済効果の根拠が不足しています。CLM-011 の引用箇所を追加し、再提出してください。' }
      ]
    }
  ];

  let AUDIT_ROWS = [
    { id: 'A-1024', date: '2026-11-02', time: '14:32', action: '検証', actor: '佐藤 美咲', target: 'CLM-014', detail: 'verified に変更 / 根拠 4 件' },
    { id: 'A-1023', date: '2026-11-02', time: '14:18', action: '保存', actor: '佐藤 美咲', target: 'RPT-021', detail: '第 4 版を保存' },
    { id: 'A-1022', date: '2026-11-02', time: '13:54', action: '差し戻し', actor: '田中 健', target: 'RPT-019', detail: 'コメント付きで差し戻し' },
    { id: 'A-1021', date: '2026-11-02', time: '13:20', action: '出典登録', actor: '鈴木 葵', target: 'SRC-031', detail: 'Renewables 2024 / SHA-256 固定' },
    { id: 'A-1020', date: '2026-11-02', time: '12:05', action: '閲覧', actor: '山本 修', target: '監査ログ', detail: '2026-11-01 の操作履歴を閲覧' },
    { id: 'A-1019', date: '2026-11-02', time: '11:42', action: '承認', actor: '田中 健', target: 'RPT-018', detail: '承認 / コメントあり' },
    { id: 'A-1018', date: '2026-11-02', time: '10:15', action: '提出', actor: '佐藤 美咲', target: 'RPT-021', detail: 'レビューへ提出' },
    { id: 'A-1017', date: '2026-11-02', time: '09:48', action: '検証', actor: '鈴木 葵', target: 'CLM-009', detail: 'verified に変更 / 根拠 5 件' },
    { id: 'A-1016', date: '2026-11-02', time: '09:20', action: '権限変更', actor: '山本 修', target: '佐藤 美咲', detail: 'editor 権限を確認' },
    { id: 'A-1015', date: '2026-11-02', time: '08:55', action: '検証', actor: 'システム', target: 'SRC-029', detail: 'スナップショット整合性チェック / 合格' }
  ];

  const ROUTES = {
    '#/dashboard': { screen: 'dashboard', nav: 'dashboard', title: 'ダッシュボード', crumbs: ['ワークスペース', 'ダッシュボード'] },
    '#/theme/overview': { screen: 'theme', nav: 'theme', tab: 'overview', title: '研究テーマ', crumbs: ['研究', '研究テーマ', '概要'] },
    '#/theme/sources': { screen: 'theme', nav: 'theme', tab: 'sources', title: '研究テーマ / 出典', crumbs: ['研究', '研究テーマ', '出典'] },
    '#/theme/claims': { screen: 'theme', nav: 'theme', tab: 'claims', title: '研究テーマ / 主張', crumbs: ['研究', '研究テーマ', '主張'] },
    '#/theme/report': { screen: 'theme', nav: 'theme', tab: 'report', title: '研究テーマ / レポート', crumbs: ['研究', '研究テーマ', 'レポート'] },
    '#/claims': { screen: 'claims', nav: 'claims', title: 'クレーム', crumbs: ['研究', 'クレーム'] },
    '#/editor': { screen: 'editor', nav: 'editor', title: 'レポートエディタ', crumbs: ['研究', 'レポート', '政策提言サマリー'] },
    '#/verification': { screen: 'verification', nav: 'verification', title: '検証結果', crumbs: ['品質', '検証結果'] },
    '#/review': { screen: 'review', nav: 'review', title: 'レビュー / 承認', crumbs: ['品質', 'レビュー / 承認'] },
    '#/audit': { screen: 'audit', nav: 'audit', title: '監査ログ', crumbs: ['管理', '監査ログ'], adminOnly: true }
  };

  const THEME_TAB_LABELS = { overview: '概要', sources: '出典', claims: '主張', report: 'レポート' };

  const state = {
    authed: false,
    role: 'editor',
    currentScreen: 'dashboard',
    themeTab: 'overview',
    reviewTab: 'pending',
    reviewItemId: 'RPT-020',
    verificationClaim: 'CLM-014',
    evidenceClaim: null,
    claimFilter: '',
    sourceTab: 'url',
    pendingSource: null,
    sourceCount: 7,
    nextSourceNumber: 32,
    editorCounts: { verified: 12, unverified: 2, contradicted: 0, insufficient: 1 },
    reportSubmitted: false,
    pendingClaimSearch: '',
    loaderTimer: null,
    toastTimer: null
  };

  const els = {};

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    cacheElements();
    bindEvents();
    renderStatic();
    applyRole();

    const storedRole = localStorage.getItem('rihrp-role') || sessionStorage.getItem('rihrp-role');
    if (storedRole && ROLE_DATA[storedRole] && location.hash !== '#/login') {
      state.role = storedRole;
      state.authed = true;
      applyRole();
      renderReview();
      showApp();
      route();
    } else {
      showLogin();
    }
  }

  function cacheElements() {
    const ids = [
      'login-view', 'app-view', 'login-form', 'login-email', 'login-password', 'login-remember',
      'login-submit', 'login-error', 'login-email-error', 'login-password-error', 'sso-button',
      'forgot-password', 'login-recent-empty', 'sidebar', 'sidebar-scrim', 'menu-button',
      'audit-nav-group', 'sidebar-user-name', 'sidebar-user-role', 'sidebar-avatar', 'logout-button',
      'breadcrumb', 'global-search-form', 'global-search', 'sync-status', 'notification-button',
      'notification-dot', 'notifications-panel', 'notification-list', 'mark-read', 'help-button',
      'role-chip-label', 'topbar-avatar', 'main-content', 'screen-loader', 'mobile-readonly',
      'screen-dashboard', 'screen-theme', 'screen-claims', 'screen-editor', 'screen-verification',
      'screen-review', 'screen-audit', 'theme-search', 'theme-status-filter', 'themes-table',
      'themes-empty', 'clear-theme-filters', 'source-search', 'sources-table', 'sources-empty',
      'theme-claim-search', 'theme-claims-table', 'theme-claims-empty', 'report-status-filter',
      'reports-table', 'reports-empty', 'theme-source-count', 'theme-claim-count',
      'claims-search', 'claims-table-body', 'claims-empty', 'claims-feedback', 'claims-selection-info',
      'claims-select-all', 'claims-verify-selected', 'claims-refresh', 'claim-status-filters',
      'claims-count-verified', 'claims-count-unverified', 'claims-count-contradicted',
      'claims-count-insufficient', 'claims-role-note', 'clear-claim-filters',
      'doc-body', 'saved-state', 'editor-save', 'editor-verify', 'editor-submit', 'editor-feedback',
      'editor-locked-note', 'editor-pill-verified', 'editor-pill-attention', 'editor-pill-warning',
      'editor-summary-verified', 'editor-summary-unverified', 'editor-summary-contradicted',
      'editor-summary-insufficient', 'editor-summary-badge', 'report-status-badge',
      'evidence-empty', 'evidence-content', 'evidence-close', 'evidence-panel',
      'verify-search', 'verify-list', 'verify-list-empty', 'verify-detail', 'verify-detail-body',
      'verify-detail-empty', 'verify-feedback', 'verify-rerun', 'verify-stat-verified',
      'verify-stat-unverified', 'verify-stat-contradicted', 'verify-stat-insufficient',
      'review-list', 'review-list-empty', 'review-detail', 'review-detail-body',
      'review-detail-empty', 'review-feedback', 'review-count-pending', 'review-count-returned',
      'review-count-approved', 'review-tabs', 'review-tab-pending', 'review-tab-returned',
      'review-tab-approved', 'audit-action-filter', 'audit-actor-filter', 'audit-from', 'audit-to',
      'audit-search', 'audit-apply', 'audit-clear', 'audit-refresh', 'audit-body', 'audit-empty',
      'audit-empty-clear', 'audit-feedback', 'audit-result-count', 'audit-page-info',
      'source-dialog', 'source-close', 'source-cancel', 'source-save', 'source-tab-url',
      'source-tab-doi', 'source-tab-text', 'source-url', 'source-doi', 'source-text',
      'source-error', 'source-success', 'source-preview-type', 'source-preview-empty',
      'source-preview-loading', 'source-preview-content', 'source-preview-name',
      'source-preview-publisher', 'source-preview-year', 'source-preview-hash', 'source-copy-hash',
      'shortcuts-dialog', 'shortcuts-close', 'shortcuts-ok', 'toast-region'
    ];
    ids.forEach((id) => {
      els[toCamel(id)] = document.getElementById(id);
    });
    els.screens = $$('.screen');
    els.themeTabs = $$('[data-theme-tab]');
    els.themePanels = $$('[data-theme-panel]');
    els.sourceTabs = $$('[data-source-tab]');
    els.sourcePanels = $$('[data-source-panel]');
    els.navItems = $$('.nav-item');
    els.screenErrors = $$('[data-screen-error]');
    els.notificationWrap = $('.notification-wrap');
    els.reviewTabs = $$('[data-review-tab]');
  }

  function toCamel(value) {
    return value.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
  }

  function bindEvents() {
    els.loginForm.addEventListener('submit', handleLoginSubmit);
    els.ssoButton.addEventListener('click', () => {
      els.loginEmail.value = els.loginEmail.value || ROLE_DATA.editor.email;
      els.loginPassword.value = els.loginPassword.value || 'research';
      handleLoginSubmit(new Event('submit', { cancelable: true }));
    });
    els.forgotPassword.addEventListener('click', () => {
      showToast('パスワード再設定の案内は、組織の管理者に依頼してください。', 'info');
    });
    ['login-email', 'login-password'].forEach((id) => {
      els[toCamel(id)].addEventListener('input', clearLoginErrors);
    });
    els.logoutButton.addEventListener('click', handleLogout);

    els.menuButton.addEventListener('click', toggleSidebar);
    els.sidebarScrim.addEventListener('click', closeSidebar);

    els.globalSearchForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const query = els.globalSearch.value.trim();
      closeNotifications();
      if (!query) {
        els.globalSearch.focus();
        return;
      }
      state.pendingClaimSearch = query;
      if (location.hash === '#/claims') {
        const input = $('#claims-search');
        if (input) {
          input.value = query;
          renderClaimsTable();
          showToast(`「${query}」でクレームを検索しました。`, 'info');
        }
      } else {
        location.hash = '#/claims';
      }
    });

    els.notificationButton.addEventListener('click', (event) => {
      event.stopPropagation();
      const isOpen = !els.notificationsPanel.hidden;
      els.notificationsPanel.hidden = isOpen;
      els.notificationButton.setAttribute('aria-expanded', String(!isOpen));
    });
    els.markRead.addEventListener('click', () => {
      els.notificationDot.hidden = true;
      showToast('すべての通知を既読にしました。', 'success');
    });
    $$('[data-go]').forEach((item) => {
      item.addEventListener('click', () => {
        const target = item.dataset.go;
        closeNotifications();
        if (target) location.hash = target;
      });
    });
    document.addEventListener('click', (event) => {
      if (!els.notificationWrap.contains(event.target)) closeNotifications();
    });

    els.helpButton.addEventListener('click', openShortcuts);
    els.shortcutsClose.addEventListener('click', () => els.shortcutsDialog.close());
    els.shortcutsOk.addEventListener('click', () => els.shortcutsDialog.close());

    $$('[data-theme-tab]').forEach((tab) => {
      tab.addEventListener('click', () => setThemeTab(tab.dataset.themeTab, true));
    });
    $('#theme-tabs').addEventListener('keydown', (event) => handleTabKeys(event, els.themeTabs, (tab) => tab.click()));

    $$('[data-review-tab]').forEach((tab) => {
      tab.addEventListener('click', () => setReviewTab(tab.dataset.reviewTab));
    });
    $('.review-tabs')?.addEventListener('keydown', (event) => handleTabKeys(event, els.reviewTabs, (tab) => tab.click()));

    $$('[data-source-tab]').forEach((tab) => {
      tab.addEventListener('click', () => setSourceTab(tab.dataset.sourceTab));
    });
    $('#source-dialog .source-tabs').addEventListener('keydown', (event) => handleTabKeys(event, els.sourceTabs, (tab) => tab.click()));
    $$('[data-source-fetch]').forEach((button) => button.addEventListener('click', fetchSourcePreview));
    [els.sourceUrl, els.sourceDoi, els.sourceText].forEach((input) => {
      input.addEventListener('input', () => {
        invalidateSourcePreview();
        els.sourceError.hidden = true;
        els.sourceSuccess.hidden = true;
      });
    });
    els.sourceClose.addEventListener('click', closeSourceDialog);
    els.sourceCancel.addEventListener('click', closeSourceDialog);
    els.sourceSave.addEventListener('click', saveSource);
    els.sourceCopyHash.addEventListener('click', () => {
      if (state.pendingSource) copyText(state.pendingSource.hash);
      else showToast('コピーするハッシュがありません。', 'error');
    });
    els.sourceDialog.addEventListener('click', (event) => {
      if (event.target === els.sourceDialog) closeSourceDialog();
    });

    $$('[data-open-source]').forEach((button) => button.addEventListener('click', openSourceDialog));

    $$('#themes-table tbody tr[data-href]').forEach((row) => {
      row.tabIndex = 0;
      row.setAttribute('role', 'link');
      row.setAttribute('aria-label', row.querySelector('.table-link')?.textContent || '研究テーマを開く');
      row.addEventListener('click', (event) => {
        if (event.target.closest('a, button, input, select')) return;
        location.hash = row.dataset.href;
      });
      row.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          location.hash = row.dataset.href;
        }
      });
    });

    els.themeSearch.addEventListener('input', filterThemes);
    els.themeStatusFilter.addEventListener('change', filterThemes);
    els.clearThemeFilters.addEventListener('click', () => {
      els.themeSearch.value = '';
      els.themeStatusFilter.value = '';
      filterThemes();
      els.themeSearch.focus();
    });

    els.sourceSearch.addEventListener('input', filterSources);
    els.themeClaimSearch.addEventListener('input', renderThemeClaims);
    els.reportStatusFilter.addEventListener('change', filterReports);

    els.claimsSearch.addEventListener('input', renderClaimsTable);
    $('#claim-status-filters').addEventListener('click', (event) => {
      const chip = event.target.closest('[data-claim-status]');
      if (!chip) return;
      state.claimFilter = chip.dataset.claimStatus;
      $$('#claim-status-filters [data-claim-status]').forEach((item) => {
        item.classList.toggle('is-active', item === chip);
      });
      renderClaimsTable();
    });
    els.claimsSelectAll.addEventListener('click', toggleAllClaims);
    els.claimsVerifySelected.addEventListener('click', verifySelectedClaims);
    els.claimsRefresh.addEventListener('click', refreshClaims);
    els.clearClaimFilters.addEventListener('click', () => {
      els.claimsSearch.value = '';
      state.claimFilter = '';
      $$('#claim-status-filters [data-claim-status]').forEach((item) => {
        item.classList.toggle('is-active', item.dataset.claimStatus === '');
      });
      renderClaimsTable();
      els.claimsSearch.focus();
    });
    els.claimsTableBody.addEventListener('change', (event) => {
      if (event.target.matches('input[type="checkbox"]')) updateSelection();
    });

    els.verifySearch.addEventListener('input', renderVerificationList);
    els.verifyRerun.addEventListener('click', () => rerunVerification(state.verificationClaim, els.verifyRerun));

    els.reviewList.addEventListener('click', (event) => {
      const item = event.target.closest('[data-review-id]');
      if (!item) return;
      state.reviewItemId = item.dataset.reviewId;
      renderReview();
    });
    els.reviewDetail.addEventListener('click', handleReviewClick);

    els.auditApply.addEventListener('click', applyAuditFilters);
    els.auditClear.addEventListener('click', clearAuditFilters);
    els.auditRefresh.addEventListener('click', refreshAudit);
    els.auditEmptyClear.addEventListener('click', clearAuditFilters);

    els.editorSave.addEventListener('click', saveEditor);
    els.editorVerify.addEventListener('click', verifyEditorClaims);
    els.editorSubmit.addEventListener('click', submitEditor);
    els.evidenceClose.addEventListener('click', () => {
      state.evidenceClaim = null;
      renderEvidence();
    });
    $$('[data-section-target]').forEach((button) => {
      button.addEventListener('click', () => {
        const target = document.getElementById(button.dataset.sectionTarget);
        $$('[data-section-target]').forEach((item) => item.classList.toggle('is-active', item === button));
        if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        if (target && !target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
        if (target) target.focus({ preventScroll: true });
      });
    });

    document.addEventListener('click', handleDocumentClick);
    document.addEventListener('keydown', handleGlobalKeydown);
    window.addEventListener('hashchange', route);
    window.addEventListener('online', () => {
      hideScreenErrors();
      showToast('接続が回復しました。', 'success');
    });
    window.addEventListener('offline', () => {
      showCurrentScreenError();
      showToast('オフラインです。接続を確認してください。', 'error');
    });
    const mobileQuery = window.matchMedia('(max-width: 767px)');
    if (mobileQuery.addEventListener) {
      mobileQuery.addEventListener('change', applyRole);
    }
  }

  function renderStatic() {
    renderClaimsTable();
    renderThemeClaims();
    renderVerification();
    renderEditorSummary();
    renderReview();
    renderAudit();
    updateSyncStatus();
  }

  function currentUser() {
    return ROLE_DATA[state.role] || ROLE_DATA.editor;
  }

  function isMobile() {
    return window.matchMedia('(max-width: 767px)').matches;
  }

  function canEdit() {
    return state.role === 'editor' && !isMobile();
  }

  function canReview() {
    return state.role === 'reviewer' && !isMobile();
  }

  function esc(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }[char]));
  }

  function normalize(value) {
    return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim();
  }

  function statusBadge(status) {
    const item = STATUS[status] || STATUS.insufficient;
    return `<span class="status ${esc(status)}"><svg class="icon" aria-hidden="true"><use href="#${item.icon}"></use></svg>${item.label}</span>`;
  }

  function sleepSafe(ms) {
    return sleep(ms);
  }

  function nowParts() {
    const date = new Date();
    const pad = (value) => String(value).padStart(2, '0');
    return {
      date: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
      time: `${pad(date.getHours())}:${pad(date.getMinutes())}`,
      short: `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
    };
  }

  function updateSyncStatus() {
    const now = nowParts();
    const span = els.syncStatus.querySelector('span');
    if (span) span.textContent = `同期済み ${now.time}`;
  }

  function setSavedState(text) {
    const span = els.savedState.querySelector('span');
    if (span) span.textContent = text;
  }

  function showToast(message, type = 'success') {
    const icon = type === 'error' ? 'i-alert-triangle' : type === 'info' ? 'i-info' : 'i-check-circle';
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<svg class="icon" aria-hidden="true"><use href="#${icon}"></use></svg><span>${esc(message)}</span>`;
    els.toastRegion.appendChild(toast);
    window.setTimeout(() => {
      toast.remove();
    }, 4300);
  }

  function setButtonLoading(button, loading, label = '処理中…') {
    if (!button) return;
    if (loading) {
      if (!button.dataset.originalHtml) button.dataset.originalHtml = button.innerHTML;
      button.classList.add('is-loading');
      button.disabled = true;
      button.textContent = label;
    } else {
      button.classList.remove('is-loading');
      if (button.dataset.originalHtml) {
        button.innerHTML = button.dataset.originalHtml;
        delete button.dataset.originalHtml;
      }
      button.disabled = false;
    }
  }

  function setInlineFeedback(element, type, message) {
    if (!element) return;
    if (!message) {
      element.hidden = true;
      element.innerHTML = '';
      element.className = 'editor-inline-feedback';
      return;
    }
    element.hidden = false;
    element.className = type === 'error' ? 'inline-error' : 'inline-success';
    element.setAttribute('role', type === 'error' ? 'alert' : 'status');
    const icon = type === 'error' ? 'i-alert-triangle' : 'i-check-circle';
    element.innerHTML = `<svg class="icon" aria-hidden="true"><use href="#${icon}"></use></svg><span>${esc(message)}</span>`;
  }

  function hideScreenErrors() {
    els.screenErrors.forEach((error) => { error.hidden = true; });
  }

  function showCurrentScreenError() {
    if (!state.authed) return;
    const screen = document.getElementById(`screen-${state.currentScreen}`);
    if (!screen) return;
    const error = screen.querySelector('[data-screen-error]');
    if (error) error.hidden = false;
  }

  function showScreenLoader() {
    els.screenLoader.hidden = false;
    els.screenLoader.setAttribute('aria-busy', 'true');
    clearTimeout(state.loaderTimer);
    state.loaderTimer = window.setTimeout(() => {
      els.screenLoader.hidden = true;
      els.screenLoader.setAttribute('aria-busy', 'false');
      if (!navigator.onLine) showCurrentScreenError();
      focusScreenHeading();
    }, 300);
  }

  function focusScreenHeading() {
    const heading = document.querySelector('.screen.is-active h1');
    if (heading) heading.focus({ preventScroll: true });
  }

  function showLogin() {
    state.authed = false;
    state.currentScreen = 'login';
    els.loginView.hidden = false;
    els.appView.hidden = true;
    closeSidebar();
    closeNotifications();
    document.title = 'サインイン | RIHRP Research Studio';
    if (location.hash !== '#/login') history.replaceState(null, '', '#/login');
    window.setTimeout(() => els.loginEmail.focus(), 40);
  }

  function showApp() {
    els.loginView.hidden = true;
    els.appView.hidden = false;
  }

  function route() {
    const hash = location.hash || '#/dashboard';
    if (!state.authed) {
      showLogin();
      return;
    }
    if (hash === '#/login') {
      showLogin();
      return;
    }
    let resolved = ROUTES[hash];
    if (!resolved && hash.startsWith('#/theme')) resolved = ROUTES['#/theme/overview'];
    if (!resolved) {
      location.hash = '#/dashboard';
      return;
    }
    if (resolved.adminOnly && state.role !== 'admin') {
      state.currentScreen = 'dashboard';
      showToast('監査ログの閲覧には管理者権限が必要です。', 'error');
      location.hash = '#/dashboard';
      return;
    }
    showApp();
    showScreen(resolved);
  }

  function showScreen(routeInfo) {
    state.currentScreen = routeInfo.screen;
    els.screens.forEach((screen) => {
      const active = screen.dataset.screen === routeInfo.screen;
      screen.classList.toggle('is-active', active);
    });
    els.navItems.forEach((item) => {
      const active = item.dataset.nav === routeInfo.nav;
      item.classList.toggle('is-active', active);
      if (active) item.setAttribute('aria-current', 'page');
      else item.removeAttribute('aria-current');
    });
    updateBreadcrumb(routeInfo.crumbs);
    document.title = `${routeInfo.title} | RIHRP Research Studio`;
    hideScreenErrors();
    closeSidebar();
    closeNotifications();
    els.mainContent.scrollTop = 0;

    if (routeInfo.screen === 'theme') {
      setThemeTab(routeInfo.tab || 'overview', false);
      filterSources();
      filterReports();
      renderThemeClaims();
    }
    if (routeInfo.screen === 'claims') {
      if (state.pendingClaimSearch) {
        els.claimsSearch.value = state.pendingClaimSearch;
        state.pendingClaimSearch = '';
        showToast(`「${els.claimsSearch.value}」で検索しています。`, 'info');
      }
      renderClaimsTable();
    }
    if (routeInfo.screen === 'editor') {
      if (!state.evidenceClaim) state.evidenceClaim = 'CLM-014';
      renderEditorSummary();
      renderEvidence();
      applyRole();
    }
    if (routeInfo.screen === 'verification') {
      renderVerification();
    }
    if (routeInfo.screen === 'review') {
      renderReview();
    }
    if (routeInfo.screen === 'audit') {
      renderAudit();
    }
    showScreenLoader();
  }

  function updateBreadcrumb(parts) {
    els.breadcrumb.innerHTML = parts.map((part, index) => {
      const current = index === parts.length - 1;
      return `${index > 0 ? '<span class="sep" aria-hidden="true">/</span>' : ''}<span${current ? ' class="current" aria-current="page"' : ''}>${esc(part)}</span>`;
    }).join('');
  }

  function resolveThemeRoute(tab) {
    return ROUTES[`#/theme/${tab}`] || ROUTES['#/theme/overview'];
  }

  function setThemeTab(tab, updateHash) {
    state.themeTab = tab;
    els.themeTabs.forEach((item) => {
      const active = item.dataset.themeTab === tab;
      item.classList.toggle('is-active', active);
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
    });
    els.themePanels.forEach((panel) => {
      const active = panel.dataset.themePanel === tab;
      panel.classList.toggle('is-active', active);
      panel.hidden = !active;
    });
    if (tab === 'claims') renderThemeClaims();
    if (tab === 'sources') filterSources();
    if (tab === 'report') filterReports();
    if (updateHash) {
      const nextHash = `#/theme/${tab}`;
      if (location.hash !== nextHash) history.replaceState(null, '', nextHash);
      updateBreadcrumb(resolveThemeRoute(tab).crumbs);
      document.title = `${resolveThemeRoute(tab).title} | RIHRP Research Studio`;
    }
  }

  function handleTabKeys(event, tabs, activate) {
    const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End'];
    if (!keys.includes(event.key)) return;
    const currentIndex = tabs.indexOf(document.activeElement);
    if (currentIndex < 0) return;
    event.preventDefault();
    let nextIndex = currentIndex;
    if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % tabs.length;
    if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = tabs.length - 1;
    tabs[nextIndex].focus();
    activate(tabs[nextIndex]);
  }

  function toggleSidebar() {
    const open = !els.sidebar.classList.contains('is-open');
    els.sidebar.classList.toggle('is-open', open);
    els.sidebarScrim.hidden = !open;
    els.menuButton.setAttribute('aria-expanded', String(open));
  }

  function closeSidebar() {
    els.sidebar.classList.remove('is-open');
    els.sidebarScrim.hidden = true;
    els.menuButton.setAttribute('aria-expanded', 'false');
  }

  function closeNotifications() {
    if (!els.notificationsPanel) return;
    els.notificationsPanel.hidden = true;
    els.notificationButton.setAttribute('aria-expanded', 'false');
  }

  function openShortcuts() {
    if (!els.shortcutsDialog.open) els.shortcutsDialog.showModal();
    window.setTimeout(() => els.shortcutsClose.focus(), 20);
  }

  function handleGlobalKeydown(event) {
    const target = event.target;
    const typing = target.matches('input, textarea, select, [contenteditable="true"]');
    if (event.key === 'Escape') {
      if (els.sidebar.classList.contains('is-open')) closeSidebar();
      closeNotifications();
    }
    if (!typing && event.key === '/') {
      event.preventDefault();
      els.globalSearch.focus();
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      els.globalSearch.focus();
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && state.currentScreen === 'editor') {
      event.preventDefault();
      saveEditor();
    }
    if (!typing && event.key === '?') {
      event.preventDefault();
      openShortcuts();
    }
  }

  function handleDocumentClick(event) {
    const retry = event.target.closest('[data-retry]');
    if (retry) {
      hideScreenErrors();
      showScreenLoader();
      window.setTimeout(() => {
        if (!navigator.onLine) {
          showCurrentScreenError();
          showToast('再試行できませんでした。接続を確認してください。', 'error');
        } else {
          showToast('最新の状態を読み込みました。', 'success');
          updateSyncStatus();
        }
      }, 360);
    }

    const copyButton = event.target.closest('[data-copy]');
    if (copyButton) {
      event.preventDefault();
      copyText(copyButton.dataset.copy);
    }

    const verificationLink = event.target.closest('[data-open-verification]');
    if (verificationLink) {
      event.preventDefault();
      state.verificationClaim = verificationLink.dataset.openVerification;
      location.hash = '#/verification';
    }

    const claimRef = event.target.closest('[data-claim]');
    if (claimRef && state.currentScreen === 'editor') {
      state.evidenceClaim = claimRef.dataset.claim;
      renderEvidence();
    }

    const verifyItem = event.target.closest('[data-verify-claim]');
    if (verifyItem) {
      state.verificationClaim = verifyItem.dataset.verifyClaim;
      renderVerification();
    }

    const verifyCurrent = event.target.closest('[data-verify-current]');
    if (verifyCurrent) {
      rerunVerification(state.verificationClaim, verifyCurrent);
    }
  }

  function handleLogout() {
    localStorage.removeItem('rihrp-role');
    sessionStorage.removeItem('rihrp-role');
    state.authed = false;
    state.evidenceClaim = null;
    showLogin();
    showToast('サインアウトしました。', 'info');
  }

  function handleLoginSubmit(event) {
    event.preventDefault();
    clearLoginErrors();
    const email = els.loginEmail.value.trim();
    const password = els.loginPassword.value;
    let invalid = false;

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      els.loginEmailError.textContent = '有効なメールアドレスを入力してください。';
      els.loginEmailError.hidden = false;
      invalid = true;
    }
    if (password.length < 4) {
      els.loginPasswordError.textContent = 'パスワードは 4 文字以上で入力してください。';
      els.loginPasswordError.hidden = false;
      invalid = true;
    }
    if (invalid) {
      els.loginError.textContent = '入力内容を確認してください。';
      els.loginError.hidden = false;
      (els.loginEmailError.hidden ? els.loginPassword : els.loginEmail).focus();
      return;
    }

    setButtonLoading(els.loginSubmit, true, '確認中…');
    els.loginError.hidden = true;

    window.setTimeout(() => {
      setButtonLoading(els.loginSubmit, false);
      if (password.length < 4) {
        els.loginError.textContent = 'メールアドレスまたはパスワードが正しくありません。';
        els.loginError.hidden = false;
        els.loginPassword.focus();
        return;
      }
      const local = email.split('@')[0].toLowerCase();
      const role = local.includes('admin') ? 'admin' : local.includes('reviewer') ? 'reviewer' : 'editor';
      state.role = role;
      state.authed = true;
      if (els.loginRemember.checked) {
        localStorage.setItem('rihrp-role', role);
        sessionStorage.removeItem('rihrp-role');
      } else {
        sessionStorage.setItem('rihrp-role', role);
        localStorage.removeItem('rihrp-role');
      }
      applyRole();
      renderReview();
      showApp();
      const destination = location.hash && location.hash !== '#/login' ? location.hash : '#/dashboard';
      if (location.hash === destination) route();
      else location.hash = destination;
      showToast(`ようこそ、${currentUser().name}さん。`, 'success');
    }, 650);
  }

  function clearLoginErrors() {
    els.loginError.hidden = true;
    els.loginEmailError.hidden = true;
    els.loginPasswordError.hidden = true;
  }

  function applyRole() {
    const user = currentUser();
    els.sidebarUserName.textContent = user.name;
    els.sidebarUserRole.textContent = user.label;
    els.sidebarAvatar.textContent = user.initials;
    els.topbarAvatar.textContent = user.initials;
    els.roleChipLabel.textContent = user.label;
    els.auditNavGroup.hidden = state.role !== 'admin';
    document.body.dataset.role = state.role;

    $$('[data-open-source]').forEach((button) => {
      button.hidden = state.role !== 'editor';
    });

    const editorAllowed = canEdit();
    [els.editorSave, els.editorVerify, els.editorSubmit, els.claimsVerifySelected, els.verifyRerun].forEach((button) => {
      if (!button) return;
      button.disabled = !editorAllowed;
      if (button === els.editorSubmit && state.reportSubmitted) button.disabled = true;
    });

    els.editorLockedNote.hidden = editorAllowed;
    els.editorLockedNote.querySelector('span').textContent = isMobile()
      ? 'モバイルでは閲覧のみです。本文の編集・検証・提出は PC で行ってください。'
      : '閲覧モードです。本文の編集・検証・提出はリサーチャー権限のみ実行できます。';
    $$('[data-editable="true"]').forEach((element) => {
      element.contentEditable = String(editorAllowed);
      element.setAttribute('aria-readonly', String(!editorAllowed));
    });

    els.claimsRoleNote.querySelector('span').textContent = isMobile()
      ? 'モバイルでは閲覧のみです。検証の実行は PC のリサーチャー権限で行ってください。'
      : state.role === 'editor'
        ? '検証の実行はリサーチャー権限で行えます。選択したクレームを一括で検証できます。'
        : '検証の実行はリサーチャー権限が必要です。現在の権限では結果の確認のみ行えます。';

    if (state.currentScreen === 'editor') {
      els.editorSubmit.disabled = !editorAllowed || state.reportSubmitted;
    }
  }

  function renderClaimFilterCounts() {
    const counts = {
      '': CLAIMS.length,
      verified: CLAIMS.filter((claim) => claim.status === 'verified').length,
      unverified: CLAIMS.filter((claim) => claim.status === 'unverified').length,
      contradicted: CLAIMS.filter((claim) => claim.status === 'contradicted').length,
      insufficient: CLAIMS.filter((claim) => claim.status === 'insufficient').length
    };
    $$('#claim-status-filters [data-claim-status]').forEach((chip) => {
      const count = chip.querySelector('.chip-count');
      if (count) count.textContent = counts[chip.dataset.claimStatus] ?? 0;
    });
  }

  function updateClaimsSummary() {
    const counts = {
      verified: CLAIMS.filter((claim) => claim.status === 'verified').length,
      unverified: CLAIMS.filter((claim) => claim.status === 'unverified').length,
      contradicted: CLAIMS.filter((claim) => claim.status === 'contradicted').length,
      insufficient: CLAIMS.filter((claim) => claim.status === 'insufficient').length
    };
    els.claimsCountVerified.textContent = counts.verified;
    els.claimsCountUnverified.textContent = counts.unverified;
    els.claimsCountContradicted.textContent = counts.contradicted;
    els.claimsCountInsufficient.textContent = counts.insufficient;
    els.verifyStatVerified.textContent = counts.verified;
    els.verifyStatUnverified.textContent = counts.unverified;
    els.verifyStatContradicted.textContent = counts.contradicted;
    els.verifyStatInsufficient.textContent = counts.insufficient;
    renderClaimFilterCounts();
  }

  function renderClaimsTable() {
    const query = normalize(els.claimsSearch.value);
    const rows = CLAIMS.filter((claim) => {
      const statusMatch = !state.claimFilter || claim.status === state.claimFilter;
      const text = normalize(`${claim.id} ${claim.title} ${claim.owner} ${claim.source}`);
      return statusMatch && (!query || text.includes(query));
    });

    els.claimsTableBody.innerHTML = rows.map((claim) => `
      <tr data-claim-row="${esc(claim.id)}">
        <td data-label=""><input class="table-check" type="checkbox" data-claim-check="${esc(claim.id)}" aria-label="${esc(claim.id)} を選択"></td>
        <td data-label="主張"><button class="row-title-button" type="button" data-open-verification="${esc(claim.id)}">${esc(claim.title)}</button><span class="cell-sub">${esc(claim.id)} / ${esc(claim.source)}</span></td>
        <td data-label="検証ステータス">${statusBadge(claim.status)}</td>
        <td data-label="根拠数"><span class="mono">${claim.evidence}</span></td>
        <td data-label="担当">${esc(claim.owner)}</td>
        <td data-label="更新"><span class="od-nowrap">${esc(claim.updated)}</span></td>
        <td data-label="操作"><button class="link-button" type="button" data-open-verification="${esc(claim.id)}">判定を見る</button></td>
      </tr>
    `).join('');
    els.claimsEmpty.hidden = rows.length > 0;
    updateSelection();
    updateClaimsSummary();
  }

  function updateSelection() {
    const checks = $$('#claims-table-body input[type="checkbox"]');
    const selected = checks.filter((check) => check.checked);
    const allSelected = checks.length > 0 && selected.length === checks.length;
    els.claimsSelectAll.textContent = allSelected ? '選択を解除' : 'すべて選択';
    if (selected.length === 0) {
      els.claimsSelectionInfo.textContent = 'クレームを選択すると一括検証できます。';
    } else {
      const unverified = selected.filter((check) => {
        const claim = CLAIMS.find((item) => item.id === check.dataset.claimCheck);
        return claim && claim.status === 'unverified';
      }).length;
      els.claimsSelectionInfo.innerHTML = `<strong>${selected.length} 件</strong>を選択中${unverified ? ` / 未検証 ${unverified} 件` : ''}`;
    }
  }

  function toggleAllClaims() {
    const checks = $$('#claims-table-body input[type="checkbox"]');
    const allSelected = checks.length > 0 && checks.every((check) => check.checked);
    checks.forEach((check) => { check.checked = !allSelected; });
    updateSelection();
  }

  async function verifySelectedClaims() {
    if (!canEdit()) {
      setInlineFeedback(els.claimsFeedback, 'error', '検証を実行する権限がありません。');
      showToast('検証にはリサーチャー権限が必要です。', 'error');
      return;
    }
    const selectedIds = $$('#claims-table-body input[type="checkbox"]:checked').map((check) => check.dataset.claimCheck);
    if (!selectedIds.length) {
      setInlineFeedback(els.claimsFeedback, 'error', '検証するクレームを選択してください。');
      const first = $('#claims-table-body input[type="checkbox"]');
      if (first) first.focus();
      return;
    }

    setButtonLoading(els.claimsVerifySelected, true, '検証中…');
    setInlineFeedback(els.claimsFeedback, '');
    await sleepSafe(850);

    let changed = 0;
    selectedIds.forEach((id) => {
      const claim = CLAIMS.find((item) => item.id === id);
      if (!claim) return;
      if (claim.status === 'unverified') {
        claim.status = 'verified';
        claim.evidence = Math.max(claim.evidence, 2);
        claim.quote = claim.quote || '検証実行時に一次資料の該当箇所を確認しました。';
        claim.verdict = '支持';
        claim.verdictDesc = '再検証の結果、引用箇所が主張を支持しています。';
        claim.reason = '';
        claim.source = claim.source === '未登録' ? 'IEA, Renewables 2024' : claim.source;
        claim.location = claim.location === '引用箇所未特定' ? '第 3 章 / p.86' : claim.location;
        if (['CLM-012', 'CLM-008'].includes(claim.id) && state.editorCounts.unverified > 0) {
          state.editorCounts.unverified -= 1;
          state.editorCounts.verified += 1;
        }
        changed += 1;
      }
    });

    setButtonLoading(els.claimsVerifySelected, false);
    applyRole();
    renderAll();
    updateSyncStatus();
    addAudit('検証', currentUser().name, selectedIds.join(', '), '一括検証を実行');
    if (changed > 0) {
      setInlineFeedback(els.claimsFeedback, 'success', `${changed} 件のクレームを検証しました。`);
      showToast(`${changed} 件のクレームを検証しました。`, 'success');
    } else {
      setInlineFeedback(els.claimsFeedback, 'success', '選択したクレームに変更はありませんでした。');
      showToast('選択したクレームはすでに検証済み、または追加対応が必要です。', 'info');
    }
  }

  async function refreshClaims() {
    setButtonLoading(els.claimsRefresh, true, '読み込み中…');
    setInlineFeedback(els.claimsFeedback, '');
    await sleepSafe(450);
    setButtonLoading(els.claimsRefresh, false);
    updateSyncStatus();
    renderClaimsTable();
    showToast('最新のクレームを読み込みました。', 'success');
  }

  function renderThemeClaims() {
    const query = normalize(els.themeClaimSearch.value);
    const rows = CLAIMS.filter((claim) => !query || normalize(`${claim.id} ${claim.title}`).includes(query));
    els.themeClaimsTable.querySelector('tbody').innerHTML = rows.map((claim) => `
      <tr>
        <td data-label="主張"><button class="row-title-button" type="button" data-open-verification="${esc(claim.id)}">${esc(claim.title)}</button><span class="cell-sub">${esc(claim.id)} / ${esc(claim.source)}</span></td>
        <td data-label="検証ステータス">${statusBadge(claim.status)}</td>
        <td data-label="根拠数"><span class="mono">${claim.evidence}</span></td>
        <td data-label="更新"><span class="od-nowrap">${esc(claim.updated)}</span></td>
      </tr>
    `).join('');
    els.themeClaimsEmpty.hidden = rows.length > 0;
  }

  function renderVerification() {
    const claim = CLAIMS.find((item) => item.id === state.verificationClaim);
    if (!claim) {
      state.verificationClaim = CLAIMS[0]?.id || null;
    }
    renderVerificationList();
    updateClaimsSummary();
    renderVerificationDetail();
  }

  function renderVerificationList() {
    const query = normalize(els.verifySearch.value);
    const rows = CLAIMS.filter((claim) => !query || normalize(`${claim.id} ${claim.title} ${claim.source}`).includes(query));
    els.verifyList.innerHTML = rows.map((claim) => `
      <button class="claim-list-item${claim.id === state.verificationClaim ? ' is-active' : ''}" type="button" data-verify-claim="${esc(claim.id)}">
        <span class="claim-list-dot ${esc(claim.status)}" aria-hidden="true"></span>
        <span class="claim-list-copy">
          <strong>${esc(claim.title)}</strong>
          <span>${esc(claim.id)} · ${STATUS[claim.status].label} · 根拠 ${claim.evidence} 件</span>
        </span>
      </button>
    `).join('');
    els.verifyListEmpty.hidden = rows.length > 0;
  }

  function renderVerificationDetail() {
    const claim = CLAIMS.find((item) => item.id === state.verificationClaim);
    if (!claim) {
      els.verifyDetailBody.innerHTML = '';
      els.verifyDetailEmpty.hidden = false;
      return;
    }
    els.verifyDetailEmpty.hidden = true;
    const verdictIcon = claim.status === 'verified' ? 'i-check-circle' : claim.status === 'unverified' ? 'i-clock' : claim.status === 'contradicted' ? 'i-x-circle' : 'i-minus-circle';
    const quote = claim.quote || '引用箇所はまだ登録されていません。根拠を追加すると、ここに引用が表示されます。';
    els.verifyDetailBody.innerHTML = `
      <div class="detail-head">
        <div>
          <p class="eyebrow">${esc(claim.id)} / ${esc(claim.owner)}</p>
          <h2>${esc(claim.title)}</h2>
        </div>
        ${statusBadge(claim.status)}
      </div>
      <div class="verify-body">
        <div class="verdict-box">
          <svg class="icon" aria-hidden="true"><use href="#${verdictIcon}"></use></svg>
          <div>
            <strong>判定: ${esc(claim.verdict)}</strong>
            <p>${esc(claim.verdictDesc)}</p>
          </div>
        </div>
        <div class="quote-box">
          <span class="evidence-label">根拠の引用箇所</span>
          <blockquote>「${esc(quote)}」</blockquote>
          <div class="quote-source">
            <svg class="icon" aria-hidden="true"><use href="#i-book-open"></use></svg>
            <span>${esc(claim.source)} / ${esc(claim.location)}</span>
          </div>
        </div>
        ${claim.reason ? `<div class="reason-box"><strong>不足理由・確認事項</strong><p>${esc(claim.reason)}</p></div>` : ''}
        <div class="source-line">
          <svg class="icon" aria-hidden="true"><use href="#i-hash"></use></svg>
          <span>根拠 ${claim.evidence} 件 / 参照 ${claim.refs.length ? claim.refs.map((ref) => esc(ref)).join(', ') : '未登録'}</span>
        </div>
        <div class="verify-actions">
          <button class="btn btn-secondary btn-sm requires-desktop" type="button" data-verify-current>再検証</button>
          <a class="link-button" href="#/editor">エディタで該当箇所を開く <svg class="icon" aria-hidden="true"><use href="#i-arrow-right"></use></svg></a>
        </div>
      </div>
    `;
  }

  async function rerunVerification(claimId, button) {
    if (!canEdit()) {
      setInlineFeedback(els.verifyFeedback, 'error', '検証を実行する権限がありません。');
      showToast('検証にはリサーチャー権限が必要です。', 'error');
      return;
    }
    const claim = CLAIMS.find((item) => item.id === claimId);
    if (!claim) {
      setInlineFeedback(els.verifyFeedback, 'error', '再検証するクレームを選択してください。');
      return;
    }
    setButtonLoading(button, true, '検証中…');
    setInlineFeedback(els.verifyFeedback, '');
    await sleepSafe(800);

    let message = '再検証しました。判定は支持のままです。';
    let type = 'success';
    if (claim.status === 'unverified') {
      claim.status = 'verified';
      claim.evidence = Math.max(claim.evidence, 2);
      claim.quote = claim.quote || '再検証時に一次資料の該当箇所を確認しました。';
      claim.verdict = '支持';
      claim.verdictDesc = '再検証の結果、引用箇所が主張を支持しています。';
      claim.reason = '';
      claim.source = claim.source === '未登録' ? 'IEA, Renewables 2024' : claim.source;
      claim.location = claim.location === '引用箇所未特定' ? '第 3 章 / p.86' : claim.location;
      if (['CLM-012', 'CLM-008'].includes(claim.id) && state.editorCounts.unverified > 0) {
        state.editorCounts.unverified -= 1;
        state.editorCounts.verified += 1;
      }
      message = '再検証が完了しました。判定を「支持」に更新しました。';
    } else if (claim.status === 'contradicted') {
      type = 'error';
      message = '矛盾が残っています。本文または根拠を修正してください。';
    } else if (claim.status === 'insufficient') {
      type = 'info';
      message = '追加の根拠が必要です。判定は変更されませんでした。';
    }

    if (button && document.body.contains(button)) setButtonLoading(button, false);
    if (type === 'error') setInlineFeedback(els.verifyFeedback, 'error', message);
    else setInlineFeedback(els.verifyFeedback, 'success', message);
    showToast(message, type);
    renderAll();
    updateSyncStatus();
    addAudit('検証', currentUser().name, claim.id, `再検証 / ${claim.status}`);
    applyRole();
  }

  function noteClaimVerified(claim) {
    if (claim.status === 'unverified') {
      claim.status = 'verified';
      claim.evidence = Math.max(claim.evidence, 2);
      claim.quote = claim.quote || '検証実行時に一次資料の該当箇所を確認しました。';
      claim.verdict = '支持';
      claim.verdictDesc = '検証済みの根拠が主張を支持しています。';
      claim.reason = '';
      claim.source = claim.source === '未登録' ? 'IEA, Renewables 2024' : claim.source;
      claim.location = claim.location === '引用箇所未特定' ? '第 3 章 / p.86' : claim.location;
      if (['CLM-012', 'CLM-008'].includes(claim.id) && state.editorCounts.unverified > 0) {
        state.editorCounts.unverified -= 1;
        state.editorCounts.verified += 1;
      }
    }
  }

  function renderEditorSummary() {
    const counts = state.editorCounts;
    els.editorSummaryVerified.textContent = counts.verified;
    els.editorSummaryUnverified.textContent = counts.unverified;
    els.editorSummaryContradicted.textContent = counts.contradicted;
    els.editorSummaryInsufficient.textContent = counts.insufficient;
    els.editorPillVerified.textContent = counts.verified;
    const attention = counts.unverified + counts.contradicted;
    els.editorPillAttention.textContent = attention;
    els.editorSummaryBadge.textContent = attention > 0 ? `要対応 ${attention}` : '提出可能';
    els.editorSummaryBadge.className = attention > 0 ? 'badge warning' : 'badge success';
    els.editorPillWarning.classList.toggle('warning', attention > 0);
    els.editorPillWarning.classList.toggle('success', attention === 0);
    els.editorPillWarning.querySelector('use').setAttribute('href', attention > 0 ? '#i-alert-triangle' : '#i-check-circle');
    if (state.reportSubmitted) {
      els.reportStatusBadge.className = 'status unverified';
      els.reportStatusBadge.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-clock"></use></svg>レビュー待ち';
    }
  }

  function renderEvidence() {
    const claim = CLAIMS.find((item) => item.id === state.evidenceClaim);
    if (!claim) {
      els.evidenceEmpty.hidden = false;
      els.evidenceContent.hidden = true;
      els.evidenceContent.innerHTML = '';
      return;
    }
    els.evidenceEmpty.hidden = true;
    els.evidenceContent.hidden = false;
    const refs = claim.refs.length
      ? claim.refs.map((ref) => `<li><svg class="icon" aria-hidden="true"><use href="#i-file-check"></use></svg><span><strong>${esc(SOURCE_NAMES[ref] || ref)}</strong><small>${esc(ref)} / スナップショット固定済み</small></span></li>`).join('')
      : '<li><svg class="icon" aria-hidden="true"><use href="#i-info"></use></svg><span><strong>根拠はまだ登録されていません</strong><small>出典を追加して検証を実行してください。</small></span></li>';
    els.evidenceContent.innerHTML = `
      <div class="evidence-kicker"><span class="mono">${esc(claim.id)}</span>${statusBadge(claim.status)}</div>
      <h3 class="evidence-claim-title">${esc(claim.title)}</h3>
      <div class="evidence-section">
        <span class="evidence-label">引用</span>
        <div class="evidence-quote"><svg class="icon" aria-hidden="true"><use href="#i-quote"></use></svg>${esc(claim.quote || '引用箇所はまだ登録されていません。')}</div>
      </div>
      <div class="evidence-section">
        <span class="evidence-label">出典</span>
        <div class="evidence-source"><strong>${esc(claim.source)}</strong><span>${esc(claim.location)}</span></div>
      </div>
      <div class="evidence-section">
        <span class="evidence-label">根拠 ${claim.evidence} 件</span>
        <ul class="evidence-list">${refs}</ul>
      </div>
      <div class="evidence-section">
        <span class="evidence-label">検証メモ</span>
        <p class="field-help">${esc(claim.reason || claim.verdictDesc)}</p>
      </div>
    `;
  }

  async function saveEditor() {
    if (!canEdit()) {
      setInlineFeedback(els.editorFeedback, 'error', '編集・保存にはリサーチャー権限が必要です。');
      return;
    }
    if (els.docBody.innerText.trim().length < 20) {
      setInlineFeedback(els.editorFeedback, 'error', '本文が空です。保存する内容を入力してください。');
      return;
    }
    setButtonLoading(els.editorSave, true, '保存中…');
    setInlineFeedback(els.editorFeedback, '');
    await sleepSafe(520);
    setButtonLoading(els.editorSave, false);
    applyRole();
    const now = nowParts();
    setSavedState(`保存済み ${now.time}`);
    setInlineFeedback(els.editorFeedback, 'success', 'レポートを保存しました。');
    showToast('レポートを保存しました。', 'success');
    updateSyncStatus();
    addAudit('保存', currentUser().name, 'RPT-021', '政策提言サマリーを保存');
  }

  async function verifyEditorClaims() {
    if (!canEdit()) {
      setInlineFeedback(els.editorFeedback, 'error', '検証にはリサーチャー権限が必要です。');
      return;
    }
    setButtonLoading(els.editorVerify, true, '検証中…');
    setInlineFeedback(els.editorFeedback, '');
    await sleepSafe(1000);
    const before = state.editorCounts.unverified;
    ['CLM-012', 'CLM-008'].forEach((id) => {
      const claim = CLAIMS.find((item) => item.id === id);
      if (claim) noteClaimVerified(claim);
    });
    state.editorCounts.unverified = Math.max(0, state.editorCounts.unverified);
    setButtonLoading(els.editorVerify, false);
    applyRole();
    renderAll();
    updateSyncStatus();
    addAudit('検証', currentUser().name, 'RPT-021', 'レポート全体の検証を実行');
    if (before > 0 || state.editorCounts.verified >= 12) {
      setInlineFeedback(els.editorFeedback, 'success', '検証が完了しました。要対応のクレームはありません。');
      showToast('検証が完了しました。要対応は 0 件です。', 'success');
    } else {
      setInlineFeedback(els.editorFeedback, 'success', '検証結果を更新しました。');
    }
  }

  async function submitEditor() {
    if (!canEdit()) {
      setInlineFeedback(els.editorFeedback, 'error', '提出にはリサーチャー権限が必要です。');
      return;
    }
    if (state.reportSubmitted) {
      setInlineFeedback(els.editorFeedback, 'success', 'このレポートはすでにレビューへ提出済みです。');
      showToast('このレポートは提出済みです。', 'info');
      return;
    }
    const attention = state.editorCounts.unverified + state.editorCounts.contradicted;
    if (attention > 0) {
      const message = `未検証または矛盾するクレームが ${attention} 件残っています。検証を実行してください。`;
      setInlineFeedback(els.editorFeedback, 'error', message);
      showToast(message, 'error');
      els.editorVerify.focus();
      return;
    }
    setButtonLoading(els.editorSubmit, true, '提出中…');
    setInlineFeedback(els.editorFeedback, '');
    await sleepSafe(720);
    state.reportSubmitted = true;
    setButtonLoading(els.editorSubmit, false);
    applyRole();
    els.reportStatusBadge.className = 'status unverified';
    els.reportStatusBadge.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-clock"></use></svg>レビュー待ち';
    addSubmittedReport();
    setInlineFeedback(els.editorFeedback, 'success', 'レビューに提出しました。承認待ちのキューに追加されました。');
    showToast('レビューに提出しました。', 'success');
    updateSyncStatus();
    addAudit('提出', currentUser().name, 'RPT-021', '政策提言サマリーを提出');
  }

  function addSubmittedReport() {
    const existing = REVIEW_ITEMS.find((item) => item.id === 'RPT-021');
    const now = nowParts();
    const total = state.editorCounts.verified + state.editorCounts.unverified + state.editorCounts.contradicted + state.editorCounts.insufficient;
    if (existing) {
      existing.status = 'pending';
      existing.submitted = `${now.date} ${now.time}`;
      existing.verified = state.editorCounts.verified;
      existing.total = total;
      existing.insufficient = state.editorCounts.insufficient;
    } else {
      REVIEW_ITEMS.unshift({
        id: 'RPT-021',
        title: '政策提言サマリー',
        theme: '再生可能エネルギー政策の根拠調査',
        author: currentUser().name,
        submitted: `${now.date} ${now.time}`,
        status: 'pending',
        verified: state.editorCounts.verified,
        total,
        insufficient: state.editorCounts.insufficient,
        summary: '再生可能エネルギー政策の根拠調査を踏まえ、導入目標・系統接続・地域合意の論点を整理した政策提言サマリー。',
        excerpt: '本稿は、2030 年までの電源構成をめぐる主要な主張を一次資料に接続し、政策提言の根拠を整理する。洋上風力と太陽光発電の導入見通しを中心に、系統制約と地域合意の論点を確認する。',
        comments: []
      });
    }
    renderReview();
  }

  function renderAll() {
    renderClaimsTable();
    renderThemeClaims();
    renderVerification();
    renderEditorSummary();
    renderEvidence();
    renderReview();
  }

  function setReviewTab(tab) {
    state.reviewTab = tab;
    els.reviewTabs.forEach((item) => {
      const active = item.dataset.reviewTab === tab;
      item.classList.toggle('is-active', active);
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
    });
    const first = REVIEW_ITEMS.find((item) => item.status === tab);
    state.reviewItemId = first ? first.id : null;
    renderReview();
  }

  function renderReview() {
    const counts = {
      pending: REVIEW_ITEMS.filter((item) => item.status === 'pending').length,
      returned: REVIEW_ITEMS.filter((item) => item.status === 'returned').length,
      approved: REVIEW_ITEMS.filter((item) => item.status === 'approved').length
    };
    els.reviewCountPending.textContent = counts.pending;
    els.reviewCountReturned.textContent = counts.returned;
    els.reviewCountApproved.textContent = counts.approved;
    const badge = $('#screen-review .page-actions .badge');
    if (badge) {
      badge.textContent = `承認待ち ${counts.pending} 件`;
      badge.className = counts.pending > 0 ? 'badge warning' : 'badge success';
    }

    const visible = REVIEW_ITEMS.filter((item) => item.status === state.reviewTab);
    if (state.reviewItemId) {
      const selected = REVIEW_ITEMS.find((item) => item.id === state.reviewItemId);
      if (!selected || selected.status !== state.reviewTab) state.reviewItemId = null;
    }
    if (!state.reviewItemId && visible.length) state.reviewItemId = visible[0].id;
    if (!visible.length) state.reviewItemId = null;

    els.reviewList.innerHTML = visible.map((item) => `
      <button class="review-item${item.id === state.reviewItemId ? ' is-active' : ''}" type="button" data-review-id="${esc(item.id)}">
        <span class="review-item-top"><strong>${esc(item.title)}</strong><span>${esc(item.id)}</span></span>
        <span>${esc(item.theme)} / ${esc(item.author)}</span>
        <span>${esc(item.submitted)} · ${statusLabel(item.status)}</span>
      </button>
    `).join('');
    els.reviewListEmpty.hidden = visible.length > 0;

    const item = REVIEW_ITEMS.find((entry) => entry.id === state.reviewItemId);
    if (!item) {
      els.reviewDetailBody.innerHTML = '';
      els.reviewDetailEmpty.hidden = false;
      return;
    }
    els.reviewDetailEmpty.hidden = true;
    renderReviewDetail(item);
  }

  function statusLabel(status) {
    if (status === 'pending') return '承認待ち';
    if (status === 'returned') return '差し戻し';
    if (status === 'approved') return '承認済み';
    return status;
  }

  function renderReviewDetail(item) {
    const comments = item.comments.length
      ? item.comments.map((comment) => `
        <div class="comment">
          <span class="avatar comment-avatar" aria-hidden="true">${esc(initialsFor(comment.author))}</span>
          <div class="comment-body">
            <div class="comment-head"><strong>${esc(comment.author)}</strong><span>${esc(comment.role)} / ${esc(comment.time)}</span></div>
            <p>${esc(comment.text)}</p>
          </div>
        </div>
      `).join('')
      : '<p class="field-help">まだコメントはありません。</p>';

    const actionBlock = item.status === 'approved'
      ? '<div class="inline-success"><svg class="icon" aria-hidden="true"><use href="#i-check-circle"></use></svg><span>このレポートは承認済みです。</span></div>'
      : canReview()
        ? `
          <div class="review-action-card">
            <h3>レビュー判断 <span class="required">コメント必須</span></h3>
            <div class="field">
              <label class="field-label" for="review-comment">レビューコメント</label>
              <textarea class="textarea" id="review-comment" rows="4" placeholder="判断の理由、修正点、確認した根拠を記録してください。" aria-describedby="review-comment-help"></textarea>
              <p class="field-help" id="review-comment-help">承認・差し戻しのいずれにもコメントが必要です。</p>
              <p class="field-error" id="review-comment-error" hidden></p>
            </div>
            <div class="review-action-row">
              <button class="btn btn-secondary" type="button" data-review-action="return"><svg class="icon" aria-hidden="true"><use href="#i-rotate-ccw"></use></svg>差し戻す</button>
              <button class="btn btn-primary" type="button" data-review-action="approve"><svg class="icon" aria-hidden="true"><use href="#i-check-circle"></use></svg>承認する</button>
            </div>
            <div class="confirm-box" id="review-confirm-box" hidden>
              <strong>このレポートを差し戻しますか？</strong>
              <p>入力したコメントが作成者に通知されます。</p>
              <div class="review-action-row">
                <button class="btn btn-secondary btn-sm" type="button" data-review-action="cancel-return">キャンセル</button>
                <button class="btn btn-danger btn-sm" type="button" data-review-action="confirm-return">差し戻しを確定</button>
              </div>
            </div>
          </div>
        `
        : `<div class="role-note"><svg class="icon" aria-hidden="true"><use href="#i-lock"></use></svg><span>${isMobile() ? 'モバイルでは閲覧のみです。承認・差し戻しは PC のレビュアー権限で行ってください。' : '承認・差し戻しにはレビュアー権限が必要です。現在の権限では閲覧のみ行えます。'}</span></div>`;

    els.reviewDetailBody.innerHTML = `
      <div class="review-doc">
        <p class="eyebrow">${esc(item.id)} / ${statusLabel(item.status)}</p>
        <h2>${esc(item.title)}</h2>
        <div class="review-meta">
          <span>${esc(item.theme)}</span><span class="dot" aria-hidden="true"></span><span>${esc(item.author)}</span><span class="dot" aria-hidden="true"></span><span>提出 ${esc(item.submitted)}</span>
        </div>
        <p class="review-excerpt">${esc(item.summary)}</p>
        <div class="review-summary">
          <div class="summary-cell"><strong>${item.verified}</strong><span>検証済み</span></div>
          <div class="summary-cell"><strong>${Math.max(0, item.total - item.verified - item.insufficient)}</strong><span>未検証</span></div>
          <div class="summary-cell"><strong>${item.insufficient}</strong><span>根拠不足</span></div>
        </div>
      </div>
      <div class="review-comments">
        <h3>コメント履歴</h3>
        <div class="comment-thread">${comments}</div>
      </div>
      <div class="review-actions requires-desktop">
        ${actionBlock}
      </div>
    `;
  }

  function initialsFor(name) {
    return String(name).split(/\s+/).map((part) => part.charAt(0)).join('').slice(0, 2);
  }

  function handleReviewClick(event) {
    const button = event.target.closest('[data-review-action]');
    if (!button) return;
    const action = button.dataset.reviewAction;
    const item = REVIEW_ITEMS.find((entry) => entry.id === state.reviewItemId);
    if (!item) return;
    if (!canReview()) {
      setInlineFeedback(els.reviewFeedback, 'error', '承認・差し戻しにはレビュアー権限が必要です。');
      return;
    }
    const textarea = $('#review-comment');
    const comment = textarea ? textarea.value.trim() : '';
    const commentError = $('#review-comment-error');

    if (action === 'cancel-return') {
      const box = $('#review-confirm-box');
      if (box) box.hidden = true;
      return;
    }
    if (!comment) {
      if (commentError) {
        commentError.textContent = 'レビューコメントを入力してください。判断の理由を記録する必要があります。';
        commentError.hidden = false;
      }
      if (textarea) {
        textarea.setAttribute('aria-invalid', 'true');
        textarea.focus();
      }
      setInlineFeedback(els.reviewFeedback, 'error', 'コメントなしでは承認・差し戻しできません。');
      return;
    }
    if (textarea) textarea.removeAttribute('aria-invalid');
    if (action === 'return') {
      const box = $('#review-confirm-box');
      if (box) {
        box.hidden = false;
        const confirm = box.querySelector('[data-review-action="confirm-return"]');
        if (confirm) confirm.focus();
      }
      return;
    }
    if (action === 'confirm-return') {
      completeReview(item, 'returned', comment, button);
      return;
    }
    if (action === 'approve') {
      completeReview(item, 'approved', comment, button);
    }
  }

  async function completeReview(item, nextStatus, comment, button) {
    const actionLabel = nextStatus === 'approved' ? '承認' : '差し戻し';
    setButtonLoading(button, true, `${actionLabel}中…`);
    setInlineFeedback(els.reviewFeedback, '');
    await sleepSafe(720);
    item.status = nextStatus;
    const now = nowParts();
    item.comments.push({
      author: currentUser().name,
      role: currentUser().label,
      time: now.time,
      text: comment
    });
    addAudit(actionLabel, currentUser().name, item.id, `${item.title} / コメント付き${actionLabel}`);
    state.reviewItemId = null;
    renderReview();
    updateSyncStatus();
    showToast(`${actionLabel}しました。`, 'success');
  }

  function renderAudit() {
    const action = els.auditActionFilter.value;
    const actor = els.auditActorFilter.value;
    const from = els.auditFrom.value;
    const to = els.auditTo.value;
    const query = normalize(els.auditSearch.value);
    const rows = AUDIT_ROWS.filter((row) => {
      const actionMatch = !action || row.action === action;
      const actorMatch = !actor || row.actor === actor;
      const dateMatch = (!from || row.date >= from) && (!to || row.date <= to);
      const textMatch = !query || normalize(`${row.target} ${row.detail} ${row.action} ${row.actor}`).includes(query);
      return actionMatch && actorMatch && dateMatch && textMatch;
    });
    els.auditBody.innerHTML = rows.map((row) => `
      <tr>
        <td data-label="時刻"><span class="audit-time">${esc(row.time)}</span><span class="cell-sub">${esc(row.date)}</span></td>
        <td data-label="操作"><span class="audit-action"><svg class="icon" aria-hidden="true"><use href="#${auditIcon(row.action)}"></use></svg>${esc(row.action)}</span></td>
        <td data-label="実行者">${esc(row.actor)}</td>
        <td data-label="対象"><span class="audit-target">${esc(row.target)}</span></td>
        <td data-label="詳細"><span class="audit-detail">${esc(row.detail)}</span></td>
      </tr>
    `).join('');
    els.auditEmpty.hidden = rows.length > 0;
    els.auditResultCount.textContent = `${rows.length} 件`;
    els.auditPageInfo.textContent = `${rows.length ? `1–${rows.length}` : '0'} / ${rows.length} 件`;
  }

  function auditIcon(action) {
    const map = {
      '検証': 'i-verify',
      '保存': 'i-save',
      '提出': 'i-send',
      '承認': 'i-check-circle',
      '差し戻し': 'i-rotate-ccw',
      '出典登録': 'i-link',
      '権限変更': 'i-users',
      '設定変更': 'i-settings',
      '閲覧': 'i-eye'
    };
    return map[action] || 'i-audit';
  }

  async function applyAuditFilters() {
    const from = els.auditFrom.value;
    const to = els.auditTo.value;
    if (from && to && from > to) {
      setInlineFeedback(els.auditFeedback, 'error', '開始日は終了日以前にしてください。');
      els.auditFrom.focus();
      return;
    }
    setButtonLoading(els.auditApply, true, '適用中…');
    setInlineFeedback(els.auditFeedback, '');
    await sleepSafe(300);
    setButtonLoading(els.auditApply, false);
    renderAudit();
    showToast('監査ログを更新しました。', 'success');
  }

  function clearAuditFilters() {
    els.auditActionFilter.value = '';
    els.auditActorFilter.value = '';
    els.auditFrom.value = '2026-10-01';
    els.auditTo.value = '2026-11-02';
    els.auditSearch.value = '';
    setInlineFeedback(els.auditFeedback, '');
    renderAudit();
  }

  async function refreshAudit() {
    setButtonLoading(els.auditRefresh, true, '更新中…');
    setInlineFeedback(els.auditFeedback, '');
    await sleepSafe(400);
    setButtonLoading(els.auditRefresh, false);
    renderAudit();
    updateSyncStatus();
    showToast('監査ログを更新しました。', 'success');
  }

  function addAudit(action, actor, target, detail) {
    const now = nowParts();
    AUDIT_ROWS.unshift({
      id: `A-${Date.now()}`,
      date: now.date,
      time: now.time,
      action,
      actor,
      target,
      detail
    });
    if (AUDIT_ROWS.length > 60) AUDIT_ROWS.length = 60;
    if (state.currentScreen === 'audit') renderAudit();
  }

  function filterThemes() {
    const query = normalize(els.themeSearch.value);
    const status = els.themeStatusFilter.value;
    const rows = $$('#themes-table tbody tr');
    let visible = 0;
    rows.forEach((row) => {
      const text = normalize(row.textContent);
      const match = (!query || text.includes(query)) && (!status || row.dataset.status === status);
      row.hidden = !match;
      if (match) visible += 1;
    });
    els.themesEmpty.hidden = visible > 0;
  }

  function filterSources() {
    const query = normalize(els.sourceSearch.value);
    const rows = $$('#sources-table tbody tr');
    let visible = 0;
    rows.forEach((row) => {
      const text = normalize(`${row.dataset.search || ''} ${row.textContent}`);
      const match = !query || text.includes(query);
      row.hidden = !match;
      if (match) visible += 1;
    });
    els.sourcesEmpty.hidden = visible > 0;
  }

  function filterReports() {
    const status = els.reportStatusFilter.value;
    const rows = $$('#reports-table tbody tr');
    let visible = 0;
    rows.forEach((row) => {
      const match = !status || row.dataset.status === status;
      row.hidden = !match;
      if (match) visible += 1;
    });
    els.reportsEmpty.hidden = visible > 0;
  }

  function openSourceDialog() {
    if (!canEdit()) {
      showToast('出典の登録はリサーチャー権限が必要です。', 'error');
      return;
    }
    resetSourceDialog();
    if (typeof els.sourceDialog.showModal === 'function') {
      if (!els.sourceDialog.open) els.sourceDialog.showModal();
    } else {
      els.sourceDialog.setAttribute('open', '');
    }
    window.setTimeout(() => els.sourceUrl.focus(), 30);
  }

  function closeSourceDialog() {
    state.pendingSource = null;
    if (typeof els.sourceDialog.close === 'function') els.sourceDialog.close();
    else els.sourceDialog.removeAttribute('open');
    setButtonLoading(els.sourceSave, false);
  }

  function resetSourceDialog() {
    state.sourceTab = 'url';
    setSourceTab('url', false);
    els.sourceUrl.value = '';
    els.sourceDoi.value = '';
    els.sourceText.value = '';
    els.sourceError.hidden = true;
    els.sourceSuccess.hidden = true;
    els.sourcePreviewEmpty.hidden = false;
    els.sourcePreviewLoading.hidden = true;
    els.sourcePreviewContent.hidden = true;
    els.sourcePreviewType.textContent = '未取得';
    els.sourceSave.disabled = true;
    state.pendingSource = null;
  }

  function invalidateSourcePreview() {
    state.pendingSource = null;
    els.sourceSave.disabled = true;
    els.sourcePreviewEmpty.hidden = false;
    els.sourcePreviewLoading.hidden = true;
    els.sourcePreviewContent.hidden = true;
    els.sourcePreviewType.textContent = '未取得';
  }

  function setSourceTab(tab, resetPreview = true) {
    state.sourceTab = tab;
    els.sourceTabs.forEach((item) => {
      const active = item.dataset.sourceTab === tab;
      item.classList.toggle('is-active', active);
      item.setAttribute('aria-selected', String(active));
      item.tabIndex = active ? 0 : -1;
    });
    els.sourcePanels.forEach((panel) => {
      const active = panel.dataset.sourcePanel === tab;
      panel.hidden = !active;
    });
    if (resetPreview) {
      els.sourceError.hidden = true;
      els.sourceSuccess.hidden = true;
      invalidateSourcePreview();
    }
    const input = tab === 'url' ? els.sourceUrl : tab === 'doi' ? els.sourceDoi : els.sourceText;
    if (input) window.setTimeout(() => input.focus(), 10);
  }

  async function fetchSourcePreview(event) {
    const button = event.currentTarget;
    const tab = state.sourceTab;
    const value = tab === 'url' ? els.sourceUrl.value.trim() : tab === 'doi' ? els.sourceDoi.value.trim() : els.sourceText.value.trim();
    const result = buildSourceData(tab, value);
    els.sourceError.hidden = true;
    els.sourceSuccess.hidden = true;

    if (result.error) {
      invalidateSourcePreview();
      els.sourceError.textContent = result.error;
      els.sourceError.hidden = false;
      const input = tab === 'url' ? els.sourceUrl : tab === 'doi' ? els.sourceDoi : els.sourceText;
      input.focus();
      return;
    }

    invalidateSourcePreview();

    setButtonLoading(button, true, '取得中…');
    els.sourcePreviewEmpty.hidden = true;
    els.sourcePreviewContent.hidden = true;
    els.sourcePreviewLoading.hidden = false;

    await sleepSafe(680);

    setButtonLoading(button, false);
    if (!els.sourceDialog.open) return;

    const hash = sha256Hex(result.snapshot);
    state.pendingSource = {
      ...result,
      hash,
      id: `SRC-${String(state.nextSourceNumber).padStart(3, '0')}`
    };
    els.sourcePreviewLoading.hidden = true;
    els.sourcePreviewEmpty.hidden = true;
    els.sourcePreviewContent.hidden = false;
    els.sourcePreviewType.textContent = result.type;
    els.sourcePreviewName.textContent = result.name;
    els.sourcePreviewPublisher.textContent = result.publisher;
    els.sourcePreviewYear.textContent = result.year;
    els.sourcePreviewHash.textContent = hash;
    els.sourceSave.disabled = false;
    els.sourceSuccess.hidden = false;
    showToast('メタデータとスナップショットを取得しました。', 'success');
  }

  function buildSourceData(tab, value) {
    if (!value) {
      return { error: tab === 'text' ? '引用テキストを入力してください。' : tab === 'doi' ? 'DOI を入力してください。' : 'URL を入力してください。' };
    }
    if (tab === 'url') {
      let url;
      try {
        url = new URL(value);
      } catch (error) {
        return { error: 'URL の形式が正しくありません。https:// で始まる URL を入力してください。' };
      }
      if (!['http:', 'https:'].includes(url.protocol)) {
        return { error: 'URL は http:// または https:// で始めてください。' };
      }
      return {
        name: `${url.hostname} のページスナップショット`,
        publisher: url.hostname,
        year: nowParts().date.slice(0, 4),
        type: 'Web ページ',
        snapshot: `URL: ${value}\nRetrieved: ${nowParts().date} ${nowParts().time}\nHost: ${url.hostname}`
      };
    }
    if (tab === 'doi') {
      if (!/^10\.\d{4,9}\/\S+$/i.test(value)) {
        return { error: 'DOI の形式が正しくありません。10. で始まる DOI を入力してください。' };
      }
      return {
        name: `DOI 文献スナップショット: ${value}`,
        publisher: 'CrossRef メタデータ',
        year: '2024',
        type: '論文',
        snapshot: `DOI: ${value}\nResolver: https://doi.org/${value}\nRetrieved: ${nowParts().date}`
      };
    }
    if (value.length < 20) {
      return { error: '引用テキストは 20 文字以上で入力してください。' };
    }
    return {
      name: value.slice(0, 42) + (value.length > 42 ? '…' : ''),
      publisher: 'ユーザー貼付',
      year: nowParts().date.slice(0, 4),
      type: '引用テキスト',
      snapshot: value
    };
  }

  async function saveSource() {
    if (!state.pendingSource) {
      els.sourceError.textContent = '先にメタデータを取得してください。';
      els.sourceError.hidden = false;
      return;
    }
    setButtonLoading(els.sourceSave, true, '登録中…');
    await sleepSafe(520);
    const source = state.pendingSource;
    addSourceRow(source);
    setButtonLoading(els.sourceSave, false);
    closeSourceDialog();
    addAudit('出典登録', currentUser().name, source.id, `${source.name} / SHA-256 固定`);
    showToast('出典を登録しました。スナップショットのハッシュを固定しました。', 'success');
    updateSyncStatus();
    if (location.hash !== '#/theme/sources') location.hash = '#/theme/sources';
    else {
      setThemeTab('sources', false);
      filterSources();
    }
  }

  function addSourceRow(source) {
    const tbody = $('#sources-table tbody');
    if (!tbody) return;
    const shortHash = `${source.hash.slice(0, 4)}…${source.hash.slice(-4)}`;
    const row = document.createElement('tr');
    row.dataset.search = `${source.name} ${source.publisher} ${source.id}`;
    row.innerHTML = `
      <td data-label="出典"><span class="table-title">${esc(source.name)}</span><span class="cell-sub">${esc(source.publisher)} / ${esc(source.year)} / ${esc(source.id)}</span></td>
      <td data-label="種別"><span class="badge neutral">${esc(source.type)}</span></td>
      <td data-label="登録"><span class="od-nowrap">${esc(nowParts().date)}</span></td>
      <td data-label="SHA-256"><button class="hash-copy" type="button" data-copy="${esc(source.hash)}"><code class="hash">${esc(shortHash)}</code><svg class="icon" aria-hidden="true"><use href="#i-copy"></use></svg><span class="visually-hidden">ハッシュをコピー</span></button></td>
      <td data-label="操作"><a class="link-button" href="#/verification">検証を見る</a></td>
    `;
    tbody.prepend(row);
    state.sourceCount += 1;
    state.nextSourceNumber += 1;
    els.themeSourceCount.textContent = `${state.sourceCount} 件`;
    const tabCount = $('#theme-tab-sources .tab-count');
    if (tabCount) tabCount.textContent = state.sourceCount;
    filterSources();
  }

  async function copyText(text) {
    if (!text) return;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        fallbackCopy(text);
      }
      showToast('クリップボードにコピーしました。', 'success');
    } catch (error) {
      try {
        fallbackCopy(text);
        showToast('クリップボードにコピーしました。', 'success');
      } catch (fallbackError) {
        showToast('コピーできませんでした。テキストを選択してコピーしてください。', 'error');
      }
    }
  }

  function fallbackCopy(text) {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '-1000px';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    area.remove();
    if (!ok) throw new Error('copy failed');
  }

  function sha256Hex(text) {
    const bytes = new TextEncoder().encode(text);
    return sha256Bytes(bytes);
  }

  function sha256Bytes(bytes) {
    const K = [
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
      0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
      0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
      0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
      0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
    ];
    const H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    const bitLength = bytes.length * 8;
    const paddedLength = ((bytes.length + 9 + 63) >> 6) << 6;
    const data = new Uint8Array(paddedLength);
    data.set(bytes);
    data[bytes.length] = 0x80;
    const view = new DataView(data.buffer);
    view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000), false);
    view.setUint32(paddedLength - 4, bitLength >>> 0, false);
    const h = H.slice();
    const w = new Uint32Array(64);
    const rotr = (value, amount) => (value >>> amount) | (value << (32 - amount));
    for (let offset = 0; offset < paddedLength; offset += 64) {
      for (let i = 0; i < 16; i += 1) w[i] = view.getUint32(offset + i * 4, false);
      for (let i = 16; i < 64; i += 1) {
        const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
        const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, hh] = h;
      for (let i = 0; i < 64; i += 1) {
        const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        const ch = (e & f) ^ (~e & g);
        const temp1 = (hh + S1 + ch + K[i] + w[i]) >>> 0;
        const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        const maj = (a & b) ^ (a & c) ^ (b & c);
        const temp2 = (S0 + maj) >>> 0;
        hh = g;
        g = f;
        f = e;
        e = (d + temp1) >>> 0;
        d = c;
        c = b;
        b = a;
        a = (temp1 + temp2) >>> 0;
      }
      h[0] = (h[0] + a) >>> 0;
      h[1] = (h[1] + b) >>> 0;
      h[2] = (h[2] + c) >>> 0;
      h[3] = (h[3] + d) >>> 0;
      h[4] = (h[4] + e) >>> 0;
      h[5] = (h[5] + f) >>> 0;
      h[6] = (h[6] + g) >>> 0;
      h[7] = (h[7] + hh) >>> 0;
    }
    return h.map((value) => value.toString(16).padStart(8, '0')).join('');
  }
})();
