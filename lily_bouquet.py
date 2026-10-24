#!/usr/bin/env python3
"""ASCII lily bouquet, window version.

Stage 1: stems and leaves grow.  Stage 2: buds form.  Stage 3: the lilies open.
Everything is drawn as smooth colour, then covered with rows of tiny code text
so it looks like it is made of code.

Setup (once):   py -m pip install pillow
Run:            py lily_bouquet_window.py
Keys:           R = replay    Esc / Q = quit
"""
import math
import random
import sys
import time

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont
except ImportError:
    sys.exit("This needs Pillow. Install it with:\n    py -m pip install pillow")

# ---- design space (everything below is laid out in these units, then scaled) ----
DW, DH = 688, 640
DURATION = 35.0   # seconds for the whole grow + bloom animation
BLOOM_AT = 14.0  # second at which the first lily starts to open (the chorus)
PULSE = 0.045     # how much the lilies breathe (0 = off, 0.08 = strong)
PULSE_SPEED = 1.6 # breathing speed (lower = slower)
FIREFLIES = 40   # how many fireflies drift around (0 turns them off)
VOLUME = 0.3     # music volume, 0.0 (silent) to 1.0 (full)
Y0 = 440          # design y that sits at the top of the window
BASE = 1045       # design y of the bottom of the bouquet

CODE = ("ymin = 1e9, ymax = -1e9, maxw = 0; for (k = 0; k < n; k++) "
        "{ x = pts[k][0]; y = pts[k][1]; if (x > xmax) xmax = x; "
        "if (y < ymin) ymin = y; if (y > ymax) ymax = y; } ")

STEM = (150, 220, 90)
LEAF_DARK = (40, 120, 40)
LEAF_LIGHT = (130, 215, 80)
LEAF_RIB = (200, 245, 140)
GOLD = (240, 185, 55)

# x, y, radius, colour, rotation, tilt, bloom start (s)   -- back to front
FLOWERS = [
    (140, 745, 64, (70, 120, 240), 0.20, 0.80, 7.7),    # blue, far left
    (568, 780, 62, (95, 160, 250), 0.40, 0.80, 8.1),    # sky blue, far right
    (410, 522, 52, (130, 185, 250), 0.30, 0.85, 7.4),   # pale blue, top
    (255, 565, 62, (205, 185, 150), 0.25, 0.80, 7.6),   # tan, top left
    (468, 558, 60, (205, 170, 50), 0.50, 0.85, 7.9),    # olive yellow, top right
    (350, 615, 105, (215, 32, 42), 0.12, 0.90, 6.8),    # big red, top
    (212, 662, 72, (235, 155, 45), 0.30, 0.80, 7.2),    # orange, left
    (492, 675, 70, (205, 55, 150), 0.00, 0.80, 7.5),    # magenta, right
    (182, 860, 58, (215, 175, 40), 0.40, 0.80, 8.4),    # yellow, low left
    (510, 892, 60, (215, 35, 45), 0.20, 0.80, 8.6),     # red, low right
    (270, 745, 108, (222, 70, 190), 0.10, 0.95, 8.0),   # big pink
    (430, 790, 118, (228, 212, 185), 0.35, 0.90, 8.2),  # big cream
    (335, 855, 92, (225, 140, 60), 0.20, 0.90, 8.7),    # orange front
    (425, 905, 56, (60, 100, 225), 0.15, 0.80, 8.5),    # deep blue, front
]
FIRST_BLOOM = min(f[6] for f in FLOWERS)   # design time the first lily opens
BUDS = [(320, 492, (120, 28, 45)), (362, 503, (135, 35, 50)), (412, 485, (165, 40, 55))]


def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def ease(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def prog(T, a, b):
    return ease((T - a) / (b - a))


def shade(c, k):
    return (int(clamp(c[0] * k, 0, 255)), int(clamp(c[1] * k, 0, 255)),
            int(clamp(c[2] * k, 0, 255)))


def bez(p0, p1, p2, t):
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
            u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])


def dbez(p0, p1, p2, t):
    return (2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0]),
            2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1]))


