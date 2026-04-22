-- Create artana schema for AI orchestration state
CREATE SCHEMA IF NOT EXISTS artana;

-- Enable pgvector extension for Artana vector-store migrations
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant permissions for the current user
GRANT ALL PRIVILEGES ON SCHEMA artana TO CURRENT_USER;
