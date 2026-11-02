import { notifyAuthSessionExpired } from "../state/authSessionEvents";

export type ResourceType = "document" | "mind_map" | "exercise" | "reading" | "video" | "code_lab";

export interface StudentProfile {
  student_id: string;
  major: string;
  grade: string;
  learning_goal: string;
  course_goal?: string;
  profile_summary?: string;
  profile_version?: number;
  last_event_id?: number | null;
  last_replanned_at?: string | null;
  last_profile_update_reason?: string;
  dimension_confidence?: Record<string, number>;
  knowledge_foundation: string;
  learning_style: string;
  cognitive_style: string;
  weak_points: string[];
  strong_points?: string[];
  misconception_patterns?: string[];
  time_preference: string;
  available_days?: string[];
  weekly_time_budget_minutes?: number;
  daily_time_budget_minutes?: Record<string, number>;
  resource_preference: string[];
  modality_effectiveness?: Record<string, { uses?: number; last_score?: number; avg_score?: number }>;
  preferred_resource_order?: string[];
  motivation: string;
  motivation_profile?: Record<string, unknown>;
  motivation_level?: number;
  persistence_level?: number;
  constraints: string[];
  assessment_preference: string;
  quiz_performance?: Record<string, unknown>;
  code_performance?: Record<string, unknown>;
  application_ability?: number;
  accuracy_trend?: number[];
  completion_trend?: number[];
  affective_state?: Record<string, unknown>;
  learning_risk?: Record<string, unknown>;
  growth_trend?: Record<string, unknown>;
  knowledge_graph_focus: string[];
  confidence_score: number;
  completion_score: number;
  updated_evidence: Array<{ source: string; topic: string; detail: string }>;
}

export interface Resource {
  id: string;
  type: ResourceType;
  title: string;
  topic: string;
  content: string;
  recommendation_reason: string;
  tags: string[];
  citation_chunk_ids?: Array<number | string>;
  grounding_status?: string;
  verification_notes?: string[];
  quality_score?: {
    accuracy: number;
    personalization: number;
    completeness: number;
    operability: number;
  };
}

export interface LearningStage {
  title: string;
  goal: string;
  estimated_minutes: number;
  resources: Resource[];
  practice_task: string;
  recommendation_reason: string;
}

export interface LearningPath {
  student_id: string;
  stages: LearningStage[];
}

export interface CourseLearningStage {
  node_id: string;
  topic: string;
  level: number;
  order: number;
  mastery_status: string;
  mastery_score?: number | null;
  priority_score: number;
  path_status: "open" | "current" | "locked" | "passed" | string;
  is_current: boolean;
  is_locked: boolean;
  is_remedial: boolean;
  estimated_minutes: number;
  scheduled_day: string;
  scheduled_date: string;
  scheduled_minutes: number;
  schedule_label: string;
  is_today_task: boolean;
  task_type: "minimum" | "stretch" | string;
  is_minimum_task: boolean;
  is_stretch_task: boolean;
  goal: string;
  practice_task: string;
  graph_basis: string[];
  profile_basis: string[];
  recommended_resource_types: ResourceType[];
  recommendation_reason: string;
}

export interface CourseLearningChapter {
  id: string;
  title: string;
  order: number;
  total_nodes: number;
  completed_nodes: number;
  is_active: boolean;
  is_complete: boolean;
}

export interface CourseLearningPath {
  student_id: string;
  course_id: number;
  plan_type: "main" | "remedial" | string;
  focus_node_id: string;
  current_stage_id: string;
  pass_threshold: number;
  is_dynamic: boolean;
  adjustment_basis: string[];
  weekly_time_budget_minutes: number;
  planned_minutes: number;
  minimum_task_count: number;
  stretch_task_count: number;
  schedule_days: string[];
  schedule_summary: string;
  active_chapter_id: string;
  active_chapter_title: string;
  chapters: CourseLearningChapter[];
  stages: CourseLearningStage[];
}

export interface CourseLearningPathRequest {
  plan_type?: "main" | "remedial";
  focus_node_id?: string;
  chapter_id?: string;
}

