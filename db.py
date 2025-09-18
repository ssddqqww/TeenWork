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


async def get_tasks_by_skills(skills: List[str]) -> List[Dict[str, Any]]:
    assert pool is not None
    if not skills:
        return []
    placeholders = ",".join(["%s"] * len(skills))
    query = f"SELECT id, title, description, skill_required, deadline_hours FROM Tasks WHERE skill_required IN ({placeholders})"
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, skills)
            rows = await cur.fetchall()
            return list(rows or [])


async def get_task_by_id(task_id: int) -> Optional[Dict[str, Any]]:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, title, description, skill_required, deadline_hours FROM Tasks WHERE id=%s",
                (task_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            return row


async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, telegram_id, name, age, skills, points FROM Users WHERE id=%s",
                (user_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            return row


async def create_user_task(user_id: int, task_id: int) -> int:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO UserTasks (user_id, task_id) VALUES (%s, %s)",
                (user_id, task_id)
            )
            return cur.lastrowid


async def get_user_task_by_id(user_task_id: int) -> Optional[Dict[str, Any]]:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, user_id, task_id, start_time, status FROM UserTasks WHERE id=%s",
                (user_task_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            return row


async def update_user_task_status(user_task_id: int, status: str) -> None:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE UserTasks SET status=%s WHERE id=%s",
                (status, user_task_id)
            )


async def list_submitted_user_tasks() -> List[Dict[str, Any]]:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT UT.id AS user_task_id,
                       UT.start_time,
                       U.id AS user_id,
                       U.telegram_id,
                       U.name AS user_name,
                       U.points,
                       T.id AS task_id,
                       T.title,
                       T.description,
                       T.skill_required,
                       T.deadline_hours
                FROM UserTasks UT
                JOIN Users U ON U.id = UT.user_id
                JOIN Tasks T ON T.id = UT.task_id
                WHERE UT.status='submitted'
                ORDER BY UT.start_time DESC
                """
            )
            rows = await cur.fetchall()
            return list(rows or [])


async def ensure_user_task_files_table() -> None:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS UserTaskFiles (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    user_task_id INT NOT NULL,
                    file_id VARCHAR(255) NOT NULL,
                    file_type VARCHAR(50) NOT NULL,
                    caption TEXT NULL,
                    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    INDEX (user_task_id)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )


async def save_user_task_file(user_task_id: int, file_id: str, file_type: str, caption: Optional[str]) -> None:
    assert pool is not None
    await ensure_user_task_files_table()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO UserTaskFiles (user_task_id, file_id, file_type, caption) VALUES (%s, %s, %s, %s)",
                (user_task_id, file_id, file_type, caption)
            )


async def list_user_task_files(user_task_id: int) -> List[Dict[str, Any]]:
    assert pool is not None
    await ensure_user_task_files_table()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, file_id, file_type, caption, submitted_at FROM UserTaskFiles WHERE user_task_id=%s ORDER BY id",
                (user_task_id,)
            )
            rows = await cur.fetchall()
            return list(rows or [])


async def increment_user_points(user_id: int, points: int) -> None:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE Users SET points = points + %s WHERE id=%s",
                (points, user_id)
            )


async def has_in_progress_task_for_user_id(user_id: int) -> bool:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM UserTasks WHERE user_id=%s AND status='in_progress' LIMIT 1",
                (user_id,)
            )
            return await cur.fetchone() is not None


async def has_in_progress_task_for_telegram(telegram_id: int) -> bool:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT 1
                FROM UserTasks UT
                JOIN Users U ON U.id = UT.user_id
                WHERE U.telegram_id=%s AND UT.status='in_progress'
                LIMIT 1
                """,
                (telegram_id,)
            )
            return await cur.fetchone() is not None


async def list_all_users() -> List[Dict[str, Any]]:
    assert pool is not None
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, telegram_id, name, age, skills, points FROM Users ORDER BY id DESC"
            )
            rows = await cur.fetchall()
            return list(rows or [])


