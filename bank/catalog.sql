CREATE TABLE IF NOT EXISTS bank_source (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bank_context (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES bank_source(id),
  content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bank_task (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES bank_source(id),
  context_id TEXT REFERENCES bank_context(id),
  exam TEXT NOT NULL,
  subject TEXT NOT NULL,
  content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bank_test (
  id TEXT PRIMARY KEY,
  exam TEXT NOT NULL,
  subject TEXT NOT NULL,
  title TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bank_test_task (
  test_id TEXT NOT NULL REFERENCES bank_test(id),
  position INTEGER NOT NULL,
  task_id TEXT NOT NULL REFERENCES bank_task(id),
  PRIMARY KEY (test_id, position),
  UNIQUE (test_id, task_id)
);
CREATE TABLE IF NOT EXISTS bank_card (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES bank_task(id),
  exam TEXT NOT NULL,
  subject TEXT NOT NULL,
  position INTEGER NOT NULL,
  overrides TEXT NOT NULL,
  UNIQUE (exam, subject, position)
);
CREATE VIEW IF NOT EXISTS database_tests AS
  SELECT v.exam, v.subject, v.id AS test_id, v.title, vt.position,
         t.id AS task_id, t.source_id, t.context_id, t.content
  FROM bank_test AS v
  JOIN bank_test_task AS vt ON vt.test_id = v.id
  JOIN bank_task AS t ON t.id = vt.task_id;
CREATE VIEW IF NOT EXISTS database_cards AS
  SELECT c.exam, c.subject, c.id AS card_id, c.position, t.id AS task_id,
         t.source_id, t.context_id, t.content, c.overrides
  FROM bank_card AS c JOIN bank_task AS t ON t.id = c.task_id;