export interface WorkflowPackage {
  event: string;
  profile: StudentProfile;
  resources: Resource[];
  learning_path: LearningPath;
  from_cache?: boolean;
  lesson_state?: LessonState;
  openmaic_classroom?: OpenMAICClassroom;
  knowledge_context?: KnowledgeContextItem[];
  graph_constraints?: GraphConstraints;
  retrieval_trace?: RetrievalTraceItem[];
  analysis_plan?: AnalysisPlan;
  verification_report?: VerificationReport;
  pedagogy_report?: PedagogyReport;
  debate_report?: DebateReport;
  decision_report?: DecisionReport;
  agent_events?: AgentEvent[];
}

export interface OpenMAICClassroom {
  job_id: string;
  status: string;
  step: string;
  poll_url: string;
  poll_interval_ms?: number;
  url: string;
  classroom_id: string;
  requirement: string;
  error?: string;
}

export interface LessonState {
  course_id: number;
  node_id: string;
  topic: string;
  current_stage: "classroom" | "artifacts" | "test" | "assessment" | string;
  classroom_completed: boolean;
  notes_completed: boolean;
  mind_map_completed: boolean;
  code_lab_completed?: boolean;
  test_completed: boolean;
  assessment_completed: boolean;
  score?: number | null;
}

export interface LessonStateUpdatePayload {
  course_id: number;
  node_id: string;
  current_stage?: string;
  classroom_completed?: boolean;
  notes_completed?: boolean;
  mind_map_completed?: boolean;
  code_lab_completed?: boolean;
  test_completed?: boolean;
  assessment_completed?: boolean;
  score?: number | null;
  openmaic_classroom?: OpenMAICClassroom;
}

export interface KnowledgeContextItem {
  chunk_id?: number | string | null;
  source_locator: string;
  content: string;
  distance?: number | null;
  heading?: string;
  retrieval_query?: string;
  storage?: string;
}

export interface GraphNodeRef {
  id: string;
  name: string;
  node_type?: string;
  summary?: string;
  level?: number | null;
  parent_id?: string;
  relation_type?: string;
  relation_reason?: string;
}

export interface GraphConstraints {
  current_node?: GraphNodeRef;
  parent?: GraphNodeRef | null;
  predecessors?: GraphNodeRef[];
  successors?: GraphNodeRef[];
  related?: GraphNodeRef[];
  source_chunk_ids?: Array<number | string>;
}

export interface RetrievalTraceItem {
  query: string;
  vector_chunk_id?: number | string | null;
  mysql_chunk_id?: number | string | null;
  source_locator?: string | null;
  distance?: number | null;
  strategy?: string;
}

export interface VerificationReport {
  decision: string;
  evidence_count: number;
  graph_constraint_count: number;
  citation_chunk_ids?: Array<number | string>;
  notes?: string[];
  fact_score?: number;
  pedagogy_score?: number;
  hallucination_risk?: string;
  unsupported_claims?: string[];
}

export interface AnalysisPlan {
  agent: string;
  topic: string;
  student_profile_basis?: Record<string, unknown>;
  resource_blueprint?: {
    topic: string;
    learning_objectives?: string[];
    prerequisites?: string[];
    successors?: string[];
    key_claims?: string[];
    misconceptions?: string[];
    difficulty_level?: string;
    style_policy?: string;
    evidence_chunk_ids?: Array<number | string>;
    graph_scope?: Record<string, unknown>;
    resource_requirements?: Record<string, Record<string, unknown>>;
  };
  risk_points?: string[];
}

export interface PedagogyReport {
  agent: string;
  score: number;
  decision: string;
  missing_resource_types?: string[];
  profile_alignment?: string[];
}

export interface DebateReport {
  agent: string;
  decision: string;
  disagreements?: string[];
  unsupported_claims?: string[];
  debate_summary: string;
}

export interface DecisionReport {
  agent: string;
  decision: string;
  next_action: string;
  revision_count: number;
  max_revision_count: number;
  reason: string;
  fallback_available: boolean;
  scores?: {
    fact_score?: number;
    pedagogy_score?: number;
  };
}

export interface AgentEvent {
  event: string;
  agent: string;
  resource_type?: ResourceType;
  summary: string;
  resources?: Resource[];
}

