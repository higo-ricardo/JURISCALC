-- SQLite indices judiciais + cálculos persistidos
CREATE TABLE IF NOT EXISTS indices (
  indice TEXT NOT NULL,
  competencia TEXT NOT NULL,
  valor REAL NOT NULL,
  fonte TEXT NOT NULL DEFAULT 'manual',
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (indice, competencia)
);
CREATE INDEX IF NOT EXISTS idx_indices_comp ON indices(competencia);

CREATE TABLE IF NOT EXISTS sync_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fonte TEXT NOT NULL,
  indice TEXT NOT NULL,
  periodo TEXT NOT NULL,
  status TEXT NOT NULL,
  mensagem TEXT DEFAULT '',
  executado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS calculos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  processo TEXT NOT NULL,
  preset TEXT NOT NULL,
  data_fim TEXT NOT NULL,
  base REAL NOT NULL,
  honorarios REAL NOT NULL,
  custas REAL NOT NULL,
  multa REAL NOT NULL,
  total REAL NOT NULL,
  criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS calculo_itens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  calculo_id INTEGER NOT NULL REFERENCES calculos(id),
  verba TEXT NOT NULL,
  valor_base REAL NOT NULL,
  data_base TEXT NOT NULL,
  corrigido REAL NOT NULL,
  juros REAL NOT NULL,
  total REAL NOT NULL
);
