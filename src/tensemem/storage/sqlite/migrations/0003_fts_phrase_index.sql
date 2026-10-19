DROP TABLE IF EXISTS facts_fts;
CREATE VIRTUAL TABLE facts_fts USING fts5(text, content='', tokenize='porter unicode61');
INSERT INTO facts_fts(rowid, text)
SELECT
  f.id,
  CASE WHEN e.kind = 'self' THEN 'user' ELSE e.canonical_name END
  || ' ' || p.name
  || ' ' || REPLACE(p.name, '_', ' ')
  || ' ' || f.object_text
FROM facts f
JOIN predicates p ON p.id = f.predicate_id
JOIN entities e ON e.id = f.subject_id;

DROP TABLE IF EXISTS episodes_fts;
CREATE VIRTUAL TABLE episodes_fts USING fts5(content, content='', tokenize='porter unicode61');
INSERT INTO episodes_fts(rowid, content)
SELECT id, content FROM episodes;
