# assets/fonts

`tools/bootstrap.py` downloads `NotoSans-Regular.ttf` and `NotoSerif-Regular.ttf`
here on first run, so Vietnamese renders identically on Windows, macOS and Linux
instead of depending on whichever fonts the machine happens to have.

The download is best effort. If it fails, `src/pdf_table_tool/config.py` falls
back to the system fonts listed there, and any `.ttf` dropped into this folder
by hand is used as a final fallback.
