'''
Pictures of what's on the canvas: a PDF drawn from the canvas's own items
(rectangles, ovals, polygons, lines and text -- what *Shape*, *Decorator* and
the connectors draw), and a PNG made from it, for the clipboard (see
*copyImage()*): eg: to paste a rule into Messages or Preview.

Tk can only draw on the screen, and macOS no longer converts the PostScript a
Tk canvas can write, so the items are drawn again here, as PDF: a vector
picture, with no need for a screen capture (and its permission), of
everything asked for, on screen or not. Text is set in PDF's own Helvetica,
which is very close to the canvas's Arial; a few symbols it hasn't (eg: the
arrows in names) are taken from PDF's Symbol font, and a window's collapse
triangle is drawn. The PNG is made from the PDF at twice the size (marked 144
dpi, so it's shown the same size: sharp on a Retina screen) -- by macOS's
*sips*; elsewhere, by the *pypdfium2* package -- and put on the clipboard (see
*util.platformSupport.pdfToPNG()*, *copyPNG()*).

Created on Oct 8, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
#################################################################################
# (c) Copyright 2026, Rob Kremer, MIT open source license.                      #
#                                                                               #
# Permission is hereby granted, free of charge, to any person obtaining a copy  #
# of this software and associated documentation files (the "Software"), to deal #
# in the Software without restriction, including without limitation the rights  #
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell     #
# copies of the Software, and to permit persons to whom the Software is         #
# furnished to do so, subject to the following conditions:                      #
#                                                                               #
# The above copyright notice and this permission notice shall be included in all#
# copies or substantial portions of the Software.                               #
#                                                                               #
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR    #
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,      #
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE   #
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER        #
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, #
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE #
# SOFTWARE.                                                                     #
#################################################################################
from __future__ import annotations
import math
import os
import shutil
import tempfile
import zlib
import tkinter as tk
import tkinter.font as tkfont
from typing import Iterable, Sequence
from util.platformSupport import pdfToPNG, copyPNG

Point = tuple[float, float]

MARGIN = 10
"Space (canvas pixels) left around what's drawn."

PNG_SCALE = 2
"How much bigger than the canvas the PNG is drawn (see the module's description)."

SYMBOLS = {"→": 0xAE, "←": 0xAC, "↑": 0xAD, "↓": 0xAF, "⇒": 0xDE, "⇐": 0xDC,
           "∀": 0x22, "∃": 0x24, "∈": 0xCE, "≠": 0xB9, "≤": 0xA3, "≥": 0xB3,
           "×": 0xB4, "∞": 0xA5, "∧": 0xD9, "∨": 0xDA}
"Characters not in Helvetica that PDF's Symbol font has: its codes for them."

TRIANGLES = {"▼": "down", "▾": "down", "▶": "right", "▸": "right",
             "▲": "up", "▴": "up", "◀": "left", "◂": "left"}
"Characters drawn as triangles (eg: a context window's collapse toggle)."

FONTS = {(False, False): "Helvetica", (True, False): "Helvetica-Bold",
         (False, True): "Helvetica-Oblique", (True, True): "Helvetica-BoldOblique"}
"PDF's fonts for (bold, italic)."

class PDF:
  '''
  A one-page PDF, drawn in canvas coordinates (y down) within *box*, at
  *scale* points per canvas pixel.
  '''
  def __init__(self, box:list[float], scale:float=1.0):
    '''
    :param box: The part of the canvas to draw (x1, y1, x2, y2).
    :param scale: Points per canvas pixel.
    '''
    self.box, self.scale = box, scale
    self.ops:list[str] = []
    "The page's content stream, so far."
    self.fonts:dict[str, str] = {}
    "The fonts used: PDF base font name -> resource name (F1, ...)."

  def pt(self, x:float, y:float) -> str:
    '''
    :returns: Canvas point (*x*, *y*) as PDF coordinates (y up, from the bottom left).
    '''
    return f"{(x - self.box[0]) * self.scale:.2f} {(self.box[3] - y) * self.scale:.2f}"

  def color(self, rgb:tuple[float, float, float], stroke:bool) -> None:
    self.ops.append(f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} {'RG' if stroke else 'rg'}")

  def lineStyle(self, width:float, dash:list[float], cap:str="butt", join:str="miter") -> None:
    caps, joins = {"butt": 0, "round": 1, "projecting": 2}, {"miter": 0, "round": 1, "bevel": 2}
    self.ops.append(f"{max(width, 0.0) * self.scale:.2f} w {caps.get(cap, 0)} J {joins.get(join, 0)} j")
    self.ops.append(f"[{' '.join(f'{d * self.scale:.2f}' for d in dash)}] 0 d")

  def path(self, segments:list[tuple[Point, ...]], close:bool) -> None:
    '''
    Start a path: *segments* is the start point, then (end point,) for a
    straight line or (control 1, control 2, end point) for a cubic curve.
    '''
    self.ops.append(f"{self.pt(*segments[0][0])} m")
    for s in segments[1:]:
      self.ops.append(f"{self.pt(*s[0])} l" if len(s) == 1 else f"{' '.join(self.pt(*p) for p in s)} c")
    if close:
      self.ops.append("h")

  def paint(self, fill:bool, stroke:bool) -> None:
    self.ops.append("B" if fill and stroke else "f" if fill else "S" if stroke else "n")

  def text(self, x:float, y:float, s:bytes, font:str, size:float) -> None:
    '''
    Set *s* (already encoded for *font*) with its baseline starting at canvas point (*x*, *y*).
    '''
    ref = self.fonts.setdefault(font, f"F{len(self.fonts) + 1}")
    esc = s.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)").decode("latin-1")
    self.ops.append(f"BT /{ref} {size * self.scale:.2f} Tf {self.pt(x, y)} Td ({esc}) Tj ET")

  def bytes(self) -> bytes:
    '''
    :returns: The PDF file.
    '''
    w, h = (self.box[2] - self.box[0]) * self.scale, (self.box[3] - self.box[1]) * self.scale
    content = zlib.compress("\n".join(self.ops).encode("latin-1"))
    fontRefs = " ".join(f"/{ref} {5 + i} 0 R" for i, ref in enumerate(self.fonts.values()))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.2f} {h:.2f}] /Resources << /Font << {fontRefs} >> >> /Contents 4 0 R >>".encode(),
            f"<< /Length {len(content)} /Filter /FlateDecode >>\nstream\n".encode() + content + b"\nendstream"]
    for name in self.fonts:
      enc = "" if name == "Symbol" else " /Encoding /WinAnsiEncoding"
      objs.append(f"<< /Type /Font /Subtype /Type1 /BaseFont /{name}{enc} >>".encode())
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, o in enumerate(objs):
      offsets.append(len(out))
      out += f"{i + 1} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)

def _pairs(coords:list[float]) -> list[Point]:
  return [(coords[i], coords[i + 1]) for i in range(0, len(coords) - 1, 2)]

def _mid(a:Point, b:Point) -> Point:
  return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

def _quad(s:Point, c:Point, e:Point) -> tuple[Point, Point, Point]:
  'The cubic curve (control 1, control 2, end) that is the quadratic one from *s* to *e*, with control *c*.'
  return ((s[0] + 2 * (c[0] - s[0]) / 3, s[1] + 2 * (c[1] - s[1]) / 3),
          (e[0] + 2 * (c[0] - e[0]) / 3, e[1] + 2 * (c[1] - e[1]) / 3), e)

def splineSegments(pts:Sequence[Point], smooth:str, closed:bool) -> list[tuple[Point, ...]]:
  '''
  :param pts: An item's points.
  :param smooth: Its "smooth" option: "raw" (the points are a cubic Bezier
    curve's: end, control, control, end, ...), something true (a Tk spline:
    the quadratic B-spline through the midpoints of the points' segments, and
    the end points) or not (straight lines).
  :param closed: A polygon (or a line that ends where it starts).
  :returns: The path the item draws (see *PDF.path()*).
  '''
  if len(pts) < 2:
    return [(pts[0],)] if pts else []
  if smooth == "raw":
    ret:list[tuple[Point, ...]] = [(pts[0],)]
    for i in range(1, len(pts) - 2, 3):
      ret.append((pts[i], pts[i + 1], pts[i + 2]))
    return ret
  if smooth in ("", "0", "false", "no", "off") or len(pts) < 3:
    return [(p,) for p in pts]
  if closed or pts[0] == pts[-1]:
    ring = pts[:-1] if pts[0] == pts[-1] else pts
    n = len(ring)
    ret = [(_mid(ring[-1], ring[0]),)]
    for i in range(n):
      ret.append(_quad(_mid(ring[i - 1], ring[i]), ring[i], _mid(ring[i], ring[(i + 1) % n])))
    return ret
  ret = [(pts[0],)]
  for i in range(len(pts) - 2):
    s = pts[0] if i == 0 else _mid(pts[i], pts[i + 1])
    e = pts[-1] if i == len(pts) - 3 else _mid(pts[i + 1], pts[i + 2])
    ret.append(_quad(s, pts[i + 1], e))
  return ret

def _ellipse(x1:float, y1:float, x2:float, y2:float) -> list[tuple[Point, ...]]:
  cx, cy, rx, ry = (x1 + x2) / 2, (y1 + y2) / 2, (x2 - x1) / 2, (y2 - y1) / 2
  k = 0.5523
  return [((cx + rx, cy),),
          ((cx + rx, cy + k * ry), (cx + k * rx, cy + ry), (cx, cy + ry)),
          ((cx - k * rx, cy + ry), (cx - rx, cy + k * ry), (cx - rx, cy)),
          ((cx - rx, cy - k * ry), (cx - k * rx, cy - ry), (cx, cy - ry)),
          ((cx + k * rx, cy - ry), (cx + rx, cy - k * ry), (cx + rx, cy))]

def arrowHead(tip:Point, toward:Point, width:float, shape:tuple[float, float, float]) -> tuple[list[Point], Point]:
  '''
  A Tk line's arrowhead at *tip*, the line coming from *toward*.

  :param shape: Its "arrowshape": (d1, d2, d3) -- as far along the line from
    the tip to the neck, and to the trailing points, and how far the trailing
    points are out from the line's edge.
  :returns: The head's polygon, and where the line is to end (under the head).
  '''
  d1, d2, d3 = shape
  dx, dy = tip[0] - toward[0], tip[1] - toward[1]
  n = math.hypot(dx, dy) or 1.0
  ux, uy = dx / n, dy / n
  px, py = -uy, ux
  out = width / 2 + d3
  neck = (tip[0] - ux * d1, tip[1] - uy * d1)
  a = (tip[0] - ux * d2 + px * out, tip[1] - uy * d2 + py * out)
  b = (tip[0] - ux * d2 - px * out, tip[1] - uy * d2 - py * out)
  frac = (width / 2) / out if out else 0
  back = frac * d2 + d1 * (1 - frac) / 2
  return [tip, a, neck, b], (tip[0] - ux * back, tip[1] - uy * back)

class Renderer:
  '''
  Draws canvas items into a *PDF*.
  '''
  def __init__(self, canvas:tk.Canvas, pdf:PDF):
    self.c, self.pdf = canvas, pdf
    self._rgb:dict[str, tuple[float, float, float]|None] = {}
    self._fonts:dict[str, tkfont.Font] = {}

  def rgb(self, color:str) -> tuple[float, float, float]|None:
    '''
    :returns: Tk colour *color* as (r, g, b) in 0..1, or None if it's "" (none).
    '''
    if not color:
      return None
    if color not in self._rgb:
      try:
        r, g, b = self.c.winfo_rgb(color)
        self._rgb[color] = (r / 65535, g / 65535, b / 65535)
      except tk.TclError:
        self._rgb[color] = None
    return self._rgb[color]

  def opt(self, item:int, name:str) -> str:
    try:
      return str(self.c.itemcget(item, name))
    except tk.TclError:
      return ""

  def num(self, item:int, name:str, default:float=0.0) -> float:
    try:
      return float(self.opt(item, name))
    except ValueError:
      return default

  def dash(self, item:int) -> list[float]:
    d = self.opt(item, "dash")
    try:
      return [float(v) for v in d.replace(",", " ").split()] if d and d[0].isdigit() else []
    except ValueError:
      return []

  def draw(self, item:int) -> None:
    '''
    Draw canvas item *item* (if it's a kind that's drawn here).
    '''
    kind = self.c.type(item)
    coords = [float(v) for v in self.c.coords(item)]
    if not coords:
      return
    if kind == "text":
      self.drawText(item, coords)
      return
    fill = self.rgb(self.opt(item, "fill"))
    outline = self.rgb(self.opt(item, "outline")) if kind != "line" else None
    width = self.num(item, "width", 1.0)
    p = self.pdf
    if kind in ("rectangle", "oval", "polygon"):
      if kind == "rectangle":
        x1, y1, x2, y2 = coords[:4]
        segs:list[tuple[Point, ...]] = [((x1, y1),), ((x2, y1),), ((x2, y2),), ((x1, y2),)]
      elif kind == "oval":
        segs = _ellipse(*coords[:4])
      else:
        segs = splineSegments(_pairs(coords), self.opt(item, "smooth"), closed=True)
      if fill is not None:
        p.color(fill, stroke=False)
      if outline is not None and width > 0:
        p.color(outline, stroke=True)
        p.lineStyle(width, self.dash(item), join=self.opt(item, "joinstyle") or "miter")
      p.path(segs, close=True)
      p.paint(fill is not None, outline is not None and width > 0)
    elif kind == "line" and fill is not None:
      pts = _pairs(coords)
      arrow = self.opt(item, "arrow")
      heads:list[list[Point]] = []
      if arrow in ("first", "both", "last") and len(pts) >= 2:
        try:
          shape = tuple(float(v) for v in self.opt(item, "arrowshape").split())
        except ValueError:
          shape = (8.0, 10.0, 3.0)
        if len(shape) != 3:
          shape = (8.0, 10.0, 3.0)
        if arrow in ("first", "both"):
          head, pts[0] = arrowHead(pts[0], pts[1], width, shape) #type: ignore[arg-type]
          heads.append(head)
        if arrow in ("last", "both"):
          head, pts[-1] = arrowHead(pts[-1], pts[-2], width, shape) #type: ignore[arg-type]
          heads.append(head)
      p.color(fill, stroke=True)
      p.lineStyle(width, self.dash(item), cap=self.opt(item, "capstyle") or "butt", join=self.opt(item, "joinstyle") or "round")
      p.path(splineSegments(pts, self.opt(item, "smooth"), closed=False), close=False)
      p.paint(False, True)
      for head in heads:
        p.color(fill, stroke=False)
        p.path([(q,) for q in head], close=True)
        p.paint(True, False)

  def font(self, spec:str) -> tkfont.Font:
    if spec not in self._fonts:
      self._fonts[spec] = tkfont.Font(root=self.c, font=spec)
    return self._fonts[spec]

  def wrap(self, text:str, f:tkfont.Font, width:float) -> list[str]:
    '''
    :returns: *text*'s lines, as a Tk text item *width* wide wraps it (at spaces).
    '''
    lines:list[str] = []
    for para in text.split("\n"):
      if width <= 0:
        lines.append(para)
        continue
      line = ""
      for word in para.split(" "):
        trial = word if not line else line + " " + word
        if line and f.measure(trial) > width:
          lines.append(line)
          line = word
        else:
          line = trial
      lines.append(line)
    return lines

  def drawText(self, item:int, coords:list[float]) -> None:
    text = self.opt(item, "text")
    color = self.rgb(self.opt(item, "fill"))
    box = self.c.bbox(item)
    if not text.strip() or color is None or box is None:
      return
    f = self.font(self.opt(item, "font"))
    actual = f.actual()
    size = float(actual["size"])
    size = -size if size < 0 else float(self.c.winfo_fpixels(f"{size}p"))
    name = FONTS[(actual["weight"] == "bold", actual["slant"] == "italic")]
    ascent, linespace = f.metrics("ascent"), f.metrics("linespace")
    justify = self.opt(item, "justify") or "left"
    lines = self.wrap(text, f, self.num(item, "width"))
    widths = [f.measure(l) for l in lines]
    left, right = float(box[0]), float(box[2])
    top = (box[1] + box[3]) / 2 - len(lines) * linespace / 2 # (the lines, centred in the box Tk drew them in)
    p = self.pdf
    p.color(color, stroke=False)
    for i, (line, w) in enumerate(zip(lines, widths)):
      x = left if justify == "left" else right - w if justify == "right" else (left + right - w) / 2
      y = top + i * linespace + ascent
      self.drawRuns(line, f, x, y, name, size, color, ascent)

  def drawRuns(self, line:str, f:tkfont.Font, x:float, y:float, name:str, size:float,
               color:tuple[float, float, float], ascent:float) -> None:
    '''
    Set *line* at (*x*, *y*) (its baseline): in runs of Helvetica, Symbol, and
    triangles (see *SYMBOLS*, *TRIANGLES*), each placed as the canvas places it.
    '''
    p = self.pdf
    run = ""
    def flush(at:float) -> None:
      if run:
        p.text(at, y, run.encode("cp1252", errors="replace"), name, size)
    start = x
    for i, ch in enumerate(line):
      if ch in SYMBOLS or ch in TRIANGLES:
        flush(start)
        cx = x + f.measure(line[:i])
        w = f.measure(ch)
        if ch in SYMBOLS:
          p.text(cx, y, bytes([SYMBOLS[ch]]), "Symbol", size)
        else:
          h = ascent * 0.6
          x1, x2, y2 = cx + w * 0.15, cx + w * 0.85, y - ascent * 0.1
          y1 = y2 - h
          tri = {"down": [(x1, y1), (x2, y1), ((x1 + x2) / 2, y2)],
                 "up": [(x1, y2), (x2, y2), ((x1 + x2) / 2, y1)],
                 "right": [(x1, y1), (x2, (y1 + y2) / 2), (x1, y2)],
                 "left": [(x2, y1), (x1, (y1 + y2) / 2), (x2, y2)]}[TRIANGLES[ch]]
          p.color(color, stroke=False)
          p.path([(q,) for q in tri], close=True)
          p.paint(True, False)
        run = ""
        start = x + f.measure(line[:i + 1])
      else:
        if not run:
          start = x + f.measure(line[:i])
        run += ch
    flush(start)

def drawItems(canvas:tk.Canvas, items:Iterable[int], scale:float=1.0) -> bytes|None:
  '''
  :param items: Canvas item ids, bottom first.
  :param scale: Points per canvas pixel.
  :returns: A PDF of *items* (those that aren't hidden), on a white page just
    big enough for them, or None if there's nothing to draw.
  '''
  shown = [i for i in items if canvas.itemcget(i, "state") != "hidden" and canvas.type(i) in ("rectangle", "oval", "polygon", "line", "text")]
  boxes = [b for b in (canvas.bbox(i) for i in shown) if b]
  if not boxes:
    return None
  box:list[float] = [min(b[0] for b in boxes) - MARGIN, min(b[1] for b in boxes) - MARGIN,
         max(b[2] for b in boxes) + MARGIN, max(b[3] for b in boxes) + MARGIN]
  pdf = PDF(box, scale)
  pdf.color((1.0, 1.0, 1.0), stroke=False) # (a white background: not transparent, which some programs show black)
  pdf.path([((box[0], box[1]),), ((box[2], box[1]),), ((box[2], box[3]),), ((box[0], box[3]),)], close=True)
  pdf.paint(True, False)
  r = Renderer(canvas, pdf)
  for i in shown:
    r.draw(i)
  return pdf.bytes()

def copyImage(canvas:tk.Canvas, items:list[int]) -> tuple[int, int]:
  '''
  Put a picture of canvas items *items* (bottom first) on the system clipboard, as a PNG.

  :returns: The picture's size (canvas pixels).
  :raises RuntimeError: If there's nothing to draw, or the PNG can't be made or
    put on the clipboard (see *util.platformSupport.pdfToPNG()*, *copyPNG()*).
  '''
  data = drawItems(canvas, items, scale=PNG_SCALE)
  if data is None:
    raise RuntimeError("there's nothing drawn to copy.")
  folder = tempfile.mkdtemp(prefix="snImage-")
  try:
    pdfPath, pngPath = os.path.join(folder, "picture.pdf"), os.path.join(folder, "picture.png")
    with open(pdfPath, "wb") as f:
      f.write(data)
    pdfToPNG(pdfPath, pngPath, 72 * PNG_SCALE)
    copyPNG(pngPath)
  finally:
    shutil.rmtree(folder, ignore_errors=True)
  return _size(canvas, items)

def _size(canvas:tk.Canvas, items:list[int]) -> tuple[int, int]:
  boxes = [b for b in (canvas.bbox(i) for i in items if canvas.itemcget(i, "state") != "hidden") if b]
  if not boxes:
    return 0, 0
  return (max(b[2] for b in boxes) - min(b[0] for b in boxes) + 2 * MARGIN,
          max(b[3] for b in boxes) - min(b[1] for b in boxes) + 2 * MARGIN)
