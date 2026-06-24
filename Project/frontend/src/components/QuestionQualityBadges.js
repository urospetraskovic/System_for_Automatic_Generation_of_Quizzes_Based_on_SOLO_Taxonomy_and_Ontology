import React from 'react';

const TONE = {
  good: '#16a34a',
  warn: '#ca8a04',
  bad: '#dc2626',
  info: '#475569',
};

// One entry per cached metric. `extract(entry)` returns { short, tone, detail }
// for a single question's cached report, or null to render nothing (e.g. the
// metric was unavailable for this question). Order here = display order.
const METRICS = [
  {
    key: 'solo_judge',
    label: 'SOLO',
    extract(e) {
      if (!e || (e.intended_level == null && e.classified_level == null)) return null;
      const agrees = e.agrees;
      return {
        short: agrees ? '✓' : (e.classified_level || '?'),
        tone: agrees ? 'good' : 'bad',
        detail: `Nameravano: ${e.intended_level || '?'} · Klasifikovano: ${e.classified_level || '?'}`
          + (e.reasoning ? ` — ${e.reasoning}` : ''),
      };
    },
  },
  {
    key: 'cove',
    label: 'CoVe',
    extract(e) {
      if (!e) return null;
      const v = e.verdict;
      const tone = v === 'SUPPORTED' ? 'good' : v === 'CONTRADICTED' ? 'bad' : 'warn';
      const short = v === 'SUPPORTED' ? '✓' : v === 'CONTRADICTED' ? '✗' : '?';
      return { short, tone, detail: `${v || 'needs review'}${e.reasoning ? ` — ${e.reasoning}` : ''}` };
    },
  },
  {
    key: 'ioc',
    label: 'IOC',
    extract(e) {
      if (!e || !e.available || e.rating == null) return null;
      const r = e.rating;
      const tone = r > 0 ? 'good' : r < 0 ? 'bad' : 'warn';
      return { short: r > 0 ? '+1' : String(r), tone, detail: e.reasoning || '' };
    },
  },
  {
    key: 'ambiguity',
    label: 'Dvosmislenost',
    extract(e) {
      if (!e || !e.available) return null;
      const amb = e.ambiguous;
      return {
        short: amb ? '✗' : '✓',
        tone: amb ? 'bad' : 'good',
        detail: amb
          ? `Dvosmisleno (${e.ambiguity_type || 'tip nepoznat'})${e.reasoning ? ` — ${e.reasoning}` : ''}`
          : 'Bez dvosmislenosti',
      };
    },
  },
  {
    key: 'grammar_homogeneity',
    label: 'Gramatika',
    extract(e) {
      if (!e || !e.available) return null;
      const v = e.verdict;
      let tone = v === 'homogeneous' ? 'good' : v === 'single_outlier' ? 'warn' : 'bad';
      if (e.correct_is_outlier) tone = 'bad';
      const short = v === 'homogeneous' ? '✓' : v === 'single_outlier' ? '1 outlier' : 'miks';
      return {
        short,
        tone,
        detail: e.correct_is_outlier
          ? 'Tačan odgovor gramatički odudara od distraktora (give-away).'
          : `Tipovi opcija: ${v}`,
      };
    },
  },
  {
    key: 'stem_only',
    label: 'H4',
    extract(e) {
      if (!e || !e.available) return null;
      const pass = e.h4_passes;
      return {
        short: pass ? '✓' : '✗',
        tone: pass ? 'good' : 'warn',
        detail: pass
          ? 'Stem je rešiv bez opcija (H4).'
          : `Stem nije samodovoljan${e.reasoning ? ` — ${e.reasoning}` : ''}`,
      };
    },
  },
  {
    key: 'readability',
    label: 'FK',
    extract(e) {
      const grade = e && e.metrics && e.metrics.flesch_kincaid_grade;
      if (grade == null) return null;
      const fit = e.fit;
      const tone = fit === 'in_range' ? 'good' : fit === 'unknown' ? 'info' : 'warn';
      return { short: String(grade), tone, detail: `Flesch-Kincaid nivo ${grade} · ${fit || 'n/a'}` };
    },
  },
  {
    key: 'solvability',
    label: 'p',
    extract(e) {
      if (!e || !e.available || e.p_value == null) return null;
      const lbl = e.difficulty_label;
      const tone = (lbl === 'trivially_easy' || lbl === 'impossible') ? 'warn' : 'info';
      return { short: String(e.p_value), tone, detail: `Solver p=${e.p_value} · ${lbl || 'n/a'}` };
    },
  },
  {
    key: 'face_validity',
    label: 'Face',
    extract(e) {
      if (!e || !e.available || e.face_validity_score == null) return null;
      const s = e.face_validity_score;
      const tone = s >= 4 ? 'good' : s >= 3 ? 'info' : 'warn';
      return { short: String(s), tone, detail: `Face-validity distraktora: prosek ${s}` };
    },
  },
];

function resolve(quality) {
  if (!quality) return [];
  const out = [];
  for (const m of METRICS) {
    const r = m.extract(quality[m.key]);
    if (r) out.push({ label: m.label, ...r });
  }
  return out;
}

/** Compact row of cached-metric pills for a question. Renders nothing if no
 * metric has been computed for this question yet. */
export function QuestionQualityBadges({ quality }) {
  const items = resolve(quality);
  if (items.length === 0) return null;
  return (
    <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 5, alignItems: 'center' }}>
      {items.map((it) => {
        const color = TONE[it.tone] || TONE.info;
        return (
          <span
            key={it.label}
            title={it.detail}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '1px 7px',
              borderRadius: 9,
              fontSize: '0.72rem',
              fontWeight: 600,
              color,
              background: `${color}14`,
              border: `1px solid ${color}3a`,
              whiteSpace: 'nowrap',
            }}
          >
            <span style={{ opacity: 0.75, fontWeight: 500 }}>{it.label}</span>
            {it.short}
          </span>
        );
      })}
    </span>
  );
}

/** Expanded per-metric detail list, shown when a card is opened. */
export function QuestionQualityDetails({ quality }) {
  const items = resolve(quality);
  if (items.length === 0) return null;
  return (
    <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
      {items.map((it) => {
        const color = TONE[it.tone] || TONE.info;
        return (
          <div key={it.label} style={{ fontSize: '0.82rem', color: 'var(--neutral-700)' }}>
            <span style={{ fontWeight: 700, color }}>{it.label}:</span>{' '}
            {it.detail}
          </div>
        );
      })}
    </div>
  );
}
