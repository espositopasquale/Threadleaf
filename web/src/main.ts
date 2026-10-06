declare const marked: { parse(text: string, options: { async: false }): string };
declare const DOMPurify: { sanitize(html: string, options: { USE_PROFILES: { html: true } }): string };
import { getLanguage, setLanguage, t, type MessageKey } from "./i18n.js";
import { createIcon, initializeIcons, setIcon } from "./icons.js";
initializeIcons();

interface ChatResponse {
  reply: string;
  sources: string[];
  answer_kind?: string;
}
interface ChatTurn { role: "user" | "assistant"; content: string; sources?: string[]; answer_kind?: string; }
const conversationKey = "ThreadLeaf-conversation-id";
let conversationId: string = crypto.randomUUID();
try {
  const saved = localStorage.getItem(conversationKey);
  if (saved && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(saved)) conversationId = saved;
  localStorage.setItem(conversationKey, conversationId);
} catch { /* Keep an in-memory conversation ID. */ }
let conversationReady = false;
let conversationLoading = true;

const log = document.getElementById("log") as HTMLDivElement;
const form = document.getElementById("form") as HTMLFormElement;
const input = document.getElementById("input") as HTMLInputElement;
const documentList = document.getElementById("document-list") as HTMLDivElement;
const documentStatus = document.getElementById("document-status") as HTMLParagraphElement;
const titleStatus = document.getElementById("title-status") as HTMLParagraphElement;
const documentSearch = document.getElementById("document-search") as HTMLInputElement;
const selectionCount = document.getElementById("selection-count") as HTMLParagraphElement;
const send = form.querySelector("button") as HTMLButtonElement;
const refresh = document.getElementById("refresh-documents") as HTMLButtonElement;
const selectAll = document.getElementById("select-all") as HTMLButtonElement;
const selectNone = document.getElementById("select-none") as HTMLButtonElement;
const documentsPanel = document.getElementById("documents-panel") as HTMLElement;
const toggleDocuments = document.getElementById("toggle-documents") as HTMLButtonElement;
const languageSelect = document.getElementById("interface-language") as HTMLSelectElement;
const settings = document.getElementById("settings-menu") as HTMLDetailsElement;
const newConversation = document.getElementById("new-conversation") as HTMLButtonElement;
const modelSelect = document.getElementById("chat-model") as HTMLSelectElement;
const modelStatus = document.getElementById("model-status")!;
let modelsReady = false;
const loadingPhrases: MessageKey[] = ["loadingThread", "loadingWeave", "loadingFollow", "loadingStitch"];
let loadingPhrase = 0;

