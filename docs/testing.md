# 测试说明

## 自动化测试

后端：

```powershell
cd D:\softbei\a3
conda activate a3
python -m pytest apps/api/tests -q
```

前端构建：

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

自动化测试应覆盖：

- 注册、登录、JWT 鉴权和未登录 401。
- 课程级画像访谈、自动确认和 `GET /api/profiles/me?course_id=<id>`。
- C/Python 内置课程的每用户幂等创建。
- 课程、材料、chunk、图谱任务和删除清理。
- MinerU 结果归一化、本地解析兜底和 chunk 切分。
- BGE-M3 模型加载配置、Milvus collection 命名、向量重建。
- Agentic RAG：Milvus 召回、MySQL 回表、MySQL fallback、Neo4j 图谱约束。
- 知识图谱抽取：根节点课程名、章节层级、三级节点完整性、掌握状态颜色。
- 学习路径：按画像时间约束排期、章节内知识点优先、补救任务插入。
- 资源生成闭环：`analysis_plan`、`retrieval_trace`、`graph_constraints`、`verification_report`、`pedagogy_report`、`debate_report`、`decision_report`、`agent_events`。
- 六类资源独立 Agent：文档、思维导图、视频脚本、代码实验、练习题、拓展阅读。
- 题库 Agent：围绕当前知识点生成专业选择题和编程题，选项不少于 3 个，保存 `correct_answer_index`，不同知识点和不同课程不能生成同一套泛化题。
- OpenMAIC 提交和 `/api/resources/openmaic-jobs/{job_id}` 后端轮询代理。
- 学习评估：选择题、编程题运行、综合评分、掌握度更新、画像更新、错题归档和路径重规划。
- 错题集：从 `assessment_submitted` 事件提取错题，按图谱章节分组，选择题/编程题重做正确后提交 `wrong_question_redo` 并更新评分。
- 智能辅导：文本/图片请求、Qwen3.7-Plus 图片理解、RAG 相关性过滤、课程隔离、证据不足降级和 `tutor_question_asked` 画像事件。
- Qwen TTS 配置相关测试；VoxCPM2 只保留为可选 fallback，不应作为默认课堂 TTS 断言。

## 手工验收流程

### 1. 登录与课程选择

1. 启动后端、前端、MySQL、Neo4j、Milvus 和 OpenMAIC。
2. 打开 `http://127.0.0.1:5173`。
3. 注册或登录测试账号。
4. 确认登录后首先进入 `/courses`。
5. 页面只提供 `C语言程序设计` 与 `Python程序设计` 两门主要课程入口。

### 2. 多课程数据隔离

分别对两门课执行：

1. 选择 `Python程序设计`。
2. 如果没有该课程画像，进入 `/courses/:courseId/profile/interview`。
3. 完成画像访谈并自动确认。
4. 进入该课程知识库页面。
5. 切换到 `C语言程序设计`，重复画像和知识库流程。
6. 再切回 Python，确认 Python 的画像、材料、图谱、路径、评估记录仍是 Python 自己的数据。
7. 确认测试账号创建的课程和知识库不会出现在 `xiaoming` 等其他账号中。

### 3. 课程知识库

1. 进入 `/courses/:courseId/knowledge-base`。
2. 上传 PDF/PPT/PPTX，可以一次上传多个文件。
3. 观察材料状态从 `queued` 到 `processing`、`mineru_submitted` 或 `ocr_running`、`chunking`、`indexing`，最终到 `parsed`。
4. 如果出现 `index_failed`，确认页面展示错误原因，并能点击“重建向量索引”。
5. 删除测试材料，确认文件、MySQL chunk、Milvus 向量和旧图谱任务被清理。
6. 未点击“使用内置课程”确认时，不应默认给当前用户挂载内置知识库。

### 4. 知识图谱

1. 进入 `/courses/:courseId/graph`。
2. 点击构建知识图谱。
3. 确认根节点为课程名，例如 `Python程序设计` 或 `C语言程序设计`。
4. 检查章节下的三级节点是否完整，例如 PDF 中存在 `1.2.1` 时，图谱不应只显示 `1.2.2`。
5. 确认节点颜色只表达掌握状态：灰色未学习、红色严重弱项、橙色掌握基础、浅绿色达标良好、绿色精通。
6. 点击图谱节点，确认进入 `/courses/:courseId/knowledge/:nodeId`。

### 5. 学习路径

