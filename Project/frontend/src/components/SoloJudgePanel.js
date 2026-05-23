import React, { useState } from 'react';
import { questionApi } from '../api';

const SOLO_LEVELS = ['unistructural', 'multistructural', 'relational', 'extended_abstract'];
const SOLO_SHORT = {
  unistructural: 'U',
  multistructural: 'M',
  relational: 'R',
  extended_abstract: 'EA',
};

// Cohen's kappa landmark interpretations (Landis & Koch, 1977).
function kappaQualitative(k) {
  if (k === null || k === undefined) return { label: '—', color: 'var(--neutral-500)' };
  if (k < 0) return { label: 'worse than chance', color: '#dc2626' };
  if (k < 0.21) return { label: 'slight', color: '#dc2626' };
  if (k < 0.41) return { label: 'fair', color: '#ea580c' };
  if (k < 0.61) return { label: 'moderate', color: '#ca8a04' };
  if (k < 0.81) return { label: 'substantial', color: '#16a34a' };
  return { label: 'almost perfect', color: '#15803d' };
}

function SoloJudgePanel({ lessonId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);

  const runJudge = () => {
    if (!lessonId) return;
    setLoading(true);
    setError(null);
    questionApi.soloJudgeLesson(lessonId)
      .then((res) => setData(res.data))
      .catch((err) => setError(err.response?.data?.error || 'Judge run failed'))
      .finally(() => setLoading(false));
  };

  if (!lessonId) return null;

  const headerStyle = {
    padding: '20px',
    borderTop: '1px solid var(--neutral-200)',
    background: 'var(--neutral-50)',
  };

  const k = data?.cohen_kappa;
  const kq = kappaQualitative(k);

  return (
    <div style={headerStyle}>
      <div
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <h4 style={{ margin: 0 }}>SOLO level agreement (LLM judge)</h4>
          {data && (
            <>
              <span style={{
                background: '#f3f4f6',
                color: kq.color,
                padding: '2px 10px',
                borderRadius: '10px',
                fontSize: '0.85rem',
                fontWeight: 600,
              }}>
                κ = {k === null ? '—' : k.toFixed(2)} ({kq.label})
              </span>
              {data.accuracy !== null && (
                <span style={{
                  background: '#f3f4f6',
                  color: 'var(--neutral-700)',
                  padding: '2px 10px',
                  borderRadius: '10px',
                  fontSize: '0.85rem',
                }}>
                  {Math.round(data.accuracy * 100)}% match
                </span>
              )}
            </>
          )}
        </div>
        <span style={{ fontSize: '0.8rem', color: 'var(--neutral-600)' }}>
          {expanded ? 'Hide' : 'Show'}
        </span>
      </div>

      {expanded && (
        <div style={{ marginTop: '16px' }}>
          <div style={{ fontSize: '0.85rem', color: 'var(--neutral-600)', marginBottom: '12px' }}>
            A second LLM independently classifies each question's SOLO level. Cohen's κ
            measures agreement with the level the generator was told to produce.
            First run takes a while (one LLM call per question); subsequent runs are
            cached and instant.
          </div>

          {!data && (
            <button
              onClick={runJudge}
              disabled={loading}
              style={{
                padding: '8px 16px',
                background: loading ? '#c4c4d6' : '#1b3a4b',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                cursor: loading ? 'wait' : 'pointer',
                fontWeight: 600,
                fontSize: '0.9rem',
              }}
            >
              {loading ? 'Running judge…' : 'Run SOLO judge'}
            </button>
          )}
          {error && <p style={{ color: '#d32f2f', marginTop: '8px' }}>{error}</p>}

          {data && (
            <>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: '12px',
                background: 'white',
                padding: '16px',
                borderRadius: '8px',
                border: '1px solid var(--neutral-200)',
                marginBottom: '16px',
              }}>
                <Stat label="Questions judged" value={`${data.judged_questions} / ${data.total_questions}`} />
                <Stat label="Cohen's κ" value={k === null ? '—' : k.toFixed(2)} sub={kq.label} color={kq.color} />
                <Stat label="Direct agreement" value={data.accuracy === null ? '—' : `${Math.round(data.accuracy * 100)}%`} />
                <Stat label="Judge model" value={data.judge_model} small />
              </div>

              <ConfusionMatrix matrix={data.confusion_matrix} />

              {data.parse_failures > 0 && (
                <div style={{ marginTop: '10px', fontSize: '0.85rem', color: '#92400e' }}>
                  {data.parse_failures} question(s) could not be parsed by the judge — they are excluded from κ.
                </div>
              )}

              <div style={{ marginTop: '16px' }}>
                <button
                  onClick={() => setData(null)}
                  style={{
                    fontSize: '0.85rem',
                    padding: '4px 10px',
                    background: 'transparent',
                    border: '1px solid var(--neutral-300)',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    color: 'var(--neutral-700)',
                  }}
                >
                  Reset
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ConfusionMatrix({ matrix }) {
  return (
    <div style={{
      background: 'white',
      padding: '16px',
      borderRadius: '8px',
      border: '1px solid var(--neutral-200)',
    }}>
      <div style={{ fontWeight: 600, marginBottom: '8px', color: 'var(--neutral-700)' }}>
        Confusion matrix
        <span style={{ fontSize: '0.8rem', fontWeight: 400, color: 'var(--neutral-500)', marginLeft: '8px' }}>
          rows = intended (generator), columns = classified (judge)
        </span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: '0.85rem' }}>
          <thead>
            <tr>
              <th style={{ ...cellStyle, background: 'var(--neutral-100)' }} />
              {SOLO_LEVELS.map((c) => (
                <th key={c} style={{ ...cellStyle, background: 'var(--neutral-100)' }}>{SOLO_SHORT[c]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {SOLO_LEVELS.map((r) => (
              <tr key={r}>
                <th style={{ ...cellStyle, background: 'var(--neutral-100)', textAlign: 'left' }}>{SOLO_SHORT[r]}</th>
                {SOLO_LEVELS.map((c) => {
                  const n = matrix[r]?.[c] ?? 0;
                  const onDiagonal = r === c;
                  return (
                    <td
                      key={c}
                      style={{
                        ...cellStyle,
                        background: onDiagonal && n > 0 ? '#dcfce7' : (n > 0 ? '#fef2f2' : 'white'),
                        fontWeight: onDiagonal ? 700 : 400,
                      }}
                    >
                      {n}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const cellStyle = {
  padding: '6px 12px',
  border: '1px solid var(--neutral-200)',
  textAlign: 'center',
  minWidth: '40px',
};

function Stat({ label, value, sub, color, small }) {
  return (
    <div>
      <div style={{ fontSize: '0.75rem', color: 'var(--neutral-500)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{
        fontSize: small ? '0.95rem' : '1.6rem',
        fontWeight: 700,
        color: color || 'var(--neutral-800)',
      }}>{value}</div>
      {sub && <div style={{ fontSize: '0.8rem', color: 'var(--neutral-500)' }}>{sub}</div>}
    </div>
  );
}

export default SoloJudgePanel;
