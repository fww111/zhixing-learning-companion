import { Route } from "lucide-react";
import type { LearningPath as LearningPathType } from "../api/client";

interface LearningPathProps {
  path?: LearningPathType;
}

export function LearningPath({ path }: LearningPathProps) {
  return (
    <section className="panel">
      <div className="panel-title">
        <Route size={18} />
        <h2>个性化学习路径</h2>
      </div>
      {path ? (
        <div className="path-list">
          {path.stages.map((stage, index) => (
            <div className="path-stage" key={stage.title}>
              <span className="stage-index">{index + 1}</span>
              <div>
                <strong>{stage.title}</strong>
                <p>{stage.goal}</p>
                <small>{stage.estimated_minutes}分钟 · {stage.practice_task}</small>
                <div className="reason">{stage.recommendation_reason}</div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="empty">生成后展示阶段目标、资源顺序和推荐理由。</p>
      )}
    </section>
  );
}
