(function (w, d) {
  if (w.MyChatWidget) return;
  w.MyChatWidget = (function () {
    // find current script robustly
    var scriptEl = document.currentScript || (function () {
      var scrs = document.getElementsByTagName('script');
      return scrs[scrs.length - 1];
    })();

    var cfg = {
      widgetUrl: (scriptEl && scriptEl.dataset && scriptEl.dataset.widgetUrl) || window.location.origin + '/widget',
      siteId: (scriptEl && scriptEl.dataset && scriptEl.dataset.siteId) || '',
      position: (scriptEl && scriptEl.dataset && scriptEl.dataset.position) || 'bottom-right',
      width: (scriptEl && scriptEl.dataset && scriptEl.dataset.width) || '360px',
      height: (scriptEl && scriptEl.dataset && scriptEl.dataset.height) || '600px',
      allowSameOrigin: (scriptEl && scriptEl.dataset && scriptEl.dataset.allowSameOrigin) === 'true'
    };

    function buildSrc() {
      try {
        var u = new URL(cfg.widgetUrl, location.href);
        if (cfg.siteId) u.searchParams.set('site_id', cfg.siteId);
        return u.toString();
      } catch (e) {
        return cfg.widgetUrl;
      }
    }

    var iframe;
    function createIframe() {
      if (iframe) return iframe;
      iframe = d.createElement('iframe');
      iframe.id = 'my-chat-widget-iframe';
      iframe.src = buildSrc();
      iframe.style.width = cfg.width;
      iframe.style.height = cfg.height;
      iframe.style.border = '0';
      iframe.style.position = 'fixed';
      iframe.style.zIndex = '99999';
      iframe.style.display = 'none';
      iframe.style.borderRadius = '12px';
      iframe.style.boxShadow = '0 8px 32px rgba(0, 0, 0, 0.15)';
      
      if (cfg.position === 'top-right') { 
        iframe.style.top = '20px'; 
        iframe.style.right = '20px'; 
      }
      else if (cfg.position === 'top-left') { 
        iframe.style.top = '20px'; 
        iframe.style.left = '20px'; 
      }
      else if (cfg.position === 'bottom-left') { 
        iframe.style.left = '20px'; 
        iframe.style.bottom = '24px'; 
      }
      else { 
        iframe.style.right = '20px'; 
        iframe.style.bottom = '24px'; 
      }

      var sandbox = ['allow-scripts','allow-forms'];
      if (cfg.allowSameOrigin) sandbox.push('allow-same-origin');
      iframe.setAttribute('sandbox', sandbox.join(' '));
      (scriptEl && scriptEl.parentNode ? scriptEl.parentNode : d.body).appendChild(iframe);

      iframe.addEventListener('load', function () {
        try { iframe.contentWindow.postMessage({ type: 'init', payload: { site_id: cfg.siteId } }, '*'); } catch(e){}
      });

      return iframe;
    }

    // safe postMessage wrapper
    function post(msg) {
      var f = createIframe();
      if (!f.contentWindow) return false;
      try { f.contentWindow.postMessage(msg, '*'); return true; } catch (e) { return false; }
    }

    // public API
    function open() { createIframe().style.display = 'block'; }
    function close() { if (iframe) iframe.style.display = 'none'; }
    function toggle() { var f = createIframe(); f.style.display = (f.style.display === 'none' ? 'block' : 'none'); }
    function on(event, cb) { window.addEventListener('message', function recv(ev) { try { var d = ev.data || {}; if (d && d.type === event) cb(d.payload); } catch(e){} }, false); }

    // init immediately but safely
    setTimeout(createIframe, 0);

    return { open: open, close: close, toggle: toggle, post: post, on: on, cfg: cfg };
  })();
})(window, document);
