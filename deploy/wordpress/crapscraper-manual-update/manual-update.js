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
  const dragHandle = root.querySelector('[data-cs-drag-handle]');
  const minimize = root.querySelector('[data-cs-minimize]');
  const historyToggle = root.querySelector('[data-cs-history-toggle]');
  const historyPanel = root.querySelector('[data-cs-history-panel]');
  const storageKey = 'crapscraper-manual-panel-v1';
  let panelState = { x: null, y: null, minimized: false };
  let historyLoaded = false;

  const persistPanel = () => {
    try { window.localStorage.setItem(storageKey, JSON.stringify(panelState)); } catch (_error) {}
  };
  const clampPanel = (x, y) => {
    const margin = 8;
    const maxX = Math.max(margin, window.innerWidth - root.offsetWidth - margin);
    const maxY = Math.max(margin, window.innerHeight - root.offsetHeight - margin);
    return { x: Math.min(Math.max(margin, x), maxX), y: Math.min(Math.max(margin, y), maxY) };
  };
  const placePanel = (x, y, save = true) => {
    if (root.dataset.context !== 'frontend' || window.innerWidth <= 782) return;
    const next = clampPanel(Number(x) || 8, Number(y) || 8);
    root.style.left = `${next.x}px`;
    root.style.top = `${next.y}px`;
    root.style.right = 'auto';
    panelState.x = next.x; panelState.y = next.y;
    if (save) persistPanel();
  };
  const setMinimized = (value, save = true) => {
    panelState.minimized = Boolean(value);
    root.classList.toggle('is-minimized', panelState.minimized);
    if (minimize) {
      minimize.setAttribute('aria-expanded', String(!panelState.minimized));
      minimize.setAttribute('aria-label', panelState.minimized ? 'Expandir painel' : 'Minimizar painel');
      minimize.title = panelState.minimized ? 'Expandir painel' : 'Minimizar painel';
      minimize.querySelector('span').textContent = panelState.minimized ? '⬇️' : '−';
    }
    if (panelState.x !== null && panelState.y !== null) placePanel(panelState.x, panelState.y, false);
    if (save) persistPanel();
  };

  if (root.dataset.context === 'frontend') {
    try { panelState = { ...panelState, ...JSON.parse(window.localStorage.getItem(storageKey) || '{}') }; } catch (_error) {}
    setMinimized(panelState.minimized, false);
    if (panelState.x !== null && panelState.y !== null) placePanel(panelState.x, panelState.y, false);
    minimize?.addEventListener('click', () => setMinimized(!panelState.minimized));
    dragHandle?.addEventListener('pointerdown', (event) => {
      if (event.target.closest('[data-cs-minimize]') || window.innerWidth <= 782) return;
      const rect = root.getBoundingClientRect();
      const offsetX = event.clientX - rect.left, offsetY = event.clientY - rect.top;
      root.classList.add('is-dragging');
      dragHandle.setPointerCapture?.(event.pointerId);
      const move = (nextEvent) => { nextEvent.preventDefault(); placePanel(nextEvent.clientX - offsetX, nextEvent.clientY - offsetY, false); };
      const finish = () => {
        root.classList.remove('is-dragging');
        dragHandle.removeEventListener('pointermove', move);
        dragHandle.removeEventListener('pointerup', finish);
        dragHandle.removeEventListener('pointercancel', finish);
        persistPanel();
      };
      dragHandle.addEventListener('pointermove', move);
      dragHandle.addEventListener('pointerup', finish);
      dragHandle.addEventListener('pointercancel', finish);
    });
    dragHandle?.addEventListener('keydown', (event) => {
      const deltas = {ArrowLeft:[-16,0],ArrowRight:[16,0],ArrowUp:[0,-16],ArrowDown:[0,16]};
      if (event.key === 'Home') { event.preventDefault(); root.style.left=''; root.style.top=''; root.style.right=''; panelState.x=null; panelState.y=null; persistPanel(); return; }
      if (!deltas[event.key]) return;
      event.preventDefault();
      const rect=root.getBoundingClientRect(),delta=deltas[event.key];
      placePanel(rect.left+delta[0],rect.top+delta[1]);
    });
    window.addEventListener('resize', () => {
      if (window.innerWidth <= 782) { root.style.left=''; root.style.top=''; root.style.right=''; return; }
      if (panelState.x !== null && panelState.y !== null) placePanel(panelState.x,panelState.y,false);
    });
  }

  const request = async (action, values = {}) => {
    const body = new URLSearchParams({ action, nonce: CrapScraperManual.nonce, product_id: productId, ...values });
    const response = await fetch(CrapScraperManual.ajaxUrl, { method: 'POST', credentials: 'same-origin', body });
    const result = await response.json();
    if (!response.ok || !result.success) throw new Error(result?.data?.message || 'Falha na atualização.');
    return result.data;
  };
  const historyLabels = {pending:'Aguardando',claimed:'Recebido pelo PC',locating:'Localizando',comparing:'Comparando',update_found:'Atualização encontrada',preparing:'Preparando',processing:'Processando',executing:'Executando',validating:'Validando',up_to_date:'Já atualizado',no_match:'Sem correspondência',source_not_found:'Fonte não encontrada',source_version_missing:'Versão ausente',relationship_required:'Vínculo necessário',comparison_stale:'Comparação desatualizada',completed:'Concluído',error:'Erro',blocked:'Bloqueado',rolled_back:'Revertido',rollback_required:'Rollback necessário'};
  const loadHistory = async (force = false) => {
    if (!historyPanel || (historyLoaded && !force)) return;
    historyPanel.classList.remove('is-error');
    historyPanel.innerHTML = '<div class="cs-history-empty">Carregando últimas atualizações…</div>';
    try {
      const data = await request('crapscraper_manual_history');
      const rows = Array.isArray(data.history) ? data.history.slice(0, 3) : [];
      historyPanel.textContent = '';
      if (!rows.length) {
        historyPanel.innerHTML = '<div class="cs-history-empty">Nenhuma atualização registrada para este produto.</div>';
      } else {
        const list = document.createElement('ol');
        list.className = 'cs-history-list';
        rows.forEach(item => {
          const row = document.createElement('li');
          const head = document.createElement('div'); head.className = 'cs-history-item-head';
          const label = document.createElement('strong'); label.textContent = historyLabels[item.status] || item.status || 'Atualização';
          const date = document.createElement('time'); date.textContent = item.date || 'Data não informada';
          head.append(label, date);
          const detail = document.createElement('div'); detail.className = 'cs-history-item-detail';
          const versions = item.previous_version || item.new_version ? `${item.previous_version || '?'} → ${item.new_version || '?'}` : 'Versão não informada';
          detail.textContent = `${item.source || 'Origem não definida'} · ${versions}`;
          row.append(head, detail);
          if (item.message) { const message = document.createElement('p'); message.textContent = item.message; row.append(message); }
          list.append(row);
        });
        historyPanel.append(list);
      }
      historyLoaded = true;
    } catch (error) {
      historyPanel.textContent = error.message || 'Não foi possível carregar o histórico.';
      historyPanel.classList.add('is-error');
    }
  };
  historyToggle?.addEventListener('click', () => {
    const expanded = historyToggle.getAttribute('aria-expanded') !== 'true';
    historyToggle.setAttribute('aria-expanded', String(expanded));
    historyPanel.hidden = !expanded;
    if (expanded) loadHistory();
  });
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
    else {
      button.disabled=false; button.removeAttribute('aria-busy'); historyLoaded=false;
      if (historyToggle?.getAttribute('aria-expanded') === 'true') loadHistory(true);
    }
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
