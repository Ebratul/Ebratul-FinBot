"use client";

import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { getMe, logout as apiLogout } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    try {
      const u = await getMe();
      setUser(u);
    } catch {
      setUser(null);
      localStorage.removeItem("finbot_token");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("finbot_token");
    if (token) {
      fetchUser();
    } else {
      setLoading(false);
    }
  }, [fetchUser]);

  const loginUser = (userData) => {
    setUser(userData);
  };

  const logoutUser = () => {
    apiLogout();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, loginUser, logoutUser, refetchUser: fetchUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
