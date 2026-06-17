from setuptools import setup, find_packages

setup(
    name="yt2shorts",
    version="1.0.0",
    packages=find_packages(),
    py_modules=["yt2shorts", "convert_cookies", "heatmap", "transcriber", "config", "downloader", "analyzer", "captions", "worker"],
    install_requires=[
        "yt-dlp>=2024.12.0",
        "google-genai>=1.14.0",
        "faster-whisper>=1.1.1",
        "httpx>=0.28.1",
        "pydantic-settings>=2.7.1",
        "fastapi>=0.115.6",
        "uvicorn[standard]>=0.34.0",
    ],
    entry_points={
        "console_scripts": [
            "yt2shorts=yt2shorts:main_interactive_cli",
        ],
    },
)