def load_font(size):
    for name in ("consola.ttf", "Menlo.ttc", "DejaVuSansMono.ttf", "cour.ttf",
                 "LiberationMono-Regular.ttf", "Courier New.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


class Scene:
    def __init__(self, S):
        self.S = S
        self.W, self.H = int(DW * S), int(DH * S)
        rnd = random.Random(11)

        # flower stems (+ tiny buds' stems), each with small leaves along it
        self.stems = []
        for k, f in enumerate(FLOWERS):
            self.stems.append(self._stem(rnd, f[0], f[1], k * 0.12))
        for k, b in enumerate(BUDS):
            self.stems.append(self._stem(rnd, b[0], b[1], 0.6 + k * 0.15))

        # broad leaves fanning out of the base
        self.leaves = []
        angles = [-78, -64, -52, -40, -28, -14, 0, 12, 26, 38, 50, 62, 76, -70, 70, -34, 32]
        for a in angles:
            ang = math.radians(a + rnd.uniform(-4, 4))
            L = rnd.uniform(140, 250)
            bx = 344 + rnd.uniform(-34, 34)
            p0 = (bx, BASE - 4)
            p1 = (bx + math.sin(ang) * L * 0.4, BASE - L * 0.55)
            p2 = (bx + math.sin(ang) * L, BASE - L * (0.22 + 0.5 * math.cos(ang)))
            self.leaves.append((p0, p1, p2, rnd.uniform(7, 14), rnd.uniform(2.0, 5.2),
                                rnd.uniform(0.85, 1.15)))

        self.tex = self._texture()

        # fireflies: soft glowing dots that wander around the bouquet and blink
        fr = random.Random(5)
        self.flies = []
        for _ in range(FIREFLIES):
            self.flies.append({
                "hx": fr.uniform(60, 630), "hy": fr.uniform(500, 1010),
                "ax": fr.uniform(15, 45), "ay": fr.uniform(10, 35),
                "w1": fr.uniform(0.25, 0.7), "w2": fr.uniform(0.6, 1.4),
                "p1": fr.uniform(0, 6.3), "p2": fr.uniform(0, 6.3),
                "bf": fr.uniform(0.5, 1.4), "bp": fr.uniform(0, 6.3),
                "size": fr.choice((0, 1, 1, 2)), "late": fr.uniform(0, 3.0),
            })
        self.glows = []                       # glows[size][brightness level] -> image
        for size in range(3):
            r = int((9 + 5 * size) * S) + 1
            levels = []
            for lv in range(1, 9):
                k = lv / 8
                img = Image.new("RGB", (2 * r + 1, 2 * r + 1))
                px = img.load()
                for yy in range(2 * r + 1):
                    for xx in range(2 * r + 1):
                        dd = math.hypot(xx - r, yy - r) / r
                        f = max(0.0, 1 - dd) ** 1.7 * k
                        core = max(0.0, 1 - dd * 2.4) * k
                        px[xx, yy] = (int(clamp(f * 255 + core * 120, 0, 255)),
                                      int(clamp(f * 235 + core * 120, 0, 255)),
                                      int(clamp(f * 110 + core * 150, 0, 255)))
                levels.append(img)
            self.glows.append((r, levels))

    def _draw_fireflies(self, out, T, tm):
        S = self.S
        for f in self.flies:
            appear = prog(T, FIRST_BLOOM + f["late"] * 0.4, FIRST_BLOOM + 2.5 + f["late"] * 0.4)
            if appear <= 0.01:
                continue
            blink = max(0.0, math.sin(tm * f["bf"] * 2.2 + f["bp"])) ** 2
            level = int(clamp(blink * appear, 0, 0.999) * 8)
            if level < 1:
                continue
            x = f["hx"] + f["ax"] * math.sin(tm * f["w1"] + f["p1"]) \
                + 0.5 * f["ax"] * math.sin(tm * f["w2"] * 1.7 + f["p2"])
            y = f["hy"] + f["ay"] * math.sin(tm * f["w2"] + f["p2"]) \
                - 14 * math.sin(tm * 0.2 + f["p1"])
            r, levels = self.glows[f["size"]]
            sx, sy = int(x * S) - r, int((y - Y0) * S) - r
            box = (max(sx, 0), max(sy, 0), min(sx + 2 * r + 1, self.W), min(sy + 2 * r + 1, self.H))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            sprite = levels[level - 1]
            if box != (sx, sy, sx + 2 * r + 1, sy + 2 * r + 1):
                sprite = sprite.crop((box[0] - sx, box[1] - sy, box[2] - sx, box[3] - sy))
            out.paste(ImageChops.add(out.crop(box), sprite), box)

    def _stem(self, rnd, x, y, delay):
        x0 = 344 + (x - 344) * 0.16 + rnd.uniform(-14, 14)
        p0 = (x0, BASE - 5)
        p1 = (x0 + (x - x0) * 0.2 + rnd.uniform(-25, 25), (BASE + y) / 2)
        p2 = (x, y)
        leaves = []
        for t in (0.36, 0.52, 0.68, 0.82):
            if rnd.random() < 0.85:
                leaves.append((t, rnd.choice((-1, 1)), rnd.uniform(34, 66), rnd.uniform(5, 9)))
        return {"p": (p0, p1, p2), "delay": delay, "leaves": leaves}

    def _texture(self):
        W, H = self.W, self.H
        img = Image.new("L", (W, H), 66)
        d = ImageDraw.Draw(img)
        font = load_font(8)
        rnd = random.Random(3)
        for row in range(H // 7 + 2):
            off = rnd.randrange(len(CODE))
            line = (CODE * (W // 30 + 3))[off:off + W // 4 + 6]
            d.text((-rnd.randrange(5), row * 7 - 2), line, fill=255, font=font)
        return img.convert("RGB")

    # ------------------------------------------------------------------ drawing
    def render(self, T, tm):
        S, W, H = self.S, self.W, self.H
        layer = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(layer)
        # Remap real seconds to the animation timeline: the first lily starts opening at
        # BLOOM_AT seconds (the chorus) and everything is finished by DURATION seconds.
        first = min(f[6] for f in FLOWERS)
        if T < BLOOM_AT:
            T = T * first / BLOOM_AT
        else:
            T = first + (T - BLOOM_AT) * (12.0 - first) / (DURATION - BLOOM_AT)
        amp = prog(T, 10.0, 12.0)

        def sw(x, y):
            return math.sin(tm * 1.15 + y * 0.006 + x * 0.002) * amp * clamp((BASE - y) / 600) ** 2 * 8

        def P(x, y):                       # design -> screen, with sway
            return ((x + sw(x, y)) * S, (y - Y0) * S)

        def P0(x, y):                      # design -> screen, no sway
            return (x * S, (y - Y0) * S)

        # --- stems and their small leaves
        tips = []
        for st in self.stems:
            p0, p1, p2 = st["p"]
            g = prog(T, 0.3 + st["delay"], 4.2 + st["delay"])
            m = max(1, int(40 * g))
            pts = [P(*bez(p0, p1, p2, g * s / m)) for s in range(m + 1)]
            if len(pts) > 1:
                d.line(pts, fill=STEM, width=max(2, int(2.2 * S)))
            tips.append((bez(p0, p1, p2, g), g))
            for t, side, L, w in st["leaves"]:
                lg = prog(g, t, t + 0.2)
                if lg < 0.03:
                    continue
                a = bez(p0, p1, p2, t)
                tx, ty = dbez(p0, p1, p2, t)
                n = math.hypot(tx, ty) or 1
                ang = math.atan2(ty, tx) + side * math.radians(48)
                dx, dy = math.cos(ang), math.sin(ang)
                b = (a[0] + dx * L * 0.5, a[1] + dy * L * 0.5 - L * 0.08)
                c = (a[0] + dx * L, a[1] + dy * L)
                self._leaf(d, P, a, b, c, w, lg, LEAF_DARK, LEAF_LIGHT, LEAF_RIB)

        # --- broad base leaves
        for p0, p1, p2, w, st, mul in self.leaves:
            g = prog(T, st, st + 2.6)
            self._leaf(d, P, p0, p1, p2, w, g, shade(LEAF_DARK, mul), shade(LEAF_LIGHT, mul),
                       shade(LEAF_RIB, mul))

        # --- tiny buds (they never open)
        nf = len(FLOWERS)
        for k, (bx, by, col) in enumerate(BUDS):
            (x, y), g = tips[nf + k]
            s = prog(g, 0.9, 1.0)
            if s > 0.02:
                cx, cy = x + sw(x, y), y
                self._bud(d, P0, cx, cy - 8, 7 * s, 15 * s, col)

        # --- flowers: buds first, then they open
        for k, (fx, fy, R, col, rot, tilt, bs) in enumerate(FLOWERS):
            (x, y), g = tips[k]
            s = prog(g, 0.88, 1.0)
            if s < 0.02:
                continue
            cx, cy = x + sw(x, y), y
            b = prog(T, bs, bs + 2.3)
            if b < 0.3:
                self._bud(d, P0, cx, cy, 0.30 * R * s, 0.40 * R * s, col)
            if b > 0.06:
                e = ease(b)
                # gentle breathing: each lily swells and relaxes a little, out of step
                pz = math.sin(tm * PULSE_SPEED + k * 0.9) * PULSE * e
                self._lily(d, P0, cx, cy, R * (0.30 + 0.70 * e) * (1 + pz),
                           shade(col, 0.62 + 0.38 * e + 1.2 * pz),
                           rot + tm * 0.04 * amp + (1 - e) * 0.6, tilt,
                           (0.5 + 0.5 * e) * (1 + 0.8 * pz))

        out = ImageChops.multiply(layer, self.tex)
        self._draw_fireflies(out, T, tm)
        return out

    def _leaf(self, d, P, p0, p1, p2, wmax, g, dark, light, rib):
        if g < 0.03:
            return
        m = max(3, int(16 * g))
        left, right, cen = [], [], []
        for s in range(m + 1):
            t = g * s / m
            x, y = bez(p0, p1, p2, t)
            dx, dy = dbez(p0, p1, p2, t)
            n = math.hypot(dx, dy) or 1
            nx, ny = -dy / n, dx / n
            w = wmax * math.sin(math.pi * min(1.0, t)) ** 0.75 * (0.35 + 0.65 * min(1.0, g * 1.5))
            left.append((x + nx * w, y + ny * w))
            right.append((x - nx * w, y - ny * w))
            cen.append((x, y))
        d.polygon([P(*p) for p in left + right[::-1]], fill=dark)
        d.polygon([P(*p) for p in cen + left[::-1]], fill=light)
        if len(cen) > 1:
            d.line([P(*p) for p in cen], fill=rib, width=1)

    def _bud(self, d, P0, cx, cy, a, b, col):
        if a < 1 or b < 1:
            return

        def egg(aa, bb, ox, oy):
            pts = []
            for k in range(24):
                th = 2 * math.pi * k / 24
                pts.append(P0(cx + ox + aa * math.cos(th) * (1 + 0.25 * math.sin(th)),
                              cy + oy + bb * math.sin(th)))
            return pts

        d.polygon(egg(a, b, 0, 0), fill=shade(col, 0.72))
        d.polygon(egg(a * 0.72, b * 0.78, -a * 0.08, -b * 0.08), fill=shade(col, 1.0))
        d.polygon(egg(a * 0.30, b * 0.40, -a * 0.25, -b * 0.28), fill=shade(col, 1.3))

    def _petal(self, P0, cx, cy, L, wm, bend, rot, tilt, u0=0.0, u1=1.0, wscale=1.0, n=10):
        top, bot = [], []
        for s in range(n + 1):
            u = u0 + (u1 - u0) * s / n
            w = wm * wscale * math.sin(math.pi * u ** 0.8)
            yb = bend * L * u * u
            top.append((u * L, yb - w))
            bot.append((u * L, yb + w))
        c, sn = math.cos(rot), math.sin(rot)
        out = []
        for x, y in top + bot[::-1]:
            out.append(P0(cx + x * c - y * sn, cy + (x * sn + y * c) * tilt))
        return out

    def _lily(self, d, P0, cx, cy, R, col, rot, tilt, open_w):
        for outer in (True, False):                 # three outer petals, then three inner
            for k in range(6):
                if (k % 2 == 1) != outer:
                    continue
                ang = rot + k * math.pi / 3
                L = R * (0.88 if outer else 1.0)
                wm = 0.25 * L * open_w
                bend = 0.07 if k % 4 < 2 else -0.07
                d.polygon(self._petal(P0, cx, cy, L, wm, bend, ang, tilt),
                          fill=shade(col, 0.72 if outer else 0.86))
                d.polygon(self._petal(P0, cx, cy, L, wm, bend, ang, tilt, 0.10, 0.97, 0.55),
                          fill=shade(col, 0.85 if outer else 1.08))
                mid = []
                for s in range(7):
                    u = 0.12 + 0.80 * s / 6
                    x, y = u * L, bend * L * u * u
                    mid.append(P0(cx + x * math.cos(ang) - y * math.sin(ang),
                                  cy + (x * math.sin(ang) + y * math.cos(ang)) * tilt))
                d.line(mid, fill=shade(col, 1.35), width=1)
        r = 0.12 * R
        c = P0(cx, cy)
        sx = r * self.S
        d.ellipse([c[0] - sx, c[1] - sx * tilt, c[0] + sx, c[1] + sx * tilt], fill=GOLD)


# ------------------------------------------------------------------------ music
def find_music():
    """Music file: given on the command line, or a file called music.* next to this script."""
    import glob
    import os
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        return args[0]
    here = os.path.dirname(os.path.abspath(__file__))
    for ext in ("mp3", "wav", "ogg"):
        hits = glob.glob(os.path.join(here, "music." + ext))
        if hits:
            return hits[0]
    return None


class Music:
    def __init__(self, path):
        self.path, self.mode = path, None
        if not path:
            return
        try:
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(VOLUME)
            self.mode = "pygame"
        except Exception:
            if path.lower().endswith(".wav") and sys.platform == "win32":
                self.mode = "winsound"
            else:
                print("Music needs pygame for mp3/ogg files. Install it with:\n"
                      "    py -m pip install pygame\n"
                      "(or use a .wav file, which works without it)")

    def play(self):
        if self.mode == "pygame":
            import pygame
            pygame.mixer.music.play(-1)                      # loop forever
        elif self.mode == "winsound":
            import winsound
            winsound.PlaySound(self.path, winsound.SND_FILENAME | winsound.SND_ASYNC
                               | winsound.SND_LOOP)

    def stop(self):
        try:
            if self.mode == "pygame":
                import pygame
                pygame.mixer.music.stop()
            elif self.mode == "winsound":
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass


# ---------------------------------------------------------------------- program
def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--snap":      # dev: save one frame
        scene = Scene(1.3)
        scene.render(float(sys.argv[2]), float(sys.argv[2])).save(sys.argv[3])
        return

    import tkinter as tk
    from PIL import ImageTk

    root = tk.Tk()
    root.title("ASCII Lily Bouquet")
    root.configure(bg="black")
    S = min(1.4, (root.winfo_screenheight() - 140) / DH)
    scene = Scene(S)
    label = tk.Label(root, bg="black", bd=0)
    label.pack()
    state = {"t0": time.time(), "img": None}

    music = Music(find_music())
    music.play()

    def restart(_e=None):
        state["t0"] = time.time()
        music.stop()
        music.play()

    def quit_(_e=None):
        music.stop()
        root.destroy()

    root.bind("r", restart)
    root.bind("R", restart)
    for key in ("<Escape>", "q", "Q"):
        root.bind(key, quit_)
    root.protocol("WM_DELETE_WINDOW", quit_)

    def tick():
        tm = time.time() - state["t0"]
        photo = ImageTk.PhotoImage(scene.render(tm, tm))
        label.configure(image=photo)
        state["img"] = photo                      # keep a reference alive
        root.after(15, tick)

    tick()
    root.mainloop()


if __name__ == "__main__":
    main()