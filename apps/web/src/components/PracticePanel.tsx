import { ChevronLeft, ChevronRight, CirclePlay, Loader2, PlayCircle, Trophy } from "lucide-react";
import { useMemo, useState } from "react";
import { executeCode } from "./codeExecutionModel";
import { generatePractice, type PracticeExercisePayload, type PracticeStep } from "../api/client";

/** 可视化步进器状态：当前帧索引 / 是否自动播放 */
export interface VisualizationState {
  frameIndex: number;
  playing: boolean;
}

export function initialVisualizationState(steps: PracticeStep[]): VisualizationState {
  return { frameIndex: steps.length ? 0 : -1, playing: false };
}

export function stepFrame(
  state: VisualizationState,
  steps: PracticeStep[],
  direction: "next" | "prev"
): VisualizationState {
  if (!steps.length) {
    return state;
  }
  const delta = direction === "next" ? 1 : -1;
  const next = Math.max(0, Math.min(steps.length - 1, state.frameIndex + delta));
  return { frameIndex: next, playing: false };
}

export function togglePlay(state: VisualizationState, steps: PracticeStep[]): VisualizationState {
  if (!steps.length) {
    return state;
  }
  if (!state.playing && state.frameIndex >= steps.length - 1) {
    return { frameIndex: 0, playing: true };
  }
  return { ...state, playing: !state.playing };
}

/** 纯函数帧推进（供自动播放 interval 调用）；到末帧停止播放。 */
export function advanceFrame(state: VisualizationState, steps: PracticeStep[]): VisualizationState {
  if (!steps.length) {
    return state;
  }
  if (state.frameIndex >= steps.length - 1) {
    return { frameIndex: steps.length - 1, playing: false };
  }
  return { frameIndex: state.frameIndex + 1, playing: true };
}

const HIGHLIGHT_SERIES = ["--viz-series-1", "--viz-series-2", "--viz-series-3"];

/**
 * 算法过程可视化（多模态创新）：SVG 条形数组 + 指针高亮 + 步进/自动播放。
 * 帧数据由出题 Agent 生成（展示核心算法的数组状态推进）。
 */
export function AlgorithmVisualizer({ steps }: { steps: PracticeStep[] }) {
  const [state, setState] = useState<VisualizationState>(() => initialVisualizationState(steps));

  useMemo(() => {
    if (!state.playing) return;
    const timer = window.setInterval(() => {
      setState((current) => advanceFrame(current, steps));
    }, 900);
    return () => window.clearInterval(timer);
  }, [state.playing, steps]);

  const frame = steps[state.frameIndex];
  if (!frame) {
    return null;
  }
  const values = Array.isArray(frame.array) ? frame.array : [];
  const highlights = Array.isArray(frame.highlight) ? frame.highlight : [];
  const max = Math.max(...values.map((value) => Math.abs(Number(value) || 0)), 1);

  return (
    <div className="algo-viz" aria-label="算法过程可视化">
      <div className="algo-viz-stage" role="img" aria-label={`第 ${state.frameIndex + 1} 步：${frame.label || ""}`}>
        <svg viewBox={`0 0 ${Math.max(values.length * 52 + 24, 120)} 130`} className="algo-viz-svg">
          {values.map((value, index) => {
            const height = Math.max(12, (Math.abs(Number(value) || 0) / max) * 72);
            const highlighted = highlights.includes(index);
            const color = highlighted ? "var(--viz-series-1)" : "var(--viz-series-6)";
            return (
              <g key={`${index}-${value}`} transform={`translate(${20 + index * 52}, 24)`}>
                <rect
                  data-tooltip={highlighted ? `高亮比较/交换中：${value}` : `${value}`}
                  fill={color}
                  height={height}
                  opacity={highlighted ? 0.95 : 0.4}
                  rx={6}
                  width={40}
                  y={88 - height}
                />
                <text className="algo-viz-value" textAnchor="middle" x={20} y={112}>
                  {value}
                </text>
                <text className="algo-viz-index" textAnchor="middle" x={20} y={126}>
                  [{index}]
                </text>
              </g>
            );
          })}
        </svg>
        <div className="algo-viz-label">{frame.label || `第 ${state.frameIndex + 1} 步`}</div>
        <div className="algo-viz-progress">
          {steps.map((_, index) => (
            <i className={index === state.frameIndex ? "active" : ""} key={index} />
          ))}
        </div>
      </div>
      <div className="algo-viz-controls">
        <button className="btn btn-sm" onClick={() => setState(stepFrame(state, steps, "prev"))} type="button" aria-label="上一步">
          <ChevronLeft size={14} />
          上一步
        </button>
        <button className="btn btn-sm" onClick={() => setState(togglePlay(state, steps))} type="button">
          {state.playing ? "暂停" : "自动播放"}
        </button>
        <button className="btn btn-sm" onClick={() => setState(stepFrame(state, steps, "next"))} type="button" aria-label="下一步">
          下一步
          <ChevronRight size={14} />
        </button>
        <span className="text-small text-muted">
          {state.frameIndex + 1}/{steps.length}
        </span>
      </div>
    </div>
  );
}

