#!/usr/bin/env python3
"""Короткий вертикальный ролик о свободных окнах.

Пример:
  python3 make_video.py --date 2026-09-30 --times 11:00 14:30 18:00 -o out.mp4
"""
import argparse, datetime as dt, math, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio_ffmpeg

W, H, FPS, DUR = 1080, 1920, 30, 12.0
HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
FONT_B = HERE + "/fonts/DejaVuSans-Bold.ttf"
FONT_R = HERE + "/fonts/DejaVuSans.ttf"
BG_TOP, BG_BOT = (250, 232, 226), (231, 196, 190)
INK, ACCENT, SOFT = (74, 44, 52), (176, 92, 104), (255, 255, 255)
DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]

def font(path, size): return ImageFont.truetype(path, size)
def ease(t): t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 3
def appear(t, start, dur=0.6): return ease((t - start) / dur)

def background():
    bg = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(BG_TOP, BG_BOT)))
    return bg

def waves(t):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(4):
        pts = []
        base = 1500 + i * 70
        for x in range(-20, W + 40, 20):
            y = base + 60 * math.sin(x / 260 + t * 0.9 + i * 0.8) + 25 * math.sin(x / 90 - t * 0.6 + i)
            pts.append((x, y))
        d.line(pts, fill=(255, 255, 255, 110 - i * 20), width=5)
    for i in range(3):
        pts = []
        for x in range(-20, W + 40, 20):
            y = 250 + i * 55 + 45 * math.sin(x / 300 - t * 0.7 + i * 1.3)
            pts.append((x, y))
        d.line(pts, fill=(255, 255, 255, 90 - i * 25), width=4)
    return layer.filter(ImageFilter.GaussianBlur(1))

def centered(d, y, text, f, fill, alpha=1.0, dy=0):
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, y + (1 - alpha) * 40 + dy), text, font=f, fill=fill + (int(255 * alpha),))

def frame(t, bg, date, times, footer):
    img = bg.copy().convert("RGBA")
    img.alpha_composite(waves(t))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    a = appear(t, 0.2)
    centered(d, 470, "СВОБОДНЫЕ ОКНА" if len(times) > 1 else "СВОБОДНОЕ ОКНО", font(FONT_B, 76), ACCENT, a)
    centered(d, 570, "лазерная эпиляция", font(FONT_R, 50), INK, appear(t, 0.5))

    a = appear(t, 1.1)
    day = f"{date.day} {MONTHS[date.month - 1]}"
    centered(d, 720, day, font(FONT_B, 120), INK, a)
    centered(d, 870, DAYS[date.weekday()], font(FONT_R, 58), INK, appear(t, 1.3))

    n = len(times)
    fs = 92 if n <= 3 else 72
    pill_h, gap = fs + 60, 34
    top = 1020 + max(0, (3 - n)) * 20
    for i, tm in enumerate(times):
        a = appear(t, 1.9 + i * 0.35)
        if a <= 0: continue
        pulse = 1 + 0.02 * math.sin((t - 1.9 - i * 0.35) * 3) if a >= 1 else 1
        f = font(FONT_B, int(fs * pulse))
        tw = d.textlength(tm, font=f)
        pw = max(tw + 140, 420)
        y = top + i * (pill_h + gap) + (1 - a) * 50
        d.rounded_rectangle([(W - pw) / 2, y, (W + pw) / 2, y + pill_h], radius=pill_h / 2,
                            fill=SOFT + (int(235 * a),), outline=ACCENT + (int(255 * a),), width=4)
        d.text(((W - tw) / 2, y + (pill_h - fs * pulse) / 2 - 8), tm, font=f, fill=ACCENT + (int(255 * a),))

    fa = appear(t, 1.9 + n * 0.35 + 0.4)
    ff = font(FONT_B, 54)
    while d.textlength(footer, font=ff) > W - 120 and ff.size > 28:
        ff = font(FONT_B, ff.size - 2)
    centered(d, 1700, footer, ff, INK, fa)
    centered(d, 1775, "время московское", font(FONT_R, 38), INK, fa)

    img.alpha_composite(ov)
    fade = min(1.0, t / 0.4, (DUR - t) / 0.5)
    if fade < 1:
        img = Image.blend(Image.new("RGBA", (W, H), BG_TOP + (255,)), img, max(0, fade))
    return img.convert("RGB")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="ГГГГ-ММ-ДД")
    p.add_argument("--times", nargs="+", required=True, help="ЧЧ:ММ ...")
    p.add_argument("--footer", default="Запись в личных сообщениях")
    p.add_argument("-o", "--out", default="slot.mp4")
    a = p.parse_args()
    date = dt.date.fromisoformat(a.date)
    times = sorted(a.times, key=lambda s: tuple(map(int, s.split(":"))))[:5]
    bg = background()
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-preset", "medium", "-crf", "20", "-movflags", "+faststart", a.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for i in range(int(DUR * FPS)):
        proc.stdin.write(frame(i / FPS, bg, date, times, a.footer).tobytes())
    proc.stdin.close(); proc.wait()
    print(a.out)

if __name__ == "__main__":
    main()
