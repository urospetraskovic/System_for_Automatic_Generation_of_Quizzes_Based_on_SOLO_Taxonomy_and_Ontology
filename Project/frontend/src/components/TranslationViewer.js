import React, { useState, useEffect, useCallback } from 'react';
import { useLanguage } from '../context/LanguageContext';
import { translationApi } from '../api';

const TranslationViewer = ({ isOpen, onClose, entityId, entityType, originalText }) => {
  const { languages, selectedLanguage } = useLanguage();
  const [translation, setTranslation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Helper to extract string value from any object structure
  const extractStringValue = (val) => {
    if (typeof val === 'string') return val;
    if (!val || typeof val !== 'object') return String(val);
    
    // Try common property names first
    const commonProps = ['text', 'option', 'value', 'label', 'content', 'title', 'name', 'description'];
    for (const prop of commonProps) {
      if (val[prop] && typeof val[prop] === 'string') {
        return val[prop];
      }
    }
    
    // If no common prop found, get first property value that's a string
    for (const key in val) {
      if (val.hasOwnProperty(key) && typeof val[key] === 'string' && val[key].trim()) {
        return val[key];
      }
    }
    
    // Last resort: try JSON.stringify or String conversion
    try {
      const str = String(val);
      if (str && str !== '[object Object]') return str;
    } catch (e) {
      // continue
    }
    
    return '[object Object]';
  };

  // Helper to safely convert options to array of strings
  const getOptionsArray = (opts) => {
    if (!opts) return [];
    if (Array.isArray(opts)) {
      return opts.map(opt => extractStringValue(opt)).filter(Boolean);
    }
    if (typeof opts === 'object') {
      return Object.values(opts).map(opt => extractStringValue(opt)).filter(Boolean);
    }
    return [];
  };

  // Helper to safely convert key points to array of strings
  const getKeyPointsArray = (points) => {
    if (!points) return [];
    if (Array.isArray(points)) {
      return points.map(p => extractStringValue(p)).filter(Boolean);
    }
    if (typeof points === 'object') {
      return Object.values(points).map(p => extractStringValue(p)).filter(Boolean);
    }
    return [];
  };

  const fetchTranslation = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await translationApi.getEntity(entityType, entityId);

      // Backend returns the entity under a key matching its type
      // (question, lesson, section, learning_object).
      const entityKeyByType = {
        question: 'question',
        lesson: 'lesson',
        section: 'section',
        'learning-object': 'learning_object',
      };
      const entity = data[entityKeyByType[entityType]];
      if (entity) {
        const trans = entity.translations?.find((t) => t.language_code === selectedLanguage);
        setTranslation(trans);
      } else {
        setError('No translation found');
      }
    } catch (err) {
      setError('Failed to load translation');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [entityType, entityId, selectedLanguage]);

  useEffect(() => {
    if (isOpen && entityId) {
      fetchTranslation();
    }
  }, [isOpen, entityId, entityType, selectedLanguage, fetchTranslation]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{languages[selectedLanguage] || selectedLanguage.toUpperCase()} Translation</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="modal-body">
          {loading && <p className="loading">Loading translation...</p>}
          
          {error && <p className="error">{error}</p>}
          
          {translation ? (
            <div className="translation-content">
              {/* Question Translation */}
              {entityType === 'question' && translation.translated_question_text && (
                <div className="translation-section">
                  <h4>Question</h4>
                  <p>{translation.translated_question_text}</p>
                  
                  {translation.translated_options && (
                    <div className="translation-options">
                      <h5>Options:</h5>
                      <ul>
                        {getOptionsArray(translation.translated_options).map((opt, i) => (
                          <li key={i}>{opt}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {translation.translated_correct_answer && (
                    <div className="translation-answer">
                      <p><strong>Correct Answer:</strong> {translation.translated_correct_answer}</p>
                    </div>
                  )}
                </div>
              )}

              {/* Lesson/Section Translation */}
              {(entityType === 'lesson' || entityType === 'section') && (
                <div className="translation-section">
                  <h4>Title</h4>
                  <p>{translation.translated_title}</p>
                  
                  {translation.translated_summary && (
                    <div className="translation-section">
                      <h5>Summary</h5>
                      <p>{translation.translated_summary}</p>
                    </div>
                  )}
                </div>
              )}

              {/* Learning Object Translation */}
              {entityType === 'learning-object' && (
                <div className="translation-section">
                  <h4>Learning Object</h4>
                  <p><strong>Title:</strong> {translation.translated_title}</p>
                  
                  {translation.translated_description && (
                    <div className="translation-section">
                      <p><strong>Description:</strong> {translation.translated_description}</p>
                    </div>
                  )}
                  
                  {translation.translated_key_points && (
                    <div className="translation-keypoints">
                      <p><strong>Key Points:</strong></p>
                      <ul>
                        {getKeyPointsArray(translation.translated_key_points).map((point, i) => (
                          <li key={i}>{point}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Original comparison */}
              {originalText && (
                <div className="original-text">
                  <h5>Original (English)</h5>
                  <p>{originalText}</p>
                </div>
              )}
            </div>
          ) : !loading && !error && (
            <p className="no-translation">No translation available for {languages[selectedLanguage] || selectedLanguage}</p>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
};

export default TranslationViewer;
