# Documentação — Controle de Energia (Economart)

Documentação técnica do sistema que recebe a foto ou o PDF da conta de energia, lê os dados com o Gemini,
confere com a pessoa e mantém o histórico, os gráficos, a folha impressa por loja e os painéis da diretoria.
Cada documento descreve o que existe no código; o que não foi verificado vem marcado como tal.

## Para começar

**Nunca rodou o sistema?** → [getting-started.md](getting-started.md): instalar, rodar, primeiro login, dados de demonstração.

**Vai usar o sistema, não programar nele?** → [`../TUTORIAL.md`](../TUTORIAL.md) (uso diário por perfil e deploy no Railway).
Dentro do sistema há também a tela **Ajuda**, diferente para cada perfil.

## Como o sistema funciona

| Documento | O que cobre |
|---|---|
| [architecture.md](architecture.md) | Visão geral: camadas, fluxo foto → conferência → salvar → folha, serviços, middleware. Comece aqui para entender rápido |
| [domain-model.md](domain-model.md) | O negócio: perfis, lojas, unidades, contas, lançamentos manuais, modos de agrupamento da folha, alertas, rejeição de arquivos |
| [database.md](database.md) | Tabelas, relações, índices, migrações Alembic (inclui a regra da revisão 0003), SQLite × Postgres, cadeia de hash da auditoria |
| [api-reference.md](api-reference.md) | Endpoints HTTP por área, perfil exigido, CSRF, códigos de resposta |
| [security.md](security.md) | Senhas, sessão, CSRF, CSP, 2FA, auditoria à prova de adulteração, criptografia, validação de upload, LGPD, limites conhecidos |
| [frontend.md](frontend.md) | Templates, paleta e componentes de CSS, JavaScript, impressão, animações, convenções de texto |

## Operação e manutenção

| Documento | O que cobre |
|---|---|
| [operations.md](operations.md) | Deploy no Railway, variáveis de ambiente, migrações na subida, backup, troca de chaves, incidentes |
| [testing.md](testing.md) | Suíte pytest, como rodar, organização, CI, o que não é coberto |
| [faq.md](faq.md) | Perguntas técnicas frequentes, com respostas curtas |

## Apresentação e decisões

| Documento | O que cobre |
|---|---|
| [ROADMAP.md](ROADMAP.md) | O que vem depois da aprovação, em ordem de benefício, esforço e risco |
| [APRESENTACAO.md](APRESENTACAO.md) | Roteiro da demonstração para a diretoria, perguntas prováveis, checklist e riscos conhecidos |
| [`../DECISIONS.md`](../DECISIONS.md) | Decisões e o porquê (folha igual à planilha, lançamento manual por referência, migração 0003, etc.) |
| [`../CHANGELOG.md`](../CHANGELOG.md) | O que mudou, dia a dia |
| [`../AGENTS.md`](../AGENTS.md) | Mapa para agentes de IA e para quem chega novo: "para fazer X, leia Y" e o que nunca fazer |

## Ordem de leitura sugerida

**Dev novo:** getting-started → architecture → domain-model → o documento da área que vai mexer.

**Backend:** database → api-reference → security.

**Frontend:** frontend → api-reference.

**Operação / DevOps:** operations → security → testing.

**Suporte:** faq → operations.
