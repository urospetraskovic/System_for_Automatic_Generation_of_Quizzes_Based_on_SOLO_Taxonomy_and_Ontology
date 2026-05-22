import React, { useEffect, useState } from 'react';
import { questionApi } from '../api';

// Codes that are domain-critical errors (red) vs. style/format warnings (amber).
const SEVERITY_COLOR = {
  error: { bg: '#fef2f2', text: '#991b1b', border: '#fecaca' },
  warn: { bg: '#fffbeb', text: '#92400e', border: '#fde68a' },
  info: { bg: '#eff6ff', text: '#1e3a8a', border: '#bfdbfe' },
};

function MCQLintPanel({ lessonId, refreshKey }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (!lessonId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    questionApi.lintLesson(lessonId)
      .then((res) => {
        if (!cancelled) setData(res.data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.response?.data?.error || 'Failed to load lint report');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [lessonId, refreshKey]);

  if (!lessonId) return null;
  if (data && data.total_questions === 0 && !expanded) return null;

  const headerStyle = {
    padding: '20px',
    borderTop: '1px solid var(--neutral-200)',
    background: 'var(--neutral-50)',
  };

  const scoreColor = (score) => {
    if (score >= 85) return '#16a34a';
    if (score >= 65) return '#ca8a04';
    return '#dc2626';
  };

  return (
    <div style={headerStyle}>
      <div
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <h4 style={{ margin: 0 }}>MCQ Quality (Haladyna lint)</h4>
          {data && data.total_questions > 0 && (
            <span style={{
              background: '#f3f4f6',
              color: scoreColor(data.average_score),
              padding: '2px 10px',
              borderRadius: '10px',
              fontSize: '0.85rem',
              fontWeight: 600,
            }}>
              {data.average_score}/100 avg
            </span>
          )}
          {data && data.aggregate_counts.error > 0 && (
            <span style={{
              background: '#fee2e2',
              color: '#991b1b',
              padding: '2px 8px',
              borderRadius: '10px',
              fontSize: '0.8rem',
            }}>
              {data.aggregate_counts.error} errors
            </span>
          )}
          {data && data.aggregate_counts.warn > 0 && (
            <span style={{
              background: '#fef3c7',
              color: '#92400e',
              padding: '2px 8px',
              borderRadius: '10px',
              fontSize: '0.8rem',
            }}>
              {data.aggregate_counts.warn} warnings
            </span>
          )}
        </div>
        <span style={{ fontSize: '0.8rem', color: 'var(--neutral-600)' }}>
          {expanded ? 'Hide' : 'Show'}
        </span>
      </div>

      {expanded && (
        <div style={{ marginTop: '16px' }}>
          {loading && <p style={{ color: 'var(--neutral-500)' }}>Running checks…</p>}
          {error && <p style={{ color: '#d32f2f' }}>{error}</p>}

          {data && data.total_questions === 0 && (
            <p style={{ color: 'var(--neutral-500)' }}>
              No questions to lint yet — generate questions first.
            </p>
          )}

          {data && data.total_questions > 0 && (
            <>
              <div style={{
                fontSize: '0.85rem',
                color: 'var(--neutral-600)',
                marginBottom: '14px',
              }}>
                {data.total_questions} question{data.total_questions === 1 ? '' : 's'} checked against the
                automatable subset of Haladyna, Downing & Rodriguez (2002) item-writing rules
                {data.embeddings_summary ? ' + Bitew 2023 embedding-based distractor plausibility' : ''}.
              </div>

              {data.embeddings_summary && (
                <div style={{
                  background: 'white',
                  padding: '12px 16px',
                  borderRadius: '8px',
                  border: '1px solid var(--neutral-200)',
                  borderLeft: '4px solid #7c3aed',
                  marginBottom: '16px',
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                  gap: '12px',
                }}>
                  {data.embeddings_summary.mean_plausibility !== undefined && (
                    <div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--neutral-500)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Plausibility (distraktor↔ključ)
                      </div>
                      <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>
                        {data.embeddings_summary.mean_plausibility.toFixed(2)}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--neutral-500)' }}>
                        target 0.40–0.92
                      </div>
                    </div>
                  )}
                  {data.embeddings_summary.mean_diversity !== undefined && (
                    <div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--neutral-500)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Diversity (distraktor↔distraktor)
                      </div>
                      <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>
                        {data.embeddings_summary.mean_diversity.toFixed(2)}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--neutral-500)' }}>
                        higher = more distinct
                      </div>
                    </div>
                  )}
                  <div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--neutral-500)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                      Coverage
                    </div>
                    <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>
                      {data.embeddings_summary.coverage}%
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--neutral-500)' }}>
                      questions with embeddings
                    </div>
                  </div>
                </div>
              )}

              {Object.keys(data.flag_frequency).length > 0 && (
                <div style={{
                  background: 'white',
                  padding: '14px',
                  borderRadius: '8px',
                  border: '1px solid var(--neutral-200)',
                  marginBottom: '16px',
                }}>
                  <div style={{ fontWeight: 600, marginBottom: '8px', color: 'var(--neutral-700)' }}>
                    Most frequent issues
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {Object.entries(data.flag_frequency).slice(0, 8).map(([code, count]) => (
                      <div key={code} style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        fontSize: '0.85rem',
                        padding: '6px 10px',
                        background: 'var(--neutral-50)',
                        borderRadius: '6px',
                      }}>
                        <code style={{ color: 'var(--neutral-700)' }}>{code}</code>
                        <span style={{ color: 'var(--neutral-500)' }}>{count} question{count === 1 ? '' : 's'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {data.reports
                  .filter((r) => r.flags.length > 0)
                  .slice(0, 30)
                  .map((report) => (
                    <ReportRow key={report.question_id} report={report} scoreColor={scoreColor} />
                  ))}
              </div>

              {data.reports.filter((r) => r.flags.length === 0).length > 0 && (
                <div style={{ marginTop: '12px', fontSize: '0.85rem', color: '#16a34a' }}>
                  {data.reports.filter((r) => r.flags.length === 0).length} question(s) passed all checks.
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ReportRow({ report, scoreColor }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{
      background: 'white',
      padding: '10px 14px',
      borderRadius: '8px',
      border: '1px solid var(--neutral-200)',
    }}>
      <div
        style={{ display: 'flex', justifyContent: 'space-between', cursor: 'pointer', alignItems: 'center' }}
        onClick={() => setOpen(!open)}
      >
        <div style={{ fontSize: '0.9rem' }}>
          Question <code>#{report.question_id}</code>
          <span style={{ marginLeft: '10px', color: 'var(--neutral-500)', fontSize: '0.8rem' }}>
            {report.flags.length} flag{report.flags.length === 1 ? '' : 's'}
          </span>
        </div>
        <div style={{
          fontWeight: 600,
          color: scoreColor(report.score),
        }}>
          {report.score}/100
        </div>
      </div>
      {open && (
        <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {report.flags.map((f, i) => {
            const c = SEVERITY_COLOR[f.severity] || SEVERITY_COLOR.info;
            return (
              <div
                key={`${f.code}-${i}`}
                style={{
                  padding: '6px 10px',
                  background: c.bg,
                  color: c.text,
                  border: `1px solid ${c.border}`,
                  borderRadius: '6px',
                  fontSize: '0.83rem',
                }}
              >
                <code style={{ fontWeight: 700 }}>{f.code}</code>
                <span style={{ marginLeft: '8px' }}>{f.message}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default MCQLintPanel;
