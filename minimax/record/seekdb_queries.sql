-- seekdb / OceanBase document schema
CREATE TABLE IF NOT EXISTS sdd_documents (
  doc_id VARCHAR(128) NOT NULL,
  version INT NOT NULL,
  kind VARCHAR(32) NOT NULL,
  path VARCHAR(512) NOT NULL,
  symbol VARCHAR(256) NULL,
  text LONGTEXT NOT NULL,
  PRIMARY KEY (doc_id, version)
);

-- latest-version projection used to build task context
SELECT d.doc_id, d.version, d.kind, d.path, d.symbol, d.text
FROM sdd_documents d
JOIN (SELECT doc_id, MAX(version) AS version FROM sdd_documents GROUP BY doc_id) latest
  ON latest.doc_id = d.doc_id AND latest.version = d.version;

-- candidate filter for the validation task
SELECT doc_id, version, kind, path, symbol, text
FROM sdd_documents
WHERE text LIKE '%approval%' OR path LIKE '%approval%'
LIMIT 500;
