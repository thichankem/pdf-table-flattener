import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings:
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
    ASSETS_DIR: Path = PROJECT_ROOT / "assets"
    FONTS_DIR: Path = ASSETS_DIR / "fonts"

    # Windows native font fallback list for Vietnamese Unicode support
    DEFAULT_FONT_SEARCH_PATHS = [
        ASSETS_DIR / "fonts" / "NotoSans-Regular.ttf",
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/times.ttf"),
    ]

    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5vl:3b")

    # Font sizing & spacing for overlaying bullets
    BULLET_FONT_SIZE: float = 9.0
    BULLET_LINE_HEIGHT: float = 12.0
    BULLET_INDENT: float = 10.0

    @classmethod
    def get_font_path(cls) -> str:
        for font_path in cls.DEFAULT_FONT_SEARCH_PATHS:
            if font_path.exists():
                return str(font_path.resolve())
        # Return fallback if none found
        return "helv"

settings = Settings()
