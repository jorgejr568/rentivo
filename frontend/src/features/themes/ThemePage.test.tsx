import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import type { components } from "../../lib/api/schema";
import { jsonResponse, problemResponse } from "../../test/auth";
import { ThemePage } from "./ThemePage";

const analytics = vi.hoisted(() => ({ pushAnalyticsFromResponse: vi.fn() }));
vi.mock("../auth/analytics", () => analytics);

type ThemeResponse = components["schemas"]["ThemeResponse"];

const defaultTheme: ThemeResponse = {
  capabilities: { can_edit: true, can_reset: false },
  effective: {
    header_font: "Montserrat",
    primary: "#8A4C94",
    primary_light: "#EEE4F1",
    secondary: "#6EAFAE",
    secondary_dark: "#357B7C",
    text_color: "#282830",
    text_contrast: "#FFFFFF",
    text_font: "Montserrat"
  },
  effective_source: "default",
  owner_name: "Meu Tema",
  options: {
    fonts: ["Montserrat", "Roboto", "Lora"]
  },
  stored: null
};

const customTheme: ThemeResponse = {
  ...defaultTheme,
  capabilities: { can_edit: true, can_reset: true },
  effective: { ...defaultTheme.effective, header_font: "Lora", primary: "#123456" },
  effective_source: "user",
  stored: { ...defaultTheme.effective, header_font: "Lora", primary: "#123456" }
};

type Handler = (init?: RequestInit) => Promise<Response> | Response;

let createObjectURL: ReturnType<typeof vi.fn>;
let revokeObjectURL: ReturnType<typeof vi.fn>;

