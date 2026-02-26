# utils/audio_utils_optimized.py - Optimized version with local Whisper support

import os
import requests
import time
import tempfile
import assemblyai as aai
import httpx
import whisper
import hashlib
import json
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor

# Import Edge TTS (fast, free, cloud-based TTS)
try:
    from interview.utils.edge_tts_local import edge_tts_fast, edge_tts_generate, VOICE_OPTIONS, EDGE_TTS_AVAILABLE
    LOCAL_TTS_AVAILABLE = EDGE_TTS_AVAILABLE
except ImportError:
    LOCAL_TTS_AVAILABLE = False
    print("Edge TTS not available. Install with: pip install edge-tts")

# Import Real-time STT
# try:
#     from interview.utils.realtime_stt import transcribe_audio_file_streaming, ASSEMBLYAI_API_KEY as REALTIME_API_KEY
#     REALTIME_STT_AVAILABLE = bool(REALTIME_API_KEY)
# except ImportError:
#     REALTIME_STT_AVAILABLE = False
#     print("Real-time STT not available.")
REALTIME_STT_AVAILABLE = False

# Cache directories
CACHE_DIR = Path("./cache")
STT_CACHE_DIR = CACHE_DIR / "stt"
TTS_CACHE_DIR = CACHE_DIR / "tts"

# Create cache directories
STT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# API Keys
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

# Whisper models cache (loaded on demand)
WHISPER_MODELS = {}
WHISPER_LOCK = threading.Lock()

def get_whisper_model(model_size="base"):
    """Load Whisper model with thread safety"""
    global WHISPER_MODELS
    with WHISPER_LOCK:
        if model_size not in WHISPER_MODELS:
            print(f"Loading Whisper {model_size} model...")
            WHISPER_MODELS[model_size] = whisper.load_model(model_size)
    return WHISPER_MODELS[model_size]

# Supported STT models
SUPPORTED_WHISPER_MODELS = {
    "whisper_tiny": "tiny",
    "whisper_base": "base",
    "whisper_small": "small",
    "whisper_medium": "medium",
    "whisper_large": "large",
}

SUPPORTED_ASSEMBLY_MODELS = {
    "assemblyai_best": aai.SpeechModel.best,
}

DEFAULT_STT_MODEL = "whisper_base"


def transcribe_with_whisper(audio_file_path: str, model_key: str) -> tuple[str | None, str | None]:
    """Transcribe audio using the specified Whisper model."""
    model_size = SUPPORTED_WHISPER_MODELS.get(model_key, "base")
    try:
        model = get_whisper_model(model_size)
        result = model.transcribe(
            audio_file_path,
            language="en",
            temperature=0.0,
            fp16=False,
            verbose=False,
        )
        text = (result.get("text") or "").strip()
        if not text:
            return None, "Transcription returned empty text."
        return text, None
    except Exception as e:
        return None, str(e)


def transcribe_with_assembly(audio_file_path: str, model_key: str = "assemblyai_best", max_wait: int = 120) -> tuple[str | None, str | None]:
    """Transcribe audio using AssemblyAI."""
    if not ASSEMBLYAI_API_KEY:
        return None, "AssemblyAI API key not found"

    speech_model = SUPPORTED_ASSEMBLY_MODELS.get(model_key, aai.SpeechModel.best)

    try:
        config = aai.TranscriptionConfig(
            speech_model=speech_model,
            language_code="en",
            punctuate=True,
            format_text=True,
        )
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_file_path)

        if transcript.status == aai.TranscriptStatus.error:
            return None, f"Transcription error: {transcript.error}"

        text = (transcript.text or "").strip()
        if not text:
            return None, "Transcription returned empty text."

        return text, None
    except Exception as e:
        return None, str(e)


