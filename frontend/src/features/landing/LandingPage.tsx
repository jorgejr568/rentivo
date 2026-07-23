import {
  ClipboardList,
  FileText,
  Github,
  Paperclip,
  QrCode,
  ShieldCheck,
  UsersRound
} from "lucide-react";

import { LandingMetadata } from "./LandingMetadata";

function PixelQr({ compact = false }: { compact?: boolean }) {
  return (
    <svg aria-hidden="true" fill="var(--ink)" height={compact ? 84 : 120} viewBox="0 0 80 80" width={compact ? 84 : 120}>
      <rect height="24" rx="2" width="24" x="4" y="4" /><rect fill="var(--surface)" height="18" rx="1" width="18" x="7" y="7" /><rect height="10" rx="1" width="10" x="11" y="11" />
      <rect height="24" rx="2" width="24" x="52" y="4" /><rect fill="var(--surface)" height="18" rx="1" width="18" x="55" y="7" /><rect height="10" rx="1" width="10" x="59" y="11" />
      <rect height="24" rx="2" width="24" x="4" y="52" /><rect fill="var(--surface)" height="18" rx="1" width="18" x="7" y="55" /><rect height="10" rx="1" width="10" x="11" y="59" />
      <rect height="5" width="5" x="32" y="8" /><rect height="5" width="5" x="40" y="8" /><rect height="5" width="5" x="32" y="16" /><rect height="5" width="5" x="44" y="16" />
      <rect height="5" width="5" x="8" y="32" /><rect height="5" width="5" x="16" y="32" /><rect height="5" width="5" x="32" y="32" /><rect height="5" width="5" x="40" y="36" />
      <rect height="5" width="5" x="8" y="40" /><rect height="5" width="5" x="24" y="40" /><rect height="5" width="5" x="52" y="32" /><rect height="5" width="5" x="64" y="32" />
      <rect height="5" width="5" x="36" y="44" /><rect height="5" width="5" x="48" y="44" /><rect height="5" width="5" x="52" y="52" /><rect height="5" width="5" x="64" y="56" />
      <rect height="5" width="5" x="36" y="56" /><rect height="5" width="5" x="48" y="60" /><rect height="5" width="5" x="56" y="64" /><rect height="5" width="5" x="68" y="68" /><rect height="5" width="5" x="36" y="68" />
    </svg>
  );
}

const featureCards = [
  [ClipboardList, "Cobranças flexíveis", "Itens fixos (aluguel, condomínio) e variáveis (água, luz). Monte uma vez, reutilize todo mês.", false],
  [FileText, "Faturas em PDF", "PDF profissional com itens detalhados, vencimento e total formatado em R$.", true],
  [QrCode, "PIX com QR Code", "QR Code PIX gerado no padrão EMV do Banco Central. O inquilino paga em segundos.", false],
  [UsersRound, "Organizações", "Gerencie imóveis em equipe com cargos e permissões — admin, gestor, visualizador.", false],
  [Paperclip, "Comprovantes", "Anexe comprovantes (PDF, JPG, PNG). Eles entram mesclados no PDF final da fatura.", true],
  [ShieldCheck, "Registro de auditoria", "Cada ação fica registrada com data, autor e estado anterior. Rastreabilidade total.", false]
] as const;

