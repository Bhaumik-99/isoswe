"""Generate PWA icons for Marvel Greenfield / Isoswe Township Operations Portal.

Produces:
- apps/web/public/icons/icon-192.png (192x192)
- apps/web/public/icons/icon-512.png (512x512)
- apps/web/public/icons/icon-maskable-512.png (512x512 with safe zone padding)
"""

import os

from PIL import Image, ImageDraw


def create_township_icon(size: int, is_maskable: bool = False) -> Image.Image:
    # 4f46e5 is indigo-600 (Township brand primary)
    img = Image.new("RGBA", (size, size), (79, 70, 229, 255))
    draw = ImageDraw.Draw(img)

    # Scale coordinates
    # Maskable safe zone is central 80% circle (10% padding on each side)
    scale = 0.7 if is_maskable else 0.85
    margin = (1.0 - scale) / 2.0 * size

    content_size = size * scale
    x0 = margin
    y0 = margin
    x1 = x0 + content_size
    y1 = y0 + content_size

    # Draw rounded background badge if not maskable
    if not is_maskable:
        # Rounded corner rectangle for primary app icon
        corner_r = int(size * 0.18)
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [(0, 0), (size - 1, size - 1)],
            radius=corner_r,
            fill=(79, 70, 229, 255),
        )

    # Draw modern geometric towers (Township representation)
    # Tower 1 (Left - medium)
    t1_x0 = x0 + content_size * 0.15
    t1_x1 = x0 + content_size * 0.38
    t1_y0 = y0 + content_size * 0.35
    t1_y1 = y1 - content_size * 0.15
    draw.rectangle([t1_x0, t1_y0, t1_x1, t1_y1], fill=(224, 231, 255, 255))

    # Tower 2 (Center - tall)
    t2_x0 = x0 + content_size * 0.38
    t2_x1 = x0 + content_size * 0.62
    t2_y0 = y0 + content_size * 0.18
    t2_y1 = y1 - content_size * 0.15
    draw.rectangle([t2_x0, t2_y0, t2_x1, t2_y1], fill=(255, 255, 255, 255))

    # Tower 3 (Right - short with emerald accent for Greenfield)
    t3_x0 = x0 + content_size * 0.62
    t3_x1 = x0 + content_size * 0.85
    t3_y0 = y0 + content_size * 0.45
    t3_y1 = y1 - content_size * 0.15
    draw.rectangle([t3_x0, t3_y0, t3_x1, t3_y1], fill=(167, 243, 208, 255))

    # Windows on Center Tower
    win_w = content_size * 0.05
    win_h = content_size * 0.04
    for r in range(4):
        wy = t2_y0 + content_size * (0.08 + r * 0.12)
        # Left window
        wx1 = t2_x0 + content_size * 0.05
        draw.rectangle([wx1, wy, wx1 + win_w, wy + win_h], fill=(79, 70, 229, 255))
        # Right window
        wx2 = t2_x1 - content_size * 0.05 - win_w
        draw.rectangle([wx2, wy, wx2 + win_w, wy + win_h], fill=(79, 70, 229, 255))

    # Ground base bar (emerald green for Greenfield)
    base_y0 = y1 - content_size * 0.15
    base_y1 = y1 - content_size * 0.08
    draw.rounded_rectangle(
        [(x0 + content_size * 0.1, base_y0), (x1 - content_size * 0.1, base_y1)],
        radius=int(content_size * 0.03),
        fill=(16, 185, 129, 255),
    )

    return img


def main():
    out_dir = os.path.join("apps", "web", "public", "icons")
    os.makedirs(out_dir, exist_ok=True)

    icon192 = create_township_icon(192, is_maskable=False)
    icon192.save(os.path.join(out_dir, "icon-192.png"), "PNG")
    print("Generated icon-192.png")

    icon512 = create_township_icon(512, is_maskable=False)
    icon512.save(os.path.join(out_dir, "icon-512.png"), "PNG")
    print("Generated icon-512.png")

    icon_maskable = create_township_icon(512, is_maskable=True)
    icon_maskable.save(os.path.join(out_dir, "icon-maskable-512.png"), "PNG")
    print("Generated icon-maskable-512.png")


if __name__ == "__main__":
    main()
