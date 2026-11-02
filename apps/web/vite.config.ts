import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 后端地址可用环境变量覆盖（如本机 8000 被 Docker Desktop 占用时：
// VITE_API_TARGET=http://127.0.0.1:8010 npm run dev）
const apiTarget = process.env.VITE_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/health": apiTarget
    }
  }
});
