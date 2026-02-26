# utils/edge_tts_local.py - Microsoft Edge TTS (FREE, Python 3.12 compatible)

import os
import asyncio
import hashlib
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    print("Edge TTS not installed. Install with: pip install edge-tts")

# Cache directory
EDGE_CACHE_DIR = Path("./cache/tts_edge")
EDGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Voice options - Best for interviews
VOICE_OPTIONS = {
    # Professional & Clear (Best for formal interviews)
    "aria": "en-US-AriaNeural",             # Female - Crisp, Bright, Clear
    "andrew": "en-US-AndrewNeural",         # Male - Confident, Authentic, Warm
    "andrew_multi": "en-US-AndrewMultilingualNeural",  # Male - Multilingual, Natural, Expressive
    "guy": "en-US-GuyNeural",               # Male - Light-Hearted, Whimsical, Friendly
    
    # Warm & Friendly (Best for casual interviews)
    "jenny": "en-US-JennyNeural",           # Female - Sincere, Pleasant, Approachable ⭐ DEFAULT
    "ava": "en-US-AvaNeural",               # Female - Pleasant, Caring, Friendly
    "eric": "en-US-EricNeural",             # Male - Confident, Sincere, Warm
    "emma": "en-US-EmmaNeural",             # Female - Cheerful, Light-Hearted, Casual
    
    # Professional & Mature
    "michelle": "en-US-MichelleNeural",     # Female - Confident, Authentic, Warm
    "brian": "en-US-BrianNeural",           # Male - Sincere, Calm, Approachable
    "sara": "en-US-SaraNeural",             # Female - Sincere, Calm, Confident
    
    # British Accent
    "sonia": "en-GB-SoniaNeural",           # Female - Gentle, Soft
    "ryan": "en-GB-RyanNeural",             # Male - Bright, Engaging
    
    # AI-Generated (Formal)
    "ai_female": "en-US-AIGenerate2Neural", # Female - Serious, Mature, Formal
    "ai_male": "en-US-AIGenerate1Neural",   # Male - Serious, Clear, Formal
}

# Default voice for interviews - Change this to switch the voice globally
DEFAULT_VOICE = VOICE_OPTIONS["andrew_multi"]  # Male - Multilingual, Natural, Expressive


def get_text_hash(text, voice):
    """Generate hash for caching"""
    return hashlib.md5(f"{text}_{voice}".encode('utf-8')).hexdigest()


async def _generate_speech_async(text, output_file, voice, rate, volume):
    """Async speech generation"""
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        volume=volume
    )
    await communicate.save(output_file)


def edge_tts_generate(
    text,
    voice=DEFAULT_VOICE,
    rate="+5%",  # Slightly faster for natural conversation
    volume="+0%",
    use_cache=True
):
    """
    Generate speech using Microsoft Edge TTS (FREE, unlimited)
    
    Args:
        text (str): Text to convert to speech
        voice (str): Voice to use (see VOICE_OPTIONS)
        rate (str): Speech rate (e.g., "+10%" faster, "-10%" slower)
        volume (str): Volume adjustment (e.g., "+10%" louder)
        use_cache (bool): Whether to use caching
    
    Returns:
        tuple: (audio_path, error_message) or (None, error_message) if failed
    """
    if not EDGE_TTS_AVAILABLE:
        return None, "Edge TTS not installed. Install with: pip install edge-tts"
    
    if not text or text.strip() == "":
        return None, "Empty text input"
    
    try:
        # Check cache first
        if use_cache:
            text_hash = get_text_hash(text, voice)
            cache_file = EDGE_CACHE_DIR / f"{text_hash}.mp3"
            
            if cache_file.exists():
                return str(cache_file), None
        
        # Generate speech
        output_path = str(cache_file) if use_cache else tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
        
        # Run async TTS in a separate thread so it works when called from FastAPI/uvicorn
        # (asyncio.run() cannot be used when the main thread already has a running event loop)
        def _run_tts():
            asyncio.run(_generate_speech_async(text, output_path, voice, rate, volume))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_tts)
            future.result(timeout=120)
        
        return output_path, None
        
    except Exception as e:
        return None, f"Edge TTS error: {str(e)}"


def edge_tts_fast(text, use_cache=True):
    """
    Quick wrapper with optimized defaults for interview responses
    
    Args:
        text (str): Text to convert to speech
        use_cache (bool): Whether to use caching
    
    Returns:
        tuple: (audio_path, error_message)
    """
    return edge_tts_generate(
        text=text,
        voice=DEFAULT_VOICE,
        rate="+8%",  # Slightly faster for more dynamic conversation
        volume="+5%",  # Slightly louder for clarity
        use_cache=use_cache
    )


def list_available_voices():
    """
    List all available Edge TTS voices
    
    Returns:
        list: Available voice names
    """
    if not EDGE_TTS_AVAILABLE:
        return []
    
    def _fetch():
        return asyncio.run(edge_tts.list_voices())
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            voices = pool.submit(_fetch).result(timeout=30)
        return [v["Name"] for v in voices if v["Locale"].startswith("en-")]
    except Exception:
        return list(VOICE_OPTIONS.values())


# Preload common interview phrases for instant responses
def preload_common_phrases(voice=DEFAULT_VOICE):
    """Preload common phrases for instant playback"""
    if not EDGE_TTS_AVAILABLE:
        return
    
    common_phrases = [
        "Hello! I'm your AI interviewer today. Let's begin with a brief introduction.",
        "That's interesting. Can you tell me more about that?",
        "Thank you for sharing that with me.",
        "Could you elaborate on that point?",
        "That's a great answer. Let's move on to the next question.",
        "Thank you. That's it for today.",
    ]
    
    print(f"Preloading common phrases with {voice}...")
    success = 0
    for phrase in common_phrases:
        try:
            result, error = edge_tts_generate(phrase, voice=voice, use_cache=True)
            if result:
                success += 1
        except:
            pass
    print(f"Preloaded {success}/{len(common_phrases)} phrases!")


# Test function
def test_edge_tts():
    """Test Edge TTS installation and functionality"""
    print("Testing Edge TTS...")
    
    if not EDGE_TTS_AVAILABLE:
        print("[X] Edge TTS not installed")
        print("Install with: pip install edge-tts")
        return False
    
    print("[OK] Edge TTS is installed")
    
    test_text = "Hello! This is a test of Microsoft Edge Text to Speech."
    print(f"Generating test audio: '{test_text}'")
    
    audio_path, error = edge_tts_fast(test_text)
    
    if error:
        print(f"[ERROR] {error}")
        return False
    
    print(f"[SUCCESS] Audio generated: {audio_path}")
    print(f"File size: {os.path.getsize(audio_path) / 1024:.2f} KB")
    
    return True


if __name__ == "__main__":
    # Run test when module is executed directly
    test_edge_tts()

