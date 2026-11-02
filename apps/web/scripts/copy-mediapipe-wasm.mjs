// 把 MediaPipe vision wasm 从 node_modules 拷到 public，供 FilesetResolver 本地加载。
// 由 predev / prebuild 自动执行；public/mediapipe/wasm 不入库（41MB，见 .gitignore）。
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = dirname(fileURLToPath(import.meta.url)) + "/..";
const source = join(webRoot, "node_modules", "@mediapipe", "tasks-vision", "wasm");
const target = join(webRoot, "public", "mediapipe", "wasm");

if (!existsSync(source)) {
  console.error("[copy-mediapipe-wasm] node_modules/@mediapipe/tasks-vision 未安装，请先 npm install");
  process.exit(0); // 不阻塞不使用感知功能的构建
}

mkdirSync(target, { recursive: true });
cpSync(source, target, { recursive: true });
console.log("[copy-mediapipe-wasm] wasm files copied to public/mediapipe/wasm");
