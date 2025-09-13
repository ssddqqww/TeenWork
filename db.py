import aiomysql
from typing import Optional, List, Dict, Any
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB

pool: Optional[aiomysql.Pool] = None


async def init_pool() -> None:

    global pool
    if pool is not None:
        return
    pool = await aiomysql.create_pool(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        db=MYSQL_DB,
        autocommit=True,
        minsize=1,
        maxsize=5,
        charset="utf8mb4"
    )


async def close_pool() -> None:
    global pool
    if pool is not None:
        pool.close()
        await pool.wait_closed()
        pool = None


async def save_user(telegram_id: int, name: str, age: int, skills: List[str]) -> None:
    assert pool is not None
    skills_csv = ",".join(skills)
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO Users (telegram_id, name, age, skills)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE name=VALUES(name), age=VALUES(age), skills=VALUES(skills)
                """,
                (telegram_id, name, age, skills_csv)
            )


async def get_user_by_telegram(telegram_id: int) -> Optional[Dict[str, Any]]:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, telegram_id, name, age, skills, points FROM Users WHERE telegram_id=%s",
                (telegram_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            return row


