"""Своя фоновая музыка: спокойный эмбиент, который программа сочиняет сама.

Лицензия не нужна: трек генерируется заново для каждого ролика из синусов,
аккорды и мелодия выбираются по дате, поэтому ролики звучат по-разному.
"""
import random, wave
import numpy as np

SR = 44100
# Спокойные последовательности аккордов (ступени от тоники, полутоны)
PROGRESSIONS = [
    [[0, 4, 7, 11], [9, 12, 16, 19], [5, 9, 12, 16], [7, 11, 14, 17]],   # Imaj7 vi IV V
    [[0, 4, 7, 14], [5, 9, 12, 16], [9, 12, 16, 19], [7, 11, 14, 19]],
    [[0, 3, 7, 10], [8, 12, 15, 19], [3, 7, 10, 14], [10, 14, 17, 21]],  # минорная, мягкая
    [[0, 4, 7, 11], [2, 5, 9, 12], [5, 9, 12, 16], [0, 4, 7, 14]],
]
KEYS = [57, 58, 60, 62, 63, 65]  # A3, A#3, C4, D4, D#4, F4 (MIDI)


def hz(m): return 440.0 * 2 ** ((m - 69) / 12)


def pad(freq, dur):
    t = np.arange(int(dur * SR)) / SR
    env = np.minimum(1, t / 1.2) * np.minimum(1, (dur - t) / 1.0).clip(0)
    vib = 1 + 0.002 * np.sin(2 * np.pi * 4.5 * t)
    s = sum(np.sin(2 * np.pi * freq * d * vib * t) for d in (0.997, 1.0, 1.003)) / 3
    s += 0.25 * np.sin(2 * np.pi * freq * 2 * t)
    return s * env


def bell(freq, dur=2.5):
    t = np.arange(int(dur * SR)) / SR
    env = np.exp(-t * 2.2) * np.minimum(1, t / 0.01)
    return (np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2.01 * t)) * env


def compose(seconds, seed, path):
    rnd = random.Random(seed)
    prog, key = rnd.choice(PROGRESSIONS), rnd.choice(KEYS)
    bar = rnd.choice([3.0, 3.2, 3.5])
    n = int(seconds * SR) + SR * 3
    out = np.zeros(n)
    t0, i = 0.0, 0
    while t0 < seconds:
        chord = prog[i % len(prog)]
        for iv in chord:
            s = pad(hz(key - 12 + iv), bar + 1.0) * 0.12
            a = int(t0 * SR); out[a:a + len(s)] += s[: n - a]
        b = pad(hz(key - 24 + chord[0]), bar + 1.0) * 0.18  # бас
        a = int(t0 * SR); out[a:a + len(b)] += b[: n - a]
        steps = rnd.choice([4, 6, 8])
        for k in range(steps):  # мягкое арпеджио
            if rnd.random() < 0.75:
                note = key + 12 + rnd.choice(chord)
                s = bell(hz(note)) * 0.07
                a = int((t0 + k * bar / steps) * SR)
                if a < n: out[a:a + len(s)] += s[: n - a]
        t0 += bar; i += 1
    # простое эхо вместо реверберации
    for d, g in ((0.23, 0.35), (0.41, 0.22), (0.67, 0.12)):
        k = int(d * SR); out[k:] += out[:-k] * g
    out = out[: int(seconds * SR)]
    out /= max(1e-9, np.abs(out).max()) / 0.6
    stereo = np.stack([out, np.roll(out, int(0.012 * SR))], axis=1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((stereo * 32767).astype("<i2").tobytes())
    return path
