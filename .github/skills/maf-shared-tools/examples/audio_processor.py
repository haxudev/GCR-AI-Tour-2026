#!/usr/bin/env python3
"""Audio Processing Tool (skill example).

Provides deterministic, local audio utilities (ffmpeg/ffprobe required):
- check ffmpeg
- merge audio files
- convert audio
- get audio duration
- add background music

This file is a self-contained example used by the maf-shared-tools skill.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def check_ffmpeg() -> bool:
    """Check if ffmpeg is installed."""

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def merge_audio_files(input_files: list[str], output_file: str, silence_between_ms: int = 0) -> dict:
    """Merge multiple audio files into a single MP3 via ffmpeg."""

    if not check_ffmpeg():
        return {"status": "error", "message": "ffmpeg is not installed. Please install ffmpeg."}

    if not input_files:
        return {"status": "error", "message": "No input files provided"}

    existing_files = [f for f in input_files if os.path.exists(f)]
    if not existing_files:
        return {"status": "error", "message": "None of the input files exist"}

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if len(existing_files) == 1:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                existing_files[0],
                "-acodec",
                "libmp3lame",
                "-q:a",
                "2",
                output_file,
            ]
            subprocess.run(cmd, capture_output=True, check=True)
        else:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                concat_file = f.name

                for i, audio_file in enumerate(existing_files):
                    f.write(f"file '{os.path.abspath(audio_file)}'\n")

                    if silence_between_ms > 0 and i < len(existing_files) - 1:
                        silence_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
                        silence_duration = silence_between_ms / 1000.0

                        silence_cmd = [
                            "ffmpeg",
                            "-y",
                            "-f",
                            "lavfi",
                            "-i",
                            "anullsrc=r=16000:cl=mono",
                            "-t",
                            str(silence_duration),
                            "-acodec",
                            "libmp3lame",
                            silence_file,
                        ]
                        subprocess.run(silence_cmd, capture_output=True, check=True)
                        f.write(f"file '{silence_file}'\n")

            cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_file,
                "-acodec",
                "libmp3lame",
                "-q:a",
                "2",
                output_file,
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            os.unlink(concat_file)

        if os.path.exists(output_file):
            return {
                "status": "success",
                "output_file": output_file,
                "files_merged": len(existing_files),
                "message": f"Successfully merged {len(existing_files)} files into {output_file}",
            }
        return {"status": "error", "message": "Output file was not created"}

    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": f"ffmpeg error: {e.stderr.decode() if e.stderr else str(e)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def convert_audio(input_file: str, output_file: str, bitrate: str = "128k", sample_rate: int = 44100) -> dict:
    """Convert an audio file to MP3 via ffmpeg."""

    if not check_ffmpeg():
        return {"status": "error", "message": "ffmpeg is not installed. Please install ffmpeg."}

    if not os.path.exists(input_file):
        return {"status": "error", "message": f"Input file does not exist: {input_file}"}

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_file,
            "-acodec",
            "libmp3lame",
            "-b:a",
            bitrate,
            "-ar",
            str(sample_rate),
            output_file,
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        if os.path.exists(output_file):
            return {"status": "success", "output_file": output_file, "message": f"Successfully converted to {output_file}"}
        return {"status": "error", "message": "Output file was not created"}

    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": f"ffmpeg error: {e.stderr.decode() if e.stderr else str(e)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_audio_duration(file_path: str) -> dict:
    """Get the duration of an audio file in seconds via ffprobe."""

    if not check_ffmpeg():
        return {"status": "error", "message": "ffmpeg is not installed. Please install ffmpeg."}

    if not os.path.exists(file_path):
        return {"status": "error", "message": f"File does not exist: {file_path}"}

    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, check=True, text=True)
        duration = float(result.stdout.strip())

        return {
            "status": "success",
            "file": file_path,
            "duration_seconds": duration,
            "duration_formatted": f"{int(duration // 60)}:{int(duration % 60):02d}",
        }

    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": f"ffprobe error: {e.stderr if e.stderr else str(e)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def add_background_music(voice_file: str, music_file: str, output_file: str, music_volume: float = 0.15) -> dict:
    """Mix background music under voice track."""

    if not check_ffmpeg():
        return {"status": "error", "message": "ffmpeg is not installed. Please install ffmpeg."}

    if not os.path.exists(voice_file):
        return {"status": "error", "message": f"Voice file does not exist: {voice_file}"}

    if not os.path.exists(music_file):
        return {"status": "error", "message": f"Music file does not exist: {music_file}"}

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        duration_info = get_audio_duration(voice_file)
        if duration_info.get("status") != "success":
            return duration_info

        voice_duration = float(duration_info["duration_seconds"])

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            voice_file,
            "-stream_loop",
            "-1",
            "-i",
            music_file,
            "-filter_complex",
            f"[1:a]volume={music_volume},atrim=0:{voice_duration}[music];[0:a][music]amix=inputs=2:duration=first[out]",
            "-map",
            "[out]",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "2",
            output_file,
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        if os.path.exists(output_file):
            return {"status": "success", "output_file": output_file, "message": f"Successfully added background music to {output_file}"}
        return {"status": "error", "message": "Output file was not created"}

    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": f"ffmpeg error: {e.stderr.decode() if e.stderr else str(e)}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def register_tools(registry: object) -> None:
    """Register this module's callable tools into the example registry."""

    register = getattr(registry, "register_tool", None)
    if not callable(register):
        return

    register("audio.check_ffmpeg", check_ffmpeg)
    register("audio.merge_audio_files", merge_audio_files)
    register("audio.convert_audio", convert_audio)
    register("audio.get_audio_duration", get_audio_duration)
    register("audio.add_background_music", add_background_music)
