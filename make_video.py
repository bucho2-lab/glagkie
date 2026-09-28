#!/usr/bin/env python3
"""Ролик «Свободное время» в стиле канала «Гладкие линии».

Живой фон из трёх клипов assets/clips со сменой через плавный переход, музыка assets/music,
логотип assets/logo.png, шрифт Prata. Надписи и плашки появляются по очереди,
по плашкам и логотипу пробегает блик, поверх летят блёстки.
Клипы, музыка и фраза выбираются по дате, их можно задать явно.

Пример:
  python3 make_video.py --date 2026-09-30 --slots 11:00 "13:30 или 14:00" 18:00 -o out.mp4
"""
import argparse, datetime as dt, glob, math, os, random, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS, DUR = 720, 1280, 30, 12.0
FF = imageio_ffmpeg.get_ffmpeg_exe()
FONT = os.path.join(HERE, "fonts", "Prata-Regular.ttf")
LOGO = os.path.join(HERE, "assets", "logo.png")
CLIPS = sorted(glob.glob(os.path.join(HERE, "assets", "clips", "*.mp4")))
MUSIC = sorted(glob.glob(os.path.join(HERE, "assets", "music", "*.m4a")))
MONTHS = ["ЯНВАРЯ", "ФЕВРАЛЯ", "МАРТА", "АПРЕЛЯ", "МАЯ", "ИЮНЯ", "ИЮЛЯ",
          "АВГУСТА", "СЕНТЯБРЯ", "ОКТЯБРЯ", "НОЯБРЯ", "ДЕКАБРЯ"]
DAYS = ["ПОНЕДЕЛЬНИК", "ВТОРНИК", "СРЕДА", "ЧЕТВЕРГ", "ПЯТНИЦА", "СУББОТА", "ВОСКРЕСЕНЬЕ"]
# Фразы из прошлых роликов канала.
SLOGANS = [
    "«ГЛАДКИЕ ЛИНИИ» - СВОБОДА - ЭТО ПРОСНУТЬСЯ И НЕ ДУМАТЬ О БРИТВЕ.",
    "«ГЛАДКИЕ ЛИНИИ» - УХОД ЗА СОБОЙ - ЭТО НЕ ТРАТА ВРЕМЕНИ. ЭТО ИНВЕСТИЦИЯ В СВОЕ «ЗАВТРА»",
    "«ГЛАДКИЕ ЛИНИИ» - УХОЖЕННАЯ ЖЕНЩИНА - СЧАСТЛИВАЯ ЖЕНЩИНА",
    "«ГЛАДКИЕ ЛИНИИ» - ВАША КОЖА БЕЗУПРЕЧНА КАЖДЫЙ ДЕНЬ!",
    "«ГЛАДКИЕ ЛИНИИ» - ЖЕНСКАЯ ЭНЕРГИЯ ЛЮБИТ БЕРЕЖНЫЙ УХОД. ЗАПИШИТЕСЬ НА ПРОЦЕДУРУ - НАПОЛНИТЕСЬ СИЯНИЕМ",
    "КОГДА ЖЕНЩИНА НАЧИНАЕТ ЗАБОТИТЬСЯ О СЕБЕ ОНА НЕ СТАНОВИТСЯ ЭГОИСТКОЙ. ОНА СТАНОВИТСЯ СЧАСТЛИВОЙ",
]
LOGO_C, LOGO_R = (192, 1069), 153
SEG, XF = 4.0, 0.6  # длина куска фона и перехода между кусками, с


