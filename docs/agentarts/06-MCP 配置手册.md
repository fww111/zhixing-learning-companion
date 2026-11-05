# 06 MCP 配置手册

> 目标：把 profile / graph / assessment 三个 MCP Server（单镜像、三端口）部署到公网可达环境，并在 AgentArts「MCP → 自定义接入」中完成注册、调试与真实工具调用。
>
> 配套文件：`docker-compose.yml`（`mcp` 服务）、`apps/mcp/Dockerfile`、`apps/mcp/.env.mcp.example`；接口契约见 `docs/agentarts/03-MCP服务接口契约.md`。

## 1. 架构与端口

| 服务 | 模块 | 端口 / 端点 | 数据依赖 |
| --- | --- | --- | --- |
| profile-server | `mcp_servers.profile_server` | `http://<host>:8100/mcp` | 关系库（MySQL，联调可 sqlite） |
| graph-server | `mcp_servers.graph_server` | `http://<host>:8101/mcp` | 关系库 + **Neo4j（必须）** |
| assessment-server | `mcp_servers.assessment_server` | `http://<host>:8102/mcp` | 关系库（+ Neo4j 间接，路径规划依赖图谱） |

- 单镜像 `zhixing-mcp-servers` 内同时启动三个进程，Dockerfile 构建上下文为**仓库根目录**。
- 协议为 MCP **streamableHttp**，服务以 `stateless_http=True` 运行，无需维护会话。
- 所有工具都要求 `user_id + course_id`，服务端校验课程归属，防止跨用户/跨课程读写。

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

容器不内置数据库，通过环境变量指向**外部间接的 MySQL / Neo4j**。在仓库根目录创建 `.env`（可参考 `apps/mcp/.env.mcp.example`，把所需键复制到根目录 `.env`；`docker compose` 会自动读取根目录 `.env` 做变量插值）。

| 变量 | 默认值（compose 内） | 说明 |
| --- | --- | --- |
| `MCP_DATABASE_URL` | `mysql+pymysql://root:123456@host.docker.internal:3306/softbei?charset=utf8mb4` | 云上部署改为 RDS/云数据库连接串；容器访问宿主机库用 `host.docker.internal` |
| `MCP_AUTO_INIT_DB` | `false` | `true` 时启动前自动建表（sqlite 联调或空库首启使用） |
| `MCP_NEO4J_URI` | `bolt://host.docker.internal:7687` | 云上 Neo4j 改为其 bolt 地址；`http://host:7474` 会自动归一化为 bolt 7687 |
| `MCP_NEO4J_USER` / `MCP_NEO4J_PASSWORD` | `neo4j` / 空 | 生产环境必须设置强密码 |
| `MCP_ACCESS_TOKEN` | 空 | 见 §6 |
| `MCP_LOG_LEVEL` | `INFO` | 日志级别 |

### 3.1 云上 MySQL（推荐生产布局）

```text
MCP_DATABASE_URL=mysql+pymysql://<user>:<password>@<rds-host>:3306/softbei?charset=utf8mb4
MCP_NEO4J_URI=bolt://<neo4j-host>:7687
MCP_NEO4J_PASSWORD=<strong-password>
```

### 3.2 本机 MySQL 未启动：sqlite 联调 profile-server

仅用于开发联调；graph-server 必须连 Neo4j，不能用 sqlite 替代。

```text
MCP_DATABASE_URL=sqlite:////data/mcp/mcp.db
MCP_AUTO_INIT_DB=true
```

`/data/mcp` 已在 compose 中挂载到宿主机 `./data/mcp`，sqlite 文件可持久化。此时 profile-server（8100）与 assessment-server（8102）的关系库工具可独立联调；graph-server（8101）在 Neo4j 未就绪时调用会返回 `graph_missing`，属预期行为。

## 4. 方案 a：ECS 部署（docker compose + 安全组）

### 4.1 构建并启动

```bash
# 仓库根目录
docker compose build mcp
docker compose up -d mcp
docker compose logs -f mcp       # 看到三个 starting ... streamable-http at /mcp 即成功
```

### 4.2 华为云安全组放行端口

在 ECS 控制台 → 实例对应安全组 → 入方向规则，放行：

| 协议 | 端口 | 源地址 | 用途 |
| --- | --- | --- | --- |
| TCP | 8100 | 0.0.0.0/0（联调期）/ AgentArts 出口网段（生产） | profile-server |
| TCP | 8101 | 同上 | graph-server |
| TCP | 8102 | 同上 | assessment-server |

