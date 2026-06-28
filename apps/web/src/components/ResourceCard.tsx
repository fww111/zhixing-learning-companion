import { BookOpenText, Code2, FileText, GitBranch, ListChecks, Video } from "lucide-react";
import { marked } from "marked";
import type { Resource, ResourceType } from "../api/client";

const icons: Record<ResourceType, typeof FileText> = {
  document: FileText,
  mind_map: GitBranch,
  exercise: ListChecks,
  reading: BookOpenText,
  video: Video,
  code_lab: Code2
};

const labels: Record<ResourceType, string> = {
  document: "讲解文档",
  mind_map: "思维导图",
  exercise: "练习题",
  reading: "拓展阅读",
  video: "视频/动画",
  code_lab: "代码实操"
};

interface ResourceCardProps {
  resource: Resource;
}

export function ResourceCard({ resource }: ResourceCardProps) {
  const Icon = icons[resource.type];
  const html = marked.parse(resource.content, { async: false }) as string;

  return (
    <article className="resource-card">
      <div className="resource-header">
        <span className="resource-icon">
          <Icon size={17} />
        </span>
        <div>
          <strong>{resource.title}</strong>
          <p>{labels[resource.type]}</p>
        </div>
      </div>
      <div className="resource-body" dangerouslySetInnerHTML={{ __html: html }} />
      <div className="reason">{resource.recommendation_reason}</div>
      <div className={`grounding-strip ${resource.grounding_status === "verified" ? "verified" : "limited"}`}>
        <span>{resource.grounding_status === "verified" ? "已通过知识库溯源校验" : "证据有限"}</span>
        {resource.citation_chunk_ids?.length ? (
          <small>引用块：{resource.citation_chunk_ids.join("、")}</small>
        ) : (
          <small>暂无可追踪原文块</small>
        )}
      </div>
      {resource.verification_notes?.length ? (
        <ul className="verification-notes">
          {resource.verification_notes.slice(0, 2).map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
      {resource.quality_score ? (
        <div className="quality">
          <span>准确性 {(resource.quality_score.accuracy * 100).toFixed(0)}%</span>
          <span>适配度 {(resource.quality_score.personalization * 100).toFixed(0)}%</span>
        </div>
      ) : null}
    </article>
  );
}
