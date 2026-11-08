"""Initialize local PostgreSQL database with Supabase compatibility schema and roles."""

import psycopg


def init_db():
    conn = psycopg.connect(
        "postgresql://postgres:postgres@localhost:5432/township_ops", autocommit=True
    )
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS auth;")
        cur.execute(
            """
            CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid AS
            'SELECT NULLIF(current_setting(''request.jwt.claim.sub'', true), '''')::uuid;'
            LANGUAGE sql STABLE;
            """
        )
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    CREATE ROLE authenticated;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
                    CREATE ROLE service_role;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    CREATE ROLE anon;
                END IF;
            END $$;
            """
        )
        cur.execute("GRANT USAGE ON SCHEMA public TO authenticated;")
        cur.execute("GRANT USAGE ON SCHEMA public TO service_role;")
        cur.execute("GRANT USAGE ON SCHEMA auth TO authenticated;")
        cur.execute("GRANT USAGE ON SCHEMA auth TO service_role;")
    conn.close()
    print("Local database auth schema, function, and roles initialized successfully.")


if __name__ == "__main__":
    init_db()
