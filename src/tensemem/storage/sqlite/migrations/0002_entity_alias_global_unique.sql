-- SQLite allows multiple NULLs in a composite PRIMARY KEY, so global aliases
-- (scope_id IS NULL) need an explicit partial unique index.
CREATE UNIQUE INDEX ux_entity_aliases_global
  ON entity_aliases(alias_norm)
  WHERE scope_id IS NULL;
