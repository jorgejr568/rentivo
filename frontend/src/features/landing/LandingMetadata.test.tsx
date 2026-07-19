import { render } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { LandingMetadata } from "./LandingMetadata";

afterEach(() => {
  document.head.innerHTML = "";
  document.title = "";
});

it("publishes canonical, social, and structured landing metadata", () => {
  render(<LandingMetadata />);

  expect(document.title).toBe("Rentivo — Gestão de cobranças para imóveis com PIX");
  expect(document.head.querySelector('link[rel="canonical"]')).toHaveAttribute("href", "/");
  expect(document.head.querySelector('meta[property="og:image"]')).toHaveAttribute(
    "content",
    "/og-cover.svg"
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
    offers: { price: "0", priceCurrency: "BRL" }
  });
});

it("restores replaced document metadata when unmounted", () => {
  document.title = "Página existente";
  const canonical = document.createElement("link");
  canonical.rel = "canonical";
  canonical.href = "/existente";
  document.head.append(canonical);

  const view = render(<LandingMetadata />);
  view.unmount();

  expect(document.title).toBe("Página existente");
  expect(document.head.querySelector('link[rel="canonical"]')).toHaveAttribute("href", "/existente");
});

it("replaces the fallback structured data without duplicating it", () => {
  document.head.innerHTML = '<script type="application/ld+json">{"name":"Fallback"}</script>';

  const view = render(<LandingMetadata />);

  expect(document.head.querySelectorAll('script[type="application/ld+json"]')).toHaveLength(1);
  expect(
    JSON.parse(document.head.querySelector('script[type="application/ld+json"]')!.textContent!)
  ).toMatchObject({ name: "Rentivo" });

  view.unmount();

  expect(document.head.querySelector('script[type="application/ld+json"]')).toHaveTextContent(
    '{"name":"Fallback"}'
  );
});
