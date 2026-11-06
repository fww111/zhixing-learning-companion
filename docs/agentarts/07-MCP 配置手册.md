# 07 MCP 配置手册（单端口）

> 目标：把聚合了 17 个工具的 MCP Server（单容器、单端口）部署到公网可达环境，并在 AgentArts「MCP → 自定义接入」中完成注册、调试与真实工具调用。
>
> 配套文件：`docker-compose.yml`（`mcp` 服务）、`apps/mcp/Dockerfile`、`apps/mcp/.env.mcp.example`；接口契约见 `docs/agentarts/03-MCP服务接口契约.md`，运行时部署契约见 `06-技术核查与打磨报告.md`。

## 1. 架构与端口

AgentArts 运行时一个容器只暴露一个端口、只对一个端口探活；平台「自定义接入」也只需登记一个 URL。因此采用**统一单端口入口**：

| 项 | 值 |
| --- | --- |
| 入口 | `mcp_servers.server:app`（`FastMCP("zhixing-learning-mcp")`，`stateless_http=True`） |
| 端点 | `POST /mcp`（JSON-RPC 2.0）+ `GET /ping`（健康检查） |
| 工具 | 17 个 = profile 8 + graph 4 + assessment 5（契约见 03 文档 §1–§3） |
| 端口 | 容器内固定 `8080`；宿主机映射默认 `8080`，可用 `.env` 的 `MCP_PORT` 改 |
| 鉴权 | `MCP_AUTH_MODE=local` + `MCP_ACCESS_TOKEN`（独立部署默认）；接入运行时网关时用 `platform` |

工具分组与数据依赖：

| 分组 | 工具数 | 职责 | 数据依赖 |
| --- | --- | --- | --- |
| profile | 8 | 画像持久化、访谈对话记录、画像随学随新事件 | 关系库（MySQL，联调可 sqlite） |
| graph | 4 | 知识图谱约束、原文证据回表、关键词检索兜底 | 关系库 + **Neo4j（必须）** |
| assessment | 5 | 综合评估、掌握度、学习路径规划、错题归档 | 关系库（+ Neo4j 间接，路径规划依赖图谱） |

所有工具都要求 `user_id + course_id`，服务端校验课程归属，防止跨用户/跨课程读写。

## 2. 前置准备

### 2.1 华为云 ECS（方案 a，大赛提供云资源/代金券时优先）

- 规格建议：2 vCPU / 4 GB 内存以上，系统盘 ≥ 40 GB，Ubuntu 22.04 / Debian 12。
- 安装 Docker 与 Compose 插件：

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # 重新登录后生效
docker --version && docker compose version
```

- 将仓库代码上传到 ECS（git clone 或 scp 打包上传），进入仓库根目录。

### 2.2 本地/内网机器（方案 b）

- 已安装 Docker Engine + Compose 插件；隧道客户端（cloudflared 或 frp）可联网。

## 3. 数据库布局与环境变量

容器不内置数据库，通过环境变量指向**外部的 MySQL / Neo4j**。在仓库根目录创建 `.env`（可参考 `apps/mcp/.env.mcp.example`，把所需键复制到根目录 `.env`；`docker compose` 会自动读取根目录 `.env` 做变量插值）。

| 变量 | 默认值（compose 内） | 说明 |
| --- | --- | --- |
| `MCP_DATABASE_URL` | `mysql+pymysql://root:123456@host.docker.internal:3306/softbei?charset=utf8mb4` | 云上部署改为 RDS/云数据库连接串；容器访问宿主机库用 `host.docker.internal` |
| `MCP_AUTO_INIT_DB` | `false` | `true` 时启动前自动建表（sqlite 联调或空库首启使用） |
| `MCP_PORT` | `8080` | 宿主机映射端口（容器内固定 8080） |
| `MCP_AUTH_MODE` | `local` | 独立部署用 `local`；接入 AgentArts 运行时网关改 `platform`（鉴权交给网关） |
| `MCP_ACCESS_TOKEN` | 空 | 见 §6；`local` 模式下设置后强制 Bearer 校验，留空则无鉴权 |
| `MCP_NEO4J_URI` | `bolt://host.docker.internal:7687` | 云上 Neo4j 改为其 bolt 地址；`http://host:7474` 会自动归一化为 bolt 7687 |
| `MCP_NEO4J_USER` / `MCP_NEO4J_PASSWORD` | `neo4j` / 空 | 生产环境必须设置强密码 |
| `MOCK_LLM` | `true` | 演示/联调用 mock LLM；接真实 Key 后改 `false` |
| `MCP_LOG_LEVEL` | `INFO` | 日志级别 |

