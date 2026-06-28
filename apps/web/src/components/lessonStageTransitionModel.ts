const lessonStageOrder = ["classroom", "artifacts", "test", "assessment"];

export function shouldPersistLessonStageTransition(currentStage: string | undefined, nextStage: string): boolean {
  const currentIndex = lessonStageOrder.indexOf(currentStage || "classroom");
  const nextIndex = lessonStageOrder.indexOf(nextStage);
  if (nextIndex < 0 || currentIndex < 0) {
    return true;
  }
  return nextIndex >= currentIndex;
}
