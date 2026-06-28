import {
  assessmentQuizItems,
  buildAssessmentQuizItems,
  buildComprehensiveAssessmentPayload,
  buildCodeAssessmentChallenge,
  codeAttemptMatchesChallenge,
  parseExerciseAssessment,
  previewQuizScore
} from "./assessmentModel.js";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

test("preview quiz score is weighted by answered assessment items", () => {
  const score = previewQuizScore({
    concept: assessmentQuizItems[0].answer,
    transfer: 0,
    debugging: assessmentQuizItems[2].answer
  });

  assert(score > 0.69 && score < 0.71, `unexpected weighted score: ${score}`);
});

test("assessment quiz items are generated for the current course topic", () => {
  const items = buildAssessmentQuizItems({
    courseName: "Python程序设计",
    topic: "1.1.1 Python语言的特点"
  });

  assert(items.length === 3, "assessment should keep three focused quiz questions");
  assert(items.every((item) => item.prompt.includes("Python语言的特点") || item.prompt.includes("Python程序设计")), "quiz prompts should reference the active course topic");
  assert(items.map((item) => item.id).join(",") === "concept,transfer,debugging", "quiz ids must stay compatible with backend evaluator");
});

test("fallback assessment avoids generic memory questions and pass-label code tasks", () => {
  const topic = "1.2.1 Python 的版本";
  const items = buildAssessmentQuizItems({
    courseName: "Python程序设计",
    topic
  });
  const challenge = buildCodeAssessmentChallenge({
    courseName: "Python程序设计",
    topic
  });
  const combinedText = [
    ...items.flatMap((item) => [item.prompt, ...item.options]),
    challenge.prompt,
    challenge.expectedOutput
  ].join("\n");

  assert(!combinedText.includes("只记住"), "fallback quiz must not ask whether the learner only remembers a title");
  assert(!combinedText.includes("这个标题"), "fallback quiz must not use title-memory wording");
  assert(!combinedText.includes("课堂视频"), "fallback quiz must not ask whether the learner watched a video");
  assert(!combinedText.includes(`${topic} 达标`), "fallback code task must not use the same pass-label output for every topic");
  assert(items.some((item) => item.prompt.includes("Python 2") || item.prompt.includes("Python 3")), "version topic should ask professional Python version knowledge");
  assert(challenge.prompt.includes("版本"), "programming challenge should be tied to the version topic");
});

test("python variable assessment fallback uses concrete professional questions", () => {
  const topic = "2.1 Python变量与输入输出";
  const items = buildAssessmentQuizItems({
    courseName: "Python程序设计",
    topic
  });
  const challenge = buildCodeAssessmentChallenge({
    courseName: "Python程序设计",
    topic
  });
  const combinedText = [
    ...items.flatMap((item) => [item.prompt, ...item.options]),
    challenge.prompt,
    challenge.starterCode,
    challenge.expectedOutput
  ].join("\n");

  assert(items.length === 3, "python variable fallback should provide three quiz items");
  assert(items[0].prompt.includes("变量名") || items[0].prompt.includes("标识符"), "first quiz should test variable naming rules");
  assert(items[0].options.includes("2nd_value"), "quiz should include an illegal Python identifier option");
  assert(items[0].answer === items[0].options.indexOf("2nd_value"), "illegal identifier should be the correct answer");
  assert(challenge.prompt.includes("input()"), "code challenge should test input for variable topics");
  assert(challenge.prompt.includes("num1") && challenge.prompt.includes("num2"), "code challenge should require concrete variables");
  assert(challenge.expectedOutput.includes("交换前") && challenge.expectedOutput.includes("交换后"), "expected output should support auto grading");
  assert(!combinedText.includes("核心作用"), "variable fallback must not use generic core-role wording");
  assert(!combinedText.includes("迁移应用") || combinedText.includes("int(input())"), "variable fallback should avoid empty transfer wording");
  assert(!combinedText.includes("练习结果不符合预期"), "variable fallback must not use generic debugging wording");
  assert(!challenge.starterCode.includes("#include"), "Python variable challenge must not use a C skeleton");
  assert(!challenge.starterCode.includes("printf"), "Python variable challenge must not use printf");
  assert(!challenge.starterCode.includes(challenge.expectedOutput), "starter code should not leak the expected answer");
});