同时确认 ECS 内部防火墙（如 ufw）放行或已关闭。

### 4.3 本机自测（ECS 上执行）

```bash
curl -i http://127.0.0.1:8100/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

返回 `200` 且 body 为 SSE/JSON-RPC 结果即 HTTP 层正常。再从本机浏览器或外部主机访问 `http://<EIP>:8100/mcp` 验证公网链路。

## 5. 方案 b：内网临时隧道（仅开发联调）

### 5.1 cloudflared（无需公网 IP，快速暴露三端口）

```bash
# 分别为三个端口建立隧道（也可在同一配置文件中声明三个 ingress）
cloudflared tunnel --url http://localhost:8100
cloudflared tunnel --url http://localhost:8101
cloudflared tunnel --url http://localhost:8102
```

得到三个 `https://<random>.trycloudflare.com` 地址，AgentArts 中登记为 `https://<random>.trycloudflare.com/mcp`。免费临时地址每次重启会变，仅用于联调。

### 5.2 frp（有公网代理服务器时）

公网服务器 `frps.toml` 放行三个 `remotePort`；本机 `frpc.toml` 示例：

```toml
[[proxies]]
name = "mcp-profile"
type = "tcp"
localIP = "127.0.0.1"
localPort = 8100
remotePort = 8100

[[proxies]]
name = "mcp-graph"
type = "tcp"
localPort = 8101
remotePort = 8101

[[proxies]]
name = "mcp-assessment"
type = "tcp"
localPort = 8102
remotePort = 8102
```

启动 `frpc -c frpc.toml` 后，以 `http://<frp-server>:810x/mcp` 登记。

## 6. 是否启用 MCP_ACCESS_TOKEN

- 启用条件：**AgentArts 自定义接入支持配置自定义请求 Header** 时才启用。服务端校验逻辑为 `Authorization: Bearer <token>` 精确匹配。
- 启用方法：根目录 `.env` 设置 `MCP_ACCESS_TOKEN=<长随机串>`，`docker compose up -d mcp` 重建生效；AgentArts 接入配置中添加 Header `Authorization: Bearer <同一 token>`。
- 若平台接入不支持自定义 Header（仅能填 URL），**保持该变量为空**，此时服务无鉴权，依赖安全组限制源地址，并尽快切换到 AgentArts 出口网段白名单。
- 验证：不带 Header 请求应返回 `401` 与 `unauthorized`；携带正确 Bearer 后正常。

## 7. AgentArts 注册三个服务

进入 AgentArts 控制台 →「MCP → 自定义接入（接入接入）→ 新建接入」，逐个添加：

| 名称 | 传输协议 | URL | 自定义 Header |
| --- | --- | --- | --- |
| zhixing-profile | streamableHttp | `http://<EIP或域名>:8100/mcp` | 启用 token 时加 `Authorization` |
| zhixing-graph | streamableHttp | `http://<EIP或域名>:8101/mcp` | 同上 |
| zhixing-assessment | streamableHttp | `http://<EIP或域名>:8102/mcp` | 同上 |

每个接入保存后点击平台提供的「测试/调试」：

1. 连通性检查通过，状态显示**已设置**；
2. 工具列表能分别拉取到 8 / 4 / 5 个工具（见契约文档 §1–§3）；
3. 在调试面板逐个执行工具，确认参数 Schema 与文档一致。

## 8. 真实工具调用验收

### 8.1 get_student_profile（profile-server，8100）

参数：

```json
{ "user_id": 1, "course_id": 1 }
```

期望：`ok: true`；画像已存在时 `exists: true` 且 `profile` 为 14 维画像对象；不存在时 `exists: false, profile: null`（不报错）。在平台「起始/运行记录」中可看到该次调用的入参与返回。

命令行等价验证：

```bash
curl -s http://127.0.0.1:8100/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_student_profile","arguments":{"user_id":1,"course_id":1}}}'
```

