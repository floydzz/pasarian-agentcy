-- This runs once when the MySQL data volume is first initialized.  Keep the
-- test schema isolated: pytest drops and recreates its tables for every run.
CREATE DATABASE IF NOT EXISTS agentcy_test;
GRANT ALL PRIVILEGES ON agentcy_test.* TO 'agentcy'@'%';
FLUSH PRIVILEGES;