test("low quality generated exercise content is rejected for python variable assessment", () => {
  const exerciseContent = [
    "1. 围绕Python变量，下列哪项最能体现该知识点的核心作用？",
    "A. 能说明它解决的问题、适用条件、输入输出关系和常见错误",
    "B. 只知道它出现在本节课中",
    "C. 只知道它对应教材中的某一页",
    "答案：A",
    "2. 把Python变量用于一个新的编程场景时，最合理的判断是什么？",
    "A. 根据问题特征选择相关语法或方法，并能解释为什么适用",
    "B. 完全照抄示例，不分析新问题差异",
    "C. 只运行一次，不检查边界情况",
    "答案：A",
    "3. Python变量相关练习结果不符合预期时，优先应该怎么做？",
    "A. 沿着输入、状态变化、关键语句和输出逐步定位问题",
    "B. 随机改动多处代码后立即提交",
    "C. 跳过该知识点，继续下一个任务",
    "答案：A",
    "编程题：围绕“Python变量”，补全 C 程序，输出 C 程序入口函数的名称。只输出一行文本。",
    "期望输出：main",
    "```c",
    "#include <stdio.h>",
    "int main() {",
    "  // 请补全 printf，输出入口函数名称",
    "  return 0;",
    "}",
    "```"
  ].join("\n");

  const items = buildAssessmentQuizItems({
    courseName: "Python程序设计",
    exerciseContent,
    topic: "2.1 Python变量与输入输出"
  });
  const challenge = buildCodeAssessmentChallenge({
    courseName: "Python程序设计",
    exerciseContent,
    topic: "2.1 Python变量与输入输出"
  });
  const combinedText = items.flatMap((item) => [item.prompt, ...item.options]).join("\n");

  assert(items[0].options.includes("2nd_value"), "low quality generic quiz should fall back to Python variable quiz");
  assert(!combinedText.includes("只知道它出现在本节课中"), "generic memory distractors should be rejected");
  assert(challenge.prompt.includes("变量交换与输入输出"), "low quality C code challenge should fall back to Python variable task");
  assert(!challenge.starterCode.includes("#include"), "fallback challenge should not keep wrong-language C code");
});

test("generated quiz items with missing options are rejected before rendering", () => {
  const exerciseContent = [
    "1. 有人认为计算机是万能的，会自动进行所有工作，这种观点的真正错误是什么？",
    "A. 计算机拥有自主智能，能自动判断任务并执行",
    "答案：B",
    "维度：概念理解",
    "权重：35%",
    "2. 程序为什么需要清晰步骤？",
    "A. 因为计算机只能按明确指令执行",
    "B. 因为程序越长越好",
    "C. 因为显示器需要刷新",
    "答案：A",
    "维度：迁移应用",
    "权重：30%",
    "3. 合上电源后没有反应，最可能先检查什么？",
    "A. 电源和连接状态",
    "B. 是否会自动完成任务",
    "C. 是否跳过本节课",
    "答案：A",
    "维度：调试反思",
    "权重：35%"
  ].join("\n");

  const parsed = parseExerciseAssessment(exerciseContent);
  const items = buildAssessmentQuizItems({
    courseName: "C语言程序设计",
    exerciseContent,
    topic: "1.1 什么是计算机程序"
  });

  assert(parsed.quizItems.length === 2, "parser should discard generated quiz items with fewer than three options");
  assert(items.length === 3, "assessment should fall back to a complete professional quiz set");
  assert(items.every((item) => item.options.length >= 3), "rendered assessment items must always have at least three options");
  assert(!items[0].prompt.includes("万能"), "incomplete generated question should not be rendered");
});

test("python pseudocode assessment fallback avoids subjective generic questions", () => {
  const topic = "2.5.5 用伪代码表示算法";
  const items = buildAssessmentQuizItems({
    courseName: "Python程序设计",
    topic
  });
  const challenge = buildCodeAssessmentChallenge({
    courseName: "Python程序设计",
    topic
  });
  const combinedText = [
    ...items.flatMap((item) => [item.prompt, ...item.options]),
    challenge.prompt,
    challenge.starterCode,
    challenge.expectedOutput
  ].join("\n");

  assert(items.length === 3, "pseudocode fallback should provide three quiz items");
  assert(combinedText.includes("伪代码"), "pseudocode fallback should test the active knowledge point");
  assert(combinedText.includes("顺序") || combinedText.includes("选择") || combinedText.includes("循环"), "pseudocode quiz should test algorithm structure");
  assert(!combinedText.includes("核心作用"), "pseudocode fallback must not use generic core-role wording");
  assert(!combinedText.includes("练习结果不符合预期"), "pseudocode fallback must not use generic debugging wording");
  assert(!combinedText.includes("只知道"), "pseudocode fallback must not include memory-only distractors");
  assert(!challenge.starterCode.includes("#include"), "Python pseudocode challenge must not use a C skeleton");
  assert(!challenge.starterCode.includes("printf"), "Python pseudocode challenge must not use printf");
});

