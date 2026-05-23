import React, { useEffect, useState } from 'react';
import { lessonApi } from '../api';

function CoveragePanel({ lessonId, refreshKey }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!lessonId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    lessonApi.getCoverage(lessonId)
      .then((res) => {
        if (!cancelled) setData(res.data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.response?.data?.error || 'Failed to load coverage');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [lessonId, refreshKey]);

  if (!lessonId) return null;

  const headerStyle = {
    padding: '20px',
    borderTop: '1px solid var(--neutral-200)',
    background: 'var(--neutral-50)',
  };

  const renderHeatStrip = (pages) => {
    if (!pages || pages.length === 0) return null;
    const maxChars = Math.max(1, ...pages.map((p) => p.char_count));
    return (
      <div style={{ display: 'flex', gap: '2px', flexWrap: 'wrap', marginTop: '12px' }}>
        {pages.map((p) => {
          const weight = p.char_count / maxChars;
          const height = 12 + Math.round(weight * 28);
          const covered = p.question_count > 0;
          const bg = covered
            ? `rgba(34, 197, 94, ${0.3 + 0.6 * weight})`
            : p.char_count < 50
              ? 'var(--neutral-200)'
              : `rgba(239, 68, 68, ${0.25 + 0.5 * weight})`;
          const tooltip = `Page ${p.page} — ${p.char_count} chars, ${p.learning_object_count} LOs, ${p.question_count} questions`;
          return (
            <div
              key={p.page}
              title={tooltip}
              style={{
                width: '14px',
                height: `${height}px`,
                background: bg,
                borderRadius: '2px',
                cursor: 'help',
              }}
            />
          );
        })}
      </div>
    );
  };

  return (
    <div style={headerStyle}>
      <div
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <h4 style={{ margin: 0 }}>PDF Coverage</h4>
          {data?.available && (
            <span className="badge" style={{
              background: 'var(--primary-lighter)',
              color: 'var(--primary-dark)',
              padding: '2px 8px',
              borderRadius: '10px',
              fontSize: '0.8rem',
            }}>
              {data.weighted_coverage_pct}% pages
            </span>
          )}
          {data?.concept_coverage?.available && (
            <span className="badge" style={{
              background: '#dbeafe',
              color: '#1e3a8a',
              padding: '2px 8px',
              borderRadius: '10px',
              fontSize: '0.8rem',
            }}>
              {data.concept_coverage.weighted_concept_coverage_pct}% concepts
            </span>
          )}
        </div>
        <span style={{ fontSize: '0.8rem', color: 'var(--neutral-600)' }}>
          {expanded ? 'Hide' : 'Show'}
        </span>
      </div>

      {expanded && (
        <div style={{ marginTop: '16px' }}>
          {loading && <p style={{ color: 'var(--neutral-500)' }}>Computing coverage…</p>}
          {error && <p style={{ color: '#d32f2f' }}>{error}</p>}

          {data && !data.available && (
            <p style={{ color: 'var(--neutral-500)' }}>{data.reason}</p>
          )}

          {data && data.available && (
            <>
              {data.reconstructed && (
                <div style={{ marginBottom: '12px', padding: '8px 12px', background: '#fffbeb', borderRadius: '6px', border: '1px solid #fde68a', fontSize: '0.85rem', color: '#92400e' }}>
                  Page metadata was reconstructed from text markers. Re-upload + re-parse this PDF for fully precise per-page counts.
                </div>
              )}

              {data.concept_coverage?.available && (
                <ConceptCoverageSection data={data.concept_coverage} />
              )}

              {data.concept_coverage && !data.concept_coverage.available && (
                <div style={{ marginBottom: '16px', padding: '8px 12px', background: 'var(--neutral-100)', borderRadius: '6px', fontSize: '0.85rem', color: 'var(--neutral-600)' }}>
                  Concept coverage unavailable: {data.concept_coverage.reason}
                </div>
              )}

              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: '12px',
                background: 'white',
                padding: '16px',
                borderRadius: '8px',
                border: '1px solid var(--neutral-200)',
              }}>
                <Stat label="Pages covered" value={`${data.pages_covered} / ${data.total_pages}`} sub={`${data.page_coverage_pct}%`} />
                <Stat label="Weighted coverage" value={`${data.weighted_coverage_pct}%`} sub="by character count" />
                <Stat label="Substantive coverage" value={`${data.substantive_weighted_coverage_pct}%`} sub="excludes near-empty pages" />
                <Stat label="Total questions" value={data.total_questions} sub={`${data.questions_with_page_data} with page data`} />
              </div>

              <div style={{ marginTop: '16px', background: 'white', padding: '16px', borderRadius: '8px', border: '1px solid var(--neutral-200)' }}>
                <div style={{ fontSize: '0.85rem', color: 'var(--neutral-600)', marginBottom: '8px' }}>
                  Per-page heatmap — bar height = character count, green = questions hit this page, red = uncovered, gray = near-empty page.
                </div>
                {renderHeatStrip(data.pages)}
              </div>

              {data.uncovered_substantive_pages?.length > 0 && (
                <div style={{ marginTop: '16px', padding: '12px 16px', background: '#fef2f2', borderRadius: '8px', border: '1px solid #fecaca' }}>
                  <div style={{ fontWeight: 600, marginBottom: '4px', color: '#991b1b' }}>
                    Substantive pages with no questions: {data.uncovered_substantive_pages.length}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: '#7f1d1d' }}>
                    Pages {data.uncovered_substantive_pages.join(', ')}
                  </div>
                </div>
              )}

              {data.questions_without_page_data > 0 && (
                <div style={{ marginTop: '12px', fontSize: '0.8rem', color: 'var(--neutral-500)' }}>
                  {data.questions_without_page_data} older question(s) have no page mapping (re-generate them to include in coverage).
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ConceptCoverageSection({ data }) {
  const [showAll, setShowAll] = useState(false);
  const uncovered = data.top_uncovered_concepts || [];
  const visibleUncovered = showAll ? uncovered : uncovered.slice(0, 8);

  return (
    <div style={{
      marginBottom: '16px',
      background: 'white',
      padding: '16px',
      borderRadius: '8px',
      border: '1px solid var(--neutral-200)',
      borderLeft: '4px solid #2563eb',
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: '12px' }}>
        <div>
          <div style={{ fontWeight: 700, color: 'var(--neutral-800)' }}>Concept coverage</div>
          <div style={{ fontSize: '0.8rem', color: 'var(--neutral-500)' }}>
            Semantic coverage over the lesson's ontology (LO titles + keywords)
          </div>
        </div>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '12px',
      }}>
        <Stat
          label="Concepts covered"
          value={`${data.concepts_covered} / ${data.total_concepts}`}
          sub={`${data.concept_coverage_pct}%`}
        />
        <Stat
          label="Weighted by centrality"
          value={`${data.weighted_concept_coverage_pct}%`}
          sub="hubs count for more"
        />
      </div>

      {uncovered.length > 0 && (
        <div style={{ marginTop: '14px' }}>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--neutral-700)', marginBottom: '6px' }}>
            Top uncovered concepts ({uncovered.length})
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {visibleUncovered.map((c) => (
              <span
                key={c.normalized}
                title={`weight ${c.weight}`}
                style={{
                  fontSize: '0.8rem',
                  padding: '3px 8px',
                  background: '#fef2f2',
                  color: '#991b1b',
                  border: '1px solid #fecaca',
                  borderRadius: '12px',
                }}
              >
                {c.concept}
              </span>
            ))}
            {uncovered.length > 8 && (
              <button
                onClick={() => setShowAll(!showAll)}
                style={{
                  fontSize: '0.8rem',
                  padding: '3px 8px',
                  background: 'transparent',
                  border: '1px solid var(--neutral-300)',
                  borderRadius: '12px',
                  cursor: 'pointer',
                  color: 'var(--neutral-600)',
                }}
              >
                {showAll ? 'show fewer' : `+${uncovered.length - 8} more`}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, sub }) {
  return (
    <div>
      <div style={{ fontSize: '0.75rem', color: 'var(--neutral-500)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ fontSize: '1.6rem', fontWeight: 700, color: 'var(--neutral-800)' }}>{value}</div>
      {sub && <div style={{ fontSize: '0.8rem', color: 'var(--neutral-500)' }}>{sub}</div>}
    </div>
  );
}

export default CoveragePanel;
