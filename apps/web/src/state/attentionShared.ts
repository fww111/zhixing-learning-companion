/**
 * 学习状态感知的跨组件共享 store（模块级单例，同窗口内生效）。
 *
 * AttentionFloating（全局悬浮窗）作为唯一写入方；TutorAssistantFloating 在发请求时
 * 读取当前状态注入 attention_state 字段，让辅导 AI"看见"学生的专注状态。
 * 这里只有状态指标，永远没有图像数据。
 */

import type { AttentionStateKey } from "../composables/attentionInference";

export interface AttentionSharedState {
  state: AttentionStateKey;
  confidence: number;
  courseId?: number;
  nodeId: string;
  updatedAt: number;
}

let current: AttentionSharedState | null = null;

export function setSharedAttention(state: AttentionSharedState | null): void {
  current = state && Date.now() - state.updatedAt < 5000 ? state : null;
}

export function getSharedAttention(): AttentionSharedState | null {
  if (current && Date.now() - current.updatedAt >= 5000) {
    current = null; // 超过 5s 没刷新视为过期（感知已停止或页面隐藏）
  }
  return current;
}
