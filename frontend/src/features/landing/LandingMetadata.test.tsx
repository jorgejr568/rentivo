import { render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

async function renderMetadata(publicUrl?: string) {
  vi.resetModules();
  vi.stubEnv("VITE_PUBLIC_APP_URL", publicUrl);
  const { LandingMetadata } = await import("./LandingMetadata");
  return render(<LandingMetadata />);
}

afterEach(() => {
  vi.unstubAllEnvs();
  document.head.innerHTML = "";
  document.title = "";
});

it("publishes configured canonical, social, and structured landing URLs", async () => {
  await renderMetadata("https://public.rentivo.test/");

  expect(document.title).toBe("Rentivo — Gestão de cobranças para imóveis com PIX");
  expect(document.head.querySelector('link[rel="canonical"]')).toHaveAttribute(
    "href",
    "https://public.rentivo.test/"
  );
  expect(document.head.querySelector('meta[property="og:image"]')).toHaveAttribute(
    "content",
    "https://public.rentivo.test/og-cover.svg"
  );
  expect(document.head.querySelector('meta[name="twitter:card"]')).toHaveAttribute(
    "content",
    "summary_large_image"
  );
  expect(
    JSON.parse(document.head.querySelector('script[type="application/ld+json"]')!.textContent!)
  ).toMatchObject({
    "@type": "SoftwareApplication",
    name: "Rentivo",
    offers: { price: "0", priceCurrency: "BRL" },
    url: "https://public.rentivo.test/"
  });
});

it("falls back to window.location.origin when the public URL is unset", async () => {
  await renderMetadata();

  const canonical = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  expect(canonical).toHaveAttribute("href", "/");
  expect(canonical?.href).toBe(`${window.location.origin}/`);
  expect(document.head.querySelector('meta[property="og:image"]')).toHaveAttribute(
    "content",
    "/og-cover.svg"
  );
  expect(
    JSON.parse(document.head.querySelector('script[type="application/ld+json"]')!.textContent!)
  ).toMatchObject({ url: "/" });
});

it("restores replaced document metadata when unmounted", async () => {
  document.title = "Página existente";
  const canonical = document.createElement("link");
  canonical.rel = "canonical";
  canonical.href = "/existente";
  document.head.append(canonical);

  const view = await renderMetadata();
  view.unmount();

  expect(document.title).toBe("Página existente");
  expect(document.head.querySelector('link[rel="canonical"]')).toHaveAttribute("href", "/existente");
});

it("replaces the fallback structured data without duplicating it", async () => {
  document.head.innerHTML = '<script type="application/ld+json">{"name":"Fallback"}</script>';

  const view = await renderMetadata();

  expect(document.head.querySelectorAll('script[type="application/ld+json"]')).toHaveLength(1);
  expect(
    JSON.parse(document.head.querySelector('script[type="application/ld+json"]')!.textContent!)
  ).toMatchObject({ name: "Rentivo" });

  view.unmount();

  expect(document.head.querySelector('script[type="application/ld+json"]')).toHaveTextContent(
    '{"name":"Fallback"}'
  );
});
