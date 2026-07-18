import { createBrowserRouter, Navigate, Outlet, type RouteObject } from "react-router-dom";

import {
  AuthenticatedAppShell,
  AuthProvider,
  useAuth
} from "../features/auth/AuthProvider";
import { ForgotPasswordPage } from "../features/auth/ForgotPasswordPage";
import { GoogleCallbackPage } from "../features/auth/GoogleCallbackPage";
import { LoginPage } from "../features/auth/LoginPage";
import { MfaVerifyPage } from "../features/auth/MfaVerifyPage";
import { ResetPasswordPage } from "../features/auth/ResetPasswordPage";
import { SignupPage } from "../features/auth/SignupPage";
import { RecoveryCodesPage } from "../features/security/RecoveryCodesPage";
import { SecurityPage } from "../features/security/SecurityPage";
import { TotpSetupPage } from "../features/security/TotpSetupPage";

// eslint-disable-next-line react-refresh/only-export-components
function PublicAuthLayout() {
  return (
    <main className="wrapper main-content">
      <Outlet />
    </main>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
function ProtectedApp() {
  const { retrySession, status } = useAuth();
  if (status === "loading") {
    return null;
  }
  if (status === "error") {
    return (
      <main className="wrapper main-content">
        <div className="toast toast--danger" role="alert">
          Não foi possível validar sua sessão.
        </div>
        <button className="btn btn--primary" onClick={retrySession} type="button">
          Tentar novamente
        </button>
      </main>
    );
  }
  if (status === "anonymous") {
    return <Navigate replace to="/login" />;
  }
  return <AuthenticatedAppShell />;
}

// eslint-disable-next-line react-refresh/only-export-components
function AuthenticatedNotFound() {
  return (
    <section className="empty-state">
      <h2>Página não encontrada</h2>
      <p>O endereço acessado não existe ou não está disponível.</p>
    </section>
  );
}

export function createAppRouter(children: RouteObject[] = [{ element: <AuthenticatedNotFound />, path: "*" }]) {
  const authenticatedRoutes: RouteObject[] = [
    { element: <SecurityPage />, path: "/security" },
    { element: <TotpSetupPage />, path: "/security/totp/setup" },
    { element: <RecoveryCodesPage />, path: "/security/recovery-codes" },
    ...children
  ];
  return createBrowserRouter([
    {
      children: [
        {
          children: [
            { element: <LoginPage />, path: "/login" },
            { element: <SignupPage />, path: "/signup" },
            { element: <MfaVerifyPage />, path: "/mfa-verify" },
            { element: <ForgotPasswordPage />, path: "/forgot-password" },
            { element: <ResetPasswordPage />, path: "/reset-password" },
            { element: <GoogleCallbackPage />, path: "/auth/google/callback" }
          ],
          element: <PublicAuthLayout />
        },
        { children: authenticatedRoutes, element: <ProtectedApp /> }
      ],
      element: (
        <AuthProvider>
          <Outlet />
        </AuthProvider>
      )
    }
  ]);
}

export const appRouter = createAppRouter();
