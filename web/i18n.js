'use strict';

// Keep interface translations separate from user paths and stored file operations.
(() => {
  const storageKey = 'caos.language';
  const translations = {
    "Riordina e rinomina i tuoi file, con anteprima e possibilità di annullare. Tutto sul tuo computer.": "Organize and rename your files, with a preview and undo. Everything stays on your computer.",
    "caos — Ogni file, al suo posto.": "caos — Every file in its place.",
    "Vai al contenuto": "Skip to content",
    "Navigazione principale": "Main navigation",
    "caos, pagina iniziale": "caos, home",
    "MENO CAOS. PIÙ SPAZIO.": "LESS CHAOS. MORE SPACE.",
    "Riordina": "Organize",
    "Cronologia": "History",
    "Come funziona": "How it works",
    "Il tuo computer.": "Your computer.",
    "I tuoi file.": "Your files.",
    "Nessun upload, nessun account.": "No uploads, no account.",
    "Tutto resta qui.": "Everything stays here.",
    "Spazio locale": "Local workspace",
    "IL TUO PICCOLO ANGOLO DI ORDINE": "YOUR LITTLE CORNER OF ORDER",
    "100% locale": "100% local",
    "Tema": "Theme",
    "Tema dell’interfaccia": "Interface theme",
    "Sistema": "System",
    "Chiaro": "Light",
    "Scuro": "Dark",
    "Lingua": "Language",
    "Lingua dell’interfaccia": "Interface language",
    "scuro": "dark",
    "chiaro": "light",
    "Segue il tema del dispositivo: {theme}": "Follows your device theme: {theme}",
    "Tema {theme}": "{theme} theme",
    "FACCIAMO SPAZIO": "LET’S MAKE ROOM",
    "Ogni file, al suo posto": "Every file in its place",
    "Ogni file, al suo posto.": "Every file in its place.",
    "Dal disordine a una cartella che respira. Decidi tu cosa cambia.": "From clutter to a little breathing room. You decide what changes.",
    "Da dove cominciamo?": "Where shall we start?",
    "Scegli la cartella da mettere in ordine.": "Choose the folder you want to organize.",
    "Cartella di partenza": "Starting folder",
    "Incolla un percorso oppure scegli una cartella": "Paste a path or choose a folder",
    "Scegli cartella": "Choose folder",
    "Un punto di partenza:": "A place to start:",
    "Download": "Downloads",
    "Prova con file di esempio": "Try sample files",
    "Il tuo modo di fare ordine": "Your way to organize",
    "Poche regole, tutte sotto il tuo controllo.": "A few simple rules. All under your control.",
    "Raggruppa i file": "Group files",
    "Per tipo di file": "By file type",
    "Per anno e mese": "By year and month",
    "Per tipo, poi anno e mese": "By type, then year and month",
    "Non spostare, rinomina soltanto": "Keep in place, rename only",
    "Immagini, Documenti, Video… ognuno a casa sua.": "Images, documents, videos… each in its own place.",
    "Rinomina i file": "Rename files",
    "Mantieni i nomi originali": "Keep original names",
    "Pulisci e uniforma i nomi": "Clean up and standardize names",
    "Usa un nome e un numero": "Use a name and a number",
    "I nomi restano esattamente come sono.": "Names stay exactly as they are.",
    "Quanto in profondità?": "How deep should we go?",
    "Includi sottocartelle": "Include subfolders",
    "Disattivato: solo i file nella cartella scelta.": "Off: only files in the selected folder.",
    "Nome di base": "Base name",
    "Per esempio: vacanza-001.jpg, vacanza-002.jpg": "For example: holiday-001.jpg, holiday-002.jpg",
    "Quali file includiamo?": "Which files should we include?",
    "Immagini": "Images",
    "Documenti": "Documents",
    "Archivi": "Archives",
    "Audio": "Audio",
    "Video": "Video",
    "Codice": "Code",
    "Altro": "Other",
    "Prima guardi l’anteprima. Poi decidi.": "Preview first. Then decide.",
    "Genera anteprima": "Generate preview",
    "Un’occhiata prima di cominciare": "A look before you begin",
    "Qui vedrai ogni cambiamento, prima che succeda.": "See every change here, before it happens.",
    "ANTEPRIMA": "PREVIEW",
    "Il bello dell’ordine inizia qui.": "A little order starts here.",
    "Scegli una cartella e genera l’anteprima.": "Choose a folder and generate a preview.",
    "Nessun file viene spostato in questo passaggio.": "No files are moved at this stage.",
    "Fai un giro con i file di esempio": "Take a tour with sample files",
    "Riepilogo anteprima": "Preview summary",
    "Hai cambiato cartella o regole. Genera una nuova anteprima per continuare.": "You changed the folder or rules. Generate a new preview to continue.",
    "Cerca un file…": "Search for a file…",
    "Cerca nell’anteprima": "Search the preview",
    "Filtra per stato": "Filter by status",
    "Tutti i file": "All files",
    "Da riordinare": "Ready to organize",
    "Già in ordine": "Already organized",
    "Esclusi": "Excluded",
    "Escluso": "Excluded",
    "Seleziona tutti": "Select all",
    "Seleziona tutti i file visibili pronti": "Select all visible files ready to organize",
    "FILE ATTUALE": "CURRENT FILE",
    "NUOVA DESTINAZIONE": "NEW DESTINATION",
    "TIPO": "TYPE",
    "DIMENSIONE": "SIZE",
    "STATO": "STATUS",
    "Nessun file corrisponde a questa ricerca.": "No files match your search.",
    "0 file selezionati": "0 files selected",
    "Potrai annullare dalla Cronologia.": "You can undo changes from History.",
    "Riordina i file": "Organize files",
    "Fatto per fare spazio alle cose che contano.": "Made to make room for the things that matter.",
    "Un po’ meno caos": "A little less chaos",
    "I CAMBIAMENTI, IN CHIARO": "EVERY CHANGE, IN PLAIN SIGHT",
    "La tua cronologia": "Your history",
    "Tieni traccia dei cambiamenti e, se vuoi, torna indietro.": "Keep track of changes and go back whenever you need to.",
    "Aggiorna": "Refresh",
    "Annulla prima le operazioni più recenti. Per proteggere i tuoi file, il ripristino si ferma se trova un file modificato o una destinazione già occupata.": "Undo the most recent operations first. To protect your files, restoring stops if a file has changed or a destination is already occupied.",
    "Una pagina ancora da scrivere.": "A fresh page, ready for you.",
    "I tuoi riordini appariranno qui.": "Your organizing operations will appear here.",
    "Con la possibilità di tornare sui tuoi passi.": "With the option to retrace your steps.",
    "Cominciamo": "Let’s begin",
    "SEMPLICE, COME DOVREBBE ESSERE": "SIMPLE, AS IT SHOULD BE",
    "Meno caos, in tre passi": "Less chaos, in three steps",
    "Uno strumento piccolo, con rispetto per i tuoi file.": "A small tool that treats your files with care.",
    "Scegli il punto di partenza": "Choose a starting point",
    "Una cartella di foto, documenti o il tuo Download. Puoi scegliere dal computer oppure incollare il percorso completo.": "A folder of photos, documents, or your Downloads. Browse your computer or paste the full path.",
    "Decidi come riordinare": "Decide how to organize",
    "Dividi per tipo, per mese o per entrambi. Mantieni i nomi, rendili più uniformi o usa una sequenza numerata.": "Group by type, by month, or both. Keep names, make them more consistent, or use a numbered sequence.",
    "Controlla e conferma": "Review and confirm",
    "L’anteprima ti mostra i percorsi finali. Seleziona i file che vuoi cambiare e applica. La Cronologia ti permette di annullare.": "The preview shows the final paths. Select the files you want to change and apply. History lets you undo.",
    "Le cose utili da sapere": "A few things worth knowing",
    "Dove vengono messi i file?": "Where do the files go?",
    "Le nuove cartelle vengono create dentro la cartella che scegli. Nell’anteprima trovi il percorso preciso di ogni file. Se scegli “Non spostare”, cambiano soltanto i nomi.": "New folders are created inside your selected folder. The preview shows each file’s exact path. Choose “Keep in place” to change names only.",
    "La lingua cambia i nomi delle cartelle?": "Does the language change folder names?",
    "No. La lingua riguarda l’interfaccia. Le cartelle delle categorie mantengono i nomi italiani (Immagini, Documenti, Archivi, Audio, Video, Codice, Altro), così i percorsi rimangono coerenti quando cambi lingua.": "No. Language affects the interface. Category folders keep their Italian names (Immagini, Documenti, Archivi, Audio, Video, Codice, Altro), so paths stay consistent when you switch languages.",
    "Che data viene usata per i mesi?": "Which date is used for months?",
    "La data di ultima modifica del file. Per le foto può essere diversa dalla data di scatto. Controlla sempre l’anteprima.": "The file’s last modified date. For photos, it may differ from the date taken. Always review the preview.",
    "E se due file hanno lo stesso nome?": "What if two files have the same name?",
    "I file esistenti non vengono sovrascritti. Quando necessario, viene aggiunto un numero al nome: vedrai il risultato nell’anteprima.": "Existing files are never overwritten. A number is added to the name when needed. You will see the result in the preview.",
    "Che cosa succede ai file esclusi?": "What happens to excluded files?",
    "Restano dove sono. I file nascosti, i collegamenti simbolici e i file non inclusi nelle categorie scelte vengono ignorati. Le cartelle protette non vengono esplorate.": "They stay where they are. Hidden files, symbolic links, and files outside the selected categories are ignored. Protected folders are not explored.",
    "Posso annullare dopo aver chiuso l’app?": "Can I undo after closing the app?",
    "Sì, la cronologia viene salvata sul computer. Il ripristino verifica che i file siano ancora al loro posto e non siano cambiati. Se li modifichi o sposti con un’altra app, potrebbe non essere possibile annullare automaticamente.": "Yes. History is saved on your computer. Restoring checks that files are still in place and have not changed. If you edit or move them with another app, automatic undo may no longer be possible.",
    "I miei file vengono caricati online?": "Are my files uploaded online?",
    "No. Il programma lavora sul tuo computer, senza account, servizi cloud o API a pagamento. I file di esempio sono una cartella separata, creata solo per provare l’app.": "No. The app runs on your computer without accounts, cloud services, or paid APIs. Sample files are created in a separate folder just for trying the app.",
    "Vuoi prendere confidenza?": "Want to get a feel for it?",
    "Ci ripenso": "Go back",
    "Conferma": "Confirm",
    "Scegli la tua cartella": "Choose your folder",
    "Apri una sottocartella oppure usa quella corrente. In questo passaggio non cambia nessun file.": "Open a subfolder or use the current one. No files change at this stage.",
    "Cartelle personali": "Personal folders",
    "Home": "Home",
    "Scrivania": "Desktop",
    "Percorso della cartella": "Folder path",
    "Apri la cartella superiore": "Open the parent folder",
    "↑ Su": "↑ Up",
    "Incolla un percorso completo": "Paste a full path",
    "Apri": "Open",
    "Puoi anche incollare un percorso e premere Apri.": "You can also paste a path and press Open.",
    "Cartella corrente": "Current folder",
    "Sottocartelle": "Subfolders",
    "Annulla": "Cancel",
    "Usa questa cartella": "Use this folder",
    "Un momento…": "One moment…",
    "Stiamo lavorando sul tuo computer.": "Working on your computer.",
    "Completato": "Completed",
    "Annullato": "Undone",
    "Non completato": "Not completed",
    "Parziale": "Partial",
    "Ripristino parziale": "Partially restored",
    "In corso": "In progress",
    "Ripristino in corso": "Restoring",
    "Ripristinato": "Restored",
    "Interrotto": "Interrupted",
    "Chiudi notifica": "Dismiss notification",
    "La connessione locale non è pronta. Ricarica la pagina e riprova.": "The local connection is not ready. Reload the page and try again.",
    "Non riesco a raggiungere l’app locale. Verifica che il programma sia ancora aperto, poi riprova.": "Cannot reach the local app. Make sure it is still running, then try again.",
    "Il programma ha restituito una risposta inattesa. Riprova oppure riavvia l’app.": "The app returned an unexpected response. Try again or restart it.",
    "Non è stato possibile completare questa operazione.": "This operation could not be completed.",
    "Si è verificato un errore.": "An error occurred.",
    "Usa la data di ultima modifica del file.": "Uses the file’s last modified date.",
    "Una cartella per tipo, poi una per anno e mese.": "A folder for each type, then one for each year and month.",
    "I file restano nella loro cartella attuale.": "Files stay in their current folder.",
    "Nomi più semplici, senza spazi o caratteri superflui.": "Simpler names, without spaces or unnecessary characters.",
    "Un nome comune, seguito da un numero progressivo.": "A shared name followed by a sequential number.",
    "Attivato: includiamo anche i file nelle sottocartelle consentite.": "On: includes files in permitted subfolders.",
    "Leggiamo le sottocartelle…": "Reading subfolders…",
    "Questa cartella non può essere riordinata. Scegli una sottocartella personale.": "This folder cannot be organized. Choose a personal subfolder.",
    "Nessuna sottocartella visibile. Puoi usare la cartella corrente se selezionabile.": "No visible subfolders. You can use the current folder if it is selectable.",
    "Incolla un altro percorso e premi Apri, oppure scegli una scorciatoia.": "Paste another path and press Open, or choose a shortcut.",
    "Questa scorciatoia non è disponibile. Incolla il percorso della cartella e premi Apri.": "This shortcut is unavailable. Paste the folder path and press Open.",
    "Prepariamo un piccolo caos da sistemare…": "Preparing a little chaos to organize…",
    "Ecco i file di esempio: puoi provare il riordino e poi annullarlo.": "Here are the sample files. Try organizing them, then undo the changes.",
    "Scegli una cartella oppure incolla il suo percorso.": "Choose a folder or paste its path.",
    "Scegli almeno una categoria di file da includere.": "Choose at least one file category to include.",
    "Leggiamo la cartella e prepariamo l’anteprima…": "Reading the folder and preparing your preview…",
    "Dimensione totale": "Total size",
    "Questa cartella non contiene file da analizzare con le opzioni scelte.": "This folder has no files to analyze with the selected options.",
    "Operazione completata ": "Operation completed ",
    "Genera una nuova anteprima ": "Generate a new preview ",
    "Deseleziona tutti": "Deselect all",
    "Un po’ di caos in meno. Fatto!": "A little less chaos. Done!",
    "Controlla il risultato dell’operazione.": "Review the operation result.",
    "Vai alla Cronologia →": "Go to History →",
    "Mettiamo ogni file al suo posto…": "Putting every file in its place…",
    "APPLICATA": "APPLIED",
    "DA VERIFICARE": "REVIEW NEEDED",
    "Questa anteprima è stata applicata. Generane una nuova per altri cambiamenti.": "This preview has been applied. Generate a new one to make more changes.",
    "Controlla l’esito nella Cronologia e genera una nuova anteprima per continuare.": "Check the result in History and generate a new preview to continue.",
    "Fatto! I file sono al loro posto.": "Done! Your files are in place.",
    "Operazione terminata: controlla i dettagli nella Cronologia.": "Operation finished. Check the details in History.",
    "Torniamo al punto di partenza?": "Back to where we started?",
    "Sì, annulla il riordino": "Yes, undo these changes",
    "Ripristiniamo i percorsi originali…": "Restoring the original paths…",
    "Dopo il ripristino, genera una nuova anteprima per continuare.": "After restoring, generate a new preview to continue.",
    "Riordino annullato. I file sono tornati al loro posto originale.": "Changes undone. Your files are back in their original places.",
    "Controlla lo stato del ripristino nella Cronologia.": "Check the restore status in History.",
    "Recuperiamo i dettagli del riordino…": "Loading the operation details…",
    "spostato": "moved",
    "spostamento da completare": "move needs completion",
    "non spostato": "not moved",
    "ripristinato": "restored",
    "spostamento in corso": "moving",
    "ripristino in corso": "restoring",
    "ripristino da completare": "restore needs completion",
    "conflitto da verificare": "conflict to review",
    "Dettagli del riordino": "Operation details",
    "Chiudi": "Close",
    "Cartella": "Folder",
    "Dettagli": "Details",
    "↶  Annulla riordino": "↶  Undo changes",
    "Aggiorniamo la cronologia…": "Refreshing history…",
    "{count} sottocartella disponibile": "{count} subfolder available",
    "{count} sottocartelle disponibili": "{count} subfolders available",
    "Apri la cartella {name}": "Open folder {name}",
    "{count} file analizzati · {root}": "{count} files analyzed · {root}",
    "Seleziona {name}": "Select {name}",
    "{count} file selezionato": "{count} file selected",
    "{count} file selezionati": "{count} files selected",
    "Riordina {count}file ": "Organize {count}files ",
    "{count} file riordinati. Puoi annullare dalla Cronologia.": "{count} files organized. You can undo changes from History.",
    "Stato: {state}. Trovi i dettagli nella Cronologia.": "Status: {state}. Find the details in History.",
    "Riordiniamo {count} file?": "Organize {count} files?",
    "Verranno applicati i cambiamenti mostrati nell’anteprima, solo ai file selezionati.\n\nCartella: {root}\n\nPotrai annullare dalla Cronologia, finché i file non vengono modificati o spostati di nuovo.": "The changes shown in the preview will be applied to the selected files only.\n\nFolder: {root}\n\nYou can undo from History, as long as the files have not been edited or moved again.",
    "\n… e altri {count} file.": "\n… and {count} more files.",
    "Sì, riordina {count} file": "Yes, organize {count} files",
    "Annullerai il riordino del {date}. I file verranno riportati ai percorsi e ai nomi originali.\n\nCartella: {root}\n\nIl programma controlla che i file non siano cambiati e non sovrascrive file esistenti.": "You will undo the operation from {date}. Files will return to their original paths and names.\n\nFolder: {root}\n\nThe app checks that files have not changed and never overwrites existing files.",
    "Cartella: {root}": "Folder: {root}",
    "Data: {date}": "Date: {date}",
    "Stato: {state}": "Status: {state}",
    "File: {count}": "Files: {count}",
    "Annullato: {date}": "Undone: {date}",
    "Operazione {id}": "Operation {id}",
    "{count} file · {name}": "{count} files · {name}"
};
  const singularTranslations = {
    '{count} file analizzati · {root}': '{count} file analyzed · {root}',
    'Riordina {count}file ': 'Organize {count}file ',
    '{count} file riordinati. Puoi annullare dalla Cronologia.': '{count} file organized. You can undo changes from History.',
    'Riordiniamo {count} file?': 'Organize {count} file?',
    '\n… e altri {count} file.': '\n… and {count} more file.',
    'Sì, riordina {count} file': 'Yes, organize {count} file',
    '{count} file · {name}': '{count} file · {name}'
  };
  let language = 'it';
  try {
    if (window.localStorage.getItem(storageKey) === 'en') language = 'en';
  } catch {
    // The interface remains usable when browser storage is unavailable.
  }
  document.documentElement.lang = language;
  let staticNodes = null;
  let staticAttributes = null;
  const renderedMessages = new Map();

  function interpolate(source, params) {
    return source.replace(/\{(\w+)\}/g, (match, key) => Object.hasOwn(params, key) ? String(params[key]) : match);
  }

  function t(source, params = {}) {
    const translated = Number(params.count) === 1 ? (singularTranslations[source] ?? translations[source]) : translations[source];
    const message = interpolate(language === 'en' ? (translated ?? source) : source, params);
    if (!Object.keys(params).length) renderedMessages.set(message, { source, params });
    return message;
  }

  function translateServerMessage(message) {
    return window.CaosMessages?.translate(String(message || ''), language) ?? String(message || '');
  }

  function retranslate(message) {
    const previous = renderedMessages.get(message);
    return previous ? t(previous.source, previous.params) : translateServerMessage(message);
  }

  function captureStatic() {
    staticNodes = [];
    staticAttributes = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const source = node.nodeValue.trim();
      if (Object.hasOwn(translations, source)) {
        const leading = node.nodeValue.match(/^\s*/)[0];
        const trailing = node.nodeValue.match(/\s*$/)[0];
        staticNodes.push({ node, source, leading, trailing });
      }
    }
    document.querySelectorAll('[aria-label], [placeholder], meta[name="description"]').forEach((node) => {
      ['aria-label', 'placeholder', 'content'].forEach((name) => {
        const source = node.getAttribute(name);
        if (source && Object.hasOwn(translations, source)) staticAttributes.push({ node, name, source });
      });
    });
  }

  function applyStatic() {
    if (!staticNodes) captureStatic();
    for (const { node, source, leading, trailing } of staticNodes) {
      if (node.isConnected) node.nodeValue = leading + t(source) + trailing;
    }
    for (const { node, name, source } of staticAttributes) node.setAttribute(name, t(source));
  }

  function applyLanguage(next, persist) {
    language = next === 'en' ? 'en' : 'it';
    document.documentElement.lang = language;
    if (persist) {
      try { window.localStorage.setItem(storageKey, language); } catch { /* Keep the in-memory choice. */ }
    }
    const control = document.getElementById('language-preference');
    if (control) control.value = language;
    applyStatic();
    window.dispatchEvent(new CustomEvent('caos:languagechange', { detail: { language } }));
  }

  window.CaosI18n = Object.freeze({
    t, retranslate, translateServerMessage, applyStatic,
    get language() { return language; },
    get locale() { return language === 'en' ? 'en-GB' : 'it-IT'; },
    setLanguage(next) { applyLanguage(next, true); }
  });

  document.addEventListener('DOMContentLoaded', () => {
    if (!staticNodes) applyStatic();
    const control = document.getElementById('language-preference');
    control.value = language;
    control.addEventListener('change', () => applyLanguage(control.value, true));
  }, { once: true });

  window.addEventListener('storage', (event) => {
    if (event.key !== storageKey && event.key !== null) return;
    try { if (event.storageArea !== window.localStorage) return; } catch { return; }
    applyLanguage(event.newValue, false);
  });
})();
