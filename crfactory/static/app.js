'use strict';

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = {
  projects: [],
  current: null,
  detail: null,
  library: [],
  ctas: [],
  libraryFilter: '',
  librarySearch: '',
  jobId: null,
  jobTimer: null,
};

/* ---------- api ---------- */

async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET' };
  if (opts.body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(opts.body);
  } else if (opts.formBody) {
    init.body = opts.formBody;
  }
  const r = await fetch(path, init);
  if (!r.ok) {
    const txt = await r.text();
    let msg = txt;
    try { msg = JSON.parse(txt).detail || txt; } catch (e) {}
    throw new Error(msg);
  }
  if (r.status === 204) return null;
  return r.json();
}

/* ---------- formatters ---------- */

function formatNumber(n) {
  n = n || 0;
  if (n >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, '') + 'K';
  return String(n);
}

function formatBytes(b) {
  b = b || 0;
  if (b < 1024) return b + ' B';
  if (b < 1024 ** 2) return (b / 1024).toFixed(1) + ' KB';
  if (b < 1024 ** 3) return (b / 1024 ** 2).toFixed(1) + ' MB';
  return (b / 1024 ** 3).toFixed(2) + ' GB';
}

function statusPill(status) {
  const map = {
    scraped:    { cls: 'pill-info',    label: 'Scraped' },
    downloaded: { cls: 'pill-warning', label: 'Downloaded' },
    stitched:   { cls: 'pill-success', label: 'Stitched' },
    failed:     { cls: 'pill-danger',  label: 'Failed' },
  };
  const v = map[status] || { cls: 'pill-muted', label: status || '—' };
  return `<span class="pill ${v.cls}">${v.label}</span>`;
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

/* ---------- toasts ---------- */

function toast(message, kind = 'info', ms = 3500) {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = message;
  $('#toast-container').appendChild(el);
  setTimeout(() => {
    el.classList.add('fade-out');
    setTimeout(() => el.remove(), 250);
  }, ms);
}

/* ---------- modals ---------- */

function openModal(id) { $('#' + id).hidden = false; }
function closeModal(id) { $('#' + id).hidden = true; }

document.addEventListener('click', (e) => {
  const target = e.target;
  if (target.matches('[data-dismiss]')) {
    closeModal(target.dataset.dismiss);
  }
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    $$('.modal').forEach(m => m.hidden = true);
  }
});

function confirmModal({ title, message, okText = 'Confirm', danger = true }) {
  return new Promise((resolve) => {
    $('#confirm-title').textContent = title;
    $('#confirm-message').textContent = message || '';
    const ok = $('#confirm-ok');
    ok.textContent = okText;
    ok.className = danger ? 'btn btn-danger' : 'btn btn-primary';
    openModal('confirm-modal');
    const handler = () => {
      ok.removeEventListener('click', handler);
      closeModal('confirm-modal');
      resolve(true);
    };
    ok.addEventListener('click', handler);
    const onClose = () => {
      $('#confirm-modal').removeEventListener('transitionend', onClose);
      if ($('#confirm-modal').hidden) resolve(false);
    };
    const dismissBtns = $$('#confirm-modal [data-dismiss]');
    const dismissHandler = () => {
      ok.removeEventListener('click', handler);
      dismissBtns.forEach(b => b.removeEventListener('click', dismissHandler));
      resolve(false);
    };
    dismissBtns.forEach(b => b.addEventListener('click', dismissHandler));
  });
}

/* ---------- async button helper ---------- */

