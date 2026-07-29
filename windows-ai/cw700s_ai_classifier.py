#!/usr/bin/env python3
"""CW700S local second-stage classifier.

- Scans D:\CW700S\ObjectMotion recursively by default.
- Samples three frames from each MP4.
- Uses a local Ultralytics YOLO model.
- Never moves, renames, or deletes the original video.
- Stores results in SQLite so reruns only analyze new or changed videos.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
import sqlite3
import tempfile
import time
from typing import Any

import cv2
import torch
from ultralytics import YOLO


DEFAULT_ROOT = Path(r"D:\CW700S")
DEFAULT_MODEL = "yolo11n.pt"

SAMPLE_POSITIONS = (0.20, 0.50, 0.80)
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}

GROUPS: dict[str, set[str]] = {
    "人物": {"person"},
    "车辆": {
        "bicycle",
        "car",
        "motorcycle",
        "bus",
        "train",
        "truck",
    },
    "动物": {
        "bird",
        "cat",
        "dog",
        "horse",
        "sheep",
        "cow",
        "elephant",
        "bear",
        "zebra",
        "giraffe",
    },
}

TARGET_CLASSES = set().union(*GROUPS.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="本地分析 CW700S ObjectMotion 告警录像",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help=r"CW700S 根目录，默认 D:\CW700S",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="要扫描的目录，默认 ROOT\\ObjectMotion",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite 数据库路径，默认 ROOT\\AI\\cw700s_ai.db",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Ultralytics 模型名称或本地路径，默认 yolo11n.pt",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.30,
        help="最低置信度，默认 0.30",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="推理尺寸，默认 640",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="本次最多分析多少个新视频，0 表示不限制",
    )
    parser.add_argument(
        "--recheck",
        action="store_true",
        help="强制重新分析所有视频",
    )
    parser.add_argument(
        "--cpu",
        action="store_true",
        help="强制使用 CPU",
    )
    parser.add_argument(
        "--save-preview",
        action="store_true",
        help="为每个视频保存一张带检测框的预览图",
    )
    parser.add_argument(
        "--video-timeout",
        type=int,
        default=30,
        help="单个视频抽帧最长等待秒数，默认 30",
    )
    return parser.parse_args()


def connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS video_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_path TEXT NOT NULL UNIQUE,
            relative_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            modified_ns INTEGER NOT NULL,
            analyzed_at TEXT NOT NULL,
            model_name TEXT NOT NULL,
            device TEXT NOT NULL,
            status TEXT NOT NULL,
            primary_category TEXT NOT NULL,
            group_labels_json TEXT NOT NULL,
            detected_classes_json TEXT NOT NULL,
            detections_json TEXT NOT NULL,
            max_confidence REAL NOT NULL,
            frames_sampled INTEGER NOT NULL,
            duration_seconds REAL,
            preview_path TEXT,
            error TEXT NOT NULL DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_video_analysis_category
        ON video_analysis(primary_category)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_video_analysis_status
        ON video_analysis(status)
        """
    )
    conn.commit()
    return conn


def video_signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def is_already_analyzed(
    conn: sqlite3.Connection,
    path: Path,
    size: int,
    modified_ns: int,
) -> bool:
    row = conn.execute(
        """
        SELECT file_size, modified_ns, status
        FROM video_analysis
        WHERE video_path = ?
        """,
        (str(path),),
    ).fetchone()

    if row is None:
        return False

    old_size, old_modified_ns, status = row
    return (
        int(old_size) == int(size)
        and int(old_modified_ns) == int(modified_ns)
        and status == "ok"
    )


def collect_videos(source: Path) -> list[Path]:
    if not source.exists():
        raise FileNotFoundError(f"录像目录不存在：{source}")

    return sorted(
        (
            path
            for path in source.rglob("*")
            if path.is_file()
            and path.suffix.lower() in VIDEO_EXTENSIONS
            and ".downloading." not in path.name.lower()
        ),
        key=lambda item: str(item).lower(),
    )


