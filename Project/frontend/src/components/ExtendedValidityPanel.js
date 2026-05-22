import React, { useState } from 'react';
import { questionApi } from '../api';

// Seven on-demand validity checks (techniques A through H from the
// QUESTION_AND_GENERATION_BEST_PRACTICES document). Each subsection has its
// own Run button; results are kept independently so the user can run only
// the ones they need.

const SECTIONS = [
  {
    key: 'ioc',
    title: 'A. Item-Objective Congruence',
    citation: 'Rovinelli & Hambleton (1977)',
    description: 'A second LLM rates each question -1/0/+1 against the LO it is anchored to. The mean is the IOC index — the classical content-validity instrument.',
    run: (lessonId) => questionApi.iocLesson(lessonId),
    summary: (d) => d && (
      <Stats items={[
        ['IOC index', d.ioc_index ?? '—', d.ioc_label],
        ['+1 ratings', d.distribution['+1']],
        ['0 ratings', d.distribution['0']],
        ['-1 ratings', d.distribution['-1']],
      ]} />
    ),
  },
  {
    key: 'stem',
    title: 'B. Stem-Only Solvability (Haladyna H4)',
    citation: 'Haladyna 2002 rule 4',
    description: 'Hide the options; ask the LLM to answer from the stem alone; embedding-compare to the key. Tests whether the stem carries the central idea.',
    run: (lessonId) => questionApi.stemOnlySolvabilityLesson(lessonId),
    summary: (d) => d && (
      <Stats items={[
        ['H4 pass rate', d.h4_pass_rate != null ? `${d.h4_pass_rate}%` : '—'],
        ['Mean similarity', d.mean_similarity ?? '—'],
        ['Passes', d.verdict_distribution.passes],
        ['Fails', d.verdict_distribution.fails],
      ]} />
    ),
  },
  {
    key: 'readability',
    title: 'C. Readability (Flesch-Kincaid)',
    citation: 'Flesch 1948 + Kincaid 1975',
    description: 'Computes the Flesch reading-ease and Flesch-Kincaid grade level of each stem, then checks whether the grade is appropriate for the SOLO level being tested.',
    run: (lessonId) => questionApi.readabilityLesson(lessonId),
    summary: (d) => d && (
      <Stats items={[
        ['Mean FK grade', d.mean_flesch_kincaid_grade ?? '—'],
        ['Mean reading ease', d.mean_flesch_reading_ease ?? '—'],
        ['In range', d.fit_distribution?.in_range ?? 0],
        ['Too hard', d.fit_distribution?.too_hard ?? 0],
      ]} />
    ),
  },
  {
    key: 'ambiguity',
    title: 'D. Linguistic Ambiguity',
    citation: 'Downing 2005',
    description: 'A second LLM checks whether the stem admits multiple distinct interpretations. Catches ambiguity that lint and embeddings cannot detect.',
    run: (lessonId) => questionApi.ambiguityLesson(lessonId),
    summary: (d) => d && (
      <Stats items={[
        ['Ambiguity rate', d.ambiguity_rate != null ? `${d.ambiguity_rate}%` : '—'],
        ['Lexical', d.type_distribution?.lexical ?? 0],
        ['Referential', d.type_distribution?.referential ?? 0],
        ['Syntactic', d.type_distribution?.syntactic ?? 0],
      ]} />
    ),
  },
  {
    key: 'misconception',
    title: 'E. Source-Grounded Misconception Mining',
    citation: 'Sadler 1998',
    description: 'Scans the source PDF for cue phrases ("česta greška", "students often think") and extracts misconception/correction pairs. Use these as seed material for grounded distractors.',
    run: (lessonId) => questionApi.misconceptionMining(lessonId),
    summary: (d) => d && (
      <Stats items={[
        ['Cue windows found', d.cue_windows_found ?? 0],
        ['Misconceptions extracted', d.misconception_count ?? 0],
      ]} />
    ),
    extra: (d) => d?.misconceptions?.length > 0 && (
      <div style={{ marginTop: 10 }}>
        <div style={{ fontSize: '0.85rem', color: 'var(--neutral-600)', marginBottom: 6 }}>
          Extracted pairs:
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {d.misconceptions.slice(0, 5).map((m, i) => (
            <div key={i} style={{
              padding: 8, background: 'var(--neutral-50)', borderRadius: 6, fontSize: '0.85rem',
            }}>
              <div><strong>Misconception:</strong> {m.misconception}</div>
              <div><strong>Correction:</strong> {m.correction}</div>
            </div>
          ))}
        </div>
      </div>
    ),
  },
  {
    key: 'grammar',
    title: 'F+G. Grammatical Homogeneity (Haladyna O7)',
    citation: 'Tarrant 2009 + Haladyna 2002',
    description: 'LLM classifies each option into a structural type (noun_phrase, verb_phrase, etc.). Flags questions where one option stands out structurally — a common give-away clue.',
    run: (lessonId) => questionApi.grammarHomogeneityLesson(lessonId),
    summary: (d) => d && (
      <Stats items={[
        ['Homogeneous %', d.homogeneous_rate != null ? `${d.homogeneous_rate}%` : '—'],
        ['Homogeneous', d.verdict_distribution?.homogeneous ?? 0],
        ['Single outlier', d.verdict_distribution?.single_outlier ?? 0],
        ['Mixed', d.verdict_distribution?.mixed ?? 0],
        ['Correct = outlier', d.correct_outlier_count ?? 0],
      ]} />
    ),
  },
  {
    key: 'face',
    title: 'H. Distractor Face Validity',
    citation: 'Considine 2005 + Tarrant 2008',
    description: 'A second LLM scores each distractor 1-5 on four criteria (plausibility, representativeness, no_giveaways, clarity). The mean across distractors is the question\'s face-validity score.',
    run: (lessonId) => questionApi.faceValidityLesson(lessonId),
    summary: (d) => d && (
      <Stats items={[
        ['Mean face-validity score', d.mean_face_validity_score ?? '—'],
        ['Plausibility', d.criterion_means?.plausibility ?? '—'],
        ['Representativeness', d.criterion_means?.representativeness ?? '—'],
        ['No give-aways', d.criterion_means?.no_giveaways ?? '—'],
        ['Clarity', d.criterion_means?.clarity ?? '—'],
      ]} />
    ),
  },
];

