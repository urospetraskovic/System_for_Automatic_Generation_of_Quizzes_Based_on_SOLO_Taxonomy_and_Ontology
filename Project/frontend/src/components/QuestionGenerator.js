import React, { useState, useEffect, useRef } from 'react';
import { questionApi, jobsApi } from '../api';

function QuestionGenerator({ course, onQuestionsGenerated, onSuccess, onError }) {
  const [lessons, setLessons] = useState([]);
  const [selectedLessons, setSelectedLessons] = useState([]);
  const [soloLevels, setSoloLevels] = useState({
    unistructural: true,
    multistructural: true,
    relational: true,
    extended_abstract: false
  });
  const [questionsPerLevel, setQuestionsPerLevel] = useState(3);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState(null); // { message, current, total }
  const pollRef = useRef(null);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
  }, []);

  useEffect(() => {
    if (course?.lessons) {
      // Filter to only show parsed lessons
      const parsedLessons = course.lessons.filter(l => l.section_count > 0);
      setLessons(parsedLessons);
    }
  }, [course]);

  const handleLessonToggle = (lessonId) => {
    setSelectedLessons(prev => {
      if (prev.includes(lessonId)) {
        return prev.filter(id => id !== lessonId);
      } else {
        // For extended abstract, allow max 2 lessons
        if (prev.length >= 2 && soloLevels.extended_abstract) {
          onError('For Extended Abstract questions, select exactly 2 lessons');
          return prev;
        }
        return [...prev, lessonId];
      }
    });
  };

  const handleSoloLevelToggle = (level) => {
    setSoloLevels(prev => {
      const newState = { ...prev, [level]: !prev[level] };
      
      // If enabling extended_abstract, ensure 2 lessons are selected
      if (level === 'extended_abstract' && !prev[level]) {
        if (selectedLessons.length < 2) {
          onError('Extended Abstract requires 2 lessons. Please select another lesson.');
        }
      }
      
      return newState;
    });
  };

  // Shared poll-until-done helper used by all three generation modes.
  const pollJob = (jobId) =>
    new Promise((resolve, reject) => {
      pollRef.current = setInterval(async () => {
        try {
          const { data: job } = await jobsApi.get(jobId);
          if (job.progress) setProgress(job.progress);
          if (job.status === 'succeeded') {
            clearInterval(pollRef.current);
            pollRef.current = null;
            resolve(job.result || {});
          } else if (job.status === 'failed') {
            clearInterval(pollRef.current);
            pollRef.current = null;
            reject(new Error(job.error || 'Job failed'));
          }
        } catch (e) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          reject(e);
        }
      }, 1500);
    });

  const reportResult = (result, label = 'Generated') => {
    const { questions, count, solo_distribution } = result || {};
    onQuestionsGenerated(questions || []);
    const summary = Object.entries(solo_distribution || {})
      .filter(([, c]) => c > 0)
      .map(([level, c]) => `${level}: ${c}`)
      .join(', ');
    onSuccess(
      summary
        ? `${label} ${count || 0} questions! (${summary})`
        : `${label} ${count || 0} questions!`
    );
  };

  const handleGenerate = async () => {
    if (selectedLessons.length === 0) {
      onError('Please select at least one lesson');
      return;
    }

    const activeLevels = Object.entries(soloLevels)
      .filter(([, active]) => active)
      .map(([level]) => level);

    if (activeLevels.length === 0) {
      onError('Please select at least one SOLO level');
      return;
    }

    if (soloLevels.extended_abstract && selectedLessons.length < 2) {
      onError('Extended Abstract questions require 2 lessons selected');
      return;
    }

    try {
      setGenerating(true);
      setProgress({ message: 'Queuing job...', current: 0, total: 0 });

      const startResp = await questionApi.generateAsync({
        lesson_ids: selectedLessons,
        solo_levels: activeLevels,
        questions_per_level: questionsPerLevel,
        save_to_db: true,
      });
      const result = await pollJob(startResp.data.job_id);
      reportResult(result, 'Generated');
    } catch (err) {
      onError(err.response?.data?.error || err.message || 'Failed to generate questions');
    } finally {
      setGenerating(false);
      setProgress(null);
    }
  };

  const handleGenerateForCourse = async () => {
    if (!course?.id) {
      onError('No course selected');
      return;
    }
    if (!window.confirm(
      `Generate questions for the WHOLE course "${course.name}"?\n\n` +
      `This will auto-size per-level quotas across every lesson to aim for ~85-90% slide coverage. ` +
      `It can take a while on big courses.`
    )) return;

    try {
      setGenerating(true);
      setProgress({ message: 'Planning course quotas...', current: 0, total: 0 });
      const startResp = await questionApi.generateForCourseAsync(course.id);
      const result = await pollJob(startResp.data.job_id);
      reportResult(result, `Course-wide generation: created`);
    } catch (err) {
      onError(err.response?.data?.error || err.message || 'Failed to generate for course');
    } finally {
      setGenerating(false);
      setProgress(null);
    }
  };

  const handleGenerateForUncovered = async () => {
    if (!course?.id) {
      onError('No course selected');
      return;
    }
    if (!window.confirm(
      `Target uncovered pages in "${course.name}"?\n\n` +
      `For each lesson, this finds substantive pages with no existing questions ` +
      `and generates one unistructural question per LO on those pages. ` +
      `Run this AFTER an initial generation to fill gaps.`
    )) return;

    try {
      setGenerating(true);
      setProgress({ message: 'Computing coverage gaps...', current: 0, total: 0 });
      const startResp = await questionApi.generateForUncoveredAsync(course.id);
      const result = await pollJob(startResp.data.job_id);
      reportResult(result, `Coverage fill: created`);
    } catch (err) {
      onError(err.response?.data?.error || err.message || 'Failed to target uncovered pages');
    } finally {
      setGenerating(false);
      setProgress(null);
    }
  };

  const getSoloLevelDescription = (level) => {
    const descriptions = {
      unistructural: 'From Learning Objects - identify, name, define single facts',
      multistructural: 'From Sections - list, describe, enumerate multiple facts',
      relational: 'From Sections + Learning Objects - compare, explain, relate',
      extended_abstract: 'From 2 Lessons combined - generalize, create, hypothesize'
    };
    return descriptions[level] || '';
  };

  const unparsedLessons = (course?.lessons || []).filter(l => !l.section_count || l.section_count === 0);

  return (
    <div className="question-generator">
      <div className="card">
        <h2>Generate Questions</h2>
        <p className="subtitle">Select lessons and SOLO levels to generate questions</p>

        {/* Lesson Selection */}
        <div className="generator-section">
          <h3>Select Lessons</h3>
          {lessons.length === 0 ? (
            <div className="empty-state">
              <p>No parsed lessons available.</p>
              <p className="hint">Go to Lessons tab and parse your PDF files first.</p>
            </div>
          ) : (
            <div className="lesson-select-grid">
              {lessons.map((lesson) => (
                <div
                  key={lesson.id}
                  className={`lesson-select-card ${selectedLessons.includes(lesson.id) ? 'selected' : ''}`}
                  onClick={() => handleLessonToggle(lesson.id)}
                >
                  <div className="checkbox">
                    {selectedLessons.includes(lesson.id) ? '✓' : ''}
                  </div>
                  <div className="lesson-select-info">
                    <h4>{lesson.title}</h4>
                    <span>{lesson.section_count} sections</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {selectedLessons.length > 0 && (
            <p className="selection-info">
              {selectedLessons.length} lesson(s) selected
              {soloLevels.extended_abstract && selectedLessons.length === 2 && (
                <span className="good"> - Ready for Extended Abstract</span>
              )}
            </p>
          )}

          {unparsedLessons.length > 0 && (
            <p className="warning-hint">
              {unparsedLessons.length} lesson(s) need parsing before they can be used
            </p>
          )}
        </div>

        {/* SOLO Level Selection */}
        <div className="generator-section">
          <h3>SOLO Levels</h3>
          <div className="solo-level-grid">
            {Object.entries(soloLevels).map(([level, active]) => (
              <div
                key={level}
                className={`solo-level-card ${active ? 'active' : ''} ${level === 'extended_abstract' && selectedLessons.length < 2 ? 'disabled' : ''}`}
                onClick={() => handleSoloLevelToggle(level)}
              >
                <div className="solo-header">
                  <div className="checkbox">{active ? '✓' : ''}</div>
                  <h4>{level.replace('_', ' ')}</h4>
                </div>
                <p className="solo-desc">{getSoloLevelDescription(level)}</p>
                {level === 'extended_abstract' && (
                  <span className="solo-note">Requires 2 lessons</span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Questions Per Level */}
        <div className="generator-section">
          <h3>Questions per Level</h3>
          <div className="questions-slider">
            <input
              type="range"
              min="1"
              max="10"
              value={questionsPerLevel}
              onChange={(e) => setQuestionsPerLevel(parseInt(e.target.value))}
            />
            <span className="slider-value">{questionsPerLevel}</span>
          </div>
          <p className="estimate">
            Estimated total: ~{Object.values(soloLevels).filter(Boolean).length * questionsPerLevel} questions
          </p>
        </div>

        {/* Generate Button */}
        <div className="generator-actions">
          {progress && (
            <div className="progress-message" style={{ width: '100%' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: 6 }}>
                <span className="spinner"></span>
                <span>{progress.message || 'Working...'}</span>
                {progress.total > 0 && (
                  <span style={{ color: 'var(--neutral-500)', fontSize: '0.9rem' }}>
                    ({progress.current || 0}/{progress.total})
                  </span>
                )}
              </div>
              {progress.total > 0 && (
                <div style={{ background: 'var(--neutral-200)', height: 8, borderRadius: 4, overflow: 'hidden' }}>
                  <div
                    style={{
                      width: `${Math.min(100, ((progress.current || 0) / progress.total) * 100)}%`,
                      height: '100%',
                      background: 'var(--primary-600, #2563eb)',
                      transition: 'width 0.4s ease',
                    }}
                  />
                </div>
              )}
            </div>
          )}
          <button
            className="btn-primary btn-large"
            onClick={handleGenerate}
            disabled={generating || selectedLessons.length === 0}
          >
            {generating ? 'Generating...' : 'Generate Questions'}
          </button>
        </div>

        {/* Auto-quota and coverage-fill buttons. These operate on the WHOLE
            course (course prop) regardless of the manual selection above. */}
        <div className="generator-section" style={{ borderTop: '1px solid var(--neutral-200, #e5e7eb)', paddingTop: '20px', marginTop: '20px' }}>
          <h3>Automated Course Coverage</h3>
          <p className="subtitle" style={{ marginTop: 0, marginBottom: '12px' }}>
            These options ignore the manual selection above and operate on every lesson in <strong>{course?.name || 'this course'}</strong>.
          </p>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <button
              className="btn-secondary btn-large"
              onClick={handleGenerateForCourse}
              disabled={generating || !course?.id}
              title="Auto-size per-level quotas across every lesson to aim for ~85-90% slide coverage."
            >
              Generate for Whole Course
            </button>
            <button
              className="btn-secondary btn-large"
              onClick={handleGenerateForUncovered}
              disabled={generating || !course?.id}
              title="Find substantive pages with no questions and generate one question per LO on those pages. Run after the initial pass."
            >
              Target Uncovered Pages
            </button>
          </div>
          <p className="hint" style={{ marginTop: '8px', fontSize: '0.85rem', color: 'var(--neutral-500, #6b7280)' }}>
            Typical flow: <em>Generate for Whole Course</em> first, then check the Coverage panel and run <em>Target Uncovered Pages</em> to fill gaps.
          </p>
        </div>
      </div>
    </div>
  );
}

export default QuestionGenerator;
