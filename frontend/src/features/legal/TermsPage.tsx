import { useEffect } from "react";
import { Link } from "react-router-dom";

export function TermsPage() {
  useEffect(() => {
    document.title = "Termos de Uso - Rentivo";
  }, []);

  return (
    <article className="panel">
      <div className="panel-head">
        <h2 className="page-title">Termos de Uso</h2>
        <p className="page-subtitle">Última atualização: 23 de julho de 2026</p>
      </div>
      <div className="panel-body">
        <p>
          Estes termos regem o uso do Rentivo, plataforma de gestão de
          cobranças de aluguel. Ao criar uma conta ou usar o serviço, você
          concorda com estes termos.
        </p>

        <h3>O serviço</h3>
        <p>
          O Rentivo permite criar e organizar cobranças de aluguel, gerar
          QR Codes PIX, emitir recibos e enviar comunicações por e-mail. O
          serviço é uma ferramenta de gestão: as relações de locação e os
          pagamentos ocorrem diretamente entre você e as pessoas que você
          cobra.
        </p>

        <h3>Sua conta</h3>
        <p>
          Você é responsável por manter suas credenciais em segurança, por
          fornecer informações verdadeiras (incluindo sua chave PIX) e por
          toda atividade realizada na sua conta. Recomendamos ativar um
          segundo fator de autenticação.
        </p>

        <h3>Conteúdo cadastrado</h3>
        <p>
          Os dados que você cadastra (imóveis, cobranças, destinatários)
          permanecem seus. Ao cadastrar dados de terceiros, como nome e
          e-mail de inquilinos, você declara ter base legal para isso e para o
          envio das comunicações feitas em seu nome pela plataforma.
        </p>

        <h3>Pagamentos</h3>
        <p>
          O Rentivo não é instituição de pagamento, não intermedeia nem
          custodia valores. Os QR Codes PIX gerados apontam para a chave PIX
          cadastrada por você, e os pagamentos são liquidados diretamente pelo
          arranjo PIX entre pagador e recebedor.
        </p>

        <h3>Uso aceitável</h3>
        <p>
          É proibido usar o serviço para atividade ilegal, para enviar
          comunicações não autorizadas (spam), para cobrar valores indevidos
          ou para tentar comprometer a segurança da plataforma ou de outras
          contas.
        </p>

        <h3>Disponibilidade e responsabilidade</h3>
        <p>
          O serviço é fornecido &quot;como está&quot;. Trabalhamos para mantê-lo
          disponível e seguro, mas não garantimos operação ininterrupta. Na
          extensão permitida pela lei, o Rentivo não responde por perdas
          decorrentes de informações incorretas cadastradas por você ou por
          indisponibilidade de serviços de terceiros (como o arranjo PIX).
        </p>

        <h3>Encerramento</h3>
        <p>
          Você pode excluir sua conta a qualquer momento em Segurança &gt;
          Excluir conta. Podemos suspender ou encerrar contas que violem
          estes termos.
        </p>

        <h3>Alterações, contato e foro</h3>
        <p>
          Podemos atualizar estes termos, indicando a data da última
          atualização nesta página. O tratamento de dados pessoais é descrito
          na <Link to="/privacy">Política de Privacidade</Link>. Dúvidas:{" "}
          <a href="mailto:suporte@rentivo.com.br">suporte@rentivo.com.br</a>.
          Estes termos são regidos pelas leis brasileiras.
        </p>
      </div>
    </article>
  );
}
