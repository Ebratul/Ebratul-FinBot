"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { login } from "@/lib/api";
import styles from "./page.module.css";

export default function LoginPage() {
  const { user, loginUser } = useAuth();
  const router = useRouter();
  const [manualUsername, setManualUsername] = useState("");
  const [manualPassword, setManualPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // If already logged in, redirect
  useEffect(() => {
    if (user) {
      router.push("/chat");
    }
  }, [user, router]);

  if (user) return null;

  const handleLogin = async (username, password) => {
    setError("");
    setLoading(true);
    try {
      const userData = await login(username, password);
      loginUser(userData);
      router.push("/chat");
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleManualSubmit = (e) => {
    e.preventDefault();
    if (!manualUsername || !manualPassword) {
      setError("Please enter both username and password");
      return;
    }
    handleLogin(manualUsername, manualPassword);
  };

  return (
    <div className={styles.page}>
      {/* Background decoration */}
      <div className={styles.bgDecor}>
        <div className={styles.bgCircle1} />
        <div className={styles.bgCircle2} />
        <div className={styles.bgCircle3} />
      </div>

      <div className={styles.container}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.logoLarge}>🤖</div>
          <h1 className={styles.title}>FinBot</h1>
          <p className={styles.subtitle}>
            Internal AI Assistant for <strong>FinSolve Technologies</strong>
          </p>
          <p className={styles.desc}>
            Ask questions about company policies, financial reports, engineering docs, and marketing assets — with role-based access control.
          </p>
        </div>

        {/* Login Form */}
        <div className={styles.sectionLabel}>
          <span className={styles.sectionLine} />
          <span>Sign In</span>
          <span className={styles.sectionLine} />
        </div>

        <form className={styles.loginForm} onSubmit={handleManualSubmit}>
          {error && (
            <div className="alert alert-error animate-slide-up">
              <span>⚠️</span>
              <span>{error}</span>
            </div>
          )}
          <div className={styles.formRow}>
            <div className={styles.formGroup}>
              <label className="input-label" htmlFor="username">Username</label>
              <input
                id="username"
                className="input"
                type="text"
                placeholder="Enter username"
                value={manualUsername}
                onChange={(e) => setManualUsername(e.target.value)}
              />
            </div>
            <div className={styles.formGroup}>
              <label className="input-label" htmlFor="password">Password</label>
              <input
                id="password"
                className="input"
                type="password"
                placeholder="Enter password"
                value={manualPassword}
                onChange={(e) => setManualPassword(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className={`btn btn-primary btn-lg ${styles.loginBtn}`}
              disabled={loading}
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </div>
        </form>

        {/* Footer */}
        <p className={styles.footer}>
          🔒 Role-Based Access Control enforced at the retrieval layer
        </p>
      </div>
    </div>
  );
}
