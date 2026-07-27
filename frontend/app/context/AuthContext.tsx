"use client";

import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import api from "../api";

export interface User {
  id: number;
  email: string;
  username: string;
  role: string;
  github_username: string | null;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, username: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const { data } = await api.get("/auth/me");
    setUser(data);
  }, []);

  useEffect(() => {
    const bootstrap = async () => {
      const token = localStorage.getItem("token");
      try {
        // Always await first so state is never set synchronously in the effect.
        if (token) await refreshUser();
        else await Promise.resolve();
      } catch {
        localStorage.removeItem("token");
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    void bootstrap();
  }, [refreshUser]);

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post("/auth/login", { email, password });
    localStorage.setItem("token", data.access_token);
    setUser(data.user);
  }, []);

  const signup = useCallback(async (email: string, username: string, password: string) => {
    const { data } = await api.post("/auth/signup", { email, username, password });
    localStorage.setItem("token", data.access_token);
    setUser(data.user);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