test("assessment fallback generates professional questions across common course knowledge types", () => {
  const cases = [
    {
      courseName: "Python程序设计",
      topic: "3.2 if条件分支语句",
      expectedTerms: ["if", "条件", "else"],
      forbiddenTerms: ["#include", "printf"]
    },
    {
      courseName: "Python程序设计",
      topic: "4.1 for循环与range函数",
      expectedTerms: ["for", "range", "循环"],
      forbiddenTerms: ["#include", "printf"]
    },
    {
      courseName: "Python程序设计",
      topic: "5.3 函数定义与参数传递",
      expectedTerms: ["def", "参数", "return"],
      forbiddenTerms: ["#include", "printf"]
    },
    {
      courseName: "Python程序设计",
      topic: "6.2 列表索引与遍历",
      expectedTerms: ["列表", "索引", "遍历"],
      forbiddenTerms: ["#include", "printf"]
    },
    {
      courseName: "Python程序设计",
      topic: "8.1 文件读写 open函数",
      expectedTerms: ["open", "文件", "读取"],
      forbiddenTerms: ["#include", "printf"]
    },
    {
      courseName: "C语言程序设计",
      topic: "5.2 一维数组的定义和引用",
      expectedTerms: ["数组", "下标", "int"],
      forbiddenTerms: ["Python 简洁"]
    },
    {
      courseName: "C语言程序设计",
      topic: "7.1 指针变量与地址",
      expectedTerms: ["指针", "地址", "&"],
      forbiddenTerms: ["Python 简洁"]
    },
    {
      courseName: "C语言程序设计",
      topic: "6.1 函数定义与调用",
      expectedTerms: ["函数", "参数", "return"],
      forbiddenTerms: ["Python 简洁"]
    }
  ];

  for (const testCase of cases) {
    const items = buildAssessmentQuizItems(testCase);
    const challenge = buildCodeAssessmentChallenge(testCase);
    const combinedText = [
      ...items.flatMap((item) => [item.prompt, ...item.options]),
      challenge.prompt,
      challenge.starterCode,
      challenge.expectedOutput
    ].join("\n");

    assert(items.length === 3, `${testCase.topic} should have three quiz items`);
    assert(
      testCase.expectedTerms.every((term) => combinedText.includes(term)),
      `${testCase.topic} should include professional terms: ${testCase.expectedTerms.join(", ")}\n${combinedText}`
    );
    assert(!combinedText.includes("核心作用"), `${testCase.topic} must not use generic core-role wording`);
    assert(!combinedText.includes("只知道"), `${testCase.topic} must not include memory-only distractors`);
    assert(!combinedText.includes("练习结果不符合预期"), `${testCase.topic} must not use generic debugging wording`);
    for (const forbiddenTerm of testCase.forbiddenTerms) {
      assert(!combinedText.includes(forbiddenTerm), `${testCase.topic} should not include ${forbiddenTerm}`);
    }
  }
});

test("assessment uses exercise agent questions when resource content is available", () => {
  const exerciseContent = [
    "# 1.2.1 input函数 分层练习",
    "1. 在 Python 中，input() 函数返回的数据类型是什么？",
    "A. int",
    "B. str",
    "C. bool",
    "答案：B",
    "维度：概念理解",
    "权重：35%",
    "2. 如果要读取用户输入的年龄并参与加法运算，哪种处理最合理？",
    "A. 直接把 input() 的结果相加",
    "B. 使用 int(input()) 做类型转换后再计算",
    "C. 使用 print(input())",
    "答案：B",
    "维度：迁移应用",
    "权重：30%",
    "3. 程序提示 ValueError 时，最应该优先检查什么？",
    "A. 用户输入是否能被转换为目标类型",
    "B. Python 是否安装成功",
    "C. 是否忘记写注释",
    "答案：A",
    "维度：调试反思",
    "权重：35%",
    "编程题：读取一行姓名并输出 `Hello, Alice`，其中 Alice 来自变量 name。",
    "期望输出：Hello, Alice",
    "```python",
    "name = \"Alice\"",
    "# 请补全输出语句",
    "```"
  ].join("\n");

  const items = buildAssessmentQuizItems({
    courseName: "Python程序设计",
    exerciseContent,
    topic: "1.2.1 input函数"
  });
  const challenge = buildCodeAssessmentChallenge({
    courseName: "Python程序设计",
    exerciseContent,
    topic: "1.2.1 input函数"
  });

  assert(items.length === 3, "exercise agent content should provide three quiz items");
  assert(items[0].prompt.includes("input()"), "quiz prompt should come from the exercise agent content");
  assert(items[0].options[1] === "str", "quiz options should preserve professional generated choices");
  assert(items[0].answer === 1, "quiz answer should parse from generated answer label");
  assert(challenge.prompt.includes("读取一行姓名"), "programming prompt should come from exercise agent content");
  assert(challenge.expectedOutput === "Hello, Alice", "expected output should parse from exercise content");
  assert(!challenge.starterCode.includes("Hello, Alice"), "starter code should not leak the expected output");
});

