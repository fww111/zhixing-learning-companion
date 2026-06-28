import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { AuthPanel } from "../components/AuthPanel";
import { useAuth } from "../state/auth";

export function AuthPage() {
  const { initialized, setAuth, token, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (initialized && token && user) {
    return <Navigate replace to="/courses" />;
  }

  return (
    <AuthPanel
      onAuthenticated={(auth) => {
        setAuth(auth);
        const from = typeof location.state === "object" && location.state && "from" in location.state
          ? String(location.state.from)
          : "/";
        navigate(from === "/auth" ? "/" : from, { replace: true });
      }}
    />
  );
}