def font(size): return ImageFont.truetype(FONT, size)
def ease_out(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3
def ease_back(x):  # с лёгким «перелётом», для плашек
    x = max(0.0, min(1.0, x)); c = 1.4; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def wrap(text, f, width):
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if cur and d.textlength(test, font=f) > width:
            lines.append(cur); cur = word
        else:
            cur = test
    return lines + [cur] if cur else lines


def text_sprite(text, f, pad=12):
    """Белый текст с мягкой тенью на прозрачном фоне."""
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    im = Image.new("RGBA", (r - l + 2 * pad, b - t + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((pad - l + 2, pad - t + 3), text, font=f, fill=(0, 0, 0, 150))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(3)))
    ImageDraw.Draw(im).text((pad - l, pad - t), text, font=f, fill=(255, 255, 255, 255))
    return im


def pill_sprite(w, h, text, f):
    pad = 8
    im = Image.new("RGBA", (int(w) + 2 * pad, int(h) + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((pad, pad, pad + w, pad + h), radius=h / 2, fill=(255, 255, 255, 38),
                        outline=(255, 255, 255, 150), width=2)
    cx, cy, r, c = pad + h * 0.55, pad + h / 2, h * 0.2, (255, 255, 255, 120)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=2)
    d.line([cx, cy, cx, cy - r * 0.6], fill=c, width=2)
    d.line([cx, cy, cx + r * 0.45, cy + r * 0.25], fill=c, width=2)
    ts = text_sprite(text, f)
    im.alpha_composite(ts, (int(pad + w / 2 + h * 0.15 - ts.width / 2), int(pad + h / 2 - ts.height / 2)))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad, pad + w, pad + h), radius=h / 2, fill=255)
    return im, mask


class El:
    """Элемент кадра: картинка, центр, момент появления и вид анимации."""
    def __init__(self, img, cx, cy, start, kind="rise", dur=0.6, mask=None):
        self.img, self.cx, self.cy, self.start, self.kind, self.dur, self.mask = img, cx, cy, start, kind, dur, mask

    def draw(self, frame, t):
        k = (t - self.start) / self.dur
        if k <= 0:
            return
        a, img, dx, dy = ease_out(k), self.img, 0, 0
        if self.kind == "rise":
            dy = (1 - a) * 30
        elif self.kind in ("left", "right", "up"):
            s = ease_back(k)
            img = img.resize((max(1, int(img.width * (0.85 + 0.15 * s))), max(1, int(img.height * (0.85 + 0.15 * s)))))
            off = (1 - a) * 90
            dx = -off if self.kind == "left" else off if self.kind == "right" else 0
            dy = off * 0.5 if self.kind == "up" else 0
        if a < 1:
            img = img.copy(); img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
        frame.alpha_composite(img, (int(self.cx - img.width / 2 + dx), int(self.cy - img.height / 2 + dy)))


def glint(frame, el, t, at):
    """Косой блик пробегает по плашке."""
    k = (t - at) / 0.7
    if not 0 < k < 1 or el.mask is None:
        return
    w, h = el.img.size
    band = Image.new("L", (w, h), 0)
    x = -60 + k * (w + 120)
    ImageDraw.Draw(band).polygon([(x, 0), (x + 40, 0), (x + 40 - h * 0.6, h), (x - h * 0.6, h)], fill=110)
    band = ImageChops.multiply(band.filter(ImageFilter.GaussianBlur(8)), el.mask)
    light = Image.new("RGBA", (w, h), (255, 255, 255, 0)); light.putalpha(band)
    frame.alpha_composite(light, (int(el.cx - w / 2), int(el.cy - h / 2)))


def star_sprite(r):
    s = r * 4
    im = Image.new("L", (s, s), 0); d = ImageDraw.Draw(im); c = s / 2
    d.polygon([(c, c - 2 * r), (c + r * 0.18, c - r * 0.18), (c + 2 * r, c), (c + r * 0.18, c + r * 0.18),
               (c, c + 2 * r), (c - r * 0.18, c + r * 0.18), (c - 2 * r, c), (c - r * 0.18, c - r * 0.18)], fill=255)
    glow = Image.new("L", (s, s), 0); ImageDraw.Draw(glow).ellipse((c - r, c - r, c + r, c + r), fill=160)
    im = ImageChops.lighter(im, glow.filter(ImageFilter.GaussianBlur(r * 0.6)))
    out = Image.new("RGBA", (s, s), (255, 250, 235, 0)); out.putalpha(im)
    return out


