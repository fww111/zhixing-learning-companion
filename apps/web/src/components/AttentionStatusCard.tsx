import { Eye, EyeOff, Video, VideoOff } from "lucide-react";
import type { AttentionStateKey, } from "../composables/attentionInference";
import type { AttentionStatus } from "../composables/useAttentionAnalysis";

const STATE_LABELS: Record<AttentionStateKey, string> = {
  focused: "专注中",
  confused: "似乎有点困惑",
  distracted: "走神啦",
  tired: "看起来累了",
  no_face: "未检测到人脸"
};

const STATE_CLASS: Record<AttentionStateKey, string> = {
  focused: "ok",
  confused: "warn",
  distracted: "warn",
  tired: "warn",
  no_face: "idle"
};

interface AttentionStatusCardProps {
  enabled: boolean;
  busy: boolean;
  status: AttentionStatus;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  onEnable: () => void;
  onDisable: () => void;
}

/** 左下角浮动卡片：学习状态感知开关 + 摄像头预览 + 实时状态。画面仅本机分析。 */
export function AttentionStatusCard({
  enabled,
  busy,
  status,
  videoRef,
  onEnable,
  onDisable
}: AttentionStatusCardProps) {
  return (
    <aside className="attention-card" aria-label="学习状态感知">
      <div className="attention-card-head">
        <Eye size={15} />
        <strong>学习状态感知</strong>
        {enabled ? (
          <button className="attention-toggle on" disabled={busy} onClick={onDisable} type="button">
            <VideoOff size={14} />
            关闭
          </button>
        ) : (
          <button className="attention-toggle" disabled={busy} onClick={onEnable} type="button">
            <Video size={14} />
            开启
          </button>
        )}
      </div>

      {!enabled ? (
        <p className="attention-hint">
          开启后在本机分析摄像头画面（专注/困惑/走神/疲劳），辅助 AI 在你卡住时主动换一种讲法。
          画面不会离开你的电脑。
        </p>
      ) : (
        <div className="attention-body">
          <video className="attention-preview" muted playsInline ref={videoRef} />
          <div className="attention-meta">
            <span className={`attention-state ${STATE_CLASS[status.state]}`}>
              {STATE_LABELS[status.state]}
            </span>
            {status.confidence > 0 ? (
              <small>置信度 {Math.round(status.confidence * 100)}%</small>
            ) : null}
            {status.blinkRatePerMinute > 0 ? (
              <small>眨眼 {status.blinkRatePerMinute}/min</small>
            ) : null}
            {busy ? <small>模型加载中…</small> : null}
            {status.error ? <small className="attention-error">{status.error}</small> : null}
            <small className="attention-privacy">
              <EyeOff size={11} /> 仅本机分析，画面不上传
            </small>
          </div>
        </div>
      )}
    </aside>
  );
}
