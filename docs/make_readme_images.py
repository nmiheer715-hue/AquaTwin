"""Compose the README images: 4K app captures (docs/img/4k) -> 1920x1080 presentation cards (docs/img).
Crops are given in the app's 1920x1080 layout pixels; the captures are 2x."""
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
SRC, OUT = os.path.join(HERE, "img", "4k"), os.path.join(HERE, "img")
W, H, BG = 1920, 1080, (11, 18, 25)
F = lambda name, size: ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name), size)
TITLE, SUB, TAG = F("segoeuib.ttf", 46), F("segoeui.ttf", 26), F("seguisb.ttf", 20)
ACC, TXT, MUT, LINE = (94, 200, 220), (221, 230, 238), (133, 151, 168), (42, 58, 76)

def card(src, box, title, sub, tag, out, side=False):
    im = Image.open(os.path.join(SRC, src + ".png")).convert("RGB")
    x0, y0, x1, y1 = [2 * v for v in box]
    crop = im.crop((x0, y0, x1, y1))
    c = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(c)
    if side:                                   # text column on the left, image on the right
        tx, ty, aw, ah, ax, ay = 90, 0, 1060, 960, 800, 60
        d.text((tx, 330), tag.upper(), font=TAG, fill=ACC)
        y = 368
        for line in title: d.text((tx, y), line, font=TITLE, fill=TXT); y += 60
        y += 16
        for line in sub: d.text((tx, y), line, font=SUB, fill=MUT); y += 38
    else:                                      # title strip on top, image below
        d.text((80, 52), tag.upper(), font=TAG, fill=ACC)
        d.text((80, 82), title[0], font=TITLE, fill=TXT)
        d.text((80, 146), sub[0], font=SUB, fill=MUT)
        aw, ah, ax, ay = 1760, 840, 80, 205
    s = min(aw / crop.width, ah / crop.height)
    nw, nh = round(crop.width * s), round(crop.height * s)
    crop = crop.resize((nw, nh), Image.LANCZOS)
    px = ax + (aw - nw) // 2 if not side else W - 80 - nw
    py = ay + (ah - nh) // 2
    sh = Image.new("RGBA", (nw + 80, nh + 80), (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((40, 50, nw + 40, nh + 50), 14, fill=(0, 0, 0, 150))
    c.paste(sh.filter(ImageFilter.GaussianBlur(18)), (px - 40, py - 40), sh.filter(ImageFilter.GaussianBlur(18)))
    m = Image.new("L", (nw, nh), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, nw - 1, nh - 1), 12, fill=255)
    c.paste(crop, (px, py), m)
    d.rounded_rectangle((px, py, px + nw - 1, py + nh - 1), 12, outline=LINE, width=2)
    c.save(os.path.join(OUT, out + ".jpg"), quality=92, subsampling=0)
    print(out, c.size)

MAP, MAPPANEL = (15, 132, 1197, 890), (15, 132, 1903, 890)
card("hero-3d", (40, 250, 1180, 885), ["The control room, in 3D"], ["Each column rises from the pipe the AI suspects; its height is the leak size. L-Town, 21 April 2019."], "AquaTwin · live replay", "hero-3d")
card("control-room", MAPPANEL, ["Every alarm: district, size, suspected pipe"], ["The leak on p327 (+12.8 m³/h), its candidate zone, and the actions: dispatch a crew or close the isolation valves."], "Decide → act", "control-room")
card("answer-key-3d", (40, 250, 1180, 885), ["Checked against the real leaks"], ["Answer key on: green = real leak found, red = false alarm. 15 of 23 leaks found in 2019 under the official scoring."], "BattLeDIM 2020", "answer-key-3d")
card("pressure-management", MAPPANEL, ["Smart pressure management"], ["Pressure each junction can lose while every home keeps ≥ 19 m. Leakage −21 % and −38 % in the two PRV areas."], "Network health", "pressure-management")
card("street-map", (15, 175, 1197, 890), ["The network on a street-map view"], ["Alarms, loggers and the answer key drawn over a clean basemap of the network's own geometry."], "Control room", "street-map")
card("forecast", (1210, 132, 1903, 715), ["Tomorrow's demand", "and tank level"], ["Forecast at midnight from history only.", "District A: 3.2 % error vs 4.6 % for", "\"same as last week\".", "Tank T1 within 0.19 m on average."], "Day-ahead forecast", "forecast", side=True)
card("sensor-planner", (0, 0, 1920, 1080), ["Plan the sensors before buying any"], ["From the network file alone: proposed districts, ranked logger sites, coverage and cost, pressure and water-quality checks."], "Sensor planner", "sensor-planner")
