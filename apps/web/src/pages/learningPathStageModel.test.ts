import { canOpenLearningPathStage, chapterSwitchSearchParams, cleanChapterTitle, learningTargetNodeId } from "./learningPathStageModel.js";

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

test("locked learning path stages are not openable", () => {
  assert(!canOpenLearningPathStage({ path_status: "locked" }), "locked stage should not open");
  assert(canOpenLearningPathStage({ path_status: "current" }), "current stage should open");
  assert(canOpenLearningPathStage({ path_status: "open" }), "open stage should open");
  assert(canOpenLearningPathStage({ path_status: "passed" }), "passed stage should open for review");
});

test("chapter switching leaves remedial focus mode", () => {
  const search = chapterSwitchSearchParams("mode=remedial&focus=node-1&chapter=chapter-1", "chapter-3");
  assert(search === "chapter=chapter-3", `unexpected params: ${search}`);
});

test("synthetic remedial stages open the original graph node", () => {
  assert(
    learningTargetNodeId({ node_id: "concept-a::remedial::assessment-weakness" }) === "concept-a",
    "remedial route should use the source graph node id for RAG and graph constraints"
  );
  assert(learningTargetNodeId({ node_id: "concept-b" }) === "concept-b", "ordinary stages should keep their own node id");
});

test("cleans table-of-contents residue from chapter titles", () => {
  assert(
    cleanChapterTitle("第 3 章 最简单的 C 程序设计——顺序程序设计 ... 37 CONTENTS") ===
      "第 3 章 最简单的 C 程序设计——顺序程序设计",
    "C chapter title should remove page number and CONTENTS residue"
  );
  assert(
    cleanChapterTitle("第 1 章 程序设计和 C 语言") === "第 1 章 程序设计和 C 语言",
    "clean titles should stay unchanged"
  );
});
