# -*- coding: utf-8 -*-

import io
import os
import string
import random
import base64
from PIL import Image, ImageDraw, ImageFont

def add_noise_arcs(draw, image):
    size = image.size
    rand_v1 = random.randint(0, size[0])
    rand_v2 = random.randint(size[0]/2, size[0])
    draw.arc([-rand_v1, -rand_v1, size[0], rand_v1], 0, 295, fill=(0, 0, 0))
    draw.line([-rand_v1, rand_v1, size[0] + rand_v1, size[1] - rand_v1], fill=(0, 0, 0))
    draw.line([-rand_v2, 0, size[0] + rand_v2, size[1]], fill=(0, 0, 0))

def add_noise_dots(draw, image):
    size = image.size
    rand_b = random.randint(50, 250)
    for p in range(int(size[0] * size[1] * 0.2)):
        draw.point((random.randint(0, size[0]), random.randint(0, size[1])), fill=(0, 0, rand_b))

def get_random_text(length=8):
    #chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
    chars = string.digits
    return ''.join(random.choice(chars) for x in range(length))

def convert_to_base64(image):
    ''' Converts image into base64'''

    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    data_uri = base64.b64encode(buffer.read()).decode('ascii')
    return data_uri

def generate_captcha(add_noise = False):
    ''' Generate a captcha and return the solution of the captcha'''

    _captcha_txt = get_random_text(length=4)

    try:
        _font = ImageFont.truetype("arial.ttf", 50)
    except Exception as ex:
        path_ubuntu = "/usr/share/fonts/truetype/freefont/FreeMono.ttf"
        if not os.path.exists(path_ubuntu):
            raise Exception('Install required fonts. Installation on Ubuntu could be: `sudo apt-install fonts-freefont-ttf`')
        _font = ImageFont.truetype(path_ubuntu, 50, encoding="unic")

    _image = Image.new('RGB', (200, 150), color = (255, 255, 255))
    _drawing = ImageDraw.Draw(_image)

    if add_noise:
        add_noise_arcs(_drawing, _image)
        add_noise_dots(_drawing, _image)

    _drawing.text((45,50), _captcha_txt, font=_font, fill=(0, 0, 0))
    #_image.save(image_path)
    _image_as_base64 = convert_to_base64(_image)

    return _captcha_txt, _image_as_base64
