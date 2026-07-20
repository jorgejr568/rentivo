import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="error-page">
      <div className="error-code">404</div>
      <h1 className="error-title">Página não encontrada</h1>
      <p className="error-message">A página que você procura não existe ou foi movida.</p>
      <Link className="btn btn--primary" to="/billings/">Voltar ao início</Link>
    </div>
  );
}
