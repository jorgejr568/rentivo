import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { jsonResponse, problemResponse } from "../../test/auth";
import { InviteListPage } from "./InviteListPage";

const analytics = vi.hoisted(() => ({ pushAnalyticsFromResponse: vi.fn() }));
const auth = vi.hoisted(() => ({ refreshSession: vi.fn<() => Promise<void>>().mockResolvedValue(undefined) }));
vi.mock("../auth/analytics", () => analytics);
vi.mock("../auth/AuthProvider", () => ({ useAuth: () => auth }));

type Invite = components["schemas"]["PendingInviteLoginResponse"];

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((complete, fail) => { resolve = complete; reject = fail; });
  return { promise, reject, resolve };
}

const acmeInvite: Invite = {
  created_at: "2026-07-18T10:00:00Z",
  enforce_mfa: true,
  invited_by_email: "owner@acme.com",
  organization_name: "Acme",
  organization_uuid: "org-acme",
  role: "manager",
  uuid: "invite-public-uuid"
};
const betaInvite: Invite = {
  ...acmeInvite,
  enforce_mfa: false,
  invited_by_email: "admin@beta.com",
  organization_name: "Beta",
  organization_uuid: "org-beta",
  role: "viewer",
  uuid: "invite-beta-uuid"
};

afterEach(() => {
  cleanup();
  analytics.pushAnalyticsFromResponse.mockReset();
  auth.refreshSession.mockReset().mockResolvedValue(undefined);
  vi.unstubAllGlobals();
});

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

function AwayButton() {
  const navigate = useNavigate();
  return <button onClick={() => navigate("/away")} type="button">Sair da página</button>;
}

function installFetch(handlers: Record<string, (init?: RequestInit) => Response | Promise<Response>>) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${String(input)}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`Unexpected request: ${key}`);
    return handler(init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/invites/"]}>
      <Routes>
        <Route element={<><InviteListPage /><LocationProbe /></>} path="/invites/" />
        <Route element={<LocationProbe />} path="/organizations/:orgUuid" />
        <Route element={<LocationProbe />} path="/security/totp/setup" />
      </Routes>
    </MemoryRouter>
  );
}

function renderPageWithAway() {
  return render(
    <MemoryRouter initialEntries={["/invites/"]}>
      <AwayButton />
      <Routes>
        <Route element={<><InviteListPage /><LocationProbe /></>} path="/invites/" />
        <Route element={<LocationProbe />} path="/away" />
        <Route element={<LocationProbe />} path="/organizations/:orgUuid" />
        <Route element={<LocationProbe />} path="/security/totp/setup" />
      </Routes>
    </MemoryRouter>
  );
}

it("renders loading, retry, and the exact empty new-account invite state", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  installFetch({
    "GET /api/v1/invites": () => {
      attempts += 1;
      if (attempts === 1) return problemResponse({
        code: "invites_unavailable",
        detail: "Convites indisponíveis.",
        fields: {},
        request_id: "request-id",
        status: 503,
        title: "Indisponível",
        type: "problem"
      });
      if (attempts === 2) throw new Error("offline");
      return jsonResponse({ items: [] });
    }
  });
  document.title = "Anterior";
  const view = renderPage();

  expect(screen.getByText("Carregando convites...")).toBeVisible();
  expect(await screen.findByText("Convites indisponíveis.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByText("Não foi possível carregar os convites.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByText("Nenhum convite pendente.")).toBeVisible();
  expect(screen.getByRole("heading", { level: 1, name: "Convites Pendentes" })).toHaveClass(
    "page-title"
  );
  await waitFor(() => expect(document.title).toBe("Convites - Rentivo"));
  view.unmount();
  expect(document.title).toBe("Anterior");
});

