import React from 'react';

import CourseManager from '../CourseManager';
import LessonManager from '../LessonManager';
import ContentViewer from '../ContentViewer';
import QuestionGenerator from '../QuestionGenerator';
import QuestionBank from '../QuestionBank';
import ManualQuestionAdder from '../ManualQuestionAdder';
import QuizBuilder from '../QuizBuilder';
import QuizSolver from '../QuizSolver';
import TranslationManager from '../TranslationManager';
import SPARQLQueryTool from '../SPARQLQueryTool';
import EduQGBenchmark from '../EduQGBenchmark';

function MissingSelection({ message, target, onGoTo }) {
  return (
    <div className="card">
      <p>{message}</p>
      <button className="btn-primary" onClick={() => onGoTo(target)}>
        {target === 'courses' ? 'Go to Courses' : 'Go to Lessons'}
      </button>
    </div>
  );
}

function TabContent({
  activeTab,
  setActiveTab,
  courses,
  selectedCourse,
  selectedLesson,
  setSelectedCourse,
  setSelectedLesson,
  questions,
  setQuestions,
  loading,
  fetchCourses,
  fetchQuestions,
  handleSelectCourse,
  handleSelectLesson,
  showSuccess,
  showError,
}) {
  switch (activeTab) {
    case 'courses':
      return (
        <CourseManager
          courses={courses}
          onSelectCourse={handleSelectCourse}
          onCoursesChange={fetchCourses}
          onSuccess={showSuccess}
          onError={showError}
          loading={loading}
        />
      );

    case 'lessons':
      return selectedCourse ? (
        <LessonManager
          course={selectedCourse}
          onSelectLesson={handleSelectLesson}
          onLessonsChange={() => handleSelectCourse(selectedCourse)}
          onSuccess={showSuccess}
          onError={showError}
          onBack={() => {
            setSelectedCourse(null);
            setActiveTab('courses');
          }}
          loading={loading}
        />
      ) : (
        <MissingSelection
          message="Please select a course first"
          target="courses"
          onGoTo={setActiveTab}
        />
      );

    case 'content':
      return selectedLesson ? (
        <ContentViewer
          lesson={selectedLesson}
          onBack={() => setActiveTab('lessons')}
          onSuccess={showSuccess}
          onError={showError}
          onLessonUpdate={(updatedLesson) => setSelectedLesson(updatedLesson)}
        />
      ) : (
        <MissingSelection
          message="Please select a lesson first"
          target="lessons"
          onGoTo={setActiveTab}
        />
      );

    case 'generate':
      return selectedCourse ? (
        <QuestionGenerator
          course={selectedCourse}
          onQuestionsGenerated={(newQuestions) => {
            setQuestions([...questions, ...newQuestions]);
            showSuccess(`Generated ${newQuestions.length} questions!`);
          }}
          onSuccess={showSuccess}
          onError={showError}
          loading={loading}
        />
      ) : (
        <MissingSelection
          message="Please select a course first to generate questions"
          target="courses"
          onGoTo={setActiveTab}
        />
      );

    case 'questions':
      return (
        <div className="questions-section">
          {selectedCourse && (
            <ManualQuestionAdder
              courseId={selectedCourse.id}
              lessons={selectedCourse.lessons || []}
              onSuccess={showSuccess}
              onError={showError}
              onRefresh={() => fetchQuestions(selectedCourse?.id)}
            />
          )}
          <QuestionBank
            questions={questions}
            courseId={selectedCourse?.id}
            onRefresh={() => fetchQuestions(selectedCourse?.id)}
            onSuccess={showSuccess}
            onError={showError}
          />
        </div>
      );

    case 'quizzes':
      return (
        <QuizBuilder
          questions={questions}
          course={selectedCourse}
          onSuccess={showSuccess}
          onError={showError}
        />
      );

    case 'solve':
      return selectedCourse ? (
        <QuizSolver
          courseId={selectedCourse.id}
          onBack={() => setActiveTab('quizzes')}
          onSuccess={showSuccess}
          onError={showError}
        />
      ) : (
        <MissingSelection
          message="Please select a course first to take quizzes"
          target="courses"
          onGoTo={setActiveTab}
        />
      );

    case 'translate':
      return <TranslationManager />;

    case 'sparql':
      return <SPARQLQueryTool />;

    case 'eduqg':
      return <EduQGBenchmark />;

    default:
      return null;
  }
}

export default TabContent;
