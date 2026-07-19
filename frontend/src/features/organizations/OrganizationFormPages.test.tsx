import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { jsonResponse, problemResponse } from "../../test/auth";
import { OrganizationCreatePage } from "./OrganizationCreatePage";
import { OrganizationEditPage } from "./OrganizationEditPage";

const analytics = vi.hoisted(() => ({ pushAnalyticsFromResponse: vi.fn() }));
vi.mock("../auth/analytics", () => analytics);

type OrganizationDetail = components["schemas"]["OrganizationLoginDetailResponse"];

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((complete, fail) => { resolve = complete; reject = fail; });
  return { promise, reject, resolve };
}

const detail: OrganizationDetail = {
  capabilities: { can_create_billing: true, can_invite: true, can_manage: true, can_view_billing_stats: true },
  created_at: "2026-07-18T10:00:00Z",
  current_role: "admin",
  enforce_mfa: false,
  invites: [],
  members: [{
    created_at: "2026-07-18T10:00:00Z",
    email: "admin@example.com",
    is_current_user: true,
    role: "admin",
    user_id: 42
  }],
  name: "Ribeiro Imóveis",
  settings: {
    pix_key: "+5571999999999",
    pix_merchant_city: "SALVADOR",
    pix_merchant_name: "RIBEIRO IMOVEIS"
  },
  stats: {
    active_count: 0,
    billed_count: 0,
    expected: 0,
    net_income: 0,
    overdue: 0,
    overdue_count: 0,
    paid_count: 0,
    pending: 0,
    pending_count: 0,
    received: 0,
    total_expenses: 0,
    year: 2026
  },
  updated_at: "2026-07-18T11:00:00Z",
  uuid: "org-public-uuid"
};

afterEach(() => {
  cleanup();
  analytics.pushAnalyticsFromResponse.mockReset();
  vi.unstubAllGlobals();
});

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

