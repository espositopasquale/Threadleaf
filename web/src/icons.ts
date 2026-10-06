type IconName = "spa" | "gear" | "folder" | "trash" | "chevronLeft" | "chevronRight" | "upload" | "send" | "search" | "info" | "newChat";
declare const ThreadLeafIcons: Record<IconName, string> | undefined;
const fallback: Record<IconName, string> = {
  spa: "\u2618", gear: "\u2699", folder: "\u{1F4C1}", trash: "\u00D7",
  chevronLeft: "\u2039", chevronRight: "\u203A", upload: "\u2191", send: "\u27A4",
  search: "\u2315",
  info: "\u24D8",
  newChat: "+",
};

export function setIcon(element: HTMLElement, name: IconName): void {
  if (typeof ThreadLeafIcons === "undefined") {
    element.textContent = fallback[name];
    return;
  }
  // The SVG is generated at build time from trusted npm icon definitions.
  element.innerHTML = ThreadLeafIcons[name];
  element.classList.add("icon");
}

export function createIcon(name: IconName): HTMLSpanElement {
  const element = document.createElement("span");
  element.setAttribute("aria-hidden", "true");
  setIcon(element, name);
  return element;
}

export function initializeIcons(): void {
  for (const element of Array.from(document.querySelectorAll<HTMLElement>("[data-icon]"))) {
    setIcon(element, element.dataset.icon as IconName);
  }
}
