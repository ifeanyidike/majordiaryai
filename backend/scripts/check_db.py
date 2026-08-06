"""Check the database credentials WITHOUT deploying.

A failed deploy takes minutes and only ever says "password authentication
failed". This connects with the exact same settings the app and Alembic use and
explains what is actually wrong.

    cd backend && .venv/bin/python -m scripts.check_db

Reads backend/.env like the app does. To test the values you are about to put
into Railway, set them inline instead:

    DB_HOST=... DB_USER=... DB_PASSWORD=... .venv/bin/python -m scripts.check_db

Prints no secrets — the password is never echoed.
"""

import sys

import psycopg2

from app.core.config import effective_db_port, settings


def main() -> int:
    port = effective_db_port()
    host = settings.db_host
    user = settings.db_user
    is_pooler = "pooler.supabase.com" in host

    print(f"host     {host}")
    print(f"port     {port}" + (f"  (remapped from {settings.db_port})"
                                if port != settings.db_port else ""))
    print(f"user     {user}")
    print(f"database {settings.db_name}")
    print(f"password {'set (' + str(len(settings.db_password)) + ' chars)' if settings.db_password else 'EMPTY'}")
    print()

    # The pooler authenticates per tenant, so it needs the project ref appended
    # to the role name. Plain "postgres" is only valid on a direct connection.
    if is_pooler and "." not in user:
        print("PROBLEM: this is a pooler host, but the user has no project ref.")
        print(f"  got:      {user}")
        print(f"  expected: {user}.<your-project-ref>")
        print("  The ref is the subdomain of your SUPABASE_URL.")
        print("  Supabase → Project Settings → Database → Connection string → Session pooler")
        return 1
    if not is_pooler and "." in user:
        print("PROBLEM: direct connections use the plain role name.")
        print(f"  got:      {user}")
        print(f"  expected: {user.split('.')[0]}")
        return 1

    try:
        conn = psycopg2.connect(
            host=host, port=port, user=user,
            password=settings.db_password, dbname=settings.db_name,
            connect_timeout=10,
        )
    except psycopg2.OperationalError as exc:
        message = str(exc).strip()
        print(f"FAILED: {message}")
        print()
        if "password authentication failed" in message:
            print("The server answered and rejected the credentials, so host and port are fine.")
            print("Either DB_PASSWORD is wrong, or DB_USER is not the exact role Supabase lists.")
            print("DB_PASSWORD is the DATABASE password (Project Settings → Database),")
            print("not your Supabase account password. You can reset it there.")
        elif "does not exist" in message:
            print("Credentials accepted but DB_NAME is wrong — for Supabase it is 'postgres'.")
        elif "timeout" in message.lower() or "could not translate" in message:
            print("Never reached the server: check DB_HOST for a typo.")
        return 1

    with conn, conn.cursor() as cur:
        cur.execute("select current_user, current_database(), version()")
        who, db, version = cur.fetchone()
        cur.execute(
            "select count(*) from information_schema.tables where table_schema = 'public'"
        )
        tables = cur.fetchone()[0]
    conn.close()

    print(f"CONNECTED as {who} to {db}")
    print(f"  {version.split(',')[0]}")
    print(f"  {tables} table(s) in the public schema")
    print()
    print("These credentials work. Put the same values in Railway.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