class Sparkles:
    """Мерцающие блёстки, медленно плывут вверх."""
    def __init__(self, seed, n=34):
        rnd = random.Random(seed)
        self.sprites = [star_sprite(r) for r in (3, 5, 7)]
        self.p = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.randrange(3), rnd.uniform(0, 6.28),
                   rnd.uniform(1.5, 3.5), rnd.uniform(8, 25)) for _ in range(n)]

    def draw(self, frame, t):
        for x, y, si, ph, sp, drift in self.p:
            a = max(0.0, math.sin(t * sp + ph)) ** 2 * min(1.0, t / 1.5)
            if a < 0.05:
                continue
            spr = self.sprites[si].copy(); spr.putalpha(spr.getchannel("A").point(lambda v: int(v * a)))
            yy = (y - t * drift) % H
            frame.alpha_composite(spr, (int(x - spr.width / 2), int(yy - spr.height / 2)))


def build(date, slots, slogan, seed):
    els, pills = [], []
    f = font(29)
    y = 170
    for i, ln in enumerate(wrap(slogan, f, 470)):
        els.append(El(text_sprite(ln, f), W / 2, y, 0.7 + 0.18 * i)); y += 37

    n = len(slots)
    ph, gap = (60, 18) if n <= 6 else (52, 14)
    tf = font(34 if n <= 6 else 30)
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    if n <= 4:
        rows = [[s] for s in slots]
    else:  # две колонки; «13:30 или 14:00» и непарная плашка отдельной строкой по центру
        rows, pair = [], []
        for sl in slots:
            if "или" in sl:
                if pair: rows.append(pair); pair = []
                rows.append([sl])
            else:
                pair.append(sl)
                if len(pair) == 2: rows.append(pair); pair = []
        if pair: rows.append(pair)
    start = 0.7 + 0.18 * (y - 170) / 37 + 0.1
    top, cw, j = y + 25, 270, 0
    for r, row in enumerate(rows):
        yy = top + r * (ph + gap) + ph / 2
        for c, sl in enumerate(row):
            if len(row) == 1:
                pw, cx, kind = max(n <= 4 and 220 or cw, d.textlength(sl, font=tf) + 130), W / 2, "up"
            else:
                pw, cx, kind = cw, 80 + cw / 2 + c * (cw + 20), ("left", "right")[c]
            img, mask = pill_sprite(pw, ph, sl, tf)
            e = El(img, cx, yy, start + 0.13 * j, kind, 0.55, mask)
            els.append(e); pills.append(e); j += 1

    t0 = start + 0.13 * j + 0.1
    day = DAYS[date.weekday()]
    for i, (txt, sz, yy) in enumerate([(str(date.day), 44, 930), (MONTHS[date.month - 1], 44, 985),
                                       (day, 40 if len(day) < 10 else 32, 1040),
                                       ("СВОБОДНОЕ", 40, 1110), ("ВРЕМЯ", 40, 1160)]):
        els.append(El(text_sprite(txt, font(sz)), 540, yy, t0 + 0.15 * i))
    return els, pills, Sparkles(seed)


def logo_sprite():
    return Image.open(LOGO).convert("RGBA").resize((LOGO_R * 2, LOGO_R * 2), Image.LANCZOS)


