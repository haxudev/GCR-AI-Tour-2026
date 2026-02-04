function setStatus(message, type = "info") {
  const status = document.getElementById("status");
  if (!message) {
    status.hidden = true;
    status.textContent = "";
    status.dataset.type = "";
    return;
  }

  status.hidden = false;
  status.textContent = message;
  status.dataset.type = type;
}

async function fetchText(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Fetch failed: ${res.status} ${res.statusText}`);
  }
  return await res.text();
}

function renderMarkdown(markdown) {
  // marked is loaded via CDN and attached to window
  const html = window.marked.parse(markdown, {
    gfm: true,
    breaks: true,
    headerIds: true,
    mangle: false,
  });

  // DOMPurify is loaded via CDN and attached to window
  const clean = window.DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
  });

  const content = document.getElementById("content");
  content.innerHTML = clean;
}

async function loadReport(reportPath) {
  setStatus(`正在加载：${reportPath}`);

  try {
    const markdown = await fetchText(reportPath);
    renderMarkdown(markdown);
    setStatus(`已加载：${reportPath}`);
  } catch (err) {
    console.error(err);
    setStatus(`加载失败：${reportPath}。${err?.message || err}`, "error");

    const content = document.getElementById("content");
    content.innerHTML = "";
  }
}

function wireUi() {
  loadReport("report.md");
}

wireUi();
