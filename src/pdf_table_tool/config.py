import os
from pathlib import Path
from typing import List, Optional


class Settings:
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
    ASSETS_DIR: Path = PROJECT_ROOT / "assets"
    FONTS_DIR: Path = ASSETS_DIR / "fonts"

    # Unicode-capable fonts, grouped by family so the renderer can match the
    # look of the table it replaces instead of always using one face.
    SERIF_FONT_CANDIDATES: List[Path] = [
        FONTS_DIR / "NotoSerif-Regular.ttf",
        Path("C:/Windows/Fonts/times.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
        Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf"),
    ]
    SANS_FONT_CANDIDATES: List[Path] = [
        FONTS_DIR / "NotoSans-Regular.ttf",
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    ]

    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b")
    # LLM assistance is opt-in: the deterministic pipeline is already lossless,
    # so the model is only ever allowed to *improve* wording, never to drop text.
    USE_LLM: bool = os.getenv("PDF_FLATTENER_USE_LLM", "0") not in ("0", "", "false")

    # Bullet typography.
    BULLET_FONT_SIZE: float = 9.5
    MIN_FONT_SIZE: float = 6.5
    PAGE_TOP_MARGIN: float = 56.0
    PAGE_BOTTOM_MARGIN: float = 48.0

    @classmethod
    def _first_existing(cls, candidates: List[Path]) -> Optional[str]:
        for path in candidates:
            try:
                if path.exists():
                    return str(path.resolve())
            except OSError:  # pragma: no cover - unreadable mount
                continue
        return None

    @classmethod
    def get_font_path(cls, serif: bool = True) -> str:
        primary = cls.SERIF_FONT_CANDIDATES if serif else cls.SANS_FONT_CANDIDATES
        fallback = cls.SANS_FONT_CANDIDATES if serif else cls.SERIF_FONT_CANDIDATES
        found = cls._first_existing(primary) or cls._first_existing(fallback)
        if found:
            return found
        raise RuntimeError(
            "No Unicode TrueType font found. Place a .ttf in assets/fonts/ "
            "(e.g. NotoSans-Regular.ttf) so Vietnamese text can be rendered."
        )


settings = Settings()
