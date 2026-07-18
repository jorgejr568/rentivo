import { useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiClient, apiRequest } from "../../lib/api/client";
import { StandardAuthPanel } from "./AuthComponents";
import { postLoginPath, useAuth } from "./AuthProvider";
import { saveMfaChallenge } from "./authStorage";

export function GoogleCallbackPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const callbackQuery = searchParams.toString();
  const requested = useRef(false);

  useEffect(() => {
    document.title = "Entrar com Google - Rentivo";
  }, []);

  useEffect(() => {
    if (requested.current) {
      return;
    }
    requested.current = true;

    const query = new URLSearchParams(callbackQuery);
    void apiRequest(
      apiClient.GET("/api/v1/auth/google/callback", {
        params: {
          query: {
            code: query.get("code") ?? undefined,
            error: query.get("error") ?? undefined,
            state: query.get("state") ?? undefined
          }
        }
      })
    )
      .then(({ data }) => {
        if (data.status === "mfa_required") {
          saveMfaChallenge({ challengeId: data.challenge_id, methods: data.methods });
          navigate(`/mfa-verify?challenge=${encodeURIComponent(data.challenge_id)}`, {
            replace: true
          });
          return;
        }
        auth.authenticate(data);
        navigate(postLoginPath(data.bootstrap), { replace: true });
      })
      .catch(() => {
        navigate("/login?error=google_auth_failed", { replace: true });
      });
  }, [auth, callbackQuery, navigate]);

  return (
    <StandardAuthPanel>
      <p className="text-muted" role="status">
        Entrando com o Google...
      </p>
    </StandardAuthPanel>
  );
}
