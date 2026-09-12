"use client";

import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { askAgent, getChatSessions, getChatHistory } from "@/lib/api";
import Navbar from "@/components/Navbar";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./chat.module.css";

export default function ChatPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);
  const [sessionId, setSessionId] = useState("");
  const [sessions, setSessions] = useState([]);

  const fetchSessions = async () => {
    try {
      const data = await getChatSessions();
      setSessions(data);
    } catch (err) {
      console.warn("Failed to load sessions:", err);
    }
  };

  useEffect(() => {
    if (!sessionId) {
      setSessionId(crypto.randomUUID());
    }
  }, [sessionId]);

  useEffect(() => {
    if (user) {
      fetchSessions();
    }
  }, [user]);

  useEffect(() => {
    const selectCollection = (collection) => {
      if (user?.accessible_collections?.includes(collection)) {
        setInput(`What information is available in the ${collection} documents?`);
      }
    };
    const collectionFromUrl = new URLSearchParams(window.location.search).get("collection");
    if (collectionFromUrl) {
      selectCollection(collectionFromUrl);
    }
    const handleCollectionEvent = (event) => {
      selectCollection(event.detail);
    };
    window.addEventListener("finbot:collection-select", handleCollectionEvent);
    return () => {
      window.removeEventListener("finbot:collection-select", handleCollectionEvent);
    };
  }, [user]);

  const handleNewChat = () => {
    setMessages([]);
    setSessionId(crypto.randomUUID());
    setError(null);
  };

  const handleSelectSession = async (id) => {
    if (id === sessionId) return;
    setSessionId(id);
    setMessages([]);
    setError(null);
    try {
      const history = await getChatHistory(id);
      setMessages(history);
    } catch(err) {
      console.error(err);
      setError("Failed to load chat history");
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/");
    }
  }, [loading, user, router]);

  if (loading) return <div className="page">Loading...</div>;
  if (!user) return null;

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || isTyping) return;

    const userMessage = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsTyping(true);
    setError(null);

    try {
      const isFirstMessage = messages.length === 0;
      const response = await askAgent(input, sessionId);
      
      if (isFirstMessage) {
        setTimeout(fetchSessions, 500);
      }
      
      const botMessage = {
        role: "assistant",
        content: response.answer,
        citations: response.citations,
        route: response.route,
        guardrail_warning: response.guardrail_warning,
        blocked: response.blocked,
        message: response.message
      };
      
      setMessages((prev) => [...prev, botMessage]);
    } catch (err) {
      setError(err.message || "Something went wrong. Please try again.");
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className={styles.chatLayout}>
      <Navbar />
      
      <div className={styles.bodyLayout}>
        <aside className={styles.sidebar}>
          <div className={styles.sidebarHeader}>
            <button onClick={handleNewChat} className="btn btn-outline" style={{ width: "100%" }}>
              + New Chat
            </button>
          </div>
          <div className={styles.sessionList}>
            {sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => handleSelectSession(s.id)}
                className={`${styles.sessionItem} ${s.id === sessionId ? styles.active : ""}`}
              >
                {s.title}
              </button>
            ))}
          </div>
        </aside>

        <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
          <main className={styles.main}>
            <div className={styles.chatContainer}>
              {messages.length === 0 && (
            <div className={styles.welcome}>
              <div className={styles.welcomeIcon}>👋</div>
              <h1>Hello, {user.display_name}</h1>
              <p>How can I help you today? I have access to your department&apos;s documents.</p>
              <div className={styles.suggestions}>
                <button onClick={() => setInput("What is the company leave policy?")} className={styles.suggestionBtn}>
                  Leave Policy
                </button>
                <button onClick={() => setInput("Who are our top investors?")} className={styles.suggestionBtn}>
                  Top Investors
                </button>
                <button onClick={() => setInput("Show me the system architecture.")} className={styles.suggestionBtn}>
                  Architecture
                </button>
              </div>
            </div>
          )}

          <div className={styles.messageList}>
            {messages.map((msg, idx) => (
              <div key={idx} className={`${styles.messageWrapper} ${msg.role === 'user' ? styles.userWrapper : styles.botWrapper}`}>
                <div className={`${styles.message} ${msg.role === 'user' ? styles.userMessage : styles.botMessage}`}>
                  <div className={styles.messageContent}>
                    {msg.role === 'assistant' ? (
                      <div className={styles.markdownBody}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      </div>
                    ) : (
                      msg.content
                    )}
                  </div>
                  
                  {msg.role === 'assistant' && (
                    <div className={styles.botMeta}>
                      {msg.route && (
                        <div className={styles.metaRow}>
                          <span className={`${styles.routeBadge} badge badge-info`}>
                            Route: {msg.route}
                          </span>
                        </div>
                      )}

                      {msg.guardrail_warning && (
                        <div className={`${styles.warning} alert alert-warning`}>
                          <span>⚠️</span>
                          <span>{msg.guardrail_warning}</span>
                        </div>
                      )}

                      {msg.blocked && (
                        <div className={`${styles.blocked} alert alert-error`}>
                          <span>🔒</span>
                          <span>{msg.message}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isTyping && (
              <div className={styles.botWrapper}>
                <div className={`${styles.message} ${styles.botMessage} ${styles.typing}`}>
                  <div className={styles.typingDots}>
                    <span></span><span></span><span></span>
                  </div>
                </div>
              </div>
            )}
            {error && (
              <div className="alert alert-error" style={{ margin: "10px 0" }}>
                <span>❌</span>
                <span>{error}</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>
      </main>

      <footer className={styles.footer}>
        <form className={styles.inputArea} onSubmit={handleSend}>
          <input
            type="text"
            className={styles.chatInput}
            placeholder="Ask a question about Ebratul Technologies docs..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isTyping}
          />
          <button type="submit" className={`btn btn-primary ${styles.sendBtn}`} disabled={isTyping || !input.trim()}>
            {isTyping ? "..." : "Send"}
          </button>
        </form>
      </footer>
      </div>
      </div>
    </div>
  );
}
