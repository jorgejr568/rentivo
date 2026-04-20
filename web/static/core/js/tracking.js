/* Rentivo GTM tracking wiring.
 *
 * No-ops when window.dataLayer is missing (i.e. GTM disabled).
 * Wires automatic listeners for:
 *   - form_start, form_submit, form_field_error, form_abandon
 *   - button_click, link_click, outbound_link_click, download_click, dropdown_open/close
 *   - file_upload_start, file_upload_complete, file_upload_error
 *   - web_vital (via vendored web-vitals IIFE), slow_page, interaction_slow, layout_shift_bad
 *   - long_task
 *   - js_error, promise_rejection, network_error
 *   - scroll_depth, page_engaged, page_idle, time_on_page
 *   - rage_click
 *
 * Never pushes PII into dataLayer. See
 * docs/superpowers/specs/2026-04-19-gtm-analytics-design.md.
 */
(function () {
  'use strict';

  if (!window.dataLayer) return;
  var dl = window.dataLayer;
  var push = function (evt) {
    try {
      dl.push(evt);
    } catch (e) {
      /* tracking must never break the page */
    }
  };

  /* ---------- helpers ---------- */

  function pagePath() {
    return location.pathname;
  }

  function pageTemplate() {
    for (var i = 0; i < dl.length; i++) {
      if (dl[i] && dl[i].event === 'page_context' && dl[i].page_template) {
        return dl[i].page_template;
      }
    }
    return null;
  }

  var UUID_RE = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/g;
  var ULID_RE = /\b[0-9A-HJKMNP-TV-Z]{26}\b/g;
  var NUM_SEG_RE = /\/\d+(?=\/|$)/g;

  function sanitizeUrl(url) {
    if (!url) return url;
    try {
      var u = new URL(url, location.origin);
      return u.pathname
        .replace(UUID_RE, ':uuid')
        .replace(ULID_RE, ':ulid')
        .replace(NUM_SEG_RE, '/:id');
    } catch (e) {
      return String(url)
        .replace(UUID_RE, ':uuid')
        .replace(ULID_RE, ':ulid')
        .replace(NUM_SEG_RE, '/:id');
    }
  }

  function elementText(el) {
    if (!el) return '';
    var t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
    return t.length > 80 ? t.slice(0, 80) : t;
  }

  function elementPath(el) {
    if (!el) return '';
    var parts = [];
    var node = el;
    var depth = 0;
    while (node && node.nodeType === 1 && depth < 5) {
      var part = node.nodeName.toLowerCase();
      if (node.id) {
        part += '#' + node.id;
        parts.unshift(part);
        break;
      } else if (node.className && typeof node.className === 'string') {
        part += '.' + node.className.trim().split(/\s+/).slice(0, 2).join('.');
      }
      parts.unshift(part);
      node = node.parentNode;
      depth++;
    }
    return parts.join('>');
  }

  function linkType(href) {
    if (!href) return 'unknown';
    if (href.indexOf('mailto:') === 0) return 'mailto';
    if (href.indexOf('tel:') === 0) return 'tel';
    try {
      var u = new URL(href, location.href);
      if (u.origin !== location.origin) return 'outbound';
      var p = u.pathname;
      if (/\/invoice$/.test(p)) return 'download';
      if (/\/receipts\/[^/]+$/.test(p)) return 'download';
      return 'internal';
    } catch (e) {
      return 'internal';
    }
  }

  function fileKind(href) {
    if (/\/invoice$/.test(href)) return 'invoice';
    if (/\/receipts\/[^/]+$/.test(href)) return 'receipt';
    return 'other';
  }

  /* ---------- form tracking ---------- */

  var formsStarted = new Set();
  var formStartTimes = new WeakMap();
  var formsSubmitted = new WeakSet();

  function formName(form) {
    if (form.getAttribute('name')) return form.getAttribute('name');
    if (form.id) return form.id;
    var action = form.getAttribute('action') || pagePath();
    return sanitizeUrl(action);
  }

  document.addEventListener(
    'focusin',
    function (e) {
      var form = e.target && e.target.form;
      if (!form || formsStarted.has(form)) return;
      formsStarted.add(form);
      formStartTimes.set(form, Date.now());
      push({
        event: 'form_start',
        form_name: formName(form),
        form_action: sanitizeUrl(form.getAttribute('action') || pagePath()),
        page_template: pageTemplate()
      });
    },
    true
  );

  document.addEventListener(
    'submit',
    function (e) {
      var form = e.target;
      if (!form || form.tagName !== 'FORM') return;
      formsSubmitted.add(form);
      var started = formStartTimes.get(form) || Date.now();
      push({
        event: 'form_submit',
        form_name: formName(form),
        field_count: form.elements ? form.elements.length : 0,
        time_to_submit_ms: Date.now() - started,
        page_template: pageTemplate()
      });
      try {
        sessionStorage.setItem('_slow_form_submit_start', String(Date.now()));
        sessionStorage.setItem('_slow_form_submit_name', formName(form));
      } catch (e2) {
        /* session storage unavailable */
      }
    },
    true
  );

  function scanFieldErrors() {
    var errs = document.querySelectorAll('.invalid-feedback, .field-error, [aria-invalid="true"]');
    errs.forEach(function (el) {
      var form = el.closest('form');
      var field = el.closest('.form-group, [data-field]');
      var fieldName =
        (field && (field.dataset.field || (field.querySelector('[name]') || {}).name)) ||
        'unknown';
      push({
        event: 'form_field_error',
        form_name: form ? formName(form) : null,
        field_name: fieldName,
        error_type: 'server',
        page_template: pageTemplate()
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scanFieldErrors);
  } else {
    scanFieldErrors();
  }

  window.addEventListener('beforeunload', function () {
    formsStarted.forEach(function (form) {
      if (!formsSubmitted.has(form)) {
        push({
          event: 'form_abandon',
          form_name: formName(form),
          time_on_form_ms: Date.now() - (formStartTimes.get(form) || Date.now()),
          page_template: pageTemplate()
        });
      }
    });
  });

  try {
    var slowStart = sessionStorage.getItem('_slow_form_submit_start');
    if (slowStart) {
      var elapsed = Date.now() - parseInt(slowStart, 10);
      if (elapsed > 3000) {
        push({
          event: 'slow_form_submit',
          form_name: sessionStorage.getItem('_slow_form_submit_name') || 'unknown',
          duration_ms: elapsed,
          page_template: pageTemplate()
        });
      }
      sessionStorage.removeItem('_slow_form_submit_start');
      sessionStorage.removeItem('_slow_form_submit_name');
    }
  } catch (e) {
    /* session storage unavailable */
  }

  /* ---------- click tracking ---------- */

  document.addEventListener(
    'click',
    function (e) {
      var el = e.target;
      if (!el) return;

      var btn = el.closest('button, [role=button]');
      if (btn) {
        push({
          event: 'button_click',
          element_id: btn.id || null,
          element_text: elementText(btn),
          element_class:
            btn.className && typeof btn.className === 'string'
              ? btn.className.slice(0, 100)
              : null,
          page_template: pageTemplate()
        });
      }

      var link = el.closest('a[href]');
      if (link) {
        var href = link.getAttribute('href');
        var type = linkType(href);
        push({
          event: 'link_click',
          href: type === 'outbound' ? href : sanitizeUrl(href),
          link_type: type,
          link_text: elementText(link),
          page_template: pageTemplate()
        });
        if (type === 'outbound') {
          push({ event: 'outbound_link_click', href: href, page_template: pageTemplate() });
        }
        if (type === 'download') {
          push({
            event: 'download_click',
            file_kind: fileKind(href),
            path: sanitizeUrl(href),
            page_template: pageTemplate()
          });
        }
      }

      var ddBtn = el.closest('.topbar-dropdown-toggle');
      if (ddBtn) {
        var expanded = ddBtn.getAttribute('aria-expanded') === 'true';
        push({
          event: expanded ? 'dropdown_close' : 'dropdown_open',
          dropdown_name: ddBtn.textContent.trim().slice(0, 40),
          page_template: pageTemplate()
        });
      }
    },
    true
  );

  /* ---------- rage clicks ---------- */

  var clickLog = [];
  document.addEventListener(
    'click',
    function (e) {
      var now = Date.now();
      var p = elementPath(e.target);
      clickLog = clickLog.filter(function (entry) {
        return now - entry.t < 1000;
      });
      clickLog.push({ t: now, p: p });
      if (
        clickLog.length >= 3 &&
        clickLog.slice(-3).every(function (x) {
          return x.p === p;
        })
      ) {
        push({
          event: 'rage_click',
          element_path: p,
          click_count: 3,
          time_span_ms: now - clickLog[clickLog.length - 3].t,
          page_template: pageTemplate()
        });
        clickLog = [];
      }
    },
    true
  );

  /* ---------- file upload tracking ---------- */

  document.addEventListener(
    'change',
    function (e) {
      var el = e.target;
      if (!el || el.type !== 'file') return;
      var files = el.files || [];
      for (var i = 0; i < files.length; i++) {
        var f = files[i];
        push({
          event: 'file_upload_start',
          form_name: el.form ? formName(el.form) : null,
          file_size_bytes: f.size,
          file_type: f.type || 'unknown',
          file_extension: (f.name.split('.').pop() || '').toLowerCase(),
          page_template: pageTemplate()
        });
      }
    },
    true
  );

  (function scanUploadFlashes() {
    var toasts = document.querySelectorAll('.toast');
    toasts.forEach(function (t) {
      var txt = (t.textContent || '').toLowerCase();
      if (txt.indexOf('comprovante') === -1) return;
      if (t.classList.contains('toast--success')) {
        push({
          event: 'file_upload_complete',
          result: 'success',
          page_template: pageTemplate()
        });
      } else if (t.classList.contains('toast--danger')) {
        var errCode = 'server_error';
        if (/muito grande|excede|tamanho/.test(txt)) errCode = 'size_limit';
        else if (/formato|tipo|inv[aá]lido/.test(txt)) errCode = 'type_rejected';
        push({
          event: 'file_upload_error',
          error_code: errCode,
          page_template: pageTemplate()
        });
      }
    });
  })();

  /* ---------- performance ---------- */

  if (window.PerformanceObserver) {
    try {
      var longCount = 0;
      var ltObs = new PerformanceObserver(function (list) {
        list.getEntries().forEach(function (entry) {
          if (longCount >= 10) return;
          if (entry.duration > 50) {
            longCount++;
            push({
              event: 'long_task',
              duration_ms: Math.round(entry.duration),
              start_time: Math.round(entry.startTime),
              page_template: pageTemplate()
            });
          }
        });
      });
      ltObs.observe({ type: 'longtask', buffered: true });
    } catch (e) {
      /* longtask type not supported */
    }
  }

  if (window.webVitals) {
    var sendVital = function (m) {
      var value = m.name === 'CLS' ? Math.round(m.value * 1000) : Math.round(m.value);
      push({
        event: 'web_vital',
        metric_name: m.name,
        metric_value: value,
        metric_rating: m.rating,
        metric_id: m.id,
        navigation_type: m.navigationType,
        page_template: pageTemplate()
      });
      if (m.rating === 'poor') {
        if (m.name === 'LCP' || m.name === 'TTFB' || m.name === 'FCP') {
          push({
            event: 'slow_page',
            metric_name: m.name,
            metric_value: value,
            page_template: pageTemplate()
          });
        }
        if (m.name === 'INP') {
          push({
            event: 'interaction_slow',
            metric_value: value,
            page_template: pageTemplate()
          });
        }
        if (m.name === 'CLS') {
          push({
            event: 'layout_shift_bad',
            metric_value: value,
            page_template: pageTemplate()
          });
        }
      }
    };
    try {
      window.webVitals.onCLS(sendVital);
    } catch (e) {
      /* CLS reporter unavailable */
    }
    try {
      window.webVitals.onINP(sendVital);
    } catch (e) {
      /* INP reporter unavailable */
    }
    try {
      window.webVitals.onLCP(sendVital);
    } catch (e) {
      /* LCP reporter unavailable */
    }
    try {
      window.webVitals.onTTFB(sendVital);
    } catch (e) {
      /* TTFB reporter unavailable */
    }
    try {
      window.webVitals.onFCP(sendVital);
    } catch (e) {
      /* FCP reporter unavailable */
    }
  }

  /* ---------- errors ---------- */

  window.addEventListener('error', function (e) {
    push({
      event: 'js_error',
      message: (e.message || '').slice(0, 200),
      filename: sanitizeUrl(e.filename || ''),
      line_no: e.lineno,
      col_no: e.colno,
      stack: e.error && e.error.stack ? e.error.stack.slice(0, 1000) : null,
      page_template: pageTemplate()
    });
  });

  window.addEventListener('unhandledrejection', function (e) {
    var reason = e.reason;
    var msg = '';
    try {
      msg = (reason && (reason.message || String(reason))).slice(0, 200);
    } catch (err) {
      msg = 'unknown';
    }
    push({
      event: 'promise_rejection',
      reason: msg,
      page_template: pageTemplate()
    });
  });

  if (window.fetch) {
    var origFetch = window.fetch;
    window.fetch = function (input, init) {
      var start = Date.now();
      var urlStr = typeof input === 'string' ? input : (input && input.url) || '';
      var method = (init && init.method) || (input && input.method) || 'GET';
      return origFetch
        .apply(this, arguments)
        .then(function (resp) {
          if (!resp.ok && resp.status >= 500) {
            push({
              event: 'network_error',
              url_path: sanitizeUrl(urlStr),
              status: resp.status,
              method: method,
              duration_ms: Date.now() - start,
              page_template: pageTemplate()
            });
          }
          return resp;
        })
        .catch(function (err) {
          push({
            event: 'network_error',
            url_path: sanitizeUrl(urlStr),
            status: 0,
            method: method,
            duration_ms: Date.now() - start,
            error: (err && err.message) || 'network',
            page_template: pageTemplate()
          });
          throw err;
        });
    };
  }

  if (window.XMLHttpRequest) {
    var XHR = window.XMLHttpRequest.prototype;
    var origOpen = XHR.open;
    var origSend = XHR.send;
    XHR.open = function (method, url) {
      this._gtm_method = method;
      this._gtm_url = url;
      return origOpen.apply(this, arguments);
    };
    XHR.send = function () {
      var self = this;
      var start = Date.now();
      self.addEventListener('loadend', function () {
        if (self.status === 0 || self.status >= 500) {
          push({
            event: 'network_error',
            url_path: sanitizeUrl(self._gtm_url || ''),
            status: self.status,
            method: self._gtm_method || 'GET',
            duration_ms: Date.now() - start,
            page_template: pageTemplate()
          });
        }
      });
      return origSend.apply(this, arguments);
    };
  }

  /* ---------- engagement ---------- */

  var scrollMarks = { 25: false, 50: false, 75: false, 100: false };
  var scrollStart = Date.now();

  window.addEventListener(
    'scroll',
    function () {
      var height = document.documentElement.scrollHeight - window.innerHeight;
      if (height <= 0) return;
      var pct = Math.min(100, Math.round((window.scrollY / height) * 100));
      [25, 50, 75, 100].forEach(function (mark) {
        if (pct >= mark && !scrollMarks[mark]) {
          scrollMarks[mark] = true;
          push({
            event: 'scroll_depth',
            depth_percent: mark,
            time_to_depth_ms: Date.now() - scrollStart,
            page_template: pageTemplate()
          });
        }
      });
    },
    { passive: true }
  );

  var pageStart = Date.now();
  var lastActivity = Date.now();
  var engagedFired = false;
  var idleFired = false;

  function markActivity() {
    lastActivity = Date.now();
    if (idleFired) idleFired = false;
  }

  ['mousemove', 'scroll', 'keydown', 'click', 'touchstart'].forEach(function (evtName) {
    window.addEventListener(evtName, markActivity, { passive: true });
  });

  setInterval(function () {
    var now = Date.now();
    var sinceActivity = now - lastActivity;
    var sincePageStart = now - pageStart;
    if (!engagedFired && sincePageStart >= 15000 && sinceActivity < 5000) {
      engagedFired = true;
      push({
        event: 'page_engaged',
        time_to_engagement_ms: sincePageStart,
        page_template: pageTemplate()
      });
    }
    if (!idleFired && sinceActivity > 30000) {
      idleFired = true;
      push({
        event: 'page_idle',
        idle_since_ms: sinceActivity,
        page_template: pageTemplate()
      });
    }
  }, 5000);

  function reportTimeOnPage() {
    var total = Date.now() - pageStart;
    var engaged = engagedFired ? total : 0;
    push({
      event: 'time_on_page',
      duration_ms: total,
      engaged_time_ms: engaged,
      page_template: pageTemplate()
    });
  }
  window.addEventListener('pagehide', reportTimeOnPage);
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') reportTimeOnPage();
  });
})();
