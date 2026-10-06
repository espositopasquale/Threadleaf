export type Language = "it" | "en";
const messages = {
  it: {
    deleteConversation: "Elimina conversazione", deleteConversationConfirm: 'Eliminare definitivamente la conversazione "{title}"?', deleteConversationError: "Impossibile eliminare la conversazione. Riprova.",
    chatModel: "Modello", defaultModel: "Modello predefinito", modelError: "Modelli non disponibili", loadingThread: "Districando il filo…", loadingWeave: "Intrecciando i fili…", loadingFollow: "Seguendo il filo…", loadingStitch: "Cucendo insieme le idee…",
    sourcesLabel: "Fonti", sourceCount: "Fonti: {count}",
    searchConversations: "Cerca nelle conversazioni…", searchConversationsLabel: "Cerca nei titoli e nei messaggi delle conversazioni", historyNoMatches: "Nessuna conversazione corrisponde alla ricerca.",
    conversationHistory: "Storico conversazioni", showHistory: "Mostra storico conversazioni", hideHistory: "Nascondi storico conversazioni", historyEmpty: "Nessuna conversazione salvata.", historyError: "Impossibile caricare lo storico. Premi Aggiorna per riprovare.",
    newConversation: "Nuova conversazione", conversationLoadError: "Impossibile caricare la conversazione. Ricarica la pagina o avvia una nuova conversazione dalle impostazioni.",
    settings: "Impostazioni", addDocument: "Aggiungi documento", folder: "Cartella di destinazione (facoltativa)", folderPlaceholder: "es. Diritto/Civile", chooseFile: "Scegli un file PDF, TXT o MD", deleteDocument: "Elimina documento", deleteConfirm: 'Eliminare definitivamente "{source}" dal disco e dal database?',
    uploading: "Caricamento del file: {percent}%", saving: "Salvataggio del documento…", reading: "Lettura del documento…", indexing: "Indicizzazione: {done} di {total} frammenti", titles: "Generazione del titolo…", deleting: "Eliminazione del documento…", operationComplete: "Operazione completata.", operationFailed: "Operazione non riuscita. Se il file è stato salvato, puoi riprovare l'indicizzazione.", retryIndex: "Riprova indicizzazione", progressLabel: "Avanzamento operazione", uploadHelp: "PDF, TXT, MD · massimo 25 MB", too_large: "Il file supera il limite di 25 MB.", invalid_path: "Percorso o tipo di file non valido.", reserved_document: "Questo nome è riservato.", busy: "È già in corso un'operazione sui documenti.", already_exists: "Esiste già un documento con questo nome. Scegli un altro nome o cartella.", not_found: "Documento non trovato.", empty_upload: "Il file è vuoto.", operationError: "Impossibile completare la richiesta.",
    pageTitle: "ThreadLeaf | Il tuo assistente per i documenti", tagline: "In conversazione con i tuoi documenti.",
    welcome: "In conversazione con i tuoi documenti.", welcomeHelp: "Fai una domanda, esplora un argomento o trova i dettagli che cerchi.",
    language: "Lingua dell'interfaccia", documents: "Documenti", refresh: "Aggiorna", selectAll: "Seleziona tutti", selectNone: "Deseleziona tutti",
    showDocuments: "Mostra documenti", hideDocuments: "Nascondi documenti", search: "Cerca un documento…", searchLabel: "Cerca tra i documenti indicizzati",
    indexedDocuments: "Documenti indicizzati", conversation: "Conversazione", message: "Messaggio", messagePlaceholder: "Chiedi informazioni sui tuoi documenti…", send: "Invia",
    hint: "L'IA può commettere errori. Verifica i dettagli importanti nei tuoi documenti.",
    selected: "{selected} di {total} documenti selezionati", chunks: "{count} frammenti", loading: "Caricamento documenti…",
    selectionHelp: "La selezione si applica alle prossime domande.", selectRequired: "Seleziona almeno un documento per usare la chat.",
    empty: "Il database non contiene documenti indicizzati.", noMatches: "Nessun documento corrisponde alla ricerca.",
    loadError: "Impossibile caricare i documenti. Premi Aggiorna per riprovare.", titleError: "Alcuni titoli non sono disponibili. Puoi comunque usare i documenti.",
    networkError: "Errore: server non raggiungibile.", requestError: "Errore: richiesta non riuscita (HTTP {status}).",
    staleSelection: "Errore: alcuni documenti non sono più nel database. Aggiorna l'elenco.",
  },
  en: {
    deleteConversation: "Delete conversation", deleteConversationConfirm: 'Permanently delete the conversation "{title}"?', deleteConversationError: "Unable to delete the conversation. Try again.",
    chatModel: "Model", defaultModel: "Default model", modelError: "Models unavailable", loadingThread: "Untangling the thread…", loadingWeave: "Weaving the threads…", loadingFollow: "Following the thread…", loadingStitch: "Stitching ideas together…",
    sourcesLabel: "Sources", sourceCount: "Sources: {count}",
    searchConversations: "Search conversations…", searchConversationsLabel: "Search conversation titles and messages", historyNoMatches: "No conversations match your search.",
    conversationHistory: "Conversation history", showHistory: "Show conversation history", hideHistory: "Hide conversation history", historyEmpty: "No saved conversations.", historyError: "Unable to load history. Click Refresh to retry.",
    newConversation: "New conversation", conversationLoadError: "Unable to load the conversation. Reload the page or start a new conversation in settings.",
    settings: "Settings", addDocument: "Add document", folder: "Destination folder (optional)", folderPlaceholder: "e.g. Law/Civil", chooseFile: "Choose a PDF, TXT or MD file", deleteDocument: "Delete document", deleteConfirm: 'Permanently delete "{source}" from disk and database?',
    uploading: "Uploading file: {percent}%", saving: "Saving document…", reading: "Reading document…", indexing: "Indexing: {done} of {total} chunks", titles: "Generating title…", deleting: "Deleting document…", operationComplete: "Operation completed.", operationFailed: "Operation failed. If the file was saved, you can retry indexing.", retryIndex: "Retry indexing", progressLabel: "Operation progress", uploadHelp: "PDF, TXT, MD · maximum 25 MB", too_large: "The file exceeds the 25 MB limit.", invalid_path: "Invalid path or file type.", reserved_document: "This filename is reserved.", busy: "A document operation is already running.", already_exists: "A document with this name already exists. Choose another name or folder.", not_found: "Document not found.", empty_upload: "The file is empty.", operationError: "Unable to complete the request.",
    pageTitle: "ThreadLeaf | Your document assistant", tagline: "Your documents, in conversation.",
    welcome: "Your documents, in conversation.", welcomeHelp: "Ask a question, explore a topic, or find the details you need.",
    language: "Interface language", documents: "Documents", refresh: "Refresh", selectAll: "Select all", selectNone: "Deselect all",
    showDocuments: "Show documents", hideDocuments: "Hide documents", search: "Search documents…", searchLabel: "Search indexed documents",
    indexedDocuments: "Indexed documents", conversation: "Conversation", message: "Message", messagePlaceholder: "Ask about your documents…", send: "Send",
    hint: "AI can make mistakes. Verify important details against your documents.",
    selected: "{selected} of {total} documents selected", chunks: "{count} chunks", loading: "Loading documents…",
    selectionHelp: "Your selection applies to future questions.", selectRequired: "Select at least one document to use the chat.",
    empty: "The database contains no indexed documents.", noMatches: "No documents match your search.",
    loadError: "Unable to load documents. Click Refresh to try again.", titleError: "Some titles are unavailable. You can still use the documents.",
    networkError: "Error: server unreachable.", requestError: "Error: request failed (HTTP {status}).",
    staleSelection: "Error: some documents are no longer in the database. Refresh the list.",
  },
};
export type MessageKey = keyof typeof messages.en;
const storageKey = "ThreadLeaf-interface-language";
let language: Language = navigator.language.toLowerCase().startsWith("it") ? "it" : "en";
try {
  const saved = localStorage.getItem(storageKey);
  if (saved === "it" || saved === "en") language = saved;
} catch { /* Use the browser language. */ }
export function getLanguage(): Language { return language; }
export function setLanguage(value: Language): void {
  language = value;
  try { localStorage.setItem(storageKey, value); } catch { /* Storage may be unavailable. */ }
}
export function t(key: MessageKey, values: Record<string, string | number> = {}): string {
  return messages[language][key].replace(/\{(\w+)\}/g, (match, name: string) => String(values[name] ?? match));
}
