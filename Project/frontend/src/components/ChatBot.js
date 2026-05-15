import React, { useState, useRef, useEffect } from 'react';
import { chatApi } from '../api';
import '../styles/ChatBot.css';

// Simple markdown parser for chat messages
const parseMarkdown = (text) => {
  if (!text) return '';
  
  let html = text;
  
  // Escape HTML first
  html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  
  // Code blocks (```)
  html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  
  // Inline code (`)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  
  // Bold (**text** or __text__)
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  
  // Italic (*text* or _text_)
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  html = html.replace(/_([^_]+)_/g, '<em>$1</em>');
  
  // Headers
  html = html.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  
  // Blockquotes
  html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
  
  // Numbered lists (handle multiline)
  html = html.replace(/^(\d+)\. (.+)$/gm, '<oli>$2</oli>');
  html = html.replace(/(<oli>.*<\/oli>\n?)+/g, (match) => {
    return '<ol>' + match.replace(/<oli>/g, '<li>').replace(/<\/oli>/g, '</li>') + '</ol>';
  });
  
  // Bullet lists
  html = html.replace(/^[-*] (.+)$/gm, '<uli>$1</uli>');
  html = html.replace(/(<uli>.*<\/uli>\n?)+/g, (match) => {
    return '<ul>' + match.replace(/<uli>/g, '<li>').replace(/<\/uli>/g, '</li>') + '</ul>';
  });
  
  // Links — only http(s)/relative hrefs allowed (block javascript: and data: URLs).
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, label, href) => {
    const safe = /^(https?:\/\/|\/)/i.test(href.trim());
    return safe
      ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`
      : label;
  });
  
  // Line breaks (double newline = paragraph, single = br)
  html = html.replace(/\n\n/g, '</p><p>');
  html = html.replace(/\n/g, '<br/>');
  
  // Wrap in paragraph if not already wrapped
  if (!html.startsWith('<')) {
    html = '<p>' + html + '</p>';
  }
  
  // Clean up empty paragraphs
  html = html.replace(/<p><\/p>/g, '');
  html = html.replace(/<p>(<[houl])/g, '$1');
  html = html.replace(/(<\/[houl]\d?>)<\/p>/g, '$1');
  
  return html;
};

function ChatBot({ courseId, lessonId, isOpen, onClose }) {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const messagesEndRef = useRef(null);

  const clearChat = () => {
    setMessages([]);
    setError('');
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async (e) => {
    e.preventDefault();
    
    if (!inputValue.trim()) return;
    
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: inputValue,
      timestamp: new Date()
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setError('');
    setIsLoading(true);

    try {
      const conversationHistory = messages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      }));
      const { data } = await chatApi.sendMessage(
        inputValue,
        courseId,
        lessonId,
        conversationHistory
      );

      const assistantMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: data.response,
        timestamp: new Date(),
        service: data.service
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      setError(err.message);
      const errorMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: `Sorry, I encountered an error: ${err.message}`,
        timestamp: new Date(),
        isError: true
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="chatbot-container">
      {/* Premium Header */}
      <div className="chatbot-header">
        <div className="header-content">
          <div className="header-icon">🎓</div>
          <div className="header-text">
            <h3>Learning Assistant</h3>
            <span>
              <span className="status-dot"></span>
              AI-Powered Help
            </span>
          </div>
        </div>
        <div className="header-actions">
          <button className="new-chat-btn" onClick={clearChat} title="New Chat">
            🔄
          </button>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>
      </div>

      {/* Messages Area */}
      <div className="chatbot-messages">
        {messages.length === 0 && (
          <div className="chatbot-welcome">
            <div className="welcome-icon">🤖</div>
            <h4>Welcome to Learning Assistant!</h4>
            <p>I'm here to help you understand your course materials</p>
            
            <div className="welcome-features">
              <div className="feature-item">
                <span className="icon">📚</span>
                <span>Course Content</span>
              </div>
              <div className="feature-item">
                <span className="icon">❓</span>
                <span>Quiz Help</span>
              </div>
              <div className="feature-item">
                <span className="icon">💡</span>
                <span>Explanations</span>
              </div>
              <div className="feature-item">
                <span className="icon">📖</span>
                <span>Study Tips</span>
              </div>
            </div>
            
            <p className="hint">Type your question below to get started!</p>
          </div>
        )}
        
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`chatbot-message ${msg.role} ${msg.isError ? 'error' : ''}`}
          >
            <div className="message-avatar">
              {msg.role === 'user' ? '👤' : '🤖'}
            </div>
            <div className="message-content">
              <div 
                className="message-text"
                dangerouslySetInnerHTML={{ __html: parseMarkdown(msg.content) }}
              />
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="chatbot-message assistant loading">
            <div className="message-avatar">🤖</div>
            <div className="message-content">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}

        {error && !messages.find(m => m.isError) && (
          <div className="chatbot-error">
            ⚠️ {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Form */}
      <form className="chatbot-input-form" onSubmit={sendMessage}>
        <input
          type="text"
          className="chatbot-input"
          placeholder="Ask me anything..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          disabled={isLoading}
        />
        <button
          type="submit"
          className="chatbot-send-btn"
          disabled={isLoading || !inputValue.trim()}
        >
          {isLoading ? '...' : 'Send'}
        </button>
      </form>
    </div>
  );
}

export default ChatBot;
