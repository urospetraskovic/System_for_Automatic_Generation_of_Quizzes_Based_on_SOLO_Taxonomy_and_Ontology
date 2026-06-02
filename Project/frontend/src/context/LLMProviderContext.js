import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import apiClient, { llmApi } from '../api';

/**
 * Global LLM-provider state.
 *
 * Stores the user's currently-selected provider in localStorage so that
 * choice survives a page reload, and attaches an axios interceptor so
 * every API call sends the X-LLM-Provider header. The backend's
 * before_request hook reads that header and routes downstream LLM calls
 * to the matching provider.
 */

const STORAGE_KEY = 'llm_provider';
const DEFAULT_PROVIDER = 'ollama';

const LLMProviderContext = createContext({
  provider: DEFAULT_PROVIDER,
  setProvider: () => {},
  providers: [],
  spend: {},
  refreshSpend: () => {},
  resetSpend: () => {},
});

export function LLMProviderProvider({ children }) {
  const [provider, setProviderRaw] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) || DEFAULT_PROVIDER;
    } catch {
      return DEFAULT_PROVIDER;
    }
  });

  const [providers, setProviders] = useState([]);
  const [spend, setSpend] = useState({});

  // Install the request interceptor on the SHARED apiClient instance — not
  // the global `axios` default. The app's services call through apiClient
  // (the named axios.create()-d instance in src/api.js), so attaching to
  // axios.interceptors would silently install a no-op. This bug was the
  // reason the X-LLM-Provider header never reached the backend and every
  // request fell through to the Ollama default.
  useEffect(() => {
    const id = apiClient.interceptors.request.use((config) => {
      config.headers = config.headers || {};
      config.headers['X-LLM-Provider'] = localStorage.getItem(STORAGE_KEY) || DEFAULT_PROVIDER;
      return config;
    });
    return () => apiClient.interceptors.request.eject(id);
  }, []);

  const setProvider = useCallback((name) => {
    const next = (name || DEFAULT_PROVIDER).toLowerCase();
    setProviderRaw(next);
    try { localStorage.setItem(STORAGE_KEY, next); } catch {}
  }, []);

  const loadProviders = useCallback(async () => {
    try {
      const res = await llmApi.providers();
      setProviders(res?.data?.providers || []);
    } catch {
      // Backend may be down; show whatever we already have.
    }
  }, []);

  const refreshSpend = useCallback(async () => {
    try {
      const res = await llmApi.spend();
      setSpend(res?.data || {});
    } catch {
      // Silent — widget will keep last-known values.
    }
  }, []);

  const resetSpend = useCallback(async (providerName) => {
    try {
      await llmApi.resetSpend(providerName);
      await refreshSpend();
    } catch {
      // ignore
    }
  }, [refreshSpend]);

  useEffect(() => {
    loadProviders();
    refreshSpend();
    const t = setInterval(refreshSpend, 5000);
    return () => clearInterval(t);
  }, [loadProviders, refreshSpend]);

  return (
    <LLMProviderContext.Provider value={{
      provider, setProvider, providers, spend, refreshSpend, resetSpend,
    }}>
      {children}
    </LLMProviderContext.Provider>
  );
}

export function useLLMProvider() {
  return useContext(LLMProviderContext);
}