def draw_logo(frame, lg, mask, t):
    s = 1 + 0.015 * math.sin(t * 1.6)  # «дыхание»
    size = int(LOGO_R * 2 * s)
    im = lg.resize((size, size), Image.BILINEAR)
    k = (t % 4.0) / 0.9  # блик раз в 4 секунды
    if 0 < k < 1:
        band = Image.new("L", (size, size), 0)
        x = -80 + k * (size + 160)
        ImageDraw.Draw(band).polygon([(x, 0), (x + 50, 0), (x + 50 - size * 0.5, size), (x - size * 0.5, size)], fill=120)
        band = ImageChops.multiply(band.filter(ImageFilter.GaussianBlur(10)), mask.resize((size, size)))
        light = Image.new("RGBA", (size, size), (255, 255, 255, 0)); light.putalpha(band)
        im.alpha_composite(light)
    frame.alpha_composite(im, (LOGO_C[0] - size // 2, LOGO_C[1] - size // 2))


def background(clips, path):
    """Три клипа по SEG секунд, крутятся по кругу, между ними плавный переход."""
    cmd = [FF, "-y", "-loglevel", "error"]
    for c in clips:
        cmd += ["-stream_loop", "-1", "-t", str(SEG + XF), "-i", c]
    fl, last = [], "[0:v]"
    for i in range(1, len(clips)):
        out = f"[x{i}]"
        fl.append(f"{last}[{i}:v]xfade=transition={('fade', 'smoothup')[i % 2]}:duration={XF}:offset={SEG * i}{out}")
        last = out
    cmd += ["-filter_complex", ";".join(fl) + f";{last}fps={FPS},format=rgb24[v]", "-map", "[v]",
            "-t", str(DUR), "-c:v", "libx264", "-crf", "16", "-preset", "veryfast", path]
    subprocess.run(cmd, check=True)


def zoom(fr, t):
    """Медленное приближение с центром в логотипе, чтобы логотип в исходнике не выглядывал."""
    z = 1.0 + 0.06 * (t / DUR)
    w, h = W / z, H / z
    x = LOGO_C[0] - LOGO_C[0] / z
    y = LOGO_C[1] - LOGO_C[1] / z
    return fr.resize((W, H), Image.BILINEAR, box=(x, y, x + w, y + h))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="ГГГГ-ММ-ДД")
    p.add_argument("--slots", nargs="+", required=True, help='время, например 11:00 "13:30 или 14:00"')
    p.add_argument("--slogan"); p.add_argument("--clips", nargs=3); p.add_argument("--music")
    p.add_argument("-o", "--out", default="slot.mp4")
    a = p.parse_args()
    date = dt.date.fromisoformat(a.date)
    k = date.toordinal()
    slogan = a.slogan or SLOGANS[k % len(SLOGANS)]
    clips = a.clips or [CLIPS[(k + s) % len(CLIPS)] for s in (0, 3, 5)]
    music = a.music or (MUSIC[k % len(MUSIC)] if MUSIC else None)

    els, pills, sparkles = build(date, a.slots[:10], slogan, k)
    lg = logo_sprite()
    lmask = Image.new("L", lg.size, 0); ImageDraw.Draw(lmask).ellipse((0, 0, lg.width - 1, lg.height - 1), fill=255)

    with tempfile.TemporaryDirectory() as tmp:
        bgp = os.path.join(tmp, "bg.mp4")
        background(clips, bgp)
        cmd = [FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-"]
        if music:
            cmd += ["-stream_loop", "-1", "-i", music, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "128k",
                    "-af", f"afade=t=in:d=0.3,afade=t=out:st={DUR - 1.2}:d=1.2", "-t", str(DUR)]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
                "-movflags", "+faststart", a.out]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        reader = imageio_ffmpeg.read_frames(bgp, pix_fmt="rgb24")
        next(reader)  # метаданные
        for i, raw in zip(range(int(DUR * FPS)), reader):
            t = i / FPS
            fr = zoom(Image.frombytes("RGB", (W, H), raw), t).convert("RGBA")
            draw_logo(fr, lg, lmask, t)
            for e in els:
                e.draw(fr, t)
            for j, e in enumerate(pills):
                glint(fr, e, t, 5.0 + 0.1 * j)
                glint(fr, e, t, 9.0 + 0.1 * j)
            sparkles.draw(fr, t)
            proc.stdin.write(fr.convert("RGB").tobytes())
        proc.stdin.close()
        if proc.wait():
            raise SystemExit("ffmpeg error")
    print(a.out)


if __name__ == "__main__":
    main()
