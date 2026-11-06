import { BookOpen, GitBranch, LogIn, Network, Route, ShieldCheck, UserPlus } from "lucide-react";
import { FormEvent, useState } from "react";
import { loginUser, registerUser, type AuthResponse } from "../api/client";

interface AuthPanelProps {
  onAuthenticated: (auth: AuthResponse) => void;
}

const processStages = [
  { icon: ShieldCheck, title: "对话构建画像", description: "目标、基础、弱项、时间、资源偏好", status: "DeepSeek V4 Pro", statusClass: "success-chip" },
  { icon: BookOpen, title: "课程材料知识库", description: "PDF/PPT 解析、分块、BGE-M3 向量、Milvus", status: "MinerU", statusClass: "warning-chip" },
  { icon: Network, title: "知识图谱与路径规划", description: "Neo4j 图谱、掌握度颜色、今日任务", status: "Neo4j", statusClass: "blue-chip" },
  { icon: Route, title: "OpenMAIC 互动课堂", description: "Agentic RAG 生成大纲，OpenMAIC 呈现学习页", status: "OpenMAIC", statusClass: "" },
  { icon: GitBranch, title: "评估反馈重规划", description: "达标回主线，未达标进入补救路径", status: "Loop", statusClass: "" }
];

export function AuthPanel({ onAuthenticated }: AuthPanelProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("xiaoming");
  const [email, setEmail] = useState("xm@example.com");
  const [account, setAccount] = useState("xiaoming");
  const [password, setPassword] = useState("secret123");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const auth =
        mode === "register"
          ? await registerUser(username, email, password)
          : await loginUser(account, password);
      localStorage.setItem("pla_token", auth.access_token);
      localStorage.setItem("pla_user", JSON.stringify(auth.user));
      onAuthenticated(auth);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "认证失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-hero-panel">
        <div className="auth-brand-row">
          <span className="brand-mark">知行</span>
          <div>
            <strong>知行学习伙伴</strong>
            <span>Zhixing Learning Companion · 多智能体个性化学习引擎</span>
          </div>
        </div>
        <div>
          <h1>把课程资料变成会看、会说、会因材施教的 AI 学习伙伴</h1>
          <p>对话构建 14 维学生画像，多智能体协作生成可溯源的学习资源；学到哪、卡在哪、下一步学什么，系统都替你安排好。</p>
        </div>
        <div className="auth-process-list">
          {processStages.map((stage, index) => {
            const Icon = stage.icon;
            return (
              <article className="auth-process-item" key={stage.title}>
                <span>{index + 1}</span>
                <Icon size={18} />
                <div>
                  <strong>{stage.title}</strong>
                  <small>{stage.description}</small>
                </div>
                <span className={`status-chip ${stage.statusClass}`}>{stage.status}</span>
              </article>
            );
          })}
        </div>
      </section>

      <form className="auth-card" onSubmit={submit}>
        <div>
          <span className="form-eyebrow">Account Gateway</span>
          <h2>进入学习空间</h2>
          <p>使用账号保存画像、课程知识库和学习记录。</p>
        </div>
        <div className="auth-tabs">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")} type="button">登录</button>
          <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")} type="button">注册</button>
        </div>
        {mode === "register" ? (
          <>
            <label>
              用户名
              <input id="register-username" name="username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} />
            </label>
            <label>
              邮箱
              <input id="register-email" name="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} type="email" />
            </label>
          </>
        ) : (
          <label>
            用户名或邮箱
            <input id="login-account" name="account" autoComplete="username" value={account} onChange={(event) => setAccount(event.target.value)} />
          </label>
        )}
        <label>
          密码
          <input id="auth-password" name="password" autoComplete={mode === "register" ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} type="password" />
        </label>
        {error ? <div className="error">{error}</div> : null}
        <button className="primary-action" disabled={loading} type="submit">
          {mode === "register" ? <UserPlus size={17} /> : <LogIn size={17} />}
          {loading ? "处理中" : mode === "register" ? "创建新学生账号" : "登录并继续"}
        </button>
        <button
          className="secondary-action full-width-action"
          onClick={() => setMode(mode === "register" ? "login" : "register")}
          type="button"
        >
          {mode === "register" ? "已有账号，返回登录" : "创建新学生账号"}
        </button>
        <div className="tag-row auth-trust-row">
          <span className="tag">JWT 安全会话</span>
          <span className="tag">MySQL 持久画像</span>
        </div>
      </form>
    </main>
  );
}
