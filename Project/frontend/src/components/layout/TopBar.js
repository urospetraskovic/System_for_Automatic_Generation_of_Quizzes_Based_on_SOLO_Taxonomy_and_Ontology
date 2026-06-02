import React, { useEffect, useState, useCallback } from 'react';
import { adminApi } from '../../api';
import { useLLMProvider } from '../../context/LLMProviderContext';

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

function formatTokens(n) {
  if (!n) return '0';
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

function TopBar({ selectedCourse, selectedLesson, apiStatus }) {
  const [stats, setStats] = useState(null);
  const [clearing, setClearing] = useState(false);
  const { provider, setProvider, providers, spend, resetSpend } = useLLMProvider();

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
    if (!window.confirm('Clear the LLM response cache? Next generation will hit the active provider fresh.')) return;
    setClearing(true);
    try {
      await adminApi.clearCache();
      refresh();
    } finally {
      setClearing(false);
    }
  };

  const handleResetSpend = async () => {
    if (!window.confirm(`Reset the cost counter for ${provider}?`)) return;
    await resetSpend(provider);
  };

  const activeSpend = spend[provider] || { input_tokens: 0, output_tokens: 0, calls: 0, est_cost_usd: 0 };
  const isAnthropic = provider === 'anthropic';
  const anthropicAvailable = providers.find((p) => p.name === 'anthropic')?.available;

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

        {/* LLM provider selector */}
        <div
          title="Which LLM provider runs every generation / validation call. Persists across reloads."
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: '0.8rem',
            background: 'var(--neutral-100)',
            padding: '4px 10px',
            borderRadius: 12,
          }}
        >
          <span style={{ color: 'var(--neutral-600)' }}>Model:</span>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            style={{
              background: 'transparent',
              border: 'none',
              fontWeight: 700,
              color: 'var(--neutral-800)',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            <option value="ollama">Ollama (local)</option>
            <option value="anthropic" disabled={!anthropicAvailable}>
              Claude Haiku 4.5 {anthropicAvailable ? '' : '(no API key)'}
            </option>
          </select>
        </div>

        {/* Spend / cost tracker — only meaningful for paid providers */}
        {isAnthropic && (
          <div
            title="Live token usage and approximate cost for this session. Click reset to zero."
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: '0.8rem',
              background: '#fef3c7',
              padding: '4px 10px',
              borderRadius: 12,
              color: '#92400e',
            }}
          >
            <span>
              <strong>${activeSpend.est_cost_usd.toFixed(3)}</strong>
              {' · '}
              {formatTokens(activeSpend.input_tokens)} in / {formatTokens(activeSpend.output_tokens)} out
              {' · '}
              {activeSpend.calls} calls
            </span>
            <button
              onClick={handleResetSpend}
              style={{
                background: 'none',
                border: 'none',
                color: '#92400e',
                cursor: 'pointer',
                fontWeight: 600,
                padding: 0,
              }}
            >
              reset
            </button>
          </div>
        )}

        {stats && (
          <div
            title="Cached LLM responses. Click clear to force fresh generation next time."
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
