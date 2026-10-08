# Calculadora de Atualização Judicial

Correção monetária + juros de mora para indenizações (TJSP, TJRJ, TJMA, JF, Fazenda EC113).

## Uso

```
python main.py init                # cria data/indices.db + seed
python main.py wizard              # CLI interativo (5 etapas)
python main.py exemplo             # cálculo exemplo
python main.py listar              # cálculos salvos
python main.py sync --tudo         # atualiza índices IBGE/BACEN
python main.py serve --port 8000  # interface web
python -m unittest tests.test_e2e -v
```

## Camadas

- `backend/engine.py` — domínio: Strategies, Repository, `Calculadora`/`CalculadoraFacade`
- `backend/service.py` — `CalculadoraService` (única porta da aplicação, DTO puro)
- `backend/ports.py` — `AppPort` (abstração para a interface)
- `backend/storage.py` — `Database` + `CalculoRepository`
- `frontend/app.py` — `WebServer`/`HandlerFactory`; `frontend/cli.py` — `WizardCLI`
- `main.py` — `Command`s (`init/wizard/exemplo/listar/sync/serve`)
