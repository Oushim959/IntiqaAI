import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
API_DIR = ROOT / "gui"
FKA_DIR = ROOT / "fka"

# Load .env from ROOT (same folder as run_all.py) so subprocesses get SMTP_*, GOOGLE_API_KEY, etc.
def _load_root_env():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        from dotenv import dotenv_values
        for k, v in dotenv_values(env_path).items():
            if k and v is not None:
                os.environ[k] = str(v)
    except Exception:
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except Exception:
            pass


# So the API subprocess can import utils and has .env vars (SMTP_*, etc.)
def _api_env():
    _load_root_env()
    env = os.environ.copy()
    root_str = str(ROOT)
    env["PYTHONPATH"] = root_str + os.pathsep + env.get("PYTHONPATH", "")
    # Prepend ffmpeg bin if present (winget Gyan.FFmpeg) so pydub/whisper find it
    winget_packages = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    ffmpeg_bin = os.path.join(winget_packages, "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe", "ffmpeg-8.0.1-full_build", "bin")
    if os.path.isdir(ffmpeg_bin):
        env["PATH"] = ffmpeg_bin + os.pathsep + env.get("PATH", "")
    return env


def main() -> None:
    """
    Start BOTH servers (IntiqAI GUI + FKA web app) from a single command.

    - IntiqAI GUI (CV filtering, HR, login): http://127.0.0.1:8001
    - FKA web app (JD/CV upload, questions, evaluation): http://127.0.0.1:8500

    Usage (from an activated venv, in this same directory):
        python run_all.py

    If you get 404 on new API routes (e.g. delete run): stop this script (Ctrl+C)
    and run it again so the latest api.py is loaded.
    """

    python = sys.executable

    processes = [
        subprocess.Popen(
            [
                python,
                "-m",
                "uvicorn",
                "api:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8001",
                "--reload",
            ],
            cwd=str(API_DIR),
            env=_api_env(),
        ),
        subprocess.Popen(
            [
                python,
                "-m",
                "uvicorn",
                "web_app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8500",
                "--reload",
            ],
            cwd=str(FKA_DIR),
            env=_api_env(),
        ),
    ]

    try:
        # Wait for both processes; if either exits, we exit.
        for p in processes:
            p.wait()
    except KeyboardInterrupt:
        # Gracefully terminate both on Ctrl+C
        for p in processes:
            p.terminate()


if __name__ == "__main__":
    main()