def _extract_frames_worker(
    video_path_text: str,
    output_dir_text: str,
) -> None:
    """Decode one video in an isolated process.

    The parent can terminate this process if OpenCV/FFmpeg hangs on a broken
    HEVC stream.
    """
    video_path = Path(video_path_text)
    output_dir = Path(output_dir_text)
    result_file = output_dir / "result.json"

    try:
        timeout_params = [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            5000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            5000,
        ]

        try:
            capture = cv2.VideoCapture(
                str(video_path),
                cv2.CAP_FFMPEG,
                timeout_params,
            )
        except Exception:
            capture = cv2.VideoCapture(str(video_path))

        if not capture.isOpened():
            raise RuntimeError("OpenCV 无法打开视频")

        try:
            frame_count = int(
                capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            )
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            duration = (
                frame_count / fps
                if frame_count > 0 and fps > 0
                else 0.0
            )

            saved: list[dict[str, int | str]] = []

            if frame_count > 0:
                target_indexes = sorted(
                    {
                        max(
                            0,
                            min(
                                frame_count - 1,
                                int((frame_count - 1) * position),
                            ),
                        )
                        for position in SAMPLE_POSITIONS
                    }
                )
                target_set = set(target_indexes)
                last_target = target_indexes[-1]
                frame_index = 0

                # Sequential decoding is slower than random seeking, but it is
                # much more reliable for short HEVC alarm clips.
                while frame_index <= last_target:
                    ok, frame = capture.read()

                    if not ok:
                        break

                    if frame_index in target_set:
                        filename = f"frame_{len(saved)}.jpg"
                        destination = output_dir / filename

                        if not cv2.imwrite(str(destination), frame):
                            raise RuntimeError("抽帧图片写入失败")

                        saved.append(
                            {
                                "file": filename,
                                "frame_index": frame_index,
                            }
                        )

                    frame_index += 1
            else:
                frame_index = 0

                while len(saved) < len(SAMPLE_POSITIONS):
                    ok, frame = capture.read()

                    if not ok:
                        break

                    if frame_index % 15 == 0:
                        filename = f"frame_{len(saved)}.jpg"
                        destination = output_dir / filename

                        if not cv2.imwrite(str(destination), frame):
                            raise RuntimeError("抽帧图片写入失败")

                        saved.append(
                            {
                                "file": filename,
                                "frame_index": frame_index,
                            }
                        )

                    frame_index += 1

            if not saved:
                raise RuntimeError("没有读取到有效画面")

            result = {
                "ok": True,
                "frames": saved,
                "duration": duration,
            }
        finally:
            capture.release()

    except Exception as exc:
        result = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    result_file.write_text(
        json.dumps(result, ensure_ascii=False),
        encoding="utf-8",
    )


def read_sample_frames(
    video_path: Path,
    timeout_seconds: int,
) -> tuple[list[Any], list[int], float]:
    """Extract frames with a hard per-video timeout."""
    with tempfile.TemporaryDirectory(
        prefix="cw700s_frames_"
    ) as temporary_dir:
        context = mp.get_context("spawn")
        process = context.Process(
            target=_extract_frames_worker,
            args=(str(video_path), temporary_dir),
        )
        process.start()
        process.join(max(5, timeout_seconds))

        if process.is_alive():
            process.terminate()
            process.join(3)

            if process.is_alive():
                process.kill()
                process.join()

            raise TimeoutError(
                f"视频抽帧超过 {timeout_seconds} 秒，已自动跳过"
            )

        result_file = Path(temporary_dir) / "result.json"

        if not result_file.exists():
            raise RuntimeError(
                f"抽帧子进程异常退出，返回代码 {process.exitcode}"
            )

        result = json.loads(
            result_file.read_text(encoding="utf-8")
        )

        if not bool(result.get("ok")):
            raise RuntimeError(
                str(result.get("error") or "视频解码失败")
            )

        frames: list[Any] = []
        frame_indexes: list[int] = []

        for item in result.get("frames") or []:
            frame_path = Path(temporary_dir) / str(item["file"])
            frame = cv2.imread(str(frame_path))

            if frame is None:
                continue

            frames.append(frame)
            frame_indexes.append(int(item["frame_index"]))

        if not frames:
            raise RuntimeError("抽出的画面无法读取")

        return (
            frames,
            frame_indexes,
            float(result.get("duration") or 0.0),
        )

def build_primary_category(group_names: list[str]) -> str:
    present = [
        name
        for name in ("人物", "车辆", "动物")
        if name in group_names
    ]

    if not present:
        return "未识别目标"

    return "+".join(present)


def preview_file_for(video_path: Path, root: Path, ai_dir: Path) -> Path:
    try:
        relative = video_path.relative_to(root)
    except ValueError:
        relative = Path(video_path.name)

    digest = hashlib.sha1(
        str(video_path).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:10]

    preview_dir = ai_dir / "previews" / relative.parent
    preview_dir.mkdir(parents=True, exist_ok=True)

    return preview_dir / f"{video_path.stem}_{digest}.jpg"


def save_preview(result: Any, destination: Path) -> None:
    plotted = result.plot()
    if plotted is None:
        raise RuntimeError("模型没有返回可保存的预览画面")

    if not cv2.imwrite(str(destination), plotted):
        raise RuntimeError("预览图写入失败")


