import React, { useEffect, useState, useCallback } from 'react';
import { adminApi } from '../../api';

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let n = bytes;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(n >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

function TopBar({ selectedCourse, selectedLesson, apiStatus }) {
  const [stats, setStats] = useState(null);
  const [clearing, setClearing] = useState(false);

  const refresh = useCallback(() => {
    adminApi.cacheStats()
      .then((r) => setStats(r.data))
      .catch(() => setStats(null));
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, [refresh]);

  const handleClear = async () => {
    if (!window.confirm('Clear the LLM response cache? Next generation will hit Ollama fresh.')) return;
    setClearing(true);
    try {
      await adminApi.clearCache();
      refresh();
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="top-bar">
      <div className="breadcrumb-container">
        {selectedCourse ? (
          <>
            <strong>{selectedCourse.name}</strong>
            {selectedLesson && (
              <>
                <span className="breadcrumb-separator">/</span>
                <strong>{selectedLesson.title}</strong>
              </>
            )}
          </>
        ) : (
          <strong>Welcome to SOLO Quiz Generator</strong>
        )}
      </div>
      <div className="top-bar-actions" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {stats && (
          <div
            title="Cached Ollama responses. Click to clear and force fresh generation next time."
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.8rem',
              color: 'var(--neutral-600)',
              background: 'var(--neutral-100)',
              padding: '4px 10px',
              borderRadius: '12px',
            }}
          >
            <span>LLM cache: {stats.entries} entries · {formatBytes(stats.size_bytes)}</span>
            <button
              onClick={handleClear}
              disabled={clearing || stats.entries === 0}
              style={{
                background: 'none',
                border: 'none',
                color: stats.entries === 0 ? 'var(--neutral-400)' : '#d32f2f',
                cursor: stats.entries === 0 ? 'default' : 'pointer',
                fontWeight: 600,
                padding: 0,
              }}
            >
              {clearing ? 'clearing…' : 'clear'}
            </button>
          </div>
        )}
        {apiStatus?.api_exhausted && (
          <div className="api-warning">API Keys Exhausted</div>
        )}
      </div>
    </div>
  );
}

export default TopBar;
