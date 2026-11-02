import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "../layouts/AppLayout";
import { AuthPage } from "../pages/AuthPage";
import { CourseAssessmentPage } from "../pages/CourseAssessmentPage";
import { CourseGraphPage } from "../pages/CourseGraphPage";
import { CourseKnowledgeBasePage } from "../pages/CourseKnowledgeBasePage";
import { CourseLearningPathPage } from "../pages/CourseLearningPathPage";
import { CourseWrongQuestionsPage } from "../pages/CourseWrongQuestionsPage";
import { CoursesPage } from "../pages/CoursesPage";
import { KnowledgeLearningPage } from "../pages/KnowledgeLearningPage";
import { ProfileInterviewPage } from "../pages/ProfileInterviewPage";
import { TutorStagePage } from "../pages/TutorStagePage";
import { AuthProvider } from "../state/auth";
import { RedirectBySession, RequireAuth, RequireCourseProfile } from "./guards";

export function AppRouter() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<RedirectBySession />} path="/" />
          <Route element={<AuthPage />} path="/auth" />
          <Route element={<RequireAuth />}>
              <Route element={<AppLayout />}>
                <Route element={<ProfileInterviewPage />} path="/profile/interview" />
                <Route element={<CoursesPage />} path="/courses" />
                <Route element={<ProfileInterviewPage />} path="/courses/:courseId/profile/interview" />
                <Route element={<RequireCourseProfile />}>
                <Route element={<CourseKnowledgeBasePage />} path="/courses/:courseId/knowledge-base" />
                <Route element={<CourseGraphPage />} path="/courses/:courseId/graph" />
                <Route element={<CourseLearningPathPage />} path="/courses/:courseId/learning-path" />
                <Route element={<CourseAssessmentPage />} path="/courses/:courseId/assessment" />
                <Route element={<CourseWrongQuestionsPage />} path="/courses/:courseId/assessment/wrong-questions" />
                <Route element={<KnowledgeLearningPage />} path="/courses/:courseId/knowledge/:nodeId" />
                <Route element={<TutorStagePage />} path="/courses/:courseId/tutor-stage" />
              </Route>
            </Route>
          </Route>
          <Route element={<Navigate replace to="/" />} path="*" />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
