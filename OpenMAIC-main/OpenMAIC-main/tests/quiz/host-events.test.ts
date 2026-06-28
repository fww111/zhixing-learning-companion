import { describe, expect, it } from 'vitest';
import { buildQuizHostEvent } from '@/lib/quiz/host-events';

describe('buildQuizHostEvent', () => {
  it('builds a host-visible event when a classroom quiz starts', () => {
    expect(
      buildQuizHostEvent('openmaic:quiz-started', {
        questionCount: 3,
        sceneId: 'quiz-1',
        totalPoints: 100,
      }),
    ).toEqual({
      type: 'openmaic:quiz-started',
      questionCount: 3,
      sceneId: 'quiz-1',
      totalPoints: 100,
    });
  });

  it('builds a host-visible event when a classroom quiz is completed', () => {
    expect(
      buildQuizHostEvent('openmaic:quiz-completed', {
        earnedScore: 80,
        questionCount: 3,
        sceneId: 'quiz-1',
        totalPoints: 100,
      }),
    ).toMatchObject({
      type: 'openmaic:quiz-completed',
      earnedScore: 80,
      sceneId: 'quiz-1',
    });
  });
});