function EditSwitcher() {
  const navigate = useNavigate();
  return <button onClick={() => navigate("/organizations/org-beta/edit")} type="button">Editar Beta</button>;
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

function renderCreate() {
  return render(
    <MemoryRouter initialEntries={["/organizations/create"]}>
      <Routes>
        <Route element={<><OrganizationCreatePage /><LocationProbe /></>} path="/organizations/create" />
        <Route element={<LocationProbe />} path="/organizations/" />
        <Route element={<LocationProbe />} path="/organizations/:orgUuid" />
      </Routes>
    </MemoryRouter>
  );
}

function renderEdit() {
  return render(
    <MemoryRouter initialEntries={["/organizations/org-public-uuid/edit"]}>
      <Routes>
        <Route element={<><OrganizationEditPage /><LocationProbe /></>} path="/organizations/:orgUuid/edit" />
        <Route element={<LocationProbe />} path="/organizations/:orgUuid" />
      </Routes>
    </MemoryRouter>
  );
}

function renderSwitchableEdit() {
  return render(
    <MemoryRouter initialEntries={["/organizations/org-public-uuid/edit"]}>
      <Routes>
        <Route element={<><EditSwitcher /><OrganizationEditPage /><LocationProbe /></>} path="/organizations/:orgUuid/edit" />
        <Route element={<LocationProbe />} path="/organizations/:orgUuid" />
      </Routes>
    </MemoryRouter>
  );
}

it("creates an organization from the exact legacy form and forwards analytics", async () => {
  const user = userEvent.setup();
  const fetchMock = installFetch({
    "POST /api/v1/organizations": (init) => {
      expect(JSON.parse(String(init?.body))).toEqual({ name: "Ribeiro Imóveis" });
      return jsonResponse({
        capabilities: { can_create_billing: true, can_invite: true, can_manage: true, can_view_billing_stats: true },
        created_at: null,
        current_role: "admin",
        enforce_mfa: false,
        name: "Ribeiro Imóveis",
        updated_at: null,
        uuid: "created-org-uuid"
      }, 201, { "X-Rentivo-Analytics-Event": "rentivo_organization_created" });
    }
  });
  document.title = "Anterior";
  const view = renderCreate();

  expect(screen.getByRole("heading", { name: "Nova organização" })).toHaveClass("pagehead__title");
  expect(screen.getByRole("link", { name: "Organizações" })).toHaveClass("crumb");
  expect(screen.getByLabelText("Nome da organização")).toHaveFocus();
  await waitFor(() => expect(document.title).toBe("Nova organização - Rentivo"));
  await user.type(screen.getByLabelText("Nome da organização"), "Ribeiro Imóveis");
  await user.click(screen.getByRole("button", { name: "Criar organização" }));

  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/organizations/created-org-uuid"));
  expect(fetchMock).toHaveBeenCalledOnce();
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
  expect(document.title).toBe("Anterior");
  view.unmount();
  expect(document.title).toBe("Anterior");
});

it("deduplicates create submissions before the saving state rerenders", async () => {
  const user = userEvent.setup();
  const create = deferred<Response>();
  const fetchMock = installFetch({
    "POST /api/v1/organizations": () => create.promise
  });
  renderCreate();
  await user.type(screen.getByLabelText("Nome da organização"), "Acme");
  const form = screen.getByRole("button", { name: "Criar organização" }).closest("form") as HTMLFormElement;

  act(() => {
    fireEvent.submit(form);
    fireEvent.submit(form);
  });

  await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
  expect(screen.getByRole("button", { name: "Criando..." })).toBeDisabled();
  await act(async () => {
    create.resolve(jsonResponse({
      capabilities: { can_create_billing: true, can_invite: true, can_manage: true, can_view_billing_stats: true },
      created_at: null,
      current_role: "admin",
      enforce_mfa: false,
      name: "Acme",
      updated_at: null,
      uuid: "created-org-uuid"
    }, 201, { "X-Rentivo-Analytics-Event": "rentivo_organization_created" }));
  });
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/organizations/created-org-uuid"));
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
});

it("aborts create on navigation and ignores its late response", async () => {
  const user = userEvent.setup();
  const create = deferred<Response>();
  let createSignal: AbortSignal | null | undefined;
  installFetch({
    "POST /api/v1/organizations": (init) => {
      createSignal = init?.signal;
      return create.promise;
    }
  });
  renderCreate();
  await user.type(screen.getByLabelText("Nome da organização"), "Acme");
  await user.click(screen.getByRole("button", { name: "Criar organização" }));
  await waitFor(() => expect(createSignal).toBeDefined());

  await user.click(screen.getByRole("link", { name: "Cancelar" }));

  expect(screen.getByTestId("location")).toHaveTextContent("/organizations/");
  expect(createSignal?.aborted).toBe(true);
  await act(async () => {
    create.resolve(jsonResponse({
      capabilities: { can_create_billing: true, can_invite: true, can_manage: true, can_view_billing_stats: true },
      created_at: null,
      current_role: "admin",
      enforce_mfa: false,
      name: "Acme",
      updated_at: null,
      uuid: "late-org-uuid"
    }, 201, { "X-Rentivo-Analytics-Event": "rentivo_organization_created" }));
  });
  expect(screen.getByTestId("location")).toHaveTextContent("/organizations/");
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("normalizes realistic body field errors and focuses the create control", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  installFetch({
    "POST /api/v1/organizations": () => {
      attempts += 1;
      if (attempts === 1) return problemResponse({
        code: "validation_error",
        detail: "Confira os campos.",
        fields: { "body.name": "Nome é obrigatório." },
        request_id: "request-id",
        status: 422,
        title: "Dados inválidos",
        type: "problem"
      });
      throw new Error("offline");
    }
  });
  renderCreate();

  await user.type(screen.getByLabelText("Nome da organização"), " ");
  await user.click(screen.getByRole("button", { name: "Criar organização" }));
  expect(await screen.findByText("Nome é obrigatório.")).toBeVisible();
  expect(screen.getByLabelText("Nome da organização")).toHaveFocus();
  await user.type(screen.getByLabelText("Nome da organização"), "Acme");
  await user.click(screen.getByRole("button", { name: "Criar organização" }));
  expect(await screen.findByText("Não foi possível criar a organização.")).toBeVisible();
  expect(screen.getByLabelText("Nome da organização")).toHaveFocus();
});

it("surfaces a create API problem without field errors", async () => {
  const user = userEvent.setup();
  installFetch({
    "POST /api/v1/organizations": () => problemResponse({
      code: "organization_conflict",
      detail: "Já existe uma organização com este nome.",
      fields: {},
      request_id: "request-id",
      status: 409,
      title: "Conflito",
      type: "problem"
    })
  });
  renderCreate();
  await user.type(screen.getByLabelText("Nome da organização"), "Acme");
  await user.click(screen.getByRole("button", { name: "Criar organização" }));
  expect(await screen.findByText("Já existe uma organização com este nome.")).toBeVisible();
  expect(screen.getByLabelText("Nome da organização")).toHaveFocus();
});

it("loads and saves every legacy organization setting", async () => {
  const user = userEvent.setup();
  installFetch({
    "GET /api/v1/organizations/org-public-uuid": () => jsonResponse(detail),
    "PATCH /api/v1/organizations/org-public-uuid": (init) => {
      expect(JSON.parse(String(init?.body))).toEqual({
        name: "Ribeiro Gestão",
        pix_key: "+5571888888888",
        pix_merchant_city: "LAURO FREITAS",
        pix_merchant_name: "RIBEIRO GESTAO"
      });
      return jsonResponse({ ...detail, name: "Ribeiro Gestão" }, 200, {
        "X-Rentivo-Analytics-Event": "rentivo_organization_updated"
      });
    }
  });
  document.title = "Anterior";
  const view = renderEdit();

  expect(screen.getByText("Carregando organização...")).toBeVisible();
  expect(await screen.findByRole("heading", { name: "Editar Organização" })).toHaveClass("mb-3");
  expect(screen.getByLabelText("Nome")).toHaveValue("Ribeiro Imóveis");
  expect(screen.getByLabelText("Chave PIX")).toHaveValue("+5571999999999");
  await waitFor(() => expect(document.title).toBe("Editar Ribeiro Imóveis - Rentivo"));
  await user.clear(screen.getByLabelText("Nome"));
  await user.type(screen.getByLabelText("Nome"), "Ribeiro Gestão");
  await user.clear(screen.getByLabelText("Chave PIX"));
  await user.type(screen.getByLabelText("Chave PIX"), "+5571888888888");
  await user.clear(screen.getByLabelText("Nome do recebedor"));
  await user.type(screen.getByLabelText("Nome do recebedor"), "RIBEIRO GESTAO");
  await user.clear(screen.getByLabelText("Cidade do recebedor"));
  await user.type(screen.getByLabelText("Cidade do recebedor"), "LAURO FREITAS");
  await user.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/organizations/org-public-uuid"));
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
  view.unmount();
  expect(document.title).toBe("Anterior");
});

it("retries edit loading, handles realistic field errors, and hides the form by capability", async () => {
  const user = userEvent.setup();
  let getAttempts = 0;
  let patchAttempts = 0;
  installFetch({
    "GET /api/v1/organizations/org-public-uuid": () => {
      getAttempts += 1;
      if (getAttempts === 1) return problemResponse({ code: "unavailable", detail: "Organização indisponível.", fields: {}, request_id: "id", status: 503, title: "Indisponível", type: "problem" });
      if (getAttempts === 2) throw new Error("offline");
      return jsonResponse(detail);
    },
    "PATCH /api/v1/organizations/org-public-uuid": () => {
      patchAttempts += 1;
      if (patchAttempts === 1) return problemResponse({
        code: "validation_error",
        detail: "As configurações são inválidas.",
        fields: { "body.pix_merchant_city": "Cidade inválida." },
        request_id: "request-id",
        status: 422,
        title: "Dados inválidos",
        type: "problem"
      });
      if (patchAttempts === 2) return problemResponse({ code: "pix_conflict", detail: "PIX recusado.", fields: {}, request_id: "id", status: 409, title: "Conflito", type: "problem" });
      throw new Error("offline");
    }
  });
  renderEdit();

  expect(await screen.findByText("Organização indisponível.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByText("Não foi possível carregar a organização.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  await screen.findByLabelText("Cidade do recebedor");
  await user.clear(screen.getByLabelText("Nome"));
  await user.type(screen.getByLabelText("Nome"), "Rascunho preservado");
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("Cidade inválida.")).toBeVisible();
  expect(screen.getByLabelText("Nome")).toHaveValue("Rascunho preservado");
  expect(screen.getByLabelText("Cidade do recebedor")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("PIX recusado.")).toBeVisible();
  expect(screen.getByLabelText("Nome")).toHaveFocus();
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("Não foi possível atualizar a organização.")).toBeVisible();
  expect(screen.getByLabelText("Nome")).toHaveFocus();

  cleanup();
  installFetch({
    "GET /api/v1/organizations/org-public-uuid": () => jsonResponse({
      ...detail,
      capabilities: { can_create_billing: true, can_invite: true, can_manage: false, can_view_billing_stats: true },
      current_role: "admin",
      settings: null
    })
  });
  renderEdit();
  expect(await screen.findByText("Você não tem permissão para editar esta organização.")).toBeVisible();
  expect(screen.queryByRole("button", { name: "Salvar" })).not.toBeInTheDocument();
});

it("edits a manageable organization whose optional settings are absent", async () => {
  installFetch({
    "GET /api/v1/organizations/org-public-uuid": () => jsonResponse({ ...detail, settings: null })
  });
  renderEdit();
  expect(await screen.findByLabelText("Nome")).toHaveValue("Ribeiro Imóveis");
  expect(screen.getByLabelText("Chave PIX")).toHaveValue("");
  expect(screen.getByLabelText("Nome do recebedor")).toHaveValue("");
  expect(screen.getByLabelText("Cidade do recebedor")).toHaveValue("");
});

it("clears edit data on organization changes and ignores an aborted save from the previous route", async () => {
  const user = userEvent.setup();
  const betaLoad = deferred<Response>();
  const save = deferred<Response>();
  let saveSignal: AbortSignal | null | undefined;
  installFetch({
    "GET /api/v1/organizations/org-beta": () => betaLoad.promise,
    "GET /api/v1/organizations/org-public-uuid": () => jsonResponse(detail),
    "PATCH /api/v1/organizations/org-public-uuid": (init) => {
      saveSignal = init?.signal;
      return save.promise;
    }
  });
  renderSwitchableEdit();
  const name = await screen.findByLabelText("Nome");
  await user.clear(name);
  await user.type(name, "Rascunho da Acme");
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  await user.click(screen.getByRole("button", { name: "Editar Beta" }));

  expect(screen.getByText("Carregando organização...")).toBeVisible();
  expect(screen.queryByDisplayValue("Rascunho da Acme")).not.toBeInTheDocument();
  expect(saveSignal?.aborted).toBe(true);
  await act(async () => {
    betaLoad.resolve(jsonResponse({ ...detail, name: "Beta Imóveis", uuid: "org-beta" }));
  });
  expect(await screen.findByLabelText("Nome")).toHaveValue("Beta Imóveis");

  await act(async () => { save.resolve(jsonResponse(detail)); });
  expect(screen.getByTestId("location")).toHaveTextContent("/organizations/org-beta/edit");
  expect(screen.getByLabelText("Nome")).toHaveValue("Beta Imóveis");
});

it("deduplicates an edit save and aborts it when the page unmounts", async () => {
  const save = deferred<Response>();
  let saveSignal: AbortSignal | null | undefined;
  const fetchMock = installFetch({
    "GET /api/v1/organizations/org-public-uuid": () => jsonResponse(detail),
    "PATCH /api/v1/organizations/org-public-uuid": (init) => {
      saveSignal = init?.signal;
      return save.promise;
    }
  });
  const view = renderEdit();
  const form = (await screen.findByRole("button", { name: "Salvar" })).closest("form") as HTMLFormElement;

  act(() => {
    fireEvent.submit(form);
    fireEvent.submit(form);
  });
  await waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1));
  expect(screen.getByRole("button", { name: "Salvando..." })).toBeDisabled();
  view.unmount();

  expect(saveSignal?.aborted).toBe(true);
  await act(async () => { save.resolve(jsonResponse(detail)); });
});

it("ignores a rejected edit save after switching organizations", async () => {
  const user = userEvent.setup();
  const save = deferred<Response>();
  installFetch({
    "GET /api/v1/organizations/org-beta": () => jsonResponse({ ...detail, name: "Beta Imóveis", uuid: "org-beta" }),
    "GET /api/v1/organizations/org-public-uuid": () => jsonResponse(detail),
    "PATCH /api/v1/organizations/org-public-uuid": () => save.promise
  });
  renderSwitchableEdit();
  await user.click(await screen.findByRole("button", { name: "Salvar" }));
  await user.click(screen.getByRole("button", { name: "Editar Beta" }));
  await screen.findByDisplayValue("Beta Imóveis");

  await act(async () => { save.reject(new Error("offline")); });
  expect(screen.getByTestId("location")).toHaveTextContent("/organizations/org-beta/edit");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
