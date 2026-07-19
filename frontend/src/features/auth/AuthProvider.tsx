import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode
} from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { AppShell } from "../../components/AppShell";
import { ApiError, apiClient, apiRequest, setCsrfToken, setUnauthorizedHandler } from "../../lib/api/client";
import type { components } from "../../lib/api/schema";
import {
  configureAnalytics,
  pushAnalyticsEvent,
  pushAnalyticsFromResponse
} from "./analytics";
import { clearMfaChallenge } from "./authStorage";

type AuthConfig = components["schemas"]["AuthConfigResponse"];
type AuthenticatedResponse = components["schemas"]["AuthenticatedResponse"];
type Bootstrap = components["schemas"]["BootstrapResponse"];
type LoadStatus = "error" | "loading" | "ready";
type SessionStatus = "anonymous" | "authenticated" | "error" | "loading";

interface AuthContextValue {
  authenticate: (response: AuthenticatedResponse) => void;
  bootstrap: Bootstrap | null;
  config: AuthConfig | null;
  configStatus: LoadStatus;
  logout: () => Promise<void>;
  retryConfig: () => void;
  retrySession: () => void;
  status: SessionStatus;
}

const AuthContext = createContext<AuthContextValue | null>(null);
const PUBLIC_AUTH_PATHS = new Set([
  "/auth/google/callback",
  "/forgot-password",
  "/login",
  "/mfa-verify",
  "/reset-password",
  "/signup"
]);

// eslint-disable-next-line react-refresh/only-export-components
export function postLoginPath(bootstrap: Bootstrap): string {
  return bootstrap.capabilities.mfa_setup_required ? "/security/totp/setup" : "/billings/";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [configAttempt, setConfigAttempt] = useState(0);
  const [configStatus, setConfigStatus] = useState<LoadStatus>("loading");
  const [sessionAttempt, setSessionAttempt] = useState(0);
  const [status, setStatus] = useState<SessionStatus>("loading");
  const sessionGeneration = useRef(0);
  const location = useLocation();
  const navigate = useNavigate();

  const clearAuthentication = useCallback(() => {
    sessionGeneration.current += 1;
    setBootstrap(null);
    setCsrfToken("");
    setStatus("anonymous");
  }, []);

  const applyBootstrap = useCallback((value: Bootstrap) => {
    setBootstrap(value);
    setCsrfToken(value.csrf_token);
    clearMfaChallenge();
    setStatus("authenticated");
    configureAnalytics(value.analytics.gtm_container_id);
    value.analytics.events.forEach((event) => pushAnalyticsEvent({ ...event }));
  }, []);

  const authenticate = useCallback((response: AuthenticatedResponse) => {
    sessionGeneration.current += 1;
    applyBootstrap(response.bootstrap);
  }, [applyBootstrap]);

  useEffect(() => {
    setUnauthorizedHandler(({ schemaPath }) => {
      if (schemaPath === "/api/v1/auth/session") {
        return;
      }
      clearAuthentication();
      if (!PUBLIC_AUTH_PATHS.has(location.pathname)) {
        clearMfaChallenge();
        navigate("/login", { replace: true });
      }
    });
    return () => setUnauthorizedHandler(null);
  }, [clearAuthentication, location.pathname, navigate]);

  useEffect(() => {
    const controller = new AbortController();
    const generation = sessionGeneration.current;
    void apiRequest(apiClient.GET("/api/v1/auth/session", { signal: controller.signal }))
      .then(({ data }) => {
        if (sessionGeneration.current === generation) {
          applyBootstrap(data.bootstrap);
        }
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || sessionGeneration.current !== generation) {
          return;
        }
        if (caught instanceof ApiError && caught.status === 401) {
          clearAuthentication();
          return;
        }
        setStatus("error");
      });
    return () => controller.abort();
  }, [applyBootstrap, clearAuthentication, sessionAttempt]);

  useEffect(() => {
    const controller = new AbortController();
    setConfigStatus("loading");
    void apiRequest(apiClient.GET("/api/v1/auth/config", { signal: controller.signal }))
      .then(({ data }) => {
        configureAnalytics(data.analytics.gtm_container_id);
        setConfig(data);
        setConfigStatus("ready");
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setConfig(null);
          setConfigStatus("error");
        }
      });
    return () => controller.abort();
  }, [configAttempt]);

  const retryConfig = useCallback(() => setConfigAttempt((attempt) => attempt + 1), []);
  const retrySession = useCallback(() => {
    setStatus("loading");
    setSessionAttempt((attempt) => attempt + 1);
  }, []);

  const logout = useCallback(async () => {
    try {
      const { response } = await apiRequest(apiClient.POST("/api/v1/auth/logout"));
      pushAnalyticsFromResponse(response);
    } finally {
      clearAuthentication();
      clearMfaChallenge();
      if (location.pathname !== "/login") {
        navigate("/login", { replace: true });
      }
    }
  }, [clearAuthentication, location.pathname, navigate]);

  const value = useMemo<AuthContextValue>(
    () => ({
      authenticate,
      bootstrap,
      config,
      configStatus,
      logout,
      retryConfig,
      retrySession,
      status
    }),
    [authenticate, bootstrap, config, configStatus, logout, retryConfig, retrySession, status]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth deve ser usado dentro de AuthProvider.");
  }
  return value;
}

export function AuthenticatedAppShell({ children }: { children?: ReactNode }) {
  const { bootstrap, logout } = useAuth();
  return (
    <AppShell
      currentUser={bootstrap?.user}
      onLogout={logout}
      pendingInviteCount={bootstrap?.pending_invite_count}
    >
      {children}
    </AppShell>
  );
}