1. 进入 `/courses/:courseId/learning-path`。
2. 确认路径来自当前课程图谱和当前课程画像，不使用固定周六/周日半小时模板。
3. 画像为 `每天1小时` 时，路径应按每日可学安排。
4. 画像为 `一周1小时，周末才有空` 时，路径只排周末，总时长约 60 分钟。
5. 有三级知识点时，任务卡应规划三级知识点；二级章节节点只作结构上下文。
6. 评估未达标后刷新学习路径，确认插入薄弱点专项补救任务。
7. `掌握基础` 仍属于未达标，只有 `达标良好` 和 `精通` 才算通过。

### 6. 知识点学习页

1. 从学习路径或知识图谱进入知识点学习页。
2. 点击生成/进入标准课堂。
3. 确认页面主体嵌入 OpenMAIC 课堂，并能自动轮询直到 `/classroom/{id}`。
4. 确认页面展示本地知识库证据、检索轨迹、图谱约束、校验分数、辩论摘要和最终决策。
5. 确认 OpenMAIC 大纲来自 Agentic RAG + 知识图谱约束，而不是只根据 topic 生成。
6. 确认思维导图是树状结构，不是简单知识点罗列。
7. 确认文档、思维导图、编程练习等按钮可点击，并展示对应资源。
8. 退出并重新进入同一课堂时，如果已有课堂缓存，不应重复调用大模型生成新内容；点击“重新生成”时应清理该知识点旧课堂缓存后重新生成。

### 7. 学习评估

1. 课堂学习结束后进入随堂测试和学习评估。
2. 评估题应与当前课程和当前知识点相关。
3. 编程题只给题目要求，不直接给答案。
4. 用户能在浏览器编辑器中编写并运行代码。
5. 代码输出与期望一致时，编程题得分通过。
6. 综合评分应考虑课堂测试、编程题、学习耗时、重试次数和知识点掌握情况。
7. 评估结束后，确认知识图谱节点颜色、学生画像、掌握记录和学习路径都被更新。

### 8. 错题集

1. 在学习评估页点击错题集入口。
2. 确认进入 `/courses/:courseId/assessment/wrong-questions`。
3. 确认错题按当前课程图谱章节和小节归档。
4. 错误选择题应展示原题、学生答案、正确答案和重做选项。
5. 错误编程题应展示题目要求、期望输出、原运行输出和重做编辑器。
6. 重做正确后，确认错题显示已解决，并且重新提交的评估更新该知识点评分。
7. 切换到另一门课后，错题集不得显示上一门课的错题。

### 9. 智能辅导

1. 登录后在任意业务页面确认右下角智能辅导入口可见。
2. 在当前课程下发送文字问题，确认回答不是简单复制 chunk 原文，而是结合本地证据生成讲解。
3. 上传截图并发送问题，确认后端使用 `TUTOR_VISION_MODEL`，默认 `qwen3.7-plus`。
4. 对一个与知识库无关的问题提问，确认系统不会强行引用不相关 chunk。
5. 关闭普通学生 UI 中的原始 RAG 证据、结构化卡和知识图谱关系展示。
6. 切换 C/Python 课程后提问，确认回答只使用当前课程证据。
7. 有课程画像时，确认问题写入 `tutor_question_asked` 学习事件。

## 接口 Smoke 示例

```powershell
$login = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/auth/login' `
  -Method Post `
  -ContentType 'application/json' `
  -Body (@{ account='demo@example.com'; password='demo123456' } | ConvertTo-Json)

$headers = @{ Authorization = "Bearer $($login.access_token)" }

$python = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/courses/default-python' `
  -Method Post `
  -Headers $headers

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/profiles/me?course_id=$($python.id)" `
  -Headers $headers
```

新用户在未完成课程画像前，`GET /api/profiles/me?course_id=<id>` 返回 404 是预期行为，前端应解释为“该课程尚无画像”，并跳转到课程画像访谈页。

## 长任务注意事项

- 几百页教材解析是长任务，上传接口只返回 `queued`。
- 首次 BGE-M3 加载如果本地模型目录不存在，会触发模型下载。
- MinerU 轮询默认最长 `MINERU_POLL_TIMEOUT_SECONDS=900` 秒。
- 后端重启会丢失进程内队列中的任务，需要重新上传或重建索引。
- OpenMAIC 课堂生成是异步任务，前端应通过后端代理轮询，不直接请求外域轮询地址。
