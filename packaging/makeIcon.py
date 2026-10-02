'''
Draw the app's (placeholder) icon -- a little semantic network: three boxes
joined by arrows, on a rounded square -- as packaging/sn.icns, and the same
picture as the documentation's logo and favicon (sphinx/source/images/sn-*.png).

Run with the build venv's Python (it needs Pillow): see build.xml's "icon"
target. Replace sn.icns with a designed icon whenever there is one.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import math, os, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

def draw(size:int) -> Image.Image:
  S = 1024
  img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
  d = ImageDraw.Draw(img)
  m = 90
  d.rounded_rectangle([m, m, S - m, S - m], radius=180, fill=(244, 241, 232, 255), outline=(60, 70, 90, 255), width=14)
  boxes = {"a": (512, 290), "b": (300, 700), "c": (724, 700)}
  w, h = 230, 130
  def edge(p, q):
    # from the edge of box p's centre toward q, stopping at q's box edge
    (x1, y1), (x2, y2) = p, q
    dx, dy = x2 - x1, y2 - y1
    t = min((w / 2) / abs(dx) if dx else 9e9, (h / 2) / abs(dy) if dy else 9e9)
    return (x1 + dx * t, y1 + dy * t), (x2 - dx * t, y2 - dy * t)
  def arrow(p, q, color):
    (sx, sy), (ex, ey) = edge(p, q)
    d.line([sx, sy, ex, ey], fill=color, width=18)
    a = math.atan2(ey - sy, ex - sx)
    L = 60
    d.polygon([(ex, ey), (ex - L * math.cos(a - 0.45), ey - L * math.sin(a - 0.45)),
               (ex - L * math.cos(a + 0.45), ey - L * math.sin(a + 0.45))], fill=color)
  arrow(boxes["b"], boxes["a"], (40, 60, 200, 255))
  arrow(boxes["c"], boxes["a"], (40, 60, 200, 255))
  arrow(boxes["b"], boxes["c"], (30, 30, 30, 255))
  for (x, y), fill in zip(boxes.values(), [(255, 236, 160, 255), (255, 255, 255, 255), (255, 255, 255, 255)]):
    d.rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], fill=fill, outline=(30, 30, 30, 255), width=14)
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
