import React, { useState, useEffect, useRef } from 'react';
import { lessonApi, questionApi, jobsApi } from '../api';

// One hub that fires every quality check in sequence and aggregates the
// headline numbers in one dashboard. The five existing detail panels
// (Coverage, Lint, SOLO judge, CoVe + Solvability, Extended A–H) remain
// below for drill-down — this panel is the "executive summary".

const CHECKS = [
  { key: 'coverage',  label: 'Concept Coverage',          fast: true,  fn: (id) => lessonApi.getCoverage(id) },
  { key: 'lint',      label: 'Haladyna Lint',             fast: true,  fn: (id) => questionApi.lintLesson(id) },
  { key: 'readability', label: 'Readability',             fast: true,  fn: (id) => questionApi.readabilityLesson(id) },
  { key: 'misc',      label: 'Misconception Mining',      fast: true,  fn: (id) => questionApi.misconceptionMining(id) },
  { key: 'judge',     label: 'SOLO Judge (Cohen κ)',      fast: false, fn: (id) => questionApi.soloJudgeLesson(id) },
  { key: 'ioc',       label: 'Item-Objective Congruence', fast: false, fn: (id) => questionApi.iocLesson(id) },
  { key: 'ambiguity', label: 'Linguistic Ambiguity',      fast: false, fn: (id) => questionApi.ambiguityLesson(id) },
  { key: 'grammar',   label: 'Grammatical Homogeneity',   fast: false, fn: (id) => questionApi.grammarHomogeneityLesson(id) },
  { key: 'face',      label: 'Distractor Face Validity',  fast: false, fn: (id) => questionApi.faceValidityLesson(id) },
  // The three slowest checks are at the end so a fast-mode run finishes
  // without ever calling them.
  { key: 'stem',      label: 'Stem-Only Solvability (H4)', fast: false, slow: true,  fn: (id) => questionApi.stemOnlySolvabilityLesson(id) },
  { key: 'cove',      label: 'Chain-of-Verification',     fast: false, slow: true,  fn: (id) => questionApi.coveLesson(id) },
  { key: 'solv',      label: 'Solvability (N=5 per Q)',   fast: false, slow: true,  fn: (id) => questionApi.solvabilityLesson(id, 5) },
];

const BTN_BIG = (loading, kind = 'primary') => {
  const palette = {
    primary: { bg: '#0d7a4a', text: '#ffffff' },
    danger:  { bg: '#dc2626', text: '#ffffff' },
    ghost:   { bg: 'transparent', text: '#0d7a4a', border: '2px solid #0d7a4a' },
  }[kind];
  return {
    padding: '12px 20px',
    background: loading ? '#c4c4d6' : palette.bg,
    color: loading ? '#ffffff' : palette.text,
    border: palette.border || 'none',
    borderRadius: 8,
    cursor: loading ? 'wait' : 'pointer',
    fontSize: '0.92rem',
    fontWeight: 700,
    letterSpacing: '0.02em',
    transition: 'background 120ms ease',
  };
};

const STAT_BOX = {
  background: 'white',
  padding: '14px 16px',
  borderRadius: 8,
  border: '1px solid var(--neutral-200)',
};

