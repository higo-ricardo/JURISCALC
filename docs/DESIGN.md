# Design do Código — Calculadora Judicial

Aprovado em 07/10/2026. Fonte: planejamento engine/wizard/presets.

## 1. backend/engine.py — núcleo
Procedural atual (`fator_correcao`, `valor_corrigido`, `juros_simples`, `calcular_verba`, `calcular_fase_ec113`, `total_geral`) evolui para:

- Value Objects imutáveis: `Indice(id, competencia, valor, fonte)`, `Verba(nome, valor_base, data_base, indice_id)`
- `CorrecaoStrategy.calcular(V0, ind_ini, ind_fim)` → `FatorSimples`, `SelicAcumulada`
- `JurosStrategy.calcular(VC, taxa, ini, fim)` → `JurosSimples`, `JurosComposto`, `SelicUnica`
- `Calculadora.calcular_verba()`, `calcular_fase_ec113()`, `total_geral()`
- `IndiceRepository.buscar(indice, competencia)` abstrai CSV/SQLite/API
- `CalculadoraFacade.calcular_processo()` — ponto único para o wizard
- Regras: puro sem I/O, `Decimal` no lugar de `float`, arredonda só no final, pro-rata die dias/30, EC113 corte 09/12/2021

Fluxo: `Wizard -> Facade -> [Repository + CorrecaoStrategy + JurosStrategy] -> Verba -> MemoriaBuilder`

## 2. backend/presets.py
- `Preset` dataclass frozen com `validar()` (tribunal, indice_default, taxa_am, tipo_juros, termo_inicial, corte_ec113?)
- `PresetRegistry.listar(), obter("TJSP_CIVEL")` — Factory, carrega de `presets.json`
- Presets: TJSP_CIVEL, TJRJ_CIVEL, JF_MANUAL_CJF, FAZENDA_EC113

## 3. frontend/wizard.py
- `WizardState(processo, verbas, preset, pagamentos, etapa_atual)`
- `Step` abstrata (`validar()->erros`, `avancar()`, `voltar()`): StepProcesso, StepVerbas, StepParametros, StepPagamentos, StepResultado
- `WizardController(state, calculadora)` — único que chama engine

## 4. Patterns e porquê
1. Strategy (Correção/Juros) — troca IPCA-E/SELIC/INPC em runtime, evita ifs, essencial EC113
2. Factory (Preset/Calculadora) — defaults por tribunal centralizados
3. Builder (Memória PDF) — mesma base gera HTML/PDF/Excel mês-a-mês
4. Facade (`calcular_processo()`) — wizard chama 1 método
5. Repository (índices) — hoje CSV, amanhã SQLite/API sem quebrar engine
6. State (wizard) — navegação voltar/avançar + rascunho

Sem Singleton, sem herança profunda.

## 5. Design System UI
- Tokens: bg #F8FAFC, ink #111827, muted #6B7280, accent #1E40AF, ok #047857, danger #B91C1C, fonte Inter/Arial 14px, radius 8px, tabela zebra
- Componentes: Field/DatePicker, SelectIndice, TabelaVerbas, TotalBar, BtnPrimario/Secundario, BadgePreset, Stepper
- Base: wireframes.html
