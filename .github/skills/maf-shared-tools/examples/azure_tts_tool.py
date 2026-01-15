#!/usr/bin/env python3
"""Azure Text-to-Speech (TTS) Tool (skill example).

This module converts text/SSML to speech using Azure Cognitive Services Speech SDK.
It is provided under the maf-shared-tools skill so `.github/**` can be self-contained.

Env:
- AZURE_SPEECH_KEY (required)
- AZURE_SPEECH_ENDPOINT (recommended) or AZURE_SPEECH_REGION/AZURE_LOCATION

Optional voice overrides:
- AZURE_SPEECH_GUEST_VOICE
- AZURE_SPEECH_HOST_VOICE
"""

from __future__ import annotations

import os
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape


VOICE_MAP = {
    "male_1": "zh-CN-YunxiNeural",
    "male_2": "zh-CN-YunjianNeural",
    "male_3": "zh-CN-YunyangNeural",
    "female_1": "zh-CN-XiaoxiaoNeural",
    "female_2": "zh-CN-XiaohanNeural",
    "female_3": "zh-CN-XiaomengNeural",
    "male_en": "en-US-GuyNeural",
    "female_en": "en-US-JennyNeural",
}

DEFAULT_MALE_VOICE = os.environ.get("AZURE_SPEECH_GUEST_VOICE") or "zh-CN-YunxiNeural"
DEFAULT_FEMALE_VOICE = os.environ.get("AZURE_SPEECH_HOST_VOICE") or "zh-CN-XiaoxiaoNeural"


def _lazy_import_speechsdk():
    try:
        import azure.cognitiveservices.speech as speechsdk  # type: ignore

        return speechsdk
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Azure Speech SDK not available. Install `azure-cognitiveservices-speech`.") from exc


def get_speech_config():
    speechsdk = _lazy_import_speechsdk()
    speech_key = os.environ.get("AZURE_SPEECH_KEY")
    speech_region = os.environ.get("AZURE_SPEECH_REGION")
    speech_endpoint = os.environ.get("AZURE_SPEECH_ENDPOINT")

    if not speech_key:
        raise ValueError("AZURE_SPEECH_KEY environment variable is not set")

    if speech_endpoint:
        return speechsdk.SpeechConfig(subscription=speech_key, endpoint=speech_endpoint)

    if not speech_region:
        speech_region = os.environ.get("AZURE_LOCATION")
    if speech_region:
        return speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)

    raise ValueError(
        "Missing Speech location config. Set AZURE_SPEECH_ENDPOINT (recommended) or AZURE_SPEECH_REGION/AZURE_LOCATION."
    )


def text_to_speech(text: str, output_file: str, voice_name: str = DEFAULT_FEMALE_VOICE, output_format: str = "mp3") -> dict:
    try:
        speechsdk = _lazy_import_speechsdk()
        speech_config = get_speech_config()
        speech_config.speech_synthesis_voice_name = voice_name

        if output_format.lower() == "mp3":
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
            )
        else:
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
            )

        audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

        result = synthesizer.speak_text_async(text).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return {"status": "success", "output_file": output_file, "voice": voice_name, "message": f"Audio saved to {output_file}"}

        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            error_msg = f"Speech synthesis canceled: {cancellation.reason}"
            if cancellation.reason == speechsdk.CancellationReason.Error:
                error_msg += f" - Error details: {cancellation.error_details}"
            return {"status": "error", "output_file": output_file, "message": error_msg}

        return {"status": "error", "output_file": output_file, "message": f"Unexpected result: {result.reason}"}

    except Exception as e:
        return {"status": "error", "output_file": output_file, "message": str(e)}


def text_to_speech_ssml(ssml: str, output_file: str, output_format: str = "mp3") -> dict:
    try:
        speechsdk = _lazy_import_speechsdk()
        speech_config = get_speech_config()

        if output_format.lower() == "mp3":
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3
            )
        else:
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
            )

        audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

        result = synthesizer.speak_ssml_async(ssml).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            return {"status": "success", "output_file": output_file, "message": f"Audio saved to {output_file}"}

        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            error_msg = f"Speech synthesis canceled: {cancellation.reason}"
            if cancellation.reason == speechsdk.CancellationReason.Error:
                error_msg += f" - Error details: {cancellation.error_details}"
            return {"status": "error", "output_file": output_file, "message": error_msg}

        return {"status": "error", "output_file": output_file, "message": f"Unexpected result: {result.reason}"}

    except Exception as e:
        return {"status": "error", "output_file": output_file, "message": str(e)}


def generate_podcast_with_ssml(
    dialogues: list[dict],
    output_file: str,
    male_voice: str = DEFAULT_MALE_VOICE,
    female_voice: str = DEFAULT_FEMALE_VOICE,
    pause_between_speakers_ms: int = 500,
) -> dict:
    ssml_parts = [
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="zh-CN">'
    ]

    for i, dialogue in enumerate(dialogues):
        speaker = str(dialogue.get("speaker", "female")).lower()
        text = str(dialogue.get("text", ""))
        if not text:
            continue

        voice = male_voice if speaker == "male" else female_voice
        safe_text = _xml_escape(text)
        pause = (
            f'<break time="{pause_between_speakers_ms}ms"/>'
            if (pause_between_speakers_ms and i < len(dialogues) - 1)
            else ""
        )
        ssml_parts.append(f'<voice name="{voice}">{safe_text}{pause}</voice>')

    ssml_parts.append("</speak>")
    ssml = "\n".join(ssml_parts)

    out = Path(output_file).expanduser()
    if not out.is_absolute():
        out = (Path.cwd() / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    return text_to_speech_ssml(ssml, str(out))


def list_available_voices() -> dict:
    return {
        "chinese_male": {
            "male_1": "zh-CN-YunxiNeural (云希 - 年轻男声)",
            "male_2": "zh-CN-YunjianNeural (云健 - 成熟男声)",
            "male_3": "zh-CN-YunyangNeural (云扬 - 新闻播报)",
        },
        "chinese_female": {
            "female_1": "zh-CN-XiaoxiaoNeural (晓晓 - 温暖女声)",
            "female_2": "zh-CN-XiaohanNeural (晓涵 - 知性女声)",
            "female_3": "zh-CN-XiaomengNeural (晓梦 - 活泼女声)",
        },
        "english_male": {"male_en": "en-US-GuyNeural"},
        "english_female": {"female_en": "en-US-JennyNeural"},
        "default_male": DEFAULT_MALE_VOICE,
        "default_female": DEFAULT_FEMALE_VOICE,
    }


def register_tools(registry: object) -> None:
    register = getattr(registry, "register_tool", None)
    if not callable(register):
        return

    register("tts.text_to_speech", text_to_speech)
    register("tts.text_to_speech_ssml", text_to_speech_ssml)
    register("tts.generate_podcast_with_ssml", generate_podcast_with_ssml)
    register("tts.list_available_voices", list_available_voices)
