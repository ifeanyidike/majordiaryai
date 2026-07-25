#!/usr/bin/env python3
"""Generate Major Dairy AI app icons in brand colors.

Mark: three ascending rounded bars (growth/results) with a rising accent dot,
on a Deep Red gradient. Matches the in-app 'analytics' brand mark.
"""
from PIL import Image, ImageDraw

S = 1024
RED_TOP = (199, 72, 80)      # #C74850
RED_BOTTOM = (132, 37, 43)   # #84252B
CREAM = (252, 251, 249)      # #FCFBF9


def gradient_bg(size=S):
    img = Image.new("RGB", (size, size))
    for y in range(size):
        t = y / size
        r = int(RED_TOP[0] + (RED_BOTTOM[0] - RED_TOP[0]) * t)
        g = int(RED_TOP[1] + (RED_BOTTOM[1] - RED_TOP[1]) * t)
        b = int(RED_TOP[2] + (RED_BOTTOM[2] - RED_TOP[2]) * t)
        ImageDraw.Draw(img).line([(0, y), (size, y)], fill=(r, g, b))
    return img


def draw_rings(img):
    """Subtle decorative rings like the app's hero headers."""
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse([620, -180, 1240, 440], outline=(252, 251, 249, 26), width=8)
    d.ellipse([700, 520, 1180, 1000], outline=(252, 251, 249, 18), width=8)
    return img


def draw_mark(draw, cx, cy, scale=1.0, color=CREAM):
    """Three ascending rounded bars + rising dot. Centered at (cx, cy)."""
    bw = int(96 * scale)          # bar width
    gap = int(60 * scale)         # gap between bars
    radius = bw // 2
    heights = [int(200 * scale), int(320 * scale), int(440 * scale)]
    total_w = 3 * bw + 2 * gap
    left = cx - total_w // 2
    baseline = cy + int(240 * scale)

    for i, h in enumerate(heights):
        x0 = left + i * (bw + gap)
        draw.rounded_rectangle([x0, baseline - h, x0 + bw, baseline], radius=radius, fill=color)

    # rising accent dot above the tallest bar
    dot_r = int(46 * scale)
    dot_cx = left + 2 * (bw + gap) + bw // 2
    dot_cy = baseline - heights[2] - int(120 * scale)
    draw.ellipse([dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r], fill=color)


# 1. Full-bleed app icon (iOS + Play Store listing)
icon = gradient_bg()
draw_rings(icon)
draw_mark(ImageDraw.Draw(icon), S // 2, S // 2)
icon.save("assets/images/icon.png")

# 2. Android adaptive foreground (transparent, mark in safe zone ~66%)
fg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
draw_mark(ImageDraw.Draw(fg), S // 2, S // 2, scale=0.62)
fg.save("assets/images/android-icon-foreground.png")

# 3. Android adaptive background (gradient, no mark)
gradient_bg().save("assets/images/android-icon-background.png")

# 4. Android monochrome (white mark, transparent)
mono = Image.new("RGBA", (S, S), (0, 0, 0, 0))
draw_mark(ImageDraw.Draw(mono), S // 2, S // 2, scale=0.62, color=(255, 255, 255))
mono.save("assets/images/android-icon-monochrome.png")

# 5. Splash icon (mark on transparent — splash bg comes from app.json)
splash = Image.new("RGBA", (S, S), (0, 0, 0, 0))
draw_mark(ImageDraw.Draw(splash), S // 2, S // 2, scale=0.8)
splash.save("assets/images/splash-icon.png")

print("icons written")