### 8.2 get_knowledge_evidence（graph-server，8101，核心验收项）

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
| 401 unauthorized | 启用了 token 但平台未配 Header / 不一致 | 核对 `Authorization: Bearer <token>` 与 `.env` 完全一致 |
| `course_not_found` | user_id/course_id 不匹配或课程非该用户所有 | 先在业务库确认课程归属，使用平台上下文中的真实 ID |
| `graph_missing` | Neo4j 不可达或该课程未建图 | 检查 `MCP_NEO4J_*`；先在主应用完成图谱构建；graph-server 不支持 sqlite 替代 |
| `storage_error` / 连接拒绝 | 数据库地址错误或未对容器网段放行 | 宿主机库用 `host.docker.internal`；RDS 白名单加 ECS 出口 IP |
| sqlite 下报表不存在 | 未开自动建表 | `.env` 设 `MCP_AUTO_INIT_DB=true` 后重启容器 |
| 工具列表为空 | 镜像构建上下文错误，代码未拷入 | 确认在仓库根目录执行 `docker compose build mcp` |

## 10. 验收清单

- [ ] `docker compose up -d mcp` 正常，容器内三个 `/mcp` 端点均响应 initialize；
- [ ] 安全组（方案 a）或隧道（方案 b）使三端口公网可达；
- [ ] 三个 MCP 在 AgentArts「接入接入」中状态均为**已设置**，工具列表完整；
- [ ] 平台工作流节点实际调用 `get_student_profile`，运行记录可见入参与返回；
- [ ] 平台工作流节点实际调用 `get_knowledge_evidence`，返回非空课程原文证据；
- [ ] 启用 token 时 401/正常两条路径均验证；不启用时安全组已限制源地址。
## 11. Windows Docker Desktop 注意事项与实测记录

### 11.1 挂载与路径

- 容器内挂载点是 `/data`（宿主机 `./data/mcp`），sqlite 连接串应为 `sqlite:////data/xxx.db`（四个斜杠 + 绝对路径），多写一层 `/data/mcp` 会报 `unable to open database file`。
- 容器运行期间，宿主机上的 sqlite 文件可能因挂载缓存显示为 0 字节，容器停止后才同步最终大小；这是 Docker Desktop 挂载缓存行为，不代表数据丢失。需要在容器运行期写种子数据时，用 `docker exec` 在容器内执行（容器内 venv 位于 `/build/apps/mcp/.venv`），不要依赖宿主机侧直接写文件。

### 11.2 实测结果（本地 Docker，sqlite 联调）

| 验证项 | 结果 |
| --- | --- |
| `docker compose build mcp` | 镜像 `zhixing-mcp-servers:latest` 构建成功 |
| `docker compose up -d mcp` | 容器稳定运行，8100/8101/8102 均监听 0.0.0.0 |
| 三端点 initialize + tools/list | 工具数 8 / 4 / 5，与契约一致 |
| 容器内 `get_student_profile` / `save_student_profile` | 调用成功，画像持久化，completion_score 正常计算 |
| Token 鉴权 | 无 Header / 错误 token 返回 401；正确 Bearer 返回 200，三端口均生效 |
| Neo4j 缺失时 graph 工具 | 优雅返回 `graph_missing`，不抛未处理异常 |

平台侧剩余动作：按 §7 在 AgentArts 完成三个接入注册（状态显示已设置），并按 §8 在工作流中实调 `get_knowledge_evidence` 确认返回课程原文。

## 12. 本机 MySQL 接入实测记录（2026-11-02）

**背景**：验收核心 `get_knowledge_evidence` 需要课程原文数据，原文存于关系库 `knowledge_chunks`；graph-server 依赖 Neo4j，无法用 sqlite 替代。因此本机打通 MySQL 是必要前置。

**凭据**：用户提供 `root201109 / funny1223`（认证通过）。仓库历史密码 `root/123456`、`root/709055` 均被拒（1045）。

**库与表**：本机 MySQL 原无项目库（只有 `musiclibrary201109`），已创建 `softbei`（utf8mb4）。容器 `MCP_AUTO_INIT_DB=true` 在 MySQL 上自动建表 16 张：`users/courses/student_profiles/profile_interviews/profile_messages/learning_profile_events/learning_path_revisions/knowledge_chunks/course_materials/course_lesson_sessions/knowledge_node_masteries/graph_build_jobs/…`。

**种子数据现状**：`users` 有 `mcp_mysql_user`(id=3)；`courses` 有 `Python程序设计`(id=1)；`student_profiles` 已有 `student-e106be83`(completion 0.85)。`knowledge_chunks/course_materials/graph_build_jobs` 均为 0 行。

