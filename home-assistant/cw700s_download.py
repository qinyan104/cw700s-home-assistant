#!/usr/bin/env python3

import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urljoin


def download(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read()


def run_ffmpeg(command: list[str]) -> None:
    result = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=90,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])


def main() -> int:
    if len(sys.argv) != 3:
        print("用法：cw700s_download.py <m3u8地址> <输出文件>")
        return 2

    playlist_url = sys.argv[1]
    output_file = Path(sys.argv[2])

    print("正在读取告警视频播放列表……")
    playlist = download(playlist_url).decode("utf-8", errors="replace")

    key_match = re.search(
        r'#EXT-X-KEY:METHOD=AES-128,URI="([^"]+)",IV=(?:0x)?([0-9a-fA-F]+)',
        playlist,
    )
    if not key_match:
        print("错误：没有找到 AES-128 密钥和 IV")
        return 1

    key_url = urljoin(playlist_url, key_match.group(1))
    iv_hex = key_match.group(2).zfill(32)

    segments = [
        urljoin(playlist_url, line.strip())
        for line in playlist.splitlines()
        if line.strip()
        and not line.strip().startswith("#")
    ]

    if not segments:
        print("错误：播放列表中没有视频片段")
        return 1

    key = download(key_url)
    if len(key) != 16:
        print(f"错误：AES 密钥长度异常：{len(key)} 字节")
        return 1

    ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"共发现 {len(segments)} 个视频片段。")

    with tempfile.TemporaryDirectory(prefix="cw700s_") as temp_name:
        temp_dir = Path(temp_name)
        decrypted_files: list[Path] = []

        for index, segment_url in enumerate(segments, start=1):
            segment_file = temp_dir / f"segment_{index:04d}.mp4"

            print(f"正在下载并解密：{index}/{len(segments)}")

            run_ffmpeg([
                ffmpeg,
                "-y",
                "-loglevel", "error",
                "-decryption_key", key.hex(),
                "-decryption_iv", iv_hex,
                "-i", f"crypto+{segment_url}",
                "-map", "0",
                "-c", "copy",
                str(segment_file),
            ])

            if not segment_file.exists() or segment_file.stat().st_size == 0:
                raise RuntimeError(f"第 {index} 个片段为空")

            decrypted_files.append(segment_file)

        concat_file = temp_dir / "concat.txt"

        with concat_file.open("w", encoding="utf-8") as file:
            for segment_file in decrypted_files:
                escaped = str(segment_file).replace("'", "'\\''")
                file.write(f"file '{escaped}'\n")

        print("正在合并全部视频片段……")

        run_ffmpeg([
            ffmpeg,
            "-y",
            "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-map", "0",
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_file),
        ])

    print(f"完整告警视频下载成功：{output_file}")
    print(f"文件大小：{output_file.stat().st_size} 字节")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"处理失败：{error}", file=sys.stderr)
        raise SystemExit(1)