### 3.1 云上 MySQL（推荐生产布局）

```text
MCP_DATABASE_URL=mysql+pymysql://<user>:<password>@<rds-host>:3306/softbei?charset=utf8mb4
MCP_NEO4J_URI=bolt://<neo4j-host>:7687
MCP_NEO4J_PASSWORD=<strong-password>
```

### 3.2 本机 MySQL 未启动：sqlite 联调 profile/assessment 工具

仅用于开发联调；graph 工具必须连 Neo4j，不能用 sqlite 替代。

```text
MCP_DATABASE_URL=sqlite:////data/mcp/mcp.db
MCP_AUTO_INIT_DB=true
```

`/data/mcp` 已在 compose 中挂载到宿主机 `./data/mcp`，sqlite 文件可持久化。此时 profile / assessment 工具可独立联调；graph 工具在 Neo4j 未就绪时调用会返回 `graph_missing`，属预期行为。

## 4. 方案 a：ECS 部署（docker compose + 安全组）

### 4.1 构建并启动

```bash
# 仓库根目录
docker compose build mcp
docker compose up -d mcp
docker compose logs -f mcp      # 看到 starting ... stateless streamable-http at /mcp 即成功
curl http://127.0.0.1:8080/ping # {"status":"ok",...}
```

### 4.2 华为云安全组放行端口

在 ECS 控制台 → 实例对应安全组 → 入方向规则，放行：

| 协议 | 端口 | 源地址 | 用途 |
| --- | --- | --- | --- |
| TCP | 8080 | 0.0.0.0/0（联调期）/ AgentArts 出口网段（生产） | MCP Server（/mcp + /ping） |

同时确认 ECS 内部防火墙（如 ufw）放行或已关闭。宿主机映射端口改过（`MCP_PORT`）时按实际端口放行。

### 4.3 本机自测（ECS 上执行）

```bash
curl -i http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

返回 `200` 且 body 为 SSE/JSON-RPC 结果即 HTTP 层正常。再从本机浏览器或外部主机访问 `http://<EIP>:8080/mcp` 验证公网链路。

## 5. 方案 b：内网临时隧道（仅开发联调）

### 5.1 cloudflared（无需公网 IP，快速暴露单端口）

```bash
cloudflared tunnel --url http://localhost:8080
```

得到一个 `https://<random>.trycloudflare.com` 地址，AgentArts 中登记为 `https://<random>.trycloudflare.com/mcp`。免费临时地址每次重启会变，仅用于联调。

### 5.2 frp（有公网代理服务器时）

公网服务器 `frps.toml` 放行一个 `remotePort`；本机 `frpc.toml` 示例：

```toml
[[proxies]]
name = "zhixing-mcp"
type = "tcp"
localIP = "127.0.0.1"
localPort = 8080
remotePort = 8080
```

启动 `frpc -c frpc.toml` 后，以 `http://<frp-server>:8080/mcp` 登记。

## 6. 鉴权：MCP_AUTH_MODE 与 MCP_ACCESS_TOKEN

- `local`（compose 默认）：`/mcp` 要求 `Authorization: Bearer <MCP_ACCESS_TOKEN>`；`/ping` 恒为公开（健康探测不受影响）。**token 留空时服务无鉴权**（启动日志有 warning），仅限安全组限制源地址的联调期，尽快设置 token 或切白名单。
- `platform`：不做本地 Bearer 校验，鉴权交给 AgentArts 运行时网关（平台注入自己的 API Key）。
- `none`：显式关闭本地鉴权。

启用步骤：根目录 `.env` 设置 `MCP_ACCESS_TOKEN=<长随机串>`，`docker compose up -d mcp` 重建生效；AgentArts 接入配置中添加 Header `Authorization: Bearer <同一 token>`。验证：不带 Header 请求应返回 `401` 与 `unauthorized`；携带正确 Bearer 后正常。

## 7. AgentArts 注册服务

进入 AgentArts 控制台 →「MCP → 自定义接入 → 新建接入」：

