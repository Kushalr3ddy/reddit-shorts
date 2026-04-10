CREATE TABLE IF NOT EXISTS reddit_shorts_pipeline (
        reddit_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        status TEXT DEFAULT 'PENDING',
        error_message TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    -- Function to handle the auto-update of the 'updated_at' column
    CREATE OR REPLACE FUNCTION update_modified_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = now();
        RETURN NEW;
    END;
    $$ language 'plpgsql';

    -- Drop trigger if exists to prevent errors on re-run
    DROP TRIGGER IF EXISTS update_shorts_modtime ON reddit_shorts_pipeline;

    CREATE TRIGGER update_shorts_modtime
        BEFORE UPDATE ON reddit_shorts_pipeline
        FOR EACH ROW
        EXECUTE PROCEDURE update_modified_column();