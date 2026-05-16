import React, { useState } from 'react';
import { quizApi } from '../api';
import { useLanguage } from '../context/LanguageContext';
import TranslationViewer from './TranslationViewer';

function QuizBuilder({ questions, course, onSuccess, onError }) {
  const { selectedLanguage } = useLanguage();
  const [quizTitle, setQuizTitle] = useState('');
  const [quizDescription, setQuizDescription] = useState('');
  const [selectedQuestionIds, setSelectedQuestionIds] = useState([]);
  const [filterLevel, setFilterLevel] = useState('all');
  const [timeLimit, setTimeLimit] = useState(null);
  const [creating, setCreating] = useState(false);
  const [createdQuiz, setCreatedQuiz] = useState(null);
  const [showTranslationViewer, setShowTranslationViewer] = useState(false);
  const [viewingTranslationId, setViewingTranslationId] = useState(null);

  const filteredQuestions = questions.filter(q => 
    filterLevel === 'all' || q.solo_level === filterLevel
  );

  const handleToggleQuestion = (questionId) => {
    setSelectedQuestionIds(prev =>
      prev.includes(questionId)
        ? prev.filter(id => id !== questionId)
        : [...prev, questionId]
    );
  };

  const handleSelectAllFiltered = () => {
    const filteredIds = filteredQuestions.map(q => q.id);
    const allSelected = filteredIds.every(id => selectedQuestionIds.includes(id));
    
    if (allSelected) {
      setSelectedQuestionIds(prev => prev.filter(id => !filteredIds.includes(id)));
    } else {
      setSelectedQuestionIds(prev => [...new Set([...prev, ...filteredIds])]);
    }
  };

  const handleAutoSelect = (config) => {
    // Auto-select questions based on SOLO distribution.
    // Fisher-Yates shuffle — `sort(() => Math.random() - 0.5)` is biased.
    const shuffle = (arr) => {
      const a = [...arr];
      for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
      }
      return a;
    };

    const selected = [];
    const levels = ['unistructural', 'multistructural', 'relational', 'extended_abstract'];

    levels.forEach(level => {
      const levelQuestions = questions.filter(q => q.solo_level === level);
      const count = config[level] || 0;
      const shuffled = shuffle(levelQuestions);
      selected.push(...shuffled.slice(0, count).map(q => q.id));
    });

    setSelectedQuestionIds(selected);
  };

  const handleCreateQuiz = async () => {
    if (!quizTitle.trim()) {
      onError('Please enter a quiz title');
      return;
    }
    
    if (selectedQuestionIds.length === 0) {
      onError('Please select at least one question');
      return;
    }

    try {
      setCreating(true);
      
      const response = await quizApi.create({
        title: quizTitle,
        description: quizDescription,
        course_id: course?.id,
        question_ids: selectedQuestionIds,
        time_limit_minutes: timeLimit,
        shuffle_questions: true,
        shuffle_options: true
      });

      setCreatedQuiz(response.data.quiz);
      onSuccess(`Quiz "${quizTitle}" created with ${selectedQuestionIds.length} questions!`);
      
      // Reset form
      setQuizTitle('');
      setQuizDescription('');
      setSelectedQuestionIds([]);
      
    } catch (err) {
      onError(err.response?.data?.error || 'Failed to create quiz');
    } finally {
      setCreating(false);
    }
  };

  const selectedQuestions = questions.filter(q => selectedQuestionIds.includes(q.id));
  const soloDistribution = {
    unistructural: selectedQuestions.filter(q => q.solo_level === 'unistructural').length,
    multistructural: selectedQuestions.filter(q => q.solo_level === 'multistructural').length,
    relational: selectedQuestions.filter(q => q.solo_level === 'relational').length,
    extended_abstract: selectedQuestions.filter(q => q.solo_level === 'extended_abstract').length
  };

  return (
    <div className="quiz-builder">
      <div className="card">
        <h2>Build Quiz</h2>
        
        {/* Quiz Details */}
        <div className="quiz-details-section">
          <h3>Quiz Details</h3>
          <div className="form-group">
            <label>Quiz Title *</label>
            <input
              type="text"
              placeholder="e.g., Chapter 5 Review Quiz"
              value={quizTitle}
              onChange={(e) => setQuizTitle(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label>Description</label>
            <textarea
              placeholder="Brief description of the quiz"
              value={quizDescription}
              onChange={(e) => setQuizDescription(e.target.value)}
              rows={2}
            />
          </div>
          <div className="form-group">
            <label>Time Limit (minutes, optional)</label>
            <input
              type="number"
              placeholder="No limit"
              value={timeLimit || ''}
              onChange={(e) => setTimeLimit(e.target.value ? parseInt(e.target.value) : null)}
              min="1"
            />
          </div>
          <div className="form-group">
            <label>Preview Language</label>
            <p style={{ marginBottom: '8px', fontSize: '0.85rem', color: '#666' }}>
              Selected language: <strong>{selectedLanguage.toUpperCase()}</strong> (click 🌐 on any question to see its translation)
            </p>
          </div>
        </div>

        {/* Quick Select */}
        <div className="quick-select-section">
          <h3>Quick Select</h3>
          <div className="quick-buttons">
            <button 
              className="btn-secondary"
              onClick={() => handleAutoSelect({ unistructural: 5, multistructural: 5, relational: 5, extended_abstract: 5 })}
            >
              Balanced (20 questions)
            </button>
            <button 
              className="btn-secondary"
              onClick={() => handleAutoSelect({ unistructural: 3, multistructural: 4, relational: 3 })}
            >
              Quick Quiz (10)
            </button>
            <button 
              className="btn-secondary"
              onClick={() => handleAutoSelect({ unistructural: 10, multistructural: 10, relational: 10, extended_abstract: 10 })}
            >
              Full Test (40)
            </button>
            <button 
              className="btn-secondary"
              onClick={() => setSelectedQuestionIds([])}
            >
              Clear All
            </button>
          </div>
        </div>

        {/* Question Selection */}
        <div className="question-selection-section">
          <h3>Select Questions ({selectedQuestionIds.length} selected)</h3>
          
          {/* Filter */}
          <div className="selection-filter">
            <select value={filterLevel} onChange={(e) => setFilterLevel(e.target.value)}>
              <option value="all">All Levels</option>
              <option value="unistructural">Unistructural</option>
              <option value="multistructural">Multistructural</option>
              <option value="relational">Relational</option>
              <option value="extended_abstract">Extended Abstract</option>
            </select>
            <button className="btn-secondary" onClick={handleSelectAllFiltered}>
              {filteredQuestions.every(q => selectedQuestionIds.includes(q.id)) 
                ? 'Deselect All Shown' 
                : 'Select All Shown'}
            </button>
          </div>

          {/* Questions List */}
          {questions.length === 0 ? (
            <div className="empty-state">
              <p>No questions available. Generate questions first.</p>
            </div>
          ) : (
            <div className="selectable-questions">
              {filteredQuestions.map((question) => (
                <div
                  key={question.id}
                  className={`selectable-question ${selectedQuestionIds.includes(question.id) ? 'selected' : ''}`}
                  onClick={() => handleToggleQuestion(question.id)}
                >
                  <div className="checkbox">
                    {selectedQuestionIds.includes(question.id) ? '✓' : ''}
                  </div>
                  <div className="question-preview">
                    <div className="preview-header">
                      <span className={`level-badge level-${question.solo_level}`}>
                        {question.solo_level?.replace('_', ' ')}
                      </span>
                      {question.solo_level === 'extended_abstract' && (
                        <span className="cross-topic-badge-mini">Cross-Topic</span>
                      )}
                      <button
                        className="btn-translate"
                        onClick={(e) => {
                          e.stopPropagation();
                          setViewingTranslationId(question.id);
                          setShowTranslationViewer(true);
                        }}
                        title={`View question in ${selectedLanguage}`}
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                      </button>
                    </div>
                    <p className="full-question-text">{question.question_text}</p>
                    {/* Lesson Source */}
                    {getLessonSourceDisplay(question) && (
                      <div className={`lesson-source ${question.solo_level === 'extended_abstract' ? 'extended-source' : ''}`}>
                        <span className="source-icon">📚</span>
                        {getLessonSourceDisplay(question)}
                      </div>
                    )}
                    {question.created_at && (
                      <div className="question-timestamp">
                        Generated: {new Date(question.created_at).toLocaleString()}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Selection Summary */}
        {selectedQuestionIds.length > 0 && (
          <div className="selection-summary">
            <h4>Selection Summary</h4>
            <div className="summary-grid">
              <div className="summary-item">
                <span className="count">{soloDistribution.unistructural}</span>
                <span className="label">Unistructural</span>
              </div>
              <div className="summary-item">
                <span className="count">{soloDistribution.multistructural}</span>
                <span className="label">Multistructural</span>
              </div>
              <div className="summary-item">
                <span className="count">{soloDistribution.relational}</span>
                <span className="label">Relational</span>
              </div>
              <div className="summary-item">
                <span className="count">{soloDistribution.extended_abstract}</span>
                <span className="label">Extended Abstract</span>
              </div>
            </div>
          </div>
        )}

        {/* Create Button */}
        <div className="builder-actions">
          <button
            className="btn-primary btn-large"
            onClick={handleCreateQuiz}
            disabled={creating || !quizTitle.trim() || selectedQuestionIds.length === 0}
          >
            {creating ? 'Creating...' : `Create Quiz (${selectedQuestionIds.length} questions)`}
          </button>
        </div>

        {/* Created Quiz */}
        {createdQuiz && (
          <div className="created-quiz">
            <h4>Quiz Created!</h4>
            <p><strong>{createdQuiz.title}</strong></p>
            <p>{createdQuiz.question_count} questions</p>
          </div>
        )}
      </div>
      
      <TranslationViewer
        isOpen={showTranslationViewer}
        onClose={() => {
          setShowTranslationViewer(false);
          setViewingTranslationId(null);
        }}
        entityId={viewingTranslationId}
        entityType="question"
        originalText={questions.find(q => q.id === viewingTranslationId)?.question_text}
      />
    </div>
  );
}

// Helper function to display lesson source
function getLessonSourceDisplay(question) {
  // Try to use lesson titles first
  if (question.secondary_lesson_title && question.primary_lesson_title) {
    return (
      <span className="source-text">
        From <strong>{question.primary_lesson_title}</strong> + <strong>{question.secondary_lesson_title}</strong>
      </span>
    );
  }
  
  if (question.primary_lesson_title) {
    return (
      <span className="source-text">
        From <strong>{question.primary_lesson_title}</strong>
      </span>
    );
  }
  
  // Fallback: extract from tags if titles are missing (for cross-topic questions)
  if (question.tags && question.tags.length > 0) {
    const lessonTags = question.tags.filter(tag => tag !== 'cross-topic');
    if (lessonTags.length > 1) {
      return (
        <span className="source-text">
          From <strong>{lessonTags[0]}</strong> + <strong>{lessonTags[1]}</strong>
        </span>
      );
    }
    if (lessonTags.length === 1) {
      return (
        <span className="source-text">
          From <strong>{lessonTags[0]}</strong>
        </span>
      );
    }
  }
  
  return null;
}

export default QuizBuilder;