it("accepts an invite, forwards analytics, and routes enforced MFA setup", async () => {
  const user = userEvent.setup();
  installFetch({
    "GET /api/v1/invites": () => jsonResponse({ items: [acmeInvite, betaInvite] }),
    "POST /api/v1/invites/invite-public-uuid/accept": () => jsonResponse({
      mfa_setup_required: true,
      organization_uuid: "org-acme",
      status: "accepted"
    }, 200, { "X-Rentivo-Analytics-Event": "rentivo_invite_accepted" })
  });
  renderPage();

  expect(await screen.findByText("owner@acme.com")).toBeVisible();
  expect(screen.getByText("MFA")).toHaveClass("tag--mfa");
  expect(screen.getByText("manager")).toBeVisible();
  expect(screen.getByText("viewer")).toBeVisible();
  await user.click(screen.getAllByRole("button", { name: "Aceitar" })[0]);
  expect(await screen.findByRole("dialog", { name: "Aceitar convite?" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Aceitar convite" }));

  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/security/totp/setup"));
  expect(auth.refreshSession).toHaveBeenCalledOnce();
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
});

it("accepts without MFA, declines with confirmation, and keeps actions usable after errors", async () => {
  const user = userEvent.setup();
  let declineAttempts = 0;
  installFetch({
    "GET /api/v1/invites": () => jsonResponse({ items: [acmeInvite, betaInvite] }),
    "POST /api/v1/invites/invite-beta-uuid/accept": () => jsonResponse({
      mfa_setup_required: false,
      organization_uuid: "org-beta",
      status: "accepted"
    }, 200, { "X-Rentivo-Analytics-Event": "rentivo_invite_accepted" }),
    "POST /api/v1/invites/invite-public-uuid/decline": () => {
      declineAttempts += 1;
      if (declineAttempts === 1) return problemResponse({
        code: "invite_response_conflict",
        detail: "Este convite não está mais pendente.",
        fields: {},
        request_id: "request-id",
        status: 409,
        title: "Conflito",
        type: "problem"
      });
      throw new Error("offline");
    }
  });
  renderPage();
  await screen.findByText("Acme");

  await user.click(screen.getAllByRole("button", { name: "Recusar" })[0]);
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Recusar" })[0]).toHaveFocus();
  await user.click(screen.getAllByRole("button", { name: "Recusar" })[0]);
  await user.click(screen.getByRole("button", { name: "Recusar convite" }));
  expect(await screen.findByText("Este convite não está mais pendente.")).toBeVisible();
  await waitFor(() => expect(screen.getAllByRole("button", { name: "Recusar" })[0]).toHaveFocus());
  await user.click(screen.getAllByRole("button", { name: "Recusar" })[0]);
  await user.click(screen.getByRole("button", { name: "Recusar convite" }));
  expect(await screen.findByText("Não foi possível recusar o convite.")).toBeVisible();

  await user.click(screen.getAllByRole("button", { name: "Aceitar" })[1]);
  await user.click(screen.getByRole("button", { name: "Aceitar convite" }));
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/organizations/org-beta"));
});

it("removes a successfully declined invite and reports analytics", async () => {
  const user = userEvent.setup();
  auth.refreshSession.mockRejectedValueOnce(new Error("offline"));
  installFetch({
    "GET /api/v1/invites": () => jsonResponse({ items: [acmeInvite, betaInvite] }),
    "POST /api/v1/invites/invite-public-uuid/decline": () => jsonResponse({
      organization_uuid: "org-acme",
      status: "declined"
    }, 200, { "X-Rentivo-Analytics-Event": "rentivo_invite_declined" })
  });
  renderPage();
  await user.click((await screen.findAllByRole("button", { name: "Recusar" }))[0]);
  await user.click(screen.getByRole("button", { name: "Recusar convite" }));
  expect(await screen.findByText("Convite recusado.")).toBeVisible();
  expect(screen.queryByText("Acme")).not.toBeInTheDocument();
  expect(screen.getByText("Beta")).toBeVisible();
  await waitFor(() => expect(screen.getByRole("button", { name: "Recusar" })).toHaveFocus());
  expect(auth.refreshSession).toHaveBeenCalledOnce();
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
});

it("surfaces API and network failures while accepting an invite", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  installFetch({
    "GET /api/v1/invites": () => jsonResponse({ items: [acmeInvite] }),
    "POST /api/v1/invites/invite-public-uuid/accept": () => {
      attempts += 1;
      if (attempts === 1) return problemResponse({ code: "invite_conflict", detail: "O convite expirou.", fields: {}, request_id: "id", status: 409, title: "Conflito", type: "problem" });
      throw new Error("offline");
    }
  });
  renderPage();
  const accept = await screen.findByRole("button", { name: "Aceitar" });
  await user.click(accept);
  await user.click(screen.getByRole("button", { name: "Aceitar convite" }));
  expect(await screen.findByText("O convite expirou.")).toBeVisible();
  await waitFor(() => expect(accept).toHaveFocus());
  await user.click(accept);
  await user.click(screen.getByRole("button", { name: "Aceitar convite" }));
  expect(await screen.findByText("Não foi possível aceitar o convite.")).toBeVisible();
  await waitFor(() => expect(accept).toHaveFocus());
});

it("deduplicates accept and disables every invite action until the response settles", async () => {
  const user = userEvent.setup();
  const acceptResponse = deferred<Response>();
  const fetchMock = installFetch({
    "GET /api/v1/invites": () => jsonResponse({ items: [acmeInvite, betaInvite] }),
    "POST /api/v1/invites/invite-public-uuid/accept": () => acceptResponse.promise
  });
  renderPage();
  await user.click((await screen.findAllByRole("button", { name: "Aceitar" }))[0]);
  const confirm = screen.getByRole("button", { name: "Aceitar convite" });

  act(() => {
    confirm.click();
    confirm.click();
  });

  await waitFor(() => expect(screen.getAllByRole("button", { name: "Aceitar" }).every((button) => button.hasAttribute("disabled"))).toBe(true));
  expect(screen.getAllByRole("button", { name: "Recusar" }).every((button) => button.hasAttribute("disabled"))).toBe(true);
  await waitFor(() => expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/accept"))).toHaveLength(1));
  await act(async () => {
    acceptResponse.resolve(jsonResponse({ mfa_setup_required: false, organization_uuid: "org-acme", status: "accepted" }));
  });
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/organizations/org-acme"));
});

it("deduplicates decline while pending", async () => {
  const user = userEvent.setup();
  const declineResponse = deferred<Response>();
  const fetchMock = installFetch({
    "GET /api/v1/invites": () => jsonResponse({ items: [acmeInvite] }),
    "POST /api/v1/invites/invite-public-uuid/decline": () => declineResponse.promise
  });
  renderPage();
  await user.click(await screen.findByRole("button", { name: "Recusar" }));
  const confirm = screen.getByRole("button", { name: "Recusar convite" });

  act(() => {
    confirm.click();
    confirm.click();
  });

  await waitFor(() => expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/decline"))).toHaveLength(1));
  await act(async () => {
    declineResponse.resolve(jsonResponse({ organization_uuid: "org-acme", status: "declined" }));
  });
  expect(await screen.findByText("Convite recusado.")).toBeVisible();
});

it("aborts an accept request and ignores stale navigation after leaving the invite page", async () => {
  const user = userEvent.setup();
  const acceptResponse = deferred<Response>();
  let acceptSignal: AbortSignal | null | undefined;
  installFetch({
    "GET /api/v1/invites": () => jsonResponse({ items: [acmeInvite] }),
    "POST /api/v1/invites/invite-public-uuid/accept": (init) => {
      acceptSignal = init?.signal;
      return acceptResponse.promise;
    }
  });
  renderPageWithAway();
  await user.click(await screen.findByRole("button", { name: "Aceitar" }));
  await user.click(screen.getByRole("button", { name: "Aceitar convite" }));
  await waitFor(() => expect(acceptSignal).toBeDefined());
  await user.click(screen.getByRole("button", { name: "Sair da página" }));

  expect(screen.getByTestId("location")).toHaveTextContent("/away");
  expect(acceptSignal?.aborted).toBe(true);
  await act(async () => {
    acceptResponse.resolve(jsonResponse({ mfa_setup_required: true, organization_uuid: "org-acme", status: "accepted" }));
  });
  expect(screen.getByTestId("location")).toHaveTextContent("/away");
});

it("ignores navigation after leaving while the accepted invite refreshes the session", async () => {
  const user = userEvent.setup();
  const sessionRefresh = deferred<void>();
  auth.refreshSession.mockReturnValueOnce(sessionRefresh.promise);
  installFetch({
    "GET /api/v1/invites": () => jsonResponse({ items: [acmeInvite] }),
    "POST /api/v1/invites/invite-public-uuid/accept": () => jsonResponse({
      mfa_setup_required: true,
      organization_uuid: "org-acme",
      status: "accepted"
    })
  });
  renderPageWithAway();
  await user.click(await screen.findByRole("button", { name: "Aceitar" }));
  await user.click(screen.getByRole("button", { name: "Aceitar convite" }));
  await waitFor(() => expect(auth.refreshSession).toHaveBeenCalledOnce());

  await user.click(screen.getByRole("button", { name: "Sair da página" }));
  await act(async () => { sessionRefresh.resolve(undefined); });

  expect(screen.getByTestId("location")).toHaveTextContent("/away");
});

it("ignores a rejected response after leaving the invite page", async () => {
  const user = userEvent.setup();
  const acceptResponse = deferred<Response>();
  installFetch({
    "GET /api/v1/invites": () => jsonResponse({ items: [acmeInvite] }),
    "POST /api/v1/invites/invite-public-uuid/accept": () => acceptResponse.promise
  });
  renderPageWithAway();
  await user.click(await screen.findByRole("button", { name: "Aceitar" }));
  await user.click(screen.getByRole("button", { name: "Aceitar convite" }));
  await user.click(screen.getByRole("button", { name: "Sair da página" }));

  await act(async () => { acceptResponse.reject(new Error("offline")); });
  expect(screen.getByTestId("location")).toHaveTextContent("/away");
});
