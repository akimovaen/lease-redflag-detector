"""OCR of scanned PDFs with Poppler and Tesseract, cached next to the PDF.

Needs `pdftoppm` (`brew install poppler`) and `tesseract` with the Ukrainian model
(`ukr.traineddata`) on the PATH. The text of `<dir>/contract.pdf` is cached as
`<dir>/text.txt`; delete it to read the scan again.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

DPI = 300
LANGUAGES = "ukr+eng"


def ocr_pdf(pdf: Path, languages: str = LANGUAGES) -> str:
    cached = pdf.with_name("text.txt")
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    for tool in ("pdftoppm", "tesseract"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} not found; install poppler and tesseract")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["pdftoppm", "-r", str(DPI), "-gray", "-png", str(pdf), f"{tmp}/p"],
            check=True,
        )
        pages = [
            subprocess.run(
                ["tesseract", str(page), "stdout", "-l", languages],
                capture_output=True,
                check=True,
                text=True,
            ).stdout
            for page in sorted(Path(tmp).glob("p-*.png"))
        ]
    text = "\n".join(pages)
    cached.write_text(text, encoding="utf-8")
    return text