export interface TutorAttachment {
  id?: string;
  filename?: string;
  content_type?: string;
  description?: string;
  data_url?: string;
}

export interface TutorChatPayload {
  course_id: number;
  message: string;
  node_id?: string;
  page_context?: string;
  attachments?: TutorAttachment[];
  history?: Array<{ role: string; content: string }>;
  /** 学习状态感知（issue #15）：focused/confused/distracted/tired/no_face */
  attention_state?: string;
}

export interface TutorAgentEvent {
  event: string;
  agent: string;
  summary: string;
  status: "pending" | "running" | "completed" | "failed";
  detail: Record<string, unknown>;
}

export interface TutorEvidenceChunk {
  chunk_id?: number | string | null;
  source_locator: string;
  heading: string;
  content: string;
  retrieval_query: string;
  distance?: number | null;
  storage: string;
}

export interface TutorMultimodalCard {
  type: "text_explanation" | "diagram" | "code_hint" | "exercise" | "video_script" | "source_evidence";
  title: string;
  content: string;
  payload: Record<string, unknown>;
}

export interface TutorSuggestedAction {
  type: "continue_chat" | "open_graph" | "open_learning_path" | "open_lesson" | "open_assessment" | "build_knowledge_base";
  label: string;
  target: string;
  payload: Record<string, unknown>;
}

export interface TutorChatResponse {
  answer: string;
  agent_events: TutorAgentEvent[];
  analysis_plan: Record<string, unknown>;
  retrieval_trace: RetrievalTraceItem[];
  graph_constraints: GraphConstraints;
  evidence_chunks: TutorEvidenceChunk[];
  verification_report: Record<string, unknown>;
  decision_report: Record<string, unknown>;
  multimodal_cards: TutorMultimodalCard[];
  suggested_actions: TutorSuggestedAction[];
  suggested_followups?: string[];
}

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  user: AuthUser;
}

