"""缓存模块 - SQLite 消息存储与去重"""

import json
import sqlite3
from pathlib import Path

from astrbot.api import logger

from ..crawler.parser import PostItem

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS posts (
    post_id      TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    summary      TEXT,
    url          TEXT NOT NULL,
    published_at TEXT NOT NULL,
    images       TEXT,
    post_type    TEXT DEFAULT 'normal',
    ordered_content TEXT DEFAULT '[]',
    created_at   TEXT DEFAULT (datetime('now','localtime'))
);
"""

# 兼容旧表：如果 ordered_content 列不存在则添加
ALTER_TABLE_SQL = """
ALTER TABLE posts ADD COLUMN ordered_content TEXT DEFAULT '[]';
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published_at DESC);
"""


class PostCache:
    """管理已获取消息的 SQLite 缓存，提供去重和查询能力"""

    def __init__(self, db_path: Path, max_history: int = 200):
        self.db_path = db_path
        self.max_history = max_history
        self._ensure_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self):
        """初始化数据库表和索引"""
        try:
            with self._get_conn() as conn:
                conn.execute(CREATE_TABLE_SQL)
                conn.execute(CREATE_INDEX_SQL)
                # 兼容旧表：尝试新增 ordered_content 列
                try:
                    conn.execute(ALTER_TABLE_SQL)
                except sqlite3.OperationalError:
                    pass  # 列已存在
                conn.commit()
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")

    def is_new(self, post_id: str) -> bool:
        """判断消息是否为新消息（未缓存过）"""
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT 1 FROM posts WHERE post_id = ?", (post_id,)
                ).fetchone()
                return row is None
        except Exception as e:
            logger.error(f"去重查询失败: {e}")
            return True

    def mark_pushed(self, post: PostItem):
        """将新消息写入 SQLite"""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO posts
                       (post_id, title, summary, url, published_at,
                        images, post_type, ordered_content)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        post.post_id,
                        post.title,
                        post.summary,
                        post.url,
                        post.published_at,
                        json.dumps(post.images, ensure_ascii=False),
                        post.post_type,
                        json.dumps(post.ordered_content, ensure_ascii=False),
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"写入消息失败: {e}")

    def get_recent_posts(self, n: int = 10) -> list[PostItem]:
        """获取最近 n 条消息，按发布时间倒序"""
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM posts ORDER BY published_at DESC LIMIT ?",
                    (n,),
                ).fetchall()
                return [self._row_to_post(row) for row in rows]
        except Exception as e:
            logger.error(f"查询最近消息失败: {e}")
            return []

    def get_post_by_index(self, index: int, n: int = 10) -> PostItem | None:
        """从最近 n 条中按序号（1-based）获取单条消息"""
        posts = self.get_recent_posts(n)
        if 1 <= index <= len(posts):
            return posts[index - 1]
        return None

    def prune_old_posts(self):
        """清理超出 max_history 的旧数据"""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """DELETE FROM posts WHERE post_id NOT IN
                       (SELECT post_id FROM posts
                        ORDER BY published_at DESC LIMIT ?)""",
                    (self.max_history,),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"清理旧数据失败: {e}")

    @staticmethod
    def _row_to_post(row: sqlite3.Row) -> PostItem:
        """将 SQLite Row 转换为 PostItem"""
        images_raw = row["images"] or "[]"
        try:
            images = json.loads(images_raw)
        except json.JSONDecodeError:
            images = []

        ordered_raw = row["ordered_content"] if "ordered_content" in row.keys() else "[]"
        try:
            ordered_content = json.loads(ordered_raw) if ordered_raw else []
        except json.JSONDecodeError:
            ordered_content = []

        return PostItem(
            post_id=row["post_id"],
            title=row["title"],
            summary=row["summary"] or "",
            url=row["url"],
            published_at=row["published_at"],
            post_type=row["post_type"] or "normal",
            images=images,
            ordered_content=ordered_content,
        )
