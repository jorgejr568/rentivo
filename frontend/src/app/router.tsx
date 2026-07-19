import { createBrowserRouter, Navigate, Outlet, type RouteObject } from "react-router-dom";

import {
  AuthenticatedAppShell,
  AuthProvider,
  useAuth
} from "../features/auth/AuthProvider";
import { LoadingState } from "../components/PageState";
import { ForgotPasswordPage } from "../features/auth/ForgotPasswordPage";
import { GoogleCallbackPage } from "../features/auth/GoogleCallbackPage";
import { LoginPage } from "../features/auth/LoginPage";
import { MfaVerifyPage } from "../features/auth/MfaVerifyPage";
import { ResetPasswordPage } from "../features/auth/ResetPasswordPage";
import { SignupPage } from "../features/auth/SignupPage";
import { BillingCreatePage } from "../features/billings/BillingCreatePage";
import { BillingDetailPage } from "../features/billings/BillingDetailPage";
import { BillingEditPage } from "../features/billings/BillingEditPage";
import { BillingListPage } from "../features/billings/BillingListPage";
import { BillDetailPage } from "../features/bills/BillDetailPage";
import { BillEditPage } from "../features/bills/BillEditPage";
import { BillGeneratePage } from "../features/bills/BillGeneratePage";
import { CommunicationComposePage } from "../features/bills/CommunicationComposePage";
import { InviteListPage } from "../features/invites/InviteListPage";
import { NotFoundPage } from "../features/notFound/NotFoundPage";
import { OrganizationCreatePage } from "../features/organizations/OrganizationCreatePage";
import { OrganizationDetailPage } from "../features/organizations/OrganizationDetailPage";
import { OrganizationEditPage } from "../features/organizations/OrganizationEditPage";
import { OrganizationListPage } from "../features/organizations/OrganizationListPage";
import { RecoveryCodesPage } from "../features/security/RecoveryCodesPage";
import { SecurityPage } from "../features/security/SecurityPage";
import { TotpSetupPage } from "../features/security/TotpSetupPage";
import { ThemePage } from "../features/themes/ThemePage";
import { LandingPage } from "../features/landing/LandingPage";

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
    return (
      <main className="wrapper main-content">
        <LoadingState label="Carregando sessão..." />
      </main>
    );
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
function HomeRoute() {
  const { status } = useAuth();
  if (status === "authenticated") {
    return <Navigate replace to="/billings/" />;
  }
  return <LandingPage />;
}

export function createAppRouter(children: RouteObject[] = []) {
  const authenticatedRoutes: RouteObject[] = [
    ...children,
    { element: <BillingListPage />, path: "/billings/" },
    { element: <BillingCreatePage />, path: "/billings/create" },
    { element: <BillingDetailPage />, path: "/billings/:billingUuid" },
    { element: <BillingEditPage />, path: "/billings/:billingUuid/edit" },
    { element: <BillGeneratePage />, path: "/billings/:billingUuid/bills/generate" },
    { element: <BillDetailPage />, path: "/billings/:billingUuid/bills/:billUuid" },
    { element: <BillEditPage />, path: "/billings/:billingUuid/bills/:billUuid/edit" },
    {
      element: <CommunicationComposePage />,
      path: "/billings/:billingUuid/bills/:billUuid/communications/compose"
    },
    { element: <OrganizationListPage />, path: "/organizations/" },
    { element: <OrganizationCreatePage />, path: "/organizations/create" },
    { element: <OrganizationDetailPage />, path: "/organizations/:orgUuid" },
    { element: <OrganizationEditPage />, path: "/organizations/:orgUuid/edit" },
    { element: <InviteListPage />, path: "/invites/" },
    { element: <ThemePage target="user" />, path: "/themes/user" },
    { element: <ThemePage target="organization" />, path: "/themes/organization/:orgUuid" },
    { element: <ThemePage target="billing" />, path: "/themes/billing/:billingUuid" },
    { element: <SecurityPage />, path: "/security" },
    { element: <TotpSetupPage />, path: "/security/totp/setup" },
    { element: <RecoveryCodesPage />, path: "/security/recovery-codes" },
    { element: <NotFoundPage />, path: "*" }
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
        { element: <HomeRoute />, path: "/" },
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
