import { useEffect } from "react";

type MetadataDefinition = {
  attributes: Record<string, string>;
  selector: string;
  tagName: "link" | "meta" | "script";
  textContent?: string;
};

const publicUrl = import.meta.env.VITE_PUBLIC_APP_URL?.replace(/\/$/, "") ?? "";
const landingUrl = `${publicUrl}/`;
const ogImageUrl = `${publicUrl}/og-cover.svg`;

const metadata: MetadataDefinition[] = [
  { attributes: { content: "Rentivo é uma plataforma gratuita e de código aberto para gestão de cobranças de aluguéis e imóveis. Gere faturas em PDF com QR Code PIX, organize equipes e acompanhe pagamentos.", name: "description" }, selector: 'meta[name="description"]', tagName: "meta" },
  { attributes: { content: "gestão de aluguel, cobrança imóvel, fatura PIX, QR Code PIX, cobrança de aluguel, gestão imobiliária", name: "keywords" }, selector: 'meta[name="keywords"]', tagName: "meta" },
  { attributes: { content: "Rentivo", name: "author" }, selector: 'meta[name="author"]', tagName: "meta" },
  { attributes: { content: "index, follow", name: "robots" }, selector: 'meta[name="robots"]', tagName: "meta" },
  { attributes: { href: landingUrl, rel: "canonical" }, selector: 'link[rel="canonical"]', tagName: "link" },
  { attributes: { href: landingUrl, hreflang: "pt-BR", rel: "alternate" }, selector: 'link[rel="alternate"][hreflang="pt-BR"]', tagName: "link" },
  { attributes: { content: "website", property: "og:type" }, selector: 'meta[property="og:type"]', tagName: "meta" },
  { attributes: { content: "Rentivo", property: "og:site_name" }, selector: 'meta[property="og:site_name"]', tagName: "meta" },
  { attributes: { content: "Rentivo — Gestão de cobranças para imóveis", property: "og:title" }, selector: 'meta[property="og:title"]', tagName: "meta" },
  { attributes: { content: "Crie cobranças, gere faturas em PDF com QR Code PIX e gerencie pagamentos de aluguéis — gratuito e open source.", property: "og:description" }, selector: 'meta[property="og:description"]', tagName: "meta" },
  { attributes: { content: landingUrl, property: "og:url" }, selector: 'meta[property="og:url"]', tagName: "meta" },
  { attributes: { content: "pt_BR", property: "og:locale" }, selector: 'meta[property="og:locale"]', tagName: "meta" },
  { attributes: { content: ogImageUrl, property: "og:image" }, selector: 'meta[property="og:image"]', tagName: "meta" },
  { attributes: { content: "summary_large_image", name: "twitter:card" }, selector: 'meta[name="twitter:card"]', tagName: "meta" },
  { attributes: { content: "Rentivo — Gestão de cobranças para imóveis", name: "twitter:title" }, selector: 'meta[name="twitter:title"]', tagName: "meta" },
  { attributes: { content: "Crie cobranças, gere faturas em PDF com QR Code PIX e gerencie pagamentos de aluguéis — gratuito e open source.", name: "twitter:description" }, selector: 'meta[name="twitter:description"]', tagName: "meta" },
  { attributes: { content: ogImageUrl, name: "twitter:image" }, selector: 'meta[name="twitter:image"]', tagName: "meta" },
  {
    attributes: { type: "application/ld+json" },
    selector: 'script[type="application/ld+json"]',
    tagName: "script",
    textContent: JSON.stringify({
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      applicationCategory: "BusinessApplication",
      description: "Gestão de cobranças para imóveis com geração de faturas em PDF e QR Code PIX.",
      inLanguage: "pt-BR",
      name: "Rentivo",
      offers: { "@type": "Offer", price: "0", priceCurrency: "BRL" },
      operatingSystem: "Web",
      url: landingUrl
    })
  }
];

export function LandingMetadata() {
  useEffect(() => {
    const originalTitle = document.title;
    const restoredElements: Array<{ created: boolean; element: HTMLElement; original?: HTMLElement }> = [];

    document.title = "Rentivo — Gestão de cobranças para imóveis com PIX";
    metadata.forEach(({ attributes, selector, tagName, textContent }) => {
      const existing = document.head.querySelector<HTMLElement>(selector);
      const element = existing ?? document.createElement(tagName);
      const original = existing?.cloneNode(true) as HTMLElement | undefined;
      if (!existing) {
        document.head.append(element);
      }
      Object.entries(attributes).forEach(([name, value]) => element.setAttribute(name, value));
      if (tagName === "script") {
        element.dataset.rentivoLanding = "true";
      }
      if (textContent !== undefined) {
        element.textContent = textContent;
      }
      restoredElements.push({ created: !existing, element, original });
    });

    return () => {
      document.title = originalTitle;
      restoredElements.forEach(({ created, element, original }) => {
        if (created) {
          element.remove();
        } else if (original) {
          element.replaceWith(original);
        }
      });
    };
  }, []);

  return null;
}
