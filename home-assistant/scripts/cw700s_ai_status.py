#!/usr/bin/env python3
"""Expose the Windows CW700S AI SQLite results to Home Assistant as JSON."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

DB_PATH = Path("/media/Windows_CW700S/AI/cw700s_ai.db")


def _scalar(
    connection: sqlite3.Connection,
    sql: str,
    parameters: tuple[Any, ...] = (),
) -> int:
    row = connection.execute(sql, parameters).fetchone()
    return int(row[0] or 0) if row else 0


def main() -> None:
    result: dict[str, Any] = {
        "status": "异常",
        "database_online": False,
        "total_analyzed": 0,
        "meaningful": 0,
        "unrecognized": 0,
        "people": 0,
        "vehicles": 0,
        "animals": 0,
        "people_vehicle": 0,
        "people_animal": 0,
        "failed": 0,
        "last_analyzed_at": "",
        "recent_meaningful": [],
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "problem_summary": "",
    }

    if not DB_PATH.exists():
        result["status"] = "无数据库"
        result["problem_summary"] = f"未找到数据库：{DB_PATH}"
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return

    try:
        connection = sqlite3.connect(
            f"file:{DB_PATH.as_posix()}?mode=ro",
            uri=True,
            timeout=5,
        )
        connection.row_factory = sqlite3.Row

        try:
            result["database_online"] = True

            result["total_analyzed"] = _scalar(
                connection,
                "SELECT COUNT(*) FROM video_analysis WHERE status = 'ok'",
            )
            result["failed"] = _scalar(
                connection,
                "SELECT COUNT(*) FROM video_analysis WHERE status = 'failed'",
            )
            result["unrecognized"] = _scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM video_analysis
                WHERE status = 'ok'
                  AND primary_category = '未识别目标'
                """,
            )
            result["people"] = _scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM video_analysis
                WHERE status = 'ok'
                  AND primary_category LIKE '%人物%'
                """,
            )
            result["vehicles"] = _scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM video_analysis
                WHERE status = 'ok'
                  AND primary_category LIKE '%车辆%'
                """,
            )
            result["animals"] = _scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM video_analysis
                WHERE status = 'ok'
                  AND primary_category LIKE '%动物%'
                """,
            )
            result["people_vehicle"] = _scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM video_analysis
                WHERE status = 'ok'
                  AND primary_category = '人物+车辆'
                """,
            )
            result["people_animal"] = _scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM video_analysis
                WHERE status = 'ok'
                  AND primary_category = '人物+动物'
                """,
            )
            result["meaningful"] = max(
                0,
                result["total_analyzed"] - result["unrecognized"],
            )

            latest = connection.execute(
                """
                SELECT analyzed_at
                FROM video_analysis
                ORDER BY analyzed_at DESC
                LIMIT 1
                """
            ).fetchone()

            if latest:
                result["last_analyzed_at"] = str(latest["analyzed_at"] or "")

            recent_rows = connection.execute(
                """
                SELECT
                    analyzed_at,
                    primary_category,
                    max_confidence,
                    relative_path
                FROM video_analysis
                WHERE status = 'ok'
                  AND primary_category <> '未识别目标'
                ORDER BY analyzed_at DESC
                LIMIT 8
                """
            ).fetchall()

            result["recent_meaningful"] = [
                {
                    "time": str(row["analyzed_at"] or ""),
                    "category": str(row["primary_category"] or ""),
                    "confidence": round(float(row["max_confidence"] or 0), 2),
                    "path": str(row["relative_path"] or ""),
                }
                for row in recent_rows
            ]

            result["status"] = (
                "正常"
                if result["failed"] == 0
                else "有失败记录"
            )
            result["problem_summary"] = (
                "AI 分类数据库读取正常"
                if result["failed"] == 0
                else f"数据库中有 {result['failed']} 条分析失败记录"
            )

        finally:
            connection.close()

    except Exception as error:
        result["status"] = "异常"
        result["problem_summary"] = (
            f"读取 AI 数据库失败：{type(error).__name__}: {error}"
        )

    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
