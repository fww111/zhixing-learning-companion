import { Navigate, Outlet, useLocation, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "../state/auth";

export function RequireAuth() {
  const { initialized, token, user } = useAuth();
  const location = useLocation();

  if (!initialized) {
    return <div className="route-loading">正在加载账户状态</div>;
  }
  if (!token || !user) {
    return <Navigate replace state={{ from: location.pathname }} to="/auth" />;
  }
  return <Outlet />;
}

export function RequireProfile() {
  const { initialized, profile } = useAuth();

  if (!initialized) {
    return <div className="route-loading">正在加载学生画像</div>;
  }
  if (!profile) {
    return <Navigate replace to="/profile/interview" />;
  }
  return <Outlet />;
}

export function RequireCourseProfile() {
  const { courseId } = useParams();
  const { initialized, refreshProfile, token } = useAuth();
  const [checking, setChecking] = useState(true);
  const [hasProfile, setHasProfile] = useState(false);
  const numericCourseId = Number(courseId);

  useEffect(() => {
    let cancelled = false;
    async function loadCourseProfile() {
      if (!initialized || !token) {
        return;
      }
      if (!Number.isFinite(numericCourseId)) {
        setChecking(false);
        setHasProfile(false);
        return;
      }
      setChecking(true);
      try {
        const profile = await refreshProfile(numericCourseId);
        if (!cancelled) {
          setHasProfile(Boolean(profile));
        }
      } catch {
        if (!cancelled) {
          setHasProfile(false);
        }
      } finally {
        if (!cancelled) {
          setChecking(false);
        }
      }
    }
    void loadCourseProfile();
    return () => {
      cancelled = true;
    };
  }, [initialized, refreshProfile, numericCourseId, token]);

  if (!initialized || checking) {
    return <div className="route-loading">正在加载当前课程画像</div>;
  }
  if (!Number.isFinite(numericCourseId)) {
    return <Navigate replace to="/courses" />;
  }
  if (!hasProfile) {
    return <Navigate replace to={`/courses/${numericCourseId}/profile/interview`} />;
  }
  return <Outlet />;
}

export function RedirectBySession() {
  const { initialized, token, user } = useAuth();

  if (!initialized) {
    return <div className="route-loading">正在进入系统</div>;
  }
  if (!token || !user) {
    return <Navigate replace to="/auth" />;
  }
  return <Navigate replace to="/courses" />;
}
