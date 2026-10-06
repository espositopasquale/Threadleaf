import { mkdir, writeFile } from "node:fs/promises";

let core, solid;
try {
  core = await import("@fortawesome/fontawesome-svg-core");
  solid = await import("@fortawesome/free-solid-svg-icons");
} catch (error) {
  if (error.code === "ERR_MODULE_NOT_FOUND") {
    throw new Error("Font Awesome npm modules are missing. Run npm install in web/ before building.", { cause: error });
  }
  throw error;
}
const definitions = {
  spa: solid.faSpa,
  gear: solid.faGear,
  folder: solid.faFolder,
  trash: solid.faTrashCan,
  chevronLeft: solid.faChevronLeft,
  chevronRight: solid.faChevronRight,
  upload: solid.faFileArrowUp,
  send: solid.faPaperPlane,
  search: solid.faMagnifyingGlass,
  info: solid.faCircleInfo,
  newChat: solid.faPenToSquare,
};
const icons = Object.fromEntries(Object.entries(definitions).map(([name, definition]) => [
  name, core.icon(definition, { attributes: { "aria-hidden": "true", focusable: "false" } }).html.join(""),
]));
const output = new URL("../public/vendor/", import.meta.url);
await mkdir(output, { recursive: true });
await writeFile(new URL("icons.js", output), `// Font Awesome icons generated from npm modules.\nglobalThis.ThreadLeafIcons = ${JSON.stringify(icons)};\n`);
console.log(`Generated ${Object.keys(icons).length} local Font Awesome SVG icons.`);
