import React, { useState } from 'react';
import './App.css';

import { LanguageProvider } from './context/LanguageContext';
import { LLMProviderProvider } from './context/LLMProviderContext';
import useAppData from './hooks/useAppData';

import Sidebar from './components/layout/Sidebar';
import TopBar from './components/layout/TopBar';
import AlertMessages from './components/layout/AlertMessages';
import HowItWorksCard from './components/layout/HowItWorksCard';
import TabContent from './components/layout/TabContent';
import ChatBot from './components/ChatBot';

function App() {
  const [activeTab, setActiveTab] = useState('courses');
  const [chatbotOpen, setChatbotOpen] = useState(false);

  const data = useAppData();
  const {
    courses,
    selectedCourse,
    selectedLesson,
    questions,
    loading,
    error,
    success,
    apiStatus,
    setSelectedCourse,
    setSelectedLesson,
    setQuestions,
    fetchCourses,
    fetchQuestions,
    handleSelectCourse,
    handleSelectLesson,
    showSuccess,
    showError,
    clearMessages,
  } = data;

  const onSelectCourse = (course) =>
    handleSelectCourse(course, () => setActiveTab('lessons'));

  const onSelectLesson = (lesson) =>
    handleSelectLesson(lesson, () => setActiveTab('content'));

  const onSelectTab = (tab) => {
    setActiveTab(tab);
    clearMessages();
  };

  return (
    <div className="app">
      <Sidebar
        activeTab={activeTab}
        selectedCourse={selectedCourse}
        selectedLesson={selectedLesson}
        onSelectTab={onSelectTab}
        onFetchQuestions={fetchQuestions}
      />

      <div className="main-container">
        <TopBar
          selectedCourse={selectedCourse}
          selectedLesson={selectedLesson}
          apiStatus={apiStatus}
        />

        <main className="main-content">
          <div className="container">
            <AlertMessages apiStatus={apiStatus} error={error} success={success} />

            <TabContent
              activeTab={activeTab}
              setActiveTab={setActiveTab}
              courses={courses}
              selectedCourse={selectedCourse}
              selectedLesson={selectedLesson}
              setSelectedCourse={setSelectedCourse}
              setSelectedLesson={setSelectedLesson}
              questions={questions}
              setQuestions={setQuestions}
              loading={loading}
              fetchCourses={fetchCourses}
              fetchQuestions={fetchQuestions}
              handleSelectCourse={onSelectCourse}
              handleSelectLesson={onSelectLesson}
              showSuccess={showSuccess}
              showError={showError}
            />

            {activeTab === 'courses' && <HowItWorksCard />}
          </div>
        </main>

        {!chatbotOpen && (
          <button
            className="chatbot-toggle-btn"
            onClick={() => setChatbotOpen(true)}
            title="Open Learning Assistant"
          >
            💬
          </button>
        )}

        <ChatBot
          courseId={selectedCourse?.id}
          lessonId={selectedLesson?.id}
          isOpen={chatbotOpen}
          onClose={() => setChatbotOpen(false)}
        />
      </div>
    </div>
  );
}

function AppWithProvider() {
  return (
    <LLMProviderProvider>
      <LanguageProvider>
        <App />
      </LanguageProvider>
    </LLMProviderProvider>
  );
}

export default AppWithProvider;
