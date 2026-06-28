import { Send, Sparkles } from "lucide-react";

interface ChatPanelProps {
  conversation: string;
  topic: string;
  loading: boolean;
  onConversationChange: (value: string) => void;
  onTopicChange: (value: string) => void;
  onSubmit: () => void;
}

export function ChatPanel({
  conversation,
  topic,
  loading,
  onConversationChange,
  onTopicChange,
  onSubmit
}: ChatPanelProps) {
  return (
    <section className="panel chat-panel">
      <div className="panel-title">
        <Sparkles size={18} />
        <h2>学习需求对话</h2>
      </div>
      <label>
        学习主题
        <input value={topic} onChange={(event) => onTopicChange(event.target.value)} />
      </label>
      <label>
        学生自述
        <textarea value={conversation} onChange={(event) => onConversationChange(event.target.value)} rows={9} />
      </label>
      <button className="primary-action" disabled={loading} onClick={onSubmit}>
        <Send size={17} />
        {loading ? "生成中" : "生成学习方案"}
      </button>
    </section>
  );
}