export interface Course {
  id: number;
  user_id: number;
  name: string;
  major: string;
  level: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface CourseMaterial {
  id: number;
  course_id: number;
  user_id: number;
  filename: string;
  file_type: string;
  size_bytes: number;
  parse_status: string;
  parse_error: string;
  ocr_used: boolean;
  created_at: string;
}

export interface KnowledgeChunk {
  id: number;
  course_id: number;
  material_id: number;
  chunk_index: number;
  source_locator: string;
  heading: string;
  content: string;
  token_count: number;
  embedding_id: string;
}

export interface SemanticSearchResult {
  id: string;
  chunk_id: number | null;
  course_id: number | null;
  source_locator: string | null;
  content: string | null;
  distance: number | null;
}

export interface VectorIndexRebuildResult {
  course_id: number;
  indexed_chunks: number;
}

export interface KnowledgeGraph {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}

export interface AssessmentReport {
  student_id: string;
  mastery: Record<string, number>;
  weak_points: string[];
  next_adjustment: string;
  dimension_scores?: Record<string, number>;
  final_score?: number;
  passed?: boolean;
  mastery_status?: string;
  feedback?: string[];
  profile_update?: ProfileUpdateSummary;
}

export interface ProfileUpdateSummary {
  course_id?: number;
  event_id?: number;
  log_id?: number | null;
  revision_id?: number | null;
  changed_dimensions?: string[];
  update_reason?: string;
  replan_required?: boolean;
  profile_summary?: string;
}

export interface LearningProfileEventCreatePayload {
  event_type: string;
  topic?: string;
  knowledge_node_id?: string;
  lesson_session_id?: number | null;
  detail?: string;
  event_payload?: Record<string, unknown>;
  evidence_strength?: string | null;
  score?: number | null;
}

export interface LearningProfileEvent {
  id: number;
  user_id: number;
  course_id: number;
  student_profile_id: number;
  knowledge_node_id: string;
  lesson_session_id?: number | null;
  event_type: string;
  topic: string;
  detail: string;
  event_payload: Record<string, unknown>;
  evidence_strength: string;
  score?: number | null;
  created_at: string;
}

export interface LearningProfileEventCreateResult {
  event: LearningProfileEvent;
  profile_update: ProfileUpdateSummary;
}

export interface ProfileUpdateLog {
  id: number;
  user_id: number;
  course_id: number;
  student_profile_id: number;
  source_event_id: number;
  changed_dimensions: string[];
  before_snapshot: Record<string, unknown>;
  after_snapshot: Record<string, unknown>;
  update_reason: string;
  confidence_delta: number;
  created_at: string;
}

export interface LearningPathRevision {
  id: number;
  user_id: number;
  course_id: number;
  trigger_type: string;
  trigger_event_id?: number | null;
  trigger_node_id: string;
  previous_plan: Record<string, unknown>;
  next_plan: Record<string, unknown>;
  change_summary: string;
  created_at: string;
}

export interface AssessmentSubmitPayload {
  student_id: string;
  event_type: "resource_viewed" | "exercise_submitted" | "feedback_submitted" | "tutor_question";
  topic: string;
  course_id?: number;
  knowledge_node_id?: string;
  score?: number;
  detail?: string;
}

export interface QuizAnswerPayload {
  id: string;
  dimension: string;
  correct: boolean;
  prompt?: string;
  options?: string[];
  correct_answer_index?: number;
  selected_answer_index?: number;
  weight: number;
}

export interface CodeAttemptPayload {
  prompt: string;
  code: string;
  expected_output: string;
  actual_output: string;
  passed: boolean;
  attempts: number;
}

export interface ComprehensiveAssessmentPayload {
  student_id: string;
  topic: string;
  course_id?: number;
  knowledge_node_id?: string;
  classroom_completed: boolean;
  notes_completed: boolean;
  mind_map_completed: boolean;
  code_lab_completed: boolean;
  quiz_answers: QuizAnswerPayload[];
  code_attempt?: CodeAttemptPayload;
  detail?: string;
}

export interface CourseCreatePayload {
  name: string;
  major?: string;
  level?: string;
  description?: string;
}

export interface ProfileInterview {
  id: number;
  user_id: number;
  course_id?: number | null;
  status: "in_progress" | "ready_to_confirm" | "confirmed";
  turn_count: number;
  current_question: string;
  profile: StudentProfile;
  created_at: string;
  updated_at: string;
}

function authHeaders(token?: string): HeadersInit {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export function isUnauthorizedError(error: unknown): boolean {
  return error instanceof ApiRequestError && (error.status === 401 || error.status === 403);
}

async function apiError(response: Response, fallback: string): Promise<Error> {
  const payload = await response.json().catch(() => undefined) as { detail?: unknown } | undefined;
  const detail = typeof payload?.detail === "string" ? payload.detail : "";
  if (response.status === 401 || response.status === 403) {
    notifyAuthSessionExpired();
  }
  return new ApiRequestError(detail || `${fallback}: ${response.status}`, response.status);
}

export async function registerUser(username: string, email: string, password: string): Promise<AuthResponse> {
  const response = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, email, password })
  });
  if (!response.ok) {
    throw new Error(response.status === 409 ? "用户名或邮箱已注册" : "注册失败");
  }
  return response.json();
}

export async function loginUser(account: string, password: string): Promise<AuthResponse> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account, password })
  });
  if (!response.ok) {
    throw new Error("账号或密码错误");
  }
  return response.json();
}

export async function getCurrentUser(token: string): Promise<AuthUser> {
  const response = await fetch("/api/auth/me", {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "登录状态已失效");
  }
  return response.json();
}

export interface GenerateLearningPackagePayload {
  conversation: string;
  topic: string;
  course_id?: number;
  node_id?: string;
  resource_types?: ResourceType[];
  force_regenerate?: boolean;
}

export async function generateLearningPackage(
  payload: GenerateLearningPackagePayload,
  token?: string
): Promise<WorkflowPackage> {
  const response = await fetch("/api/resources/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`鐢熸垚澶辫触锛?{response.status}`);
  }
  return response.json();
}

export async function pollOpenMAICClassroom(
  token: string | undefined,
  jobId: string,
  pollUrl = ""
): Promise<OpenMAICClassroom> {
  const params = pollUrl ? `?poll_url=${encodeURIComponent(pollUrl)}` : "";
  const pollJobId = jobId || "_";
  const response = await fetch(`/api/resources/openmaic-jobs/${encodeURIComponent(pollJobId)}${params}`, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "鏌ヨ OpenMAIC 璇惧爞浠诲姟澶辫触");
  }
  return response.json();
}

