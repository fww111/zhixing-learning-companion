export type QuizHostEventType =
  | 'openmaic:quiz-started'
  | 'openmaic:quiz-submitted'
  | 'openmaic:quiz-completed';

export interface QuizHostEventPayload {
  readonly answeredCount?: number;
  readonly earnedScore?: number;
  readonly questionCount: number;
  readonly sceneId: string;
  readonly totalPoints?: number;
}

export function buildQuizHostEvent(type: QuizHostEventType, payload: QuizHostEventPayload) {
  return {
    type,
    ...payload,
  };
}
