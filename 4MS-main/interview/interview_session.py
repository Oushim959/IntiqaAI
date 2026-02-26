"""
Interview Session Module for IntiqAI

This module manages interview sessions including audio handling
and timing instrumentation. Minimal Streamlit dependencies.
"""

import os
import sys
import time
from pathlib import Path
from typing import Tuple, Optional

# Ensure dir containing utils/ is on path (utils can be in parent or same dir as this file)
_this_dir = Path(__file__).resolve().parent
_parent = _this_dir.parent
for _d in (_parent, _this_dir):
    _s = str(_d)
    if _s not in sys.path:
        sys.path.insert(0, _s)

# Import audio utilities with fallback (utils may be in parent or same dir as this file)
def _load_audio_utils():
    try:
        from interview.utils.audio_utils_optimized import transcribe_audio_file_optimized as _t, elevenlabs_tts_optimized as _e
        return _t, _e, True
    except ImportError as e:
        print(f"DEBUG: Audio utils import failed: {e}")
        try:
            from interview.utils.audio_utils import transcribe_audio_file as _t, elevenlabs_tts as _e
            return _t, _e, False
        except ImportError as e2:
            print(f"DEBUG: Fallback audio utils import failed: {e2}")
            return None, None, False

_t, _e, USE_OPTIMIZED = _load_audio_utils()
transcribe_audio_file = _t
if _e is None:
    def elevenlabs_tts(text, api_key=None, voice_id="andrew", use_cache=True):
        return None, "Audio utils not available"
else:
    elevenlabs_tts = _e

# Check for pydub
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False


# ============================================================================
# AUDIO FUNCTIONS
# ============================================================================

def get_audio_duration(audio_path: str) -> float:
    """
    Get exact audio duration using pydub.

    Args:
        audio_path: Path to the audio file

    Returns:
        Duration in seconds
    """
    if not PYDUB_AVAILABLE:
        # Fallback: estimate from file size
        file_size_kb = os.path.getsize(audio_path) / 1024
        return max(file_size_kb / 50, 2)

    try:
        audio = AudioSegment.from_mp3(audio_path)
        duration_seconds = len(audio) / 1000
        return duration_seconds
    except Exception:
        file_size_kb = os.path.getsize(audio_path) / 1024
        return max(file_size_kb / 50, 2)


def prepare_audio_for_playback(audio_path: str) -> Tuple[Optional[bytes], str, float]:
    """
    Prepare audio for playback by reading the file and determining format.

    Args:
        audio_path: Path to the audio file

    Returns:
        Tuple of (audio_bytes, audio_format, duration_seconds)
        Returns (None, "", 0.0) if file doesn't exist
    """
    if not os.path.exists(audio_path):
        return None, "", 0.0

    try:
        # Get duration
        duration = get_audio_duration(audio_path)

        # Read audio file
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

        # Detect audio format
        file_ext = os.path.splitext(audio_path)[1].lower()
        audio_format = "audio/mp3" if file_ext == ".mp3" else "audio/wav"

        return audio_bytes, audio_format, duration

    except Exception:
        return None, "", 0.0


def transcribe_audio(
    audio_path: str,
    stt_model: str = "whisper_base",
    max_wait: int = 180
) -> Tuple[Optional[str], Optional[str]]:
    """
    Transcribe audio file to text.

    Args:
        audio_path: Path to the audio file
        stt_model: Speech-to-text model to use
        max_wait: Maximum wait time in seconds

    Returns:
        Tuple of (transcribed_text, error_message)
    """
    if transcribe_audio_file is None:
        return None, "Audio utils not available. Install utils.audio_utils or utils.audio_utils_optimized."
    if USE_OPTIMIZED:
        return transcribe_audio_file(audio_path, stt_model=stt_model, max_wait=max_wait)
    else:
        return transcribe_audio_file(audio_path, max_wait=max_wait)


def generate_tts(
    text: str,
    use_cache: bool = True
) -> Tuple[Optional[str], Optional[str]]:
    """
    Generate text-to-speech audio.

    Args:
        text: Text to convert to speech
        use_cache: Whether to use caching

    Returns:
        Tuple of (audio_path, error_message)
    """
    if USE_OPTIMIZED:
        return elevenlabs_tts(text, use_cache=use_cache)
    else:
        return elevenlabs_tts(text)