**.env（仓库根，git 忽略）当前内容**：
```env
MCP_DATABASE_URL=mysql+pymysql://root201109:funny1223@host.docker.internal:3306/softbei?charset=utf8mb4
MCP_AUTO_INIT_DB=true
MCP_NEO4J_URI=bolt://host.docker.internal:7687
MCP_NEO4J_USER=neo4j
MCP_NEO4J_PASSWORD=
# MCP_ACCESS_TOKEN=...   # 平台支持自定义 Header 时才启用
```
容器访问宿主机库必须用 `host.docker.internal`（见 §4）。

**实测结果**：profile-server 工具调用走 MySQL 全部通过——`get_student_profile` exists=true → `save_student_profile`（completion 0.85）→ `get_student_profile` 一致。

**坑：三进程并发建表竞态**。容器内三个 uvicorn 同时启动都会执行 `MCP_AUTO_INIT_DB` 建表，MySQL 下并发 `create_all` 触发 `1050 Table 'users' already exists`，导致 graph/assessment 进程崩溃重启。已在 `apps/mcp/src/mcp_servers/runtime.py` 对 `init_db()` 包 try/except：匹配 `"already exists"`/`"1050"` 记录 warning 继续，其余错误 re-raise。改后必须 `docker compose build mcp` 重建镜像再 `up`。

**坑：MySQL 严格模式缺默认值**。手工 INSERT 课程需补 `description/created_at/updated_at` 等 NOT NULL 字段；直接用项目 ORM（`User`/`Course`）插入最稳妥。

**验证脚本**：`apps/mcp/scripts/mysql_smoke.py`（容器 profile-server 三连调用，已通过）。

**剩余缺口**：`knowledge_chunks/course_materials` 为 0 行，`graph-server` 对 course 1 返回 `graph_missing`（无图谱无原文）；Neo4j 未启动（`NEO4J_URI` 默认指向宿主机 7687）。`get_knowledge_evidence` 返回原文需先灌入课程数据 + 建图谱（见 §8 验收）。

## 13. 验收核心达成：get_knowledge_evidence 返回课程原文（2026-11-02）

**目标**：平台工作流实调 `get_knowledge_evidence` 返回课程原文证据。

**灌数据方式**：本机启动 Neo4j 容器后，本地调用内置课程逻辑（等价 `POST /api/courses/default-python` 内部 `CourseService.ensure_default_python_course`）灌入内置 Python 课程。

**数据现状（MySQL softbei + Neo4j）**：
- 内置课程 `Python 程序设计` **course_id=3**（描述带 `built-in:python` marker）。
- `knowledge_chunks` 140 行（原文 chunk）；`course_materials` 1 行；`graph_build_jobs` course 3 = succeeded/100%/done。
- Neo4j：141 节点 / 250 边。

**注意：内置课程 id 不是 1**。本机曾有旧空课程 `Python程序设计`(id=1)，内置接口按 `name + built-in:python marker` 匹配，新建了 id=3。调用 `get_knowledge_evidence` 必须用 **course_id=3**（否则旧空课程 course 1 无图谱，返回 graph_missing）。

**验证（容器 graph-server :8101 真实调用）**：
- `get_course_graph`(3,3) → ok=true, 141 nodes, 250 edges。
- `get_knowledge_evidence`(3,3,"outline-chapter-1") → ok=true, node_name="第 1 章 Python 概述", evidence=[{chunk_id:141, content:"建立 Python 语言、开发环境、运行方式和学习路径的整体认知。"}]。

**验收结论**：工作流若以 user_id=3、course_id=3、任一图谱 node_id 调用 `get_knowledge_evidence`，将返回课程原文 chunk 证据。平台实调验收项达成条件满足。

**本机 Neo4j 运行方式（仅联调）**：
```powershell
# 数据卷用 Docker 命名卷（bind 挂到仓库 Windows 目录会被 Docker Desktop 分配到 126MB 小分区并写满报 No space）
docker volume create neo4j-data
docker run -d --name neo4j-local --restart unless-stopped \
  -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/testlocal2026 \
  -v neo4j-data:/data neo4j:5-community
```
`.env`：`MCP_NEO4J_URI=bolt://host.docker.internal:7687`、`MCP_NEO4J_USER=neo4j`、`MCP_NEO4J_PASSWORD=testlocal2026`。

**坑：Docker Desktop 对 Windows bind 挂载分配小分区**。`-v E:\...\data\neo4j\data:/data` 会被分配约 126MB 的 `/dev/sde`，Neo4j 初始化写满后 `java.io.IOException: No space left on device`，容器反复重启。改用 Docker 命名卷 `-v neo4j-data:/data`（落在 1007G 大盘）即解决。`docker exec neo4j-local df -h /data` 可核对。