function Stats({ items }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
      gap: 12,
      marginTop: 10,
    }}>
      {items.map(([label, value, sub]) => (
        <div key={label}>
          <div style={{ fontSize: '0.7rem', color: 'var(--neutral-500)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
          <div style={{ fontSize: '1.3rem', fontWeight: 700 }}>{value}</div>
          {sub && <div style={{ fontSize: '0.75rem', color: 'var(--neutral-500)' }}>{sub}</div>}
        </div>
      ))}
    </div>
  );
}

function ExtendedValidityPanel({ lessonId }) {
  const [expanded, setExpanded] = useState(false);
  const [state, setState] = useState({}); // {sectionKey: {data, loading, error}}

  if (!lessonId) return null;

  const updateSection = (key, patch) =>
    setState((s) => ({ ...s, [key]: { ...s[key], ...patch } }));

  const runSection = (section) => {
    updateSection(section.key, { loading: true, error: null });
    section.run(lessonId)
      .then((res) => updateSection(section.key, { data: res.data, loading: false }))
      .catch((err) => updateSection(section.key, {
        loading: false,
        error: err.response?.data?.error || `${section.title} failed`,
      }));
  };

  return (
    <div style={{
      padding: 20,
      borderTop: '1px solid var(--neutral-200)',
      background: 'var(--neutral-50)',
    }}>
      <div
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setExpanded(!expanded)}
      >
        <h4 style={{ margin: 0 }}>Extended Validity (A–H)</h4>
        <span style={{ fontSize: '0.8rem', color: 'var(--neutral-600)' }}>
          {expanded ? 'Hide' : 'Show'}
        </span>
      </div>

      {expanded && (
        <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <p style={{ fontSize: '0.85rem', color: 'var(--neutral-600)', marginTop: 0 }}>
            Seven additional scientifically-grounded validity checks. Each runs on demand —
            results are cached server-side after the first run.
          </p>
          {SECTIONS.map((section) => {
            const s = state[section.key] || {};
            return (
              <section key={section.key} style={{
                background: 'white',
                padding: 14,
                borderRadius: 8,
                border: '1px solid var(--neutral-200)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
                  <div>
                    <h5 style={{ margin: 0 }}>{section.title}</h5>
                    <div style={{ fontSize: '0.75rem', color: 'var(--neutral-500)', marginTop: 2 }}>
                      {section.citation}
                    </div>
                  </div>
                  <button
                    onClick={() => runSection(section)}
                    disabled={s.loading}
                    style={{
                      padding: '6px 12px',
                      background: s.loading ? 'var(--neutral-200)' : 'var(--primary-600)',
                      color: 'white',
                      border: 'none',
                      borderRadius: 6,
                      cursor: s.loading ? 'wait' : 'pointer',
                      fontSize: '0.85rem',
                    }}
                  >
                    {s.loading ? 'Running…' : (s.data ? 'Re-run' : 'Run')}
                  </button>
                </div>
                <p style={{ fontSize: '0.85rem', color: 'var(--neutral-600)', margin: '8px 0' }}>
                  {section.description}
                </p>
                {s.error && <div style={{ color: '#d32f2f', fontSize: '0.85rem' }}>{s.error}</div>}
                {section.summary && section.summary(s.data)}
                {section.extra && section.extra(s.data)}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default ExtendedValidityPanel;
