"""Simulate a printed and scanned lease, then read it back with OCR.

Pages are rendered as images, degraded like a cheap office scan (skew, blur,
specks, low contrast, JPEG artifacts) and passed to Tesseract.
"""

import io
import random
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

DPI = 150
PAGE_SIZE = (1275, 1650)  # US Letter at 150 DPI
MARGIN = 120
FONT_SIZE = 21  # about 10 pt at 150 DPI
LINE_HEIGHT = 28
PARAGRAPH_GAP = 10
FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
]


@dataclass(frozen=True)
class Noise:
    name: str
    max_skew: float  # degrees
    blur: float  # Gaussian blur radius
    speck_share: float  # share of pixels turned into dark specks
    downscale: float  # scan resolution relative to the page
    contrast: float  # 1.0 keeps the original contrast
    jpeg_quality: int


NOISE_LEVELS = {
    "light": Noise("light", 0.5, 0.6, 0.0003, 1.0, 0.9, 60),
    "medium": Noise("medium", 1.0, 0.8, 0.002, 0.75, 0.8, 45),
    "heavy": Noise("heavy", 1.5, 0.9, 0.004, 0.7, 0.7, 35),
}


def load_font() -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        if Path(path).exists():
            return ImageFont.truetype(path, FONT_SIZE)
    return ImageFont.load_default(FONT_SIZE)


def wrap(paragraph: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in paragraph.split():
        candidate = f"{current} {word}".strip()
        if current and font.getlength(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    return [*lines, current] if current else lines


def render_pages(paragraphs: list[str]) -> list[Image.Image]:
    font = load_font()
    width = PAGE_SIZE[0] - 2 * MARGIN
    bottom = PAGE_SIZE[1] - MARGIN
    pages: list[Image.Image] = []
    page = draw = None
    y = bottom

    def new_page() -> None:
        nonlocal page, draw, y
        page = Image.new("L", PAGE_SIZE, 255)
        draw = ImageDraw.Draw(page)
        footer = f"- {len(pages) + 1} -"
        footer_x = (PAGE_SIZE[0] - font.getlength(footer)) / 2
        draw.text((footer_x, bottom + 40), footer, font=font, fill=0)
        pages.append(page)
        y = MARGIN

    for paragraph in paragraphs:
        for line in wrap(paragraph, font, width):
            if y + LINE_HEIGHT > bottom:
                new_page()
            draw.text((MARGIN, y), line, font=font, fill=0)
            y += LINE_HEIGHT
        y += PARAGRAPH_GAP
    return pages


def degrade(page: Image.Image, noise: Noise, rng: random.Random) -> Image.Image:
    width, height = page.size
    scanned = page.rotate(
        rng.uniform(-noise.max_skew, noise.max_skew), fillcolor=255, expand=False
    )
    scanned = scanned.filter(ImageFilter.GaussianBlur(noise.blur))

    speck_count = round(width * height * noise.speck_share)
    specks = [(rng.randrange(width), rng.randrange(height)) for _ in range(speck_count)]
    ImageDraw.Draw(scanned).point(specks, fill=0)

    scanned = ImageEnhance.Contrast(scanned).enhance(noise.contrast)
    if noise.downscale < 1.0:
        small = (round(width * noise.downscale), round(height * noise.downscale))
        scanned = scanned.resize(small, Image.Resampling.BILINEAR)
        scanned = scanned.resize(page.size, Image.Resampling.BILINEAR)

    buffer = io.BytesIO()
    scanned.save(buffer, "JPEG", quality=noise.jpeg_quality)
    return Image.open(buffer).convert("L")


def ocr(page: Image.Image) -> str:
    tesseract = shutil.which("tesseract")
    if tesseract is None:
        raise RuntimeError(
            "tesseract not found; install it with `brew install tesseract`"
        )
    buffer = io.BytesIO()
    page.save(buffer, "PNG", dpi=(DPI, DPI))
    result = subprocess.run(
        [tesseract, "stdin", "stdout", "-l", "eng"],
        input=buffer.getvalue(),
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8")


def scan(paragraphs: list[str], noise: Noise, seed: int, pdf_path: Path) -> str:
    """Renders, degrades and OCRs a document; saves the scan as a PDF."""
    rng = random.Random(seed)
    pages = [degrade(page, noise, rng) for page in render_pages(paragraphs)]
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(pdf_path, save_all=True, append_images=pages[1:], resolution=DPI)
    text = "\n".join(ocr(page) for page in pages)
    return text.replace("\f", "").strip() + "\n"