export async function updateLessonState(
  token: string | undefined,
  payload: LessonStateUpdatePayload
): Promise<LessonState> {
  const response = await fetch("/api/resources/lessons/state", {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw await apiError(response, "更新课堂状态失败");
  }
  return response.json();
}

export async function startProfileInterview(token: string, courseId?: number): Promise<ProfileInterview> {
  const response = await fetch("/api/profile-interviews", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ course_id: courseId ?? null })
  });
  if (!response.ok) {
    throw await apiError(response, "鍒涘缓鐢诲儚璁胯皥澶辫触");
  }
  return response.json();
}

export async function answerProfileInterview(
  token: string,
  interviewId: number,
  answer: string,
  topic = ""
): Promise<ProfileInterview> {
  const response = await fetch(`/api/profile-interviews/${interviewId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ answer, topic })
  });
  if (!response.ok) {
    throw await apiError(response, "鎻愪氦鐢诲儚鍥炵瓟澶辫触");
  }
  return response.json();
}

export async function confirmProfileInterview(token: string, interviewId: number): Promise<{ profile: StudentProfile }> {
  const response = await fetch(`/api/profile-interviews/${interviewId}/confirm`, {
    method: "POST",
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "纭鐢诲儚澶辫触");
  }
  return response.json();
}

export async function getMyProfile(token: string, courseId?: number): Promise<StudentProfile | undefined> {
  const params = courseId ? `?course_id=${encodeURIComponent(String(courseId))}` : "";
  const response = await fetch(`/api/profiles/me${params}`, {
    headers: authHeaders(token)
  });
  if (response.status === 404) {
    return undefined;
  }
  if (!response.ok) {
    throw await apiError(response, "鍔犺浇瀛︾敓鐢诲儚澶辫触");
  }
  return response.json();
}

export async function listCourses(token: string): Promise<Course[]> {
  const response = await fetch("/api/courses", {
    headers: authHeaders(token),
    cache: "no-store"
  });
  if (!response.ok) {
    throw await apiError(response, "鍔犺浇璇剧▼澶辫触");
  }
  return response.json();
}

export async function getCourse(token: string, courseId: number): Promise<Course> {
  const response = await fetch(`/api/courses/${courseId}`, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "鍔犺浇璇剧▼澶辫触");
  }
  return response.json();
}

export async function createCourse(token: string, payload: CourseCreatePayload): Promise<Course> {
  const response = await fetch("/api/courses", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw await apiError(response, "鍒涘缓璇剧▼澶辫触");
  }
  return response.json();
}

export async function ensureDefaultPythonCourse(token: string): Promise<Course> {
  const response = await fetch("/api/courses/default-python", {
    method: "POST",
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "创建 Python 示例知识库失败");
  }
  return response.json();
}

export async function ensureDefaultCCourse(token: string): Promise<Course> {
  const response = await fetch("/api/courses/default-c", {
    method: "POST",
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "创建 C 语言示例知识库失败");
  }
  return response.json();
}

export async function applyBuiltInKnowledgeBase(
  token: string,
  courseId: number,
  template: "python" | "c"
): Promise<Course> {
  const response = await fetch(`/api/courses/${courseId}/builtin-knowledge-base`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ template })
  });
  if (!response.ok) {
    throw await apiError(response, "使用内置知识库失败");
  }
  return response.json();
}

export async function uploadMaterial(token: string, courseId: number, file: File): Promise<CourseMaterial> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`/api/courses/${courseId}/materials`, {
    method: "POST",
    headers: authHeaders(token),
    body: formData
  });
  if (!response.ok) {
    throw await apiError(response, "涓婁紶璧勬枡澶辫触");
  }
  return response.json();
}

export async function listMaterials(token: string, courseId: number): Promise<CourseMaterial[]> {
  const response = await fetch(`/api/courses/${courseId}/materials`, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "鍔犺浇璇剧▼璧勬枡澶辫触");
  }
  return response.json();
}

export async function listChunks(token: string, courseId: number): Promise<KnowledgeChunk[]> {
  const response = await fetch(`/api/courses/${courseId}/chunks`, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "鍔犺浇鐭ヨ瘑鍒囩墖澶辫触");
  }
  return response.json();
}

export async function semanticSearch(
  token: string,
  courseId: number,
  query: string
): Promise<SemanticSearchResult[]> {
  const response = await fetch(`/api/courses/${courseId}/semantic-search?q=${encodeURIComponent(query)}`, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "语义检索失败");
  }
  return response.json();
}

export async function rebuildVectorIndex(token: string, courseId: number): Promise<VectorIndexRebuildResult> {
  const response = await fetch(`/api/courses/${courseId}/vector-index/rebuild`, {
    method: "POST",
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "閲嶅缓鍚戦噺绱㈠紩澶辫触");
  }
  return response.json();
}

export async function buildKnowledgeGraph(token: string, courseId: number): Promise<KnowledgeGraph> {
  const response = await fetch(`/api/courses/${courseId}/knowledge-graph/build`, {
    method: "POST",
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "鏋勫缓鐭ヨ瘑鍥捐氨澶辫触");
  }
  return response.json();
}

export async function getKnowledgeGraph(token: string, courseId: number): Promise<KnowledgeGraph> {
  const response = await fetch(`/api/courses/${courseId}/knowledge-graph`, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "鍔犺浇鐭ヨ瘑鍥捐氨澶辫触");
  }
  return response.json();
}

export async function planCourseLearningPath(
  token: string | undefined,
  courseId: number,
  payload: CourseLearningPathRequest = {}
): Promise<CourseLearningPath> {
  const response = await fetch(`/api/courses/${courseId}/learning-paths/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw await apiError(response, "鐢熸垚瀛︿範璺緞澶辫触");
  }
  return response.json();
}