beforeEach(() => {
  let previewNumber = 0;
  createObjectURL = vi.fn(() => `blob:theme-preview-${++previewNumber}`);
  revokeObjectURL = vi.fn();
  const NativeURL = URL;
  class PreviewURL extends NativeURL {
    static createObjectURL = createObjectURL as (obj: Blob | MediaSource) => string;
    static revokeObjectURL = revokeObjectURL as (url: string) => void;
  }
  vi.stubGlobal("URL", PreviewURL);
  analytics.pushAnalyticsFromResponse.mockReset();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function pdfResponse() {
  return new Response("pdf", { headers: { "Content-Type": "application/pdf" } });
}

function deferred<Value>() {
  let resolve!: (value: Value) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<Value>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

function installFetch(handlers: Record<string, Handler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${String(input)}`;
    const handler = handlers[key];
    if (!handler) {
      throw new Error(`Unexpected request: ${key}`);
    }
    return handler(init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderPage(
  element: React.ReactElement,
  path = "/themes/user",
  routePath = "/themes/user"
) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={element} path={routePath} />
      </Routes>
    </MemoryRouter>
  );
}

function NavigateButton({ to }: { to: string }) {
  const navigate = useNavigate();
  return <button onClick={() => navigate(to)} type="button">Navegar</button>;
}

function renderStrictThemeRoutes(initialPath: string, navigateTo: string) {
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={[initialPath]}>
        <NavigateButton to={navigateTo} />
        <Routes>
          <Route element={<ThemePage target="billing" />} path="/themes/billing/:billingUuid" />
          <Route
            element={<ThemePage target="organization" />}
            path="/themes/organization/:orgUuid"
          />
          <Route element={<ThemePage target="user" />} path="/themes/user" />
        </Routes>
      </MemoryRouter>
    </StrictMode>
  );
}

it("populates a new-account user theme from effective defaults and previews it", async () => {
  installFetch({
    "GET /api/v1/themes/user": () => jsonResponse(defaultTheme),
    "POST /api/v1/themes/preview": () => pdfResponse()
  });

  const { unmount } = renderPage(<ThemePage target="user" />);

  expect(screen.getByText("Carregando tema...")).toBeVisible();
  expect(await screen.findByRole("heading", { level: 1, name: "Meu Tema" })).toHaveClass(
    "page-title"
  );
  for (const name of ["Fontes", "Cores", "Pré-visualização"]) {
    expect(screen.getByRole("heading", { level: 2, name })).toHaveStyle({
      fontSize: "0.98rem",
      margin: "0",
      whiteSpace: "nowrap"
    });
  }
  expect(screen.getByLabelText("Fonte do Cabeçalho")).toHaveValue("Montserrat");
  expect(screen.getByLabelText("Fonte do Texto")).toHaveValue("Montserrat");
  expect(screen.getByLabelText("Primária")).toHaveValue("#8a4c94");
  expect(screen.getByLabelText("Primária Clara")).toHaveValue("#eee4f1");
  expect(screen.getByLabelText("Secundária")).toHaveValue("#6eafae");
  expect(screen.getByLabelText("Secundária Escura")).toHaveValue("#357b7c");
  expect(screen.getByLabelText("Texto")).toHaveValue("#282830");
  expect(screen.getByLabelText("Contraste")).toHaveValue("#ffffff");
  expect(screen.getByLabelText("Primária").closest(".theme-color-grid")).not.toBeNull();
  expect(screen.queryByText("Tema efetivo atual:")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Primária")).not.toHaveAttribute("aria-describedby");
  expect(screen.getByLabelText("Fonte do Cabeçalho")).not.toHaveAttribute("aria-describedby");
  expect(await screen.findByTitle("Pré-visualização do tema")).toHaveAttribute(
    "src",
    "blob:theme-preview-1"
  );
  expect(createObjectURL).toHaveBeenCalledOnce();
  unmount();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:theme-preview-1");
});

const targetCases = [
  { apiPath: "/api/v1/themes/user", ownerName: "Meu Tema", target: "user", uuid: undefined },
  {
    apiPath: "/api/v1/themes/organizations/org-123",
    ownerName: "Acme",
    target: "organization",
    uuid: "org-123"
  },
  {
    apiPath: "/api/v1/themes/billings/billing-123",
    ownerName: "Aluguel",
    target: "billing",
    uuid: "billing-123"
  }
] as const;

it.each(targetCases)("saves the $target target through its typed API path", async ({
  apiPath,
  ownerName,
  target,
  uuid
}) => {
  const user = userEvent.setup();
  let savedBody: unknown;
  const savedTheme: ThemeResponse = {
    ...customTheme,
    effective: { ...customTheme.effective, header_font: "Roboto" },
    effective_source: target,
    owner_name: ownerName
  };
  installFetch({
    [`GET ${apiPath}`]: () => jsonResponse({ ...customTheme, owner_name: ownerName }),
    [`PUT ${apiPath}`]: (init) => {
      savedBody = JSON.parse(String(init?.body));
      return jsonResponse(savedTheme, 200, {
        "X-Rentivo-Analytics-Event": "rentivo_theme_changed",
        "X-Rentivo-Analytics-Scope": target
      });
    },
    "POST /api/v1/themes/preview": () => pdfResponse()
  });

  renderPage(
    <ThemePage target={target} targetUuid={uuid} />
  );
  await user.selectOptions(await screen.findByLabelText("Fonte do Cabeçalho"), "Roboto");
  await user.selectOptions(screen.getByLabelText("Fonte do Texto"), "Roboto");
  await user.click(screen.getByRole("button", { name: "Salvar" }));

  await waitFor(() => expect(savedBody).toEqual({
    ...customTheme.effective,
    header_font: "Roboto",
    text_font: "Roboto"
  }));
  expect(await screen.findByText(/salvo com sucesso!/)).toBeVisible();
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
  const analyticsResponse = analytics.pushAnalyticsFromResponse.mock.calls[0][0] as Response;
  expect(analyticsResponse.headers.get("X-Rentivo-Analytics-Event")).toBe("rentivo_theme_changed");
  expect(analyticsResponse.headers.get("X-Rentivo-Analytics-Scope")).toBe(target);
});

it("loads an exact organization label on a direct route", async () => {
  const fetchMock = installFetch({
    "GET /api/v1/themes/organizations/org-route": () => jsonResponse({
      ...customTheme,
      effective_source: "organization",
      owner_name: "Acme Direta"
    }),
    "POST /api/v1/themes/preview": () => pdfResponse()
  });

  renderPage(
    <ThemePage target="organization" />,
    "/workspaces/not-the-organization/themes/organization/org-route",
    "/workspaces/:workspaceId/themes/organization/:orgUuid"
  );

  expect(await screen.findByRole("heading", { name: "Acme Direta — Tema" })).toBeVisible();
  expect(document.title).toBe("Acme Direta — Tema - Rentivo");
  expect(screen.getByRole("link", { name: "Voltar" })).toHaveAttribute(
    "href",
    "/organizations/org-route"
  );
  expect(screen.queryByText("Tema efetivo atual:")).not.toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  expect(fetchMock.mock.calls.map(([input, init]) => (
    `${init?.method ?? "GET"} ${String(input)}`
  ))).toEqual([
    "GET /api/v1/themes/organizations/org-route",
    "POST /api/v1/themes/preview"
  ]);
});

it("uses inherited effective values for a billing without a stored theme", async () => {
  const fetchMock = installFetch({
    "GET /api/v1/themes/billings/billing-prop": () => jsonResponse({
      ...defaultTheme,
      effective: { ...customTheme.effective, text_font: "Roboto" },
      effective_source: "organization",
      owner_name: "Aluguel Direto"
    }),
    "POST /api/v1/themes/preview": () => pdfResponse()
  });

  renderPage(<ThemePage target="billing" targetUuid="billing-prop" />);

  expect(await screen.findByRole("heading", { name: "Aluguel Direto — Tema" })).toBeVisible();
  expect(document.title).toBe("Aluguel Direto — Tema - Rentivo");
  expect(screen.getByLabelText("Fonte do Cabeçalho")).toHaveValue("Lora");
  expect(screen.getByLabelText("Fonte do Texto")).toHaveValue("Roboto");
  const sourceBanner = screen.getByText("Tema efetivo atual:").closest("div");
  expect(sourceBanner).toHaveTextContent("da organização");
  expect(sourceBanner).toHaveStyle({
    background: "var(--paper)",
    borderLeftColor: "var(--charcoal)"
  });
  expect(screen.getByRole("link", { name: "Voltar" })).toHaveAttribute(
    "href",
    "/billings/billing-prop"
  );
  expect(screen.queryByRole("button", { name: "Usar Padrão" })).not.toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  expect(fetchMock.mock.calls.map(([input, init]) => (
    `${init?.method ?? "GET"} ${String(input)}`
  ))).toEqual([
    "GET /api/v1/themes/billings/billing-prop",
    "POST /api/v1/themes/preview"
  ]);
});

it("honors read-only capabilities while retaining preview access", async () => {
  installFetch({
    "GET /api/v1/themes/billings/read-only": () => jsonResponse({
      ...customTheme,
      capabilities: { can_edit: false, can_reset: false },
      effective_source: "billing",
      owner_name: "Aluguel"
    }),
    "POST /api/v1/themes/preview": () => pdfResponse()
  });

  renderPage(<ThemePage target="billing" targetUuid="read-only" />);

  expect(await screen.findByText("Você tem acesso somente para consulta.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Visualizar" })).toBeEnabled();
  expect(screen.getByLabelText("Fonte do Cabeçalho")).toBeDisabled();
  expect(screen.getByLabelText("Primária")).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Usar Padrão" })).not.toBeInTheDocument();
});

it("debounces changed previews, replaces object URLs, and supports a manual retry", async () => {
  let previewCalls = 0;
  installFetch({
    "GET /api/v1/themes/user": () => jsonResponse(defaultTheme),
    "POST /api/v1/themes/preview": () => {
      previewCalls += 1;
      if (previewCalls === 2) {
        return problemResponse({
          code: "preview_failed",
          detail: "Não foi possível gerar esta prévia.",
          fields: {},
          request_id: "request-id",
          status: 422,
          title: "Prévia inválida",
          type: "problem"
        });
      }
      return pdfResponse();
    }
  });
  renderPage(<ThemePage target="user" />);
  await screen.findByTitle("Pré-visualização do tema");
  await waitFor(() => expect(createObjectURL).toHaveBeenCalledOnce());

  fireEvent.change(screen.getByLabelText("Primária"), { target: { value: "#abcdef" } });
  fireEvent.change(screen.getByLabelText("Secundária"), { target: { value: "#bcdefa" } });
  await new Promise((resolve) => setTimeout(resolve, 250));
  expect(previewCalls).toBe(1);
  await waitFor(() => expect(screen.getByText("Não foi possível gerar esta prévia.")).toBeVisible());

  fireEvent.change(screen.getByLabelText("Primária"), { target: { value: "#fedcba" } });
  fireEvent.click(screen.getByRole("button", { name: "Visualizar" }));
  await waitFor(() => expect(screen.getByTitle("Pré-visualização do tema")).toHaveAttribute(
    "src",
    "blob:theme-preview-2"
  ));
  await new Promise((resolve) => setTimeout(resolve, 350));
  expect(previewCalls).toBe(3);
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:theme-preview-1");
  expect(screen.queryByText("Não foi possível gerar esta prévia.")).not.toBeInTheDocument();
});

it("keeps only the latest out-of-order preview and aborts pending work on unmount", async () => {
  const previews = [deferred<Response>(), deferred<Response>(), deferred<Response>()];
  const signals: AbortSignal[] = [];
  let previewCalls = 0;
  installFetch({
    "GET /api/v1/themes/user": () => jsonResponse(defaultTheme),
    "POST /api/v1/themes/preview": (init) => {
      signals.push(init?.signal as AbortSignal);
      return previews[previewCalls++].promise;
    }
  });
  const { unmount } = renderPage(<ThemePage target="user" />);
  await screen.findByRole("heading", { name: "Meu Tema" });
  await waitFor(() => expect(previewCalls).toBe(1));

  fireEvent.click(screen.getByRole("button", { name: "Visualizar" }));
  expect(signals[0]?.aborted).toBe(true);
  await waitFor(() => expect(previewCalls).toBe(2));
  await act(async () => {
    previews[1].resolve(pdfResponse());
  });
  expect(await screen.findByTitle("Pré-visualização do tema")).toHaveAttribute(
    "src",
    "blob:theme-preview-1"
  );

  await act(async () => {
    previews[0].resolve(pdfResponse());
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(createObjectURL).toHaveBeenCalledOnce();
  expect(screen.getByTitle("Pré-visualização do tema")).toHaveAttribute(
    "src",
    "blob:theme-preview-1"
  );

  fireEvent.click(screen.getByRole("button", { name: "Visualizar" }));
  expect(signals[1]?.aborted).toBe(true);
  await waitFor(() => expect(previewCalls).toBe(3));
  unmount();
  expect(signals[2]?.aborted).toBe(true);
  await act(async () => {
    previews[2].resolve(pdfResponse());
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(createObjectURL).toHaveBeenCalledOnce();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:theme-preview-1");
});

it("silently ignores an AbortError when a newer preview starts", async () => {
  let previewCalls = 0;
  installFetch({
    "GET /api/v1/themes/user": () => jsonResponse(defaultTheme),
    "POST /api/v1/themes/preview": (init) => {
      previewCalls += 1;
      if (previewCalls === 1) {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
        });
      }
      return pdfResponse();
    }
  });
  renderPage(<ThemePage target="user" />);
  await screen.findByRole("heading", { name: "Meu Tema" });
  await waitFor(() => expect(previewCalls).toBe(1));

  fireEvent.click(screen.getByRole("button", { name: "Visualizar" }));

  await waitFor(() => expect(screen.getByTitle("Pré-visualização do tema")).toHaveAttribute(
    "src",
    "blob:theme-preview-1"
  ));
  expect(screen.queryByText("Não foi possível gerar a pré-visualização.")).not.toBeInTheDocument();
});

it.each([
  {
    expected: "Meu Tema - Rentivo",
    ownerLabel: undefined,
    ownerName: "Meu Tema",
    target: "user",
    uuid: undefined
  },
  {
    expected: "Acme — Tema - Rentivo",
    ownerLabel: undefined,
    ownerName: "Acme",
    target: "organization",
    uuid: "org-title"
  },
  {
    expected: "Aluguel — Tema - Rentivo",
    ownerLabel: undefined,
    ownerName: "Aluguel",
    target: "billing",
    uuid: "billing-title"
  }
] as const)("sets and restores the legacy $target document title", async ({
  expected,
  ownerLabel,
  ownerName,
  target,
  uuid
}) => {
  const apiPath = target === "user"
    ? "/api/v1/themes/user"
    : target === "organization"
      ? `/api/v1/themes/organizations/${uuid}`
      : `/api/v1/themes/billings/${uuid}`;
  installFetch({
    [`GET ${apiPath}`]: () => jsonResponse({ ...defaultTheme, owner_name: ownerName }),
    "POST /api/v1/themes/preview": () => pdfResponse()
  });
  document.title = "Título anterior";
  const { unmount } = renderPage(
    <ThemePage ownerLabel={ownerLabel} target={target} targetUuid={uuid} />
  );

  await screen.findByRole("heading", {
    level: 1,
    name: target === "user" ? "Meu Tema" : target === "organization" ? "Acme — Tema" : "Aluguel — Tema"
  });
  expect(document.title).toBe(expected);
  unmount();
  expect(document.title).toBe("Título anterior");
});

it("preserves an explicit owner label over the theme owner name", async () => {
  const fetchMock = installFetch({
    "GET /api/v1/themes/organizations/org-override": () => jsonResponse({
      ...defaultTheme,
      owner_name: "Nome da API"
    }),
    "POST /api/v1/themes/preview": () => pdfResponse()
  });
  renderPage(
    <ThemePage ownerLabel="Nome injetado — Tema" target="organization" targetUuid="org-override" />
  );

  expect(await screen.findByRole("heading", { name: "Nome injetado — Tema" })).toBeVisible();
  expect(document.title).toBe("Nome injetado — Tema - Rentivo");
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it("ignores a stale theme response after route navigation", async () => {
  const oldTheme = deferred<Response>();
  const oldSignals: AbortSignal[] = [];
  installFetch({
    "GET /api/v1/themes/organizations/new-org": () => jsonResponse({
      ...defaultTheme,
      effective: { ...defaultTheme.effective, header_font: "Roboto" },
      owner_name: "Organização nova"
    }),
    "GET /api/v1/themes/organizations/old-org": (init) => {
      oldSignals.push(init?.signal as AbortSignal);
      return oldTheme.promise;
    },
    "POST /api/v1/themes/preview": () => pdfResponse()
  });
  render(
    <MemoryRouter initialEntries={["/themes/organization/old-org"]}>
      <NavigateButton to="/themes/organization/new-org" />
      <Routes>
        <Route element={<ThemePage target="organization" />} path="/themes/organization/:orgUuid" />
      </Routes>
    </MemoryRouter>
  );
  await waitFor(() => expect(oldSignals).toHaveLength(1));

  fireEvent.click(screen.getByRole("button", { name: "Navegar" }));

  expect(oldSignals.every((signal) => signal.aborted)).toBe(true);
  expect(await screen.findByRole("heading", { name: "Organização nova — Tema" })).toBeVisible();
  expect(screen.getByLabelText("Fonte do Cabeçalho")).toHaveValue("Roboto");
  await act(async () => {
    oldTheme.resolve(jsonResponse({ ...customTheme, owner_name: "Organização antiga" }));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(screen.getByRole("heading", { name: "Organização nova — Tema" })).toBeVisible();
  expect(screen.queryByText("Organização antiga — Tema")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Fonte do Cabeçalho")).toHaveValue("Roboto");
});

it("cancels pending preview and debounce work when the target changes", async () => {
  const firstPreview = deferred<Response>();
  const previewSignals: AbortSignal[] = [];
  let previewCalls = 0;
  installFetch({
    "GET /api/v1/themes/organizations/org-a": () => jsonResponse({
      ...defaultTheme,
      owner_name: "Organização A"
    }),
    "GET /api/v1/themes/organizations/org-b": () => jsonResponse({
      ...defaultTheme,
      effective: { ...defaultTheme.effective, primary: "#112233" },
      owner_name: "Organização B"
    }),
    "POST /api/v1/themes/preview": (init) => {
      previewSignals.push(init?.signal as AbortSignal);
      previewCalls += 1;
      return previewCalls === 1 ? firstPreview.promise : pdfResponse();
    }
  });
  render(
    <MemoryRouter initialEntries={["/themes/organization/org-a"]}>
      <NavigateButton to="/themes/organization/org-b" />
      <Routes>
        <Route element={<ThemePage target="organization" />} path="/themes/organization/:orgUuid" />
      </Routes>
    </MemoryRouter>
  );
  await screen.findByRole("heading", { name: "Organização A — Tema" });
  await waitFor(() => expect(previewCalls).toBe(1));
  fireEvent.change(screen.getByLabelText("Primária"), { target: { value: "#abcdef" } });

  fireEvent.click(screen.getByRole("button", { name: "Navegar" }));

  expect(previewSignals[0]?.aborted).toBe(true);
  expect(await screen.findByRole("heading", { name: "Organização B — Tema" })).toBeVisible();
  await waitFor(() => expect(previewCalls).toBe(2));
  await new Promise((resolve) => setTimeout(resolve, 350));
  expect(previewCalls).toBe(2);
  expect(screen.getByLabelText("Primária")).toHaveValue("#112233");
});

it("aborts a stale save success and keeps the new organization target usable", async () => {
  const user = userEvent.setup();
  const oldSave = deferred<Response>();
  const saveSignals: AbortSignal[] = [];
  installFetch({
    "GET /api/v1/themes/organizations/org-a": () => jsonResponse({
      ...defaultTheme,
      owner_name: "Organização A"
    }),
    "GET /api/v1/themes/organizations/org-b": () => jsonResponse({
      ...defaultTheme,
      effective: { ...defaultTheme.effective, primary: "#112233" },
      owner_name: "Organização B"
    }),
    "POST /api/v1/themes/preview": () => pdfResponse(),
    "PUT /api/v1/themes/organizations/org-a": (init) => {
      saveSignals.push(init?.signal as AbortSignal);
      return oldSave.promise;
    },
    "PUT /api/v1/themes/organizations/org-b": () => jsonResponse({
      ...customTheme,
      effective_source: "organization",
      owner_name: "Organização B"
    }, 200, {
      "X-Rentivo-Analytics-Event": "rentivo_theme_changed"
    })
  });
  renderStrictThemeRoutes(
    "/themes/organization/org-a",
    "/themes/organization/org-b"
  );
  await screen.findByRole("heading", { name: "Organização A — Tema" });

  await user.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(saveSignals).toHaveLength(1));
  expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Navegar" }));

  expect(saveSignals[0].aborted).toBe(true);
  expect(await screen.findByRole("heading", { name: "Organização B — Tema" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Salvar" })).toBeEnabled();
  await act(async () => {
    oldSave.resolve(jsonResponse({
      ...customTheme,
      effective_source: "organization",
      owner_name: "Organização A salva"
    }, 200, {
      "X-Rentivo-Analytics-Event": "stale_theme_changed"
    }));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(screen.getByRole("heading", { name: "Organização B — Tema" })).toBeVisible();
  expect(screen.getByLabelText("Primária")).toHaveValue("#112233");
  expect(screen.queryByText("Tema da organização salvo com sucesso!")).not.toBeInTheDocument();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();

  await user.click(screen.getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("Tema da organização salvo com sucesso!")).toBeVisible();
  expect(analytics.pushAnalyticsFromResponse).toHaveBeenCalledOnce();
});

it("aborts and suppresses a stale save failure after changing target types", async () => {
  const user = userEvent.setup();
  const oldSave = deferred<Response>();
  let saveSignal: AbortSignal | undefined;
  installFetch({
    "GET /api/v1/themes/billings/billing-a": () => jsonResponse({
      ...defaultTheme,
      owner_name: "Cobrança A"
    }),
    "GET /api/v1/themes/user": () => jsonResponse(defaultTheme),
    "POST /api/v1/themes/preview": () => pdfResponse(),
    "PUT /api/v1/themes/billings/billing-a": (init) => {
      saveSignal = init?.signal as AbortSignal;
      return oldSave.promise;
    }
  });
  renderStrictThemeRoutes("/themes/billing/billing-a", "/themes/user");
  await screen.findByRole("heading", { name: "Cobrança A — Tema" });
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(saveSignal).toBeDefined());

  await user.click(screen.getByRole("button", { name: "Navegar" }));

  expect(saveSignal?.aborted).toBe(true);
  expect(await screen.findByRole("heading", { name: "Meu Tema" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Salvar" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Navegar" })).toHaveFocus();
  await act(async () => {
    oldSave.resolve(problemResponse({
      code: "validation_error",
      detail: "Falha antiga.",
      fields: { "body.primary": "Cor antiga inválida." },
      request_id: "old-request",
      status: 422,
      title: "Tema antigo inválido",
      type: "problem"
    }));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(screen.queryByText("Falha antiga.")).not.toBeInTheDocument();
  expect(screen.queryByText("Cor antiga inválida.")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Meu Tema" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Navegar" })).toHaveFocus();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("aborts a stale reset success without reloading the previous target", async () => {
  const user = userEvent.setup();
  const oldReset = deferred<Response>();
  let oldGetCalls = 0;
  let resetSignal: AbortSignal | undefined;
  installFetch({
    "DELETE /api/v1/themes/organizations/org-a": (init) => {
      resetSignal = init?.signal as AbortSignal;
      return oldReset.promise;
    },
    "GET /api/v1/themes/billings/billing-b": () => jsonResponse({
      ...customTheme,
      effective_source: "billing",
      owner_name: "Cobrança B"
    }),
    "GET /api/v1/themes/organizations/org-a": () => {
      oldGetCalls += 1;
      return jsonResponse({ ...customTheme, owner_name: "Organização A" });
    },
    "POST /api/v1/themes/preview": () => pdfResponse()
  });
  renderStrictThemeRoutes(
    "/themes/organization/org-a",
    "/themes/billing/billing-b"
  );
  await user.click(await screen.findByRole("button", { name: "Usar Padrão" }));
  await user.click(screen.getByRole("button", { name: "Usar padrão" }));
  await waitFor(() => expect(resetSignal).toBeDefined());
  expect(screen.getByRole("button", { name: "Usar Padrão" })).toBeDisabled();

  await user.click(screen.getByRole("button", { name: "Navegar" }));

  expect(resetSignal?.aborted).toBe(true);
  expect(await screen.findByRole("heading", { name: "Cobrança B — Tema" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Usar Padrão" })).toBeEnabled();
  const settledOldGetCalls = oldGetCalls;
  await act(async () => {
    oldReset.resolve(new Response(null, { status: 204 }));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(oldGetCalls).toBe(settledOldGetCalls);
  expect(screen.getByRole("heading", { name: "Cobrança B — Tema" })).toBeVisible();
  expect(screen.queryByText("Tema da organização redefinido para o padrão.")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Navegar" })).toHaveFocus();
});

it("aborts and suppresses a stale reset failure after changing targets", async () => {
  const user = userEvent.setup();
  const oldReset = deferred<Response>();
  let resetSignal: AbortSignal | undefined;
  installFetch({
    "DELETE /api/v1/themes/billings/billing-a": (init) => {
      resetSignal = init?.signal as AbortSignal;
      return oldReset.promise;
    },
    "GET /api/v1/themes/billings/billing-a": () => jsonResponse({
      ...customTheme,
      effective_source: "billing",
      owner_name: "Cobrança A"
    }),
    "GET /api/v1/themes/organizations/org-b": () => jsonResponse({
      ...customTheme,
      effective_source: "organization",
      owner_name: "Organização B"
    }),
    "POST /api/v1/themes/preview": () => pdfResponse()
  });
  renderStrictThemeRoutes(
    "/themes/billing/billing-a",
    "/themes/organization/org-b"
  );
  await user.click(await screen.findByRole("button", { name: "Usar Padrão" }));
  await user.click(screen.getByRole("button", { name: "Usar padrão" }));
  await waitFor(() => expect(resetSignal).toBeDefined());

  await user.click(screen.getByRole("button", { name: "Navegar" }));

  expect(resetSignal?.aborted).toBe(true);
  expect(await screen.findByRole("heading", { name: "Organização B — Tema" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Usar Padrão" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Navegar" })).toHaveFocus();
  await act(async () => {
    oldReset.resolve(problemResponse({
      code: "reset_failed",
      detail: "Falha antiga ao restaurar.",
      fields: {},
      request_id: "old-reset",
      status: 409,
      title: "Falha antiga",
      type: "problem"
    }));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(screen.queryByText("Falha antiga ao restaurar.")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Organização B — Tema" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Navegar" })).toHaveFocus();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("clears a stale custom theme when the reset refresh fails", async () => {
  const user = userEvent.setup();
  let getCalls = 0;
  installFetch({
    "DELETE /api/v1/themes/user": () => new Response(null, { status: 204 }),
    "GET /api/v1/themes/user": () => {
      getCalls += 1;
      if (getCalls === 1) {
        return jsonResponse(customTheme);
      }
      throw new Error("offline");
    },
    "POST /api/v1/themes/preview": () => pdfResponse()
  });
  renderPage(<ThemePage target="user" />);
  await user.click(await screen.findByRole("button", { name: "Usar Padrão" }));
  await user.click(screen.getByRole("button", { name: "Usar padrão" }));

  expect(await screen.findByText("Não foi possível carregar o tema.")).toBeVisible();
  expect(screen.queryByRole("heading", { name: "Meu Tema" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Fonte do Cabeçalho")).not.toBeInTheDocument();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("aborts a pending theme GET and ignores its result after unmount", async () => {
  const pendingTheme = deferred<Response>();
  let loadSignal: AbortSignal | undefined;
  installFetch({
    "GET /api/v1/themes/user": (init) => {
      loadSignal = init?.signal as AbortSignal;
      return pendingTheme.promise;
    }
  });
  const { unmount } = renderPage(<ThemePage target="user" />);
  await waitFor(() => expect(loadSignal).toBeDefined());

  unmount();

  expect(loadSignal?.aborted).toBe(true);
  await act(async () => {
    pendingTheme.resolve(jsonResponse(defaultTheme));
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(screen.queryByRole("heading", { name: "Meu Tema" })).not.toBeInTheDocument();
  expect(createObjectURL).not.toHaveBeenCalled();
});

it("submits the theme with Enter from the focused save control", async () => {
  const user = userEvent.setup();
  let putCalls = 0;
  installFetch({
    "GET /api/v1/themes/user": () => jsonResponse(defaultTheme),
    "POST /api/v1/themes/preview": () => pdfResponse(),
    "PUT /api/v1/themes/user": () => {
      putCalls += 1;
      return jsonResponse(customTheme, 200, {
        "X-Rentivo-Analytics-Event": "rentivo_theme_changed",
        "X-Rentivo-Analytics-Scope": "user"
      });
    }
  });
  renderPage(<ThemePage target="user" />);
  const saveButton = await screen.findByRole("button", { name: "Salvar" });
  saveButton.focus();

  await user.keyboard("{Enter}");

  await waitFor(() => expect(putCalls).toBe(1));
  expect(await screen.findByText("Tema salvo com sucesso!")).toBeVisible();
});

it("closes reset confirmation with Escape and restores focus to its trigger", async () => {
  const user = userEvent.setup();
  installFetch({
    "GET /api/v1/themes/user": () => jsonResponse(customTheme),
    "POST /api/v1/themes/preview": () => pdfResponse()
  });
  renderPage(<ThemePage target="user" />);
  const resetButton = await screen.findByRole("button", { name: "Usar Padrão" });
  await user.click(resetButton);
  expect(screen.getByRole("dialog", { name: "Restaurar o tema padrão?" })).toBeVisible();

  await user.keyboard("{Escape}");

  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(resetButton).toHaveFocus();
});

it.each(targetCases)("resets and refetches the $target target", async ({
  apiPath,
  ownerName,
  target,
  uuid
}) => {
  const user = userEvent.setup();
  let getCalls = 0;
  installFetch({
    [`DELETE ${apiPath}`]: () => new Response(null, { status: 204 }),
    [`GET ${apiPath}`]: () => jsonResponse({
      ...(++getCalls === 1 ? customTheme : defaultTheme),
      owner_name: ownerName
    }),
    "POST /api/v1/themes/preview": () => pdfResponse()
  });

  renderPage(
    <ThemePage target={target} targetUuid={uuid} />
  );
  await user.click(await screen.findByRole("button", { name: "Usar Padrão" }));
  expect(screen.getByRole("dialog", { name: "Restaurar o tema padrão?" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Usar padrão" }));

  expect(await screen.findByText(/redefinido para o padrão\./)).toBeVisible();
  expect(getCalls).toBe(2);
  if (target === "billing") {
    expect(screen.getByText("padrão do sistema")).toBeVisible();
  }
  expect(screen.queryByRole("button", { name: "Usar Padrão" })).not.toBeInTheDocument();
  expect(analytics.pushAnalyticsFromResponse).not.toHaveBeenCalled();
});

it("maps API field errors and reports an unexpected save failure", async () => {
  const user = userEvent.setup();
  let saveCalls = 0;
  installFetch({
    "GET /api/v1/themes/user": () => jsonResponse(defaultTheme),
    "POST /api/v1/themes/preview": () => pdfResponse(),
    "PUT /api/v1/themes/user": () => {
      saveCalls += 1;
      if (saveCalls === 1) {
        return problemResponse({
          code: "validation_error",
          detail: "Revise as cores informadas.",
          fields: {
            "body.header_font": "Fonte inválida.",
            "body.primary": "Cor inválida."
          },
          request_id: "request-id",
          status: 422,
          title: "Dados inválidos",
          type: "problem"
        });
      }
      throw new Error("offline");
    }
  });
  renderPage(<ThemePage target="user" />);

  await user.click(await screen.findByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("Revise as cores informadas.")).toBeVisible();
  expect(screen.getByText("Cor inválida.")).toBeVisible();
  expect(screen.getByText("Fonte inválida.")).toBeVisible();
  expect(screen.getByLabelText("Primária")).toHaveAttribute("aria-describedby", "primary-error");
  expect(screen.getByLabelText("Fonte do Cabeçalho")).toHaveAttribute(
    "aria-describedby",
    "header_font-error"
  );
  fireEvent.change(screen.getByLabelText("Primária"), { target: { value: "#abcdef" } });
  expect(screen.queryByText("Cor inválida.")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Primária")).not.toHaveAttribute("aria-describedby");
  expect(screen.getByLabelText("Fonte do Cabeçalho")).toHaveAttribute(
    "aria-describedby",
    "header_font-error"
  );
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("Não foi possível salvar o tema.")).toBeVisible();
});

it("keeps a custom theme available when reset fails", async () => {
  const user = userEvent.setup();
  installFetch({
    "DELETE /api/v1/themes/user": () => {
      throw new Error("offline");
    },
    "GET /api/v1/themes/user": () => jsonResponse(customTheme),
    "POST /api/v1/themes/preview": () => pdfResponse()
  });
  renderPage(<ThemePage target="user" />);

  await user.click(await screen.findByRole("button", { name: "Usar Padrão" }));
  await user.click(screen.getByRole("button", { name: "Usar padrão" }));

  expect(await screen.findByText("Não foi possível restaurar o tema padrão.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Usar Padrão" })).toBeEnabled();
});

it("retries a failed theme load", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  installFetch({
    "GET /api/v1/themes/user": () => {
      attempts += 1;
      if (attempts === 1) {
        throw new Error("offline");
      }
      return jsonResponse(defaultTheme);
    },
    "POST /api/v1/themes/preview": () => pdfResponse()
  });
  renderPage(<ThemePage target="user" />);

  expect(await screen.findByText("Não foi possível carregar o tema.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Tentar novamente" }));
  expect(await screen.findByRole("heading", { name: "Meu Tema" })).toBeVisible();
  expect(attempts).toBe(2);
});

it("reports a missing organization route parameter without making an API request", async () => {
  const fetchMock = installFetch({});
  renderPage(<ThemePage target="organization" />, "/themes/organization", "/themes/organization");

  expect(await screen.findByText("Não foi possível identificar a organização.")).toBeVisible();
  expect(fetchMock).not.toHaveBeenCalled();
});
