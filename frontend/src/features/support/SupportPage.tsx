import { useEffect } from "react";
import { Link } from "react-router-dom";

export function SupportPage() {
  useEffect(() => {
    document.title = "Suporte - Rentivo";
  }, []);

  return (
    <article className="panel">
      <div className="panel-head">
        <h2 className="page-title">Suporte</h2>
      </div>
      <div className="panel-body">
        <p>
          Precisa de ajuda com o Rentivo? Fale com a gente pelo e-mail{" "}
          <a href="mailto:suporte@rentivo.com.br">suporte@rentivo.com.br</a>.
          Respondemos em até 2 dias úteis.
        </p>
        <p>
          Para dúvidas sobre dados pessoais, consulte a{" "}
          <Link to="/privacy">Política de Privacidade</Link> e os{" "}
          <Link to="/terms">Termos de Uso</Link>.
        </p>
        <Link className="btn btn--primary" to="/">
          Voltar ao início
        </Link>
      </div>
    </article>
  );
}
