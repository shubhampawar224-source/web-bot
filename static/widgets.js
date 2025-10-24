(function() {
  const iframe = document.createElement('iframe');
  iframe.src = 'http://127.0.0.1:8000/static/widget.html';
  iframe.style.position = 'fixed';
  iframe.style.bottom = '20px';
  iframe.style.right = '20px';
  iframe.style.width = '360px';
  iframe.style.height = '500px';
  iframe.style.border = 'none';
  iframe.style.zIndex = '999999';
  iframe.style.borderRadius = '16px';
  iframe.style.boxShadow = '0 4px 20px rgba(0,0,0,0.3)';
  document.body.appendChild(iframe);
})();
