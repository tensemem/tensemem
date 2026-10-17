-- Initial schema for TenseMem (design doc §9).
-- schema_migrations is owned by the migration runner.

CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE scopes (
  id INTEGER PRIMARY KEY,
  user_id TEXT NOT NULL,
  agent_id TEXT NOT NULL DEFAULT '',
  namespace TEXT NOT NULL DEFAULT 'default',
  applied_seq INTEGER NOT NULL DEFAULT 0,
  projection_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE (namespace, user_id, agent_id)
);

CREATE TABLE episodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  public_id TEXT NOT NULL UNIQUE,
  scope_id INTEGER NOT NULL REFERENCES scopes(id),
  kind TEXT NOT NULL DEFAULT 'message'
    CHECK (kind IN ('message', 'explicit_op')),
  session_id TEXT,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
  content TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  ingested_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING', 'PROCESSED', 'SKIPPED', 'FAILED', 'DISMISSED', 'DELETED')),
  metadata TEXT NOT NULL DEFAULT '{}',
  UNIQUE (scope_id, content_hash, occurred_at)
);
CREATE INDEX ix_episodes_scope_seq ON episodes(scope_id, id);
CREATE INDEX ix_episodes_scope_time ON episodes(scope_id, occurred_at);
CREATE INDEX ix_episodes_pending
  ON episodes(scope_id, status)
  WHERE status IN ('PENDING', 'FAILED');

CREATE TABLE rejected_claims (
  id INTEGER PRIMARY KEY,
  scope_id INTEGER NOT NULL REFERENCES scopes(id),
  subject_id INTEGER NOT NULL,
  predicate_id INTEGER NOT NULL,
  object_norm TEXT NOT NULL,
  until_seq INTEGER NOT NULL,
  episode_id INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_rejected_claims_lookup
  ON rejected_claims(scope_id, subject_id, predicate_id, object_norm);

CREATE TABLE predicates (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT NOT NULL DEFAULT '',
  cardinality TEXT NOT NULL CHECK (cardinality IN ('ONE', 'MANY')),
  value_type TEXT NOT NULL DEFAULT 'text',
  sensitivity TEXT NOT NULL DEFAULT 'normal',
  pinned INTEGER NOT NULL DEFAULT 0,
  decay_days INTEGER,
  builtin INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE predicate_aliases (
  alias_norm TEXT PRIMARY KEY,
  predicate_id INTEGER NOT NULL REFERENCES predicates(id)
);

CREATE TABLE entities (
  id INTEGER PRIMARY KEY,
  scope_id INTEGER REFERENCES scopes(id),
  canonical_name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'thing',
  created_at TEXT NOT NULL
);

CREATE TABLE entity_aliases (
  alias_norm TEXT NOT NULL,
  scope_id INTEGER,
  entity_id INTEGER NOT NULL REFERENCES entities(id),
  PRIMARY KEY (alias_norm, scope_id)
);

CREATE TABLE facts (
  id INTEGER PRIMARY KEY,
  public_id TEXT NOT NULL UNIQUE,
  scope_id INTEGER NOT NULL REFERENCES scopes(id),
  subject_id INTEGER NOT NULL REFERENCES entities(id),
  predicate_id INTEGER NOT NULL REFERENCES predicates(id),
  object_text TEXT NOT NULL,
  object_entity_id INTEGER REFERENCES entities(id),
  object_norm TEXT NOT NULL,
  slot_key TEXT NOT NULL,
  status TEXT NOT NULL CHECK (
    status IN (
      'CANDIDATE', 'ACTIVE', 'SUPERSEDED', 'RETRACTED', 'STALE', 'REJECTED', 'DELETED'
    )
  ),
  modality TEXT NOT NULL DEFAULT 'asserted',
  confidence REAL NOT NULL DEFAULT 1.0,
  importance REAL NOT NULL DEFAULT 0.5,
  source TEXT NOT NULL DEFAULT 'extracted',
  valid_from TEXT,
  valid_precision TEXT NOT NULL DEFAULT 'unknown',
  valid_to TEXT,
  recorded_at TEXT NOT NULL,
  invalidated_at TEXT,
  last_confirmed_at TEXT NOT NULL,
  superseded_by INTEGER REFERENCES facts(id),
  source_episode_id INTEGER REFERENCES episodes(id),
  recorded_seq INTEGER NOT NULL,
  extractor_version TEXT
);
CREATE UNIQUE INDEX ux_facts_active_slot ON facts(slot_key) WHERE status = 'ACTIVE';
CREATE INDEX ix_facts_scope_status ON facts(scope_id, status);
CREATE INDEX ix_facts_slot_history ON facts(slot_key, valid_from);

CREATE TABLE fact_edges (
  src_fact_id INTEGER NOT NULL REFERENCES facts(id),
  dst_id INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (
    kind IN ('SUPERSEDES', 'EVIDENCED_BY', 'DERIVED_FROM', 'CONTRADICTS')
  ),
  created_at TEXT NOT NULL,
  PRIMARY KEY (src_fact_id, dst_id, kind)
);
CREATE INDEX ix_edges_dst ON fact_edges(dst_id, kind);

CREATE TABLE fact_events (
  id INTEGER PRIMARY KEY,
  fact_id INTEGER NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  reason TEXT NOT NULL,
  episode_id INTEGER,
  at TEXT NOT NULL
);

CREATE VIRTUAL TABLE facts_fts USING fts5(text, content='', tokenize='porter unicode61');
CREATE VIRTUAL TABLE episodes_fts USING fts5(content, content='', tokenize='porter unicode61');

CREATE TABLE embeddings (
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('fact', 'episode', 'predicate', 'entity')),
  owner_id INTEGER NOT NULL,
  model TEXT NOT NULL,
  dim INTEGER NOT NULL,
  vector BLOB NOT NULL,
  PRIMARY KEY (owner_kind, owner_id, model)
);

CREATE TABLE jobs (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  scope_id INTEGER NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'QUEUED'
    CHECK (status IN ('QUEUED', 'LEASED', 'DONE', 'DEAD')),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_run_at TEXT NOT NULL,
  lease_until TEXT,
  last_error TEXT,
  idempotency_key TEXT UNIQUE,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_jobs_ready ON jobs(status, next_run_at);

CREATE TABLE llm_cache (
  key TEXT PRIMARY KEY,
  response TEXT NOT NULL,
  created_at TEXT NOT NULL
);
