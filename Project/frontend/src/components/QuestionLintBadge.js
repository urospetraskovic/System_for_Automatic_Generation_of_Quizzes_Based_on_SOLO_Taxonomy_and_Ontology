import React from 'react';

// Mirrors MCQLintPanel's palette so the bank and the Haladyna panel agree.
const SEVERITY_COLOR = {
  error: { bg: '#fef2f2', text: '#991b1b', border: '#fecaca' },
  warn: { bg: '#fffbeb', text: '#92400e', border: '#fde68a' },
  info: { bg: '#eff6ff', text: '#1e3a8a', border: '#bfdbfe' },
};

function scoreColor(score) {
  if (score >= 85) return '#16a34a';
  if (score >= 65) return '#ca8a04';
  return '#dc2626';
}

/**
 * Compact at-a-glance chip for a question's Haladyna lint result.
 * Renders nothing until the report is loaded (caller passes undefined).
 */
export function QuestionLintBadge({ report }) {
  if (!report) return null;
  const issues = report.flags ? report.flags.length : 0;
  const color = scoreColor(report.score);
  return (
    <span
      title={issues === 0 ? 'Prošlo sve Haladyna provere' : `${issues} problem(a) kvaliteta`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '2px 8px',
        borderRadius: 10,
        fontSize: '0.75rem',
        fontWeight: 600,
        color,
        background: `${color}1a`,
        border: `1px solid ${color}40`,
        whiteSpace: 'nowrap',
      }}
    >
      {issues === 0 ? '✓' : '⚠'} {report.score}
      {issues > 0 && (
        <span style={{ fontWeight: 500 }}>
          · {issues} {issues === 1 ? 'problem' : 'problema'}
        </span>
      )}
    </span>
  );
}

/**
 * Expanded list of lint flags for a question — shown when a card is opened.
 */
export function QuestionLintFlags({ report }) {
  if (!report || !report.flags || report.flags.length === 0) return null;
  return (
    <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
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
              borderRadius: 6,
              fontSize: '0.83rem',
            }}
          >
            <code style={{ fontWeight: 700 }}>{f.code}</code>
            <span style={{ marginLeft: 8 }}>{f.message}</span>
          </div>
        );
      })}
    </div>
  );
}
