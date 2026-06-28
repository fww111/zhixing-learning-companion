from __future__ import annotations

import json
import re
from typing import Any

import httpx


class LLMClient:
    transient_retry_attempts = 2

    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
        mock: bool = False,
        timeout_seconds: int = 180,
    ) -> None:
        self.api_key = api_key or ""
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.mock = mock or not self.api_key
        self.timeout_seconds = max(30, timeout_seconds)

    async def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if self.mock:
            return self._mock_json(system_prompt, user_prompt)

        strict_system_prompt = (
            f"{system_prompt}\n"
            "输出要求：只返回一个 JSON 对象；不要输出解释、Markdown 标题、代码块、示例代码或额外文本。"
        )
        response = await self._complete(strict_system_prompt, user_prompt, max_tokens=900)
        try:
            return self.parse_json(response)
        except json.JSONDecodeError:
            repair_prompt = (
                "请把下面这段内容整理为一个合法 JSON 对象。"
                "只返回 JSON，不要输出解释、Markdown 或代码块。\n\n"
                f"{response}"
            )
            repaired = await self._complete(strict_system_prompt, repair_prompt, max_tokens=900)
            return self.parse_json(repaired)

    async def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        if self.mock:
            return self._mock_text(system_prompt, user_prompt)

        return await self._complete(system_prompt, user_prompt, max_tokens=1600)

    async def complete_multimodal_text(
        self,
        system_prompt: str,
        user_prompt: str,
        images: list[dict[str, Any]],
    ) -> str:
        if self.mock:
            return self._mock_multimodal_text(system_prompt, user_prompt, images)

        return await self._complete_multimodal(system_prompt, user_prompt, images, max_tokens=1600)

    async def stream_text(self, text: str):
        for token in text.split():
            yield token + " "

    async def _complete(self, system_prompt: str, user_prompt: str, max_tokens: int | None = None) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        last_error: Exception | None = None
        for attempt in range(self.transient_retry_attempts):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds, connect=20.0)) as client:
                    response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                return data["choices"][0]["message"]["content"]
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ConnectError) as exc:
                last_error = exc
                if attempt + 1 >= self.transient_retry_attempts:
                    raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("unreachable llm completion state")

    async def _complete_multimodal(
        self,
        system_prompt: str,
        user_prompt: str,
        images: list[dict[str, Any]],
        max_tokens: int | None = None,
    ) -> str:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for image in images:
            data_url = str(image.get("data_url") or "").strip()
            if data_url.startswith("data:image/"):
                content.append({"type": "image_url", "image_url": {"url": data_url}})
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        last_error: Exception | None = None
        for attempt in range(self.transient_retry_attempts):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds, connect=20.0)) as client:
                    response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                return data["choices"][0]["message"]["content"]
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ConnectError) as exc:
                last_error = exc
                if attempt + 1 >= self.transient_retry_attempts:
                    raise
        if last_error is not None:
            raise last_error
        raise RuntimeError("unreachable llm multimodal completion state")

    def parse_json(self, content: str) -> dict[str, Any]:
        match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
        if match:
            content = match.group(1)
        if not content.lstrip().startswith(("{", "[")):
            object_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", content)
            if object_match:
                content = object_match.group(1)
        return json.loads(content)

    def _mock_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return {
            "major": "计算机科学与技术",
            "grade": "大二",
            "learning_goal": "4周内入门机器学习",
            "knowledge_foundation": "Python基础一般，线性代数薄弱",
            "learning_style": "偏好图解、案例和短练习",
            "cognitive_style": "先直观理解再公式推导",
            "weak_points": ["梯度下降", "矩阵运算", "模型评估"],
            "time_preference": "每天晚间45分钟",
            "resource_preference": ["动画", "代码实操", "短练习"],
            "updated_evidence": [{"source": "mock_llm", "topic": "画像构建", "detail": user_prompt[:120]}],
        }

    def _mock_text(self, system_prompt: str, user_prompt: str) -> str:
        if "智能辅导生成智能体" in system_prompt:
            topic_match = re.search(r"当前知识点[：:]\s*(.+)", user_prompt)
            topic = topic_match.group(1).splitlines()[0].strip() if topic_match else "当前知识点"
            evidence_match = re.search(r"(chunk#[^\n]+)\n([^\n]+)", user_prompt)
            citation = evidence_match.group(1).split("|")[0].strip() if evidence_match else "chunk#unknown"
            evidence = evidence_match.group(2).strip() if evidence_match else "课程知识库证据不足"
            question_match = re.search(r"学生问题[：:]\s*(.+)", user_prompt)
            question = question_match.group(1).splitlines()[0].strip() if question_match else "你的问题"
            return (
                f"围绕“{topic}”，我先回答你的问题：{question}\n\n"
                f"课程知识库中的关键依据是：{evidence}\n\n"
                "这意味着学习时不要只背结论，还要理解它背后的判定规则、常见反例和可操作练习。"
                "如果遇到类似截图或代码报错，可以先定位是哪条规则被违反，再把变量名或语句改成符合语法的形式。\n\n"
                f"引用依据：{citation}。"
            )
        topic_match = re.search(r"知识点[：:]\s*(.+)", user_prompt)
        topic = topic_match.group(1).splitlines()[0].strip() if topic_match else "当前知识点"
        if "思维导图" in system_prompt:
            return f"""# {topic}思维导图

## 核心概念
- 用一句话说明{topic}解决的问题
- 标出它在课程知识结构中的前置与后续关系

## 学习分支
- 定义与边界
- 关键步骤
- 典型示例
- 易错点与自检问题

## 学习建议
先看整体结构，再用一个小例子验证理解，最后用练习题检查迁移能力。"""
        if "题库" in system_prompt or "练习" in system_prompt:
            classified_exercise = self._mock_exercise_text(topic)
            if classified_exercise:
                return classified_exercise
            if (
                "伪代码" in topic
                or "算法表示" in topic
                or "算法描述" in topic
                or "流程图" in topic
                or "顺序结构" in topic
                or "选择结构" in topic
                or "循环结构" in topic
            ):
                return f"""# {topic}分层练习

1. 围绕{topic}，下列哪一段最符合“用伪代码表示算法”的表达要求？
A. 输入 n；如果 n 是偶数则输出“偶数”，否则输出“奇数”
B. 这个算法很重要，需要认真学习
C. Python 程序只要能运行，就不需要描述步骤
答案：A
维度：概念理解
权重：35%

2. 围绕{topic}，要用伪代码描述“求 1 到 n 的累加和”，哪种步骤最合理？
A. 输入 n；sum 置 0；从 1 循环到 n，把当前数累加到 sum；输出 sum
B. 只写“计算累加和”，不说明输入、循环和输出
C. 先输出结果，再决定 n 的取值
答案：A
维度：迁移应用
权重：30%

3. 围绕{topic}，如果伪代码漏写循环终止条件，最可能导致什么问题？
A. 算法步骤不完整，无法判断循环何时结束，后续转成程序时容易出现死循环或结果错误
B. 变量名一定不合法
C. Python 解释器版本一定不兼容
答案：A
维度：调试反思
权重：35%

编程题：围绕“{topic}”，把“输入一个整数 n，输出 1 到 n 的累加和”这一伪代码过程转成 Python 程序。测试输入固定为 5，只输出累加和结果。
期望输出：15
```python
# 测试输入固定为一行：5
n = int(input())
total = 0
# 请使用循环把 1 到 n 累加到 total
# 请输出 total
```
"""
            if (
                "变量" in topic
                or "变量名" in topic
                or "标识符" in topic
                or "赋值" in topic
                or "input" in topic
                or "输入" in topic
                or "输出" in topic
                or "交换" in topic
            ):
                return f"""# {topic}分层练习

1. 围绕{topic}，在 Python 中，下列哪个变量名是不合法的？
A. _my_var
B. 2nd_value
C. userName
D. PI
答案：B
维度：概念理解
权重：35%

2. 围绕{topic}，如果要把用户输入的两个整数相加，哪种写法最合理？
A. 使用 num1 = int(input()) 和 num2 = int(input()) 先完成类型转换，再进行加法
B. 直接把两个 input() 的返回值相加，因为 input() 默认返回整数
C. 只使用 print(input())，不需要变量保存和类型转换
答案：A
维度：迁移应用
权重：30%

3. 围绕{topic}，代码 2nd_value = 10 报错，最准确的原因是什么？
A. Python 变量名不能以数字开头，应该改成符合标识符规则的名称
B. Python 变量名不能包含下划线
C. Python 中所有变量赋值前都必须先声明类型
答案：A
维度：调试反思
权重：35%

编程题：变量交换与输入输出。围绕“{topic}”，编写 Python 程序：使用 input() 接收两个整数，分别赋值给变量 num1 和 num2；先输出交换前两个变量的值；再交换两个变量；最后输出交换后的值。测试输入固定为两行：3 和 8。
期望输出：交换前：num1=3, num2=8
交换后：num1=8, num2=3
```python
# 测试输入固定为两行：3 和 8
num1 = int(input())
num2 = int(input())
# 请输出交换前两个变量的值，格式：交换前：num1=3, num2=8
# 请交换 num1 和 num2
# 请输出交换后两个变量的值，格式：交换后：num1=8, num2=3
```
"""
            if "版本" in topic or "Python" in topic:
                return f"""# {topic}分层练习

1. 围绕{topic}，关于 Python 2 与 Python 3 的差异，哪一项判断更准确？
A. Python 3 改进了文本编码处理，并调整了 print 等常见语法形式
B. Python 2 与 Python 3 的语法和标准库完全兼容
C. Python 版本只影响编辑器主题，不会影响程序运行
答案：A
维度：概念理解
权重：35%

2. 学完{topic}后，在选择项目运行环境时，为什么要确认 Python 版本？
A. 因为库的兼容范围、语法特性和解释器行为都可能依赖具体版本
B. 因为版本号越长，程序运行速度一定越快
C. 因为 Python 版本只用于给文件命名
答案：A
维度：迁移应用
权重：30%

3. 围绕{topic}，旧示例出现 SyntaxError: Missing parentheses in call to 'print'，最可能的原因是什么？
A. 在 Python 3 环境中运行了 Python 2 风格的 print 语句
B. 变量名一定和关键字冲突
C. 操作系统不支持 Python 解释器
答案：A
维度：调试反思
权重：35%

编程题：围绕“{topic}”，补全 Python 程序，使用变量 major 表示 Python 主版本号，并输出“Python 3”。只输出这一行文本。
期望输出：Python 3
```python
language = "Python"
major = 3
# 请补全输出语句
```
"""
            return f"""# {topic}分层练习

1. 围绕{topic}，下列哪项最能体现该知识点的核心作用？
A. 能说明它解决的问题、适用条件、输入输出关系和常见错误
B. 只知道它出现在本节课中
C. 只知道它对应教材中的某一页
答案：A
维度：概念理解
权重：35%

2. 学完{topic}后，面对一个相邻知识点的小任务，哪种做法最能体现迁移应用？
A. 完全照抄示例，不分析新问题差异
B. 根据问题特征选择相关语法或方法，并能解释为什么适用
C. 只运行一次，不检查边界情况
答案：B
维度：迁移应用
权重：30%

3. 如果围绕{topic}的练习结果不符合预期，优先应该检查什么？
A. 输入数据、处理步骤和输出结果是否与题意一致
B. 是否跳过本节继续下一节
C. 是否把所有代码都删除重写
答案：A
维度：调试反思
权重：35%

编程题：围绕“{topic}”，补全最小可运行程序，输出该知识点的一个关键变量值或结论。只输出题目要求的一行文本。
期望输出：{topic} 核心结论
```python
topic = "{topic}"
result = "核心结论"
# 请补全输出语句，组合 topic 和 result
```
"""
        if "视频" in system_prompt:
            return f"""# {topic}教学视频脚本

## 开场
用课程中的真实场景引出{topic}为什么重要。

## 分镜
1. 展示知识点在知识图谱中的位置。
2. 用图示解释核心概念。
3. 拆解一个教材示例。
4. 给出一个即时小练习。

## 收束
提醒学生用练习结果检查是否真正掌握。"""
        if "代码" in system_prompt or "实操" in system_prompt:
            return f"""# {topic}代码实操

```python
def explain_topic():
    topic = "{topic}"
    steps = ["复述定义", "运行最小示例", "修改参数观察结果", "写出自检结论"]
    for index, step in enumerate(steps, 1):
        print(f"{{index}}. {{topic}} - {{step}}")

explain_topic()
```

## 实操任务
运行代码后，把每一步替换成课程材料中的具体例子。"""
        if "阅读" in system_prompt:
            return f"""# {topic}拓展阅读

## 阅读顺序
1. 先读课程材料中的定义和例子。
2. 再对照相邻知识点，找到区别和联系。
3. 最后整理一张概念卡片。

## 阅读产出
写下三个关键词、一个例子和一个仍不清楚的问题。"""
        return f"""# {topic}个性化讲解

## 学习目标
理解{topic}的定义、使用场景和常见误区。

## 讲解
结合本地课程知识库中的定义和示例，先建立直观理解，再通过一个小任务完成迁移。

## 自检
如果能够独立说明{topic}解决的问题，并完成一个简单例子，就可以进入下一步学习。"""

    def _mock_multimodal_text(self, system_prompt: str, user_prompt: str, images: list[dict[str, Any]]) -> str:
        base = self._mock_text(system_prompt, user_prompt)
        image_names = [
            str(image.get("filename") or "image").strip()
            for image in images
            if str(image.get("data_url") or "").startswith("data:image/")
        ]
        if not image_names:
            return base
        return (
            f"{base}\n\n"
            f"已结合上传图片（{', '.join(image_names[:3])}）进行多模态理解；"
            "实际在线模式会由 Qwen3.7-Plus 读取图片内容后再结合课程证据回答。"
        )

    def _mock_exercise_text(self, topic: str) -> str | None:
        template_key = self._mock_assessment_template_key(topic)
        templates: dict[str, str] = {
            "python_branch": f"""# {topic}分层练习

1. 围绕{topic}，Python 中 if 条件分支的执行规则哪一项正确？
A. 条件表达式为 True 时执行 if 代码块，否则可进入 elif 或 else 分支
B. if 和 else 两个代码块每次都会同时执行
C. 条件分支只能判断数字，不能判断比较表达式
答案：A
维度：概念理解
权重：35%

2. 围绕{topic}，要根据 score 是否大于等于 60 输出“及格/不及格”，最合理的结构是什么？
A. 使用 if score >= 60: 处理及格情况，并用 else: 处理不及格情况
B. 只写两个连续的 print，不需要条件判断
C. 使用 input() 就会自动判断是否及格
答案：A
维度：迁移应用
权重：30%

3. 围绕{topic}，if 语句缩进错误最可能造成什么结果？
A. 分支代码块归属错误，可能触发 IndentationError 或导致逻辑路径不符合预期
B. 变量名会自动变成全局变量
C. else 会自动补全缺失的条件
答案：A
维度：调试反思
权重：35%

编程题：围绕“{topic}”，补全 Python 程序，根据 score 的值输出“及格”或“不及格”。测试 score 固定为 72，只输出判断结果。
期望输出：及格
```python
score = 72
# 请使用 if/else 判断 score 是否大于等于 60
# 请输出：及格
```
""",
            "python_loop": f"""# {topic}分层练习

1. 围绕{topic}，for i in range(1, 5) 会依次产生哪些 i 值？
A. 1、2、3、4
B. 1、2、3、4、5
C. 0、1、2、3、4、5
答案：A
维度：概念理解
权重：35%

2. 围绕{topic}，要计算 1 到 n 的累加和，循环体中最关键的语句是什么？
A. total = total + i，把当前循环变量累加到 total
B. total = i，每次覆盖之前的结果
C. print(i)，打印循环变量就等于完成累加
答案：A
维度：迁移应用
权重：30%

3. 围绕{topic}，循环结果少算最后一个数时，优先应该检查什么？
A. range 的结束边界是否是左闭右开，以及循环变量是否覆盖了目标范围
B. print 的字体大小是否合适
C. Python 文件名是否包含中文
答案：A
维度：调试反思
权重：35%

编程题：围绕“{topic}”，补全 Python 程序，使用 for 和 range 计算 1 到 5 的累加和。只输出一行数字。
期望输出：15
```python
total = 0
# 请使用 for i in range(1, 6) 完成累加
# 请输出 total
```
""",
            "python_function": f"""# {topic}分层练习

1. 围绕{topic}，Python 函数定义中 def、参数和 return 的作用哪项正确？
A. def 定义可复用逻辑，参数接收外部数据，return 把结果返回给调用处
B. def 只能定义变量，return 只能打印文本
C. 函数参数只能是字符串，不能是数字
答案：A
维度：概念理解
权重：35%

2. 围绕{topic}，要封装一个求两个数最大值的函数，哪种设计更合理？
A. def max_value(a, b): 接收两个参数，并用 return 返回较大的值
B. 在函数内部固定写死 a=1、b=2，不接收参数
C. 只在函数里 print，不考虑调用处是否需要继续使用结果
答案：A
维度：迁移应用
权重：30%

3. 围绕{topic}，函数调用结果是 None，最可能需要检查什么？
A. 函数体是否缺少 return，或者 return 是否只写在某个分支里
B. 文件扩展名是否必须改成 .txt
C. 参数名是否必须叫 number
答案：A
维度：调试反思
权重：35%

编程题：围绕“{topic}”，补全 Python 函数 max_value(a, b)，用 return 返回较大的数，并输出 max_value(4, 9)。只输出一行数字。
期望输出：9
```python
def max_value(a, b):
    # 请返回 a 和 b 中较大的值

# 请输出 max_value(4, 9)
```
""",
            "python_sequence": f"""# {topic}分层练习

1. 围绕{topic}，Python 列表索引和遍历的说法哪项正确？
A. 列表下标从 0 开始，可以用 for 循环依次访问元素
B. 列表下标从 1 开始，不能通过循环访问
C. 列表只能保存一个元素
答案：A
维度：概念理解
权重：35%

2. 围绕{topic}，要统计列表 nums 中所有元素的和，哪种思路最合理？
A. 初始化 total，再遍历 nums，把每个元素累加到 total
B. 只访问 nums[0]，它一定代表所有元素之和
C. 把列表转成字符串后直接相加
答案：A
维度：迁移应用
权重：30%

3. 围绕{topic}，访问列表时出现 IndexError，优先应该检查什么？
A. 索引是否超出 0 到 len(list)-1 的有效范围
B. 变量名是否必须叫 list
C. 是否没有导入 math 模块
答案：A
维度：调试反思
权重：35%

编程题：围绕“{topic}”，补全 Python 程序，遍历列表 nums 并输出所有元素之和。只输出一行数字。
期望输出：12
```python
nums = [2, 4, 6]
total = 0
# 请遍历 nums，把每个元素累加到 total
# 请输出 total
```
""",
            "python_file": f"""# {topic}分层练习

1. 围绕{topic}，Python 使用 open 读取文件时，哪项说法正确？
A. open(path, 'r', encoding='utf-8') 可打开文本文件读取内容，用完应关闭或使用 with 管理
B. open() 只能创建文件，不能读取文件
C. 读取文件不需要路径，也不需要处理编码
答案：A
维度：概念理解
权重：35%

2. 围绕{topic}，要逐行读取文本文件并统计行数，哪种思路最合理？
A. 使用 with open(...) as f: 打开文件，再遍历文件对象累加行数
B. 只调用一次 print，不需要读取文件内容
C. 把文件名赋值给变量就能得到所有行数
答案：A
维度：迁移应用
权重：30%

3. 围绕{topic}，读取文件时出现乱码，优先应该检查什么？
A. 文件实际编码和 open 中指定的 encoding 是否一致
B. 循环变量是否叫 i
C. 是否写了太多注释
答案：A
维度：调试反思
权重：35%

编程题：围绕“{topic}”，模拟文件读取结果 lines，补全 Python 程序输出文本行数。只输出一行数字。
期望输出：3
```python
lines = ['第一行', '第二行', '第三行']
# 请输出 lines 的长度，模拟 open 读取后的行数统计
```
""",
            "c_array": f"""# {topic}分层练习

1. 围绕{topic}，C 语言一维数组 int a[5] 的下标范围哪项正确？
A. 有效下标是 0 到 4
B. 有效下标是 1 到 5
C. 有效下标是 0 到 5
答案：A
维度：概念理解
权重：35%

2. 围绕{topic}，要累加数组 a 中 5 个整数，哪种循环边界更合理？
A. for (i = 0; i < 5; i++) 依次访问 a[i]
B. for (i = 1; i <= 5; i++) 依次访问 a[i]，不会越界
C. 不需要循环，数组会自动求和
答案：A
维度：迁移应用
权重：30%

3. 围绕{topic}，数组访问越界最可能带来什么问题？
A. 读写未定义内存位置，导致结果异常或程序崩溃
B. 数组长度会自动扩大
C. 编译器一定会自动修复下标
答案：A
维度：调试反思
权重：35%

编程题：围绕“{topic}”，补全 C 程序，定义一维数组 a，计算 3 个整数元素的和并输出。只输出一行数字。
期望输出：12
```c
#include <stdio.h>
int main() {{
  int a[3] = {{2, 4, 6}};
  int sum = 0;
  // 请使用 for 循环累加数组元素
  // 请输出 sum
  return 0;
}}
```
""",
            "c_pointer": f"""# {topic}分层练习

1. 围绕{topic}，C 语言中 &x 和 *p 的含义哪项正确？
A. &x 取得变量 x 的地址，*p 访问指针 p 指向地址中的值
B. &x 表示乘法，*p 表示字符串
C. 指针变量只能保存普通整数，不能保存地址
答案：A
维度：概念理解
权重：35%

2. 围绕{topic}，若 int x = 3; int *p = &x; 执行 *p = 5; 后 x 的值是什么？
A. 5
B. 3
C. 无法确定，因为 p 没有指向 x
答案：A
维度：迁移应用
权重：30%

3. 围绕{topic}，使用指针前最应该确认什么？
A. 指针是否已经指向有效地址，避免野指针或空指针解引用
B. 指针变量名是否必须叫 p
C. 是否所有指针都必须指向数组
答案：A
维度：调试反思
权重：35%

编程题：围绕“{topic}”，补全 C 程序，通过指针 p 修改变量 x 的值，并输出 x。只输出一行数字。
期望输出：5
```c
#include <stdio.h>
int main() {{
  int x = 3;
  int *p = &x;
  // 请通过 *p 把 x 修改为 5
  // 请输出 x
  return 0;
}}
```
""",
            "c_function": f"""# {topic}分层练习

1. 围绕{topic}，C 语言函数定义中返回类型、参数和 return 的作用哪项正确？
A. 返回类型说明返回值类型，参数接收调用者传入的数据，return 返回结果并结束函数
B. 所有函数都不能有参数
C. return 只能在 main 函数中使用
答案：A
维度：概念理解
权重：35%

2. 围绕{topic}，要定义一个求两个 int 最大值的函数，哪种函数头更合理？
A. int max(int a, int b)
B. void max() 且不接收任何参数
C. char max(int a, int b) 且返回字符串
答案：A
维度：迁移应用
权重：30%

3. 围绕{topic}，函数返回值异常时优先检查什么？
A. 参数传入是否正确、分支是否都有 return、返回类型是否匹配
B. 源文件是否必须放在桌面
C. 注释是否超过三行
答案：A
维度：调试反思
权重：35%

编程题：围绕“{topic}”，补全 C 程序，调用 max 函数返回两个整数中的较大值并输出。只输出一行数字。
期望输出：9
```c
#include <stdio.h>
int max(int a, int b) {{
  // 请返回较大的整数
}}
int main() {{
  // 请输出 max(4, 9) 的结果
  return 0;
}}
```
""",
        }
        return templates.get(template_key)

    def _mock_assessment_template_key(self, topic: str) -> str:
        text = topic.lower()
        is_c_course = "c语言" in text or "c 语言" in text
        if is_c_course:
            if any(keyword in text for keyword in ["数组", "下标", "一维数组", "二维数组"]):
                return "c_array"
            if any(keyword in text for keyword in ["指针", "地址", "*p", "取地址"]):
                return "c_pointer"
            if any(keyword in text for keyword in ["函数", "调用", "return", "参数"]):
                return "c_function"
            return ""
        if any(keyword in text for keyword in ["if", "else", "elif", "分支", "条件", "选择结构"]):
            return "python_branch"
        if any(keyword in text for keyword in ["for", "while", "range", "循环", "遍历"]):
            return "python_loop"
        if any(keyword in text for keyword in ["列表", "字典", "元组", "字符串", "索引", "切片"]):
            return "python_sequence"
        if any(keyword in text for keyword in ["文件", "open", "读写", "读取", "写入"]):
            return "python_file"
        if any(keyword in text for keyword in ["函数", "def", "return", "参数", "调用"]):
            return "python_function"
        return ""