async function loadModels(): Promise<void> {
  try {
    const response = await fetch("/models");
    if (!response.ok) throw new Error();
    const data: { models: string[]; default: string } = await response.json();
    for (const name of data.models) modelSelect.add(new Option(name, name));
    const defaultName = data.default.includes(":") ? data.default : `${data.default}:latest`;
    const defaultOption = modelSelect.options[0];
    defaultOption.removeAttribute("data-i18n");
    defaultOption.textContent = data.default;
    let saved: string | null = null;
    try { saved = localStorage.getItem("ThreadLeaf-chat-model"); } catch { /* Use the configured model. */ }
    modelSelect.value = saved && data.models.includes(saved) ? saved : data.models.includes(defaultName) ? defaultName : "";
    modelsReady = true;
  } catch {
    modelStatus.dataset.i18n = "modelError";
    modelStatus.textContent = t("modelError");
  }
  updateSelection();
}
modelSelect.addEventListener("change", () => {
  try { localStorage.setItem("ThreadLeaf-chat-model", modelSelect.value); } catch { /* Keep the selection in memory. */ }
});
const historyPanel = document.getElementById("history-panel") as HTMLElement;
const toggleHistory = document.getElementById("toggle-history") as HTMLButtonElement;
const historyList = document.getElementById("conversation-list") as HTMLDivElement;
const historyStatus = document.getElementById("history-status") as HTMLParagraphElement;
const historyNew = document.getElementById("history-new") as HTMLButtonElement;
const historyRefresh = document.getElementById("history-refresh") as HTMLButtonElement;
const historySearch = document.getElementById("history-search") as HTMLInputElement;
let historyRequest: AbortController | null = null;
let historySearchTimer: ReturnType<typeof setTimeout> | null = null;
interface ConversationSummary { thread_id: string; title: string; updated_at: string; }
let savedConversations: ConversationSummary[] = [];
let historyError = false;
let historyLoading = false;
let historyDeleting = false;
let historyDeleteError = false;
try { historyPanel.hidden = localStorage.getItem("ThreadLeaf-history-hidden") !== "false"; } catch { /* Start collapsed. */ }
const fileInput = document.getElementById("document-file") as HTMLInputElement;
const uploadFolder = document.getElementById("upload-folder") as HTMLInputElement;
const addDocument = document.getElementById("add-document") as HTMLButtonElement;
const operationPanel = document.getElementById("document-operation") as HTMLDivElement;
const operationStatus = document.getElementById("operation-status") as HTMLParagraphElement;
const operationProgress = document.getElementById("operation-progress") as HTMLProgressElement;
const retryIndex = document.getElementById("retry-index") as HTMLButtonElement;
interface DocumentOperation { id: string | null; state: string; stage: string; source?: string; operation?: string; done: number; total: number; }
let operation: DocumentOperation = { id: null, state: "idle", stage: "idle", done: 0, total: 0 };
let mutating = false;
let operationError: MessageKey | null = null;
let uploadPercent = 0;
let completionTimer: ReturnType<typeof setTimeout> | null = null;
const panelStorageKey = "ThreadLeaf-documents-panel-hidden";

function setPanelHidden(hidden: boolean): void {
  documentsPanel.hidden = hidden;
  toggleDocuments.setAttribute("aria-expanded", String(!hidden));
  toggleDocuments.setAttribute("aria-label", t(hidden ? "showDocuments" : "hideDocuments"));
  toggleDocuments.title = t(hidden ? "showDocuments" : "hideDocuments");
  const chevron = document.getElementById("rail-chevron")!;
  chevron.textContent = hidden ? "›" : "‹";
  setIcon(chevron, hidden ? "chevronRight" : "chevronLeft");
  try { localStorage.setItem(panelStorageKey, String(hidden)); } catch { /* Storage may be unavailable. */ }
}

let panelHidden = false;
try { panelHidden = localStorage.getItem(panelStorageKey) === "true"; } catch { /* Keep the panel visible. */ }
setPanelHidden(panelHidden);
toggleDocuments.addEventListener("click", () => { setPanelHidden(!documentsPanel.hidden); });
interface IndexedDocument { source: string; chunks: number; title?: string; title_generation_failed?: boolean; }
interface DocumentFolder { folders: Map<string, DocumentFolder>; documents: IndexedDocument[]; }
const folderOpen = new Map<string, boolean>();
let documents: IndexedDocument[] = [];
let selected = new Set<string>();
let ready = false;
let sending = false;
let initialized = false;
let loadFailed = false;
const storageKey = "ThreadLeaf-selected-documents";

