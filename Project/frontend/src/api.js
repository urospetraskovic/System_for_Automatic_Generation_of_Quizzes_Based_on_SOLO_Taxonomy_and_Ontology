/**
 * API Client Module
 * Centralized API calls for all backend endpoints
 * Eliminates scattered axios calls throughout the application
 */

import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000/api';

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ==================== COURSE ENDPOINTS ====================

export const courseApi = {
  getAll: () => apiClient.get('/courses'),
  getById: (courseId) => apiClient.get(`/courses/${courseId}`),
  create: (courseData) => apiClient.post('/courses', courseData),
  update: (courseId, courseData) => apiClient.put(`/courses/${courseId}`, courseData),
  delete: (courseId) => apiClient.delete(`/courses/${courseId}`),
};

// ==================== LESSON ENDPOINTS ====================

export const lessonApi = {
  getForCourse: (courseId) => apiClient.get(`/courses/${courseId}/lessons`),
  getById: (lessonId) => apiClient.get(`/lessons/${lessonId}`),
  create: (courseId, formData) => apiClient.post(`/courses/${courseId}/lessons`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  delete: (lessonId) => apiClient.delete(`/lessons/${lessonId}`),
  parse: (lessonId) => apiClient.post(`/lessons/${lessonId}/parse`),
  getSections: (lessonId) => apiClient.get(`/lessons/${lessonId}/sections`),
  getOntology: (lessonId) => apiClient.get(`/lessons/${lessonId}/ontology`),
  clearOntology: (lessonId) => apiClient.post(`/lessons/${lessonId}/ontology/clear`),
  generateOntology: (lessonId) => apiClient.post(`/lessons/${lessonId}/ontology/generate`),
  getCoverage: (lessonId) => apiClient.get(`/lessons/${lessonId}/coverage`),
};

// ==================== SECTION ENDPOINTS ====================

export const sectionApi = {
  getForLesson: (lessonId) => apiClient.get(`/lessons/${lessonId}/sections`),
  getById: (sectionId) => apiClient.get(`/sections/${sectionId}`),
  create: (lessonId, sectionData) => apiClient.post(`/lessons/${lessonId}/sections`, sectionData),
  update: (sectionId, sectionData) => apiClient.put(`/sections/${sectionId}`, sectionData),
  delete: (sectionId) => apiClient.delete(`/sections/${sectionId}`),
};

// ==================== LEARNING OBJECT ENDPOINTS ====================

export const learningObjectApi = {
  getForSection: (sectionId) => apiClient.get(`/sections/${sectionId}/learning-objects`),
  getById: (loId) => apiClient.get(`/learning-objects/${loId}`),
  create: (sectionId, loData) => apiClient.post(`/sections/${sectionId}/learning-objects`, loData),
  update: (loId, loData) => apiClient.put(`/learning-objects/${loId}`, loData),
  delete: (loId) => apiClient.delete(`/learning-objects/${loId}`),
};

// ==================== QUESTION ENDPOINTS ====================

export const questionApi = {
  getAll: (courseId = null) => {
    const params = courseId ? `?course_id=${courseId}` : '';
    return apiClient.get(`/questions${params}`);
  },
  getById: (questionId) => apiClient.get(`/questions/${questionId}`),
  create: (questionData) => apiClient.post('/questions', questionData),
  generate: (generationParams) => apiClient.post('/generate-questions', generationParams),
  // Async variant — returns { job_id, status }. Poll with jobsApi.get(jobId).
  generateAsync: (generationParams) => apiClient.post('/jobs/generate-questions', generationParams),
  // Auto-quota mode: generate questions for every lesson in a course at all
  // SOLO levels, aiming for ~85-90% slide coverage.
  generateForCourseAsync: (courseId) =>
    apiClient.post('/jobs/generate-questions-for-course', { course_id: courseId }),
  // Coverage-targeted mode: fill gaps by generating questions for LOs that
  // sit on uncovered substantive pages.
  generateForUncoveredAsync: (courseId) =>
    apiClient.post('/jobs/generate-questions-for-uncovered', { course_id: courseId }),
  // Auto-quota mode restricted to a user-selected list of lesson IDs.
  generateForLessonsAsync: (lessonIds) =>
    apiClient.post('/jobs/generate-questions-for-lessons', { lesson_ids: lessonIds }),
  delete: (questionId) => apiClient.delete(`/questions/${questionId}`),
  lint: (questionId) => apiClient.get(`/questions/${questionId}/lint`),
  lintLesson: (lessonId) => apiClient.get(`/lessons/${lessonId}/lint`),
  // Bulk hydration of every cached lesson-scoped validation report. Returns
  // {} when nothing is cached yet.
  qualityCache: (lessonId) => apiClient.get(`/lessons/${lessonId}/quality-cache`),
  clearQualityCache: (lessonId) => apiClient.delete(`/lessons/${lessonId}/quality-cache`),
  soloJudge: (questionId) => apiClient.get(`/questions/${questionId}/solo-judge`),
  soloJudgeLesson: (lessonId) => apiClient.get(`/lessons/${lessonId}/solo-judge`),
  cove: (questionId) => apiClient.get(`/questions/${questionId}/cove`),
  coveLesson: (lessonId) => apiClient.get(`/lessons/${lessonId}/cove`),
  solvability: (questionId, nTrials = 5) => apiClient.get(`/questions/${questionId}/solvability?n_trials=${nTrials}`),
  solvabilityLesson: (lessonId, nTrials = 5) => apiClient.get(`/lessons/${lessonId}/solvability?n_trials=${nTrials}`),
  // Extended validity layer (A-H).
  stemOnlySolvabilityLesson: (lessonId) => apiClient.get(`/lessons/${lessonId}/stem-only-solvability`),
  iocLesson: (lessonId) => apiClient.get(`/lessons/${lessonId}/ioc`),
  readabilityLesson: (lessonId) => apiClient.get(`/lessons/${lessonId}/readability`),
  ambiguityLesson: (lessonId) => apiClient.get(`/lessons/${lessonId}/ambiguity`),
  misconceptionMining: (lessonId) => apiClient.get(`/lessons/${lessonId}/misconception-mining`),
  grammarHomogeneityLesson: (lessonId) => apiClient.get(`/lessons/${lessonId}/grammar-homogeneity`),
  faceValidityLesson: (lessonId) => apiClient.get(`/lessons/${lessonId}/face-validity`),
};

// ==================== JOBS ENDPOINTS ====================

export const jobsApi = {
  get: (jobId) => apiClient.get(`/jobs/${jobId}`),
  list: () => apiClient.get('/jobs'),
};

// ==================== QUIZ ENDPOINTS ====================

export const quizApi = {
  getForCourse: (courseId) => apiClient.get(`/courses/${courseId}/quizzes`),
  getById: (quizId) => apiClient.get(`/quizzes/${quizId}`),
  create: (quizData) => apiClient.post('/quizzes', quizData),
  update: (quizId, quizData) => apiClient.put(`/quizzes/${quizId}`, quizData),
  delete: (quizId) => apiClient.delete(`/quizzes/${quizId}`),
  addQuestions: (quizId, questionIds) => apiClient.post(
    `/quizzes/${quizId}/questions`,
    { question_ids: questionIds }
  ),
  removeQuestion: (quizId, questionId) => apiClient.delete(
    `/quizzes/${quizId}/questions/${questionId}`
  ),
};

// ==================== HEALTH CHECK ====================

export const healthApi = {
  check: () => apiClient.get('/health'),
};

// ==================== ONTOLOGY ENDPOINTS ====================

export const ontologyApi = {
  getStats: () => apiClient.get('/ontology/stats'),
  exportFull: (format = 'json') => apiClient.get(`/ontology/export?format=${format}`),
  exportCourse: (courseId) => apiClient.get(`/ontology/export/course/${courseId}`, {
    responseType: 'blob'
  }),
  exportLesson: (lessonId) => apiClient.get(`/ontology/export/lesson/${lessonId}`, {
    responseType: 'blob'
  }),
  save: (courseId = null) => apiClient.post('/ontology/save', { course_id: courseId }),
  // Lesson-scoped (relationships table) exports — returns a Blob the caller can download.
  downloadLessonOwl: (lessonId) => apiClient.get(`/lessons/${lessonId}/ontology/export/owl`, {
    responseType: 'blob',
  }),
  downloadLessonTurtle: (lessonId) => apiClient.get(`/lessons/${lessonId}/ontology/export/turtle`, {
    responseType: 'blob',
  }),
  deleteRelationship: (relId) => apiClient.delete(`/relationships/${relId}`),
};

// ==================== SPARQL ENDPOINTS ====================

export const sparqlApi = {
  getExamples: () => apiClient.get('/sparql/examples'),
  execute: (query) => apiClient.post('/sparql', { query }),
};

// ==================== CHATBOT ENDPOINTS ====================

export const chatApi = {
  sendMessage: (message, courseId, lessonId, conversationHistory) => 
    apiClient.post('/chat', {
      message,
      course_id: courseId,
      lesson_id: lessonId,
      conversation_history: conversationHistory
    }),
  explainAnswer: (question, correctAnswer, userAnswer) =>
    apiClient.post('/chat/explain-answer', {
      question,
      correct_answer: correctAnswer,
      user_answer: userAnswer
    })
};

// ==================== TRANSLATION ENDPOINTS ====================

export const translationApi = {
  getLanguages: () => apiClient.get('/translate/languages'),
  getQuizzes: () => apiClient.get('/quizzes'),
  translateQuiz: (quizId, targetLanguage) => apiClient.post(`/translate/quiz/${quizId}`, {
    target_language: targetLanguage
  }),
  getQuizStatus: (quizId) => apiClient.get(`/translate/quiz/${quizId}/status`),
  fixQuizTranslations: (quizId, targetLanguage = null) =>
    apiClient.post(`/translate/quiz/${quizId}/fix`, { target_language: targetLanguage }),
  retranslateQuestion: (questionId, targetLanguage) =>
    apiClient.post(`/translate/question/${questionId}/retranslate`, {
      target_language: targetLanguage,
    }),
  // Translation viewer needs to fetch the full entity (with embedded translations).
  getEntity: (entityType, entityId) => {
    const pathByType = {
      question: `/questions/${entityId}`,
      lesson: `/lessons/${entityId}`,
      section: `/sections/${entityId}`,
      'learning-object': `/learning-objects/${entityId}`,
    };
    const path = pathByType[entityType];
    if (!path) {
      return Promise.reject(new Error(`Unknown entity type: ${entityType}`));
    }
    return apiClient.get(path);
  },
};

// ==================== ADMIN ENDPOINTS ====================

export const adminApi = {
  cacheStats: () => apiClient.get('/admin/llm-cache/stats'),
  clearCache: () => apiClient.delete('/admin/llm-cache'),
};

// ==================== LLM PROVIDER ENDPOINTS ====================

export const llmApi = {
  providers: () => apiClient.get('/llm/providers'),
  spend: () => apiClient.get('/llm/spend'),
  resetSpend: (providerName) =>
    apiClient.delete(`/llm/spend${providerName ? `?provider=${providerName}` : ''}`),
};

// ==================== EDUQG BENCHMARK ENDPOINTS ====================

export const eduqgApi = {
  benchmark: () => apiClient.get('/eduqg/benchmark'),
  overview: () => apiClient.get('/eduqg/overview'),
  questions: (book, offset = 0, limit = 25) =>
    apiClient.get('/eduqg/questions', { params: { book, offset, limit } }),
  evaluate: (eduqgId) => apiClient.post('/eduqg/evaluate', { eduqg_id: eduqgId }, { timeout: 60000 }),
};

// ==================== ERROR HANDLING ====================

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 500) {
      console.error('[API ERROR]', error.response.data?.error || 'Server error');
    }
    return Promise.reject(error);
  }
);

export default apiClient;
