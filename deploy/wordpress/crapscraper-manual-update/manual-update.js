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
  const toolbarTrigger = document.querySelector('#wp-admin-bar-crapscraper-manual-toolbar > .ab-item');
  const closeButton = root.querySelector('[data-cs-close]');
  const updateToggle = root.querySelector('.cs-accordion > [data-cs-accordion-toggle]');
  const updatePanel = root.querySelector('.cs-accordion > [data-cs-accordion-panel]');
  const historyToggle = root.querySelector('[data-cs-history-toggle]');
  const historyPanel = root.querySelector('[data-cs-history-panel]');
  const monitor = root.querySelector('[data-cs-monitor]');
  const monitorLabel = root.querySelector('[data-cs-monitor-label]');
  let historyLoaded = false;

  if (root.dataset.context === 'toolbar' && toolbarTrigger) {
    const positionToolbar = () => {
      if (root.hidden) return;
      const triggerRect = toolbarTrigger.getBoundingClientRect();
      const margin = 8;
      const gap = 7;
      const panelWidth = root.offsetWidth;
      const top = Math.round(triggerRect.bottom + gap);
      const left = Math.round(Math.min(
        window.innerWidth - panelWidth - margin,
        Math.max(margin, triggerRect.right - panelWidth)
      ));
      root.style.top = `${top}px`;
      root.style.left = `${left}px`;
      root.style.right = 'auto';
      root.style.maxHeight = `${Math.max(180, window.innerHeight - top - margin)}px`;
      root.style.setProperty('--cs-anchor-x', `${Math.round(Math.min(panelWidth - 18, Math.max(18, triggerRect.left + (triggerRect.width / 2) - left)))}px`);
    };
    const setToolbarOpen = (open, restoreFocus = false) => {
      if (open) root.style.removeProperty('display');
      else root.style.display = 'none';
      root.hidden = !open;
      toolbarTrigger.setAttribute('aria-expanded', String(open));
      toolbarTrigger.parentElement?.classList.toggle('is-active', open);
      if (open) {
        positionToolbar();
        loadMonitor();
        closeButton?.focus();
      }
      else if (restoreFocus) toolbarTrigger.focus();
    };
    toolbarTrigger.setAttribute('aria-haspopup', 'dialog');
    toolbarTrigger.setAttribute('aria-controls', root.id);
    toolbarTrigger.setAttribute('aria-expanded', 'false');
    toolbarTrigger.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      setToolbarOpen(root.hidden);
    });
    closeButton?.addEventListener('click', () => setToolbarOpen(false, true));
    document.addEventListener('click', event => {
      if (!root.hidden && !root.contains(event.target) && !toolbarTrigger.contains(event.target)) setToolbarOpen(false);
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !root.hidden) setToolbarOpen(false, true);
    });
    window.addEventListener('resize', positionToolbar);
    window.addEventListener('scroll', positionToolbar, {passive:true});
  }

  updateToggle?.addEventListener('click', () => {
    const expanded = updateToggle.getAttribute('aria-expanded') !== 'true';
    updateToggle.setAttribute('aria-expanded', String(expanded));
    updatePanel.hidden = !expanded;
  });

  const request = async (action, values = {}) => {
    const body = new URLSearchParams({ action, nonce: CrapScraperManual.nonce, product_id: productId, ...values });
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(CrapScraperManual.ajaxUrl, {
        method: 'POST', credentials: 'same-origin', body, signal: controller.signal,
      });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result?.data?.message || 'Falha na atualização.');
      return result.data;
    } catch (error) {
      if (error?.name === 'AbortError') throw new Error('O servidor demorou demais para responder. Tente novamente.');
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  };
  const setMonitor = data => {
    if (!monitor) return;
    const state = ['online', 'offline'].includes(data?.state) ? data.state : 'checking';
    monitor.classList.remove('is-online', 'is-offline', 'is-checking');
    monitor.classList.add(`is-${state}`);
    const label = data?.label || (state === 'checking' ? 'Verificando' : 'Offline');
    if (monitorLabel) monitorLabel.textContent = label;
    monitor.title = data?.title || 'Não foi possível consultar o monitor da loja';
  };
  const loadMonitor = async () => {
    if (!monitor || document.hidden) return;
    try {
      setMonitor(await request('crapscraper_manual_monitor'));
    } catch (_error) {
      setMonitor({state:'checking', label:'Indisponível', title:'Não foi possível consultar o monitor da loja'});
    }
  };
  const historyLabels = {pending:'Aguardando',claimed:'Recebido pelo PC',checking:'Verificando',locating:'Localizando',comparing:'Comparando',update_available:'Atualização encontrada',update_found:'Atualização encontrada',preparing:'Preparando',processing:'Processando',executing:'Executando',validating:'Validando',already_updated:'Já atualizado',up_to_date:'Já atualizado',no_match:'Sem correspondência',source_not_found:'Fonte não encontrada',source_version_missing:'Versão ausente',relationship_required:'Vínculo necessário',comparison_stale:'Comparação desatualizada',completed:'Concluído',error:'Erro',blocked:'Bloqueado',rolled_back:'Revertido',rollback_required:'Rollback necessário'};
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
    const terminal = ['already_updated','up_to_date','no_match','source_not_found','source_version_missing','relationship_required','comparison_stale','completed','error','blocked','rolled_back','rollback_required'].includes(data.status);
    const labels = { pending:'Aguardando o CrapScraper', claimed:'Pedido recebido pelo PC', checking:'Verificando versão atual', locating:'Localizando versão', comparing:'Comparando versões', update_available:'Atualização encontrada', update_found:'Atualização encontrada', preparing:'Preparando atualização', processing:'Executando atualização', executing:'Executando atualização', validating:'Validando atualização', already_updated:'Produto já está atualizado', up_to_date:'Produto já está atualizado', no_match:'Não foi possível localizar correspondência', source_not_found:'Fonte não encontrada', source_version_missing:'Versão da fonte não identificada', relationship_required:'Vínculo seguro necessário', comparison_stale:'Comparação desatualizada', completed:'Atualização concluída', rolled_back:'Falha revertida com segurança', error:'Erro' };
    const currentVersion = data.current_version || data.previous_version || '';
    const targetVersion = data.target_version || data.new_version || '';
    const versions = currentVersion || targetVersion ? ` · ${currentVersion || '?'} → ${targetVersion || '?'}` : '';
    const tone = !terminal ? 'loading' : (['already_updated','up_to_date','no_match','source_not_found','source_version_missing','comparison_stale'].includes(data.status) ? 'empty' : (data.status === 'completed' ? 'success' : 'error'));
    const label = labels[data.status] || data.message || 'Processando';
    show(`${label}${data.source ? ` · ${data.source}` : ''}${versions}`, tone, {
      stage: label,
      source: data.source || 'Ainda não definida',
      version: currentVersion || targetVersion
        ? `${currentVersion || '?'} → ${targetVersion || '?'}` : 'Aguardando consulta',
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
