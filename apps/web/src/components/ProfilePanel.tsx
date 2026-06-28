import {
  Activity,
  AlertTriangle,
  BarChart3,
  Brain,
  CalendarClock,
  CheckCircle2,
  Gauge,
  Layers3,
  Sparkles,
  Target,
  UserRoundCog
} from "lucide-react";
import type { StudentProfile } from "../api/client";
import {
  buildProfileVisualizationModel,
  type ProfileDimensionCard,
  type ProfileMetric,
  type ProfileRadarAxis,
  type ProfileTagGroup,
  type ProfileTimelineItem
} from "./profileVisualizationModel";

interface ProfilePanelProps {
  profile?: StudentProfile;
}

export function ProfilePanel({ profile }: ProfilePanelProps) {
  const model = profile ? buildProfileVisualizationModel(profile) : undefined;

  return (
    <section className="profile-dimension-panel dynamic-profile-panel" aria-label="课程动态学生画像">
      <div className="profile-dimension-header">
        <div className="panel-title">
          <UserRoundCog size={18} />
          <h2>课程动态学生画像</h2>
        </div>
        <span>{model?.versionLabel || "等待构建"}</span>
      </div>

      {model ? (
        <div className="profile-visual-dashboard">
          <article className="profile-hero-card">
            <div className="profile-hero-identity" aria-hidden="true">
              <div className="profile-portrait">
                <Brain size={30} />
              </div>
              <div className="profile-portrait-rings">
                <span />
                <span />
                <span />
              </div>
            </div>
            <div className="profile-hero-copy">
              <span>课程专属画像</span>
              <strong>{model.summary}</strong>
              <p>画像随课堂学习、随堂测试、编程练习和学习评估持续更新，并用于约束学习路径与资源推荐。</p>
            </div>
          </article>

          <div className="profile-visual-metrics">
            {model.metrics.map((metric) => (
              <MetricCard key={metric.label} metric={metric} />
            ))}
          </div>

          <div className="profile-visual-main">
            <RadarCard axes={model.radarAxes} />
            <article className="profile-visual-card profile-profile-focus-card">
              <div className="profile-card-title">
                <Sparkles size={16} />
                <strong>画像重点</strong>
              </div>
              <div className="profile-focus-stack">
                {model.dimensionCards.slice(0, 3).map((card) => (
                  <DimensionMini key={card.title} card={card} />
                ))}
              </div>
            </article>
          </div>

          {model.updateReason ? (
            <article className="profile-update-explain profile-visual-update">
              <Activity size={16} />
              <div>
                <strong>最近一次画像更新</strong>
                <p>{model.updateReason}</p>
              </div>
            </article>
          ) : null}

          <div className="profile-dimension-card-grid">
            {model.dimensionCards.map((card) => (
              <DimensionCard key={card.title} card={card} />
            ))}
          </div>

          <div className="profile-tag-section">
            {model.tagGroups.map((group) => (
              <TagGroup key={group.title} group={group} />
            ))}
          </div>

          {model.modalityRows.length ? (
            <article className="profile-visual-card">
              <div className="profile-card-title">
                <BarChart3 size={16} />
                <strong>资源模态有效性</strong>
              </div>
              <div className="profile-modality-list profile-modality-bars">
                {model.modalityRows.map((row) => (
                  <div key={row.label}>
                    <span>{row.label}</span>
                    <small>{row.detail}</small>
                    <div className="profile-dimension-meter" aria-label={`${row.label} 有效性 ${row.score}%`}>
                      <span style={{ width: `${row.score}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </article>
          ) : null}

          {model.growthSummary || model.riskSignals.length ? (
            <article className="profile-visual-card">
              <div className="profile-card-title">
                <AlertTriangle size={16} />
                <strong>风险与成长趋势</strong>
              </div>
              {model.growthSummary ? <p>{model.growthSummary}</p> : null}
              {model.riskSignals.length ? (
                <div className="profile-chip-row">
                  {model.riskSignals.map((item) => <span key={item}>{item}</span>)}
                </div>
              ) : null}
            </article>
          ) : null}

          {model.timeline.length ? <EvidenceTimeline items={model.timeline} /> : null}
        </div>
      ) : (
        <div className="profile-dimension-empty profile-visual-empty">
          <div className="profile-empty-illustration" aria-hidden="true">
            <UserRoundCog size={28} />
          </div>
          <strong>等待画像 Agent 提问</strong>
          <p>完成课程专属访谈后，这里会持续展示画像摘要、能力雷达、薄弱点、资源偏好、学习时间和路径调整线索。</p>
        </div>
      )}
    </section>
  );
}

function MetricCard({ metric }: { metric: ProfileMetric }) {
  return (
    <article className={`profile-metric-card ${metric.tone}`}>
      <span>{metric.label}</span>
      <strong>{metric.value}</strong>
      <small>{metric.detail}</small>
    </article>
  );
}

function RadarCard({ axes }: { axes: ProfileRadarAxis[] }) {
  const points = radarPoints(axes);
  return (
    <article className="profile-visual-card profile-radar-card">
      <div className="profile-card-title">
        <Gauge size={16} />
        <strong>六维能力画像</strong>
      </div>
      <div className="profile-radar-layout">
        <svg className="profile-radar-svg" viewBox="0 0 220 220" role="img" aria-label="学生画像六维雷达图">
          {[30, 55, 80].map((radius) => (
            <polygon key={radius} points={radarGridPoints(radius)} className="profile-radar-grid" />
          ))}
          {axes.map((axis, index) => {
            const [x, y] = radarCoordinate(index, 86);
            return <line key={axis.label} x1="110" y1="110" x2={x} y2={y} className="profile-radar-axis" />;
          })}
          <polygon points={points} className="profile-radar-area" />
          {axes.map((axis, index) => {
            const [x, y] = radarCoordinate(index, 86 * (axis.score / 100));
            return <circle key={axis.label} cx={x} cy={y} r="4" className="profile-radar-dot" />;
          })}
        </svg>
        <div className="profile-radar-legend">
          {axes.map((axis) => (
            <div key={axis.label}>
              <span>{axis.label}</span>
              <strong>{axis.score}%</strong>
              <small>{axis.description}</small>
            </div>
          ))}
        </div>
      </div>
    </article>
  );
}

function DimensionMini({ card }: { card: ProfileDimensionCard }) {
  return (
    <div className="profile-focus-item">
      <span>{card.title}</span>
      <strong>{card.value}</strong>
    </div>
  );
}

function DimensionCard({ card }: { card: ProfileDimensionCard }) {
  const icon = cardIcon(card.title);
  return (
    <article className="profile-dimension-card">
      <div>
        {icon}
        <span>{card.title}</span>
      </div>
      <strong>{card.value}</strong>
      <p>{card.detail}</p>
      <div className="profile-dimension-meter" aria-label={`${card.title} 完成度 ${card.score}%`}>
        <span style={{ width: `${card.score}%` }} />
      </div>
    </article>
  );
}

function TagGroup({ group }: { group: ProfileTagGroup }) {
  return (
    <article className="profile-insight-card">
      <strong>{group.title}</strong>
      <div>
        {group.items.map((item) => <span key={`${group.title}-${item}`}>{item}</span>)}
      </div>
    </article>
  );
}

function EvidenceTimeline({ items }: { items: ProfileTimelineItem[] }) {
  return (
    <article className="profile-visual-card profile-evidence-card">
      <div className="profile-card-title">
        <Activity size={16} />
        <strong>最近画像证据</strong>
      </div>
      <div className="profile-evidence-timeline">
        {items.map((item, index) => (
          <div key={`${item.source}-${item.topic}-${index}`}>
            <span>{item.source} · {item.topic}</span>
            <p>{item.detail}</p>
          </div>
        ))}
      </div>
    </article>
  );
}

function radarPoints(axes: ProfileRadarAxis[]) {
  return axes.map((axis, index) => radarCoordinate(index, 86 * (axis.score / 100)).join(",")).join(" ");
}

function radarGridPoints(radius: number) {
  return Array.from({ length: 6 }, (_, index) => radarCoordinate(index, radius).join(",")).join(" ");
}

function radarCoordinate(index: number, radius: number) {
  const angle = -Math.PI / 2 + index * (Math.PI * 2 / 6);
  return [Number((110 + Math.cos(angle) * radius).toFixed(2)), Number((110 + Math.sin(angle) * radius).toFixed(2))];
}

function cardIcon(title: string) {
  if (title.includes("目标")) {
    return <Target size={15} />;
  }
  if (title.includes("时间")) {
    return <CalendarClock size={15} />;
  }
  if (title.includes("基础")) {
    return <Layers3 size={15} />;
  }
  if (title.includes("评估")) {
    return <CheckCircle2 size={15} />;
  }
  return <Sparkles size={15} />;
}