function updateSelection(): void {
  selectionCount.textContent = t("selected", { selected: selected.size, total: documents.length });
  documentStatus.textContent = t(loadFailed ? "loadError" : !ready ? "loading" : !documents.length ? "empty" : selected.size ? "selectionHelp" : "selectRequired");
  titleStatus.textContent = documents.some(doc => doc.title_generation_failed) ? t("titleError") : "";
  send.disabled = !conversationReady || !ready || sending || mutating || historyDeleting || selected.size === 0;
  newConversation.disabled = sending || conversationLoading || historyDeleting;
  modelSelect.disabled = !modelsReady || sending || conversationLoading;
  historyNew.disabled = sending || conversationLoading || historyDeleting;
  historyList.querySelectorAll<HTMLButtonElement>("button").forEach(button => { button.disabled = sending || conversationLoading || mutating || historyDeleting; });
  selectAll.disabled = !ready || mutating || documents.length === 0;
  selectNone.disabled = !ready || mutating || selected.size === 0;
  refresh.disabled = mutating;
  addDocument.disabled = mutating || sending;
  fileInput.disabled = mutating || sending;
  uploadFolder.disabled = mutating || sending;
  if (initialized) {
    try { localStorage.setItem(storageKey, JSON.stringify([...selected])); } catch { /* Storage may be unavailable. */ }
  }
}

function renderDocuments(): void {
  documentList.replaceChildren();
  const search = documentSearch.value.trim().toLocaleLowerCase();
  const visible = documents.filter(doc => `${doc.source} ${doc.title ?? ""}`.toLocaleLowerCase().includes(search));
  const root: DocumentFolder = { folders: new Map(), documents: [] };
  for (const doc of visible) {
    const parts = doc.source.replace(/\\/g, "/").split("/");
    parts.pop();
    let folder = root;
    for (const part of parts) {
      if (!folder.folders.has(part)) folder.folders.set(part, { folders: new Map(), documents: [] });
      folder = folder.folders.get(part)!;
    }
    folder.documents.push(doc);
  }
  function renderFile(doc: IndexedDocument, container: HTMLElement): void {
    const row = document.createElement("div");
    row.className = "document-row";
    const label = document.createElement("label");
    label.className = "document-choice";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selected.has(doc.source);
    checkbox.disabled = !ready || mutating;
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selected.add(doc.source); else selected.delete(doc.source);
      updateSelection();
    });
    const text = document.createElement("span");
    const name = document.createElement("strong");
    const filename = doc.source.replace(/\\/g, "/").split("/").pop()!;
    name.textContent = doc.title ?? filename;
    name.title = doc.source;
    const info = document.createElement("small");
    info.textContent = `${filename} · ${t("chunks", { count: doc.chunks })}`;
    text.append(name, info);
    label.append(checkbox, text);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "delete-document";
    remove.appendChild(createIcon("trash"));
    remove.setAttribute("aria-label", `${t("deleteDocument")}: ${doc.title ?? filename}`);
    remove.title = t("deleteDocument");
    remove.disabled = mutating || sending;
    remove.addEventListener("click", () => {
      if (confirm(t("deleteConfirm", { source: doc.source }))) void requestOperation("/documents", "DELETE", doc.source);
    });
    row.append(label, remove);
    container.appendChild(row);
  }
  function renderFolder(folder: DocumentFolder, container: HTMLElement, path: string): void {
    for (const [name, child] of [...folder.folders].sort(([a], [b]) => a.localeCompare(b))) {
      const fullPath = path ? `${path}/${name}` : name;
      const details = document.createElement("details");
      details.className = "document-folder";
      details.open = Boolean(search) || (folderOpen.get(fullPath) ?? true);
      details.addEventListener("toggle", () => { if (!search) folderOpen.set(fullPath, details.open); });
      const summary = document.createElement("summary");
      summary.append(createIcon("folder"), document.createTextNode(` ${name}`));
      const body = document.createElement("div");
      body.className = "folder-contents";
      details.append(summary, body);
      renderFolder(child, body, fullPath);
      container.appendChild(details);
    }
    for (const doc of folder.documents.sort((a, b) => (a.title ?? a.source).localeCompare(b.title ?? b.source))) {
      renderFile(doc, container);
    }
  }
  renderFolder(root, documentList, "");
  if (ready && documents.length && !visible.length) documentList.textContent = t("noMatches");
}

