/* AndIron Group — News Dashboard frontend */

// ── Toast helper ──────────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.className = `toast show ${type}`;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.className = 'toast'; }, 4500);
}

// ── Refresh all clients ───────────────────────────────────────────────────────
async function refreshAll() {
  const overlay = document.getElementById('loadingOverlay');
  const msg     = document.getElementById('loadingMsg');
  const btn     = document.getElementById('refreshAllBtn');

  overlay.classList.add('active');
  if (msg) msg.textContent = 'Fetching news for all clients — this takes 1–2 minutes…';
  if (btn) btn.disabled = true;

  try {
    const res  = await fetch('/api/refresh', { method: 'POST' });
    const data = await res.json();

    if (data.success) {
      showToast('News refreshed successfully', 'success');
      setTimeout(() => window.location.reload(), 600);
    } else {
      overlay.classList.remove('active');
      if (btn) btn.disabled = false;
      showToast('Error: ' + (data.error || 'Unknown error'), 'error');
    }
  } catch (err) {
    overlay.classList.remove('active');
    if (btn) btn.disabled = false;
    showToast('Network error: ' + err.message, 'error');
  }
}

// ── Refresh a single client ───────────────────────────────────────────────────
async function refreshClient(clientId) {
  const overlay = document.getElementById('loadingOverlay');
  const msg     = document.getElementById('loadingMsg');

  overlay.classList.add('active');
  if (msg) msg.textContent = `Fetching news for ${clientId.replace(/_/g, ' ')}…`;

  try {
    const res  = await fetch(`/api/refresh/${clientId}`, { method: 'POST' });
    const data = await res.json();

    if (data.success) {
      showToast(`Fetched ${data.count} stories`, 'success');
      setTimeout(() => window.location.reload(), 600);
    } else {
      overlay.classList.remove('active');
      showToast('Error: ' + (data.error || 'Unknown error'), 'error');
    }
  } catch (err) {
    overlay.classList.remove('active');
    showToast('Network error: ' + err.message, 'error');
  }
}
