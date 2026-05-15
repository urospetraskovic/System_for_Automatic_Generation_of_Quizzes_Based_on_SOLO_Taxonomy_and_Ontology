import React, { useState } from 'react';
import { questionApi } from '../api';
import TranslationViewer from './TranslationViewer';

function QuestionBank({ questions, courseId, onRefresh, onSuccess, onError }) {
  const [filter, setFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedQuestions, setSelectedQuestions] = useState([]);
  const [expandedQuestion, setExpandedQuestion] = useState(null);
  const [editingQuestion, setEditingQuestion] = useState(null);
  const [editFormData, setEditFormData] = useState({});
  const [showEditModal, setShowEditModal] = useState(false);
  const [showTranslationViewer, setShowTranslationViewer] = useState(false);
  const [viewingTranslationId, setViewingTranslationId] = useState(null);

  const filteredQuestions = questions.filter(q => {
    const matchesFilter = filter === 'all' || q.solo_level === filter;
    const matchesSearch = !searchTerm || 
      q.question_text?.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  const handleSelectQuestion = (questionId) => {
    setSelectedQuestions(prev => 
      prev.includes(questionId) 
        ? prev.filter(id => id !== questionId)
        : [...prev, questionId]
    );
  };

  const handleSelectAll = () => {
    if (selectedQuestions.length === filteredQuestions.length) {
      setSelectedQuestions([]);
    } else {
      setSelectedQuestions(filteredQuestions.map(q => q.id));
    }
  };

  const handleEditQuestion = (question) => {
    setEditingQuestion(question);
    setEditFormData({
      question_text: question.question_text,
      explanation: question.explanation,
      difficulty: question.difficulty,
      bloom_level: question.bloom_level || '',
      options: question.options || [],
      correct_option_index: question.correct_option_index,
      correct_answer: question.correct_answer,
      tags: Array.isArray(question.tags) ? question.tags.join(', ') : ''
    });
    setShowEditModal(true);
  };

  const handleUpdateQuestion = async () => {
    if (!editingQuestion) return;

    try {
      const tagsArray = editFormData.tags
        ? editFormData.tags.split(',').map(t => t.trim()).filter(t => t)
        : [];

      const updateData = {
        question_text: editFormData.question_text,
        explanation: editFormData.explanation,
        difficulty: editFormData.difficulty,
        bloom_level: editFormData.bloom_level,
        tags: tagsArray,
        mark_human_modified: true
      };

      // Include options for multiple choice
      if (editingQuestion.question_type === 'multiple_choice') {
        updateData.options = editFormData.options;
        updateData.correct_option_index = editFormData.correct_option_index;
        updateData.correct_answer = editFormData.options[editFormData.correct_option_index];
      } else if (editingQuestion.question_type === 'true_false') {
        updateData.correct_answer = editFormData.correct_answer;
      } else if (editingQuestion.question_type === 'short_answer') {
        updateData.correct_answer = editFormData.correct_answer;
      }

      await questionApi.update(editingQuestion.id, updateData);

      // Trigger refresh to reload questions
      onSuccess('Question updated successfully');
      setShowEditModal(false);
      setEditingQuestion(null);
      onRefresh();
    } catch (err) {
      onError(err.response?.data?.error || 'Failed to update question');
    }
  };

  const handleDeleteQuestion = async (questionId) => {
    if (!window.confirm('Are you sure you want to delete this question?')) return;

    try {
      await questionApi.delete(questionId);
      onSuccess('Question deleted');
      onRefresh();
    } catch (err) {
      onError('Failed to delete question');
    }
  };

  const handleDeleteSelected = async () => {
    if (selectedQuestions.length === 0) return;
    
    const confirmMessage = `Are you sure you want to delete ${selectedQuestions.length} question${selectedQuestions.length > 1 ? 's' : ''}? This action cannot be undone.`;
    if (!window.confirm(confirmMessage)) return;

    try {
      let deletedCount = 0;
      let failedCount = 0;
      
      for (const questionId of selectedQuestions) {
        try {
          await questionApi.delete(questionId);
          deletedCount++;
        } catch (err) {
          failedCount++;
        }
      }
      
      setSelectedQuestions([]);
      onRefresh();
      
      if (failedCount === 0) {
        onSuccess(`Successfully deleted ${deletedCount} question${deletedCount > 1 ? 's' : ''}`);
      } else {
        onSuccess(`Deleted ${deletedCount} question${deletedCount > 1 ? 's' : ''}, ${failedCount} failed`);
      }
    } catch (err) {
      onError('Failed to delete questions');
    }
  };

  const getSoloLevelColor = (level) => {
    const colors = {
      unistructural: '#4CAF50',
      multistructural: '#2196F3',
      relational: '#FF9800',
      extended_abstract: '#9C27B0'
    };
    return colors[level] || '#gray';
  };

  const getSoloLevelIcon = (level) => {
    const icons = {
      unistructural: '①',
      multistructural: '②',
      relational: '③',
      extended_abstract: '④'
    };
    return icons[level] || '?';
  };

  const questionsByLevel = {
    all: questions.length,
    unistructural: questions.filter(q => q.solo_level === 'unistructural').length,
    multistructural: questions.filter(q => q.solo_level === 'multistructural').length,
    relational: questions.filter(q => q.solo_level === 'relational').length,
    extended_abstract: questions.filter(q => q.solo_level === 'extended_abstract').length
  };

  return (
    <div className="question-bank">
      <div className="card">
        <div className="card-header">
          <h2>Question Bank</h2>
          <button className="btn-secondary" onClick={onRefresh}>
            Refresh
          </button>
        </div>

        {/* Filters */}
        <div className="filters-section">
          <div className="filter-tabs">
            {[
              { key: 'all', label: 'All' },
              { key: 'unistructural', label: 'Unistructural' },
              { key: 'multistructural', label: 'Multistructural' },
              { key: 'relational', label: 'Relational' },
              { key: 'extended_abstract', label: 'Extended Abstract' }
            ].map(({ key, label }) => (
              <button
                key={key}
                className={`filter-tab ${filter === key ? 'active' : ''}`}
                onClick={() => setFilter(key)}
                style={filter === key ? { borderColor: getSoloLevelColor(key) } : {}}
              >
                {label} ({questionsByLevel[key]})
              </button>
            ))}
          </div>
          
          <div className="search-box">
            <input
              type="text"
              placeholder="Search questions..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        </div>

        {/* Selection Actions */}
        {selectedQuestions.length > 0 && (
          <div className="selection-actions">
            <span>{selectedQuestions.length} selected</span>
            <button 
              className="btn-secondary"
              onClick={() => setSelectedQuestions([])}
            >
              Clear Selection
            </button>
            <button 
              className="btn-danger"
              onClick={handleDeleteSelected}
            >
              🗑️ Delete Selected
            </button>
          </div>
        )}

        {/* Questions List */}
        {questions.length === 0 ? (
          <div className="empty-state">
            <p>No questions in the bank yet.</p>
            <p className="hint">Generate questions from your lessons first.</p>
          </div>
        ) : filteredQuestions.length === 0 ? (
          <div className="empty-state">
            <p>No questions match your filters.</p>
          </div>
        ) : (
          <div className="questions-list">
            <div className="list-header">
              <label className="select-all">
                <input
                  type="checkbox"
                  checked={selectedQuestions.length === filteredQuestions.length && filteredQuestions.length > 0}
                  onChange={handleSelectAll}
                />
                Select All
              </label>
            </div>

            {filteredQuestions.map((question) => (
              <div 
                key={question.id} 
                className={`question-card ${selectedQuestions.includes(question.id) ? 'selected' : ''}`}
              >
                <div className="question-select">
                  <input
                    type="checkbox"
                    checked={selectedQuestions.includes(question.id)}
                    onChange={() => handleSelectQuestion(question.id)}
                  />
                </div>
                
                <div 
                  className="question-content"
                  onClick={() => setExpandedQuestion(
                    expandedQuestion === question.id ? null : question.id
                  )}
                >
                  <div className="question-header">
                    <span 
                      className="solo-badge"
                      style={{ backgroundColor: getSoloLevelColor(question.solo_level) }}
                    >
                      {getSoloLevelIcon(question.solo_level)} {question.solo_level?.replace('_', ' ')}
                    </span>
                    <span className="question-type">{question.question_type}</span>
                    
                    {/* AI Generation Status Badge */}
                    <span className={`question-status-badge ${question.human_modified ? 'human-modified' : question.is_ai_generated ? 'ai-generated' : 'human-created'}`}>
                      {question.human_modified ? 'Human Modified' : question.is_ai_generated ? 'AI Generated' : 'Human Created'}
                    </span>
                  </div>
                  
                  <p className="question-text">{question.question_text}</p>
                  
                  {/* Lesson Source */}
                  <div className={`lesson-source ${question.solo_level === 'extended_abstract' ? 'extended-source' : ''}`}>
                    <span className="source-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg></span>
                    {getLessonSourceDisplay(question)}
                  </div>

                  {/* Creation Date */}
                  {question.created_at && (
                    <div className="question-meta-info">
                      <span className="creation-date">{formatDate(question.created_at)}</span>
                    </div>
                  )}

                  {expandedQuestion === question.id && (
                    <div className="question-details">
                      {question.options && (
                        <div className="options-list">
                          {question.options.map((opt, i) => (
                            <div 
                              key={i} 
                              className={`option ${i === question.correct_option_index ? 'correct' : ''}`}
                            >
                              {opt}
                              {i === question.correct_option_index && <span className="correct-mark">✓</span>}
                            </div>
                          ))}
                        </div>
                      )}
                      
                      {question.explanation && (
                        <div className="explanation">
                          <strong>Explanation:</strong> {question.explanation}
                        </div>
                      )}

                      {question.source_line && (
                        <div
                          className="source-line"
                          style={{
                            marginTop: 8,
                            padding: '8px 12px',
                            borderLeft: '3px solid var(--primary-300, #93c5fd)',
                            background: 'var(--neutral-50, #f9fafb)',
                            fontSize: '0.85rem',
                            color: 'var(--neutral-700, #374151)',
                            fontStyle: 'italic',
                          }}
                          title="Verbatim quote from the source text that justifies the correct answer."
                        >
                          <strong style={{ fontStyle: 'normal' }}>Source:</strong> "{question.source_line}"
                        </div>
                      )}

                      {Array.isArray(question.tags) && question.tags.length > 0 && (
                        <div className="tags">
                          {question.tags.map((tag, i) => (
                            <span key={i} className="tag">{tag}</span>
                          ))}
                        </div>
                      )}

                      {question.tags && !Array.isArray(question.tags) && question.tags.ontology_anchor && (
                        <div
                          className="ontology-anchor"
                          style={{
                            marginTop: 8,
                            padding: '6px 10px',
                            background: 'var(--primary-50, #eff6ff)',
                            border: '1px solid var(--primary-200, #bfdbfe)',
                            borderRadius: 6,
                            fontSize: '0.8rem',
                            color: 'var(--primary-800, #1e40af)',
                          }}
                          title="The ontology relationship this question was generated from."
                        >
                          <strong>Ontology anchor:</strong>{' '}
                          {question.tags.ontology_anchor.source} →{' '}
                          <code style={{ background: 'rgba(0,0,0,0.05)', padding: '0 4px', borderRadius: 3 }}>
                            {question.tags.ontology_anchor.type}
                          </code>{' '}
                          → {question.tags.ontology_anchor.target}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div className="question-actions">
                  <button
                    className="btn-icon btn-translate"
                    onClick={() => {
                      setViewingTranslationId(question.id);
                      setShowTranslationViewer(true);
                    }}
                    title="View translation"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                  </button>
                  <button
                    className="btn-icon btn-edit"
                    onClick={() => handleEditQuestion(question)}
                    title="Edit question"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                  </button>
                  <button
                    className="btn-icon btn-danger"
                    onClick={() => handleDeleteQuestion(question.id)}
                    title="Delete question"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Edit Question Modal */}
        {showEditModal && editingQuestion && (
          <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h3>Edit Question</h3>
                <button 
                  className="btn-close" 
                  onClick={() => setShowEditModal(false)}
                >
                  ✕
                </button>
              </div>
              <div className="modal-body">
                <div className="form-group">
                  <label>Question Text</label>
                  <textarea
                    value={editFormData.question_text || ''}
                    onChange={(e) => setEditFormData({...editFormData, question_text: e.target.value})}
                    placeholder="Question text"
                    rows="3"
                  />
                </div>

                {editingQuestion.question_type === 'multiple_choice' && (
                  <div className="form-group">
                    <label>Options</label>
                    {editFormData.options && editFormData.options.map((option, index) => (
                      <div key={index} className="option-input-group">
                        <input
                          type="radio"
                          name="correct_option"
                          checked={editFormData.correct_option_index === index}
                          onChange={() => setEditFormData(prev => ({...prev, correct_option_index: index}))}
                        />
                        <input
                          type="text"
                          value={option}
                          onChange={(e) => {
                            const newOptions = [...editFormData.options];
                            newOptions[index] = e.target.value;
                            setEditFormData(prev => ({...prev, options: newOptions}));
                          }}
                          placeholder={`Option ${index + 1}`}
                        />
                      </div>
                    ))}
                  </div>
                )}

                {editingQuestion.question_type === 'true_false' && (
                  <div className="form-group">
                    <label>Correct Answer</label>
                    <div className="true-false-options">
                      <label>
                        <input
                          type="radio"
                          name="correct_answer"
                          value="True"
                          checked={editFormData.correct_answer === 'True'}
                          onChange={(e) => setEditFormData({...editFormData, correct_answer: e.target.value})}
                        />
                        True
                      </label>
                      <label>
                        <input
                          type="radio"
                          name="correct_answer"
                          value="False"
                          checked={editFormData.correct_answer === 'False'}
                          onChange={(e) => setEditFormData({...editFormData, correct_answer: e.target.value})}
                        />
                        False
                      </label>
                    </div>
                  </div>
                )}

                {editingQuestion.question_type === 'short_answer' && (
                  <div className="form-group">
                    <label>Expected Answer</label>
                    <input
                      type="text"
                      value={editFormData.correct_answer || ''}
                      onChange={(e) => setEditFormData({...editFormData, correct_answer: e.target.value})}
                      placeholder="Expected answer"
                    />
                  </div>
                )}

                <div className="form-group">
                  <label>Explanation</label>
                  <textarea
                    value={editFormData.explanation || ''}
                    onChange={(e) => setEditFormData({...editFormData, explanation: e.target.value})}
                    placeholder="Explanation for the correct answer"
                    rows="3"
                  />
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Difficulty (0-1)</label>
                    <input
                      type="number"
                      min="0"
                      max="1"
                      step="0.1"
                      value={editFormData.difficulty || 0.5}
                      onChange={(e) => setEditFormData({...editFormData, difficulty: parseFloat(e.target.value)})}
                    />
                  </div>

                  <div className="form-group">
                    <label>Bloom's Level</label>
                    <select
                      value={editFormData.bloom_level || ''}
                      onChange={(e) => setEditFormData({...editFormData, bloom_level: e.target.value})}
                    >
                      <option value="">Select level...</option>
                      <option value="remember">Remember</option>
                      <option value="understand">Understand</option>
                      <option value="apply">Apply</option>
                      <option value="analyze">Analyze</option>
                      <option value="evaluate">Evaluate</option>
                      <option value="create">Create</option>
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label>Tags (comma-separated)</label>
                  <input
                    type="text"
                    value={editFormData.tags || ''}
                    onChange={(e) => setEditFormData({...editFormData, tags: e.target.value})}
                    placeholder="tag1, tag2, tag3"
                  />
                </div>

                {/* Human Modified Notice */}
                <div className="form-status-info">
                  <span className="status-badge human-modified">
                    Saving changes will mark this as: Human Modified
                  </span>
                </div>
              </div>
              <div className="modal-footer">
                <button 
                  className="btn-secondary" 
                  onClick={() => setShowEditModal(false)}
                >
                  Cancel
                </button>
                <button 
                  className="btn-primary" 
                  onClick={handleUpdateQuestion}
                >
                  Save Changes
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Stats */}
        <div className="bank-stats">
          <div className="stat">
            <span className="stat-value">{questions.length}</span>
            <span className="stat-label">Total Questions</span>
          </div>
          <div className="stat">
            <span className="stat-value">{questionsByLevel.unistructural}</span>
            <span className="stat-label">Unistructural</span>
          </div>
          <div className="stat">
            <span className="stat-value">{questionsByLevel.multistructural}</span>
            <span className="stat-label">Multistructural</span>
          </div>
          <div className="stat">
            <span className="stat-value">{questionsByLevel.relational}</span>
            <span className="stat-label">Relational</span>
          </div>
          <div className="stat">
            <span className="stat-value">{questionsByLevel.extended_abstract}</span>
            <span className="stat-label">Extended Abstract</span>
          </div>
        </div>
      </div>

      {/* Translation Viewer Modal */}
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

function formatDate(dateString) {
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
      year: 'numeric', 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch (e) {
    return 'Unknown date';
  }
}

export default QuestionBank;
