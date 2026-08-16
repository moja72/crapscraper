(() => {
  const root = document.getElementById('crapscraper-manual');
  if (!root || !window.CrapScraperManual) return;
  const button = document.getElementById('crapscraper-manual-button');
  const status = document.getElementById('crapscraper-manual-status');
  const progress = document.getElementById('crapscraper-manual-progress');
  const productId = root.dataset.productId;

  const request = async (action, values = {}) => {
    const body = new URLSearchParams({ action, nonce: CrapScraperManual.nonce, product_id: productId, ...values });
    const response = await fetch(CrapScraperManual.ajaxUrl, { method: 'POST', credentials: 'same-origin', body });
    const result = await response.json();
    if (!response.ok || !result.success) throw new Error(result?.data?.message || 'Falha na atualização.');
    return result.data;
  };
  const show = (message, tone = 'loading') => {
    status.className = `cs-status is-${tone}`;
    status.setAttribute('role', tone === 'error' ? 'alert' : 'status');
    status.textContent = message;
    progress.hidden = tone !== 'loading';
  };
  const poll = async (jobId) => {
    const data = await request('crapscraper_manual_status', { job_id: jobId });
    const labels = { approved: 'Validando vínculo', validating: 'Validando produto', downloading: 'Baixando arquivo', prepared: 'Arquivo validado', plan_ready: 'Plano seguro pronto', executing: 'Atualizando produto', completed: 'Atualização concluída', rolled_back: 'Falha revertida com segurança' };
    show(`${labels[data.status] || 'Processando'} · ${data.source || ''} · ${data.previous_version || '?'} → ${data.new_version || '?'}`, data.terminal ? (data.status === 'completed' ? 'success' : 'error') : 'loading');
    if (!data.terminal) window.setTimeout(() => poll(jobId).catch(fail), 2000);
  };
  const fail = (error) => { show(error.message || String(error), 'error'); button.disabled = false; button.removeAttribute('aria-busy'); };
  button.addEventListener('click', async () => {
    button.disabled = true; button.setAttribute('aria-busy', 'true');
    show('Consultando PluginTheme…', 'loading');
    try {
      const data = await request('crapscraper_manual_start');
      if (data.status === 'up_to_date') { show(data.message, 'empty'); button.disabled = false; button.removeAttribute('aria-busy'); return; }
      show(`${data.message} ${data.previous_version} → ${data.new_version}`, 'loading');
      await poll(data.job_id);
    } catch (error) { fail(error); }
  });
})();
