import React from 'react';

const NAV_ITEMS = {
  workflow: [
    {
      key: 'courses',
      label: 'Courses',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        </svg>
      ),
    },
    {
      key: 'lessons',
      label: 'Lessons',
      requires: 'course',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
        </svg>
      ),
    },
    {
      key: 'content',
      label: 'Content',
      requires: 'lesson',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
      ),
    },
  ],
  questions: [
    {
      key: 'generate',
      label: 'Generate',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      ),
    },
    {
      key: 'questions',
      label: 'Bank',
      onActivate: 'fetchQuestions',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      ),
    },
    {
      key: 'quizzes',
      label: 'Build Quiz',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
        </svg>
      ),
    },
    {
      key: 'solve',
      label: 'Take Quiz',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
          <polyline points="22 4 12 14.01 9 11.01" />
        </svg>
      ),
    },
  ],
  content: [
    {
      key: 'translate',
      label: 'Translate',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="2" y1="12" x2="22" y2="12" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
      ),
    },
    {
      key: 'sparql',
      label: 'SPARQL Query',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="1" />
          <path d="M12 1v6m0 6v6M4.22 4.22l4.24 4.24m5.08 5.08l4.24 4.24M1 12h6m6 0h6M4.22 19.78l4.24-4.24m5.08-5.08l4.24-4.24" />
        </svg>
      ),
    },
  ],
  evaluation: [
    {
      key: 'eduqg',
      label: 'EduQG Benchmark',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 3v18h18" />
          <rect x="7" y="12" width="3" height="6" />
          <rect x="12" y="8" width="3" height="10" />
          <rect x="17" y="5" width="3" height="13" />
        </svg>
      ),
    },
  ],
};

function NavButton({ item, activeTab, onSelect, selectedCourse, selectedLesson }) {
  const disabled =
    (item.requires === 'course' && !selectedCourse) ||
    (item.requires === 'lesson' && !selectedLesson);

  return (
    <button
      className={`nav-link ${activeTab === item.key ? 'active' : ''}`}
      onClick={() => onSelect(item)}
      disabled={disabled}
    >
      <span className="nav-icon">{item.icon}</span>
      {item.label}
    </button>
  );
}

function Sidebar({
  activeTab,
  selectedCourse,
  selectedLesson,
  onSelectTab,
  onFetchQuestions,
}) {
  const handleSelect = (item) => {
    onSelectTab(item.key);
    if (item.onActivate === 'fetchQuestions') {
      onFetchQuestions(selectedCourse?.id);
    }
  };

  const renderGroup = (items) =>
    items.map((item) => (
      <NavButton
        key={item.key}
        item={item}
        activeTab={activeTab}
        onSelect={handleSelect}
        selectedCourse={selectedCourse}
        selectedLesson={selectedLesson}
      />
    ));

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1>SOLO Quiz</h1>
        <p>Question Generator</p>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section">{renderGroup(NAV_ITEMS.workflow)}</div>
        <div className="nav-section">
          <div className="nav-section-title">Questions</div>
          {renderGroup(NAV_ITEMS.questions)}
        </div>
        <div className="nav-section">
          <div className="nav-section-title">Content</div>
          {renderGroup(NAV_ITEMS.content)}
        </div>
        <div className="nav-section">
          <div className="nav-section-title">Evaluation</div>
          {renderGroup(NAV_ITEMS.evaluation)}
        </div>
      </nav>

      <div className="sidebar-footer">
        {selectedCourse && (
          <div className="selected-context">
            <strong>Current Selection</strong>
            <span className="context-item">{selectedCourse.name}</span>
            {selectedLesson && (
              <span className="context-item context-lesson">{selectedLesson.title}</span>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

export default Sidebar;
