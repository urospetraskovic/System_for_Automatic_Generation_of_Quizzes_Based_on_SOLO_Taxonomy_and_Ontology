import React, { createContext, useState, useContext, useEffect } from 'react';
import { translationApi } from '../api';

const LanguageContext = createContext();

export const LanguageProvider = ({ children }) => {
  const [languages, setLanguages] = useState({});
  const [selectedLanguage, setSelectedLanguage] = useState('sr');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchLanguages();
  }, []);

  const fetchLanguages = async () => {
    try {
      const { data } = await translationApi.getLanguages();
      if (data.success) {
        setLanguages(data.languages);
        setSelectedLanguage('sr'); // Default to Serbian
      }
    } catch (error) {
      console.error('Error fetching languages:', error);
    } finally {
      setLoading(false);
    }
  };

  const value = {
    languages,
    selectedLanguage,
    setSelectedLanguage,
    loading
  };

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error('useLanguage must be used within LanguageProvider');
  }
  return context;
};
