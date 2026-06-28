# 部署说明

## 1. 本地运行前置服务

本地完整链路需要以下服务：

- MySQL：业务数据库。
- Neo4j：课程知识图谱。
- Milvus：向量召回层。
- OpenMAIC：标准课堂生成和课堂前端。
- 可选 MinerU：PDF/PPT/PPTX 精准解析 API。

创建 MySQL 数据库：

```sql
CREATE DATABASE IF NOT EXISTS softbei DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Neo4j 浏览器地址通常为：

```text
http://127.0.0.1:7474/
```

后端连接使用 Bolt：

```text
NEO4J_URI=bolt://127.0.0.1:7687
```

Milvus 默认连接：

```text
MILVUS_URI=http://127.0.0.1:19530
```

如果 Milvus 未启动，材料解析后的 MySQL chunk 仍会保留，但材料状态可能变为 `index_failed`，需要启动 Milvus 后重建向量索引。

## 2. 环境变量

复制 `.env.example` 到仓库根目录 `.env`，只在本地 `.env` 写入真实密钥。

```text
MOCK_LLM=false
LLM_API_KEY=你的 DeepSeek Key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro
TUTOR_VISION_API_KEY=你的百炼或 DashScope Key
TUTOR_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
TUTOR_VISION_MODEL=qwen3.7-plus
DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/softbei?charset=utf8mb4
JWT_SECRET_KEY=换成足够长的随机字符串

MILVUS_URI=http://127.0.0.1:19530
MILVUS_TOKEN=
MILVUS_DB_NAME=

OPENMAIC_BASE_URL=http://127.0.0.1:3000

EMBEDDING_PROVIDER=local_bge
EMBEDDING_MODEL=D:/softbei/a3/data/models/embeddings/BAAI/bge-m3
EMBEDDING_DEVICE=cpu
EMBEDDING_CACHE_DIR=D:/softbei/a3/data/models/embeddings

MINERU_ENABLED=false
MINERU_API_TOKEN=

NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=你的本地 Neo4j 密码
```

`LLM_API_KEY`、`TUTOR_VISION_API_KEY`、`MINERU_API_TOKEN`、`NEO4J_PASSWORD`、`TTS_QWEN_API_KEY` 不要写入 README、测试文件或提交记录。`TUTOR_VISION_API_KEY` 也可通过 `QWEN_API_KEY` 或 `DASHSCOPE_API_KEY` 复用。

## 3. 后端

```powershell
conda activate a3
cd D:\softbei\a3\apps\api
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

后端启动时会通过 SQLAlchemy 创建业务表。上传目录、模型缓存和课堂生成结果都是本地运行产物，不提交 Git。

## 4. 前端

```powershell
cd D:\softbei\a3\apps\web
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5173
```

当前产品流程：

```text
/auth
 -> /courses
 -> /courses/:courseId/profile/interview
 -> /courses/:courseId/knowledge-base
 -> /courses/:courseId/graph
 -> /courses/:courseId/learning-path
 -> /courses/:courseId/knowledge/:nodeId
```

## 5. OpenMAIC

OpenMAIC 作为独立 Next.js 服务运行，默认地址：

```text
http://127.0.0.1:3000
```

FastAPI 会调用：

```text
OPENMAIC_BASE_URL/api/generate-classroom
```

提交课堂生成任务。OpenMAIC 返回 `queued` 或 `running` 时，前端通过本项目后端代理轮询：

```text
GET /api/resources/openmaic-jobs/{job_id}
```

拿到 `/classroom/{id}` 后，学习页嵌入 OpenMAIC 前端课堂。

### TTS 配置

当前默认课堂语音使用 OpenMAIC 侧配置的阿里云百炼 Qwen TTS。请在 `OpenMAIC-main/OpenMAIC-main/.env.local` 或 OpenMAIC 设置页配置百炼 Key、模型和发音人，例如 `Cherry`、`Ethan`、`Serena`。

VoxCPM2 不再作为默认课堂 TTS。FastAPI 后端保留 `POST /tts/upload` 作为 OpenMAIC 兼容的可选实验接口，但 CPU-only 或低内存机器不建议启用本地 VoxCPM2。

## 6. BGE-M3 本地模型

推荐模型目录：

```text
D:/softbei/a3/data/models/embeddings/BAAI/bge-m3
```

如果该目录已存在，`EMBEDDING_MODEL` 直接指向该路径即可。首次下载需要能访问 Hugging Face 或可用镜像；离线环境应提前手动下载模型到上述目录。

后端 `vector_service.py` 会在导入 `sentence_transformers` 前设置：

```text
HF_HOME=D:/softbei/a3/data/models/embeddings
SENTENCE_TRANSFORMERS_HOME=D:/softbei/a3/data/models/embeddings
```

