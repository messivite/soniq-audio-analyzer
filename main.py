import os
import subprocess
import threading
import logging
import numpy as np
import librosa
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

_in_progress = set()
_lock = threading.Lock()

TEMP_DIR = "/tmp/soniq-audio"
os.makedirs(TEMP_DIR, exist_ok=True)


def analyze_audio(video_id: str) -> dict:
    audio_path = os.path.join(TEMP_DIR, f"{video_id}.mp3")
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-x", "--audio-format", "mp3",
                "--audio-quality", "5",
                "--no-playlist",
                "-o", audio_path,
                f"https://youtube.com/watch?v={video_id}",
            ],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp error: {result.stderr[-200:]}")

        y, sr = librosa.load(audio_path, sr=22050, mono=True, duration=120)

        # BPM
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo[0]) if hasattr(tempo, '__len__') else float(tempo)

        # Key
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = chroma.mean(axis=1)
        key_idx = int(np.argmax(chroma_mean))
        key_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        key = key_names[key_idx]

        # Majör/minör tahmini (kromatik enerji dağılımı)
        major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        major_corr = np.corrcoef(chroma_mean, np.roll(major_profile, key_idx))[0, 1]
        minor_corr = np.corrcoef(chroma_mean, np.roll(minor_profile, key_idx))[0, 1]
        scale = "minor" if minor_corr > major_corr else "major"

        # Danceability proxy (beat strength)
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        dance = float(np.mean(onset_env) / (np.std(onset_env) + 1e-6))

        mood = _detect_mood(bpm, scale, dance)

        return {
            "video_id": video_id,
            "bpm": round(bpm, 1),
            "key": key,
            "scale": scale,
            "danceability": round(dance, 2),
            "mood": mood,
            "tags": [mood],
        }

    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)
            log.info(f"[analyzer] deleted {audio_path}")


def _detect_mood(bpm: float, scale: str, dance: float) -> str:
    if bpm > 120 and dance > 2.0:
        return "enerjik"
    if scale == "minor" and bpm < 80:
        return "hüzünlü"
    if scale == "minor" and bpm < 110:
        return "melankolik"
    if scale == "major" and bpm > 110 and dance > 2.0:
        return "neşeli"
    if bpm < 75:
        return "sakin"
    if scale == "major" and bpm < 100:
        return "romantik"
    return "dinamik"


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    if not data or not data.get("video_id"):
        return jsonify({"error": "video_id required"}), 400

    video_id = data["video_id"].strip()

    with _lock:
        if video_id in _in_progress:
            return jsonify({"error": "already processing", "video_id": video_id}), 409
        _in_progress.add(video_id)

    try:
        log.info(f"[analyzer] start {video_id}")
        result = analyze_audio(video_id)
        log.info(f"[analyzer] done {video_id} → {result['mood']}")
        return jsonify(result)
    except Exception as e:
        log.error(f"[analyzer] error {video_id}: {e}")
        return jsonify({"error": str(e), "video_id": video_id}), 500
    finally:
        with _lock:
            _in_progress.discard(video_id)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8090))
    app.run(host="0.0.0.0", port=port)