async function withButtonLoading(btn, fn) {
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span>${original}`;
  try { return await fn(); }
  finally {
    btn.innerHTML = original;
    btn.disabled = false;
  }
}

/* ---------- config / sidebar ---------- */

async function loadConfig() {
  const c = await api('/api/config');
  $('#storage-root').value = c.storage_root;
  $('#brand-sub').textContent = `v0.3 · ${c.platform} · ${c.video_encoder}`;
}

$('#save-storage').onclick = (e) => withButtonLoading(e.currentTarget, async () => {
  await api('/api/config', { method: 'POST', body: { storage_root: $('#storage-root').value.trim() }});
  toast('Storage location saved.', 'success');
  await loadProjects();
  if (state.current) await selectProject(state.current);
});

/* ---------- projects sidebar ---------- */

async function loadProjects() {
  state.projects = await api('/api/projects');
  renderSidebar();
}

function renderSidebar() {
  const nav = $('#project-nav');
  nav.innerHTML = '';
  if (!state.projects.length) {
    nav.innerHTML = '<div class="nav-empty muted">No projects yet — create one to get started.</div>';
    return;
  }
  for (const p of state.projects) {
    const link = document.createElement('div');
    link.className = 'project-link' + (p.slug === state.current ? ' active' : '');
    const stitched = p.stats?.stitched ?? 0;
    const total = p.stats?.total ?? 0;
    const ctaDot = p.has_cta ? '' : '<span class="dot warn" title="No CTA uploaded"></span>';
    link.innerHTML = `
      <strong>${escapeHtml(p.name)}</strong>
      <span class="nav-meta">
        ${ctaDot}
        ${stitched}/${total} stitched
        · ${(p.channels || []).length} channel${(p.channels || []).length === 1 ? '' : 's'}
      </span>
    `;
    link.onclick = () => selectProject(p.slug);
    nav.appendChild(link);
  }
}

/* ---------- project view ---------- */

async function selectProject(slug) {
  state.current = slug;
  renderSidebar();
  $('#welcome').hidden = true;
  $('#project-view').hidden = false;
  state.detail = await api(`/api/projects/${slug}`);
  renderProject();
  await Promise.all([loadCtas(), loadLibrary(), loadActiveJob()]);
}

function renderProject() {
  const d = state.detail;
  if (!d) return;
  $('#project-title').textContent = d.project.name;
  $('#project-sub').textContent = `${d.project.slug} · ${(d.project.channels || []).join(', ') || 'no channels yet'} · output → ${d.output_dir}`;

  $('#stat-total').textContent = d.stats.total;
  $('#stat-scraped').textContent = d.stats.scraped;
  $('#stat-stitched').textContent = d.stats.stitched;
  $('#stat-failed').textContent = d.stats.failed;
  $('#stat-disk').textContent = formatBytes(d.disk?.total_bytes || 0);

  const f = $('#settings-form');
  f.channels.value = (d.project.channels || []).join(', ');
  f.output_width.value = d.project.output_width;
  f.output_height.value = d.project.output_height;
  f.framerate.value = d.project.framerate;
  f.video_bitrate.value = d.project.video_bitrate;
  f.audio_bitrate.value = d.project.audio_bitrate;

  const count = d.cta_count ?? 0;
  const ctaPill = $('#cta-pill');
  ctaPill.textContent = count;
  ctaPill.className = 'pill ' + (count > 0 ? 'pill-success' : 'pill-muted');
}

async function loadCtas() {
  state.ctas = await api(`/api/projects/${state.current}/ctas`);
  renderCtas();
}

function renderCtas() {
  const ul = $('#cta-list');
  ul.innerHTML = '';
  if (!state.ctas.length) {
    const empty = document.createElement('li');
    empty.className = 'cta-list-empty';
    empty.textContent = 'No CTA videos yet — upload at least one before processing.';
    ul.appendChild(empty);
    return;
  }
  for (const c of state.ctas) {
    const li = document.createElement('li');
    li.innerHTML = `
      <span class="cta-name" title="${escapeHtml(c.name)}">${escapeHtml(c.name)}</span>
      <span class="cta-size">${formatBytes(c.size)}</span>
      <button class="btn btn-ghost btn-sm" data-cta-act="play" data-name="${escapeHtml(c.name)}">▶ Play</button>
      <button class="btn btn-danger-ghost btn-sm" data-cta-act="delete" data-name="${escapeHtml(c.name)}">Delete</button>
    `;
    ul.appendChild(li);
  }
}

$('#cta-list').onclick = async (e) => {
  const btn = e.target.closest('[data-cta-act]');
  if (!btn) return;
  const name = btn.dataset.name;
  const act = btn.dataset.ctaAct;
  if (act === 'play') {
    $('#video-modal-title').textContent = name;
    $('#video-modal-player').src = `/api/projects/${state.current}/ctas/${encodeURIComponent(name)}?t=${Date.now()}`;
    openModal('video-modal');
  } else if (act === 'delete') {
    const ok = await confirmModal({
      title: `Delete CTA "${name}"?`,
      message: 'Removes the file from the project. Already-stitched videos that used it are not affected.',
      okText: 'Delete',
    });
    if (!ok) return;
    await api(`/api/projects/${state.current}/ctas/${encodeURIComponent(name)}`, { method: 'DELETE' });
    toast(`Deleted ${name}.`, 'success');
    await loadCtas();
    state.detail = await api(`/api/projects/${state.current}`);
    renderProject();
    await loadProjects();
  }
};

async function loadLibrary() {
  state.library = await api(`/api/projects/${state.current}/library?limit=2000`);
  renderLibrary();
}

function renderLibrary() {
  const tb = $('#library-table tbody');
  const filter = state.libraryFilter;
  const search = state.librarySearch.toLowerCase().trim();
  let rows = state.library;
  if (filter) rows = rows.filter(r => r.status === filter);
  if (search) rows = rows.filter(r =>
    (r.title || '').toLowerCase().includes(search) ||
    (r.channel || '').toLowerCase().includes(search)
  );
  tb.innerHTML = '';
  for (const r of rows) {
    const tr = document.createElement('tr');
    const ytLink = `https://youtube.com/watch?v=${r.video_id}`;
    const thumb = r.thumbnail_url
      ? `<img class="thumb" src="${escapeHtml(r.thumbnail_url)}" loading="lazy" alt="">`
      : `<div class="thumb"></div>`;
    const playBtn = r.status === 'stitched'
      ? `<button class="btn btn-ghost btn-sm" data-act="play" data-id="${r.video_id}">▶ Play</button>`
      : '';
    const retryBtn = r.status === 'failed'
      ? `<button class="btn btn-secondary btn-sm" data-act="retry" data-id="${r.video_id}">Retry</button>`
      : '';
    tr.innerHTML = `
      <td>${thumb}</td>
      <td>${statusPill(r.status)}</td>
      <td class="title-cell">
        <a href="${ytLink}" target="_blank" rel="noopener">${escapeHtml(r.title || r.video_id)}</a>
        <div class="vid">${r.video_id}${r.cta_used ? ' · cta: ' + escapeHtml(r.cta_used) : ''}${r.error ? ' · ' + escapeHtml(r.error.slice(0, 80)) : ''}</div>
      </td>
      <td>${escapeHtml(r.channel || '')}</td>
      <td class="num">${formatNumber(r.view_count)}</td>
      <td class="actions">
        ${playBtn}
        ${retryBtn}
        <button class="btn btn-danger-ghost btn-sm" data-act="delete" data-id="${r.video_id}">Delete</button>
      </td>
    `;
    tb.appendChild(tr);
  }
  $('#library-count').textContent =
    `${rows.length} of ${state.library.length} shown` +
    (filter || search ? ' (filtered)' : '');
}

