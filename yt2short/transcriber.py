from faster_whisper import WhisperModel
from config import settings

_model = None


def _get_model():
    global _model
    if _model is None:
        print(f"Loading whisper model '{settings.whisper_model}' ({settings.whisper_device}, {settings.whisper_compute_type})...")
        _model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
    return _model


def transcribe(audio_path: str) -> dict:
    model = _get_model()
    segments, info = model.transcribe(audio_path, word_timestamps=True)

    words = []
    for seg in segments:
        for w in seg.words:
            words.append({
                "text": w.word.strip(),
                "start": round(w.start, 2),
                "end": round(w.end, 2),
                "probability": round(w.probability, 2),
            })

    return {
        "language": info.language,
        "duration": round(info.duration, 1),
        "words": words,
    }
