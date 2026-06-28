import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  getMyProfile,
  isUnauthorizedError,
  type AuthResponse,
  type AuthUser,
  type StudentProfile
} from "../api/client";
import { subscribeAuthSessionExpired } from "./authSessionEvents";

interface AuthState {
  initialized: boolean;
  token: string;
  user?: AuthUser;
  profile?: StudentProfile;
  profileCourseId?: number | null;
  setAuth: (auth: AuthResponse) => void;
  setProfile: (profile?: StudentProfile, courseId?: number | null) => void;
  loadProfile: (courseId?: number) => Promise<StudentProfile | undefined>;
  refreshProfile: (courseId?: number) => Promise<StudentProfile | undefined>;
  handleAuthError: (error: unknown) => boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [initialized, setInitialized] = useState(false);
  const [token, setToken] = useState(() => localStorage.getItem("pla_token") ?? "");
  const [user, setUser] = useState<AuthUser | undefined>(() => {
    const stored = localStorage.getItem("pla_user");
    return stored ? JSON.parse(stored) as AuthUser : undefined;
  });
  const [profile, setProfileState] = useState<StudentProfile>();
  const [profileCourseId, setProfileCourseId] = useState<number | null>();

  const clearSession = useCallback(() => {
    localStorage.removeItem("pla_token");
    localStorage.removeItem("pla_user");
    setToken("");
    setUser(undefined);
    setProfileState(undefined);
    setProfileCourseId(undefined);
    setInitialized(true);
  }, []);

  useEffect(() => subscribeAuthSessionExpired(clearSession), [clearSession]);

  const handleAuthError = useCallback((error: unknown): boolean => {
    if (!isUnauthorizedError(error)) {
      return false;
    }
    clearSession();
    return true;
  }, [clearSession]);

  const loadProfile = useCallback(async (courseId?: number) => {
    if (!token) {
      return undefined;
    }
    try {
      return await getMyProfile(token, courseId);
    } catch (caught) {
      if (handleAuthError(caught)) {
        return undefined;
      }
      throw caught;
    }
  }, [handleAuthError, token]);

  const refreshProfile = useCallback(async (courseId?: number) => {
    const nextProfile = await loadProfile(courseId);
    setProfileState(nextProfile);
    setProfileCourseId(nextProfile ? courseId ?? null : undefined);
    return nextProfile;
  }, [loadProfile]);

  const setAuth = useCallback((auth: AuthResponse) => {
    localStorage.setItem("pla_token", auth.access_token);
    localStorage.setItem("pla_user", JSON.stringify(auth.user));
    setToken(auth.access_token);
    setUser(auth.user);
    setProfileState(undefined);
    setProfileCourseId(undefined);
    setInitialized(false);
  }, []);

  const setProfile = useCallback((nextProfile?: StudentProfile, courseId?: number | null) => {
    setProfileState(nextProfile);
    setProfileCourseId(nextProfile ? courseId ?? null : undefined);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!token) {
        setProfileState(undefined);
        setProfileCourseId(undefined);
      }
      if (!cancelled) {
        setInitialized(true);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const value = useMemo<AuthState>(() => ({
    initialized,
    token,
    user,
    profile,
    setAuth,
    setProfile,
    loadProfile,
    refreshProfile,
    handleAuthError,
    logout: clearSession,
    profileCourseId,
  }), [clearSession, handleAuthError, initialized, loadProfile, profile, profileCourseId, refreshProfile, setAuth, setProfile, token, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