def upsert_result(
    conn: sqlite3.Connection,
    *,
    video_path: Path,
    relative_path: str,
    file_size: int,
    modified_ns: int,
    model_name: str,
    device: str,
    status: str,
    primary_category: str,
    group_labels: list[str],
    detected_classes: list[str],
    detections: list[dict[str, Any]],
    max_confidence: float,
    frames_sampled: int,
    duration_seconds: float | None,
    preview_path: str | None,
    error: str,
) -> None:
    conn.execute(
        """
        INSERT INTO video_analysis (
            video_path,
            relative_path,
            file_size,
            modified_ns,
            analyzed_at,
            model_name,
            device,
            status,
            primary_category,
            group_labels_json,
            detected_classes_json,
            detections_json,
            max_confidence,
            frames_sampled,
            duration_seconds,
            preview_path,
            error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_path) DO UPDATE SET
            relative_path = excluded.relative_path,
            file_size = excluded.file_size,
            modified_ns = excluded.modified_ns,
            analyzed_at = excluded.analyzed_at,
            model_name = excluded.model_name,
            device = excluded.device,
            status = excluded.status,
            primary_category = excluded.primary_category,
            group_labels_json = excluded.group_labels_json,
            detected_classes_json = excluded.detected_classes_json,
            detections_json = excluded.detections_json,
            max_confidence = excluded.max_confidence,
            frames_sampled = excluded.frames_sampled,
            duration_seconds = excluded.duration_seconds,
            preview_path = excluded.preview_path,
            error = excluded.error
        """,
        (
            str(video_path),
            relative_path,
            file_size,
            modified_ns,
            datetime.now().isoformat(timespec="seconds"),
            model_name,
            device,
            status,
            primary_category,
            json.dumps(group_labels, ensure_ascii=False),
            json.dumps(detected_classes, ensure_ascii=False),
            json.dumps(detections, ensure_ascii=False),
            round(float(max_confidence), 4),
            int(frames_sampled),
            (
                round(float(duration_seconds), 3)
                if duration_seconds is not None
                else None
            ),
            preview_path,
            error,
        ),
    )
    conn.commit()


def print_summary(conn: sqlite3.Connection) -> None:
    print("\n=== 当前数据库统计 ===")

    rows = conn.execute(
        """
        SELECT primary_category, COUNT(*)
        FROM video_analysis
        WHERE status = 'ok'
        GROUP BY primary_category
        ORDER BY COUNT(*) DESC, primary_category
        """
    ).fetchall()

    if not rows:
        print("还没有成功分析的录像")
    else:
        for category, count in rows:
            print(f"{category}: {count}")

    failed = conn.execute(
        """
        SELECT COUNT(*)
        FROM video_analysis
        WHERE status = 'failed'
        """
    ).fetchone()[0]

    print(f"分析失败记录: {failed}")


