import { useEffect, useMemo, useState } from 'react';

import { questionApi } from '../api';

/**
 * Build a question_id -> lint report map for a set of questions.
 *
 * Lint is computed per lesson (the backend caches `/lessons/:id/lint`), so we
 * fetch once per distinct lesson present in `questions` and merge the per-item
 * reports. Returns an empty map until the fetches resolve; consumers should
 * treat a missing entry as "not linted yet" rather than "clean".
 */
export default function useQuestionLint(questions) {
  const [lintByQuestionId, setLintByQuestionId] = useState({});

  // Stable, sorted list of lesson ids so the effect only re-runs when the set
  // of lessons actually changes (not on every questions array identity change).
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
      setLintByQuestionId({});
      return;
    }
    let cancelled = false;
    Promise.all(
      lessonIds.map((id) =>
        questionApi.lintLesson(id)
          .then((res) => res.data?.reports || [])
          .catch(() => [])
      )
    ).then((reportLists) => {
      if (cancelled) return;
      const map = {};
      for (const reports of reportLists) {
        for (const report of reports) {
          map[report.question_id] = report;
        }
      }
      setLintByQuestionId(map);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lessonKey]);

  return lintByQuestionId;
}
