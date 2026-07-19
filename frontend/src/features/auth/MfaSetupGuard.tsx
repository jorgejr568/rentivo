import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "./AuthProvider";

const MFA_SETUP_PATHS = new Set([
  "/security/recovery-codes",
  "/security/totp/setup"
]);

export function MfaSetupGuard() {
  const { bootstrap } = useAuth();
  const location = useLocation();

  if (
    bootstrap?.capabilities.mfa_setup_required &&
    !MFA_SETUP_PATHS.has(location.pathname)
  ) {
    return <Navigate replace to="/security/totp/setup" />;
  }
  return <Outlet />;
}