test("exercise assessment parser exposes generated quiz and code challenge", () => {
  const parsed = parseExerciseAssessment([
    "1. C语言中 scanf 读取 int 变量时，变量前通常需要什么符号？",
    "A. *",
    "B. &",
    "C. %",
    "答案：B",
    "编程题：输出 `OK`。",
    "期望输出：OK"
  ].join("\n"));

  assert(parsed.quizItems.length === 1, "parser should extract generated quiz item");
  assert(parsed.quizItems[0].prompt.includes("scanf"), "parser should keep professional topic text");
  assert(parsed.codeChallenge?.expectedOutput === "OK", "parser should extract code expected output");
});

test("programming assessment challenge does not put the answer code in the editor", () => {
  const challenge = buildCodeAssessmentChallenge({
    courseName: "Python程序设计",
    topic: "1.1.1 Python语言的特点"
  });

  assert(challenge.prompt.includes("1.1.1 Python语言的特点"), "challenge should be tied to the current topic");
  assert(challenge.expectedOutput.trim().length > 0, "challenge needs a hidden expected output for scoring");
  assert(!challenge.starterCode.includes(challenge.expectedOutput), "starter code should not contain the expected answer output");
  assert(!challenge.starterCode.includes("print("), "starter code should not give the final answer directly");
  assert(codeAttemptMatchesChallenge(challenge.expectedOutput, `${challenge.expectedOutput}\n`), "exact expected output should pass");
  assert(!codeAttemptMatchesChallenge(challenge.expectedOutput, "Hello Python"), "unrelated successful output should not pass");
});

test("comprehensive assessment payload carries classroom, quiz and runnable code evidence", () => {
  const payload = buildComprehensiveAssessmentPayload({
    answers: {
      concept: assessmentQuizItems[0].answer,
      transfer: assessmentQuizItems[1].answer,
      debugging: assessmentQuizItems[2].answer
    },
    codeAttempt: {
      prompt: "输出 Hello Python",
      code: "print('Hello Python')",
      expectedOutput: "Hello Python",
      actualOutput: "Hello Python",
      passed: true,
      attempts: 2
    },
    courseId: 1,
    lessonState: {
      course_id: 1,
      node_id: "outline-section-1-1",
      topic: "1.1 初识 Python",
      current_stage: "test",
      classroom_completed: true,
      notes_completed: true,
      mind_map_completed: true,
      code_lab_completed: false,
      test_completed: false,
      assessment_completed: false
    },
    nodeId: "outline-section-1-1",
    studentId: "user-1",
    topic: "1.1 初识 Python"
  });

  assert(payload.classroom_completed, "classroom completion should be part of assessment evidence");
  assert(payload.notes_completed, "notes completion should be part of assessment evidence");
  assert(payload.mind_map_completed, "mind map completion should be part of assessment evidence");
  assert(payload.code_lab_completed, "passing the code attempt should complete code evidence");
  assert(payload.quiz_answers.every((answer) => answer.correct), "all quiz answers should be marked correct");
  assert(payload.quiz_answers.every((answer) => answer.prompt && answer.options?.length), "quiz prompt and options should be persisted for the wrong-question collection");
  assert(payload.quiz_answers.every((answer) => typeof answer.correct_answer_index === "number"), "correct answer index should be persisted for review");
  assert(payload.code_attempt?.attempts === 2, "code attempts should be preserved");
});
