(function () {
  const state = {
    editor: null,
  };

  const loadMonaco = () => {
    return new Promise((resolve, reject) => {
      if (window.monaco && window.monaco.editor) {
        resolve(window.monaco);
        return;
      }
      if (typeof window.require !== 'function') {
        reject(new Error('Monaco loader not available'));
        return;
      }
      window.require.config({
        paths: {
          vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.44.0/min/vs',
        },
      });
      window.require(['vs/editor/editor.main'], () => {
        if (window.monaco && window.monaco.editor) resolve(window.monaco);
        else reject(new Error('Monaco failed to load'));
      });
    });
  };

  const setupEditor = async () => {
    const container = document.querySelector('[data-script-editor]');
    const textarea = document.querySelector('[name="code"]');
    if (!container || !textarea) return;

    try {
      const monaco = await loadMonaco();
      state.editor = monaco.editor.create(container, {
        value: textarea.value || '',
        language: 'python',
        automaticLayout: true,
        minimap: { enabled: false },
        fontSize: 14,
        theme: 'vs-dark',
      });
    } catch (err) {
      console.warn('Monaco unavailable, using fallback textarea', err);
      container.classList.add('d-none');
      textarea.classList.remove('d-none');
    }
  };

  // ✅ Sync editor to textarea before any form submission
  document.body.addEventListener('htmx:configRequest', (event) => {
    const form = event.detail && event.detail.elt && event.detail.elt.closest('form');
    if (!form) return;
    const textarea = form.querySelector('[name="code"]');
    if (textarea && state.editor) textarea.value = state.editor.getValue();
  });

  document.addEventListener('DOMContentLoaded', setupEditor);

  // Append to bottom of script_builder.js
function openLogStream(runId, scriptId) {
  const logPanel = document.getElementById("log-panel");
  const logStatus = document.getElementById("log-status");
  if (!runId || !scriptId || !logPanel) return;

  const url = `/flows/scripts/${scriptId}/runs/${runId}/stream/`;
  const evtSource = new EventSource(url);
  logPanel.innerHTML = "";
  logStatus.textContent = "streaming";

  evtSource.onmessage = (e) => {
    try {
      const payload = JSON.parse(e.data || "{}");
      if (payload.type === "log") {
        const div = document.createElement("div");
        div.textContent = `[${payload.level}] ${payload.message}`;
        logPanel.appendChild(div);
        logPanel.scrollTop = logPanel.scrollHeight;
      } else if (payload.type === "status") {
        logStatus.textContent = payload.status || "done";
        evtSource.close();
      }
    } catch (err) {
      console.warn("Bad SSE payload", err);
    }
  };

  evtSource.onerror = () => {
    logStatus.textContent = "error";
    evtSource.close();
  };
}

// Optional: listen for a custom event or htmx:afterRequest to open SSE
document.body.addEventListener("htmx:afterRequest", (event) => {
  const xhr = event.detail && event.detail.xhr;
  if (!xhr) return;
  try {
    const data = JSON.parse(xhr.responseText || "{}");
    if (data.run && data.run.id && data.run.script_id) {
      openLogStream(data.run.id, data.run.script_id);
    }
  } catch (_) {}
});

})();