async function loadDocuments(): Promise<void> {
  ready = false;
  loadFailed = false;
  refresh.disabled = true;
  send.disabled = true;
  selectAll.disabled = true;
  selectNone.disabled = true;
  documentStatus.textContent = t("loading");
  renderDocuments();
  try {
    const response = await fetch("/documents", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data: { documents: IndexedDocument[] } = await response.json();
    documents = data.documents.filter(doc => {
      const filename = doc.source.replace(/\\/g, "/").split("/").pop()?.toLowerCase();
      return filename !== "readme.txt" && filename !== "reeadme.txt";
    });
    let saved: string[] | null = initialized ? [...selected] : null;
    if (!initialized) {
      try {
        const value: unknown = JSON.parse(localStorage.getItem(storageKey) ?? "null");
        if (Array.isArray(value) && value.every(item => typeof item === "string")) saved = value;
      } catch { /* Use all documents when no valid preference exists. */ }
    }
    const available = new Set(documents.map(doc => doc.source));
    selected = new Set(saved === null ? available : saved.filter(source => available.has(source)));
    initialized = true;
    ready = true;
    refreshSourceTitles();
    updateSelection();
    renderDocuments();
  } catch {
    loadFailed = true;
    documentStatus.textContent = t("loadError");
  } finally {
    refresh.disabled = mutating;
  }
}

function applyLanguage(): void {
  document.documentElement.lang = getLanguage();
  document.title = t("pageTitle");
  languageSelect.value = getLanguage();
  renderHistory();
  for (const el of Array.from(document.querySelectorAll<HTMLElement>("[data-i18n]"))) {
    el.textContent = t(el.dataset.i18n as MessageKey, JSON.parse(el.dataset.i18nValues ?? "{}"));
  }
  for (const attribute of ["aria-label", "placeholder"]) {
    for (const el of Array.from(document.querySelectorAll<HTMLElement>(`[data-i18n-${attribute}]`))) {
      el.setAttribute(attribute, t(el.getAttribute(`data-i18n-${attribute}`) as MessageKey, JSON.parse(el.dataset.i18nValues ?? "{}")));
    }
  }
  log.dataset.emptyTitle = t("welcome");
  log.dataset.emptyDescription = t("welcomeHelp");
  setPanelHidden(documentsPanel.hidden);
  updateSelection();
  renderDocuments();
  renderOperation();
}

languageSelect.addEventListener("change", () => {
  setLanguage(languageSelect.value === "it" ? "it" : "en");
  applyLanguage();
});
applyLanguage();

documentSearch.addEventListener("input", renderDocuments);
refresh.addEventListener("click", () => { void loadDocuments(); });
selectAll.addEventListener("click", () => { selected = new Set(documents.map(doc => doc.source)); updateSelection(); renderDocuments(); });
selectNone.addEventListener("click", () => { selected.clear(); updateSelection(); renderDocuments(); });
void restoreConversation();
void loadHistory();
void resumeOperation();

function renderOperation(): void {
  if (operation.state !== "complete" || mutating || operationError) {
    if (completionTimer !== null) clearTimeout(completionTimer);
    completionTimer = null;
  } else if (completionTimer === null) {
    const completedId = operation.id;
    completionTimer = setTimeout(() => {
      completionTimer = null;
      if (operation.state === "complete" && operation.id === completedId && !mutating && !operationError) {
        operation = { id: null, state: "idle", stage: "idle", done: 0, total: 0 };
        renderOperation();
      }
    }, 3000);
  }
  operationPanel.hidden = operation.state === "idle" && !operationError;
  let key: MessageKey = "saving";
  if (operationError) key = operationError;
  else if (operation.state === "failed") key = "operationFailed";
  else if (operation.state === "complete") key = "operationComplete";
  else if (operation.stage === "uploading") key = "uploading";
  else if (operation.stage === "reading") key = "reading";
  else if (operation.stage === "indexing") key = "indexing";
  else if (operation.stage === "titles") key = "titles";
  else if (operation.stage === "deleting") key = "deleting";
  operationStatus.textContent = t(key, { done: operation.done, total: operation.total, percent: uploadPercent });
  operationProgress.max = 100;
  if (operation.state === "complete") operationProgress.value = 100;
  else if (operation.stage === "uploading") operationProgress.value = uploadPercent;
  else if (operation.total) operationProgress.value = Math.round(operation.done / operation.total * 100);
  else operationProgress.removeAttribute("value");
  operationProgress.hidden = Boolean(operationError) || operation.state === "failed";
  retryIndex.hidden = operation.state !== "failed" || operation.operation === "delete" || !operation.source;
  retryIndex.disabled = mutating;
}

function operationErrorKey(value: unknown): MessageKey {
  return typeof value === "string" && ["too_large", "invalid_path", "reserved_document", "busy", "already_exists", "not_found", "empty_upload"].includes(value)
    ? value as MessageKey : "operationError";
}

async function watchOperation(): Promise<void> {
  mutating = true;
  updateSelection(); renderDocuments(); renderOperation();
  while (operation.state === "running") {
    await new Promise(resolve => setTimeout(resolve, 800));
    try {
      const response = await fetch("/documents/operations", { cache: "no-store" });
      if (!response.ok) throw new Error();
      operation = await response.json();
      renderOperation();
    } catch {
      operationError = "networkError";
      renderOperation();
      // Keep mutations disabled while the server state is unknown; polling resumes automatically.
      continue;
    }
    operationError = null;
  }
  mutating = false;
  const uploaded = operation.operation === "upload" && operation.state === "complete" ? operation.source : undefined;
  await loadDocuments();
  if (uploaded) { selected.add(uploaded); updateSelection(); renderDocuments(); }
  renderOperation();
}

async function resumeOperation(): Promise<void> {
  try {
    const response = await fetch("/documents/operations", { cache: "no-store" });
    if (!response.ok) return;
    const current: DocumentOperation = await response.json();
    if (mutating) return;
    operation = current.state === "complete"
      ? { id: null, state: "idle", stage: "idle", done: 0, total: 0 }
      : current;
    renderOperation();
    if (operation.state === "running") await watchOperation();
  } catch { /* Document loading reports connectivity errors. */ }
}

async function requestOperation(url: string, method: string, source: string): Promise<void> {
  if (mutating || sending) return;
  mutating = true; operationError = null;
  updateSelection(); renderDocuments();
  try {
    const response = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ source }) });
    const data = await response.json();
    if (!response.ok) { operationError = operationErrorKey(data.detail); throw new Error(); }
    operation = data;
    await watchOperation();
  } catch {
    operationError ??= "networkError";
    mutating = false;
    updateSelection(); renderDocuments(); renderOperation();
  }
}

