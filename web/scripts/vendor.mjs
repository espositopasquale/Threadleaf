import { copyFile, mkdir } from "node:fs/promises";

const root = new URL("../", import.meta.url);
await mkdir(new URL("public/vendor/", root), { recursive: true });
for (const [source, destination] of [
  ["node_modules/marked/lib/marked.umd.js", "public/vendor/marked.umd.js"],
  ["node_modules/dompurify/dist/purify.min.js", "public/vendor/purify.min.js"],
  ["node_modules/marked/LICENSE.md", "public/vendor/marked-LICENSE.txt"],
  ["node_modules/dompurify/LICENSE", "public/vendor/dompurify-LICENSE.txt"],
  ["node_modules/dompurify/LICENSE-MPL", "public/vendor/dompurify-LICENSE-MPL.txt"],
  ["node_modules/@fortawesome/fontawesome-svg-core/LICENSE.txt", "public/vendor/fontawesome-core-LICENSE.txt"],
  ["node_modules/@fortawesome/free-solid-svg-icons/LICENSE.txt", "public/vendor/fontawesome-icons-LICENSE.txt"],
  ["LICENSE", "public/vendor/ThreadLeaf-LICENSE.txt"],
  ["../COPYRIGHT", "public/vendor/ThreadLeaf-COPYRIGHT.txt"],
]) {
  await copyFile(new URL(source, root), new URL(destination, root));
}
