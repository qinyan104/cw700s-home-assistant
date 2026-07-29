#!/usr/bin/env python3
"""CW700S health probe for Home Assistant command_line sensor."""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

ROOT = Path('/media/Windows_CW700S')
STATE_FILE = Path('/config/cw700s_sync_state.json')
WARNING_FREE_GB = 10.0
CRITICAL_FREE_GB = 5.0
STALE_HOURS = 36.0

def _load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {'meta': {}, 'events': {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            return {'meta': {}, 'events': {}}
        data.setdefault('meta', {})
        data.setdefault('events', {})
        return data
    except (OSError, ValueError):
        return {'meta': {}, 'events': {}}

def _hours_since(value: str) -> float | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    return max(0.0, (now - dt).total_seconds() / 3600)

def main() -> None:
    result: dict[str, Any] = {
        'status': '异常',
        'problem_summary': '健康检查尚未完成',
        'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'share_online': False,
        'share_writable': False,
        'free_gb': 0.0,
        'total_gb': 0.0,
        'used_percent': 0.0,
        'last_sync_time': '',
        'hours_since_sync': None,
        'query_failures': 0,
        'failed_events': 0,
        'downloaded_events': 0,
        'total_event_records': 0,
    }
    critical: list[str] = []
    warning: list[str] = []

    result['share_online'] = ROOT.exists() and ROOT.is_dir()
    if not result['share_online']:
        critical.append('Windows 共享目录不可用')
    else:
        probe_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', encoding='utf-8', prefix='.cw700s_health_', suffix='.tmp',
                dir=ROOT, delete=False,
            ) as probe:
                probe.write('ok')
                probe_path = Path(probe.name)
            result['share_writable'] = True
        except OSError as exc:
            critical.append(f'Windows 共享不可写：{exc}')
        finally:
            if probe_path is not None:
                try:
                    probe_path.unlink(missing_ok=True)
                except OSError:
                    pass

        try:
            usage = shutil.disk_usage(ROOT)
            total_gb = usage.total / (1024 ** 3)
            free_gb = usage.free / (1024 ** 3)
            used_percent = ((usage.total - usage.free) / usage.total * 100) if usage.total else 0.0
            result['total_gb'] = round(total_gb, 2)
            result['free_gb'] = round(free_gb, 2)
            result['used_percent'] = round(used_percent, 1)
            if free_gb < CRITICAL_FREE_GB:
                critical.append(f'Windows 磁盘仅剩 {free_gb:.1f} GB')
            elif free_gb < WARNING_FREE_GB:
                warning.append(f'Windows 磁盘仅剩 {free_gb:.1f} GB')
        except OSError as exc:
            warning.append(f'无法读取磁盘空间：{exc}')

    state = _load_state()
    meta = state.get('meta') or {}
    events = state.get('events') or {}
    last_sync_time = str(meta.get('last_sync_time') or '')
    hours_since_sync = _hours_since(last_sync_time)
    result['last_sync_time'] = last_sync_time
    result['hours_since_sync'] = round(hours_since_sync, 1) if hours_since_sync is not None else None
    result['query_failures'] = int(meta.get('last_query_failures') or 0)

    failed_events = 0
    downloaded_events = 0
    if isinstance(events, dict):
        for record in events.values():
            if not isinstance(record, dict):
                continue
            status = str(record.get('status') or '')
            if status == 'failed':
                failed_events += 1
            elif status == 'downloaded':
                downloaded_events += 1
    result['failed_events'] = failed_events
    result['downloaded_events'] = downloaded_events
    result['total_event_records'] = len(events) if isinstance(events, dict) else 0

    if not last_sync_time:
        warning.append('还没有同步时间记录')
    elif hours_since_sync is None:
        warning.append('无法解析最近同步时间')
    elif hours_since_sync > STALE_HOURS:
        warning.append(f'距离上次同步已 {hours_since_sync:.1f} 小时')
    if result['query_failures'] > 0:
        warning.append(f"上次同步有 {result['query_failures']} 个日期查询失败")
    if failed_events > 0:
        warning.append(f'状态文件中还有 {failed_events} 条下载失败记录')

    if critical:
        result['status'] = '异常'
        result['problem_summary'] = '；'.join(critical + warning)
    elif warning:
        result['status'] = '警告'
        result['problem_summary'] = '；'.join(warning)
    else:
        result['status'] = '正常'
        result['problem_summary'] = '共享、磁盘和同步状态均正常'

    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            'status': '异常',
            'problem_summary': f'健康检查脚本异常：{type(exc).__name__}: {exc}',
            'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }, ensure_ascii=False, separators=(',', ':')))