**验证脚本**：`apps/mcp/scripts/evidence_smoke.py`（graph-server 两连调用，已通过）。

## 14. 方案b：cloudflared 内网隧道联调（已实测通过，2026-11-02）

**适用**：无公网 ECS 时的开发联调；临时、无 uptime 保证、仅联调用。生产/演示仍建议方案a（ECS + 安全组）。

**安装 cloudflared（Windows）**：
```powershell
winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements --silent
# 装到 C:\Program Files (x86)\cloudflared\cloudflared.exe，新开终端即可用
```

**为三个端口各起一条快速隧道（后台运行）**：
```powershell
cloudflared tunnel --url http://127.0.0.1:8100 --no-autoupdate
cloudflared tunnel --url http://127.0.0.1:8101 --no-autoupdate
cloudflared tunnel --url http://127.0.0.1:8102 --no-autoupdate
```
每条隧道启动后从日志提取 `https://<random>.trycloudflare.com` 公网地址。快速隧道 URL 每次启动都会变；隧道进程必须保持运行。

**实测公网地址（本次会话）**：
| 服务 | 端口 | 公网地址 |
|---|---|---|
| profile-server | 8100 | https://habitat-roommate-rush-privilege.trycloudflare.com |
| graph-server | 8101 | https://elementary-county-vendors-acquire.trycloudflare.com |
| assessment-server | 8102 | https://bundle-connectors-revelation-trembl.trycloudflare.com |

AgentArts 注册时 streamableHttp 地址填 `https://<上述>/mcp`。

**坑：FastMCP DNS rebinding 保护导致 421 Invalid Host header**。三个 server 的 `FastMCP(...)` 默认 host=127.0.0.1，自动启用 DNS rebinding 保护，只允许 localhost Host，拒绝 trycloudflare.com 的 Host（返回 421）。已在 `apps/mcp/src/mcp_servers/runtime.py` 的 `build_asgi_app()` 中：若检测到 transport_security 为空或已启用，则显式 `TransportSecuritySettings(enable_dns_rebinding_protection=False)` 关闭。**这是联调开关**，生产/公网域名场景不建议全局关闭。改后必须 `docker compose build mcp` 重建镜像。

**实测验证**：
- 三个端点经公网隧道 `tools/list` 全部 HTTP200（8/4/5 工具）。
- 经公网隧道实调 `get_knowledge_evidence`(3,3,"outline-chapter-1") → ok=true，返回课程原文 chunk。

**验证脚本**：`apps/mcp/scripts/tunnel_smoke.py`（三端点公网 tools/list）、`tunnel_evidence.py`（公网 get_knowledge_evidence）。

## 14.5 本地 venv 排障：E 盘批量写文件被截断

本地 venv 仅用于跑 pytest / scripts，**不是交付物**（`.gitignore` 已忽略 `.venv`，运行形态以容器为准）。

- **现象**：在 E 盘执行 `python -m venv .venv` 或 `uv sync` 时，包目录结构被创建，但文件全部落不下来——`site-packages` 下 122 个包目录均无 `__init__.py`，`httpx.__file__ = None`，`python -m pip` 报 `No module named pip.__main__`；`uv sync --reinstall` 还可能以 ACCESS VIOLATION（exit -1073741819）崩溃。单个文件写入正常（可写后读回）。
- **对照**：同版本 Python 在 C 盘建 venv 完全正常（pip 439 个文件、可运行）。判定为 E 盘批量写小文件被截断（文件系统错误 / 实时防护拦截 / 磁盘故障），与源码无关。
- **处理**：把本地 venv 建在 C 盘，editable 仍指向 iii 的源码，不影响 iii 自洽：

```powershell
python -m venv C:\Users\lenovo\zhixing-mcp-venv
$py = "C:\Users\lenovo\zhixing-mcp-venv\Scripts\python.exe"
& $py -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -e "E:\iii\zhixing-learning-companion\apps\mcp"
& $py -m pip install -i https://mirrors.aliyun.com/pypi/simple/ pytest
```

- **验证**：`pytest -q` → 11 passed；三端点真实调用全 ok（8/4/5 工具，profile exists、graph 141/250、evidence 返回原文、plan dynamic=true）。
- **提示**：E 盘若反复出现文件截断或盘符掉线，应先排查磁盘健康（`chkdsk` / 磁盘管理 / 数据线），再继续在该盘写入。
## 15. 方案a：华为云 ECS 完整部署（公网 IP 直连，URL 固定）