def main() -> int:
    args = parse_args()

    root = args.root.resolve()
    source = (
        args.source.resolve()
        if args.source is not None
        else (root / "ObjectMotion").resolve()
    )
    ai_dir = (root / "AI").resolve()
    db_path = (
        args.db.resolve()
        if args.db is not None
        else (ai_dir / "cw700s_ai.db").resolve()
    )

    ai_dir.mkdir(parents=True, exist_ok=True)

    device: str | int
    if args.cpu:
        device = "cpu"
    elif torch.cuda.is_available():
        device = 0
    else:
        device = "cpu"

    device_display = (
        torch.cuda.get_device_name(0)
        if device != "cpu"
        else "CPU"
    )

    print("=== CW700S 本地二次分类 ===")
    print(f"录像目录：{source}")
    print(f"数据库：{db_path}")
    print(f"模型：{args.model}")
    print(f"设备：{device_display}")
    print(f"置信度：{args.confidence}")
    print(f"单视频超时：{args.video_timeout} 秒")
    print("原视频不会被移动、改名或删除。\n")

    conn = connect_db(db_path)

    try:
        videos = collect_videos(source)
        pending: list[tuple[Path, int, int]] = []
        skipped = 0

        for video_path in videos:
            try:
                size, modified_ns = video_signature(video_path)
            except OSError as exc:
                print(f"[跳过] 无法读取文件信息：{video_path}：{exc}")
                continue

            if (
                not args.recheck
                and is_already_analyzed(
                    conn,
                    video_path,
                    size,
                    modified_ns,
                )
            ):
                skipped += 1
                continue

            pending.append((video_path, size, modified_ns))

        if args.limit > 0:
            pending = pending[: args.limit]

        print(
            f"发现录像 {len(videos)} 条；"
            f"已分析跳过 {skipped} 条；"
            f"本次待分析 {len(pending)} 条。"
        )

        if not pending:
            print_summary(conn)
            return 0

        print("\n正在加载模型。首次运行会自动下载模型文件……")
        model = YOLO(args.model)

        succeeded = 0
        failed = 0
        started = time.perf_counter()

        for index, (video_path, size, modified_ns) in enumerate(pending, 1):
            try:
                relative_path = str(video_path.relative_to(root))
            except ValueError:
                relative_path = video_path.name

            try:
                print(
                    f"[{index}/{len(pending)}] 开始：{relative_path}",
                    flush=True,
                )

                frames, frame_indexes, duration = read_sample_frames(
                    video_path,
                    args.video_timeout,
                )

                results = model.predict(
                    source=frames,
                    conf=args.confidence,
                    imgsz=args.imgsz,
                    device=device,
                    verbose=False,
                    quantize=(16 if device != "cpu" else None),
                )

                group_hits: set[str] = set()
                detected_classes: set[str] = set()
                detections: list[dict[str, Any]] = []
                max_confidence = 0.0
                best_result_index = 0
                best_result_score = -1.0

                for result_index, result in enumerate(results):
                    frame_score = 0.0
                    boxes = result.boxes

                    if boxes is not None and len(boxes) > 0:
                        class_ids = boxes.cls.detach().cpu().tolist()
                        confidences = boxes.conf.detach().cpu().tolist()
                        coordinates = boxes.xyxy.detach().cpu().tolist()

                        for class_id, score, xyxy in zip(
                            class_ids,
                            confidences,
                            coordinates,
                            strict=True,
                        ):
                            class_name = str(
                                result.names[int(class_id)]
                            )
                            score = float(score)

                            if class_name not in TARGET_CLASSES:
                                continue

                            detected_classes.add(class_name)
                            max_confidence = max(
                                max_confidence,
                                score,
                            )
                            frame_score = max(frame_score, score)

                            for group_name, members in GROUPS.items():
                                if class_name in members:
                                    group_hits.add(group_name)

                            detections.append(
                                {
                                    "frame_index": int(
                                        frame_indexes[result_index]
                                    ),
                                    "class": class_name,
                                    "confidence": round(score, 4),
                                    "xyxy": [
                                        round(float(value), 1)
                                        for value in xyxy
                                    ],
                                }
                            )

                    if frame_score > best_result_score:
                        best_result_score = frame_score
                        best_result_index = result_index

                group_labels = [
                    name
                    for name in ("人物", "车辆", "动物")
                    if name in group_hits
                ]
                primary_category = build_primary_category(group_labels)

                preview_path: str | None = None
                if args.save_preview:
                    destination = preview_file_for(
                        video_path,
                        root,
                        ai_dir,
                    )
                    save_preview(
                        results[best_result_index],
                        destination,
                    )
                    preview_path = str(destination)

                upsert_result(
                    conn,
                    video_path=video_path,
                    relative_path=relative_path,
                    file_size=size,
                    modified_ns=modified_ns,
                    model_name=args.model,
                    device=device_display,
                    status="ok",
                    primary_category=primary_category,
                    group_labels=group_labels,
                    detected_classes=sorted(detected_classes),
                    detections=detections,
                    max_confidence=max_confidence,
                    frames_sampled=len(frames),
                    duration_seconds=duration,
                    preview_path=preview_path,
                    error="",
                )

                succeeded += 1
                labels_text = (
                    "、".join(group_labels)
                    if group_labels
                    else "未识别人物/车辆/动物"
                )

                print(
                    f"[{index}/{len(pending)}] "
                    f"{relative_path} → {labels_text} "
                    f"(最高置信度 {max_confidence:.2f})"
                )

            except KeyboardInterrupt:
                print("\n收到停止命令。已完成的结果已经保存。")
                break
            except Exception as exc:
                failed += 1

                upsert_result(
                    conn,
                    video_path=video_path,
                    relative_path=relative_path,
                    file_size=size,
                    modified_ns=modified_ns,
                    model_name=args.model,
                    device=device_display,
                    status="failed",
                    primary_category="分析失败",
                    group_labels=[],
                    detected_classes=[],
                    detections=[],
                    max_confidence=0.0,
                    frames_sampled=0,
                    duration_seconds=None,
                    preview_path=None,
                    error=f"{type(exc).__name__}: {exc}",
                )

                print(
                    f"[{index}/{len(pending)}] "
                    f"{relative_path} → 分析失败："
                    f"{type(exc).__name__}: {exc}"
                )

        elapsed = time.perf_counter() - started

        print(
            "\n本次完成："
            f"成功 {succeeded}，失败 {failed}，"
            f"耗时 {elapsed:.1f} 秒。"
        )
        print_summary(conn)
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
