import { BrainCircuit, ChevronDown, Lightbulb, Loader2, RefreshCw, Wand2, Wrench } from "lucide-react";
import { useState } from "react";
import { requestDebugHint } from "../api/client";
import {
  applyAIFix,
  canApplyFix,
  debugCategoryLabel,
  debugMentorFailed,
  debugMentorGuidance,
  debugMentorLoading,
  debugMentorReady,
  initialDebugMentorState,
  unlockNextHint,
  type DebugMentorState
} from "./debugMentorModel";

export interface DebugMentorRunSnapshot {
  verdict: string;
  stderr: string;
  compile_output: string;
  stdout: string;
}

/**
 * AI 结对调试面板（创新功能）：沙箱失败 → 根因诊断 + 三级递进提示逐级解锁
 * →（可选）应用参考修复代码 → 由宿主把代码填入编辑器并自动重跑沙箱验证。
 * 教育原则：先自己改，提示是递进的，AI 不直接代改。
 */
export function DebugMentorPanel({
  courseId,
  nodeId,
  topic,
  sourceCode,
  runResult,
  token,
  onApplyFix
}: {
  courseId: number;
  nodeId: string;
  topic: string;
  sourceCode: string;
  runResult: DebugMentorRunSnapshot | null;
  token: string | undefined;
  onApplyFix: (fixedCode: string) => void;
}) {
  const [state, setState] = useState<DebugMentorState>(initialDebugMentorState);
  const [applying, setApplying] = useState(false);
  const failedRun = runResult !== null && runResult.verdict !== "accepted";

  async function handleAnalyze() {
    if (applying) return;
    setApplying(true);
    setState(debugMentorLoading(state));
    try {
      const result = await requestDebugHint(token, {
        course_id: courseId,
        node_id: nodeId,
        topic,
        source_code: sourceCode,
        error_output: `${runResult?.compile_output || ""}\n${runResult?.stderr || ""}`.trim(),
        verdict: runResult?.verdict || "",
        actual_output: runResult?.stdout || ""
      });
      setState(debugMentorReady(state, result));
    } catch (caught) {
      setState(debugMentorFailed(state, caught instanceof Error ? caught.message : "AI 结对调试失败"));
    } finally {
      setApplying(false);
    }
  }

  function handleApplyFix() {
    if (applying) return;
    setApplying(true);
    try {
      const { state: next, fixedCode } = applyAIFix(state);
      setState(next);
      onApplyFix(fixedCode);
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="debug-mentor">
      {state.stage === "idle" && failedRun ? (
        <button className="debug-mentor-launch secondary-action compact-button" onClick={() => { void handleAnalyze(); }} type="button">
          <BrainCircuit size={15} />
          AI 结对调试：帮我看看哪里错了
        </button>
      ) : null}

      {state.stage === "loading" ? (
        <div className="debug-mentor-loading">
          <Loader2 className="spin" size={15} />
          <span>AI 正在结合课程知识库分析错误…</span>
        </div>
      ) : null}

      {state.stage === "error" ? (
        <div className="debug-mentor-error">
          <span>{state.error}</span>
          <button className="secondary-action compact-button" onClick={() => { void handleAnalyze(); }} type="button">
            <RefreshCw size={13} />
            重试
          </button>
        </div>
      ) : null}

      {state.stage === "ready" && state.result ? (
        <div className="debug-mentor-card">
          <div className="debug-mentor-head">
            <BrainCircuit size={15} />
            <strong>AI 结对调试</strong>
            <em className="debug-mentor-category">{debugCategoryLabel(state.result.error_category)}</em>
            {state.result.key_concept ? <em className="debug-mentor-concept">{state.result.key_concept}</em> : null}
          </div>
          <p className="debug-mentor-diagnosis">{state.result.diagnosis}</p>
          <div className="debug-mentor-hints">
            {state.result.hints.slice(0, state.unlockedLevel).map((hint, index) => (
              <div className={`debug-mentor-hint level-${index + 1}`} key={`${index}-${hint.slice(0, 10)}`}>
                <Lightbulb size={13} />
                <span>{hint}</span>
              </div>
            ))}
            {state.unlockedLevel < Math.min(3, state.result.hints.length) ? (
              <button className="debug-mentor-unlock secondary-action compact-button" onClick={() => setState(unlockNextHint(state))} type="button">
                <ChevronDown size={13} />
                再看一条提示（{state.unlockedLevel}/{Math.min(3, state.result.hints.length)}）
              </button>
            ) : null}
          </div>
          <small className="debug-mentor-guidance">{debugMentorGuidance(state.unlockedLevel)}</small>
          {canApplyFix(state) ? (
            <button className="debug-mentor-apply primary-action compact-button" disabled={applying} onClick={handleApplyFix} type="button">
              <Wand2 size={14} />
              应用 AI 参考修复（自动重跑沙箱验证）
            </button>
          ) : null}
          {state.appliedFix ? (
            <small className="debug-mentor-applied">
              <Wrench size={12} />
              修复代码已填入编辑器，等待重新运行验证。
            </small>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