export async function createLearningProfileEvent(
  token: string | undefined,
  courseId: number,
  payload: LearningProfileEventCreatePayload
): Promise<LearningProfileEventCreateResult> {
  const response = await fetch(`/api/courses/${courseId}/profile-events`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw await apiError(response, "记录学习画像事件失败");
  }
  return response.json();
}

export async function listLearningProfileEvents(
  token: string | undefined,
  courseId: number
): Promise<LearningProfileEvent[]> {
  const response = await fetch(`/api/courses/${courseId}/profile-events`, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "加载学习画像事件失败");
  }
  return response.json();
}

export async function listProfileUpdateLogs(
  token: string | undefined,
  courseId: number
): Promise<ProfileUpdateLog[]> {
  const response = await fetch(`/api/courses/${courseId}/profile-update-logs`, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "加载画像更新日志失败");
  }
  return response.json();
}

export async function listLearningPathRevisions(
  token: string | undefined,
  courseId: number
): Promise<LearningPathRevision[]> {
  const response = await fetch(`/api/courses/${courseId}/learning-path-revisions`, {
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "加载学习路径调整历史失败");
  }
  return response.json();
}

export async function submitAssessment(token: string, payload: AssessmentSubmitPayload | ComprehensiveAssessmentPayload): Promise<AssessmentReport> {
  const response = await fetch("/api/assessments/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw await apiError(response, "鎻愪氦瀛︿範璇勪及澶辫触");
  }
  return response.json();
}

export async function sendTutorMessage(
  token: string | undefined,
  payload: TutorChatPayload,
  timeoutMs = 120000
): Promise<TutorChatResponse> {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch("/api/tutor/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders(token) },
      body: JSON.stringify(payload),
      signal: controller.signal
    });
    if (!response.ok) {
      throw await apiError(response, "智能辅导请求失败");
    }
    return response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("智能辅导请求超时，请稍后重试");
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
}

export async function deleteMaterial(token: string, courseId: number, materialId: number): Promise<void> {
  const response = await fetch(`/api/courses/${courseId}/materials/${materialId}`, {
    method: "DELETE",
    headers: authHeaders(token)
  });
  if (!response.ok) {
    throw await apiError(response, "鍒犻櫎璧勬枡澶辫触");
  }
}