def get_audio_hash(audio_path):
    """Generate hash for audio file for caching"""
    with open(audio_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def get_text_hash(text):
    """Generate hash for text for caching"""
    return hashlib.md5(text.encode()).hexdigest()


def transcribe_audio_file_optimized(audio_file_path, stt_model: str = DEFAULT_STT_MODEL, max_wait: int = 120):
    """
    Optimized transcription supporting multiple STT backends.
    
    Args:
        audio_file_path (str): Path to the audio file
        stt_model (str): Selected STT model key
        max_wait (int): Maximum wait time in seconds (used for cloud services)
    
    Returns:
        tuple: (transcribed_text, error_message) or (None, error_message) if failed
    """
    stt_model = (stt_model or DEFAULT_STT_MODEL).lower()
    if stt_model not in SUPPORTED_WHISPER_MODELS and stt_model not in SUPPORTED_ASSEMBLY_MODELS:
        print(f"[WARNING] Unsupported STT model '{stt_model}', falling back to {DEFAULT_STT_MODEL}")
        stt_model = DEFAULT_STT_MODEL

    # Check cache first
    audio_hash = get_audio_hash(audio_file_path)
    cache_key = f"{audio_hash}_{stt_model}"
    cache_file = STT_CACHE_DIR / f"{cache_key}.json"
    
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
                if cached_data.get("model") == stt_model:
                    return cached_data['text'], None
        except:
            pass  # If cache read fails, continue with transcription
    
    text = None
    error = None
    # Browser recordings are often .webm; Whisper needs ffmpeg to decode them. Prefer AssemblyAI for webm when key is set.
    ext = (os.path.splitext(audio_file_path)[1] or "").lower()
    use_assembly_first_for_webm = ext in (".webm", ".ogg") and ASSEMBLYAI_API_KEY

    if stt_model in SUPPORTED_WHISPER_MODELS:
        if use_assembly_first_for_webm:
            print("Using AssemblyAI for .webm recording (no ffmpeg required)...")
            text, error = transcribe_with_assembly(audio_file_path, "assemblyai_best", max_wait)
            if error:
                print(f"[WARNING] AssemblyAI failed: {error}. Trying Whisper...")
                text, error = transcribe_with_whisper(audio_file_path, stt_model)
        else:
            print(f"Using {stt_model.replace('_', ' ').title()} for transcription...")
            text, error = transcribe_with_whisper(audio_file_path, stt_model)
            if error:
                print(f"[ERROR] Whisper ({stt_model}) failed: {error}. Falling back to AssemblyAI Best.")
                text, error = transcribe_with_assembly(audio_file_path, "assemblyai_best", max_wait)

    elif stt_model in SUPPORTED_ASSEMBLY_MODELS:
        print(f"Using {stt_model.replace('_', ' ').title()} for transcription...")
        text, error = transcribe_with_assembly(audio_file_path, stt_model, max_wait)

    if text and not error:
        try:
            with open(cache_file, 'w') as f:
                json.dump({'text': text, 'model': stt_model}, f)
        except Exception:
            pass
        return text, None

    return text, error or "Transcription failed"


def transcribe_audio_file(audio_file_path, stt_model: str = DEFAULT_STT_MODEL, max_wait: int = 120):
    """Backwards compatible wrapper for external callers."""
    return transcribe_audio_file_optimized(audio_file_path, stt_model=stt_model, max_wait=max_wait)


# TTS Caching and optimization
COMMON_PHRASES_CACHE = {}

def preload_common_phrases():
    """Preload common interview phrases for instant playback"""
    common_phrases = [
        "Hello! I'm your AI interviewer today. Let's begin with a brief introduction. Could you please tell me about yourself?",
        "Thank you for that introduction. Let me look at your resume for a moment.",
        "That's interesting. Can you elaborate on that?",
        "Thank you, that's it for today.",
        "I see. Let me ask you about a specific project from your resume.",
        "Could you tell me more about your experience with",
        "That's a great point. Now, let's move on to some technical questions.",
    ]
    
    # Use thread pool for parallel TTS generation
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        for phrase in common_phrases:
            future = executor.submit(_cache_phrase, phrase)
            futures.append((phrase, future))
        
        for phrase, future in futures:
            try:
                audio_path = future.result()
                if audio_path:
                    COMMON_PHRASES_CACHE[phrase[:50]] = audio_path
            except:
                pass


def _cache_phrase(text):
    """Helper to cache a single phrase"""
    text_hash = get_text_hash(text)
    cache_file = TTS_CACHE_DIR / f"{text_hash}.mp3"
    
    if not cache_file.exists():
        audio_path, error = elevenlabs_tts(text)
        if audio_path and not error:
            # Move to cache
            import shutil
            shutil.move(audio_path, str(cache_file))
            return str(cache_file)
    else:
        return str(cache_file)
    
    return None


def elevenlabs_tts_optimized(text, api_key=None, voice_id="andrew_multi", use_cache=True):
    """
    TTS using Edge TTS (fast, free, cloud-based replacement for ElevenLabs)
    
    Args:
        text (str): The text to convert to speech.
        api_key (str, optional): Ignored (kept for compatibility).
        voice_id (str): Voice name (andrew_multi, jenny, aria, etc.)
        use_cache (bool): Whether to use caching
    
    Returns:
        tuple: (audio_path, error_message) or (None, error_message) if failed
    """
    if not text:
        return None, "Empty text input"
    
    if not LOCAL_TTS_AVAILABLE:
        return None, "Edge TTS not available. Install with: pip install edge-tts"
    
    try:
        # Map voice_id to Edge TTS voice if it's a full voice ID
        if voice_id in VOICE_OPTIONS:
            voice_name = VOICE_OPTIONS[voice_id]
        else:
            # Default to andrew_multi if voice not found
            voice_name = VOICE_OPTIONS.get("andrew_multi", VOICE_OPTIONS.get("andrew", "en-US-AndrewMultilingualNeural"))
        
        # Use Edge TTS
        audio_path, error = edge_tts_generate(
            text=text,
            voice=voice_name,
            use_cache=use_cache
        )
        
        return audio_path, error
        
    except Exception as e:
        return None, f"TTS error: {str(e)}"


# Original function for compatibility
def elevenlabs_tts(text, api_key=None, voice_id="andrew_multi"):
    """TTS function (now using Edge TTS instead of ElevenLabs)"""
    return elevenlabs_tts_optimized(text, api_key, voice_id, use_cache=True)


# Initialize common phrases cache on module load (optional)
if LOCAL_TTS_AVAILABLE:
    # Uncomment to preload common phrases on startup
    # threading.Thread(target=preload_common_phrases, daemon=True).start()
    pass
