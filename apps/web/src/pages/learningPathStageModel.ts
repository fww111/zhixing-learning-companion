import type { CourseLearningStage } from "../api/client";

export function learningTargetNodeId(stage: Pick<CourseLearningStage, "node_id">): string {
  return stage.node_id.split("::remedial::", 1)[0] || stage.node_id;
}

export function canOpenLearningPathStage(stage: Pick<CourseLearningStage, "path_status">): boolean {
  return stage.path_status !== "locked";
}

export function chapterSwitchSearchParams(currentSearch: string, chapterId: string): string {
  const nextParams = new URLSearchParams(currentSearch);
  nextParams.delete("mode");
  nextParams.delete("focus");
  if (chapterId) {
    nextParams.set("chapter", chapterId);
  } else {
    nextParams.delete("chapter");
  }
  return nextParams.toString();
}

export function cleanChapterTitle(title: string): string {
  return title
    .replace(/\s*\.{2,}\s*\d+\s*CONTENTS\s*$/i, "")
    .replace(/\s+\d+\s*CONTENTS\s*$/i, "")
    .replace(/\s*CONTENTS\s*$/i, "")
    .trim();
}
