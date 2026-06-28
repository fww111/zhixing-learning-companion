import { detectLessonCodeLanguage, lessonCodeLabViewModel } from "./lessonCodeLabModel.js";
import type { Course, Resource } from "../api/client.js";

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

const baseCourse: Course = {
  id: 1,
  user_id: 1,
  name: "Python 程序设计",
  major: "计算机科学与技术",
  level: "undergraduate",
  description: "built-in:python demo",
  status: "ready",
  created_at: "2026-06-07T00:00:00",
  updated_at: "2026-06-07T00:00:00"
};

const baseResource: Resource = {
  id: "r1",
  type: "code_lab",
  title: "code lab",
  topic: "topic",
  content: "",
  recommendation_reason: "",
  tags: [],
  citation_chunk_ids: [],
  grounding_status: "verified",
  verification_notes: []
};

test("C course code lab uses C label and C starter code", () => {
  const model = lessonCodeLabViewModel({
    course: { ...baseCourse, name: "C语言程序设计", description: "built-in:c demo" },
    resource: { ...baseResource, content: "请完成数组初始化练习。" },
    topic: "6.3.2 字符数组的初始化"
  });

  assert(model.language === "c", "C course should be detected as C");
  assert(model.labLabel === "Browser C Lab", `unexpected label: ${model.labLabel}`);
  assert(model.starterCode.includes("#include <stdio.h>"), "C starter should include stdio");
  assert(!model.starterCode.includes("language = 'Python'"), "C starter must not use Python template");
});

test("C fenced resource content is used as starter code", () => {
  const model = lessonCodeLabViewModel({
    course: baseCourse,
    resource: {
      ...baseResource,
      content: [
        "```c",
        "#include <stdio.h>",
        "int main(void) {",
        "    printf(\"ok\\n\");",
        "    return 0;",
        "}",
        "```"
      ].join("\n")
    },
    topic: "C practice"
  });

  assert(model.language === "c", "C fenced block should force C");
  assert(model.starterCode.startsWith("#include <stdio.h>"), `unexpected starter: ${model.starterCode}`);
});

test("C course ignores stale Python fenced starter code", () => {
  const model = lessonCodeLabViewModel({
    course: { ...baseCourse, name: "C语言程序设计", description: "built-in:c demo" },
    resource: {
      ...baseResource,
      content: [
        "```python",
        "language = 'Python'",
        "print(language)",
        "```"
      ].join("\n")
    },
    topic: "字符数组初始化"
  });

  assert(model.language === "c", "C course should still be C");
  assert(model.starterCode.includes("#include <stdio.h>"), "stale Python fenced code should not be reused for C");
  assert(!model.starterCode.includes("language = 'Python'"), "C starter must not show stale Python code");
});

test("Python course keeps Python lab by default", () => {
  assert(detectLessonCodeLanguage(baseCourse, baseResource, "变量") === "python", "Python should remain default");
  const model = lessonCodeLabViewModel({ course: baseCourse, resource: baseResource, topic: "变量" });

  assert(model.labLabel === "Browser Python Lab", `unexpected label: ${model.labLabel}`);
  assert(model.starterCode.includes("language = 'Python'"), "Python starter should stay Python");
});
