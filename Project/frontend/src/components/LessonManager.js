import React, { useState, useRef, useEffect, useCallback } from 'react';
import { lessonApi, ontologyApi } from '../api';
import { useLanguage } from '../context/LanguageContext';
import TranslationViewer from './TranslationViewer';

function LessonManager({ course, onSelectLesson, onLessonsChange, onSuccess, onError, onBack, loading }) {
  const { selectedLanguage } = useLanguage();
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [showTranslationViewer, setShowTranslationViewer] = useState(false);
  const [viewingTranslationId, setViewingTranslationId] = useState(null);
  const fileInputRef = useRef(null);

  // Local copy of lessons. Initialised from props, kept in sync when the
  // parent refetches, and refreshable directly from the server so we don't
  // depend on a parent-state round-trip after parse/upload/delete (which
  // was leaving the card showing "0 Sections" after a successful parse).
  const [lessons, setLessons] = useState(course.lessons || []);

  useEffect(() => {
    setLessons(course.lessons || []);
  }, [course.lessons]);

  const refreshLessons = useCallback(async () => {
    if (!course?.id) return;
    try {
      const res = await lessonApi.getForCourse(course.id);
      setLessons(res.data.lessons || []);
    } catch {
      // Fall back to whatever the parent had.
    }
  }, [course?.id]);

  // Always re-fetch from the server when the course id changes. The
  // parent's `course.lessons` can be stale (e.g. after a hard refresh on
  // the lessons tab, or when the previous page mutated lessons without
  // re-fetching the parent course). Fetching directly here guarantees
  // we render every lesson the backend actually has.
  useEffect(() => {
    refreshLessons();
  }, [refreshLessons]);

  const handleExportCourseOntology = async () => {
    try {
      setExporting(true);
      setUploadProgress('Generating course ontology...');
      
      const response = await ontologyApi.exportCourse(course.id);
      
      // Create download link
      const blob = new Blob([response.data], { type: 'application/rdf+xml' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      
      // Clean filename
      const courseName = course.name.replace(/[^a-zA-Z0-9]/g, '_');
      link.download = `${courseName}_ontology.owl`;
      
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      
      onSuccess(`Ontology exported for "${course.name}" with all ${lessons.length} lessons!`);
    } catch (err) {
      onError(err.response?.data?.error || 'Failed to export ontology');
    } finally {
      setExporting(false);
      setUploadProgress(null);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      onError('Only PDF files are allowed');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', file.name.replace('.pdf', '').replace(/_/g, ' '));

    try {
      setUploading(true);
      setUploadProgress('Uploading PDF...');

      await lessonApi.create(course.id, formData);

      onSuccess('Lesson uploaded! Click "Parse" to extract sections.');
      await refreshLessons();
      onLessonsChange();
      fileInputRef.current.value = '';
    } catch (err) {
      onError(err.response?.data?.error || 'Failed to upload lesson');
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  const handleParseLesson = async (lessonId, e) => {
    e.stopPropagation();

    try {
      setUploadProgress(`Parsing lesson... This may take a minute.`);
      const response = await lessonApi.parse(lessonId);

      const { section_count, learning_object_count } = response.data;
      onSuccess(`Parsed ${section_count} sections with ${learning_object_count} learning objects!`);
      await refreshLessons();
      onLessonsChange();
    } catch (err) {
      onError(err.response?.data?.error || 'Failed to parse lesson');
    } finally {
      setUploadProgress(null);
    }
  };

  const handleDeleteLesson = async (lessonId, e) => {
    e.stopPropagation();
    if (!window.confirm('Delete this lesson and all its content?')) return;

    try {
      await lessonApi.delete(lessonId);
      onSuccess('Lesson deleted');
      await refreshLessons();
      onLessonsChange();
    } catch (err) {
      onError('Failed to delete lesson');
    }
  };

  return (
    <div className="lesson-manager">
      <div className="card">
        <div className="card-header">
          <div>
            <button className="btn-back" onClick={onBack}>← Back to Courses</button>
            <h2>Lessons in {course.name}</h2>
          </div>
          <div className="upload-button-wrapper" style={{ display: 'flex', gap: '10px' }}>
            {lessons.length > 0 && (
              <button 
                className="btn-secondary"
                onClick={handleExportCourseOntology}
                disabled={exporting}
                title="Export combined ontology for all lessons in this course"
                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
              >
                {exporting ? (
                  <>
                    <span className="spinner" style={{ width: '14px', height: '14px' }}></span>
                    Exporting...
                  </>
                ) : (
                  <>Export Course Ontology</>
                )}
              </button>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              onChange={handleFileUpload}
              style={{ display: 'none' }}
              id="lesson-upload"
            />
            <label htmlFor="lesson-upload" className="btn-primary">
              {uploading ? 'Uploading...' : 'Upload PDF Lesson'}
            </label>
          </div>
        </div>

        {uploadProgress && (
          <div className="progress-message">
            <span className="spinner"></span> {uploadProgress}
          </div>
        )}

        {loading ? (
          <div className="loading-state">Loading lessons...</div>
        ) : lessons.length === 0 ? (
          <div className="empty-state">
            <p>No lessons yet. Upload your first PDF lesson!</p>
            <p className="hint">Lessons are PDF files containing educational content (e.g., "Virtual Memory.pdf")</p>
          </div>
        ) : (
          <div className="lesson-list">
            {lessons.map((lesson) => (
              <div 
                key={lesson.id} 
                className="lesson-card"
                onClick={() => onSelectLesson(lesson)}
              >
                <div className="lesson-info">
                  <h3>{lesson.title}</h3>
                  {lesson.filename && (
                    <p className="filename">{lesson.filename}</p>
                  )}
                  <div className="lesson-stats">
                    <span>{lesson.section_count || 0} Sections</span>
                    {lesson.summary && <span className="parsed-badge">Parsed</span>}
                  </div>
                </div>
                <div className="lesson-actions">
                  <button 
                    className="btn-translate"
                    onClick={(e) => {
                      e.stopPropagation();
                      setViewingTranslationId(lesson.id);
                      setShowTranslationViewer(true);
                    }}
                    title={`View lesson in ${selectedLanguage}`}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                  </button>
                  {!lesson.section_count || lesson.section_count === 0 ? (
                    <button 
                      className="btn-secondary"
                      onClick={(e) => handleParseLesson(lesson.id, e)}
                      title="Parse lesson to extract sections"
                    >
                      Parse
                    </button>
                  ) : (
                    <button 
                      className="btn-secondary"
                      onClick={(e) => { e.stopPropagation(); onSelectLesson(lesson); }}
                    >
                      View Content
                    </button>
                  )}
                  <button 
                    className="btn-icon btn-danger"
                    onClick={(e) => handleDeleteLesson(lesson.id, e)}
                    title="Delete lesson"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                  </button>
                </div>
              </div>
            ))}
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
        entityType="lesson"
        originalText={course.lessons?.find(l => l.id === viewingTranslationId)?.title}
      />
    </div>
  );
}

export default LessonManager;
