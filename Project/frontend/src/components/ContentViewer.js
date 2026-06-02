import React, { useState, useEffect } from 'react';
import { lessonApi, sectionApi, learningObjectApi, ontologyApi, questionApi } from '../api';
import TranslationViewer from './TranslationViewer';
import CoveragePanel from './CoveragePanel';
import MCQLintPanel from './MCQLintPanel';
import SoloJudgePanel from './SoloJudgePanel';
import AdvancedQualityPanel from './AdvancedQualityPanel';
import ExtendedValidityPanel from './ExtendedValidityPanel';
import QualityOverviewPanel from './QualityOverviewPanel';

// Backend metric_key (as written by backend/services/validation_cache.put())
// → frontend short key (as read by buildHeadline + sub-panel props). The
// names diverged historically: backend uses descriptive snake_case, FE uses
// short labels. Translating once at the cache fetch boundary keeps the rest
// of the FE consistent and fixes silent headline drops on lesson reload.
const BACKEND_TO_FE_KEY = {
  lint: 'lint',
  solo_judge: 'judge',
  cove: 'cove',
  solvability: 'solv',
  stem_only: 'stem',
  ioc: 'ioc',
  readability: 'readability',
  ambiguity: 'ambiguity',
  misconception_mining: 'misc',
  grammar_homogeneity: 'grammar',
  face_validity: 'face',
};

function translateCachedQuality(payload) {
  const out = {};
  for (const [k, v] of Object.entries(payload || {})) {
    const feKey = BACKEND_TO_FE_KEY[k] || k;
    out[feKey] = v;
  }
  return out;
}

