import {
  buildMindMapTree,
  splitMindMapBranches
} from "./mindMapModel.js";

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

test("groups flat LLM mind-map text into branches with leaves", () => {
  const tree = buildMindMapTree([
    "# 1.1 初识 Python",
    "*定义与定位",
    "高级通用编程语言",
    "解释型、动态类型",
    "*历史与版本",
    "创建者：Guido van Rossum",
    "1991 年公开发布",
    "*核心特点",
    "简洁易读",
    "跨平台",
    "*典型应用领域",
    "数据科学与分析",
    "人工智能与机器学习",
    "*Hello World 示例",
    "print(\"Hello, world!\")",
    "*常见误区",
    "忽略缩进"
  ].join("\n"), "初识 Python");

  assert(tree.label === "1.1 初识 Python", `unexpected root: ${tree.label}`);
  assert(tree.children.length === 6, `expected six branches, got ${tree.children.length}`);
  assert(tree.children[0].label === "定义与定位", `unexpected first branch: ${tree.children[0].label}`);
  assert(tree.children[0].children.length === 2, "flat statements should become leaves under the branch");

  const [left, right] = splitMindMapBranches(tree.children);
  assert(left.length > 0 && right.length > 0, "branches should be split across both sides");
});

test("uses graph constraints and evidence when generated mind-map content has only a title", () => {
  const tree = buildMindMapTree("# 变量", "变量", {
    graphConstraints: {
      current_node: { name: "变量", summary: "变量用于保存程序运行中的数据。" },
      parent: { name: "第 2 章 基础语法" },
      predecessors: [{ name: "解释器与执行方式" }],
      successors: [{ name: "数据类型" }, { name: "表达式" }],
      related: [{ name: "赋值语句" }]
    },
    knowledgeContext: [
      {
        heading: "变量与赋值",
        content: "变量名指向对象，赋值语句会让名称绑定到新的对象。"
      }
    ],
    tags: ["Python 入门"]
  });

  assert(tree.children.length >= 4, `fallback should create branches, got ${tree.children.length}`);
  assert(
    tree.children.some((branch) => branch.label === "核心内容" && branch.children.length > 0),
    "fallback should include evidence-backed core content"
  );
  assert(
    tree.children.some((branch) => branch.label === "后续衔接"),
    "fallback should include graph successor branch"
  );
});