function QualityOverviewPanel({ lessonId, onResultsChange, initialResults }) {
  const [expanded, setExpanded] = useState(true);
  const [results, setResults] = useState(initialResults || {});  // {key: data}

  // Sync DOWN: when the parent loads new cache data (e.g. after lesson
  // change or after the server-side validation_cache responds), reflect it
  // here so the sub-panel hydration works correctly.
  //
  // Idempotent: bail out without changing state if every incoming key
  // already maps to the same reference. Without this, the sync UP roundtrip
  // (results → onResultsChange → parent setQualityResults → new
  // initialResults reference → here again) created a render loop that
  // inflated the "completed" counter past CHECKS.length (the "15 / 12"
  // bug the user saw).
  useEffect(() => {
    if (!initialResults || Object.keys(initialResults).length === 0) return;
    setResults((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const [k, v] of Object.entries(initialResults)) {
        if (next[k] !== v) {
          next[k] = v;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [initialResults]);

  // Sync UP: whenever local results change (e.g. after a Run All), surface
  // them to the parent so the detail-panels below the hub can show the
  // same data without re-running.
  useEffect(() => {
    if (onResultsChange) onResultsChange(results);
  }, [results, onResultsChange]);
  const [progress, setProgress] = useState(null);  // {idx, total, label, mode, list} | null
  const [errors, setErrors] = useState({});
  const [activeJobs, setActiveJobs] = useState(0);
  const abortFlagRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await jobsApi.list();
        if (cancelled) return;
        const running = (res.data?.jobs || []).filter(
          (j) => j.status === 'running' || j.status === 'pending'
        );
        setActiveJobs(running.length);
      } catch {
        // silent — not critical
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (!lessonId) return null;

  const runChecks = async (checksList, mode) => {
    abortFlagRef.current = false;
    // Don't preemptively clear results: keep showing the prior tiles while
    // the run is in progress, and let each completed check overwrite its
    // own key when its result lands. This stops the visible dashboard from
    // flashing empty during a Quick re-run and preserves any metrics not
    // in the current checksList (e.g. running Quick after a Full).
    setErrors({});
    setProgress({
      idx: 0,
      total: checksList.length,
      label: checksList[0]?.label || 'Starting…',
      mode,
      list: checksList,
    });
    for (let i = 0; i < checksList.length; i++) {
      if (abortFlagRef.current) break;
      const check = checksList[i];
      setProgress({
        idx: i,
        total: checksList.length,
        label: check.label,
        mode,
        list: checksList,
      });
      try {
        const res = await check.fn(lessonId);
        if (abortFlagRef.current) break;
        setResults((prev) => ({ ...prev, [check.key]: res.data }));
      } catch (err) {
        if (abortFlagRef.current) break;
        setErrors((prev) => ({
          ...prev,
          [check.key]: err.response?.data?.error || `${check.label} failed`,
        }));
      }
    }
    setProgress(null);
  };

  const runAll = () => runChecks(CHECKS, 'full');
  const runQuick = () => runChecks(CHECKS.filter((c) => c.fast), 'quick');
  const abort = () => {
    abortFlagRef.current = true;
  };

  // Count completed checks against the CHECKS whitelist so the counter is
  // strictly bounded by CHECKS.length. Previously a raw Object.keys count
  // could overshoot (e.g. "15 / 12") whenever stale or extra keys leaked
  // into the results dict.
  const completed = CHECKS.filter((c) => results[c.key] != null).length;
  const inProgress = progress != null;
  const headline = buildHeadline(results);

  return (
    <div style={{
      padding: 20,
      borderTop: '1px solid var(--neutral-200)',
      background: '#f0fdf4',
    }}>
      <div
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setExpanded(!expanded)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 15, flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0, color: '#166534' }}>★ Quality Overview</h3>
          <span style={{ fontSize: '0.85rem', color: 'var(--neutral-600)' }}>
            One-click full quality audit
          </span>
          {completed > 0 && !inProgress && (
            <span style={{
              background: '#dcfce7',
              color: '#166534',
              padding: '2px 10px',
              borderRadius: 10,
              fontSize: '0.8rem',
              fontWeight: 600,
            }}>
              {completed} / {progress?.total || CHECKS.length} checks complete
            </span>
          )}
        </div>
        <span style={{ fontSize: '0.8rem', color: 'var(--neutral-600)' }}>
          {expanded ? 'Hide' : 'Show'}
        </span>
      </div>

      {expanded && (
        <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Concurrent-job warning */}
          {activeJobs > 0 && (
            <div style={{
              padding: '10px 14px',
              background: '#fef3c7',
              border: '1px solid #fde68a',
              borderRadius: 8,
              fontSize: '0.85rem',
              color: '#92400e',
            }}>
              ⚠ <strong>{activeJobs} background job{activeJobs === 1 ? '' : 's'}</strong>{' '}
              currently running on the same Ollama server (question generation, parsing, …).
              Quality checks will compete with those jobs for LLM time and will be
              significantly slower. Consider waiting for jobs to finish before running checks.
            </div>
          )}

          {/* Action row */}
          {!inProgress ? (
            <div style={{
              display: 'flex',
              gap: 14,
              alignItems: 'center',
              flexWrap: 'wrap',
              padding: '14px 16px',
              background: 'white',
              border: '1px solid var(--neutral-200)',
              borderLeft: '4px solid #0d7a4a',
              borderRadius: 8,
            }}>
              <div style={{ flex: 1, minWidth: 200, fontSize: '0.9rem', color: 'var(--neutral-700)' }}>
                Run all {CHECKS.length} quality metrics, or pick <strong>Quick mode</strong>
                {' '}({CHECKS.filter((c) => c.fast).length} fast checks, no extra LLM calls).
                Cached after the first run.
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button onClick={runQuick} style={BTN_BIG(false, 'ghost')}>
                  Quick run ({CHECKS.filter((c) => c.fast).length})
                </button>
                <button onClick={runAll} style={BTN_BIG(false, 'primary')}>
                  {completed > 0 ? 'Re-run all' : `Run all ${CHECKS.length}`}
                </button>
              </div>
            </div>
          ) : (
            <ProgressCard
              progress={progress}
              completedKeys={Object.keys(results)}
              errorKeys={Object.keys(errors)}
              onAbort={abort}
            />
          )}

          {/* Errors */}
          {Object.keys(errors).length > 0 && !inProgress && (
            <div style={{
              padding: '8px 14px',
              background: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: 8,
              fontSize: '0.85rem',
              color: '#991b1b',
            }}>
              <strong>{Object.keys(errors).length} check(s) failed:</strong>{' '}
              {Object.entries(errors).map(([k, msg]) => `${k} — ${msg}`).join('; ')}
            </div>
          )}

          {/* Headline dashboard */}
          {headline.length > 0 && (
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 12,
            }}>
              {headline.map((h) => (
                <div key={h.label} style={{
                  ...STAT_BOX,
                  borderLeft: `4px solid ${h.color || '#0d7a4a'}`,
                }}>
                  <div style={{
                    fontSize: '0.7rem',
                    color: 'var(--neutral-500)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    marginBottom: 4,
                  }}>
                    {h.label}
                  </div>
                  <div style={{
                    fontSize: '1.6rem',
                    fontWeight: 800,
                    color: h.color || 'var(--neutral-800)',
                  }}>
                    {h.value}
                  </div>
                  {h.sub && (
                    <div style={{ fontSize: '0.75rem', color: 'var(--neutral-500)', marginTop: 2 }}>
                      {h.sub}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {completed > 0 && !inProgress && (
            <div style={{ fontSize: '0.82rem', color: 'var(--neutral-600)', fontStyle: 'italic' }}>
              ↓ Scroll down for detailed per-check reports and per-question drill-downs.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Progress card — clean single-source-of-truth display.
// ---------------------------------------------------------------------------
function ProgressCard({ progress, completedKeys, errorKeys, onAbort }) {
  const { idx, total, label, mode, list } = progress;
  const current = list?.[idx];
  const isSlowCheck = current?.slow;

  return (
    <div style={{
      padding: '16px',
      background: 'white',
      border: '2px solid #0d7a4a',
      borderRadius: 8,
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        marginBottom: 10,
        gap: 12,
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.9rem', color: '#166534', fontWeight: 600, marginBottom: 4 }}>
            Step {idx + 1} of {total} — {mode === 'quick' ? 'Quick mode' : 'Full audit'}
          </div>
          <div style={{ fontSize: '1.05rem', color: 'var(--neutral-800)', fontWeight: 700 }}>
            {label}…
            {isSlowCheck && (
              <span style={{
                marginLeft: 10,
                fontSize: '0.75rem',
                padding: '2px 8px',
                background: '#fef3c7',
                color: '#92400e',
                borderRadius: 10,
                fontWeight: 600,
              }}>
                slow check
              </span>
            )}
          </div>
        </div>
        <button onClick={onAbort} style={BTN_BIG(false, 'danger')}>
          Abort
        </button>
      </div>

      <div style={{ background: '#d1fae5', height: 8, borderRadius: 4, overflow: 'hidden', marginBottom: 10 }}>
        <div style={{
          width: `${(idx / total) * 100}%`,
          height: '100%',
          background: '#0d7a4a',
          transition: 'width 250ms ease',
        }} />
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {list.map((c, i) => {
          const isDone = completedKeys.includes(c.key);
          const hasErr = errorKeys.includes(c.key);
          const isCurrent = i === idx;
          const isPending = i > idx;
          let bg = '#dcfce7', color = '#166534', icon = '✓';
          if (hasErr) { bg = '#fef2f2'; color = '#991b1b'; icon = '✕'; }
          else if (isCurrent) { bg = '#fef3c7'; color = '#92400e'; icon = '⟳'; }
          else if (isPending) { bg = '#f3f4f6'; color = '#6b7280'; icon = '·'; }
          else if (!isDone) { bg = '#f3f4f6'; color = '#6b7280'; icon = '·'; }
          return (
            <span key={c.key} style={{
              padding: '4px 10px',
              background: bg,
              color,
              borderRadius: 10,
              fontSize: '0.78rem',
              fontWeight: 600,
              whiteSpace: 'nowrap',
            }}>
              {icon} {c.label.split(' (')[0]}
            </span>
          );
        })}
      </div>

      {isSlowCheck && (
        <div style={{
          marginTop: 12,
          fontSize: '0.8rem',
          color: 'var(--neutral-600)',
          fontStyle: 'italic',
        }}>
          This check makes many LLM calls per question — with a large corpus on local Ollama
          it can take a long time. Use <strong>Abort</strong> if you want to skip it.
        </div>
      )}
    </div>
  );
}

function buildHeadline(r) {
  const out = [];

  if (r.coverage?.concept_coverage?.available) {
    const cc = r.coverage.concept_coverage;
    out.push({
      label: 'Concept Coverage',
      value: `${cc.weighted_concept_coverage_pct}%`,
      sub: `${cc.concepts_covered}/${cc.total_concepts} concepts`,
      color: cc.weighted_concept_coverage_pct >= 70 ? '#16a34a'
        : cc.weighted_concept_coverage_pct >= 50 ? '#ca8a04' : '#dc2626',
    });
  }

  if (r.lint) {
    const l = r.lint;
    out.push({
      label: 'Haladyna Avg Score',
      value: `${l.average_score}/100`,
      sub: `${l.aggregate_counts?.error || 0} errors · ${l.aggregate_counts?.warn || 0} warnings`,
      color: l.average_score >= 85 ? '#16a34a'
        : l.average_score >= 65 ? '#ca8a04' : '#dc2626',
    });
  }

  if (r.judge && r.judge.cohen_kappa != null) {
    const k = r.judge.cohen_kappa;
    const lbl = k < 0 ? 'worse than chance'
              : k < 0.21 ? 'slight'
              : k < 0.41 ? 'fair'
              : k < 0.61 ? 'moderate'
              : k < 0.81 ? 'substantial' : 'almost perfect';
    out.push({
      label: "SOLO Judge κ",
      value: k.toFixed(2),
      sub: lbl,
      color: k >= 0.61 ? '#16a34a' : k >= 0.41 ? '#ca8a04' : '#dc2626',
    });
  }

  if (r.cove) {
    out.push({
      label: 'CoVe Supported',
      value: `${r.cove.support_rate}%`,
      sub: `${r.cove.needs_review} need review`,
      color: r.cove.support_rate >= 80 ? '#16a34a'
        : r.cove.support_rate >= 60 ? '#ca8a04' : '#dc2626',
    });
  }

  if (r.solv?.mean_p_value != null) {
    // Solvability is the slowest check and is now progressively cached.
    // A `partial: true` payload means an earlier run was interrupted and
    // the dashboard is showing what completed so far — flag that visibly
    // so the user knows the number is provisional.
    const isPartial = r.solv.partial === true;
    const done = r.solv.completed_questions;
    const total = r.solv.total_questions;
    out.push({
      label: 'Solver mean p',
      value: r.solv.mean_p_value.toFixed(2),
      sub: isPartial && done != null && total != null
        ? `partial — ${done}/${total} solved`
        : 'LLM-blind difficulty',
      color: r.solv.mean_p_value <= 0.9 && r.solv.mean_p_value >= 0.5 ? '#16a34a' : '#ca8a04',
    });
  }

  if (r.stem?.h4_pass_rate != null) {
    out.push({
      label: 'H4 Stem-Only Pass',
      value: `${r.stem.h4_pass_rate}%`,
      sub: 'self-contained stems',
      color: r.stem.h4_pass_rate >= 70 ? '#16a34a'
        : r.stem.h4_pass_rate >= 50 ? '#ca8a04' : '#dc2626',
    });
  }

  if (r.ioc?.ioc_index != null) {
    out.push({
      label: 'IOC Index',
      value: r.ioc.ioc_index.toFixed(2),
      sub: r.ioc.ioc_label,
      color: r.ioc.ioc_index >= 0.5 ? '#16a34a' : r.ioc.ioc_index >= 0 ? '#ca8a04' : '#dc2626',
    });
  }

  if (r.readability?.mean_flesch_kincaid_grade != null) {
    out.push({
      label: 'Readability (FK)',
      value: r.readability.mean_flesch_kincaid_grade.toFixed(1),
      sub: 'grade level',
    });
  }

  if (r.ambiguity?.ambiguity_rate != null) {
    out.push({
      label: 'Ambiguity Rate',
      value: `${r.ambiguity.ambiguity_rate}%`,
      sub: `${r.ambiguity.ambiguous_count} flagged`,
      color: r.ambiguity.ambiguity_rate <= 10 ? '#16a34a'
        : r.ambiguity.ambiguity_rate <= 25 ? '#ca8a04' : '#dc2626',
    });
  }

  if (r.misc) {
    out.push({
      label: 'Misconceptions Mined',
      value: r.misc.misconception_count ?? 0,
      sub: `from ${r.misc.cue_windows_found ?? 0} cue windows`,
    });
  }

  if (r.grammar?.homogeneous_rate != null) {
    out.push({
      label: 'Grammar Homogeneous',
      value: `${r.grammar.homogeneous_rate}%`,
      sub: `${r.grammar.correct_outlier_count} clue risk`,
      color: r.grammar.homogeneous_rate >= 80 ? '#16a34a'
        : r.grammar.homogeneous_rate >= 60 ? '#ca8a04' : '#dc2626',
    });
  }

  if (r.face?.mean_face_validity_score != null) {
    out.push({
      label: 'Face Validity',
      value: `${r.face.mean_face_validity_score.toFixed(2)}/5`,
      sub: 'distractor rubric',
      color: r.face.mean_face_validity_score >= 4 ? '#16a34a'
        : r.face.mean_face_validity_score >= 3 ? '#ca8a04' : '#dc2626',
    });
  }

  return out;
}

export default QualityOverviewPanel;
