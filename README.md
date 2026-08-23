# Zodyam · Integração Mercado Livre

Repositório privado usado por uma rotina automática (Claude Code cloud routine)
para monitorar diariamente as vendas orgânicas e as campanhas de Mercado Ads
da loja **ZODYAM COMERCIO VAREJISTA LTDA** via API oficial do Mercado Livre.

## Conteúdo

- `credentials.json` — client_id, client_secret, access_token e refresh_token
  da aplicação "Zodyam Monitor". **Contém segredos** — mantenha o repo privado.
  A rotina diária lê este arquivo, renova o `access_token` via `refresh_token`
  e sobrescreve o arquivo com o token novo a cada execução.
- `reports/` — um arquivo `YYYY-MM-DD.md` por dia com o resumo gerado.

## Permissões concedidas ao app

Leitura apenas: Publicação e sincronização, Publicidade (Ads), Métricas do
negócio, Vendas e envios. O app não tem permissão de escrita — não pausa nem
altera nada na conta automaticamente.

## Revogar acesso

Para revogar o acesso a qualquer momento: Mercado Livre > Central de
vendedores > Publicidade/Configurações > Aplicativos conectados, ou apague o
aplicativo "Zodyam Monitor" em developers.mercadolivre.com.br/devcenter.