| 名称 | 传输协议 | URL | 自定义 Header |
| --- | --- | --- | --- |
| zhixing-learning-mcp | streamableHttp | `http://<EIP或域名>:8080/mcp` | 启用 token 时加 `Authorization` |

保存后点击平台提供的「测试/调试」：

1. 连通性检查通过，状态显示**已设置**；
2. 工具列表能拉取到 **17 个工具**（见契约文档 §1–§3）；
3. 在调试面板逐个执行工具，确认参数 Schema 与文档一致。

## 8. 真实工具调用验收

### 8.1 get_student_profile（profile 组）

参数：

```json
{ "user_id": 1, "course_id": 1 }
```

期望：`ok: true`；画像已存在时 `exists: true` 且 `profile` 为 14 维画像对象；不存在时 `exists: false, profile: null`（不报错）。在平台「起始/运行记录」中可看到该次调用的入参与返回。

命令行等价验证：

```bash
curl -s http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_student_profile","arguments":{"user_id":1,"course_id":1}}}'
```

### 8.2 get_knowledge_evidence（graph 组，核心验收项）

参数：

```json
{ "user_id": 1, "course_id": 1, "node_id": "py-1-1", "limit": 6 }
```

期望：`ok: true`，`evidence` 数组中每项含 `chunk_id / material_id / heading / source_locator / content / token_count`，**`content` 为课程教材原文**（优先按节点 `source_chunk_ids` 回表，无绑定时按节点名 LIKE 兜底）。工作流节点实际调用成功且返回非空原文证据，即满足验收标准。

在 AgentArts 工作流中把该节点串入资源生成/辅导流程，下游节点应能直接消费 `evidence[].content`。

## 9. 故障排查

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 平台连接超时 | 安全组/防火墙未放行；隧道断开 | 检查安全组入方向、ufw、隧道状态；外部 telnet/curl 验证端口 |
| 401 unauthorized | `local` 模式启用了 token 但平台未配 Header / 不一致 | 核对 `Authorization: Bearer <token>` 与 `.env` 完全一致；或临时改 `MCP_AUTH_MODE=none` 定位 |
| `course_not_found` | user_id/course_id 不匹配或课程非该用户所有 | 先在业务库确认课程归属，使用平台上下文中的真实 ID |
| `graph_missing` | Neo4j 不可达或该课程未建图 | 检查 `MCP_NEO4J_*`；先在主应用完成图谱构建；graph 工具不支持 sqlite 替代 |
| `storage_error` / 连接拒绝 | 数据库地址错误或未对容器网段放行 | 宿主机库用 `host.docker.internal`；RDS 白名单加 ECS 出口 IP |
| sqlite 下报表不存在 | 未开自动建表 | `.env` 设 `MCP_AUTO_INIT_DB=true` 后重启容器 |
| 工具列表为空 | 镜像构建上下文错误，代码未拷入 | 确认在仓库根目录执行 `docker compose build mcp` |

## 10. 验收清单

- [ ] `docker compose up -d mcp` 正常，`GET /ping` 返回 ok，`/mcp` 响应 initialize；
- [ ] 安全组（方案 a）或隧道（方案 b）使 8080 端口公网可达；
- [ ] MCP 在 AgentArts「自定义接入」中状态为**已设置**，工具列表 17 个完整；
- [ ] 平台工作流节点实际调用 `get_student_profile`，运行记录可见入参与返回；
- [ ] 平台工作流节点实际调用 `get_knowledge_evidence`，返回非空课程原文证据；
- [ ] 启用 token 时 401/正常两条路径均验证；不启用时安全组已限制源地址。

## 11. Windows Docker Desktop 注意事项与实测记录

### 11.1 挂载与路径

- 容器内挂载点是 `/data`（宿主机 `./data/mcp`），sqlite 连接串应为 `sqlite:////data/xxx.db`（四个斜杠 + 绝对路径），多写一层 `/data/mcp` 会报 `unable to open database file`。
- 容器运行期间，宿主机上的 sqlite 文件可能因挂载缓存显示为 0 字节，容器停止后才同步最终大小；这是 Docker Desktop 挂载缓存行为，不代表数据丢失。需要在容器运行期写种子数据时，用 `docker exec` 在容器内执行（容器内 venv 位于 `/build/apps/mcp/.venv`），不要依赖宿主机侧直接写文件。