export function LandingPage() {
  return (
    <>
      <LandingMetadata />
      <nav className="topbar">
        <div className="wrapper">
          <a className="topbar-brand" href="/"><span className="brand__mark">R</span><span>rent<em>ivo</em></span></a>
          <div className="topbar-menu">
            <a className="topbar-link" href="/login">Entrar</a>
            <a className="btn btn--primary btn--sm" href="/signup">Criar conta</a>
          </div>
        </div>
      </nav>
      <main>
        <section className="hero">
          <div className="wrapper hero__inner">
            <div>
              <span className="eyebrow"><span className="dot" />100% gratuito · open source</span>
              <h1 className="hero__title">Cobranças de aluguel,<br />com <span className="hl">PIX em segundos</span></h1>
              <p className="hero__sub">Monte a cobrança uma vez, gere a fatura todo mês em PDF com QR Code PIX e acompanhe quem pagou — sem planilha, sem dor de cabeça.</p>
              <div className="hero__cta"><a className="btn btn--primary btn--lg" href="/signup">Começar agora</a><a className="btn btn--lg" href="/login">Já tenho conta</a></div>
              <div className="hero__note"><span className="dot" />Sem cartão de crédito · seus dados ficam com você</div>
            </div>
            <div className="hero__visual" aria-hidden="true">
              <div className="hcard hcard--invoice">
                <div className="hcard__top"><div><div className="hcard__eyebrow">Fatura · Apt 302</div><div className="hcard__month">Maio 2026</div></div><span className="tag tag--pending"><span className="dot" />Pendente</span></div>
                <div className="hrow"><span>Aluguel</span><span>R$ 2.500,00</span></div><div className="hrow"><span>Condomínio</span><span>R$ 680,00</span></div><div className="hrow"><span>Água</span><span>R$ 87,00</span></div><div className="hrow"><span>Energia elétrica</span><span>R$ 250,00</span></div><div className="hrow hrow--total"><span>Total</span><span>R$ 3.517,00</span></div>
              </div>
              <div className="hcard hcard--qr"><PixelQr /><div className="hcard__qrlabel">PAGAR COM PIX</div></div>
              <div className="hcard hcard--status"><span className="tag tag--paid"><span className="dot" />Pago</span><span className="tag tag--pending"><span className="dot" />Pendente</span><span className="tag tag--overdue"><span className="dot" />Atrasado</span><span className="tag tag--sent"><span className="dot" />Enviado</span></div>
            </div>
          </div>
        </section>
        <div className="trust"><div className="wrapper trust__inner"><span className="trust__item"><ShieldCheck aria-hidden="true" size={18} />Padrão EMV · Banco Central</span><span className="trust__item"><span className="mono">PDF</span> Faturas profissionais</span><span className="trust__item"><span className="mono">BRL</span> Valores em centavos, sem erro</span><span className="trust__item"><Github aria-hidden="true" size={18} />Código aberto · GPL-3.0</span></div></div>
        <section className="features" id="features"><div className="wrapper"><div className="sec-head"><div className="sec-head__eyebrow">Recursos</div><h2 className="sec-head__title">Tudo que um locador precisa</h2><p className="sec-head__sub">Do modelo de cobrança ao comprovante de pagamento, num fluxo só.</p></div><div className="features__grid">
          {featureCards.map(([Icon, heading, copy, accented]) => <div className={`fcard${accented ? " fcard--accent" : ""}`} key={heading}><div className="fcard__icon"><Icon aria-hidden="true" size={22} /></div><h3>{heading}</h3><p>{copy}</p></div>)}
        </div></div></section>
        <section className="steps-sec"><div className="wrapper"><div className="sec-head"><div className="sec-head__eyebrow">Como funciona</div><h2 className="sec-head__title">Três passos por mês</h2></div><div className="steps">
          <div className="step"><div className="step__n">1</div><h3>Crie a cobrança</h3><p>Defina os itens fixos e variáveis e configure sua chave PIX uma única vez.</p></div>
          <div className="step"><div className="step__n">2</div><h3>Gere a fatura</h3><p>Preencha os valores do mês, defina o vencimento e o PDF com QR Code sai pronto.</p></div>
          <div className="step"><div className="step__n">3</div><h3>Envie e acompanhe</h3><p>Compartilhe, marque como pago, anexe o comprovante e mantenha o histórico.</p></div>
        </div></div></section>
        <section className="showcase"><div className="wrapper">
          <div className="show-row"><div className="show-vis"><div className="panel"><div className="panel__head"><h4>Status dos pagamentos</h4><span className="panel__title-eyebrow">Maio</span></div><div className="panel__body" style={{ paddingBottom: "0.5rem", paddingTop: "0.5rem" }}><div className="between" style={{ borderBottom: "1.5px solid var(--line)", padding: "0.6rem 0" }}><span style={{ fontSize: "0.9rem", fontWeight: 600 }}>Apartamento 302</span><span className="tag tag--pending"><span className="dot" />Pendente</span></div><div className="between" style={{ borderBottom: "1.5px solid var(--line)", padding: "0.6rem 0" }}><span style={{ fontSize: "0.9rem", fontWeight: 600 }}>Casa Acácias 47</span><span className="tag tag--overdue"><span className="dot" />Atrasado</span></div><div className="between" style={{ padding: "0.6rem 0" }}><span style={{ fontSize: "0.9rem", fontWeight: 600 }}>Kitnet Centro</span><span className="tag tag--paid"><span className="dot" />Pago</span></div></div></div></div><div className="show-text"><h2>Você sempre sabe quem pagou</h2><p>Acompanhe o status de cada fatura em tempo real. Marque pagamentos com um clique e identifique atrasos antes que virem problema.</p><ul className="checklist"><li>Status claro: pago, pendente, enviado, atrasado</li><li>Histórico mês a mês por imóvel</li><li>Painel com total a receber, recebido e em atraso</li></ul></div></div>
          <div className="show-row show-row--rev"><div className="show-vis"><div className="panel"><div className="panel__head"><h4>Fatura gerada</h4><span className="tag tag--solid">PDF</span></div><div className="panel__body flex gap" style={{ alignItems: "center" }}><PixelQr compact /><div><div className="mono" style={{ color: "var(--muted)", fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase" }}>Total a pagar</div><div style={{ fontFamily: "var(--font-display)", fontSize: "1.7rem", fontWeight: 700 }}>R$ 3.517,00</div><div className="muted" style={{ fontSize: "0.82rem" }}>Vencimento 10/05/2026</div></div></div></div></div><div className="show-text"><h2>Um PDF que parece de banco</h2><p>Faturas com layout limpo, itens detalhados e QR Code PIX embutido. O inquilino abre, lê o valor e paga sem digitar nada.</p><ul className="checklist"><li>QR Code PIX no padrão oficial EMV</li><li>Comprovantes mesclados ao PDF final</li><li>Armazenamento local ou em S3</li></ul></div></div>
        </div></section>
        <section className="cta-sec"><div className="wrapper"><div className="cta"><h2>Comece a cobrar melhor hoje</h2><p>Sem cartão, sem limite, sem pegadinha. O Rentivo é 100% gratuito e de código aberto.</p><div className="btn-row"><a className="btn btn--primary btn--lg" href="/signup">Criar conta gratuita</a><a className="btn btn--lg btn--ink" href="https://github.com/jorgejr568/rentivo" rel="noopener" target="_blank"><Github aria-hidden="true" size={18} />GitHub</a></div></div></div></section>
      </main>
      <footer className="foot"><div className="wrapper foot__inner"><div><a className="topbar-brand" href="/" style={{ color: "var(--ink)" }}><span className="brand__mark">R</span><span style={{ color: "var(--ink)" }}>rent<em>ivo</em></span></a><p className="muted" style={{ fontSize: "0.85rem", margin: "0.5rem 0 0" }}>Gestão de cobranças para imóveis.<br />Gratuito e de código aberto.</p></div><div className="foot__links"><a href="/login">Entrar</a><a href="/signup">Criar conta</a><a href="/privacy">Privacidade</a><a href="/terms">Termos</a><a href="https://github.com/jorgejr568/rentivo" rel="noopener" target="_blank">GitHub</a></div></div></footer>
    </>
  );
}
