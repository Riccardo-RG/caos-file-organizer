/* Translate API messages at display time; never translate filenames or paths. */
(() => {
  'use strict';

  const english = new Map([
    ["Questo sistema non offre lo spostamento atomico senza sovrascrittura richiesto dall'app.", 'This system does not provide the atomic, no-overwrite file moves required by this app.'],
    ['Questo filesystem non supporta lo spostamento sicuro senza sovrascrittura. Nessun file è stato sostituito.', 'This filesystem does not support safe, no-overwrite file moves. No files were replaced.'],
    ['Percorso del file non valido.', 'Invalid file path.'],
    ['Il percorso esce dalla cartella selezionata.', 'The path is outside the selected folder.'],
    ['Il prefisso deve essere un testo.', 'The prefix must be text.'],
    ['Scegli un prefisso da 1 a 100 byte, senza barre.', 'Choose a prefix between 1 and 100 bytes long, without slashes.'],
    ['Il prefisso non può essere nascosto o contenere caratteri di controllo.', 'The prefix cannot start with a dot or contain control characters.'],
    ['Le opzioni non sono valide.', 'The options are invalid.'],
    ['Le opzioni di scansione non sono valide.', 'The scanning options are invalid.'],
    ['La modalità di organizzazione o rinomina non è valida.', 'The organization or renaming mode is invalid.'],
    ['La selezione delle categorie non è valida.', 'The category selection is invalid.'],
    ['Identificativo non valido.', 'Invalid identifier.'],
    ['Anteprima o operazione non trovata. Crea una nuova anteprima.', 'Preview or operation not found. Create a new preview.'],
    ['Il registro non è leggibile. Nessun file è stato modificato.', 'The journal cannot be read. No files were changed.'],
    ["Il registro dell'operazione non è valido.", 'The operation journal is invalid.'],
    ["Il registro dell'operazione è incompleto o danneggiato. Nessun file è stato modificato.", 'The operation journal is incomplete or damaged. No files were changed.'],
    ['Scegli una cartella valida.', 'Choose a valid folder.'],
    ['Inserisci il percorso completo della cartella.', 'Enter the full path to the folder.'],
    ['La cartella non esiste o non è accessibile.', 'The folder does not exist or cannot be accessed.'],
    ['Seleziona la cartella reale, senza collegamenti simbolici nel percorso.', 'Select the actual folder, without symbolic links in its path.'],
    ['Le librerie Foto e i pacchetti applicazione non possono essere riordinati. Scegli una cartella di file o immagini esportate.', 'Photo libraries and application bundles cannot be organized. Choose a folder of files or exported images.'],
    ['Le cartelle di sistema non possono essere organizzate. Seleziona Download, Foto o Documenti.', 'System folders cannot be organized. Select Downloads, Pictures, or Documents.'],
    ["La cartella dei registri dell'app non può essere organizzata.", "The app's journal folder cannot be organized."],
    ['Il percorso deve indicare una cartella accessibile.', 'The path must point to an accessible folder.'],
    ['La cartella è stata sostituita da un collegamento. Operazione annullata.', 'The folder was replaced with a symbolic link. Operation cancelled.'],
    ['La cartella originale non è più disponibile.', 'The original folder is no longer available.'],
    ['La cartella originale è stata sostituita. Crea una nuova anteprima.', 'The original folder was replaced. Create a new preview.'],
    ["Una cartella è cambiata durante la scansione. Ripeti l'anteprima.", 'A folder changed during the scan. Create a new preview.'],
    ['Questa cartella supera 100.000 file. Seleziona una sottocartella.', 'This folder contains more than 100,000 files. Select a subfolder.'],
    ['Nome di cartella in conflitto (maiuscole/minuscole).', 'Folder name conflict (letter case).'],
    ['Il nome di destinazione è troppo lungo.', 'The destination filename is too long.'],
    ['Categoria esclusa.', 'Category excluded.'],
    ['Download incompleto o file temporaneo.', 'Incomplete download or temporary file.'],
    ['File su un filesystem differente.', 'File is on a different filesystem.'],
    ['Il file è cambiato durante la scansione.', 'The file changed during the scan.'],
    ['Il filesystem non permette uno spostamento sicuro fra questi percorsi.', 'The filesystem does not support a safe move between these paths.'],
    ['Questa anteprima è già stata utilizzata. Crea una nuova anteprima.', 'This preview has already been used. Create a new preview.'],
    ["La selezione contiene file non disponibili nell'anteprima.", 'The selection contains files that are unavailable in the preview.'],
    ['Seleziona almeno un file da sistemare.', 'Select at least one file to organize.'],
    ['Entrambi i percorsi esistono. Nessun file è stato eliminato; verifica manualmente i collegamenti.', 'Both paths exist. No files were deleted; check the links manually.'],
    ["I percorsi sono cambiati durante l'operazione. Controlla i file manualmente.", 'The paths changed during the operation. Check the files manually.'],
    ['Questa operazione è già stata annullata.', 'This operation has already been undone.'],
    ['Questa operazione non contiene modifiche annullabili.', 'This operation has no changes that can be undone.'],
    ["L'app è stata interrotta. I progressi sono conservati nel registro; puoi annullare le modifiche sicure.", 'The app was interrupted. Progress has been saved in the journal; changes that are safe to restore can be undone.'],
    ["Indirizzo non autorizzato. Apri l'app dal suo indirizzo locale.", 'Unauthorized address. Open the app using its local address.'],
    ["Richiesta da un'altra pagina non consentita.", 'Requests from another page are not allowed.'],
    ['Sessione non valida. Ricarica la pagina e riprova.', 'Invalid session. Reload the page and try again.'],
    ["Non hai accesso a questa cartella. Scegline un'altra o verifica i permessi di macOS.", 'You do not have access to this folder. Choose another folder or check your macOS permissions.'],
    ["La cartella non è disponibile. Scegline un'altra.", 'The folder is unavailable. Choose another folder.'],
    ['Pagina non trovata.', 'Page not found.'],
    ['Risorsa non disponibile.', 'Resource unavailable.'],
    ['Formato della richiesta non supportato.', 'Unsupported request format.'],
    ['La richiesta deve contenere dati JSON.', 'The request must contain JSON data.'],
    ['Dimensione della richiesta non valida.', 'Invalid request size.'],
    ['Formato della richiesta non valido.', 'Invalid request format.'],
    ['Scegli prima una cartella.', 'Choose a folder first.'],
    ['Opzioni non valide.', 'Invalid options.'],
    ["Genera prima un'anteprima.", 'Create a preview first.'],
    ['Selezione dei file non valida.', 'Invalid file selection.'],
    ['Operazione non valida.', 'Invalid operation.'],
    ['Operazione non trovata.', 'Operation not found.'],
    ['Richiesta non valida.', 'Invalid request.'],
    ["Accesso alla cartella negato. Controlla i permessi del Terminale nelle impostazioni di macOS, oppure scegli un'altra cartella.", 'Folder access denied. Check Terminal permissions in macOS settings, or choose another folder.'],
    ['La cartella o un file non esiste più. Genera una nuova anteprima.', 'The folder or a file no longer exists. Create a new preview.'],
    ["L'operazione ha impiegato troppo tempo. Riprova.", 'The operation timed out. Try again.'],
    ['Errore inatteso. Controlla la cronologia prima di riprovare: eventuali spostamenti restano registrati.', 'Unexpected error. Check the history before trying again: any file moves remain recorded.'],
    ['Inserisci il percorso completo di una cartella.', 'Enter the full path to a folder.'],
    ['Il percorso non indica una cartella.', 'The path does not point to a folder.'],
    ['Caos può ascoltare soltanto su 127.0.0.1.', 'Caos can only listen on 127.0.0.1.'],
    ['La porta deve essere compresa tra 0 e 65535.', 'The port must be between 0 and 65535.'],
  ]);

  // Each template consumes a complete server message. Captured user paths stay
  // byte-for-byte intact, even when they contain punctuation or Italian text.
  const templates = [
    [/^Il file non è un file regolare: ([\s\S]*)$/, path => `This is not a regular file: ${path}`],
    [/^Il file è cambiato durante la lettura: ([\s\S]*)$/, path => `The file changed while it was being read: ${path}`],
    [/^Impossibile leggere la cartella ([\s\S]*)$/, detail => `Could not read folder ${detail}`],
    [/^Impossibile leggere la sottocartella ([\s\S]*)$/, detail => `Could not read subfolder ${detail}`],
    [/^Il file è cambiato o non è accessibile: ([\s\S]*)\. Crea una nuova anteprima\.$/, path => `The file changed or cannot be accessed: ${path}. Create a new preview.`],
    [/^Il file è stato modificato: ([\s\S]*)\. Crea una nuova anteprima\.$/, path => `The file was modified: ${path}. Create a new preview.`],
    [/^La destinazione è già occupata: ([\s\S]*)\. Crea una nuova anteprima\.$/, path => `The destination is already occupied: ${path}. Create a new preview.`],
    [/^La cartella di destinazione è cambiata o non è accessibile: ([\s\S]*)\.$/, path => `The destination folder changed or cannot be accessed: ${path}.`],
    [/^Il file è cambiato durante lo spostamento: ([\s\S]*)$/, path => `The file changed during the move: ${path}`],
    [/^Il file è stato modificato durante lo spostamento: ([\s\S]*)$/, path => `The file was modified during the move: ${path}`],
    [/^Il file richiede una verifica manuale: ([\s\S]*)$/, path => `This file needs a manual check: ${path}`],
    [/^Impossibile annullare: ([\s\S]*) è stato modificato, spostato o rimosso\.$/, path => `Cannot undo: ${path} was modified, moved, or removed.`],
  ];

  // These server-controlled prefixes wrap another error, never a naked path.
  const wrappers = [
    ['File non elaborabile: ', 'Cannot process file: '],
    ['Spostamento interrotto: ', 'Move interrupted: '],
    ['Annullamento interrotto: ', 'Undo interrupted: '],
    ["Impossibile completare l'operazione: ", 'Could not complete the operation: '],
  ];

  function toEnglish(message, depth = 0) {
    if (english.has(message)) return english.get(message);
    for (const [pattern, render] of templates) {
      const match = pattern.exec(message);
      if (match) return render(match[1]);
    }
    if (depth < 8) {
      for (const [source, target] of wrappers) {
        if (message.startsWith(source)) return target + toEnglish(message.slice(source.length), depth + 1);
      }
    }
    // Unknown messages and operating-system errors retain their original detail.
    return message;
  }

  window.CaosMessages = Object.freeze({
    translate(message, language) {
      return language === 'en' && typeof message === 'string' ? toEnglish(message) : message;
    },
  });
})();
