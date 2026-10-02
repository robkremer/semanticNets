'''
Draw the app's (placeholder) icon -- a little semantic network: three boxes
joined by arrows, on a rounded square -- as packaging/sn.icns, and the same
picture as the documentation's logo and favicon (sphinx/source/images/sn-*.png).

Run with the build venv's Python (it needs Pillow): see build.xml's "icon"
target. Replace sn.icns with a designed icon whenever there is one.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import math, os, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

BACKGROUND = (255, 212, 38, 255) # a bright yellow
BORDER = (120, 72, 0, 255)       # a deep amber, round the edge
ORANGE = (255, 122, 0, 255)
WHITE = (255, 255, 255, 255)
INK = (30, 30, 30, 255)          # the boxes' outlines, and the plain relation
ISA = (28, 58, 200, 255)         # the isa arrows (blue, as in the editor)

def draw(size:int) -> Image.Image:
  S = 1024
  img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
  d = ImageDraw.Draw(img)
  m = 90 # (the macOS icon grid's margin round the rounded square)
  d.rounded_rectangle([m, m, S - m, S - m], radius=185, fill=BACKGROUND, outline=BORDER, width=16)
  # three big boxes, reaching nearly to the edges: top and left orange, right white
  w, h = 300, 190
  boxes = {"a": ((512, 252), ORANGE), "b": ((272, 734), ORANGE), "c": ((752, 734), WHITE)}
  def edge(p, q):
    # from the edge of box p toward box q, stopping at q's edge
    (x1, y1), (x2, y2) = p, q
    dx, dy = x2 - x1, y2 - y1
    t = min((w / 2) / abs(dx) if dx else 9e9, (h / 2) / abs(dy) if dy else 9e9)
    return (x1 + dx * t, y1 + dy * t), (x2 - dx * t, y2 - dy * t)
  def arrow(p, q, color):
    (sx, sy), (ex, ey) = edge(p, q)
    a = math.atan2(ey - sy, ex - sx)
    L = 84 # (the head's length)
    d.line([sx, sy, ex - (L - 10) * math.cos(a), ey - (L - 10) * math.sin(a)], fill=color, width=26)
    d.polygon([(ex, ey), (ex - L * math.cos(a - 0.42), ey - L * math.sin(a - 0.42)),
               (ex - L * math.cos(a + 0.42), ey - L * math.sin(a + 0.42))], fill=color)
  # a soft drop shadow under the top box -- it's the type (in the editor, types have shadows)
  shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
  (x, y), _ = boxes["a"]
  ImageDraw.Draw(shadow).rectangle([x - w / 2 + 26, y - h / 2 + 30, x + w / 2 + 26, y + h / 2 + 30], fill=(60, 30, 0, 150))
  img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))
  d = ImageDraw.Draw(img)
  arrow(boxes["b"][0], boxes["a"][0], ISA)
  arrow(boxes["c"][0], boxes["a"][0], ISA)
  arrow(boxes["b"][0], boxes["c"][0], INK)
  for (x, y), fill in boxes.values():
    d.rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], fill=fill, outline=INK, width=16)
  return img.resize((size, size), Image.LANCZOS)

def main() -> None:
  out = os.path.join(HERE, "sn.icns")
  tmp = tempfile.mkdtemp()
  iconset = os.path.join(tmp, "sn.iconset")
  os.makedirs(iconset)
  for n in (16, 32, 128, 256, 512):
    draw(n).save(os.path.join(iconset, f"icon_{n}x{n}.png"))
    draw(n * 2).save(os.path.join(iconset, f"icon_{n}x{n}@2x.png"))
  subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out], check=True)
  draw(256).save(os.path.join(HERE, "sn-icon.png"))
  images = os.path.join(HERE, "..", "sphinx", "source", "images") # (the documentation's logo and favicon: see sphinx/source/conf.py)
  draw(128).save(os.path.join(images, "sn-logo.png"))
  draw(64).save(os.path.join(images, "sn-favicon.png"))
  shutil.rmtree(tmp)
  print("wrote", out)

if __name__ == "__main__":
  main()