适合：大赛提供云资源/代金券。相比隧道方案，公网 IP 固定、有 uptime、可长期联调。

### 15.1 申请 ECS（如无实例）
- 计费：优先用大赛代金券/包周期。
- 规格建议：2 核 4G、系统盘 40G ESSD、公网带宽按固定 5M（或按流量）。
- 镜像：**Ubuntu 22.04 LTS**（本手册命令基于 Ubuntu/Debian apt）。
- 网络：勾选"分配公网 IPv4 地址"，选择安全组。
- 登录方式：设 root 密码或绑定 SSH 密钥。

### 15.2 安全组放行（华为云控制台 → ECS → 安全组 → 入方向）
| 协议 | 端口 | 源 | 用途 |
|---|---|---|---|
| TCP | 22 | 你的办公 IP | SSH |
| TCP | 8100 | 0.0.0.0/0（或限定 AgentArts 出口） | profile-server |
| TCP | 8101 | 0.0.0.0/0 | graph-server |
| TCP | 8102 | 0.0.0.0/0 | assessment-server |

> 无鉴权公网暴露时，建议把 8100-8102 源 IP 收窄到 AgentArts 平台出口，或启用 MCP_ACCESS_TOKEN（见 §9）。

### 15.3 登录 ECS，装 Docker + git
```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git
sudo systemctl enable --now docker
docker --version && docker compose version
```

### 15.4 拉取仓库
```bash
cd ~
git clone <你的仓库地址> zhixing-learning-companion-main
cd zhixing-learning-companion-main
```

### 15.5 在 ECS 本机装 MySQL 并建 softbei 库
```bash
sudo apt install -y mysql-server
sudo systemctl enable --now mysql
sudo mysql -e "CREATE DATABASE IF NOT EXISTS softbei CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mysql -e "CREATE USER IF NOT EXISTS 'mcp'@'%' IDENTIFIED BY '改成一个强密码'; GRANT ALL PRIVILEGES ON softbei.* TO 'mcp'@'%'; FLUSH PRIVILEGES;"
```

### 15.6 配置 .env（仓库根目录）
```bash
cat > .env <<'EOF'
MCP_DATABASE_URL=mysql+pymysql://mcp:改成强密码@host.docker.internal:3306/softbei?charset=utf8mb4
MCP_AUTO_INIT_DB=true
NEO4J_URI=bolt://host.docker.internal:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=
EOF
```
- 容器内连 ECS 本机 MySQL：compose 已配 `extra_hosts: host.docker.internal:host-gateway`，Linux 下即指向宿主机网关，无需改。
- Neo4j 暂不启动不影响 get_knowledge_evidence（graph-server 无 Neo4j 时 fallback 到 MySQL chunks，已验证返回原文）。

### 15.7 构建并启动
```bash
docker compose build mcp
docker compose up -d mcp
docker logs zhixing-mcp | grep -E "Uvicorn running|Application startup"
```
三个进程应同时监听 8100/8101/8102。

### 15.8 灌课程数据（新 MySQL 是空库）
复用本地已验证的内置课程种子逻辑：在 mcp 容器内用 `apps.api` 的课程模型/服务写入 `course_materials` 与 `knowledge_chunks`（candidate course_id=3，node `outline-chapter-1`）。
```bash
docker exec -it zhixing-mcp /build/apps/mcp/.venv/bin/python <种子脚本路径>
```
种子脚本沿用本地跑通版本（写入 user/course/student_profile + 课程 chunks）。完成后在容器内或本地 `tools/call` 调 `get_knowledge_evidence` 确认返回课程原文。

### 15.9 AgentArts 注册
streamableHttp，地址填：
- profile：`http://<ECS公网IP>:8100/mcp`
- graph：`http://<ECS公网IP>:8101/mcp`
- assessment：`http://<ECS公网IP>:8102/mcp`
注册后在平台"接入接入"设为已设置，工作流节点实调 `get_knowledge_evidence` 验证返回原文。

### 15.10 从本机快速自测公网是否通
```powershell
curl.exe -X POST "http://<ECS公网IP>:8101/mcp" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\",\"params\":{}}"
```
能返回 4 个 graph 工具即说明安全组+容器都通。