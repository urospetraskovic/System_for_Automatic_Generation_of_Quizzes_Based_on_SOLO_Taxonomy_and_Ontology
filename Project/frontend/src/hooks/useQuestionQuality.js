import { useEffect, useMemo, useState } from 'react';

import { questionApi } from '../api';

/**
 * Build a question_id -> { metricKey: report } map from whatever is ALREADY
 * cached for each lesson. Reads `/lessons/:id/quality-cache`, which returns
 * every cached validation report keyed by metric and never triggers a
 * (re)computation. Metrics the user has not run yet simply won't appear.
 *
 * `lint` is intentionally excluded here — it is surfaced separately via
 * useQuestionLint, which computes it on demand because it is cheap.
 */
export default function useQuestionQuality(questions) {
  const [qualityByQuestionId, setQualityByQuestionId] = useState({});

  const lessonIds = useMemo(() => {
    const ids = new Set();
    for (const q of questions || []) {
      if (q.primary_lesson_id != null) ids.add(q.primary_lesson_id);
    }
    return Array.from(ids).sort((a, b) => a - b);
  }, [questions]);

  const lessonKey = lessonIds.join(',');

  useEffect(() => {
    if (lessonIds.length === 0) {
      setQualityByQuestionId({});
      return;
    }
    let cancelled = false;
    Promise.all(
      lessonIds.map((id) =>
        questionApi.qualityCache(id)
          .then((res) => res.data || {})
          .catch(() => ({}))
      )
    ).then((cacheBlobs) => {
      if (cancelled) return;
      const map = {};
      for (const blob of cacheBlobs) {
        for (const [metricKey, payload] of Object.entries(blob)) {
          if (metricKey === 'lint') continue;
          const reports = payload && payload.reports;
          if (!Array.isArray(reports)) continue;
          for (const entry of reports) {
            const qid = entry.question_id;
            if (qid == null) continue;
            if (!map[qid]) map[qid] = {};
            map[qid][metricKey] = entry;
          }
        }
      }
      setQualityByQuestionId(map);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lessonKey]);

  return qualityByQuestionId;
}
