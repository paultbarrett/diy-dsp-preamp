import os
import logging
import time

# display
from PIL import Image, ImageDraw, ImageFont

text = "-32dB"

text = "-14|-43"

text = "\u25A1"

for size in range(8,80):
    font = ImageFont.truetype('DejaVuSansMono.ttf', size)
    (width, height), (offset_x, offset_y) = font.font.getsize(text)
    print("size {}: height:{} offset_y:{}".format(size, height, offset_y))
