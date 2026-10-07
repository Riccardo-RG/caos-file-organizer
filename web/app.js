'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const I = window.CaosI18n;
  const t = I.t;
  const serverMessage = I.translateServerMessage;
  I.applyStatic();
  const categoryNames = { images: 'Immagini', documents: 'Documenti', archives: 'Archivi', audio: 'Audio', video: 'Video', code: 'Codice', other: 'Altro' };
  const stateNames = { applied: 'Completato', completed: 'Completato', undone: 'Annullato', failed: 'Non completato', partial: 'Parziale', undo_partial: 'Ripristino parziale', applying: 'In corso', undoing: 'Ripristino in corso', rolled_back: 'Ripristinato', interrupted: 'Interrotto' };
  const fileStateNames = { ready: 'Da riordinare', unchanged: 'Già in ordine', skipped: 'Escluso' };
  let config = null;
  let plan = null;
  let selection = new Set();
  let stale = false;
  let applied = false;
  let lastOperationState = null;
  let busy = false;
  let operations = [];
  let confirmResolver = null;
  let browserFolder = null;
  let folderRequest = 0;
  let lastResultOperation = null;
  let previewRestored = false;
  let dialogContent = null;
  let folderErrorMessage = '';
  let connectionErrorMessage = '';
  let busyMessage = '';
  const activeToasts = new Set();

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function bytes(value) {
    const n = Number(value) || 0;
    if (n < 1000) return `${n} B`;
    const index = Math.min(Math.floor(Math.log(n) / Math.log(1000)), 4);
    return `${(n / (1000 ** index)).toLocaleString(I.locale, { maximumFractionDigits: 1 })} ${['B', 'KB', 'MB', 'GB', 'TB'][index]}`;
  }

  function date(value) {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.valueOf())) return String(value || '');
    return new Intl.DateTimeFormat(I.locale, { dateStyle: 'medium', timeStyle: 'short' }).format(parsed);
  }

  function relative(path, root) {
    const value = String(path || '');
    const base = String(root || '').replace(/\/$/, '') + '/';
    return value.startsWith(base) ? value.slice(base.length) : value;
  }

  function toast(message, error = false) {
    const node = element('div', `toast${error ? ' error' : ''}`);
    const label = element('span');
    const refresh = () => { label.textContent = typeof message === 'function' ? message() : I.retranslate(serverMessage(message)); };
    refresh();
    node.append(label);
    const close = element('button', '', '×');
    close.type = 'button';
    close.setAttribute('aria-label', t('Chiudi notifica'));
    const refreshToast = () => {
      refresh();
      close.setAttribute('aria-label', t('Chiudi notifica'));
    };
    activeToasts.add(refreshToast);
    const dismiss = () => { activeToasts.delete(refreshToast); node.remove(); };
    close.addEventListener('click', dismiss);
    node.append(close);
    $('toast-region').append(node);
    window.setTimeout(dismiss, error ? 14000 : 6500);
  }

  async function api(path, body) {
    const headers = { 'Accept': 'application/json' };
    const options = { method: body === undefined ? 'GET' : 'POST', headers, credentials: 'same-origin', cache: 'no-store' };
    if (body !== undefined) {
      if (!config?.csrf) throw new Error(t('La connessione locale non è pronta. Ricarica la pagina e riprova.'));
      headers['Content-Type'] = 'application/json';
      headers['X-Caos-Token'] = config.csrf;
      options.body = JSON.stringify(body);
    }
    let response;
    try { response = await fetch(path, options); }
    catch { throw new Error(t('Non riesco a raggiungere l’app locale. Verifica che il programma sia ancora aperto, poi riprova.')); }
    let data;
    try { data = await response.json(); }
    catch { throw new Error(t('Il programma ha restituito una risposta inattesa. Riprova oppure riavvia l’app.')); }
    if (!response.ok) throw new Error(data.error || t('Non è stato possibile completare questa operazione.'));
    return data;
  }

  async function runBusy(label, action) {
    if (busy) return;
    busy = true;
    busyMessage = label;
    $('busy-label').textContent = I.retranslate(label);
    $('busy-overlay').hidden = false;
    $('main').inert = true;
    document.querySelector('.sidebar').inert = true;
    document.body.setAttribute('aria-busy', 'true');
    try { return await action(); }
    catch (error) { toast(error.message || t('Si è verificato un errore.'), true); }
    finally {
      busy = false;
      $('busy-overlay').hidden = true;
      $('main').inert = false;
      document.querySelector('.sidebar').inert = false;
      document.body.removeAttribute('aria-busy');
    }
  }

  function renderDialog() {
    if (!dialogContent) return;
    const { title, description, details = '', confirm = t('Conferma'), icon = '↗', information = false } = dialogContent();
    $('dialog-title').textContent = title;
    $('dialog-description').textContent = description;
    $('dialog-details').textContent = details;
    $('dialog-details').hidden = !details;
    $('dialog-icon').textContent = icon;
    $('dialog-confirm').textContent = confirm;
    $('dialog-cancel').hidden = information;
  }

  function ask(content) {
    if (confirmResolver) confirmResolver(false);
    dialogContent = typeof content === 'function' ? content : () => content;
    renderDialog();
    $('confirm-dialog').showModal();
    // Put initial focus on the reversible choice when confirming a file operation.
    ($('dialog-cancel').hidden ? $('dialog-confirm') : $('dialog-cancel')).focus();
    return new Promise((resolve) => { confirmResolver = resolve; });
  }

  function finishDialog(result) {
    $('confirm-dialog').close();
    dialogContent = null;
    const resolve = confirmResolver;
    confirmResolver = null;
    if (resolve) resolve(result);
  }
  $('dialog-confirm').addEventListener('click', () => finishDialog(true));
  $('dialog-cancel').addEventListener('click', () => finishDialog(false));
  $('confirm-dialog').addEventListener('cancel', (event) => { event.preventDefault(); finishDialog(false); });

  function navigate(refreshHistory = true) {
    const mapping = { '#cronologia': 'history', '#come-funziona': 'help' };
    const page = mapping[location.hash] || 'organize';
    ['organize', 'history', 'help'].forEach((name) => { $(`page-${name}`).hidden = page !== name; });
    document.querySelectorAll('[data-page]').forEach((link) => {
      const active = link.dataset.page === page;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    if (page === 'history' && config && refreshHistory) loadHistory().catch((error) => toast(error.message, true));
    document.title = `${page === 'history' ? t('Cronologia') : page === 'help' ? t('Come funziona') : t('Ogni file, al suo posto.')} — caos`;
  }
  window.addEventListener('hashchange', navigate);

  function markStale() {
    if (!plan || applied) return;
    stale = true;
    $('stale-warning').hidden = false;
    updateSelection();
  }

  function setPath(path) {
    if (!path) return;
    $('folder-path').value = path;
    markStale();
    $('folder-path').setCustomValidity('');
  }

  function updateHints() {
    const groupingHints = {
      type: t('Immagini, Documenti, Video… ognuno a casa sua.'),
      month: t('Usa la data di ultima modifica del file.'),
      type_month: t('Una cartella per tipo, poi una per anno e mese.'),
      none: t('I file restano nella loro cartella attuale.')
    };
    const renameHints = {
      keep: t('I nomi restano esattamente come sono.'),
      clean: t('Nomi più semplici, senza spazi o caratteri superflui.'),
      sequence: t('Un nome comune, seguito da un numero progressivo.')
    };
    $('grouping-hint').textContent = groupingHints[$('grouping').value];
    $('rename-hint').textContent = renameHints[$('rename').value];
    $('prefix-row').hidden = $('rename').value !== 'sequence';
    $('recursive-hint').textContent = $('recursive').checked
      ? t('Attivato: includiamo anche i file nelle sottocartelle consentite.')
      : t('Disattivato: solo i file nella cartella scelta.');
  }

  $('organize-form').addEventListener('input', markStale);
  $('organize-form').addEventListener('change', () => { updateHints(); markStale(); });
  $('folder-path').addEventListener('input', () => $('folder-path').setCustomValidity(''));

  async function browseFolder(path) {
    const request = ++folderRequest;
    browserFolder = null;
    $('folder-browser-path').value = path || '';
    $('folder-current-path').textContent = '—';
    $('folder-up').disabled = true;
    $('folder-select').disabled = true;
    $('folder-browser-error').hidden = true;
    $('folder-browser-reason').hidden = true;
    $('folder-list').replaceChildren();
    $('folder-list').setAttribute('aria-busy', 'true');
    $('folder-browser-status').textContent = t('Leggiamo le sottocartelle…');
    try {
      const data = await api(`/api/folders${path ? `?path=${encodeURIComponent(path)}` : ''}`);
      if (request !== folderRequest || !$('folder-dialog').open) return;
      browserFolder = data;
      $('folder-browser-path').value = data.path;
      $('folder-current-path').textContent = data.path;
      renderFolder(data);
    } catch (error) {
      if (request !== folderRequest || !$('folder-dialog').open) return;
      folderErrorMessage = error.message;
      $('folder-browser-error').textContent = serverMessage(folderErrorMessage);
      $('folder-browser-error').hidden = false;
      $('folder-browser-status').textContent = t('Incolla un altro percorso e premi Apri, oppure scegli una scorciatoia.');
    } finally {
      if (request === folderRequest) $('folder-list').removeAttribute('aria-busy');
    }
  }

  function renderFolder(data) {
    $('folder-up').disabled = !data.parent;
    $('folder-select').disabled = !data.can_select || $('folder-browser-path').value.trim() !== data.path;
    $('folder-browser-reason').textContent = serverMessage(data.reason) || t('Questa cartella non può essere riordinata. Scegli una sottocartella personale.');
    $('folder-browser-reason').hidden = Boolean(data.can_select);
    const folders = Array.isArray(data.folders) ? data.folders : [];
    $('folder-browser-status').textContent = folders.length
      ? t(folders.length === 1 ? '{count} sottocartella disponibile' : '{count} sottocartelle disponibili', { count: folders.length.toLocaleString(I.locale) })
      : t('Nessuna sottocartella visibile. Puoi usare la cartella corrente se selezionabile.');
    $('folder-list').replaceChildren(...folders.map((folder) => {
      const item = element('li');
      const button = element('button', 'folder-entry');
      button.type = 'button';
      button.setAttribute('aria-label', t('Apri la cartella {name}', { name: folder.name }));
      const icon = element('span', 'folder-entry-icon', '▱');
      icon.setAttribute('aria-hidden', 'true');
      const arrow = element('span', 'folder-entry-arrow', '→');
      arrow.setAttribute('aria-hidden', 'true');
      button.append(icon, element('span', 'folder-entry-name', folder.name), arrow);
      button.addEventListener('click', () => browseFolder(folder.path));
      item.append(button);
      return item;
    }));
  }

  function closeFolderBrowser() {
    folderRequest += 1;
    browserFolder = null;
    $('folder-dialog').close();
  }

  $('pick-folder').addEventListener('click', () => {
    if (busy) return;
    $('folder-dialog').showModal();
    browseFolder($('folder-path').value.trim() || config?.home);
    $('folder-browser-path').focus();
  });
  $('folder-location-form').addEventListener('submit', (event) => {
    event.preventDefault();
    browseFolder($('folder-browser-path').value.trim());
  });
  $('folder-browser-path').addEventListener('input', () => {
    $('folder-select').disabled = !browserFolder?.can_select || $('folder-browser-path').value.trim() !== browserFolder.path;
  });
  $('folder-up').addEventListener('click', () => { if (browserFolder?.parent) browseFolder(browserFolder.parent); });
  document.querySelectorAll('[data-folder-place]').forEach((button) => {
    button.addEventListener('click', () => {
      const path = config?.[button.dataset.folderPlace];
      if (path || button.dataset.folderPlace === 'home') browseFolder(path);
      else {
        folderErrorMessage = 'Questa scorciatoia non è disponibile. Incolla il percorso della cartella e premi Apri.';
        $('folder-browser-error').textContent = t(folderErrorMessage);
        $('folder-browser-error').hidden = false;
      }
    });
  });
  $('folder-select').addEventListener('click', () => {
    if (!browserFolder?.can_select || $('folder-select').disabled) return;
    setPath(browserFolder.path);
    closeFolderBrowser();
  });
  $('folder-cancel').addEventListener('click', closeFolderBrowser);
  $('folder-dialog').addEventListener('cancel', (event) => { event.preventDefault(); closeFolderBrowser(); });
  $('use-downloads').addEventListener('click', () => { if (config) setPath(config.downloads); });

  async function demo() {
    await runBusy(t('Prepariamo un piccolo caos da sistemare…'), async () => {
      const result = await api('/api/demo', {});
      setPath(result.path);
      $('grouping').value = 'type';
      $('rename').value = 'clean';
      $('recursive').checked = false;
      document.querySelectorAll('[name=categories]').forEach((input) => { input.checked = true; });
      updateHints();
      location.hash = '#riordina';
      await generatePreview();
      toast(t('Ecco i file di esempio: puoi provare il riordino e poi annullarlo.'));
    });
  }
  ['use-demo', 'empty-demo', 'help-demo'].forEach((id) => $(id).addEventListener('click', demo));

  function options() {
    const grouping = $('grouping').value;
    return {
      organize: grouping !== 'none',
      grouping: grouping === 'none' ? 'type' : grouping,
      rename: $('rename').value,
      prefix: $('prefix').value.trim() || 'file',
      recursive: $('recursive').checked,
      categories: Array.from(document.querySelectorAll('[name=categories]:checked'), (input) => input.value)
    };
  }

  async function generatePreview() {
    const root = $('folder-path').value.trim();
    const data = await api('/api/preview', { root, options: options() });
    plan = data;
    lastResultOperation = null;
    previewRestored = false;
    selection = new Set(plan.files.filter((file) => file.status === 'ready').map((file) => String(file.id)));
    stale = false;
    applied = false;
    lastOperationState = null;
    $('stale-warning').hidden = true;
    $('preview-empty').hidden = true;
    $('preview-content').hidden = false;
    $('result-banner').hidden = true;
    $('file-search').value = '';
    $('status-filter').value = 'all';
    $('preview-subtitle').textContent = t('{count} file analizzati · {root}', { count: plan.files.length.toLocaleString(I.locale), root: plan.root });
    $('preview-label').textContent = t('ANTEPRIMA');
    renderStats();
    renderFiles();
    $('preview-section').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
  }

  $('organize-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!$('folder-path').value.trim()) {
      $('folder-path').setCustomValidity(t('Scegli una cartella oppure incolla il suo percorso.'));
      $('folder-path').reportValidity();
      return;
    }
    if (!options().categories.length) { toast(t('Scegli almeno una categoria di file da includere.'), true); return; }
    runBusy(t('Leggiamo la cartella e prepariamo l’anteprima…'), generatePreview);
  });

  function renderStats() {
    const files = plan.files;
    const stats = [
      [files.filter((file) => file.status === 'ready').length, t('Da riordinare')],
      [files.filter((file) => file.status === 'unchanged').length, t('Già in ordine')],
      [files.filter((file) => file.status === 'skipped').length, t('Esclusi')],
      [bytes(files.reduce((total, file) => total + (Number(file.size) || 0), 0)), t('Dimensione totale')]
    ];
    $('preview-stats').replaceChildren(...stats.map(([value, label]) => {
      const box = element('div', 'stat-box');
      box.append(element('strong', '', typeof value === 'number' ? value.toLocaleString(I.locale) : value), element('span', '', label));
      return box;
    }));
  }

  function visibleFiles() {
    if (!plan) return [];
    const query = $('file-search').value.trim().toLocaleLowerCase(I.language);
    const filter = $('status-filter').value;
    return plan.files.filter((file) => (filter === 'all' || file.status === filter) && (!query || `${file.source} ${file.destination || ''}`.toLocaleLowerCase(I.language).includes(query)));
  }

  function renderFiles() {
    if (!plan) {
      $('file-rows').replaceChildren();
      updateSelection();
      return;
    }
    const files = visibleFiles();
    const fragment = document.createDocumentFragment();
    for (const file of files) {
      const id = String(file.id);
      const row = element('tr', selection.has(id) ? 'selected' : '');
      const checkCell = element('td', 'check-cell');
      const check = element('input');
      check.type = 'checkbox';
      check.checked = selection.has(id);
      check.disabled = file.status !== 'ready' || applied;
      check.setAttribute('aria-label', t('Seleziona {name}', { name: relative(file.source, plan.root) }));
      check.addEventListener('change', () => {
        if (check.checked) selection.add(id); else selection.delete(id);
        row.classList.toggle('selected', check.checked);
        updateSelection();
      });
      checkCell.append(check);

      const nameCell = element('td');
      const path = element('div', 'file-path');
      const filename = String(file.source || '').split('/').pop() || '';
      const extension = filename.includes('.') ? filename.split('.').pop().slice(0, 4).toUpperCase() : 'FILE';
      const icon = element('span', `file-icon ${file.category}`, extension);
      icon.setAttribute('aria-hidden', 'true');
      const names = element('div', 'file-names');
      const original = element('div', 'file-original', relative(file.source, plan.root));
      original.title = file.source;
      names.append(original);
      if (file.destination && file.status !== 'skipped') {
        const target = element('div', 'file-destination', relative(file.destination, plan.root));
        target.title = file.destination;
        names.append(target);
      }
      if (file.reason) names.append(element('div', 'file-reason', serverMessage(file.reason)));
      path.append(icon, names);
      nameCell.append(path);

      const categoryCell = element('td');
      const category = element('span', 'type-label');
      category.append(element('i', `category-dot ${file.category}`), document.createTextNode(t(categoryNames[file.category] || 'Altro')));
      categoryCell.append(category);
      const sizeCell = element('td', 'file-size size-cell', bytes(file.size));
      const statusCell = element('td');
      statusCell.append(element('span', `status-badge ${file.status}`, t(fileStateNames[file.status] || file.status)));
      row.append(checkCell, nameCell, categoryCell, sizeCell, statusCell);
      fragment.append(row);
    }
    $('file-rows').replaceChildren(fragment);
    $('no-results').hidden = files.length !== 0;
    $('no-results').textContent = plan.files.length ? t('Nessun file corrisponde a questa ricerca.') : t('Questa cartella non contiene file da analizzare con le opzioni scelte.');
    updateSelection();
  }

  function updateSelection() {
    const count = selection.size;
    const total = plan?.files.filter((file) => file.status === 'ready').length || 0;
    const size = plan?.files.filter((file) => selection.has(String(file.id))).reduce((value, file) => value + (Number(file.size) || 0), 0) || 0;
    $('selection-count').textContent = t(count === 1 ? '{count} file selezionato' : '{count} file selezionati', { count: count.toLocaleString(I.locale) }) + (count ? ` · ${bytes(size)}` : '');
    $('apply-button').disabled = !count || stale || applied || !plan;
    $('apply-button').firstChild.textContent = applied
      ? (['applied', 'completed'].includes(lastOperationState) ? t('Operazione completata ') : t('Genera una nuova anteprima '))
      : t('Riordina {count}file ', { count: count ? `${count.toLocaleString(I.locale)} ` : '' });
    $('select-ready').textContent = total > 0 && count === total ? t('Deseleziona tutti') : t('Seleziona tutti');
    $('select-ready').disabled = !total || applied;
    const available = visibleFiles().filter((file) => file.status === 'ready');
    const selectedVisible = available.filter((file) => selection.has(String(file.id))).length;
    $('select-visible').checked = available.length > 0 && selectedVisible === available.length;
    $('select-visible').indeterminate = selectedVisible > 0 && selectedVisible < available.length;
    $('select-visible').disabled = !available.length || applied;
  }

  $('file-search').addEventListener('input', renderFiles);
  $('status-filter').addEventListener('change', renderFiles);
  $('select-visible').addEventListener('change', (event) => {
    if (!plan || applied) return;
    visibleFiles().filter((file) => file.status === 'ready').forEach((file) => {
      if (event.target.checked) selection.add(String(file.id)); else selection.delete(String(file.id));
    });
    renderFiles();
  });
  $('select-ready').addEventListener('click', () => {
    if (!plan || applied) return;
    const ready = plan.files.filter((file) => file.status === 'ready');
    if (selection.size === ready.length) selection.clear();
    else selection = new Set(ready.map((file) => String(file.id)));
    renderFiles();
  });

  function operationErrors(operation) {
    const errors = [];
    if (operation.error) errors.push(serverMessage(operation.error));
    if (Array.isArray(operation.errors)) operation.errors.forEach((error) => errors.push(serverMessage(typeof error === 'string' ? error : error.message || error.error || JSON.stringify(error))));
    if (Array.isArray(operation.entries)) operation.entries.forEach((entry) => {
      if (entry.error) errors.push(`${relative(entry.source || entry.destination, operation.root)}: ${serverMessage(entry.error)}`);
    });
    return [...new Set(errors)].join('\n');
  }

  function showResult(operation) {
    lastResultOperation = operation;
    const success = ['applied', 'completed'].includes(operation.state);
    const banner = $('result-banner');
    banner.className = `result-banner${success ? '' : ' warning'}`;
    const text = element('div');
    text.append(element('strong', '', success ? t('Un po’ di caos in meno. Fatto!') : t('Controlla il risultato dell’operazione.')));
    text.append(document.createTextNode(success ? t('{count} file riordinati. Puoi annullare dalla Cronologia.', { count: operation.count ?? selection.size }) : operationErrors(operation) || t('Stato: {state}. Trovi i dettagli nella Cronologia.', { state: t(stateNames[operation.state] || operation.state) })));
    const link = element('a', 'text-button', t('Vai alla Cronologia →'));
    link.href = '#cronologia';
    banner.replaceChildren(text, link);
    banner.hidden = false;
  }

  $('apply-button').addEventListener('click', async () => {
    if (!plan || !selection.size || stale || applied || busy) return;
    const chosen = plan.files.filter((file) => selection.has(String(file.id)));
    const answer = await ask(() => ({
      title: t('Riordiniamo {count} file?', { count: chosen.length }),
      description: t('Verranno applicati i cambiamenti mostrati nell’anteprima, solo ai file selezionati.\n\nCartella: {root}\n\nPotrai annullare dalla Cronologia, finché i file non vengono modificati o spostati di nuovo.', { root: plan.root }),
      details: chosen.slice(0, 6).map((file) => `${relative(file.source, plan.root)} → ${relative(file.destination, plan.root)}`).join('\n') + (chosen.length > 6 ? t('\n… e altri {count} file.', { count: chosen.length - 6 }) : ''),
      confirm: t('Sì, riordina {count} file', { count: chosen.length })
    }));
    if (!answer) return;
    await runBusy(t('Mettiamo ogni file al suo posto…'), async () => {
      const operation = await api('/api/apply', { plan_id: plan.id, selected_ids: chosen.map((file) => file.id) });
      applied = true;
      lastOperationState = operation.state;
      const success = ['applied', 'completed'].includes(operation.state);
      $('preview-label').textContent = success ? t('APPLICATA') : t(stateNames[operation.state] || 'DA VERIFICARE').toLocaleUpperCase(I.language);
      $('preview-subtitle').textContent = success
        ? t('Questa anteprima è stata applicata. Generane una nuova per altri cambiamenti.')
        : t('Controlla l’esito nella Cronologia e genera una nuova anteprima per continuare.');
      showResult(operation);
      renderFiles();
      await loadHistory();
      toast(success ? t('Fatto! I file sono al loro posto.') : t('Operazione terminata: controlla i dettagli nella Cronologia.'), !success);
      $('result-banner').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  });

  async function undo(operation) {
    const answer = await ask(() => ({
      title: t('Torniamo al punto di partenza?'),
      description: t('Annullerai il riordino del {date}. I file verranno riportati ai percorsi e ai nomi originali.\n\nCartella: {root}\n\nIl programma controlla che i file non siano cambiati e non sovrascrive file esistenti.', { date: date(operation.created_at), root: operation.root }),
      confirm: t('Sì, annulla il riordino'), icon: '↶'
    }));
    if (!answer) return;
    await runBusy(t('Ripristiniamo i percorsi originali…'), async () => {
      const result = await api('/api/undo', { operation_id: operation.id });
      if (plan && plan.root === operation.root) {
        plan = null;
        lastResultOperation = null;
        previewRestored = true;
        selection.clear();
        stale = false;
        applied = false;
        lastOperationState = null;
        $('file-rows').replaceChildren();
        $('preview-content').hidden = true;
        $('preview-empty').hidden = false;
        $('stale-warning').hidden = true;
        $('preview-label').textContent = t('ANTEPRIMA');
        $('preview-subtitle').textContent = t('Dopo il ripristino, genera una nuova anteprima per continuare.');
        $('result-banner').hidden = true;
        updateSelection();
      }
      if (result.state === 'undone' || result.state === 'rolled_back') toast(t('Riordino annullato. I file sono tornati al loro posto originale.'));
      else toast(() => operationErrors(result) || t('Controlla lo stato del ripristino nella Cronologia.'), true);
      await loadHistory();
    });
  }

  async function operationDetails(summary) {
    const operation = await runBusy(t('Recuperiamo i dettagli del riordino…'), () => api(`/api/operations/${encodeURIComponent(summary.id)}`));
    if (!operation) return;
    ask(() => {
      const entryStateNames = { moved: 'spostato', duplicated: 'spostamento da completare', pending: 'non spostato', undone: 'ripristinato', moving: 'spostamento in corso', linked: 'spostamento da completare', restoring: 'ripristino in corso', restored_linked: 'ripristino da completare', conflict: 'conflitto da verificare' };
      const lines = [t('Cartella: {root}', { root: operation.root }), t('Data: {date}', { date: date(operation.created_at) }), t('Stato: {state}', { state: t(stateNames[operation.state] || operation.state) }), t('File: {count}', { count: operation.count ?? 0 })];
      if (operation.undone_at) lines.push(t('Annullato: {date}', { date: date(operation.undone_at) }));
      if (operationErrors(operation)) lines.push('', operationErrors(operation));
      if (Array.isArray(operation.entries)) {
        lines.push('', ...operation.entries.map((entry) => `${relative(entry.source, operation.root)} → ${relative(entry.destination, operation.root)}${entry.state ? ` (${t(entryStateNames[entry.state] || entry.state)})` : ''}`));
      }
      return { title: t('Dettagli del riordino'), description: t('Operazione {id}', { id: operation.id }), details: lines.join('\n'), confirm: t('Chiudi'), icon: '≡', information: true };
    });
  }

  function renderHistory() {
    $('history-empty').hidden = operations.length > 0;
    $('history-count').textContent = operations.length;
    $('history-count').hidden = !operations.length;
    $('history-list').replaceChildren(...operations.map((operation) => {
      const card = element('article', 'history-card');
      const successful = ['applied', 'completed'].includes(operation.state);
      const restored = ['undone', 'rolled_back'].includes(operation.state);
      card.append(element('span', `history-icon${successful || restored ? '' : ' warning'}`, restored ? '↶' : successful ? '✓' : '!'));
      const info = element('div', 'history-info');
      const titleRow = element('div', 'history-title-row');
      titleRow.append(element('h3', '', t('{count} file · {name}', { count: operation.count ?? 0, name: operation.root?.split('/').filter(Boolean).pop() || t('Cartella') })), element('span', `status-badge ${operation.state}`, t(stateNames[operation.state] || operation.state)));
      info.append(titleRow, element('p', '', operation.root), element('div', 'history-meta', date(operation.created_at)));
      const actions = element('div', 'history-actions');
      const details = element('button', 'text-button', t('Dettagli'));
      details.type = 'button';
      details.addEventListener('click', () => operationDetails(operation));
      actions.append(details);
      if (operation.can_undo || (operation.can_undo === undefined && ['applied', 'completed', 'partial', 'undo_partial'].includes(operation.state))) {
        const restore = element('button', 'button button-secondary', t('↶  Annulla riordino'));
        restore.type = 'button';
        restore.addEventListener('click', () => undo(operation));
        actions.append(restore);
      }
      card.append(info, actions);
      return card;
    }));
  }

  async function loadHistory() {
    const data = await api('/api/history');
    operations = Array.isArray(data.operations) ? data.operations : [];
    renderHistory();
  }

  $('refresh-history').addEventListener('click', () => runBusy(t('Aggiorniamo la cronologia…'), loadHistory));

  function renderPreviewHeading() {
    if (plan && applied) {
      const success = ['applied', 'completed'].includes(lastOperationState);
      $('preview-label').textContent = success ? t('APPLICATA') : t(stateNames[lastOperationState] || 'DA VERIFICARE').toLocaleUpperCase(I.language);
      $('preview-subtitle').textContent = success
        ? t('Questa anteprima è stata applicata. Generane una nuova per altri cambiamenti.')
        : t('Controlla l’esito nella Cronologia e genera una nuova anteprima per continuare.');
    } else {
      $('preview-label').textContent = t('ANTEPRIMA');
      $('preview-subtitle').textContent = plan
        ? t('{count} file analizzati · {root}', { count: plan.files.length.toLocaleString(I.locale), root: plan.root })
        : t(previewRestored ? 'Dopo il ripristino, genera una nuova anteprima per continuare.' : 'Qui vedrai ogni cambiamento, prima che succeda.');
    }
  }

  window.addEventListener('caos:languagechange', () => {
    navigate(false);
    updateHints();
    renderPreviewHeading();
    if (plan) renderStats();
    renderFiles();
    renderHistory();
    if (lastResultOperation && !$('result-banner').hidden) showResult(lastResultOperation);
    if ($('folder-dialog').open) {
      if (browserFolder) renderFolder(browserFolder);
      else $('folder-browser-status').textContent = t($('folder-list').hasAttribute('aria-busy')
        ? 'Leggiamo le sottocartelle…'
        : 'Incolla un altro percorso e premi Apri, oppure scegli una scorciatoia.');
      if (!$('folder-browser-error').hidden) $('folder-browser-error').textContent = I.retranslate(serverMessage(folderErrorMessage));
    }
    if (dialogContent) renderDialog();
    if (busy) $('busy-label').textContent = I.retranslate(busyMessage);
    if (!$('connection-error').hidden) $('connection-error').textContent = I.retranslate(serverMessage(connectionErrorMessage));
    if ($('folder-path').validity.customError) $('folder-path').setCustomValidity(t('Scegli una cartella oppure incolla il suo percorso.'));
    activeToasts.forEach((refresh) => refresh());
  });

  async function initialize() {
    navigate();
    try {
      config = await api('/api/config');
      $('app-version').textContent = `v${String(config.version || '1.0').replace(/^v/, '')}`;
      $('connection-error').hidden = true;
      await loadHistory();
    } catch (error) {
      connectionErrorMessage = error.message;
      $('connection-error').textContent = serverMessage(connectionErrorMessage);
      $('connection-error').hidden = false;
      toast(error.message, true);
    }
  }
  initialize();
})();
