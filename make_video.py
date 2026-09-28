#!/usr/bin/env python3
"""Ролик «Свободное время» в стиле канала «Гладкие линии».

Фон из assets/backgrounds (фото с медленным приближением), музыка из assets/music,
логотип assets/logo.png, шрифт Prata. Фон и музыка выбираются по дате, их можно задать явно.

Пример:
  python3 make_video.py --date 2026-09-30 --slots 11:00 "13:30 или 14:00" 18:00 -o out.mp4
"""
import argparse, datetime as dt, glob, os, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio_ffmpeg

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS, DUR = 720, 1280, 30, 12.0
FONT = os.path.join(HERE, "fonts", "Prata-Regular.ttf")
LOGO = os.path.join(HERE, "assets", "logo.png")
BACKGROUNDS = sorted(glob.glob(os.path.join(HERE, "assets", "backgrounds", "*.jpg")))
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
WHITE = (255, 255, 255)
LOGO_C, LOGO_R = (192, 1069), 153


def font(size): return ImageFont.truetype(FONT, size)


def wrap(d, text, f, width):
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if cur and d.textlength(test, font=f) > width:
            lines.append(cur); cur = word
        else:
            cur = test
    return lines + [cur] if cur else lines


def shadow_text(layer, xy, text, f, anchor="mm", blur=3, alpha=150):
    """Белый текст с мягкой тенью, как в роликах канала."""
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((xy[0] + 2, xy[1] + 3), text, font=f, fill=(0, 0, 0, alpha), anchor=anchor)
    layer.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    ImageDraw.Draw(layer).text(xy, text, font=f, fill=WHITE + (255,), anchor=anchor)


def clock_icon(d, cx, cy, r, color):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=2)
    d.line([cx, cy, cx, cy - r * 0.6], fill=color, width=2)
    d.line([cx, cy, cx + r * 0.45, cy + r * 0.25], fill=color, width=2)


def pill(layer, box, text, f):
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=(y1 - y0) / 2, fill=(255, 255, 255, 38), outline=(255, 255, 255, 150), width=2)
    h = y1 - y0
    clock_icon(d, x0 + h * 0.55, (y0 + y1) / 2, h * 0.2, (255, 255, 255, 120))
    shadow_text(layer, ((x0 + x1) / 2 + h * 0.15, (y0 + y1) / 2), text, f)


def overlay(date, slots, slogan):
    """Всё, кроме логотипа: фраза, плашки с временем, дата. Рисуется один раз."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    f = font(29)
    lines = wrap(d, slogan, f, 470)
    y = 170
    for ln in lines:
        shadow_text(layer, (W / 2, y), ln, f); y += 37

    n = len(slots)
    ph, gap = (60, 18) if n <= 6 else (52, 14)
    tf = font(34 if n <= 6 else 30)
    top = y + 25
    if n <= 4:  # одна колонка
        for i, s in enumerate(slots):
            pw = max(220, d.textlength(s, font=tf) + 130)
            yy = top + i * (ph + gap)
            pill(layer, ((W - pw) / 2, yy, (W + pw) / 2, yy + ph), s, tf)
    else:  # две колонки; «13:30 или 14:00» и непарная плашка идут отдельной строкой по центру
        rows, pair = [], []
        for sl in slots:
            if "или" in sl:
                if pair: rows.append(pair); pair = []
                rows.append([sl])
            else:
                pair.append(sl)
                if len(pair) == 2: rows.append(pair); pair = []
        if pair: rows.append(pair)
        cw = 270
        for r, row in enumerate(rows):
            yy = top + r * (ph + gap)
            if len(row) == 1:
                pw = max(cw, d.textlength(row[0], font=tf) + 130)
                pill(layer, ((W - pw) / 2, yy, (W + pw) / 2, yy + ph), row[0], tf)
            else:
                for c, sl in enumerate(row):
                    x0 = 80 + c * (cw + 20)
                    pill(layer, (x0, yy, x0 + cw, yy + ph), sl, tf)

    cx, fb = 540, font(44)
    shadow_text(layer, (cx, 930), str(date.day), fb)
    shadow_text(layer, (cx, 985), MONTHS[date.month - 1], fb)
    shadow_text(layer, (cx, 1040), DAYS[date.weekday()], font(40 if len(DAYS[date.weekday()]) < 10 else 32))
    fs = font(40)
    shadow_text(layer, (cx, 1110), "СВОБОДНОЕ", fs)
    shadow_text(layer, (cx, 1160), "ВРЕМЯ", fs)
    return layer


def logo_layer():
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lg = Image.open(LOGO).convert("RGBA").resize((LOGO_R * 2, LOGO_R * 2), Image.LANCZOS)
    layer.alpha_composite(lg, (LOGO_C[0] - LOGO_R, LOGO_C[1] - LOGO_R))
    return layer


def background_frame(bg, t):
    """Медленное приближение фото (эффект живого фона)."""
    z = 1.0 + 0.08 * (t / DUR)
    w, h = int(W / z), int(H / z)
    x, y = (W - w) // 2, (H - h) // 2
    return bg.crop((x, y, x + w, y + h)).resize((W, H), Image.BILINEAR)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="ГГГГ-ММ-ДД")
    p.add_argument("--slots", nargs="+", required=True, help='время, например 11:00 "13:30 или 14:00"')
    p.add_argument("--slogan"); p.add_argument("--background"); p.add_argument("--music")
    p.add_argument("-o", "--out", default="slot.mp4")
    a = p.parse_args()
    date = dt.date.fromisoformat(a.date)
    k = date.toordinal()
    slogan = a.slogan or SLOGANS[k % len(SLOGANS)]
    bg = Image.open(a.background or BACKGROUNDS[k % len(BACKGROUNDS)]).convert("RGB")
    bg = bg.resize((W, int(bg.height * W / bg.width))) if bg.width != W else bg
    bg = bg.crop((0, (bg.height - H) // 2, W, (bg.height - H) // 2 + H)) if bg.height != H else bg
    music = a.music or (MUSIC[k % len(MUSIC)] if MUSIC else None)

    ov, lg = overlay(date, a.slots[:10], slogan), logo_layer()
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-"]
    if music:
        cmd += ["-stream_loop", "-1", "-i", music, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "128k",
                "-af", f"afade=t=in:d=0.3,afade=t=out:st={DUR - 1.2}:d=1.2", "-t", str(DUR)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
            "-movflags", "+faststart", a.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(int(DUR * FPS)):
        t = i / FPS
        fr = background_frame(bg, t).convert("RGBA")
        fr.alpha_composite(lg)
        k_in = max(0.0, min(1.0, (t - 0.8) / 0.5))  # текст проявляется после первой секунды
        if k_in >= 1:
            fr.alpha_composite(ov)
        elif k_in > 0:
            o = ov.copy(); o.putalpha(o.getchannel("A").point(lambda v: int(v * k_in))); fr.alpha_composite(o)
        proc.stdin.write(fr.convert("RGB").tobytes())
    proc.stdin.close()
    if proc.wait():
        raise SystemExit("ffmpeg error")
    print(a.out)


if __name__ == "__main__":
    main()
