import os
import subprocess
import threading
import logging
from flask import Flask, request, jsonify
import essentia.standard as es

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Aynı video_id için eşzamanlı analiz başlatılmasın
_in_progress = set()
_lock = threading.Lock()

TEMP_DIR = "/tmp/soniq-audio"
os.makedirs(TEMP_DIR, exist_ok=True)


def analyze_audio(video_id: str) -> dict:
    audio_path = os.path.join(TEMP_DIR, f"{video_id}.mp3")
    try:
        # İndir
        result = subprocess.run(
            [
                "yt-dlp",
                "-x", "--audio-format", "mp3",
                "--audio-quality", "5",       # düşük kalite yeterli, hızlı indirir
                "--no-playlist",
                "-o", audio_path,
                f"https://youtube.com/watch?v={video_id}",
            ],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp error: {result.stderr[-200:]}")

        # Analiz
        audio = es.MonoLoader(filename=audio_path, sampleRate=44100)()

        bpm, _, _, _, _ = es.RhythmExtractor2013(method='multifeature')(audio)
        key, scale, key_strength = es.KeyExtractor()(audio)
        dance, _ = es.Danceability()(audio)

        # Mood tahmini
        mood = _detect_mood(bpm, scale, dance)

        return {
            "video_id": video_id,
            "bpm": round(float(bpm), 1),
            "key": key,
            "scale": scale,
            "key_strength": round(float(key_strength), 2),
            "danceability": round(float(dance), 2),
            "mood": mood,
            "tags": [mood],
        }

    finally:
        # Her durumda dosyayı sil
        if os.path.exists(audio_path):
            os.remove(audio_path)
            log.info(f"[analyzer] deleted {audio_path}")


def _detect_mood(bpm: float, scale: str, dance: float) -> str:
    if bpm > 120 and dance > 1.5:
        return "enerjik"
    if scale == "minor" and bpm < 80:
        return "hüzünlü"
    if scale == "minor" and bpm < 110:
        return "melankolik"
    if scale == "major" and bpm > 110 and dance > 1.5:
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

    # Aynı anda aynı video_id için tek analiz
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
