import React, { useState, useEffect, useCallback } from 'react';
import { quizApi, translationApi } from '../api';

// Language flags helper
const getLanguageFlag = (code) => {
  const flags = {
    'en': '🇬🇧', 'sr': '🇷🇸', 'fr': '🇫🇷', 'es': '🇪🇸', 'de': '🇩🇪',
    'ru': '🇷🇺', 'zh': '🇨🇳', 'ja': '🇯🇵', 'pt': '🇵🇹', 'it': '🇮🇹'
  };
  return flags[code] || '🌐';
};

const languageNames = {
  'en': 'English', 'sr': 'Serbian', 'fr': 'French', 'es': 'Spanish', 'de': 'German',
  'ru': 'Russian', 'zh': 'Chinese', 'ja': 'Japanese', 'pt': 'Portuguese', 'it': 'Italian'
};

function QuizSolver({ courseId, onBack, onSuccess, onError }) {
  const [quizzes, setQuizzes] = useState([]);
  const [selectedQuiz, setSelectedQuiz] = useState(null);
  const [quizData, setQuizData] = useState(null);
  const [userAnswers, setUserAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [score, setScore] = useState(null);
  const [loading, setLoading] = useState(false);
  const [timeElapsed, setTimeElapsed] = useState(0);
  const [revealedAnswers, setRevealedAnswers] = useState({});
  const [selectedLanguage, setSelectedLanguage] = useState('original');
  const [showLanguageSelector, setShowLanguageSelector] = useState(false);
  const [retranslating, setRetranslating] = useState(null); // question id being retranslated
  const [deletingQuizId, setDeletingQuizId] = useState(null); // quiz id being deleted

  const fetchQuizzes = useCallback(async () => {
    try {
      setLoading(true);
      const response = await quizApi.getForCourse(courseId);
      setQuizzes(response.data.quizzes || []);
    } catch (err) {
      onError('Failed to fetch quizzes');
    } finally {
      setLoading(false);
    }
  }, [courseId, onError]);

  useEffect(() => {
    fetchQuizzes();
  }, [fetchQuizzes]);

  // Delete quiz handler
  const handleDeleteQuiz = async (e, quizId, quizTitle) => {
    e.stopPropagation(); // Prevent quiz card click
    
    if (!window.confirm(`Are you sure you want to delete "${quizTitle}"? This action cannot be undone.`)) {
      return;
    }
    
    try {
      setDeletingQuizId(quizId);
      await quizApi.delete(quizId);
      setQuizzes(prev => prev.filter(q => q.id !== quizId));
      onSuccess(`Quiz "${quizTitle}" deleted successfully`);
    } catch (err) {
      onError(err.response?.data?.error || 'Failed to delete quiz');
    } finally {
      setDeletingQuizId(null);
    }
  };

  // Timer effect - starts when quiz is selected
  useEffect(() => {
    let interval;
    if (quizData && !submitted) {
      interval = setInterval(() => {
        setTimeElapsed(prev => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [quizData, submitted]);

  const handleSelectQuiz = async (quiz) => {
    try {
      setLoading(true);
      const response = await quizApi.getById(quiz.id);
      setQuizData(response.data.quiz);
      setSelectedQuiz(quiz);
      setUserAnswers({});
      setSubmitted(false);
      setScore(null);
    } catch (err) {
      onError('Failed to load quiz');
    } finally {
      setLoading(false);
    }
  };

  const handleAnswerChange = (questionId, answer) => {
    setUserAnswers({
      ...userAnswers,
      [questionId]: answer
    });
  };

  const calculateScore = () => {
    if (!quizData?.questions) return 0;
    
    let correctCount = 0;
    quizData.questions.forEach(question => {
      const userAnswer = userAnswers[question.id];
      if (userAnswer !== undefined) {
        if (question.correct_option_index !== undefined) {
          // Multiple choice
          if (parseInt(userAnswer) === question.correct_option_index) {
            correctCount++;
          }
        } else if (question.correct_answer) {
          // True/False or short answer
          if (userAnswer.toLowerCase() === question.correct_answer.toLowerCase()) {
            correctCount++;
          }
        }
      }
    });

    const percentage = (correctCount / quizData.questions.length) * 100;
    return { correctCount, totalCount: quizData.questions.length, percentage };
  };

  const handleSubmit = () => {
    const scoreData = calculateScore();
    setScore(scoreData);
    setSubmitted(true);
    onSuccess(`Quiz submitted! Score: ${scoreData.correctCount}/${scoreData.totalCount} (${scoreData.percentage.toFixed(1)}%)`);
  };

  const handleRetake = () => {
    setUserAnswers({});
    setSubmitted(false);
    setScore(null);
    setTimeElapsed(0);
    setRevealedAnswers({});
  };

  const toggleRevealAnswer = (questionId) => {
    setRevealedAnswers({
      ...revealedAnswers,
      [questionId]: !revealedAnswers[questionId]
    });
  };

  const formatTime = (seconds) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
      return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
    return `${minutes}:${String(secs).padStart(2, '0')}`;
  };

  const handleBackToList = () => {
    setSelectedQuiz(null);
    setQuizData(null);
    setUserAnswers({});
    setSubmitted(false);
    setScore(null);
    setTimeElapsed(0);
    setRevealedAnswers({});
    setSelectedLanguage('original');
    setShowLanguageSelector(false);
  };

  // Retranslate a single question
  const handleRetranslate = async (questionId) => {
    if (selectedLanguage === 'original') return;

    setRetranslating(questionId);
    try {
      const { data } = await translationApi.retranslateQuestion(questionId, selectedLanguage);
      if (data.success) {
        const quizResponse = await quizApi.getById(selectedQuiz.id);
        setQuizData(quizResponse.data.quiz);
        onSuccess('Translation updated!');
      } else {
        onError(data.error || 'Retranslation failed');
      }
    } catch (error) {
      onError(error.response?.data?.error || 'Failed to retranslate question');
    } finally {
      setRetranslating(null);
    }
  };

  // Get translated text for a question
  const getQuestionText = (question) => {
    if (selectedLanguage === 'original' || !question.translations) {
      return question.question_text;
    }
    const translation = question.translations.find(t => t.language_code === selectedLanguage);
    return translation ? translation.translated_question_text : question.question_text;
  };

  const getOptions = (question) => {
    if (selectedLanguage === 'original' || !question.translations) {
      return question.options;
    }
    const translation = question.translations.find(t => t.language_code === selectedLanguage);
    return translation?.translated_options || question.options;
  };

  const getExplanation = (question) => {
    if (selectedLanguage === 'original' || !question.translations) {
      return question.explanation;
    }
    const translation = question.translations.find(t => t.language_code === selectedLanguage);
    return translation?.translated_explanation || question.explanation;
  };

  // Quiz list view - show when no quiz selected OR when language selector modal is open
  if (!selectedQuiz || showLanguageSelector) {
    return (
      <div className="quiz-solver">
        <div className="card">
          <div className="card-header">
            <button className="btn-back" onClick={onBack}>← Back</button>
            <h2>Available Quizzes</h2>
          </div>

          {loading ? (
            <div className="loading-state">Loading quizzes...</div>
          ) : quizzes.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon"></div>
              <p>No quizzes available for this course</p>
              <p className="hint">Create a quiz using the "Build Quiz" section first</p>
            </div>
          ) : (
            <div className="quiz-list">
              {quizzes.map(quiz => (
                <div
                  key={quiz.id}
                  className="quiz-card"
                  onClick={() => {
                    if (quiz.available_languages && quiz.available_languages.length > 0) {
                      setSelectedQuiz(quiz);
                      setShowLanguageSelector(true);
                    } else {
                      handleSelectQuiz(quiz);
                    }
                  }}
                >
                  <div className="quiz-info">
                    <h3>{quiz.title}</h3>
                    {quiz.description && <p className="quiz-description">{quiz.description}</p>}
                    {quiz.available_languages && quiz.available_languages.length > 0 && (
                      <div className="quiz-languages">
                        <span className="languages-label">🌐 Available in:</span>
                        <span className="lang-badge">🇬🇧 English</span>
                        {quiz.available_languages.map(lang => (
                          <span key={lang} className="lang-badge">
                            {getLanguageFlag(lang)} {languageNames[lang] || lang}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="quiz-meta">
                    <div className="meta-item">
                      <span className="meta-icon">Q:</span>
                      <span>{quiz.question_count} questions</span>
                    </div>
                    {quiz.time_limit_minutes && (
                      <div className="meta-item">
                        <span className="meta-icon">Time:</span>
                        <span>{quiz.time_limit_minutes} min</span>
                      </div>
                    )}
                    {quiz.passing_score && (
                      <div className="meta-item">
                        <span className="meta-icon">Pass:</span>
                        <span>Pass: {quiz.passing_score}%</span>
                      </div>
                    )}
                    <button
                      className="btn-delete-quiz"
                      onClick={(e) => handleDeleteQuiz(e, quiz.id, quiz.title)}
                      disabled={deletingQuizId === quiz.id}
                      title="Delete quiz"
                    >
                      {deletingQuizId === quiz.id ? '...' : '🗑️'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Language Selector Modal */}
        {showLanguageSelector && selectedQuiz && (
          <div className="language-modal-overlay" onClick={() => {
            setShowLanguageSelector(false);
            setSelectedQuiz(null);
          }}>
            <div className="language-modal" onClick={e => e.stopPropagation()}>
              <h3>🌐 Choose Quiz Language</h3>
              <p className="modal-subtitle">Select the language you want to take this quiz in</p>
              
              <div className="language-options">
                <button 
                  className={`language-option ${selectedLanguage === 'original' ? 'selected' : ''}`}
                  onClick={() => setSelectedLanguage('original')}
                >
                  <span className="lang-flag">🇬🇧</span>
                  <span className="lang-name">English (Original)</span>
                </button>
                {selectedQuiz.available_languages && selectedQuiz.available_languages.map(lang => (
                  <button 
                    key={lang}
                    className={`language-option ${selectedLanguage === lang ? 'selected' : ''}`}
                    onClick={() => setSelectedLanguage(lang)}
                  >
                    <span className="lang-flag">{getLanguageFlag(lang)}</span>
                    <span className="lang-name">{languageNames[lang] || lang}</span>
                  </button>
                ))}
              </div>

              <div className="modal-actions">
                <button className="btn-secondary" onClick={() => {
                  setShowLanguageSelector(false);
                  setSelectedQuiz(null);
                }}>
                  Cancel
                </button>
                <button className="btn-primary" onClick={() => {
                  setShowLanguageSelector(false);
                  handleSelectQuiz(selectedQuiz);
                }}>
                  Start Quiz
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Quiz taking view
  if (quizData) {
    return (
      <div className="quiz-taker">
        <div className="card">
          <div className="card-header">
            <div>
              <button className="btn-back" onClick={handleBackToList}>← Back to Quizzes</button>
              <h2>
                {selectedQuiz.title}
                {selectedLanguage !== 'original' && (
                  <span className="current-lang-badge">
                    {getLanguageFlag(selectedLanguage)} {languageNames[selectedLanguage]}
                  </span>
                )}
              </h2>
              {selectedQuiz.description && (
                <p className="quiz-description">{selectedQuiz.description}</p>
              )}
            </div>
            {!submitted && (
              <div className="quiz-progress">
                <div className="progress-info">
                  <span>Time: {formatTime(timeElapsed)}</span>
                  <span>Answered: {Object.keys(userAnswers).length}/{quizData.questions?.length || 0}</span>
                </div>
              </div>
            )}
          </div>

          {submitted && score ? (
            <div className="result-section">
              <div className="score-display">
                <div className="score-circle">
                  <span className="score-percentage">{score.percentage.toFixed(1)}%</span>
                </div>
                <div className="score-details">
                  <p>
                    <strong>Score:</strong> {score.correctCount} out of {score.totalCount} correct
                  </p>
                  <p>
                    <strong>Status:</strong>{' '}
                    {score.percentage >= (selectedQuiz.passing_score || 70) ? (
                      <span style={{ color: 'var(--success)' }}>✓ PASSED</span>
                    ) : (
                      <span style={{ color: 'var(--error)' }}>✗ FAILED</span>
                    )}
                  </p>
                </div>
              </div>
            </div>
          ) : null}

          <div className="questions-section">
            {quizData.questions?.map((question, index) => {
              const isCorrect =
                submitted &&
                ((question.correct_option_index !== undefined &&
                  parseInt(userAnswers[question.id]) === question.correct_option_index) ||
                  (question.correct_answer &&
                    userAnswers[question.id]?.toLowerCase() ===
                      question.correct_answer.toLowerCase()));

              return (
                <div
                  key={question.id}
                  className={`question-section ${submitted ? (isCorrect ? 'correct' : 'incorrect') : ''}`}
                >
                  <div className="question-header">
                    <h4>
                      Question {index + 1}
                      {submitted && (isCorrect ? ' ✓' : ' ✗')}
                    </h4>
                    <div className="question-meta">
                      <span className="solo-badge" style={{ backgroundColor: getSoloColor(question.solo_level) }}>
                        {question.solo_level.replace(/_/g, ' ')}
                      </span>
                      {selectedLanguage !== 'original' && !submitted && (
                        <button 
                          className="btn-retranslate"
                          onClick={() => handleRetranslate(question.id)}
                          disabled={retranslating === question.id}
                          title="Retranslate this question"
                        >
                          {retranslating === question.id ? '⟳' : '🔄'}
                        </button>
                      )}
                    </div>
                  </div>

                  <p className="question-text">{getQuestionText(question)}</p>

                  {/* Lesson Source */}
                  <div className={`lesson-source ${question.solo_level === 'extended_abstract' ? 'extended-source' : ''}`}>
                    <span className="source-icon"></span>
                    {getLessonSourceDisplay(question)}
                  </div>

                  {question.question_type === 'multiple_choice' && question.options ? (
                    <div className="options-list">
                      {getOptions(question).map((option, optIdx) => (
                        <label
                          key={optIdx}
                          className={`option-label ${
                            userAnswers[question.id] === optIdx.toString() ? 'selected' : ''
                          } ${submitted ? (optIdx === question.correct_option_index ? 'correct-answer' : '') : ''}`}
                        >
                          <input
                            type="radio"
                            name={`question-${question.id}`}
                            value={optIdx}
                            checked={userAnswers[question.id] === optIdx.toString()}
                            onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                            disabled={submitted}
                          />
                          <span className="option-text">{option}</span>
                        </label>
                      ))}
                    </div>
                  ) : question.question_type === 'true_false' ? (
                    <div className="options-list">
                      {['True', 'False'].map((option, optIdx) => (
                        <label
                          key={optIdx}
                          className={`option-label ${
                            userAnswers[question.id] === option ? 'selected' : ''
                          } ${submitted ? (option === question.correct_answer ? 'correct-answer' : '') : ''}`}
                        >
                          <input
                            type="radio"
                            name={`question-${question.id}`}
                            value={option}
                            checked={userAnswers[question.id] === option}
                            onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                            disabled={submitted}
                          />
                          <span className="option-text">{option}</span>
                        </label>
                      ))}
                    </div>
                  ) : (
                    <div className="short-answer">
                      <input
                        type="text"
                        placeholder="Enter your answer"
                        value={userAnswers[question.id] || ''}
                        onChange={(e) => handleAnswerChange(question.id, e.target.value)}
                        disabled={submitted}
                        className="answer-input"
                      />
                    </div>
                  )}

                  {!submitted && (
                    <button 
                      className="btn-show-answer"
                      onClick={() => toggleRevealAnswer(question.id)}
                    >
                      {revealedAnswers[question.id] ? 'Hide Answer' : 'Show Answer'}
                    </button>
                  )}

                  {revealedAnswers[question.id] && !submitted && (
                    <div className="revealed-answer">
                      <strong>Correct Answer:</strong>
                      {question.correct_option_index !== undefined && (
                        <p>{getOptions(question)[question.correct_option_index]}</p>
                      )}
                      {question.correct_answer && !question.options && (
                        <p>{question.correct_answer}</p>
                      )}
                      {getExplanation(question) && (
                        <p className="answer-explanation">{getExplanation(question)}</p>
                      )}
                    </div>
                  )}

                  {submitted && getExplanation(question) && (
                    <div className="explanation">
                      <strong>Explanation:</strong> {getExplanation(question)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {!submitted ? (
            <div className="quiz-actions">
              <button className="btn-secondary" onClick={handleBackToList}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleSubmit}
                disabled={Object.keys(userAnswers).length === 0}
              >
                Submit Quiz
              </button>
            </div>
          ) : (
            <div className="quiz-actions">
              <button className="btn-secondary" onClick={handleBackToList}>
                Back to Quizzes
              </button>
              <button className="btn-primary" onClick={handleRetake}>
                Retake Quiz
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return null;
}

function getSoloColor(level) {
  const colors = {
    unistructural: '#8b5cf6',
    multistructural: '#ec4899',
    relational: '#f59e0b',
    extended_abstract: '#06b6d4'
  };
  return colors[level] || '#6b7280';
}

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

export default QuizSolver;
