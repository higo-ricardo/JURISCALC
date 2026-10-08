# Roadmap — Sync IBGE/BACEN → SQLite

## Objetivo
Manter `indices` atualizados localmente para cálculo offline e auditável.

## Arquitetura
```
IBGE SIDRA (IPCA, IPCA-E, INPC) + BACEN SGS (SELIC, TR) + FGV (IGP-M)
      │  sync semanal, idempotente, com versionamento fonte
      v
SQLite `data/indices.db` tabela `indices` + `sync_log`
      │
      v
IndiceRepository.buscar() (engine nunca chama API direto)
```

## Schema (ver backend/tabelas/schema.sql)
- `indices(indice TEXT, competencia TEXT, valor REAL, fonte TEXT, atualizado_em TEXT, PRIMARY KEY(indice, competencia))`
- `sync_log(id, fonte, indice, periodo, status, mensagem, executado_em)`

## APIs
1. IBGE SIDRA — IPCA (tabela 1419?), IPCA-E (tabela 647?), INPC (tabela 1420?). Endpoint base `https://apisidra.ibge.gov.br/values/...`
   Fallback: `https://servicodados.ibge.gov.br/api/v3/...`
2. BACEN SGS — SELIC diária (série 11), TR (série 226). `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial=...&dataFinal=...`
3. FGV IGP-M — sem API pública estável → import CSV manual / IPEAData fallback

Competência: mensal `AAAA-MM`. SELIC diária → agrega para mensal + acumulada EC113.

## Fases
- Fase 0: criar `data/`, `schema.sql`, `sync.py` com `fetch_ibge()`, `fetch_bcb()`, `upsert()`, `last_sync()`. Dry-run + log.
- Fase 1: IBGE IPCA/INPC/IPCA-E → upsert idempotente (INSERT OR REPLACE), valida variação absurda (>5% m/m bloqueia).
- Fase 2: BACEN SELIC/TR + acumulada mensal para EC113.
- Fase 3: agendador semanal (`task scheduler`/`cron` ou `python sync.py --auto`), `sync_log`, alerta se gap > 45 dias.
- Fase 4: tela wizard mostra `atualizado até AAAA-MM (fonte)` + botão Atualizar.

## Regras
- Engine lê só SQLite. Sync nunca altera cálculo passado sem versionar fonte.
- Pro-rata: se mês não publicado usa mês anterior + flag `provisorio`.
- Teste: `test_sync.py` com fixtures JSON, sem rede.
- Rate-limit: 1 req/2s, retry 3x backoff.

## Comandos
```
python -m backend.tabelas.sync --indice IPCA-E --de 2020-01 --ate 2026-10
python -m backend.tabelas.sync --tudo --db data/indices.db
pytest tests/test_sync.py -q
```

## Status
[ ] schema.sql [ ] sync.py [ ] test_sync.py [ ] cron semanal [ ] badge atualizado-ate no wizard
