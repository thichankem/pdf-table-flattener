import os
from pathlib import Path
from typing import List, Optional


class Settings:
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
    ASSETS_DIR: Path = PROJECT_ROOT / "assets"
    FONTS_DIR: Path = ASSETS_DIR / "fonts"

    # Unicode-capable fonts, grouped by family so the renderer can match the
    # look of the table it replaces instead of always using one face.  The
    # bundled copies come first: they are the only entries guaranteed to exist
    # on every machine this is shipped to, and they render Vietnamese the same
    # way on all three platforms.  The system paths after them are what keeps a
    # checkout without assets/ working, so the lists cover Windows, macOS and
    # the usual Linux font packages.
    SERIF_FONT_CANDIDATES: List[Path] = [
        FONTS_DIR / "NotoSerif-Regular.ttf",
        # Windows
        Path("C:/Windows/Fonts/times.ttf"),
        # macOS
        Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf"),
        Path("/Library/Fonts/Times New Roman.ttf"),
        Path("/System/Library/Fonts/NewYork.ttf"),
        # Linux
        Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf"),
        Path("/usr/share/fonts/liberation/LiberationSerif-Regular.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSerif.ttf"),
        Path("/usr/share/fonts/noto/NotoSerif-Regular.ttf"),
    ]
    SANS_FONT_CANDIDATES: List[Path] = [
        FONTS_DIR / "NotoSans-Regular.ttf",
        # Windows
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        # macOS
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
        # Linux
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/noto/NotoSans-Regular.ttf"),
    ]

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
    def _any_bundled_font(cls) -> Optional[str]:
        """Any .ttf the user dropped into assets/fonts/ themselves."""
        try:
            for path in sorted(cls.FONTS_DIR.glob("*.ttf")):
                return str(path.resolve())
        except OSError:  # pragma: no cover - unreadable mount
            pass
        return None

    @classmethod
    def get_font_path(cls, serif: bool = True) -> str:
        primary = cls.SERIF_FONT_CANDIDATES if serif else cls.SANS_FONT_CANDIDATES
        fallback = cls.SANS_FONT_CANDIDATES if serif else cls.SERIF_FONT_CANDIDATES
        found = (
            cls._first_existing(primary)
            or cls._first_existing(fallback)
            or cls._any_bundled_font()
        )
        if found:
            return found
        raise RuntimeError(
            "No Unicode-capable TrueType font was found.\n"
            f"Copy a .ttf file into {cls.FONTS_DIR} "
            "(NotoSans-Regular.ttf, for example) so accented text renders.\n"
            "Re-running START_<your OS> downloads the Noto fonts automatically."
        )


settings = Settings()
