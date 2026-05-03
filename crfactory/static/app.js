const $ = (sel, root = document) => root.querySelector(sel);

const state = { current: null, jobTimer: null };

async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET' };
  if (opts.body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(opts.body);
  } else if (opts.formBody) {
    init.body = opts.formBody;
  }
  const r = await fetch(path, init);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

async function loadConfig() {
  const c = await api('/api/config');
  $('#storage-root').value = c.storage_root;
  $('#env-badge').textContent = `${c.platform} · ${c.video_encoder}`;
}

$('#save-storage').onclick = async () => {
  await api('/api/config', { method: 'POST', body: { storage_root: $('#storage-root').value.trim() }});
  alert('Storage root saved.');
  loadProjects();
};

async function loadProjects() {
  const list = await api('/api/projects');
  const ul = $('#projects-list');
  ul.innerHTML = '';
  if (list.length === 0) {
    const li = document.createElement('li');
    li.className = 'muted';
    li.textContent = 'No projects yet — create one below.';
    ul.appendChild(li);
    return;
  }
  for (const p of list) {
    const li = document.createElement('li');
    li.innerHTML = `<strong>${p.name}</strong> <span class="muted">${p.slug} · ${(p.channels||[]).join(', ') || 'no channels'}</span>`;
    li.onclick = () => openProject(p.slug);
    ul.appendChild(li);
  }
}

$('#new-project-form').onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const channels = (fd.get('channels') || '').split(',').map(s => s.trim()).filter(Boolean);
  await api('/api/projects', { method: 'POST', body: {
    name: fd.get('name'),
    channels,
    trim_seconds: parseFloat(fd.get('trim_seconds') || '3'),
  }});
  e.target.reset();
  e.target.querySelector('input[name=trim_seconds]').value = '3';
  loadProjects();
};

async function openProject(slug) {
  const data = await api(`/api/projects/${slug}`);
  state.current = data.project;
  $('#project-detail').hidden = false;
  $('#project-title').textContent = data.project.name;
  const f = $('#settings-form');
  f.channels.value = (data.project.channels || []).join(', ');
  f.trim_seconds.value = data.project.trim_seconds;
  f.output_width.value = data.project.output_width;
  f.output_height.value = data.project.output_height;
  f.framerate.value = data.project.framerate;
  f.video_bitrate.value = data.project.video_bitrate;
  f.audio_bitrate.value = data.project.audio_bitrate;
  $('#cta-status').textContent = data.has_cta ? '✓ CTA uploaded' : '✗ No CTA uploaded';
  $('#stats').textContent = JSON.stringify(data.stats, null, 2);
  $('#output-dir-line').textContent = `Output: ${data.output_dir}`;
  loadLibrary();
}

$('#settings-form').onsubmit = async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const channels = (fd.get('channels') || '').split(',').map(s => s.trim()).filter(Boolean);
  await api(`/api/projects/${state.current.slug}`, { method: 'PUT', body: {
    channels,
    trim_seconds: parseFloat(fd.get('trim_seconds')),
    output_width: parseInt(fd.get('output_width')),
    output_height: parseInt(fd.get('output_height')),
    framerate: parseInt(fd.get('framerate')),
    video_bitrate: fd.get('video_bitrate'),
    audio_bitrate: fd.get('audio_bitrate'),
  }});
  alert('Settings saved.');
  openProject(state.current.slug);
};

$('#upload-cta').onclick = async () => {
  const file = $('#cta-file').files[0];
  if (!file) return alert('Pick a video file first.');
  const fd = new FormData();
  fd.append('file', file);
  const r = await fetch(`/api/projects/${state.current.slug}/cta`, { method: 'POST', body: fd });
  if (!r.ok) return alert('Upload failed: ' + await r.text());
  alert('CTA uploaded.');
  openProject(state.current.slug);
};

$('#scrape-btn').onclick = async () => {
  const limit = parseInt($('#scrape-limit').value || '50');
  const j = await api(`/api/projects/${state.current.slug}/scrape`, {
    method: 'POST', body: { limit },
  });
  watchJob(j.job_id);
};

$('#process-btn').onclick = async () => {
  const j = await api(`/api/projects/${state.current.slug}/process`, {
    method: 'POST', body: {},
  });
  watchJob(j.job_id);
};

$('#reveal-output').onclick = async () => {
  await api(`/api/projects/${state.current.slug}/reveal`, { method: 'POST', body: {} });
};

function watchJob(id) {
  if (state.jobTimer) clearInterval(state.jobTimer);
  state.jobTimer = setInterval(async () => {
    const j = await api(`/api/jobs/${id}`);
    $('#job-log').textContent = `[${j.type} · ${j.status}]\n` + j.log.join('\n');
    if (j.status === 'done' || j.status === 'error') {
      clearInterval(state.jobTimer);
      openProject(state.current.slug);
    }
  }, 1500);
}

async function loadLibrary() {
  const rows = await api(`/api/projects/${state.current.slug}/library?limit=200`);
  const tb = $('#library tbody');
  tb.innerHTML = '';
  for (const r of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML =
      `<td>${r.status || ''}</td>` +
      `<td>${(r.view_count || 0).toLocaleString()}</td>` +
      `<td>${(r.title || '').replace(/</g, '&lt;')}</td>` +
      `<td>${(r.channel || '').replace(/</g, '&lt;')}</td>` +
      `<td><a href="https://youtube.com/watch?v=${r.video_id}" target="_blank">${r.video_id}</a></td>`;
    tb.appendChild(tr);
  }
}

loadConfig().then(loadProjects);