$('#library-table').onclick = async (e) => {
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const id = btn.dataset.id;
  const act = btn.dataset.act;
  if (act === 'play') {
    $('#video-modal-title').textContent = id;
    const player = $('#video-modal-player');
    player.src = `/api/projects/${state.current}/library/${id}/output?t=${Date.now()}`;
    openModal('video-modal');
  } else if (act === 'retry') {
    await withButtonLoading(btn, async () => {
      await api(`/api/projects/${state.current}/library/${id}/retry`, { method: 'POST', body: {} });
      toast('Marked for retry. Click "Download & stitch" to run.', 'info');
      await loadLibrary();
    });
  } else if (act === 'delete') {
    const ok = await confirmModal({
      title: 'Delete from library?',
      message: 'This removes the row and any downloaded raw / stitched files for this video. Cannot be undone.',
      okText: 'Delete',
    });
    if (!ok) return;
    await api(`/api/projects/${state.current}/library/${id}?delete_files=true`, { method: 'DELETE' });
    toast('Deleted.', 'success');
    await loadLibrary();
    state.detail = await api(`/api/projects/${state.current}`);
    renderProject();
  }
};

$('#video-modal').addEventListener('click', (e) => {
  if (e.target.matches('[data-dismiss]') || e.target.classList.contains('modal-backdrop')) {
    $('#video-modal-player').pause();
    $('#video-modal-player').removeAttribute('src');
    $('#video-modal-player').load();
  }
});

