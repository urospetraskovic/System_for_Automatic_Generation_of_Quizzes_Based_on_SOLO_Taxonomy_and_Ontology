import React, { useState, useEffect } from 'react';
import { translationApi } from '../api';
import './TranslationManager.css';

const TranslationManager = () => {
  const [languages, setLanguages] = useState({});
  const [targetLanguage, setTargetLanguage] = useState('sr');
  const [quizzes, setQuizzes] = useState([]);
  const [selectedQuizzes, setSelectedQuizzes] = useState([]);
  const [translating, setTranslating] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 0, currentQuiz: '' });
  const [message, setMessage] = useState(null);
  const [translationResults, setTranslationResults] = useState([]);
  const [statusModal, setStatusModal] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(false);

  useEffect(() => {
    fetchLanguages();
    fetchQuizzes();
  }, []);

  const fetchLanguages = async () => {
    try {
      const { data } = await translationApi.getLanguages();
      if (data.success) {
        setLanguages(data.languages);
      }
    } catch (error) {
      console.error('Error fetching languages:', error);
    }
  };

  const fetchQuizzes = async () => {
    try {
      const { data } = await translationApi.getQuizzes();
      if (data.quizzes) {
        setQuizzes(data.quizzes);
      }
    } catch (error) {
      console.error('Error fetching quizzes:', error);
    }
  };

  const showMessage = (msg, isError = false) => {
    setMessage({ text: msg, isError });
    setTimeout(() => setMessage(null), 8000);
  };

  const toggleQuizSelection = (quizId) => {
    setSelectedQuizzes(prev => 
      prev.includes(quizId) 
        ? prev.filter(id => id !== quizId)
        : [...prev, quizId]
    );
  };

  const selectAllQuizzes = () => {
    if (selectedQuizzes.length === quizzes.length) {
      setSelectedQuizzes([]);
    } else {
      setSelectedQuizzes(quizzes.map(q => q.id));
    }
  };

  const handleTranslate = async () => {
    if (selectedQuizzes.length === 0) {
      showMessage('Please select at least one quiz to translate', true);
      return;
    }

    if (!targetLanguage) {
      showMessage('Please select a target language', true);
      return;
    }

    setTranslating(true);
    setTranslationResults([]);
    setProgress({ current: 0, total: selectedQuizzes.length, currentQuiz: '' });

    const results = [];

    for (let i = 0; i < selectedQuizzes.length; i++) {
      const quizId = selectedQuizzes[i];
      const quiz = quizzes.find(q => q.id === quizId);
      
      setProgress({ 
        current: i + 1, 
        total: selectedQuizzes.length, 
        currentQuiz: quiz?.title || `Quiz ${quizId}` 
      });

      try {
        const { data } = await translationApi.translateQuiz(quizId, targetLanguage);
        results.push({
          quizId,
          quizTitle: quiz?.title || `Quiz ${quizId}`,
          success: data.success,
          questionsTranslated: data.questions_translated || 0,
          totalQuestions: data.total_questions || 0,
          error: data.error
        });
      } catch (error) {
        results.push({
          quizId,
          quizTitle: quiz?.title || `Quiz ${quizId}`,
          success: false,
          error: error.response?.data?.error || error.message,
        });
      }
    }

    setTranslationResults(results);
    setTranslating(false);
    fetchQuizzes();
    
    const successCount = results.filter(r => r.success).length;
    const totalQuestions = results.reduce((sum, r) => sum + (r.questionsTranslated || 0), 0);
    const allComplete = results.every(r => r.questionsTranslated === r.totalQuestions);
    
    if (successCount === results.length && allComplete) {
      showMessage(`All ${successCount} quizzes fully translated! (${totalQuestions} questions)`);
    } else if (successCount > 0) {
      showMessage(`Translated ${totalQuestions} questions. Check status for incomplete translations.`, true);
    } else {
      showMessage(`Translation failed. Please try again.`, true);
    }
  };

  const viewTranslationStatus = async (quizId, e) => {
    e.stopPropagation();
    setLoadingStatus(true);

    try {
      const { data } = await translationApi.getQuizStatus(quizId);
      if (data.success) {
        setStatusModal(data);
      } else {
        showMessage('Failed to load translation status', true);
      }
    } catch (error) {
      showMessage('Error loading translation status', true);
    } finally {
      setLoadingStatus(false);
    }
  };

  const closeStatusModal = () => {
    setStatusModal(null);
  };

  const fixBadTranslations = async (quizId, langCode = null) => {
    try {
      const { data } = await translationApi.fixQuizTranslations(quizId, langCode);
      if (data.success) {
        showMessage(`Fixed! Deleted ${data.deleted_count} bad translations. Re-translate to fix.`);
        const statusResp = await translationApi.getQuizStatus(quizId);
        if (statusResp.data.success) {
          setStatusModal(statusResp.data);
        }
        fetchQuizzes();
      } else {
        showMessage('Failed to fix translations', true);
      }
    } catch (error) {
      showMessage('Error fixing translations', true);
    }
  };

  return (
    <div className="translation-manager">
      <div className="tm-container">
        <div className="tm-header">
          <h1>Quiz Translation</h1>
          <p className="subtitle">Translate your quizzes so students can take them in different languages</p>
        </div>

        {message && (
          <div className={`message ${message.isError ? 'error' : 'success'}`}>
            {message.text}
          </div>
        )}

        {translating && (
          <div className="translation-progress">
            <div className="progress-header">
              <span>Translating: {progress.currentQuiz}</span>
              <span>{progress.current} / {progress.total}</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${(progress.current / progress.total) * 100}%` }} />
            </div>
          </div>
        )}

        <div className="tm-section">
          <h3>Select Target Language</h3>
          <div className="language-grid">
            {Object.entries(languages).map(([code, name]) => (
              <button
                key={code}
                className={`language-btn ${targetLanguage === code ? 'active' : ''}`}
                onClick={() => setTargetLanguage(code)}
                disabled={translating}
              >
                <span className="lang-flag">{getLanguageFlag(code)}</span>
                <span className="lang-name">{name}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="tm-section">
          <div className="section-header">
            <h3>Select Quizzes to Translate</h3>
            <button className="btn-select-all" onClick={selectAllQuizzes} disabled={translating || quizzes.length === 0}>
              {selectedQuizzes.length === quizzes.length ? 'Deselect All' : 'Select All'}
            </button>
          </div>

          {quizzes.length === 0 ? (
            <div className="empty-state"><p>No quizzes found. Create some quizzes first!</p></div>
          ) : (
            <div className="quiz-grid">
              {quizzes.map(quiz => (
                <div key={quiz.id} className={`quiz-card ${selectedQuizzes.includes(quiz.id) ? 'selected' : ''}`}
                  onClick={() => !translating && toggleQuizSelection(quiz.id)}>
                  <div className="quiz-checkbox">
                    <input type="checkbox" checked={selectedQuizzes.includes(quiz.id)} onChange={() => {}} disabled={translating} />
                  </div>
                  <div className="quiz-info">
                    <h4>{quiz.title}</h4>
                    <div className="quiz-meta"><span className="meta-item">{quiz.question_count} questions</span></div>
                    {quiz.available_languages && quiz.available_languages.length > 0 && (
                      <div className="translated-langs">
                        <span className="langs-label">Fully translated:</span>
                        {quiz.available_languages.map(lang => (
                          <span key={lang} className="lang-tag complete">{getLanguageFlag(lang)} {lang.toUpperCase()}</span>
                        ))}
                      </div>
                    )}
                    <button className="btn-view-status" onClick={(e) => viewTranslationStatus(quiz.id, e)} disabled={loadingStatus}>
                      View Status
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="tm-section">
          <button className="btn-translate-large" onClick={handleTranslate} disabled={translating || selectedQuizzes.length === 0}>
            {translating ? `Translating... (${progress.current}/${progress.total})` : `Translate ${selectedQuizzes.length} Quiz${selectedQuizzes.length !== 1 ? 'zes' : ''} to ${languages[targetLanguage] || targetLanguage}`}
          </button>
        </div>

        {translationResults.length > 0 && (
          <div className="tm-section results-section">
            <h3>Translation Results</h3>
            <div className="results-list">
              {translationResults.map((result, idx) => (
                <div key={idx} className={`result-item ${result.questionsTranslated === result.totalQuestions ? 'success' : 'partial'}`}>
                  <span className="result-icon">{result.questionsTranslated === result.totalQuestions ? '' : ''}</span>
                  <span className="result-title">{result.quizTitle}</span>
                  {result.success ? (
                    <span className="result-detail">
                      {result.questionsTranslated}/{result.totalQuestions} questions
                      {result.questionsTranslated < result.totalQuestions && <span className="missing-warning"> - {result.totalQuestions - result.questionsTranslated} missing!</span>}
                    </span>
                  ) : (<span className="result-error">{result.error}</span>)}
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="info-box">
          <p><strong>How it works:</strong></p>
          <ul>
            <li>Select the quizzes you want to translate</li>
            <li>Choose the target language</li>
            <li>Click translate - each question will be translated using AI</li>
            <li>A language only appears as available when ALL questions are translated</li>
            <li>Use View Status to see which questions are missing translations</li>
          </ul>
        </div>
      </div>

      {statusModal && (
        <div className="status-modal-overlay" onClick={closeStatusModal}>
          <div className="status-modal" onClick={e => e.stopPropagation()}>
            <div className="status-modal-header">
              <h2>Translation Status</h2>
              <button className="btn-close" onClick={closeStatusModal}>×</button>
            </div>
            <div className="status-modal-content">
              <h3>{statusModal.quiz_title}</h3>
              <p className="total-questions">Total questions: {statusModal.total_questions}</p>
              
              <div className="fix-section">
                <p className="fix-info">If translations show as complete but display in English, the AI may have failed. Click below to fix:</p>
                <button className="btn-fix" onClick={() => fixBadTranslations(statusModal.quiz_id)}>
                  🔧 Fix Bad Translations
                </button>
              </div>
              
              <div className="language-status-list">
                {Object.entries(statusModal.language_status).map(([langCode, status]) => (
                  <div key={langCode} className={`language-status-item ${status.is_complete ? 'complete' : 'incomplete'}`}>
                    <div className="lang-header">
                      <span className="lang-flag">{getLanguageFlag(langCode)}</span>
                      <span className="lang-name">{status.language_name}</span>
                      <span className={`status-badge ${status.is_complete ? 'complete' : 'incomplete'}`}>
                        {status.is_complete ? '✓ Complete' : `${status.translated_count}/${status.total_questions}`}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="status-modal-footer">
              <button className="btn-primary" onClick={closeStatusModal}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const getLanguageFlag = (code) => {
  const flags = { 'en': '', 'sr': '', 'fr': '', 'es': '', 'de': '', 'ru': '', 'zh': '', 'ja': '', 'pt': '', 'it': '' };
  return flags[code] || '';
};

export default TranslationManager;
