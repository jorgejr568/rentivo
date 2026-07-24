import { useEffect } from "react";
import { Link } from "react-router-dom";

export function PrivacyPolicyPage() {
  useEffect(() => {
    document.title = "Política de Privacidade - Rentivo";
  }, []);

  return (
    <article className="panel">
      <div className="panel-head">
        <h2 className="page-title">Política de Privacidade</h2>
        <p className="page-subtitle">Última atualização: 23 de julho de 2026</p>
      </div>
      <div className="panel-body">
        <p>
          O Rentivo é uma plataforma de gestão de cobranças de aluguel. Esta
          política explica quais dados pessoais tratamos, por que tratamos e
          quais são os seus direitos, em conformidade com a Lei Geral de
          Proteção de Dados (LGPD, Lei nº 13.709/2018).
        </p>

        <h3>Dados que coletamos</h3>
        <p>
          <strong>Dados de conta:</strong> e-mail e senha (armazenada apenas
          como hash criptográfico). Se você entrar com o Google, recebemos o
          e-mail associado à sua conta Google.
        </p>
        <p>
          <strong>Dados de segurança:</strong> chaves de acesso (passkeys),
          configuração de autenticação por aplicativo (TOTP), códigos de
          recuperação e dispositivos conhecidos, usados para proteger sua
          conta.
        </p>
        <p>
          <strong>Dados de recebimento:</strong> chave PIX, nome e cidade do
          recebedor, usados para gerar as cobranças que você cria.
        </p>
        <p>
          <strong>Conteúdo de cobranças:</strong> os dados que você cadastra
          sobre imóveis, cobranças, despesas, recibos e destinatários (como
          nome e e-mail de inquilinos). Você é responsável por ter base legal
          para cadastrar dados de terceiros.
        </p>
        <p>
          <strong>Registros técnicos:</strong> endereço IP, identificação do
          navegador e registros de auditoria de ações na conta, mantidos por
          segurança. Usamos cookies essenciais de sessão e métricas de uso do
          site.
        </p>

        <h3>Como usamos os dados</h3>
        <p>
          Usamos seus dados para operar o serviço (gerar cobranças PIX, enviar
          e-mails de cobrança e recibos), proteger sua conta, enviar
          comunicações transacionais (como avisos de segurança) e entender o
          uso do produto para melhorá-lo. Não vendemos dados pessoais.
        </p>

        <h3>Bases legais</h3>
        <p>
          Tratamos dados com base na execução de contrato (operar sua conta),
          no cumprimento de obrigação legal (registros fiscais e de
          auditoria), no legítimo interesse (segurança e prevenção a fraudes)
          e no consentimento, quando aplicável.
        </p>

        <h3>Compartilhamento</h3>
        <p>
          Usamos operadores para funcionar: Amazon Web Services (hospedagem,
          armazenamento de arquivos e envio de e-mails), Cloudflare (proteção
          contra abuso no cadastro) e Google (login opcional e métricas de
          uso). Esses operadores tratam dados conforme nossos contratos e suas
          próprias políticas. Não compartilhamos dados com terceiros para fins
          de publicidade.
        </p>

        <h3>Segurança e retenção</h3>
        <p>
          Dados sensíveis são criptografados em repouso com chaves gerenciadas
          (KMS), senhas são armazenadas apenas como hash e todo o tráfego usa
          HTTPS. Mantemos seus dados enquanto sua conta existir. Após a
          exclusão da conta, registros de cobranças e de auditoria podem ser
          retidos pelo prazo exigido por obrigações legais e fiscais.
        </p>

        <h3>Seus direitos (LGPD)</h3>
        <p>
          Você pode solicitar acesso, correção, portabilidade e exclusão dos
          seus dados, além de informações sobre o tratamento. Você pode
          excluir sua conta diretamente em Segurança &gt; Excluir conta (no
          site ou no aplicativo). Para outras solicitações, fale com{" "}
          <a href="mailto:suporte@rentivo.com.br">suporte@rentivo.com.br</a>.
        </p>

        <h3>Alterações</h3>
        <p>
          Podemos atualizar esta política e indicaremos a data da última
          atualização nesta página. O uso do serviço também é regido pelos{" "}
          <Link to="/terms">Termos de Uso</Link>.
        </p>
      </div>
    </article>
  );
}
