-- Runs once, when the Postgres volume is created. The engine keeps its own
-- schema (repos, issues, ETags) in a second database next to the platform's.
CREATE DATABASE firstpr_catalogue OWNER firstpr;
