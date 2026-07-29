"""Automatic incremental synchronizer for Xiaomi camera alarm clips."""
from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timedelta
import json
import locale
import logging
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

from aiohttp import web
import voluptuous as vol
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.util import dt as dt_util

DOMAIN = "cw700s_downloader"
SERVICE_SYNC = "sync"
SERVICE_STOP = "stop"

STATUS_ENTITY_ID = "sensor.cw700s_sync_status"
STATUS_FRIENDLY_NAME = "CW700S 同步状态"

DEFAULT_ENTITY_ID = "camera.your_cw700s"

# Windows 中的 D:\CW700S
DESTINATION_ROOT = Path("/media/Windows_CW700S")

STATE_FILE = Path("/config/cw700s_sync_state.json")
LOG_FILE = Path("/config/cw700s_sync.log")
DOWNLOADER = Path("/config/cw700s_download.py")

INITIAL_DAYS = 35
INCREMENTAL_DAYS = 30
MAX_EVENTS_PER_DAY = 1000

# 受控并发：不要一次开得过高，避免小米云限流
QUERY_CONCURRENCY = 2
DOWNLOAD_CONCURRENCY = 3

# 单日查询失败时自动重试，防止临时断线或小米云重置连接
QUERY_RETRIES = 4
QUERY_RETRY_BASE_DELAY = 2.0

# 每完成多少条事件保存一次状态；任务结束时还会再保存一次
STATE_SAVE_INTERVAL = 20

QUERY_DAY_TIMEOUT = 180
DOWNLOAD_TIMEOUT = 300
QUERY_PAGE_DELAY = 0.20

# 最近告警预览
RECENT_COUNT = 6
THUMBNAIL_DIR = Path("/config/cw700s_thumbnails")
THUMBNAIL_INDEX_FILE = THUMBNAIL_DIR / "index.json"
THUMBNAIL_WIDTH = 640
THUMBNAIL_TIMEOUT = 45

_LOGGER = logging.getLogger(__name__)

SYNC_SCHEMA = vol.Schema(
    {
        vol.Optional(
            "entity_id",
            default=DEFAULT_ENTITY_ID,
        ): cv.entity_id,
        vol.Optional(
            "full_scan",
            default=False,
        ): cv.boolean,
    }
)


def _append_log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(f"[{stamp}] {message}\n")


async def _log(hass: HomeAssistant, message: str) -> None:
    _LOGGER.info(message)
    await hass.async_add_executor_job(_append_log, message)


def _load_state() -> dict[str, Any]:
    default = {
        "meta": {},
        "events": {},
    }

    if not STATE_FILE.exists():
        return default

    try:
        data = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )

        if not isinstance(data, dict):
            return default

        data.setdefault("meta", {})
        data.setdefault("events", {})

        return data

    except (OSError, ValueError):
        return default


def _save_state(state: dict[str, Any]) -> None:
    temporary = STATE_FILE.with_suffix(".json.tmp")

    temporary.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(STATE_FILE)


async def _save_state_async(
    hass: HomeAssistant,
    state: dict[str, Any],
) -> None:
    # 在事件循环中先做快照，再交给线程写盘。
    # 这样并发下载继续更新原 state 时，不会与 JSON 序列化冲突。
    snapshot = copy.deepcopy(state)

    await hass.async_add_executor_job(
        _save_state,
        snapshot,
    )


def _scan_library_stats() -> dict[str, Any]:
    stats: dict[str, Any] = {
        "total_videos": 0,
        "people_motion": 0,
        "object_motion": 0,
        "other_motion": 0,
        "storage_bytes": 0,
        "storage_mb": 0.0,
        "storage_gb": 0.0,
        "latest_file": "",
        "latest_file_time": "",
        "storage_available": DESTINATION_ROOT.exists(),
    }

    if not DESTINATION_ROOT.exists():
        return stats

    latest_mtime = 0.0
    latest_path: Path | None = None

    try:
        for path in DESTINATION_ROOT.rglob("*.mp4"):
            if path.name.endswith(".downloading.mp4"):
                continue

            try:
                item = path.stat()
            except OSError:
                continue

            stats["total_videos"] += 1
            stats["storage_bytes"] += item.st_size

            parts = set(path.parts)

            if "PeopleMotion" in parts:
                stats["people_motion"] += 1
            elif "ObjectMotion" in parts:
                stats["object_motion"] += 1
            else:
                stats["other_motion"] += 1

            if item.st_mtime > latest_mtime:
                latest_mtime = item.st_mtime
                latest_path = path

    except OSError:
        stats["storage_available"] = False
        return stats

    stats["storage_mb"] = round(
        stats["storage_bytes"] / 1024 / 1024,
        1,
    )
    stats["storage_gb"] = round(
        stats["storage_bytes"] / 1024 / 1024 / 1024,
        3,
    )

    if latest_path is not None:
        try:
            stats["latest_file"] = str(
                latest_path.relative_to(DESTINATION_ROOT)
            )
        except ValueError:
            stats["latest_file"] = str(latest_path)

        stats["latest_file_time"] = datetime.fromtimestamp(
            latest_mtime
        ).strftime("%Y-%m-%d %H:%M:%S")

    return stats


