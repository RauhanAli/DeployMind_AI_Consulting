-- Executed once when the Postgres volume is first created.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE deploymind_test OWNER deploymind;
\c deploymind_test
CREATE EXTENSION IF NOT EXISTS vector;
