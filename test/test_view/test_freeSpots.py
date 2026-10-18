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
'''
*freeSpotIn()* and *clearOf()* (in *layout*) give just what they gave before
they were made quicker: the same spot, with the same tie-breaking, as the
straightforward versions kept here (*freeSpotInBefore()*, *clearOfBefore()*:
every grid spot sorted by distance; every pair of candidates against every
rect), over many seeded random cases -- on round numbers, so there are many
ties, and on fractions.

Created on Oct 18, 2026

@author: robkremer
'''
import random
import unittest
from typing import Sequence, Iterable
from sn.view.graphics.layout import freeSpotIn, clearOf, intoRect


def freeSpotInBefore(box:Sequence[float], rect:Sequence[float], obstacles:Iterable[Sequence[float]], *,
                     margin:float=10.0, topMargin:float|None=None, gap:float|tuple[float, float]=10.0, step:float=10.0,
                     rows:bool=False) -> tuple[float, float]|None:
  'layout.freeSpotIn() as it was (8cba6f2).'
  obs = [o for o in obstacles]
  gx, gy = gap if isinstance(gap, tuple) else (gap, gap)
  w, h = box[2] - box[0], box[3] - box[1]
  lo_x, lo_y = rect[0] + margin, rect[1] + (margin if topMargin is None else topMargin)
  hi_x, hi_y = rect[2] - margin - w, rect[3] - margin - h
  if hi_x < lo_x or hi_y < lo_y:
    return None
  def clear(x:float, y:float) -> bool:
    return all(x + w + gx <= o[0] or o[2] + gx <= x or y + h + gy <= o[1] or o[3] + gy <= y for o in obs)
  nx, ny = int((hi_x - lo_x) // step), int((hi_y - lo_y) // step)
  spots = [(lo_x + i * step, lo_y + j * step) for i in range(nx + 1) for j in range(ny + 1)]
  if rows:
    spots.sort(key=lambda p: (p[1], p[0]))
  else:
    ex, ey = intoRect(box, rect, margin, topMargin)
    tx, ty = box[0] + ex, box[1] + ey
    if clear(tx, ty):
      return ex, ey
    spots.sort(key=lambda p: (p[0] - tx) ** 2 + (p[1] - ty) ** 2)
  for x, y in spots:
    if clear(x, y):
      return x - box[0], y - box[1]
  return None

def clearOfBefore(box:Sequence[float], keepOut:Sequence[Sequence[float]], obstacles:Sequence[Sequence[float]]=[], *,
                  within:Sequence[float]|None=None, gap:float=10.0) -> tuple[float, float]|None:
  'layout.clearOf() as it was (8cba6f2).'
  w, h = box[2] - box[0], box[3] - box[1]
  def hits(x:float, y:float, rects:Sequence[Sequence[float]], g:float) -> bool:
    return any(x < r[2] + g and r[0] - g < x + w and y < r[3] + g and r[1] - g < y + h for r in rects)
  def inside(x:float, y:float) -> bool:
    return within is None or (within[0] <= x and within[1] <= y and x + w <= within[2] and y + h <= within[3])
  def search(rects:Sequence[Sequence[float]]) -> tuple[float, float]|None:
    xs, ys = {box[0]}, {box[1]}
    for r, g in [*((r, gap) for r in keepOut), *((r, gap / 2) for r in rects)]:
      xs |= {r[0] - g - w, r[2] + g}
      ys |= {r[1] - g - h, r[3] + g}
    if within is not None:
      xs |= {within[0], within[2] - w}
      ys |= {within[1], within[3] - h}
    best:tuple[float, float, float]|None = None
    for x in xs:
      for y in ys:
        d = (x - box[0]) ** 2 + (y - box[1]) ** 2
        if (best is None or d < best[0]) and inside(x, y) and not hits(x, y, keepOut, gap) and not hits(x, y, rects, gap / 2):
          best = (d, x, y)
    return None if best is None else (best[1] - box[0], best[2] - box[1])
  if inside(box[0], box[1]) and not hits(box[0], box[1], keepOut, gap):
    return 0.0, 0.0
  return search(obstacles) or (search([]) if obstacles else None)


class Test(unittest.TestCase):

  def rect(self, rnd:random.Random, x0:float, y0:float, x1:float, y1:float, wMax:float, hMax:float, frac:bool) -> list[float]:
    'A random rect with its top left in [x0, x1] x [y0, y1].'
    num = (lambda a, b: rnd.uniform(a, b)) if frac else (lambda a, b: rnd.randrange(int(a) // 5, int(b) // 5 + 1) * 5)
    x, y = num(x0, x1), num(y0, y1)
    return [x, y, x + num(5, wMax), y + num(5, hMax)]

  def test_freeSpotInAsBefore(self):
    rnd = random.Random(1)
    nones = found = 0
    for case in range(1500):
      frac = case % 3 == 0
      W, H = rnd.choice([(200, 150), (400, 300), (700, 500)])
      rect = [rnd.choice([0, -50, 120]), rnd.choice([0, 35, -20])]
      rect += [rect[0] + W, rect[1] + H]
      box = self.rect(rnd, rect[0] - 300, rect[1] - 300, rect[2] + 300, rect[3] + 300, 120, 60, frac)
      obstacles = [self.rect(rnd, rect[0] - 40, rect[1] - 40, rect[2], rect[3], 100, 60, frac)
                   for _ in range(rnd.choice([0, 1, 3, 8, 20, 40]))]
      kw:dict = dict(margin=rnd.choice([0, 5, 10, 12.5]), rows=rnd.random() < 0.3)
      if rnd.random() < 0.4: kw["topMargin"] = rnd.choice([0, 22, 30.5])
      if rnd.random() < 0.5: kw["gap"] = rnd.choice([0, 5, 10, (10, 4), (7.5, 12)])
      if rnd.random() < 0.3: kw["step"] = rnd.choice([5, 7.5, 10, 13])
      want = freeSpotInBefore(box, rect, obstacles, **kw)
      self.assertEqual(freeSpotIn(box, rect, obstacles, **kw), want, (case, box, rect, obstacles, kw))
      nones += want is None
      found += want is not None
    self.assertGreater(nones, 50)
    self.assertGreater(found, 500)

  def test_clearOfAsBefore(self):
    rnd = random.Random(2)
    nones = moved = 0
    for case in range(1500):
      frac = case % 3 == 0
      box = self.rect(rnd, 0, 0, 300, 300, 80, 50, frac)
      keepOut = [self.rect(rnd, -50, -50, 300, 300, 200, 200, frac) for _ in range(rnd.choice([0, 1, 1, 2, 4, 8]))]
      obstacles = [self.rect(rnd, -100, -100, 400, 400, 80, 50, frac) for _ in range(rnd.choice([0, 0, 2, 6, 20, 50]))]
      kw:dict = {}
      if rnd.random() < 0.5: kw["gap"] = rnd.choice([0, 5, 10, 7.5])
      if rnd.random() < 0.4: kw["within"] = self.rect(rnd, -100, -100, 50, 50, 600, 600, frac)
      want = clearOfBefore(box, keepOut, obstacles, **kw)
      self.assertEqual(clearOf(box, keepOut, obstacles, **kw), want, (case, box, keepOut, obstacles, kw))
      nones += want is None
      moved += want is not None and want != (0, 0)
    self.assertGreater(nones, 20)
    self.assertGreater(moved, 500)

  def test_ties(self):
    'Several spots as near as each other: the same one as before.'
    rect = [0, 0, 400, 300]
    for box, obstacles in (
        ([170, 135, 230, 165], [[170, 135, 230, 165]]), # (its own spot taken: as near left and right, up and down)
        ([170, 135, 230, 165], [[150, 120, 250, 180]]),
        ([500, 135, 560, 165], [[300, 100, 400, 200]]),
        ([170, 135, 230, 165], [[100, 0, 300, 300]])):
      for kw in ({}, {"gap": 0}, {"step": 5}, {"gap": (10, 0)}):
        self.assertEqual(freeSpotIn(box, rect, obstacles, **kw), freeSpotInBefore(box, rect, obstacles, **kw), (box, obstacles, kw))
    for box, keepOut, obstacles, within in (
        ([140, 140, 160, 160], [[100, 100, 200, 200]], [], None), # (in the middle: as near out each side)
        ([140, 140, 160, 160], [[100, 100, 200, 200]], [[60, 140, 90, 160], [210, 140, 240, 160]], None),
        ([140, 140, 160, 160], [[100, 100, 200, 200]], [], [0, 0, 300, 300]),
        ([100, 100, 200, 200], [[100, 100, 200, 200]], [], None)):
      self.assertEqual(clearOf(box, keepOut, obstacles, within=within), clearOfBefore(box, keepOut, obstacles, within=within),
                       (box, keepOut, obstacles, within))

if __name__ == "__main__":
  unittest.main()