addDocument.addEventListener("click", () => { fileInput.click(); });
fileInput.addEventListener("change", async () => {
  const file = fileInput.files?.[0];
  if (!file || mutating || sending) return;
  if (file.size > 25 * 1024 * 1024) { operationError = "too_large"; renderOperation(); fileInput.value = ""; return; }
  const folder = uploadFolder.value.trim().replace(/\\/g, "/");
  const source = folder ? `${folder}/${file.name}` : file.name;
  mutating = true; operationError = null; uploadPercent = 0;
  operation = { id: null, state: "running", stage: "uploading", operation: "upload", source, done: 0, total: 0 };
  updateSelection(); renderDocuments(); renderOperation();
  try {
    operation = await new Promise<DocumentOperation>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/documents/upload?source=${encodeURIComponent(source)}`);
      xhr.upload.addEventListener("progress", event => {
        if (event.lengthComputable) uploadPercent = Math.round(event.loaded / event.total * 100);
        renderOperation();
      });
      xhr.addEventListener("load", () => {
        try {
          const data = JSON.parse(xhr.responseText);
          if (xhr.status < 200 || xhr.status >= 300) { operationError = operationErrorKey(data.detail); reject(new Error()); }
          else resolve(data);
        } catch { reject(new Error()); }
      });
      xhr.addEventListener("error", () => reject(new Error()));
      xhr.send(file);
    });
    await watchOperation();
  } catch {
    operation.state = "failed";
    operationError ??= "networkError";
    mutating = false; updateSelection(); renderDocuments(); renderOperation();
  } finally { fileInput.value = ""; }
});
retryIndex.addEventListener("click", () => { if (operation.source) void requestOperation("/documents/reindex", "POST", operation.source); });
document.addEventListener("click", event => { if (!settings.contains(event.target as Node)) settings.open = false; });
document.addEventListener("keydown", event => { if (event.key === "Escape") settings.open = false; });

function add(role: "user" | "bot", text: string): HTMLDivElement {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.textContent = text;
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

function renderAnswer(el: HTMLDivElement, data: ChatResponse): void {
  const content = document.createElement("div");
  content.className = "markdown";
  if (typeof marked !== "undefined" && typeof DOMPurify !== "undefined") {
    content.innerHTML = DOMPurify.sanitize(marked.parse(data.reply, { async: false }), { USE_PROFILES: { html: true } });
  } else { content.textContent = data.reply; content.classList.add("plain-text"); }
  el.replaceChildren(content);
  const sources = [...new Set(data.sources)];
  if (sources.length && data.answer_kind !== "casual" && data.answer_kind !== "insufficient") {
    const details = document.createElement("details");
    details.className = "source-details";
    const summary = document.createElement("summary");
    summary.dataset.i18nAriaLabel = "sourceCount";
    summary.dataset.i18nValues = JSON.stringify({ count: sources.length });
    summary.setAttribute("aria-label", t("sourceCount", { count: sources.length }));
    summary.append(createIcon("info"), document.createTextNode(String(sources.length)));
    const popup = document.createElement("div");
    popup.className = "source-popover";
    const heading = document.createElement("strong");
    heading.dataset.i18n = "sourcesLabel";
    heading.textContent = t("sourcesLabel");
    popup.appendChild(heading);
    for (const source of sources) {
      const row = document.createElement("div");
      row.className = "source-item";
      const title = document.createElement("span");
      title.dataset.sourceTitle = source;
      title.textContent = documents.find(doc => doc.source === source)?.title ?? source.split(/[\\/]/).pop() ?? source;
      const filename = document.createElement("small");
      filename.textContent = source;
      row.append(title, filename);
      popup.appendChild(row);
    }
    details.append(summary, popup);
    function openSources(): void {
      details.open = true;
      const bounds = summary.getBoundingClientRect();
      const viewport = log.getBoundingClientRect();
      const above = bounds.top - viewport.top - 12;
      const below = viewport.bottom - bounds.bottom - 12;
      details.dataset.below = String(below > above);
      popup.style.maxHeight = `${Math.min(220, Math.max(48, above, below))}px`;
    }
    summary.addEventListener("click", event => {
      event.preventDefault();
      const pinned = details.dataset.pinned !== "true";
      details.dataset.pinned = String(pinned);
      if (pinned) openSources(); else details.open = false;
    });
    details.addEventListener("mouseenter", openSources);
    details.addEventListener("mouseleave", () => {
      if (details.dataset.pinned !== "true" && !details.contains(document.activeElement)) details.open = false;
    });
    details.addEventListener("focusin", openSources);
    details.addEventListener("focusout", () => {
      setTimeout(() => { if (details.dataset.pinned !== "true" && !details.contains(document.activeElement)) details.open = false; }, 0);
    });
    el.appendChild(details);
  }
  log.scrollTop = log.scrollHeight;
}

function refreshSourceTitles(): void {
  log.querySelectorAll<HTMLElement>("[data-source-title]").forEach(title => {
    const source = title.dataset.sourceTitle!;
    title.textContent = documents.find(doc => doc.source === source)?.title ?? source.split(/[\\/]/).pop() ?? source;
  });
}

function closeSources(except?: Node): void {
  log.querySelectorAll<HTMLDetailsElement>(".source-details").forEach(details => {
    if (!except || !details.contains(except)) { details.open = false; details.dataset.pinned = "false"; }
  });
}
document.addEventListener("click", event => { closeSources(event.target as Node); });
document.addEventListener("keydown", event => { if (event.key === "Escape") closeSources(); });

function renderHistory(): void {
  setIcon(document.getElementById("history-chevron")!, historyPanel.hidden ? "chevronRight" : "chevronLeft");
  toggleHistory.setAttribute("aria-expanded", String(!historyPanel.hidden));
  toggleHistory.dataset.i18nAriaLabel = historyPanel.hidden ? "showHistory" : "hideHistory";
  toggleHistory.setAttribute("aria-label", t(historyPanel.hidden ? "showHistory" : "hideHistory"));
  historyStatus.textContent = historyDeleteError ? t("deleteConversationError") : historyError ? t("historyError") : historyLoading ? "…" : savedConversations.length ? "" : t(historySearch.value.trim() ? "historyNoMatches" : "historyEmpty");
  historyList.replaceChildren();
  for (const item of historyLoading ? [] : savedConversations) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    button.textContent = item.title;
    button.setAttribute("aria-current", String(item.thread_id === conversationId));
    button.disabled = sending || conversationLoading || mutating || historyDeleting;
    const date = document.createElement("time");
    date.dateTime = item.updated_at;
    date.textContent = new Date(item.updated_at).toLocaleString(getLanguage());
    button.appendChild(date);
    button.addEventListener("click", () => { if (!sending && !conversationLoading && !mutating && !historyDeleting) void restoreConversation(item.thread_id); });
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "history-delete";
    remove.setAttribute("aria-label", `${t("deleteConversation")}: ${item.title}`);
    remove.title = t("deleteConversation");
    remove.disabled = button.disabled;
    remove.append(createIcon("trash"));
    remove.addEventListener("click", () => { void deleteConversation(item); });
    const row = document.createElement("div");
    row.className = "history-row";
    row.append(button, remove);
    historyList.appendChild(row);
  }
}

async function deleteConversation(item: ConversationSummary): Promise<void> {
  if (sending || conversationLoading || mutating || historyDeleting) return;
  if (!window.confirm(t("deleteConversationConfirm", { title: item.title }))) return;
  historyDeleting = true;
  historyDeleteError = false;
  updateSelection();
  try {
    const response = await fetch(`/conversations/${item.thread_id}`, { method: "DELETE" });
    if (!response.ok) throw new Error();
    if (item.thread_id === conversationId) {
      conversationId = crypto.randomUUID();
      try { localStorage.setItem(conversationKey, conversationId); } catch { /* Keep the ID in memory. */ }
      log.replaceChildren();
      input.value = "";
      conversationReady = true;
    }
    await loadHistory();
  } catch {
    historyDeleteError = true;
  } finally {
    historyDeleting = false;
    updateSelection();
    renderHistory();
  }
}

async function loadHistory(): Promise<void> {
  historyRequest?.abort();
  const request = new AbortController();
  historyRequest = request;
  historyLoading = true;
  historyError = false;
  renderHistory();
  try {
    const res = await fetch(`/conversations?q=${encodeURIComponent(historySearch.value.trim())}`, { cache: "no-store", signal: request.signal });
    if (!res.ok) throw new Error();
    const data: { conversations: ConversationSummary[] } = await res.json();
    if (historyRequest === request) savedConversations = data.conversations;
  } catch { if (historyRequest === request && !request.signal.aborted) historyError = true; }
  finally { if (historyRequest === request) { historyLoading = false; renderHistory(); } }
}

toggleHistory.addEventListener("click", () => {
  historyPanel.hidden = !historyPanel.hidden;
  try { localStorage.setItem("ThreadLeaf-history-hidden", String(historyPanel.hidden)); } catch { /* Keep state in memory. */ }
  renderHistory();
  if (!historyPanel.hidden) void loadHistory();
});
historyRefresh.addEventListener("click", () => { void loadHistory(); });
historySearch.addEventListener("input", () => {
  if (historySearchTimer !== null) clearTimeout(historySearchTimer);
  historyRequest?.abort();
  historyRequest = null;
  historyError = false;
  historyLoading = true;
  renderHistory();
  historySearchTimer = setTimeout(() => { void loadHistory(); }, 250);
});
historyNew.addEventListener("click", () => { newConversation.click(); });

async function restoreConversation(targetId: string = conversationId): Promise<void> {
  conversationLoading = true;
  updateSelection();
  try {
    const res = await fetch(`/conversations/${targetId}`);
    if (!res.ok) throw new Error();
    const data: { messages: ChatTurn[]; sources: string[] | null } = await res.json();
    const switched = conversationId !== targetId;
    conversationId = targetId;
    try { localStorage.setItem(conversationKey, conversationId); } catch { /* Keep state in memory. */ }
    log.replaceChildren();
    input.value = "";
    if (switched && ready) {
      const available = new Set(documents.map(doc => doc.source));
      selected = new Set(data.sources === null ? available : data.sources.filter(source => available.has(source)));
    }
    for (const turn of data.messages) {
      const el = add(turn.role === "user" ? "user" : "bot", turn.content);
      if (turn.role === "assistant") renderAnswer(el, { reply: turn.content, sources: turn.sources ?? [], answer_kind: turn.answer_kind });
    }
    conversationReady = true;
  } catch {
    const error = add("bot", t("conversationLoadError"));
    error.dataset.i18n = "conversationLoadError";
  }
  conversationLoading = false;
  renderHistory();
  await loadDocuments();
}

newConversation.addEventListener("click", () => {
  if (sending || conversationLoading || historyDeleting) return;
  conversationId = crypto.randomUUID();
  try { localStorage.setItem(conversationKey, conversationId); } catch { /* Keep the ID in memory. */ }
  log.replaceChildren();
  conversationReady = true;
  settings.open = false;
  updateSelection();
  renderHistory();
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = input.value.trim();
  if (!message || !conversationReady || !ready || sending || mutating || historyDeleting || !selected.size) return;
  const sources = [...selected];
  sending = true;
  updateSelection();
  renderDocuments();
  input.value = "";
  add("user", message);
  const pending = add("bot", "");
  const showLoading = () => {
    const key = loadingPhrases[loadingPhrase++ % loadingPhrases.length];
    pending.dataset.i18n = key;
    pending.textContent = t(key);
  };
  showLoading();
  const loadingTimer = setInterval(showLoading, 4000);
  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, sources, thread_id: conversationId, model: modelSelect.value || null }),
    });
    if (!res.ok) {
      const error = await res.json();
      pending.dataset.i18n = res.status === 400 && typeof error.detail === "string" && error.detail.includes("Aggiorna")
        ? "staleSelection" : "requestError";
      pending.dataset.i18nValues = JSON.stringify({ status: res.status });
      throw new Error();
    }
    const data: ChatResponse = await res.json();
    clearInterval(loadingTimer);
    delete pending.dataset.i18n;
    void loadHistory();
    renderAnswer(pending, data);
  } catch {
    clearInterval(loadingTimer);
    if (loadingPhrases.includes(pending.dataset.i18n as MessageKey)) delete pending.dataset.i18n;
    pending.dataset.i18n ??= "networkError";
    pending.textContent = t(pending.dataset.i18n as MessageKey, JSON.parse(pending.dataset.i18nValues ?? "{}"));
  } finally {
    clearInterval(loadingTimer);
    sending = false;
    updateSelection();
    renderDocuments();
  }
});

void loadModels();
