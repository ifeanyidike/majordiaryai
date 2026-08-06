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
        # Supavisor's three signatures, confirmed empirically against the
        # pooler. They are precise, so map each to its real cause.
        if "ENOIDENTIFIER" in message:
            print("DB_USER has no project ref — the pooler cannot tell which project")
            print("you mean. Use postgres.<your-project-ref>.")
            return 1
        if "ENOTFOUND" in message:
            print(f"The project ref in DB_USER does not exist on this host: {user}")
            print("Check it against the subdomain of your SUPABASE_URL, and make sure")
            print("DB_HOST is the pooler for that same project/region.")
            return 1
        if "password authentication failed" in message:
            # Getting here means the tenant resolved: ref is right, password isn't.
            print("The project ref resolved (a bad ref returns ENOTFOUND instead),")
            print("so DB_USER is correct and DB_PASSWORD is the problem.")
            print()
            print("  Supabase → Project Settings → Database → Reset database password")
            print()
            print("It is the DATABASE password, not your Supabase account login.")
            print("Also check the Railway value for a trailing space or wrapping quotes.")
            return 1
        if False:
            print("The server answered and rejected the credentials, so host and port are fine.")
            print()
            if is_pooler and "." in user:
                # Supavisor strips the .<ref> suffix and authenticates the
                # underlying role, so the error always names it "postgres" —
                # it says nothing about whether the ref itself is right.
                print("The username is correctly qualified, and the pooler reports the")
                print('underlying role ("postgres") regardless, so this points at:')
                print("  1. DB_PASSWORD — must be the DATABASE password")
                print("     (Supabase → Project Settings → Database → Reset database password),")
                print("     NOT your Supabase account login.")
                print("  2. A stray character in the variable — trailing space, or quotes")
                print("     pasted around the value. Retype it rather than pasting.")
                print("  3. The project ref in DB_USER not matching this host's project.")
            else:
                print("Either DB_PASSWORD is wrong, or DB_USER is not the role Supabase lists.")
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