export type PracticeStage = "idle" | "generating" | "ready" | "error";

/**
 * 随堂实战练习面板（内嵌编译器完整形态）：
 * 学完本节 → 按知识点出题（沙箱预验证参考解）→ 编辑器作答 → OJ 式判分 → 算法过程可视化复盘。
 */
export function PracticePanel({
  courseId,
  nodeId,
  topic,
  token
}: {
  courseId: number;
  nodeId: string;
  topic: string;
  token: string | undefined;
}) {
  const [stage, setStage] = useState<PracticeStage>("idle");
  const [exercise, setExercise] = useState<PracticeExercisePayload>();
  const [code, setCode] = useState("");
  const [output, setOutput] = useState("点击「运行判分」提交到服务端沙箱。");
  const [verdict, setVerdict] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [passed, setPassed] = useState(false);

  async function handleGenerate() {
    if (stage === "generating") return;
    setStage("generating");
    setError("");
    try {
      const { generatePractice } = await import("../api/client");
      const result = await generatePractice(token, courseId, topic, nodeId);
      setExercise(result.exercise);
      setCode(result.exercise.starter_code);
      setVerdict("");
      setPassed(false);
      setOutput("阅读题面后，在下方编辑器完成作答，然后「运行判分」。");
      setStage("ready");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "出题失败，请稍后重试");
      setStage("error");
    }
  }

  async function handleRun() {
    if (!exercise || running) return;
    setRunning(true);
    try {
      const outcome = await executeCode({
        token,
        courseId,
        source: code,
        expectedOutput: exercise.expected_output,
        stdinText: exercise.stdin_text
      });
      setOutput(outcome.output);
      setVerdict(outcome.verdict || "");
      const ok = outcome.serverVerified ? Boolean(outcome.passed) : outcome.category === "ok";
      setPassed(ok);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="practice-panel">
      <div className="practice-head">
        <CirclePlay size={17} />
        <h3>随堂实战练习</h3>
        <span className="text-small text-muted">学完本节，AI 按教材证据出题，服务端沙箱真实判分</span>
        <button className="primary-action compact-button" disabled={stage === "generating"} onClick={() => { void handleGenerate(); }} type="button">
          {stage === "generating" ? <Loader2 className="spin" size={14} /> : <PlayCircle size={14} />}
          {stage === "generating" ? "出题中（含沙箱预验证）…" : stage === "ready" ? "再出一题" : "为本知识点出一道实战题"}
        </button>
      </div>

      {stage === "error" ? <div className="error">{error}</div> : null}

      {stage === "ready" && exercise ? (
        <div className="practice-body">
          <div className="practice-question">
            <div className="practice-question-head">
              <strong>{exercise.title}</strong>
              <em className={`practice-difficulty ${exercise.difficulty}`}>{exercise.difficulty}</em>
              {exercise.verified ? (
                <em className="practice-verified">
                  <Trophy size={12} />
                  判分用例已预验证
                </em>
              ) : (
                <em className="practice-unverified">参考解未通过预验证，判分仅供参考</em>
              )}
            </div>
            <p>{exercise.description}</p>
            {exercise.hints.length ? (
              <details className="practice-hints">
                <summary>卡住了？展开提示（{exercise.hints.length} 条）</summary>
                <ul>
                  {exercise.hints.map((hint, index) => (
                    <li key={`${index}-${hint.slice(0, 10)}`}>{hint}</li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>

          {exercise.visualization.steps.length ? (
            <AlgorithmVisualizer steps={exercise.visualization.steps} />
          ) : null}

          <div className="practice-code-grid">
            <div className="code-editor-shell">
              <div className="code-toolbar">
                <span>C++ · 内嵌编译器</span>
                <button className="primary-action compact-button" disabled={running} onClick={() => { void handleRun(); }} type="button">
                  <PlayCircle size={14} />
                  {running ? "判分中…" : "运行判分"}
                </button>
              </div>
              <textarea aria-label="随堂实战代码编辑器" onChange={(event) => setCode(event.target.value)} value={code} />
            </div>
            <div className="practice-io">
              <div>
                <span>测试输入（固定）</span>
                <pre>{exercise.stdin_text || "（无输入）"}</pre>
              </div>
              <div>
                <span>期望输出</span>
                <pre>{exercise.expected_output}</pre>
              </div>
              <div>
                <span>
                  本次输出
                  {verdict ? (
                    <em className={`sandbox-badge ${verdict === "accepted" ? "ok" : "warn"}`}>服务端沙箱 · {verdict === "accepted" ? "AC 通过" : verdict === "wrong_answer" ? "输出不一致" : verdict === "compile_error" ? "编译失败" : verdict === "timeout" ? "运行超时" : "运行出错"}</em>
                  ) : null}
                </span>
                <pre>{output}</pre>
              </div>
            </div>
          </div>

          {passed ? (
            <p className="auto-advance-note practice-pass">
              <Trophy size={14} />
              实战通过！本次练习已计入学习证据，画像与掌握度随学随新。
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
