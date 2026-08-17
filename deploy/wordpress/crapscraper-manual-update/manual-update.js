(() => {
  const root = document.getElementById('crapscraper-manual');
  if (!root || !window.CrapScraperManual) return;
  const button = document.getElementById('crapscraper-manual-button');
  const status = document.getElementById('crapscraper-manual-status');
  const progress = document.getElementById('crapscraper-manual-progress');
  const stage = root.querySelector('[data-cs-stage]');
  const source = root.querySelector('[data-cs-source]');
  const version = root.querySelector('[data-cs-version]');
  const productId = root.dataset.productId;

  const request = async (action, values = {}) => {
    const body = new URLSearchParams({ action, nonce: CrapScraperManual.nonce, product_id: productId, ...values });
    const response = await fetch(CrapScraperManual.ajaxUrl, { method: 'POST', credentials: 'same-origin', body });
    const result = await response.json();
    if (!response.ok || !result.success) throw new Error(result?.data?.message || 'Falha na atualização.');
    return result.data;
  };
  const show = (message, tone = 'loading', details = {}) => {
    status.className = `cs-status is-${tone}`;
    status.setAttribute('role', tone === 'error' ? 'alert' : 'status');
    status.textContent = message;
    progress.hidden = tone !== 'loading';
    if (stage) stage.textContent = details.stage || message || '—';
    if (source) source.textContent = details.source || '—';
    if (version) version.textContent = details.version || '—';
  };
  const poll = async (requestId) => {
    const data = await request('crapscraper_manual_status', { request_id: requestId });
    const terminal = ['up_to_date','no_match','source_not_found','source_version_missing','relationship_required','comparison_stale','completed','error','blocked','rolled_back','rollback_required'].includes(data.status);
    const labels = { pending:'Aguardando o CrapScraper', claimed:'Pedido recebido pelo PC', locating:'Localizando versão', comparing:'Comparando versões', update_found:'Atualização encontrada', preparing:'Preparando atualização', processing:'Executando atualização', executing:'Executando atualização', validating:'Validando atualização', up_to_date:'Produto já está atualizado', no_match:'Não foi possível localizar correspondência', source_not_found:'Fonte não encontrada', source_version_missing:'Versão da fonte não identificada', relationship_required:'Vínculo seguro necessário', comparison_stale:'Comparação desatualizada', completed:'Atualização concluída', rolled_back:'Falha revertida com segurança', error:'Erro' };
    const versions = data.previous_version || data.new_version ? ` · ${data.previous_version || '?'} → ${data.new_version || '?'}` : '';
    const tone = !terminal ? 'loading' : (['up_to_date','no_match','source_not_found','source_version_missing','comparison_stale'].includes(data.status) ? 'empty' : (data.status === 'completed' ? 'success' : 'error'));
    const label = labels[data.status] || data.message || 'Processando';
    show(`${label}${data.source ? ` · ${data.source}` : ''}${versions}`, tone, {
      stage: label,
      source: data.source || 'Ainda não definida',
      version: data.previous_version || data.new_version
        ? `${data.previous_version || '?'} → ${data.new_version || '?'}` : 'Aguardando consulta',
    });
    if (!terminal) window.setTimeout(() => poll(requestId).catch(fail), 3000);
    else { button.disabled=false; button.removeAttribute('aria-busy'); }
  };
  const fail = (error) => { show(error.message || String(error), 'error', {stage:'Erro ao processar'}); button.disabled = false; button.removeAttribute('aria-busy'); };
  button.addEventListener('click', async () => {
    button.disabled = true; button.setAttribute('aria-busy', 'true');
    show('Enviando pedido seguro…', 'loading', {stage:'Criando pedido', source:'Ainda não definida', version:'Aguardando consulta'});
    try {
      const data = await request('crapscraper_manual_start');
      show(data.message || 'Pedido criado. Aguardando o CrapScraper no PC.', 'loading', {stage:'Aguardando o CrapScraper', source:'Ainda não definida', version:'Aguardando consulta'});
      await poll(data.request_id);
    } catch (error) { fail(error); }
  });
})();
