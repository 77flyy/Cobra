import asyncpg
import asyncio

async def initialize_db():
    # Connect to the default 'postgres' database as superuser
    conn = await asyncpg.connect(
        database="postgres",
        user="postgres",
        password="admin123",  # Replace with your postgres password
        host="localhost"
    )

    # Enable autocommit for CREATE DATABASE
    await conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL READ COMMITTED;")
    await conn.execute("COMMIT")

    # Check and create user if it does not exist
    user_exists = await conn.fetchval("""
        SELECT 1 FROM pg_roles WHERE rolname = 'cobra_user';
    """)
    if not user_exists:
        await conn.execute("CREATE USER cobra_user WITH PASSWORD 'admin123';")
        print("User 'cobra_user' created.")

    # Check and create database if it does not exist
    db_exists = await conn.fetchval("""
        SELECT 1 FROM pg_database WHERE datname = 'cobra_db';
    """)
    if not db_exists:
        await conn.execute("COMMIT")
        await conn.execute("CREATE DATABASE cobra_db OWNER cobra_user;")
        print("Database 'cobra_db' created.")

    await conn.close()

    # Reconnect to the 'cobra_db' database as the new user
    conn = await asyncpg.connect(
        database="cobra_db",
        user="cobra_user",
        password="admin123",
        host="localhost"
    )

    # Create tables
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS wallets (
        chat_id TEXT PRIMARY KEY,
        pubkey TEXT,
        privkey TEXT,
        priority_level TEXT,
        buy_slip TEXT,
        sell_slip TEXT,
        balance TEXT,
        tokens TEXT,
        withdraw_to TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS telegram (
        chat_id TEXT PRIMARY KEY,
        username TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Create indexes for frequently queried fields
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_wallets_pubkey ON wallets(pubkey);
    CREATE INDEX IF NOT EXISTS idx_telegram_chat_id ON telegram(chat_id);
    """)

    await conn.close()
    print("PostgreSQL database, tables, and indexes initialized successfully.")

if __name__ == "__main__":
    asyncio.run(initialize_db())
