import React, { useEffect, useRef } from 'react';
import type { SelectedElementInfo } from '../../types/worldclass';

interface LiveSandboxRendererProps {
  htmlCode: string;
  onErrorDetected: (error: string) => void;
  onClearErrors: () => void;
  isMobile: boolean;
  inspectorActive?: boolean;
  onElementSelected?: (element: SelectedElementInfo) => void;
}

export const LiveSandboxRenderer: React.FC<LiveSandboxRendererProps> = ({
  htmlCode,
  onErrorDetected,
  onClearErrors,
  isMobile,
  inspectorActive = false,
  onElementSelected,
}) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Generate wrapper with Tailwind CSS CDN, error catcher, inspector bridge, and fonts
  const fullHtml = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body {
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      margin: 0;
      padding: 0;
      box-sizing: border-box;
      -webkit-font-smoothing: antialiased;
    }
    .jarvis-inspect-hover {
      outline: 2px dashed #6366f1 !important;
      outline-offset: 3px !important;
      cursor: crosshair !important;
      position: relative;
    }
  </style>
  <script>
    // Error interception for DevTools bar
    window.onerror = function(message, source, lineno, colno, error) {
      window.parent.postMessage({ type: 'PREVIEW_ERROR', message: message }, '*');
      return false;
    };
    window.addEventListener('unhandledrejection', function(event) {
      window.parent.postMessage({ type: 'PREVIEW_ERROR', message: event.reason ? event.reason.message : 'Promise rejection' }, '*');
    });

    // Visual Inspector Listener
    (function() {
      const active = ${inspectorActive ? 'true' : 'false'};
      if (!active) return;

      let hoveredEl = null;

      function getCssPath(el) {
        if (!el || el === document.body) return 'body';
        if (el.id) return '#' + el.id;
        let path = [];
        let curr = el;
        while (curr && curr !== document.body && curr.nodeType === 1) {
          let node = curr.nodeName.toLowerCase();
          if (curr.className && typeof curr.className === 'string') {
            const firstClass = curr.className.trim().split(/\\s+/)[0];
            if (firstClass && !firstClass.includes(':') && !firstClass.includes('[')) {
              node += '.' + firstClass;
            }
          }
          path.unshift(node);
          curr = curr.parentElement;
        }
        return path.slice(-3).join(' > ');
      }

      document.addEventListener('mouseover', function(e) {
        if (!active) return;
        if (hoveredEl && hoveredEl !== e.target) {
          hoveredEl.classList.remove('jarvis-inspect-hover');
        }
        hoveredEl = e.target;
        hoveredEl.classList.add('jarvis-inspect-hover');
      }, true);

      document.addEventListener('mouseout', function(e) {
        if (!active) return;
        if (hoveredEl) {
          hoveredEl.classList.remove('jarvis-inspect-hover');
          hoveredEl = null;
        }
      }, true);

      document.addEventListener('click', function(e) {
        if (!active) return;
        e.preventDefault();
        e.stopPropagation();
        const target = e.target;
        const rect = target.getBoundingClientRect();
        window.parent.postMessage({
          type: 'ELEMENT_CLICKED',
          elementInfo: {
            tagName: target.tagName,
            className: target.className ? String(target.className) : '',
            textContent: (target.textContent || '').trim().slice(0, 60),
            selector: getCssPath(target),
            boundingRect: {
              top: rect.top,
              left: rect.left,
              width: rect.width,
              height: rect.height,
            }
          }
        }, '*');
      }, true);
    })();
  </script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">
  ${htmlCode}
</body>
</html>
`;

  useEffect(() => {
    onClearErrors();
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'PREVIEW_ERROR') {
        onErrorDetected(event.data.message || 'Script runtime error detected');
      } else if (event.data?.type === 'ELEMENT_CLICKED') {
        if (onElementSelected && event.data.elementInfo) {
          onElementSelected(event.data.elementInfo);
        }
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [htmlCode, inspectorActive, onElementSelected]);

  return (
    <iframe
      ref={iframeRef}
      srcDoc={fullHtml}
      title="Live App Preview"
      sandbox="allow-scripts allow-modals"
      className="w-full h-full border-none bg-slate-950 transition-all duration-300"
    />
  );
};
