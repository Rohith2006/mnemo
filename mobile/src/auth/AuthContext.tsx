import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, ApiError, getServerUrl, setServerUrl as persistServerUrl, getToken, setToken, clearToken } from "../api/client";
import type { TokenResponse, UserOut } from "../api/types";
import { registerForPush } from "../notifications/push";

type AuthState = {
  loading: boolean;
  serverUrl: string | null;
  user: UserOut | null;
  configureServer: (url: string, persist?: boolean) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [serverUrl, setServerUrlState] = useState<string | null>(null);
  const [user, setUser] = useState<UserOut | null>(null);

  useEffect(() => {
    (async () => {
      const url = await getServerUrl();
      setServerUrlState(url);
      const token = await getToken();
      if (url && token) {
        try {
          const me = await api.get<UserOut>("/api/me");
          setUser(me);
        } catch {
          await clearToken();
          setUser(null);
        }
      }
      setLoading(false);
    })();
  }, []);

  const configureServer = useCallback(async (url: string, persist: boolean = true) => {
    await persistServerUrl(url, persist);
    setServerUrlState(url.trim().replace(/\/+$/, ""));
  }, []);

  const signup = useCallback(async (email: string, password: string, name: string) => {
    const res = await api.post<TokenResponse>("/auth/signup", { email, password, name }, false);
    await setToken(res.access_token);
    setUser(res.user);
    registerForPush();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<TokenResponse>("/auth/login", { email, password }, false);
    await setToken(res.access_token);
    setUser(res.user);
    registerForPush();
  }, []);

  const logout = useCallback(async () => {
    await clearToken();
    setUser(null);
  }, []);

  const refreshMe = useCallback(async () => {
    try {
      setUser(await api.get<UserOut>("/api/me"));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        await clearToken();
        setUser(null);
      }
    }
  }, []);

  return (
    <AuthContext.Provider value={{ loading, serverUrl, user, configureServer, signup, login, logout, refreshMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