def _set_status(
    hass: HomeAssistant,
    status: str,
    **attributes: Any,
) -> None:
    current = hass.states.get(STATUS_ENTITY_ID)
    merged = dict(current.attributes) if current else {}

    merged.update(
        {
            "friendly_name": STATUS_FRIENDLY_NAME,
            "icon": "mdi:cctv",
            "running": status in {
                "准备中",
                "查询中",
                "下载中",
                "整理中",
                "停止中",
            },
            "scan_days": INCREMENTAL_DAYS,
            "query_concurrency": QUERY_CONCURRENCY,
            "query_retries": QUERY_RETRIES,
            "download_concurrency": DOWNLOAD_CONCURRENCY,
        }
    )
    merged.update(attributes)

    hass.states.async_set(
        STATUS_ENTITY_ID,
        status,
        merged,
    )


async def _refresh_idle_status(
    hass: HomeAssistant,
    status: str = "空闲",
    **attributes: Any,
) -> None:
    state = await hass.async_add_executor_job(
        _load_state
    )
    stats = await hass.async_add_executor_job(
        _scan_library_stats
    )

    meta = state.get("meta", {})

    _set_status(
        hass,
        status,
        last_sync_time=meta.get("last_sync_time", ""),
        last_query_failures=meta.get(
            "last_query_failures",
            0,
        ),
        completed=0,
        total=0,
        progress_percent=0,
        **stats,
        **attributes,
    )


def _load_thumbnail_index() -> dict[str, Any]:
    if not THUMBNAIL_INDEX_FILE.exists():
        return {}

    try:
        data = json.loads(
            THUMBNAIL_INDEX_FILE.read_text(
                encoding="utf-8",
            )
        )
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_thumbnail_index(index: dict[str, Any]) -> None:
    THUMBNAIL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = THUMBNAIL_INDEX_FILE.with_suffix(
        ".json.tmp"
    )
    temporary.write_text(
        json.dumps(
            index,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(THUMBNAIL_INDEX_FILE)


def _find_ffmpeg() -> str:
    candidates = [
        shutil.which("ffmpeg"),
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
    ]

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)

    return ""


def _generate_thumbnail(
    source: Path,
    destination: Path,
) -> bool:
    ffmpeg = _find_ffmpeg()

    if not ffmpeg:
        return False

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = destination.with_name(
        destination.stem + ".tmp.jpg"
    )

    try:
        if temporary.exists():
            temporary.unlink()

        # 先截取第 1 秒；极短录像失败时退回第 0 秒。
        for seek in ("1", "0"):
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                seek,
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                f"scale='min({THUMBNAIL_WIDTH},iw)':-2",
                "-q:v",
                "3",
                "-y",
                str(temporary),
            ]

            result = subprocess.run(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=THUMBNAIL_TIMEOUT,
                check=False,
            )

            if (
                result.returncode == 0
                and temporary.exists()
                and temporary.stat().st_size > 0
            ):
                temporary.replace(destination)
                return True

        return False

    except (OSError, subprocess.SubprocessError):
        return False

    finally:
        try:
            if temporary.exists():
                temporary.unlink()
        except OSError:
            pass