/* status / search filters */
$$('#status-filters .chip').forEach(chip => {
  chip.onclick = () => {
    $$('#status-filters .chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    state.libraryFilter = chip.dataset.status;
    renderLibrary();
  };
});
$('#library-search').oninput = (e) => {
  state.librarySearch = e.target.value;
  renderLibrary();
};

/* add by URL */
$('#add-by-url-btn').onclick = () => {
  const f = $('#add-by-url-form');
  f.hidden = !f.hidden;
  if (!f.hidden) $('#add-url-input').focus();
};
$('#add-url-cancel').onclick = () => { $('#add-by-url-form').hidden = true; };
$('#add-url-submit').onclick = (e) => withButtonLoading(e.currentTarget, async () => {
  const url = $('#add-url-input').value.trim();
  if (!url) return toast('Paste a YouTube URL or video ID first.', 'warning');
  const r = await api(`/api/projects/${state.current}/library/add`, { method: 'POST', body: { url } });
  if (r.added) toast(`Added ${r.video_id} to library.`, 'success');
  else toast(r.reason || 'Already in library.', 'warning');
  $('#add-url-input').value = '';
  $('#add-by-url-form').hidden = true;
  await loadLibrary();
  state.detail = await api(`/api/projects/${state.current}`);
  renderProject();
});

/* settings */
$('#settings-form').onsubmit = (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const channels = (fd.get('channels') || '').split(',').map(s => s.trim()).filter(Boolean);
  withButtonLoading(e.target.querySelector('button'), async () => {
    await api(`/api/projects/${state.current}`, { method: 'PUT', body: {
      channels,
      output_width: parseInt(fd.get('output_width')),
      output_height: parseInt(fd.get('output_height')),
      framerate: parseInt(fd.get('framerate')),
      video_bitrate: fd.get('video_bitrate'),
      audio_bitrate: fd.get('audio_bitrate'),
    }});
    toast('Settings saved.', 'success');
    state.detail = await api(`/api/projects/${state.current}`);
    renderProject();
    await loadProjects();
  });
};

/* CTA upload */
$('#upload-cta').onclick = (e) => withButtonLoading(e.currentTarget, async () => {
  const fileInput = $('#cta-file');
  const file = fileInput.files[0];
  if (!file) return toast('Pick a video file first.', 'warning');
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch(`/api/projects/${state.current}/ctas`, { method: 'POST', body: fd });
  if (!r.ok) return toast('Upload failed: ' + await r.text(), 'error');
  const data = await r.json();
  toast(`Added "${data.name}" to CTA pool.`, 'success');
  fileInput.value = '';
  await loadCtas();
  state.detail = await api(`/api/projects/${state.current}`);
  renderProject();
  await loadProjects();
});

/* actions */
$('#scrape-btn').onclick = (e) => withButtonLoading(e.currentTarget, async () => {
  const limit = parseInt($('#scrape-limit').value || '50');
  const j = await api(`/api/projects/${state.current}/scrape`, { method: 'POST', body: { limit } });
  toast('Scrape started.', 'info');
  watchJob(j.job_id);
});

$('#process-btn').onclick = (e) => withButtonLoading(e.currentTarget, async () => {
  if (!state.detail.has_cta) {
    toast('Upload at least one CTA video first.', 'warning');
    return;
  }
  const j = await api(`/api/projects/${state.current}/process`, { method: 'POST', body: {} });
  toast('Processing started.', 'info');
  watchJob(j.job_id);
});

$('#reveal-btn').onclick = async () => {
  await api(`/api/projects/${state.current}/reveal`, { method: 'POST', body: {} });
};

$('#delete-project-btn').onclick = async () => {
  const ok = await confirmModal({
    title: `Delete project "${state.detail.project.name}"?`,
    message: 'This removes the project folder, library DB, raw downloads, and all stitched outputs. Cannot be undone.',
    okText: 'Delete project',
  });
  if (!ok) return;
  await api(`/api/projects/${state.current}?purge=true`, { method: 'DELETE' });
  toast('Project deleted.', 'success');
  state.current = null;
  state.detail = null;
  $('#project-view').hidden = true;
  $('#welcome').hidden = false;
  await loadProjects();
};

/* jobs */

async function loadActiveJob() {
  const jobs = await api(`/api/jobs?slug=${state.current}`);
  const running = jobs.find(j => j.status === 'running' || j.status === 'pending');
  if (running) watchJob(running.id);
  else hideJobCard();
}

function hideJobCard() {
  if (state.jobTimer) { clearInterval(state.jobTimer); state.jobTimer = null; }
  state.jobId = null;
  $('#job-card').hidden = true;
}

function renderJob(j) {
  $('#job-card').hidden = false;
  $('#job-title').textContent = j.type === 'scrape' ? 'Scraping channels' : 'Downloading & stitching';
  const finished = j.finished_at && new Date(j.finished_at);
  const started = new Date(j.started_at);
  const seconds = Math.round(((finished || new Date()) - started) / 1000);
  $('#job-time').textContent = `· ${seconds}s elapsed`;

  const pill = $('#job-status-pill');
  if (j.status === 'running' || j.status === 'pending') {
    pill.innerHTML = `<span class="pill pill-info"><span class="spinner" style="margin-right:.35rem"></span>${j.status}</span>`;
  } else if (j.status === 'done') {
    pill.innerHTML = statusPill('stitched').replace('Stitched', 'Done');
  } else {
    pill.innerHTML = statusPill('failed').replace('Failed', j.status);
  }

  const progress = j.progress;
  if (progress && progress.total) {
    const pct = Math.round((progress.done / progress.total) * 100);
    $('#job-progress-bar').hidden = false;
    $('#job-progress-fill').style.width = pct + '%';
    $('#job-progress-text').textContent = `${progress.done} / ${progress.total} (${pct}%)`;
  } else {
    $('#job-progress-bar').hidden = true;
  }

  $('#job-log').textContent = (j.log || []).join('\n');
  $('#job-log').scrollTop = $('#job-log').scrollHeight;
}

function watchJob(id) {
  if (state.jobTimer) clearInterval(state.jobTimer);
  state.jobId = id;
  const tick = async () => {
    try {
      const j = await api(`/api/jobs/${id}`);
      renderJob(j);
      if (j.status === 'done' || j.status === 'error') {
        clearInterval(state.jobTimer); state.jobTimer = null;
        if (j.status === 'done') toast(`${j.type === 'scrape' ? 'Scrape' : 'Process'} complete.`, 'success');
        else toast(`${j.type} failed. Check the log.`, 'error');
        state.detail = await api(`/api/projects/${state.current}`);
        renderProject();
        await loadLibrary();
        await loadProjects();
      }
    } catch (e) {
      clearInterval(state.jobTimer); state.jobTimer = null;
    }
  };
  tick();
  state.jobTimer = setInterval(tick, 1500);
}

/* ---------- new project ---------- */

$('#new-project-btn').onclick = () => openModal('new-project-modal');
$('#welcome-new-project').onclick = () => openModal('new-project-modal');

$('#new-project-form').onsubmit = (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const channels = (fd.get('channels') || '').split(',').map(s => s.trim()).filter(Boolean);
  const submitBtn = e.target.querySelector('button[type="submit"], button:not([type="button"])');
  withButtonLoading(submitBtn, async () => {
    try {
      const p = await api('/api/projects', { method: 'POST', body: {
        name: fd.get('name'),
        channels,
      }});
      toast(`Project "${p.name}" created.`, 'success');
      e.target.reset();
      closeModal('new-project-modal');
      await loadProjects();
      await selectProject(p.slug);
    } catch (err) {
      toast('Failed to create: ' + err.message, 'error');
    }
  });
};

/* ---------- boot ---------- */

(async () => {
  try {
    await loadConfig();
    await loadProjects();
    if (state.projects.length) {
      await selectProject(state.projects[0].slug);
    }
  } catch (e) {
    toast('Startup error: ' + e.message, 'error');
  }
})();