因此通过后端接口触发向量化时，不需要额外手动设置这两个环境变量。

当前 `requirements.txt` 显式包含 `sentence-transformers`、`transformers` 和 `torch`。其中 `transformers`/`torch` 用于本地 BGE-M3 直接编码兜底路径，避免只依赖 `sentence-transformers` 的间接依赖解析。

## 7. MinerU 解析

启用 MinerU：

```text
MINERU_ENABLED=true
MINERU_API_TOKEN=你的 MinerU Token
```

如果 `MINERU_ENABLED=true` 但缺少 Token，材料解析应快速失败，避免几百页 PDF 静默落到本地 OCR 慢链路。

MinerU 失败后是否允许回退本地解析由以下变量控制：

```text
MINERU_FALLBACK_TO_LOCAL=false
```

## 8. 课程知识库长任务

课程材料链路：

```text
上传文件
 -> queued
 -> MinerU 或本地解析
 -> chunking
 -> MySQL chunk
 -> BGE-M3 embedding
 -> Milvus upsert
 -> parsed / index_failed / failed
```

当前队列是后端进程内 `ThreadPoolExecutor`。后端重启会丢失排队或运行中的任务，测试时需要重新上传、删除错误材料或重建索引。生产化建议迁移为 Redis/Celery/RQ。

## 9. 常见问题

### Milvus 连接失败

错误示例：

```text
Fail connecting to server on 127.0.0.1:19530
```

处理：

1. 确认 Milvus 服务已启动。
2. 确认 `.env` 中 `MILVUS_URI=http://127.0.0.1:19530`。
3. 若材料已 `index_failed`，启动 Milvus 后点击“重建向量索引”。

### Milvus Lite 路径写法错误

`pymilvus` 新版客户端期望 URI 是 HTTP 地址。如果配置成：

```text
MILVUS_URI=D:/softbei/a3/data/milvus/softbei_milvus_lite.db
```

可能出现 illegal uri。当前项目默认按 Milvus Server 地址配置。若要支持 Milvus Lite，需要在代码和配置中明确使用对应客户端模式，不能把本地 db 文件路径直接当 HTTP URI。

### OpenMAIC 课堂一直等待

检查：

1. `http://127.0.0.1:3000` 是否能打开。
2. `OPENMAIC_BASE_URL` 是否指向本机 OpenMAIC。
3. 浏览器请求 `GET /api/resources/openmaic-jobs/{job_id}` 返回内容。
4. OpenMAIC 是否返回了本机允许轮询的 `poll_url`。
5. OpenMAIC provider 和 Qwen TTS 配置是否可用。

### 智能辅导图片请求超时

检查：

1. `.env` 中 `TUTOR_VISION_API_KEY` 或 `QWEN_API_KEY`/`DASHSCOPE_API_KEY` 是否已配置。
2. `TUTOR_VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1` 是否可访问。
3. `TUTOR_VISION_MODEL=qwen3.7-plus` 是否是当前百炼账号可用模型。
4. 上传图片是否过大。后端 `TutorAttachment.data_url` 单项上限约 700KB，前端应压缩截图后发送。
5. 问题是否已绑定正确课程；未选择当前课程或课程不存在时会返回 `course not found`。

### 错题集没有更新

检查：

1. 学习页是否提交了 `POST /api/assessments/submit`。
2. 选择题 payload 是否包含题干、选项、`selected_answer_index` 和 `correct_answer_index`。
3. 编程题 payload 是否包含 `expected_output`、`actual_output` 和 `passed`。
4. 当前课程是否有知识图谱；错题集按图谱章节分组，没有图谱时只能降级显示未归档题目。
5. 错题重做是否以 `wrong_question_redo` 详情重新提交评估。

### VoxCPM2 不生效

这是预期的默认部署策略。当前课堂 TTS 默认使用 OpenMAIC 侧阿里云百炼 Qwen TTS；FastAPI 的 `/tts/upload` 只是可选实验兜底。如果确实要启用本地 VoxCPM2，需要单独安装 `voxcpm` 及其模型依赖，并确认本机内存和 PyTorch 运行环境满足要求。

### bcrypt 登录报错

如果登录或注册时出现：

```text
ValueError: password cannot be longer than 72 bytes
```

按项目 `requirements.txt` 重新安装兼容依赖：

```powershell
cd D:\softbei\a3\apps\api
pip install -r requirements.txt --force-reinstall
```

### 端口被占用

```powershell
netstat -ano | findstr :8000
```

确认是旧项目进程后，再结束对应 PID。

## 10. 验证

```powershell
cd D:\softbei\a3
conda activate a3
python -m pytest apps/api/tests -q

cd D:\softbei\a3\apps\web
npm run build
```

端到端验证时，必须分别跑通 `C语言程序设计` 和 `Python程序设计`，并确认两门课数据完全隔离。
