import { Bot, CheckCircle2, Clock3 } from "lucide-react";
import type { AgentEvent, ResourceType } from "../api/client";

interface AgentTimelineProps {
  running: boolean;
  completed: boolean;
  events?: AgentEvent[];
  resourceTypes?: ResourceType[];
}

const resourceAgentLabels: Record<ResourceType, string> = {
  mind_map: "思维导图Agent",
  document: "文档生成Agent",
  video: "视频脚本Agent",
  code_lab: "代码实操Agent",
  exercise: "题库生成Agent",
  reading: "拓展阅读Agent"
};

const fallbackAgents = ["画像构建Agent", "文档生成Agent", "题库生成Agent", "多模态资源Agent", "代码实操Agent", "路径规划Agent", "学习评估Agent"];
const resourceTypeValues = new Set<ResourceType>(["mind_map", "document", "video", "code_lab", "exercise", "reading"]);

function asResourceType(value: string | undefined): ResourceType | undefined {
  return value && resourceTypeValues.has(value as ResourceType) ? value as ResourceType : undefined;
}

export function AgentTimeline({ running, completed, events = [], resourceTypes = [] }: AgentTimelineProps) {
  const completedTypes = new Set(
    events
      .filter((event) => event.event === "agent_completed" && event.resource_type)
      .map((event) => asResourceType(event.resource_type))
      .filter((type): type is ResourceType => Boolean(type))
  );
  const agents: Array<{ key: string; resourceType?: ResourceType; label: string; detail: string }> = resourceTypes.length
    ? resourceTypes.map((type) => ({ key: type, resourceType: type, label: resourceAgentLabels[type], detail: "按路径推荐资源生成" }))
    : fallbackAgents.map((agent) => ({ key: agent, label: agent, detail: "工作流阶段" }));

  return (
    <section className="panel">
      <div className="panel-title">
        <Bot size={18} />
        <h2>Agent协作</h2>
      </div>
      <div className="timeline">
        {agents.map((agent, index) => {
          const isDone = (agent.resourceType ? completedTypes.has(agent.resourceType) : false) || (!resourceTypes.length && completed) || (running && index === 0);
          return (
            <div className="timeline-item" key={agent.key}>
              <span className={isDone ? "status-dot done" : "status-dot"}>
                {isDone ? <CheckCircle2 size={14} /> : <Clock3 size={14} />}
              </span>
              <div>
                <strong>{agent.label}</strong>
                <p>{isDone ? "已调用模型结合知识库生成" : running ? "排队等待" : agent.detail}</p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
