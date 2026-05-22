import React, { useState } from 'react';
import { questionApi } from '../api';

// Cove + Solvability share a panel because they are both slow (multiple LLM
// calls per question) and both are scientifically-grounded a-priori validity
// checks. Each runs on demand via its own button.

const VERDICT_COLOR = {
  SUPPORTED: '#16a34a',
  UNDERDETERMINED: '#ca8a04',
  CONTRADICTED: '#dc2626',
};

const DIFFICULTY_COLOR = {
  trivially_easy: '#dc2626',
  appropriate: '#16a34a',
  hard: '#ca8a04',
  too_hard_or_misframed: '#dc2626',
};

function AdvancedQualityPanel({ lessonId }) {
  const [expanded, setExpanded] = useState(false);
  const [coveData, setCoveData] = useState(null);
  const [solvData, setSolvData] = useState(null);
  const [coveLoading, setCoveLoading] = useState(false);
  const [solvLoading, setSolvLoading] = useState(false);
  const [coveErr, setCoveErr] = useState(null);
  const [solvErr, setSolvErr] = useState(null);

  if (!lessonId) return null;

  const runCove = () => {
    setCoveLoading(true);
    setCoveErr(null);
    questionApi.coveLesson(lessonId)
      .then((res) => setCoveData(res.data))
      .catch((err) => setCoveErr(err.response?.data?.error || 'CoVe failed'))
      .finally(() => setCoveLoading(false));
  };

  const runSolv = () => {
    setSolvLoading(true);
    setSolvErr(null);
    questionApi.solvabilityLesson(lessonId, 5)
      .then((res) => setSolvData(res.data))
      .catch((err) => setSolvErr(err.response?.data?.error || 'Solvability failed'))
      .finally(() => setSolvLoading(false));
  };

  const headerStyle = {
    padding: '20px',
    borderTop: '1px solid var(--neutral-200)',
    background: 'var(--neutral-50)',
  };

  return (
    <div style={headerStyle}>
      <div
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <h4 style={{ margin: 0 }}>Advanced validity (CoVe + Solvability)</h4>
          {coveData && (
            <span style={{
              background: '#ecfeff',
              color: '#155e75',
              padding: '2px 10px',
              borderRadius: '10px',
              fontSize: '0.8rem',
              fontWeight: 600,
            }}>
              CoVe: {coveData.support_rate}% supported
            </span>
          )}
          {solvData?.mean_p_value !== undefined && solvData.mean_p_value !== null && (
            <span style={{
              background: '#fef3c7',
              color: '#78350f',
              padding: '2px 10px',
              borderRadius: '10px',
              fontSize: '0.8rem',
              fontWeight: 600,
            }}>
              Mean LLM p = {solvData.mean_p_value.toFixed(2)}
            </span>
          )}
        </div>
        <span style={{ fontSize: '0.8rem', color: 'var(--neutral-600)' }}>
          {expanded ? 'Hide' : 'Show'}
        </span>
      </div>

      {expanded && (
        <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* CoVe section */}
          <section style={{
            background: 'white',
            padding: '16px',
            borderRadius: '8px',
            border: '1px solid var(--neutral-200)',
            borderLeft: '4px solid #06b6d4',
          }}>
            <h5 style={{ marginTop: 0 }}>Chain-of-Verification (CoVe)</h5>
            <div style={{ fontSize: '0.85rem', color: 'var(--neutral-600)', marginBottom: '12px' }}>
              Dhuliawala et al. 2023, ACL 2024. A second LLM plans verification questions
              about the correct answer, answers them from source material only, and decides
              whether the correct answer is uniquely defensible.
            </div>
            {!coveData && (
              <button
                onClick={runCove}
                disabled={coveLoading}
                style={btnStyle(coveLoading)}
              >
                {coveLoading ? 'Running CoVe…' : 'Run Chain-of-Verification'}
              </button>
            )}
            {coveErr && <p style={{ color: '#d32f2f' }}>{coveErr}</p>}
            {coveData && (
              <>
                <div style={statsGridStyle}>
                  <Stat label="Supported" value={coveData.supported} color="#16a34a" />
                  <Stat label="Underdetermined" value={coveData.underdetermined} color="#ca8a04" />
                  <Stat label="Contradicted" value={coveData.contradicted} color="#dc2626" />
                  <Stat label="Need review" value={coveData.needs_review} />
                </div>
                <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {coveData.reports
                    .filter((r) => r.needs_review)
                    .slice(0, 20)
                    .map((r) => (
                      <div
                        key={r.question_id}
                        style={{
                          padding: '6px 12px',
                          background: 'var(--neutral-50)',
                          borderRadius: '6px',
                          fontSize: '0.85rem',
                          display: 'flex',
                          justifyContent: 'space-between',
                        }}
                      >
                        <span>Q#{r.question_id}</span>
                        <span style={{ color: VERDICT_COLOR[r.verdict] || 'var(--neutral-500)', fontWeight: 600 }}>
                          {r.verdict || 'unparseable'}
                        </span>
                      </div>
                    ))}
                </div>
              </>
            )}
          </section>

          {/* Solvability section */}
          <section style={{
            background: 'white',
            padding: '16px',
            borderRadius: '8px',
            border: '1px solid var(--neutral-200)',
            borderLeft: '4px solid #f59e0b',
          }}>
            <h5 style={{ marginTop: 0 }}>Solvability test (a-priori item difficulty)</h5>
            <div style={{ fontSize: '0.85rem', color: 'var(--neutral-600)', marginBottom: '12px' }}>
              LLM-blind solver: hide the key, ask an LLM to pick the best option N=5 times
              (shuffled per trial), compute p-value. p ≈ 1 → trivially easy; 0.6–0.9 → appropriate;
              p &lt; 0.5 → ambiguous or misframed.
            </div>
            {!solvData && (
              <button
                onClick={runSolv}
                disabled={solvLoading}
                style={btnStyle(solvLoading)}
              >
                {solvLoading ? 'Running solver…' : 'Run solvability test'}
              </button>
            )}
            {solvErr && <p style={{ color: '#d32f2f' }}>{solvErr}</p>}
            {solvData && (
              <>
                <div style={statsGridStyle}>
                  <Stat label="Trivially easy" value={solvData.difficulty_distribution.trivially_easy} color={DIFFICULTY_COLOR.trivially_easy} />
                  <Stat label="Appropriate" value={solvData.difficulty_distribution.appropriate} color={DIFFICULTY_COLOR.appropriate} />
                  <Stat label="Hard" value={solvData.difficulty_distribution.hard} color={DIFFICULTY_COLOR.hard} />
                  <Stat label="Too hard / misframed" value={solvData.difficulty_distribution.too_hard_or_misframed} color={DIFFICULTY_COLOR.too_hard_or_misframed} />
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

const btnStyle = (loading) => ({
  padding: '8px 16px',
  background: loading ? 'var(--neutral-200)' : 'var(--primary-600)',
  color: 'white',
  border: 'none',
  borderRadius: '6px',
  cursor: loading ? 'wait' : 'pointer',
  fontWeight: 600,
});

const statsGridStyle = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
  gap: '12px',
};

function Stat({ label, value, color }) {
  return (
    <div>
      <div style={{ fontSize: '0.7rem', color: 'var(--neutral-500)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
      <div style={{ fontSize: '1.5rem', fontWeight: 700, color: color || 'var(--neutral-800)' }}>{value}</div>
    </div>
  );
}

export default AdvancedQualityPanel;
