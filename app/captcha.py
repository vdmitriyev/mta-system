import base64
import io
import secrets
import string

from PIL import Image, ImageDraw, ImageFont

FONT_SIZE = 50
FONT_FILES = (
    "arial.ttf",
    "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)


def load_font():
    for font_file in FONT_FILES:
        try:
            return ImageFont.truetype(font_file, FONT_SIZE)
        except OSError:
            continue
    # font that comes with Pillow
    return ImageFont.load_default(size=FONT_SIZE)


def add_noise_arcs(draw, image):
    width, height = image.size
    rand_v1 = secrets.randbelow(width + 1)
    rand_v2 = width // 2 + secrets.randbelow(width // 2 + 1)
    draw.arc([-rand_v1, -rand_v1, width, rand_v1], 0, 295, fill=(0, 0, 0))
    draw.line([-rand_v1, rand_v1, width + rand_v1, height - rand_v1], fill=(0, 0, 0))
    draw.line([-rand_v2, 0, width + rand_v2, height], fill=(0, 0, 0))


def add_noise_dots(draw, image):
    width, height = image.size
    blue = 50 + secrets.randbelow(201)
    for _ in range(int(width * height * 0.2)):
        draw.point(
            (secrets.randbelow(width + 1), secrets.randbelow(height + 1)),
            fill=(0, 0, blue),
        )


def get_random_text(length: int = 4) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def convert_to_base64(image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def generate_captcha(add_noise: bool = False) -> tuple:
    """Creates a captcha. Returns its text and its image (PNG as base64)."""

    text = get_random_text(length=4)
    image = Image.new("RGB", (200, 150), color=(255, 255, 255))
    drawing = ImageDraw.Draw(image)

    if add_noise:
        add_noise_arcs(drawing, image)
        add_noise_dots(drawing, image)

    drawing.text((45, 50), text, font=load_font(), fill=(0, 0, 0))
    return text, convert_to_base64(image)