### 11.2 实测记录（本地 Docker，sqlite / MySQL 联调）

以下记录在**三进程旧架构（8100/8101/8102）**下取得；架构已统一为单端口聚合服务，鉴权与建表逻辑不变，结论仍然适用，建议按 §4/§10 在当前镜像上复跑一遍。

| 验证项 | 结果 |
| --- | --- |
| `docker compose build mcp` / `up -d mcp` | 镜像构建成功，容器稳定运行 |
| initialize + tools/list | 工具数与契约一致（8 / 4 / 5，聚合后共 17） |
| `get_student_profile` / `save_student_profile` | 调用成功，画像持久化，completion_score 正常计算 |
| Token 鉴权 | 无 Header / 错误 token 返回 401；正确 Bearer 返回 200 |
| Neo4j 缺失时 graph 工具 | 优雅返回 `graph_missing`，不抛未处理异常 |

平台侧剩余动作：按 §7 在 AgentArts 完成接入注册（状态显示已设置），并按 §8 在工作流中实调 `get_knowledge_evidence` 确认返回课程原文。

## 12. 本机 MySQL 接入实测记录（2026-11-02）

**背景**：验收核心 `get_knowledge_evidence` 需要课程原文数据，原文存于关系库 `knowledge_chunks`；graph 工具依赖 Neo4j，无法用 sqlite 替代。因此本机打通 MySQL 是必要前置。

**凭据**：使用本机已有的 MySQL 账号（此处不记录明文凭据，凭据只放在 git 忽略的根目录 `.env` 中）。仓库历史默认密码均被拒（1045）时，用自己设置的账号密码即可。

**库与表**：本机 MySQL 原无项目库，已创建 `softbei`（utf8mb4）。容器 `MCP_AUTO_INIT_DB=true` 在 MySQL 上自动建表 16 张：`users/courses/student_profiles/profile_interviews/profile_messages/learning_profile_events/learning_path_revisions/knowledge_chunks/course_materials/course_lesson_sessions/knowledge_node_masteries/graph_build_jobs/…`。

**种子数据现状**：`users` 有 `mcp_mysql_user`(id=3)；`courses` 有 `Python程序设计`(id=1)；`student_profiles` 已有 `student-e106be83`(completion 0.85)。`knowledge_chunks/course_materials/graph_build_jobs` 均为 0 行。

**.env（仓库根，git 忽略）模板**：
```env
MCP_DATABASE_URL=mysql+pymysql://<db_user>:<db_password>@host.docker.internal:3306/softbei?charset=utf8mb4
MCP_AUTO_INIT_DB=true
MCP_NEO4J_URI=bolt://host.docker.internal:7687
MCP_NEO4J_USER=neo4j
MCP_NEO4J_PASSWORD=
# MCP_ACCESS_TOKEN=...   # 平台支持自定义 Header 时才启用
```
容器访问宿主机库必须用 `host.docker.internal`（见 §3）。

**实测结果**：profile 工具调用走 MySQL 全部通过——`get_student_profile` exists=true → `save_student_profile`（completion 0.85）→ `get_student_profile` 一致。

**历史坑：三进程并发建表竞态（已随单端口架构消除）**。旧三进程架构下三个 uvicorn 同时执行 `MCP_AUTO_INIT_DB` 建表，MySQL 下并发 `create_all` 触发 `1050 Table already exists`。现统一为单容器单进程，`init_db()` 仅执行一次，该竞态不再存在；如仍遇到（例如双副本部署），先重启容器即可。

**坑：MySQL 严格模式缺默认值**。手工 INSERT 课程需补 `description/created_at/updated_at` 等 NOT NULL 字段；直接用项目 ORM（`User`/`Course`）插入最稳妥。

**验证脚本**：`apps/mcp/scripts/mysql_smoke.py`（工具三连调用；可用 `MCP_SMOKE_URL` 覆盖目标地址）。

**剩余缺口**：`knowledge_chunks/course_materials` 为 0 行，graph 工具对 course 1 返回 `graph_missing`（无图谱无原文）；Neo4j 未启动（`MCP_NEO4J_URI` 默认指向宿主机 7687）。`get_knowledge_evidence` 返回原文需先灌入课程数据 + 建图谱（见 §8 验收）。
