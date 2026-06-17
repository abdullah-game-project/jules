from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    gemini_api_key: str = ""
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    clip_duration: int = 30
    clip_min_duration: int = 15
    clip_max_duration: int = 60
    max_clips: int = 5
    temp_dir: str = "./temp"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
