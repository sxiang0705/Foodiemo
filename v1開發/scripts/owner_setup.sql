-- Run only by the database owner on the target PostgreSQL server.
-- Password must be set interactively using psql \password; do not put it here.
-- CREATE DATABASE deliberately fails when the name already exists.
CREATE ROLE foodiemo_v1_test_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE foodiemo_v1_test OWNER foodiemo_v1_test_owner TEMPLATE template0;
REVOKE ALL ON DATABASE foodiemo_v1_test FROM PUBLIC;
COMMENT ON DATABASE foodiemo_v1_test IS 'foodiemo-v1-isolated';
-- Reconnect: \connect foodiemo_v1_test
-- REVOKE CREATE ON SCHEMA public FROM PUBLIC;
-- GRANT ALL ON SCHEMA public TO foodiemo_v1_test_owner;
-- \password foodiemo_v1_test_owner