function ContentViewer({ lesson, onBack, onSuccess, onError, onLessonUpdate }) {
  const [sections, setSections] = useState([]);
  const [expandedSection, setExpandedSection] = useState(null);
  const [loading, setLoading] = useState(false);
  const [ontology, setOntology] = useState([]);
  const [showOntology, setShowOntology] = useState(false);
  const [editingLO, setEditingLO] = useState(null);
  const [editFormData, setEditFormData] = useState({});
  const [showEditModal, setShowEditModal] = useState(false);

  // Shared quality-check results. When QualityOverviewPanel runs Run All / Quick
  // Run, it pushes the per-check data here; the sub-panels (SOLO judge, CoVe,
  // Solvability, Extended A–H) read their slice from this and display it
  // without forcing the user to click Run again on each sub-panel.
  //
  // On lesson mount we also hit the server-side validation_cache via
  // /api/lessons/<id>/quality-cache to rehydrate whatever was previously
  // run — without this, headlines disappear after every page reload.
  //
  // Key translation: the backend stores cached reports under metric keys like
  // "solo_judge", "grammar_homogeneity", "face_validity", but every React
  // panel here reads short FE keys ("judge", "grammar", "face", …). Without
  // mapping at this boundary, the headline dashboard silently misses ~half
  // its tiles on lesson reload, even though the data is sitting in cache.
  const [qualityResults, setQualityResults] = useState({});

  useEffect(() => {
    let cancelled = false;
    if (!lesson?.id) {
      setQualityResults({});
      return;
    }
    // Fetch both the persistent validation_cache (LLM-backed metrics) and
    // the live coverage report (cheap, no LLM, never cached) in parallel.
    // Merging both into qualityResults means the headline dashboard renders
    // all 12 tiles on lesson open without forcing the user to click Run.
    Promise.all([
      questionApi.qualityCache(lesson.id).catch(() => ({ data: {} })),
      lessonApi.getCoverage(lesson.id).catch(() => null),
    ]).then(([cacheRes, covRes]) => {
      if (cancelled) return;
      const next = translateCachedQuality(cacheRes?.data || {});
      if (covRes?.data) {
        next.coverage = covRes.data;
      }
      setQualityResults(next);
    });
    return () => { cancelled = true; };
  }, [lesson?.id]);
  const [showTranslationViewer, setShowTranslationViewer] = useState(false);
  const [viewingTranslationId, setViewingTranslationId] = useState(null);
  const [viewingTranslationType, setViewingTranslationType] = useState('section');

  useEffect(() => {
    if (lesson?.sections) {
      setSections(lesson.sections);
    } else {
      fetchSections();
    }
    
    if (lesson?.id) {
      fetchOntology();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lesson]);

  const fetchSections = async () => {
    if (!lesson?.id) return;
    
    try {
      setLoading(true);
      const response = await lessonApi.getSections(lesson.id);
      setSections(response.data.sections || []);
    } catch (err) {
      onError('Failed to fetch sections');
    } finally {
      setLoading(false);
    }
  };

  const fetchOntology = async () => {
    if (!lesson?.id) return;
    try {
      const response = await lessonApi.getOntology(lesson.id);
      setOntology(response.data.relationships || []);
    } catch (err) {
      // Silent failure for ontology fetch
    }
  };

  const fetchLearningObjects = async (sectionId) => {
    try {
      const response = await sectionApi.getById(sectionId);
      const updatedSection = response.data.section;
      
      setSections(sections.map(s => 
        s.id === sectionId ? { ...s, learning_objects: updatedSection.learning_objects } : s
      ));
    } catch (err) {
      // Silent failure for learning objects fetch
    }
  };

  const toggleSection = (sectionId) => {
    if (expandedSection === sectionId) {
      setExpandedSection(null);
    } else {
      setExpandedSection(sectionId);
      // Fetch learning objects if not already loaded
      const section = sections.find(s => s.id === sectionId);
      if (section && !section.learning_objects) {
        fetchLearningObjects(sectionId);
      }
    }
  };

  const handleEditLO = (lo) => {
    setEditingLO(lo);
    setEditFormData({
      title: lo.title,
      content: lo.content,
      object_type: lo.object_type,
      keywords: lo.keywords ? lo.keywords.join(', ') : ''
    });
    setShowEditModal(true);
  };

  const handleUpdateLO = async () => {
    if (!editingLO) return;
    
    try {
      const keywordsArray = editFormData.keywords
        ? editFormData.keywords.split(',').map(k => k.trim()).filter(k => k)
        : [];
      
      const response = await learningObjectApi.update(editingLO.id, {
        title: editFormData.title,
        content: editFormData.content,
        object_type: editFormData.object_type,
        keywords: keywordsArray
      });
      
      // Update sections with new learning object data
      setSections(sections.map(s => ({
        ...s,
        learning_objects: s.learning_objects.map(lo =>
          lo.id === editingLO.id ? response.data.learning_object : lo
        )
      })));
      
      setShowEditModal(false);
      setEditingLO(null);
      onSuccess('Learning object updated successfully');
    } catch (err) {
      onError(err.response?.data?.error || 'Failed to update learning object');
    }
  };

  const handleDeleteLO = async (loId, loTitle) => {
    if (!window.confirm(`Are you sure you want to delete "${loTitle}"?`)) {
      return;
    }
    
    try {
      await learningObjectApi.delete(loId);
      
      // Remove from sections
      setSections(sections.map(s => ({
        ...s,
        learning_objects: s.learning_objects.filter(lo => lo.id !== loId),
        learning_object_count: (s.learning_object_count || 1) - 1
      })));
      
      onSuccess('Learning object deleted successfully');
    } catch (err) {
      onError(err.response?.data?.error || 'Failed to delete learning object');
    }
  };

  const handleDownloadOWL = async () => {
    try {
      const response = await ontologyApi.downloadLessonOwl(lesson.id);

      const contentDisposition = response.headers['content-disposition'];
      let filename = `ontology_${lesson.title.replace(/[^a-zA-Z0-9]/g, '_')}.owl`;
      if (contentDisposition && contentDisposition.includes('filename=')) {
        filename = contentDisposition.split('filename=')[1].replace(/"/g, '');
      }

      const url = window.URL.createObjectURL(response.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      onError('Failed to download ontology file');
    }
  };

  const handleDeleteRelationship = async (relId) => {
    if (!window.confirm('Are you sure you want to delete this relationship?')) {
      return;
    }

    try {
      await ontologyApi.deleteRelationship(relId);
      setOntology(ontology.filter(r => r.id !== relId));
      onSuccess('Relationship deleted successfully');
    } catch (err) {
      onError('Failed to delete relationship');
    }
  };

  const handleClearOntology = async () => {
    if (!window.confirm('Are you sure you want to clear ALL ontology relationships? This cannot be undone.')) {
      return;
    }
    
    try {
      setLoading(true);
      const response = await lessonApi.clearOntology(lesson.id);
      setOntology([]);
      onSuccess(`Cleared ${response.data.cleared_count} relationships successfully`);
    } catch (err) {
      onError(err.response?.data?.error || 'Failed to clear ontology');
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerateOntology = async () => {
    if (!window.confirm('Generate ontology relationships? This will create relationships based on your sections and learning objects.')) {
      return;
    }
    
    try {
      setLoading(true);
      const response = await lessonApi.generateOntology(lesson.id);
      onSuccess(`Generated ${response.data.generated_count} ontology relationships`);
      // Refresh ontology
      fetchOntology();
    } catch (err) {
      onError(err.response?.data?.error || 'Failed to generate ontology');
    } finally {
      setLoading(false);
    }
  };

  const handleParseLesson = async () => {
    try {
      setLoading(true);
      const response = await lessonApi.parse(lesson.id);
      
      const { sections: newSections, section_count, learning_object_count, ontology_relationships } = response.data;
      setSections(newSections || []);
      onSuccess(`Parsed ${section_count} sections with ${learning_object_count} learning objects and ${ontology_relationships} ontology relationships!`);
      
      // Refresh ontology
      fetchOntology();
      
      // Update parent with new lesson data
      if (onLessonUpdate) {
        onLessonUpdate({ ...lesson, sections: newSections, section_count });
      }
    } catch (err) {
      onError(err.response?.data?.error || 'Failed to parse lesson');
    } finally {
      setLoading(false);
    }
  };

  const getLearningObjectTypeIcon = (type) => {
    const icons = {
      concept: '[C]',
      definition: '[D]',
      procedure: '[P]',
      principle: '[PR]',
      example: '[E]',
      fact: '[F]'
    };
    return icons[type] || '[O]';
  };

  return (
    <div className="content-viewer">
      <div className="card">
        <div className="card-header">
          <div>
            <button className="btn-back" onClick={onBack}>Back to Lessons</button>
            <h2>{lesson.title}</h2>
            {lesson.filename && <span className="filename">{lesson.filename}</span>}
          </div>
          {sections.length === 0 && (
            <button 
              className="btn-primary" 
              onClick={handleParseLesson}
              disabled={loading}
            >
              {loading ? 'Parsing...' : 'Parse Content'}
            </button>
          )}
        </div>

        {lesson.summary && (
          <div className="lesson-summary">
            <h4>Summary</h4>
            <p>{lesson.summary}</p>
          </div>
        )}

        {/* Master Quality Overview hub — runs everything at once */}
        {sections.length > 0 && (
          <QualityOverviewPanel
            lessonId={lesson.id}
            onResultsChange={setQualityResults}
            initialResults={qualityResults}
          />
        )}

        {/* PDF Coverage Panel */}
        {sections.length > 0 && (
          <CoveragePanel lessonId={lesson.id} refreshKey={sections.length} />
        )}

        {/* MCQ Quality (Haladyna lint) Panel */}
        {sections.length > 0 && (
          <MCQLintPanel lessonId={lesson.id} refreshKey={sections.length} />
        )}

        {/* SOLO LLM-judge Panel */}
        {sections.length > 0 && (
          <SoloJudgePanel lessonId={lesson.id} initialData={qualityResults.judge} />
        )}

        {/* Advanced validity: CoVe + Solvability */}
        {sections.length > 0 && (
          <AdvancedQualityPanel
            lessonId={lesson.id}
            initialCove={qualityResults.cove}
            initialSolv={qualityResults.solv}
          />
        )}

        {/* Extended validity layer: A-H (IOC, stem-only, readability, ambiguity,
            misconception mining, grammar homogeneity, face validity) */}
        {sections.length > 0 && (
          <ExtendedValidityPanel
            lessonId={lesson.id}
            initialResults={{
              ioc: qualityResults.ioc,
              stem: qualityResults.stem,
              readability: qualityResults.readability,
              ambiguity: qualityResults.ambiguity,
              misconception: qualityResults.misc,
              grammar: qualityResults.grammar,
              face: qualityResults.face,
            }}
          />
        )}

        {/* Domain Ontology Section */}
        {sections.length > 0 && (
          <div className="ontology-section" style={{ padding: '20px', borderTop: '1px solid var(--neutral-200)', background: 'var(--neutral-50)' }}>
            <div 
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
            >
              <div 
                style={{ display: 'flex', alignItems: 'center', gap: '15px', cursor: 'pointer', flex: 1 }}
                onClick={() => setShowOntology(!showOntology)}
              >
                <h4 style={{ margin: 0 }}>Domain Ontology</h4>
                <span className="badge" style={{ background: 'var(--primary-lighter)', color: 'var(--primary-dark)', padding: '2px 8px', borderRadius: '10px', fontSize: '0.8rem' }}>
                  {ontology.length} Relationships
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <button 
                  onClick={handleRegenerateOntology}
                  disabled={loading}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '10px 16px',
                    background: 'var(--info)',
                    color: 'white',
                    borderRadius: '6px',
                    textDecoration: 'none',
                    fontSize: '0.9rem',
                    fontWeight: '600',
                    cursor: loading ? 'not-allowed' : 'pointer',
                    transition: 'background 0.2s',
                    border: 'none',
                    opacity: loading ? 0.6 : 1
                  }}
                  onMouseEnter={(e) => !loading && (e.target.style.background = '#2563eb')}
                  onMouseLeave={(e) => !loading && (e.target.style.background = 'var(--info)')}
                  title="Generate ontology relationships based on current sections and learning objects"
                >
                  Generate Ontology
                </button>
                <button 
                  onClick={handleClearOntology}
                  disabled={loading || ontology.length === 0}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '10px 16px',
                    background: 'var(--warning)',
                    color: 'white',
                    borderRadius: '6px',
                    textDecoration: 'none',
                    fontSize: '0.9rem',
                    fontWeight: '600',
                    cursor: (loading || ontology.length === 0) ? 'not-allowed' : 'pointer',
                    transition: 'background 0.2s',
                    border: 'none',
                    opacity: (loading || ontology.length === 0) ? 0.6 : 1
                  }}
                  onMouseEnter={(e) => !(loading || ontology.length === 0) && (e.target.style.background = '#d97706')}
                  onMouseLeave={(e) => !(loading || ontology.length === 0) && (e.target.style.background = 'var(--warning)')}
                  title="Delete all ontology relationships"
                >
                  Delete All
                </button>
                {ontology.length > 0 && (
                  <button 
                    onClick={handleDownloadOWL}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '10px 18px',
                      background: 'var(--primary-light)',
                      color: 'white',
                      borderRadius: '6px',
                      textDecoration: 'none',
                      fontSize: '0.95rem',
                      fontWeight: '600',
                      cursor: 'pointer',
                      transition: 'background 0.2s',
                      border: 'none'
                    }}
                    onMouseEnter={(e) => e.target.style.background = '#1d4ed8'}
                    onMouseLeave={(e) => e.target.style.background = 'var(--primary-light)'}
                    title="Download ontology as OWL file for Protégé"
                  >
                    Download OWL
                  </button>
                )}
                <span style={{ fontSize: '0.8rem', color: 'var(--neutral-600)' }}>{showOntology ? 'Hide' : 'Show'}</span>
              </div>
            </div>

            {showOntology && (
              <div className="ontology-content" style={{ marginTop: '20px' }}>
                {ontology.length > 0 ? (
                  <div className="ontology-table-container" style={{ 
                    overflowX: 'auto', 
                    background: 'white', 
                    borderRadius: '12px', 
                    border: '1px solid var(--neutral-200)',
                    boxShadow: 'var(--shadow-sm)'
                  }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                      <thead>
                        <tr style={{ background: 'var(--neutral-50)', borderBottom: '2px solid var(--neutral-200)' }}>
                          <th style={{ padding: '12px 20px', fontSize: '0.85rem', color: 'var(--neutral-600)', fontWeight: '600' }}>Source Concept</th>
                          <th style={{ padding: '12px 20px', fontSize: '0.85rem', color: 'var(--neutral-600)', fontWeight: '600', textAlign: 'center' }}>Relationship</th>
                          <th style={{ padding: '12px 20px', fontSize: '0.85rem', color: 'var(--neutral-600)', fontWeight: '600' }}>Target Concept</th>
                          <th style={{ padding: '12px 20px', fontSize: '0.85rem', color: 'var(--neutral-600)', fontWeight: '600', textAlign: 'center' }}>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ontology.map((rel, idx) => (
                          <tr key={idx} style={{ borderBottom: idx === ontology.length - 1 ? 'none' : '1px solid var(--neutral-100)' }}>
                            <td style={{ padding: '15px 20px', fontWeight: '600', color: 'var(--neutral-800)' }}>
                              {rel.source_title}
                            </td>
                            <td style={{ padding: '15px 20px', textAlign: 'center' }}>
                              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                                <span style={{
                                  fontSize: '0.7rem',
                                  fontWeight: '800',
                                  textTransform: 'uppercase',
                                  color: 'var(--primary-main)',
                                  background: 'var(--primary-lighter)',
                                  padding: '2px 8px',
                                  borderRadius: '4px',
                                  border: '1px solid var(--primary-light)',
                                  whiteSpace: 'nowrap'
                                }}>
                                  {rel.relationship_type.replace('_', ' ')}
                                </span>
                                <span style={{ color: 'var(--neutral-400)', fontSize: '1.2rem', lineHeight: '1' }}>⟶</span>
                                {rel.description && (
                                  <span style={{ fontSize: '0.75rem', color: 'var(--neutral-500)', fontStyle: 'italic', maxWidth: '200px' }}>
                                    {rel.description}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td style={{ padding: '15px 20px', fontWeight: '600', color: 'var(--neutral-800)' }}>
                              {rel.target_title}
                            </td>
                            <td style={{ padding: '15px 20px', textAlign: 'center' }}>
                              <button 
                                className="btn-icon btn-delete"
                                onClick={() => handleDeleteRelationship(rel.id)}
                                title="Delete relationship"
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#d32f2f', fontWeight: 'bold', fontSize: '0.85rem', padding: '4px 8px' }}
                              >
                                Delete
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div style={{ padding: '40px', textAlign: 'center', background: 'white', borderRadius: '12px', border: '1px dashed var(--neutral-300)' }}>
                    <p style={{ color: 'var(--neutral-500)', margin: 0 }}>No ontology relationships identified yet. Parse the lesson to generate them.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {loading ? (
          <div className="loading-state">
            <span className="spinner"></span> Parsing lesson content...
          </div>
        ) : sections.length === 0 ? (
          <div className="empty-state">
            <p>This lesson hasn't been parsed yet.</p>
            <p>Click "Parse Content" to extract sections and learning objects using AI.</p>
          </div>
        ) : (
          <div className="sections-list">
            <h3>Sections ({sections.length})</h3>
            
            {sections.map((section, idx) => (
              <div key={section.id} className="section-card">
                <div 
                  className="section-header"
                  onClick={() => toggleSection(section.id)}
                >
                  <div className="section-title">
                    <span className="section-number">{idx + 1}</span>
                    <h4>{section.title}</h4>
                    {section.start_page && section.end_page && (
                      <span className="page-range" style={{ marginLeft: '12px', color: 'var(--neutral-500)', fontSize: '0.85rem' }}>
                        Pages {section.start_page}-{section.end_page}
                      </span>
                    )}
                  </div>
                  <div className="section-meta" style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                    <button
                      className="btn-icon btn-translate"
                      onClick={(e) => {
                        e.stopPropagation();
                        setViewingTranslationId(section.id);
                        setViewingTranslationType('section');
                        setShowTranslationViewer(true);
                      }}
                      title="View section translation"
                      style={{ 
                        background: 'none', 
                        border: 'none', 
                        cursor: 'pointer', 
                        color: '#2563eb',
                        fontSize: '1.1rem',
                        padding: '4px 8px'
                      }}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                    </button>
                    <span className="lo-count" style={{ 
                      background: 'var(--neutral-100)', 
                      padding: '2px 10px', 
                      borderRadius: '12px', 
                      fontSize: '0.8rem',
                      color: 'var(--neutral-600)',
                      fontWeight: '500'
                    }}>
                      {section.learning_object_count || 0} Learning Objects
                    </span>
                    <span className="expand-icon" style={{ fontSize: '0.8rem' }}>
                      {expandedSection === section.id ? 'Hide' : 'Show'}
                    </span>
                  </div>
                </div>

                {expandedSection === section.id && (
                  <div className="section-content">
                    {section.summary && (
                      <div className="section-summary">
                        <p>{section.summary}</p>
                      </div>
                    )}

                    {section.learning_objects && section.learning_objects.length > 0 ? (
                      <div className="learning-objects">
                        <h5>Learning Objects:</h5>
                        {section.learning_objects.map((lo) => (
                          <div key={lo.id} className="learning-object">
                            <div className="lo-header">
                              <span className="lo-icon">
                                {getLearningObjectTypeIcon(lo.object_type)}
                              </span>
                              <span className="lo-title">{lo.title}</span>
                              <span className="lo-type">{lo.object_type}</span>
                              {/* AI Generation Status Badge */}
                              <span className={`lo-status-badge ${lo.human_modified ? 'human-modified' : lo.is_ai_generated ? 'ai-generated' : 'human-created'}`}>
                                {lo.human_modified ? 'Human Modified' : lo.is_ai_generated ? 'AI Generated' : 'Human Created'}
                              </span>
                              {/* Action Buttons */}
                              <button 
                                className="btn-icon btn-translate"
                                onClick={() => {
                                  setViewingTranslationId(lo.id);
                                  setViewingTranslationType('learning-object');
                                  setShowTranslationViewer(true);
                                }}
                                title="View translation"
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb', fontSize: '0.95rem', fontWeight: 'bold', padding: '4px 8px' }}
                              >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                              </button>
                              <button 
                                className="btn-icon btn-edit"
                                onClick={() => handleEditLO(lo)}
                                title="Edit"
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1976d2', fontSize: '0.85rem', fontWeight: 'bold', padding: '4px 8px' }}
                              >
                                Edit
                              </button>
                              <button 
                                className="btn-icon btn-delete"
                                onClick={() => handleDeleteLO(lo.id, lo.title)}
                                title="Delete"
                                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#d32f2f', fontSize: '0.85rem', fontWeight: 'bold', padding: '4px 8px' }}
                              >
                                Delete
                              </button>
                            </div>
                            {/* Rich Description */}
                            {lo.description && (
                              <p className="lo-content" style={{ color: 'var(--neutral-700)', lineHeight: '1.6', marginTop: '8px' }}>
                                {lo.description}
                              </p>
                            )}
                            {/* Content Fallback */}
                            {!lo.description && lo.content && (
                              <p className="lo-content">{lo.content}</p>
                            )}
                            {/* Key Points */}
                            {lo.key_points && lo.key_points.length > 0 && (
                              <div style={{ marginTop: '8px', marginBottom: '8px' }}>
                                <strong style={{ fontSize: '0.85rem', color: 'var(--neutral-600)' }}>Key Points:</strong>
                                <ul style={{ margin: '4px 0 0 20px', fontSize: '0.85rem', color: 'var(--neutral-700)' }}>
                                  {lo.key_points.map((point, i) => (
                                    <li key={i}>{point}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {/* Keywords */}
                            {lo.keywords && lo.keywords.length > 0 && (
                              <div className="lo-keywords">
                                {lo.keywords.map((kw, i) => (
                                  <span key={i} className="keyword-tag">{kw}</span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="no-los">No learning objects extracted for this section.</p>
                    )}

                    {section.content && (
                      <details className="raw-content">
                        <summary>View Raw Content</summary>
                        <pre>{section.content}</pre>
                      </details>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="content-stats">
          <div className="stat">
            <span className="stat-value">{sections.length}</span>
            <span className="stat-label">Sections</span>
          </div>
          <div className="stat">
            <span className="stat-value">
              {sections.reduce((acc, s) => acc + (s.learning_object_count || 0), 0)}
            </span>
            <span className="stat-label">Learning Objects</span>
          </div>
        </div>
      </div>

      {/* Edit Learning Object Modal */}
      {showEditModal && editingLO && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Edit Learning Object</h3>
              <button 
                className="btn-close" 
                onClick={() => setShowEditModal(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.5rem', color: '#666', padding: '0', width: '24px', height: '24px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Title</label>
                <input
                  type="text"
                  value={editFormData.title || ''}
                  onChange={(e) => setEditFormData({...editFormData, title: e.target.value})}
                  placeholder="Learning object title"
                />
              </div>
              <div className="form-group">
                <label>Type</label>
                <select
                  value={editFormData.object_type || ''}
                  onChange={(e) => setEditFormData({...editFormData, object_type: e.target.value})}
                >
                  <option value="">Select type...</option>
                  <option value="concept">Concept</option>
                  <option value="definition">Definition</option>
                  <option value="procedure">Procedure</option>
                  <option value="principle">Principle</option>
                  <option value="example">Example</option>
                  <option value="fact">Fact</option>
                </select>
              </div>
              <div className="form-group">
                <label>Content</label>
                <textarea
                  value={editFormData.content || ''}
                  onChange={(e) => setEditFormData({...editFormData, content: e.target.value})}
                  placeholder="Learning object content"
                  rows="6"
                />
              </div>
              <div className="form-group">
                <label>Keywords (comma-separated)</label>
                <input
                  type="text"
                  value={editFormData.keywords || ''}
                  onChange={(e) => setEditFormData({...editFormData, keywords: e.target.value})}
                  placeholder="keyword1, keyword2, keyword3"
                />
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
                onClick={handleUpdateLO}
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Translation Viewer Modal */}
      <TranslationViewer
        isOpen={showTranslationViewer}
        onClose={() => {
          setShowTranslationViewer(false);
          setViewingTranslationId(null);
        }}
        entityId={viewingTranslationId}
        entityType={viewingTranslationType}
        originalText={
          viewingTranslationType === 'section'
            ? sections.find(s => s.id === viewingTranslationId)?.title || sections.find(s => s.id === viewingTranslationId)?.summary
            : sections.flatMap(s => s.learning_objects || []).find(lo => lo.id === viewingTranslationId)?.title
        }
      />
    </div>
  );
}

export default ContentViewer;