def _collect_recent_items(
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for file_id, raw in state.get("events", {}).items():
        record = dict(raw or {})

        if record.get("status") != "downloaded":
            continue

        path_text = str(
            record.get("output_path") or ""
        )

        if not path_text:
            continue

        path = Path(path_text)

        try:
            item = path.stat()
        except OSError:
            continue

        if item.st_size <= 0:
            continue

        created = int(
            record.get("create_time") or 0
        )

        records.append(
            {
                "file_id": str(
                    record.get("file_id")
                    or file_id
                ),
                "path": str(path),
                "filename": path.name,
                "create_time": created,
                "local_time": str(
                    record.get("local_time") or ""
                ),
                "event_type": str(
                    record.get("event_type")
                    or "Motion"
                ),
                "size_bytes": item.st_size,
                "mtime_ns": item.st_mtime_ns,
            }
        )

    records.sort(
        key=lambda item: (
            int(item.get("create_time") or 0),
            int(item.get("mtime_ns") or 0),
        ),
        reverse=True,
    )

    return records[:RECENT_COUNT]


def _build_recent_items(
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    items = _collect_recent_items(state)
    previous_index = _load_thumbnail_index()
    next_index: dict[str, Any] = {}

    THUMBNAIL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for slot in range(1, RECENT_COUNT + 1):
        thumbnail = THUMBNAIL_DIR / (
            f"recent_{slot}.jpg"
        )

        if slot > len(items):
            try:
                if thumbnail.exists():
                    thumbnail.unlink()
            except OSError:
                pass
            continue

        item = items[slot - 1]
        item["slot"] = slot
        item["thumbnail_path"] = str(thumbnail)
        item["thumbnail_url"] = (
            f"/api/cw700s/recent/{slot}/thumbnail"
        )
        item["video_url"] = (
            f"/api/cw700s/recent/{slot}/video"
        )
        item["size_mb"] = round(
            int(item["size_bytes"]) / 1024 / 1024,
            2,
        )

        source_key = {
            "path": item["path"],
            "mtime_ns": item["mtime_ns"],
            "size_bytes": item["size_bytes"],
        }
        old_key = previous_index.get(str(slot), {})

        if (
            old_key != source_key
            or not thumbnail.exists()
            or thumbnail.stat().st_size <= 0
        ):
            ok = _generate_thumbnail(
                Path(item["path"]),
                thumbnail,
            )

            if not ok:
                try:
                    if thumbnail.exists():
                        thumbnail.unlink()
                except OSError:
                    pass

        next_index[str(slot)] = source_key

    _save_thumbnail_index(next_index)
    return items


def _recent_placeholder_svg(slot: int) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
<rect width="640" height="360" fill="#20252b"/>
<circle cx="320" cy="155" r="42" fill="none" stroke="#8da2b5" stroke-width="8"/>
<path d="M300 132 L350 155 L300 178 Z" fill="#8da2b5"/>
<text x="320" y="245" text-anchor="middle" fill="#d4dde5" font-family="sans-serif" font-size="24">最近告警 {slot}</text>
<text x="320" y="280" text-anchor="middle" fill="#8da2b5" font-family="sans-serif" font-size="18">暂无可用缩略图</text>
</svg>"""


async def _refresh_recent_items(
    hass: HomeAssistant,
) -> None:
    state = await hass.async_add_executor_job(
        _load_state
    )
    items = await hass.async_add_executor_job(
        _build_recent_items,
        state,
    )

    data = hass.data.setdefault(DOMAIN, {})
    data["recent_items"] = items

    for slot in range(1, RECENT_COUNT + 1):
        entity_id = f"sensor.cw700s_recent_{slot}"

        if slot <= len(items):
            item = items[slot - 1]
            local_time = str(item.get("local_time") or "")
            display_time = (
                local_time[5:]
                if len(local_time) >= 16
                else local_time
            )

            event_type = str(
                item.get("event_type") or "Motion"
            )
            state_text = (
                f"{display_time} · {event_type}"
                if display_time
                else event_type
            )

            hass.states.async_set(
                entity_id,
                state_text,
                {
                    "friendly_name": f"最近告警 {slot}",
                    "icon": "mdi:video-outline",
                    "event_type": item.get("event_type", "Motion"),
                    "event_time": local_time,
                    "filename": item.get("filename", ""),
                    "size_mb": item.get("size_mb", 0),
                    "thumbnail_url": item.get("thumbnail_url", ""),
                    "video_url": item.get("video_url", ""),
                    "slot": slot,
                },
            )
        else:
            hass.states.async_set(
                entity_id,
                "暂无录像",
                {
                    "friendly_name": f"最近告警 {slot}",
                    "icon": "mdi:video-off-outline",
                    "slot": slot,
                    "thumbnail_url": f"/api/cw700s/recent/{slot}/thumbnail",
                    "video_url": f"/api/cw700s/recent/{slot}/video",
                },
            )


def _recent_item(
    hass: HomeAssistant,
    slot_text: str,
) -> dict[str, Any] | None:
    try:
        slot = int(slot_text)
    except (TypeError, ValueError):
        return None

    if slot < 1 or slot > RECENT_COUNT:
        return None

    items = (
        hass.data
        .get(DOMAIN, {})
        .get("recent_items", [])
    )

    if slot > len(items):
        return None

    return items[slot - 1]


class CW700SRecentThumbnailView(HomeAssistantView):
    url = "/api/cw700s/recent/{slot}/thumbnail"
    name = "api:cw700s:recent:thumbnail"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request, slot):
        item = _recent_item(self.hass, slot)
        headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        }

        if item is not None:
            thumbnail = Path(
                str(item.get("thumbnail_path") or "")
            )

            try:
                if (
                    thumbnail.exists()
                    and thumbnail.stat().st_size > 0
                ):
                    return web.FileResponse(
                        thumbnail,
                        headers=headers,
                    )
            except OSError:
                pass

        try:
            slot_number = int(slot)
        except (TypeError, ValueError):
            slot_number = 0

        return web.Response(
            text=_recent_placeholder_svg(slot_number),
            content_type="image/svg+xml",
            headers=headers,
        )


class CW700SRecentVideoView(HomeAssistantView):
    url = "/api/cw700s/recent/{slot}/video"
    name = "api:cw700s:recent:video"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request, slot):
        item = _recent_item(self.hass, slot)

        if item is None:
            raise web.HTTPNotFound(
                text="该位置暂无录像",
            )

        video = Path(str(item.get("path") or ""))

        try:
            if not video.exists() or video.stat().st_size <= 0:
                raise web.HTTPNotFound(
                    text="录像文件不存在",
                )
        except OSError as error:
            raise web.HTTPNotFound(
                text=f"无法读取录像：{error}",
            ) from error

        filename = video.name.replace('"', "")

        return web.FileResponse(
            video,
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": (
                    f'inline; filename="{filename}"'
                ),
            },
        )


async def _initialize_dashboard(
    hass: HomeAssistant,
) -> None:
    await _refresh_idle_status(hass)
    await _refresh_recent_items(hass)


def _safe(value: str) -> str:
    value = re.sub(
        r'[\\/:*?"<>|]+',
        "_",
        str(value or "Motion"),
    )

    return value.strip(" ._") or "Motion"


def _resolve_entity(
    hass: HomeAssistant,
    entity_id: str,
):
    entities = (
        hass.data
        .get("xiaomi_miot", {})
        .get("entities", {})
    )

    entity = entities.get(entity_id)

    if entity is None:
        entity = next(
            (
                item
                for item in entities.values()
                if getattr(
                    item,
                    "entity_id",
                    None,
                ) == entity_id
            ),
            None,
        )

    if entity is None:
        raise HomeAssistantError(
            f"没有找到摄像头实体：{entity_id}"
        )

    return (
        getattr(entity, "parent_entity", None)
        or entity
    )


async def _query_day(
    entity,
    cloud,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    device = getattr(entity, "device", None)

    did = str(
        getattr(device, "did", "")
        or getattr(entity, "miot_did", "")
    )

    model = str(
        getattr(entity, "model", "")
        or ""
    )

    if not did:
        raise HomeAssistantError(
            "无法取得摄像头 DID"
        )

    api = cloud.get_api_by_host(
        "business.smartcamera.api.io.mi.com",
        "common/app/get/eventlist",
    )

    begin_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000) - 1

    common = {
        "did": did,
        "model": model,
        "doorBell": bool(
            getattr(entity, "is_doorbell", False)
        ),
        "eventType": "Default",
        "needMerge": True,
        "sortType": "DESC",
        "region": str(
            cloud.default_server
        ).upper(),
        "language": (
            locale.getlocale()[0]
            or "zh_CN"
        ),
        "endTime": end_ms,
    }

    cursor = end_ms
    pages = 0

    events: list[dict[str, Any]] = []
    seen: set[str] = set()

    while (
        cursor >= begin_ms
        and len(events) < MAX_EVENTS_PER_DAY
        and pages < 200
    ):
        pages += 1

        request = dict(common)
        request["beginTime"] = begin_ms
        request["endTime"] = cursor
        request["limit"] = min(
            20,
            MAX_EVENTS_PER_DAY - len(events),
        )

        response = await cloud.async_request_api(
            api,
            request,
            method="GET",
            crypt=True,
        ) or {}

        data = response.get("data") or {}

        for raw in (
            data.get("thirdPartPlayUnits")
            or []
        ):
            event = dict(raw or {})

            file_id = str(
                event.get("fileId")
                or ""
            )

            created = int(
                event.get("createTime")
                or 0
            )

            if not file_id:
                continue

            if file_id in seen:
                continue

            if not (
                begin_ms
                <= created
                <= end_ms
            ):
                continue

            seen.add(file_id)
            events.append(event)

        if not bool(data.get("isContinue")):
            break

        next_time = int(
            data.get("nextTime")
            or 0
        )

        if (
            next_time >= cursor
            or next_time < begin_ms
        ):
            break

        cursor = next_time - 1

        await asyncio.sleep(QUERY_PAGE_DELAY)

    events.sort(
        key=lambda item: int(
            item.get("createTime")
            or 0
        )
    )

    return events


async def _query_one_day(
    semaphore: asyncio.Semaphore,
    entity,
    cloud,
    day,
    now: datetime,
    timezone,
):
    start = datetime.combine(
        day,
        datetime.min.time(),
        tzinfo=timezone,
    )

    end = min(
        start + timedelta(days=1),
        now,
    )

    last_error: Exception | None = None

    for attempt in range(1, QUERY_RETRIES + 1):
        try:
            # 只限制真正发请求的部分；等待重试时不占用并发名额。
            async with semaphore:
                events = await asyncio.wait_for(
                    _query_day(
                        entity,
                        cloud,
                        start,
                        end,
                    ),
                    timeout=QUERY_DAY_TIMEOUT,
                )

            return day, events, None, attempt

        except Exception as error:
            last_error = error

            if attempt >= QUERY_RETRIES:
                break

            # 2、4、8 秒退避，并按日期轻微错开，避免同时重连。
            delay = (
                QUERY_RETRY_BASE_DELAY
                * (2 ** (attempt - 1))
                + (day.toordinal() % 5) * 0.2
            )
            await asyncio.sleep(delay)

    return day, [], last_error, QUERY_RETRIES


def _paths(
    timezone,
    event: dict[str, Any],
):
    file_id = str(
        event.get("fileId")
        or event.get("file_id")
        or ""
    )

    created = int(
        event.get("createTime")
        or event.get("create_time")
        or 0
    )

    event_type = str(
        event.get("eventType")
        or event.get("event_type")
        or "Motion"
    )

    event_time = datetime.fromtimestamp(
        created / 1000,
        timezone,
    )

    folder = (
        DESTINATION_ROOT
        / _safe(event_type)
        / event_time.strftime("%Y-%m-%d")
    )

    base = (
        f"{event_time:%H-%M-%S}_"
        f"{_safe(event_type)}"
    )

    # fileId 后八位用于避免同一秒出现两个事件时重名
    canonical = folder / (
        f"{base}_"
        f"{_safe(file_id)[-8:]}.mp4"
    )

    # 兼容之前已经下载的旧文件名
    legacy = folder / f"{base}.mp4"

    local_time = event_time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    return canonical, legacy, local_time


def _existing_file_size(
    canonical: Path,
    legacy: Path,
) -> int:
    try:
        if canonical.exists():
            size = canonical.stat().st_size

            if size > 0:
                return size

        if legacy.exists():
            size = legacy.stat().st_size

            if size > 0:
                canonical.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                # 将以前的文件自动改成带 fileId 的新名称
                legacy.replace(canonical)

                return size

    except OSError:
        return 0

    return 0


def _prepare_temporary(
    canonical: Path,
    temporary: Path,
) -> None:
    canonical.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if temporary.exists():
        temporary.unlink()


def _finalize_download(
    temporary: Path,
    canonical: Path,
) -> int:
    if not temporary.exists():
        return 0

    size = temporary.stat().st_size

    if size <= 0:
        return 0

    temporary.replace(canonical)
    return size


def _remove_file(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


async def _download_one(
    hass: HomeAssistant,
    entity,
    timezone,
    event: dict[str, Any],
    state: dict[str, Any],
) -> str:
    file_id = str(
        event.get("fileId")
        or event.get("file_id")
        or ""
    )

    created = int(
        event.get("createTime")
        or event.get("create_time")
        or 0
    )

    event_type = str(
        event.get("eventType")
        or event.get("event_type")
        or "Motion"
    )

    is_alarm = bool(
        event.get("isAlarm")
        or event.get("is_alarm")
    )

    if not file_id or not created:
        return "invalid"

    canonical, legacy, local_time = _paths(
        timezone,
        event,
    )

    record = state["events"].setdefault(
        file_id,
        {},
    )

    record.update(
        {
            "file_id": file_id,
            "create_time": created,
            "local_time": local_time,
            "event_type": event_type,
            "is_alarm": is_alarm,
            "output_path": str(canonical),
        }
    )

    existing_size = await hass.async_add_executor_job(
        _existing_file_size,
        canonical,
        legacy,
    )

    if existing_size > 0:
        record.update(
            {
                "status": "downloaded",
                "size_bytes": existing_size,
                "last_error": "",
            }
        )

        return "skipped"

    temporary = canonical.with_name(
        canonical.stem
        + ".downloading.mp4"
    )

    try:
        await hass.async_add_executor_job(
            _prepare_temporary,
            canonical,
            temporary,
        )

        stream_url = entity.get_alarm_m3u8_url(
            file_id,
            is_alarm,
        )

        if not stream_url:
            raise RuntimeError(
                "无法生成 M3U8 地址"
            )

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(DOWNLOADER),
            stream_url,
            str(temporary),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        try:
            output, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=DOWNLOAD_TIMEOUT,
            )

        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            output = b"download timeout"

        except asyncio.CancelledError:
            process.kill()
            await process.communicate()

            await hass.async_add_executor_job(
                _remove_file,
                temporary,
            )

            raise

        text = output.decode(
            "utf-8",
            errors="replace",
        )[-1500:]

        if process.returncode == 0:
            size = await hass.async_add_executor_job(
                _finalize_download,
                temporary,
                canonical,
            )

            if size > 0:
                record.update(
                    {
                        "status": "downloaded",
                        "size_bytes": size,
                        "last_error": "",
                    }
                )

                return "downloaded"

        await hass.async_add_executor_job(
            _remove_file,
            temporary,
        )

        record["status"] = "failed"
        record["last_error"] = (
            text
            or f"返回代码 {process.returncode}"
        )
        record["attempts"] = int(
            record.get("attempts", 0)
        ) + 1

        return "failed"

    except asyncio.CancelledError:
        raise

    except Exception as error:
        await hass.async_add_executor_job(
            _remove_file,
            temporary,
        )

        record["status"] = "failed"
        record["last_error"] = (
            f"{type(error).__name__}: {error}"
        )
        record["attempts"] = int(
            record.get("attempts", 0)
        ) + 1

        return "failed"


async def _download_limited(
    semaphore: asyncio.Semaphore,
    hass: HomeAssistant,
    entity,
    timezone,
    event: dict[str, Any],
    state: dict[str, Any],
):
    async with semaphore:
        result = await _download_one(
            hass,
            entity,
            timezone,
            event,
            state,
        )

        return event, result


async def _run_sync(
    hass: HomeAssistant,
    entity_id: str,
    force_full: bool,
) -> None:
    _set_status(
        hass,
        "准备中",
        stage="preparing",
        completed=0,
        total=0,
        progress_percent=0,
        last_error="",
    )

    if not DESTINATION_ROOT.exists():
        await _log(
            hass,
            "同步终止：网络存储不存在："
            f"{DESTINATION_ROOT}",
        )
        _set_status(
            hass,
            "错误",
            stage="error",
            last_error=f"网络存储不存在：{DESTINATION_ROOT}",
            storage_available=False,
        )
        return

    if not DOWNLOADER.exists():
        await _log(
            hass,
            "同步终止：下载脚本不存在："
            f"{DOWNLOADER}",
        )
        _set_status(
            hass,
            "错误",
            stage="error",
            last_error=f"下载脚本不存在：{DOWNLOADER}",
        )
        return

    entity = _resolve_entity(
        hass,
        entity_id,
    )

    device = getattr(
        entity,
        "device",
        None,
    )

    cloud = (
        getattr(device, "cloud", None)
        or getattr(
            entity,
            "xiaomi_cloud",
            None,
        )
    )

    if cloud is None:
        await _log(
            hass,
            "同步终止：摄像头没有可用的小米云连接",
        )
        _set_status(
            hass,
            "错误",
            stage="error",
            last_error="摄像头没有可用的小米云连接",
        )
        return

    timezone = (
        dt_util.get_time_zone(
            hass.config.time_zone
        )
        or dt_util.DEFAULT_TIME_ZONE
    )

    state = await hass.async_add_executor_job(
        _load_state
    )

    full = (
        force_full
        or not bool(
            state["meta"].get(
                "initial_sync_completed"
            )
        )
    )

    days = (
        INITIAL_DAYS
        if full
        else INCREMENTAL_DAYS
    )

    now = datetime.now(timezone)

    first_date = (
        now.date()
        - timedelta(days=days - 1)
    )

    candidates: dict[
        str,
        dict[str, Any],
    ] = {}

    query_failures = 0

    await _log(
        hass,
        (
            f"开始{'全量' if full else '增量'}同步："
            f"{first_date} 至 {now.date()}；"
            f"查询并发 {QUERY_CONCURRENCY}，"
            f"查询重试 {QUERY_RETRIES} 次，"
            f"下载并发 {DOWNLOAD_CONCURRENCY}"
        ),
    )

    _set_status(
        hass,
        "查询中",
        stage="querying",
        full_scan=full,
        scan_days=days,
        date_from=str(first_date),
        date_to=str(now.date()),
        completed=0,
        total=days,
        progress_percent=0,
        added=0,
        skipped=0,
        failed=0,
        query_failures=0,
    )

    days_to_query = [
        first_date + timedelta(days=offset)
        for offset in range(days)
    ]

    query_semaphore = asyncio.Semaphore(
        QUERY_CONCURRENCY
    )

    query_tasks = [
        asyncio.create_task(
            _query_one_day(
                query_semaphore,
                entity,
                cloud,
                day,
                now,
                timezone,
            )
        )
        for day in days_to_query
    ]

    query_results = await asyncio.gather(
        *query_tasks
    )

    # 按日期顺序写日志，结果更容易查看
    query_results.sort(
        key=lambda item: item[0]
    )

    for day, events, error, attempts in query_results:
        if error is not None:
            query_failures += 1

            await _log(
                hass,
                f"{day} 查询失败（已尝试 {attempts} 次）："
                f"{type(error).__name__}: {error}",
            )

            continue

        for event in events:
            file_id = str(
                event.get("fileId")
                or ""
            )

            if file_id:
                candidates[file_id] = event

        await _log(
            hass,
            (
                f"{day} 查询到 {len(events)} 条告警"
                + (f"（第 {attempts} 次成功）" if attempts > 1 else "")
            ),
        )

    _set_status(
        hass,
        "整理中",
        stage="preparing_downloads",
        completed=days,
        total=days,
        progress_percent=100,
        query_failures=query_failures,
        candidate_events=len(candidates),
    )

    # 自动重新尝试最近 35 天内下载失败的事件
    retry_cutoff = int(
        (
            now
            - timedelta(days=INITIAL_DAYS)
        ).timestamp()
        * 1000
    )

    for file_id, record in (
        state["events"].items()
    ):
        if (
            record.get("status")
            == "downloaded"
        ):
            continue

        if int(
            record.get("create_time")
            or 0
        ) < retry_cutoff:
            continue

        candidates.setdefault(
            file_id,
            dict(record),
        )

    ordered = sorted(
        candidates.values(),
        key=lambda item: int(
            item.get("createTime")
            or item.get("create_time")
            or 0
        ),
    )

    added = 0
    skipped = 0
    failed = 0
    invalid = 0
    completed = 0
    total = len(ordered)

    _set_status(
        hass,
        "下载中" if total else "整理中",
        stage="downloading" if total else "finalizing",
        completed=0,
        total=total,
        progress_percent=0 if total else 100,
        candidate_events=total,
        added=0,
        skipped=0,
        failed=0,
        invalid=0,
        query_failures=query_failures,
    )

    download_semaphore = asyncio.Semaphore(
        DOWNLOAD_CONCURRENCY
    )

    download_tasks = [
        asyncio.create_task(
            _download_limited(
                download_semaphore,
                hass,
                entity,
                timezone,
                event,
                state,
            )
        )
        for event in ordered
    ]

    try:
        for future in asyncio.as_completed(
            download_tasks
        ):
            event, result = await future
            completed += 1

            if result == "downloaded":
                added += 1
            elif result == "skipped":
                skipped += 1
            elif result == "failed":
                failed += 1
            else:
                invalid += 1

            progress_percent = (
                round(completed * 100 / total, 1)
                if total
                else 100
            )

            _set_status(
                hass,
                "下载中",
                stage="downloading",
                completed=completed,
                total=total,
                progress_percent=progress_percent,
                added=added,
                skipped=skipped,
                failed=failed,
                invalid=invalid,
                query_failures=query_failures,
            )

            # 分批写入状态，避免每条事件都重写整个 JSON。
            if (
                completed % STATE_SAVE_INTERVAL == 0
                or completed == total
            ):
                await _save_state_async(
                    hass,
                    state,
                )

            # 跳过大量已有文件时，不再每条都写日志。
            # 每 10 条报告一次进度，失败时立即报告。
            if (
                result == "failed"
                or completed % 10 == 0
                or completed == total
            ):
                created = int(
                    event.get("createTime")
                    or event.get("create_time")
                    or 0
                )

                when = (
                    datetime.fromtimestamp(
                        created / 1000,
                        timezone,
                    ).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if created
                    else "未知时间"
                )

                await _log(
                    hass,
                    (
                        f"[{completed}/{total}] "
                        f"最近完成 {when}：{result}；"
                        f"新增 {added}，"
                        f"跳过 {skipped}，"
                        f"失败 {failed}"
                    ),
                )

    finally:
        unfinished = [
            task
            for task in download_tasks
            if not task.done()
        ]

        for task in unfinished:
            task.cancel()

        if unfinished:
            await asyncio.gather(
                *unfinished,
                return_exceptions=True,
            )

    # 所有日期都成功查询后，才认为首次全量扫描完成
    if full and query_failures == 0:
        state["meta"][
            "initial_sync_completed"
        ] = True

    state["meta"]["last_sync_time"] = (
        now.isoformat(
            timespec="seconds"
        )
    )

    state["meta"][
        "last_query_failures"
    ] = query_failures

    state["meta"][
        "query_concurrency"
    ] = QUERY_CONCURRENCY

    state["meta"][
        "download_concurrency"
    ] = DOWNLOAD_CONCURRENCY

    await _save_state_async(
        hass,
        state,
    )

    await _log(
        hass,
        (
            "同步完成："
            f"候选 {total}，"
            f"新增 {added}，"
            f"跳过 {skipped}，"
            f"失败 {failed}，"
            f"无效 {invalid}，"
            f"查询失败日期 {query_failures}"
        ),
    )

    stats = await hass.async_add_executor_job(
        _scan_library_stats
    )

    _set_status(
        hass,
        "空闲" if failed == 0 and query_failures == 0 else "已完成，有异常",
        stage="idle",
        completed=total,
        total=total,
        progress_percent=100,
        added=added,
        skipped=skipped,
        failed=failed,
        invalid=invalid,
        query_failures=query_failures,
        last_sync_time=state["meta"].get("last_sync_time", ""),
        last_error="" if failed == 0 and query_failures == 0 else "请查看同步日志",
        **stats,
    )


    await _refresh_recent_items(hass)


async def _run_guarded(
    hass: HomeAssistant,
    entity_id: str,
    force_full: bool,
) -> None:
    try:
        await _run_sync(
            hass,
            entity_id,
            force_full,
        )

    except asyncio.CancelledError:
        await _log(
            hass,
            "同步任务已取消",
        )
        _set_status(
            hass,
            "已停止",
            stage="stopped",
            last_error="",
        )
        raise

    except Exception as error:
        await _log(
            hass,
            (
                "同步异常终止："
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )

        _LOGGER.exception(
            "CW700S sync failed"
        )

        _set_status(
            hass,
            "错误",
            stage="error",
            last_error=(
                f"{type(error).__name__}: {error}"
            ),
        )


async def async_setup(
    hass: HomeAssistant,
    config: dict,
) -> bool:
    data = hass.data.setdefault(
        DOMAIN,
        {},
    )

    data.setdefault("task", None)
    data.setdefault("recent_items", [])

    hass.http.register_view(
        CW700SRecentThumbnailView(hass)
    )
    hass.http.register_view(
        CW700SRecentVideoView(hass)
    )

    async def handle_sync(
        call: ServiceCall,
    ) -> None:
        current = data.get("task")

        if (
            current is not None
            and not current.done()
        ):
            raise HomeAssistantError(
                "CW700S 同步任务正在运行"
            )

        data["task"] = (
            hass.async_create_task(
                _run_guarded(
                    hass,
                    call.data["entity_id"],
                    call.data["full_scan"],
                ),
                "CW700S alarm video sync",
            )
        )

    async def handle_stop(
        call: ServiceCall,
    ) -> None:
        current = data.get("task")

        if current is None or current.done():
            await _refresh_idle_status(
                hass,
                status="空闲",
                message="当前没有正在运行的同步任务",
            )
            return

        _set_status(
            hass,
            "停止中",
            stage="stopping",
        )

        current.cancel()

        try:
            await current
        except asyncio.CancelledError:
            pass
        finally:
            data["task"] = None

    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC,
        handle_sync,
        schema=SYNC_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP,
        handle_stop,
        schema=vol.Schema({}),
    )

    hass.async_create_task(
        _initialize_dashboard(hass),
        "CW700S initialize dashboard and recent clips",
    )

    return True
