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
  const poll = async (requestId) => {
    const data = await request('crapscraper_manual_status', { request_id: requestId });
    const terminal = ['up_to_date','completed','error','blocked','rolled_back','rollback_required'].includes(data.status);
    const labels = { pending:'Aguardando o CrapScraper no PC', claimed:'Pedido recebido pelo PC', processing:'Verificando e atualizando', up_to_date:'Produto já atualizado', completed:'Atualização concluída', rolled_back:'Falha revertida com segurança' };
    const versions = data.previous_version || data.new_version ? ` · ${data.previous_version || '?'} → ${data.new_version || '?'}` : '';
    const tone = !terminal ? 'loading' : (data.status === 'up_to_date' ? 'empty' : (data.status === 'completed' ? 'success' : 'error'));
    show(`${labels[data.status] || data.message || 'Processando'}${data.source ? ` · ${data.source}` : ''}${versions}`, tone);
    if (!terminal) window.setTimeout(() => poll(requestId).catch(fail), 3000);
    else { button.disabled=false; button.removeAttribute('aria-busy'); }
  };
  const fail = (error) => { show(error.message || String(error), 'error'); button.disabled = false; button.removeAttribute('aria-busy'); };
  button.addEventListener('click', async () => {
    button.disabled = true; button.setAttribute('aria-busy', 'true');
    show('Consultando PluginTheme…', 'loading');
    try {
      const data = await request('crapscraper_manual_start');
      show(data.message || 'Pedido criado. Aguardando o CrapScraper no PC.', 'loading');
      await poll(data.request_id);
    } catch (error) { fail(error); }
  });
})();
