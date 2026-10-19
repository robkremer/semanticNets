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
*freeRingSpot()* (in *layout*: *FindFree.placeNode()*'s search) gives just
the spot that *FindFree*'s search gave when it asked Tk about each place
(see *freeRingSpotBefore()*, kept here: the same rings, in the same order,
each place tried against every box) -- over many seeded random cases: in
crowded and sparse boxes, with limits that cut the rings off on each side,
and with nowhere free.

Created on Oct 18, 2026

@author: robkremer
'''
import random
import unittest
from typing import Sequence
from sn.view.graphics.layout import freeRingSpot, _BoxIndex, UNBOUNDED


def freeRingSpotBefore(rect:Sequence[int], boxes:Sequence[Sequence[float]], gap:float, quanta:int=10,
                       limit:Sequence[int]=(-UNBOUNDED, -UNBOUNDED, UNBOUNDED, UNBOUNDED),
                       maxRings:int=100) -> tuple[int, int]|None:
  'FindFree.placeNode()\'s place() as it was (c45ce3d), with Tk\'s find_overlapping() over the boxes.'
  w, h = rect[2] - rect[0], rect[3] - rect[1]
  for dist in range(0, maxRings):
    yStart = max(limit[1], rect[1] - dist * quanta)
    yEnd = min(limit[3], rect[1] + dist * quanta)
    for y in range(yStart, yEnd + 1, quanta):
      xStart = max(limit[0], rect[0] - dist * quanta)
      xEnd = min(limit[2], rect[0] + dist * quanta)
      xIncr = quanta if y == yStart or y == yEnd else max(1, xEnd - xStart)
      for x in range(xStart, xEnd + 1, xIncr):
        g = [x - gap, y - gap, x + w + gap, y + h + gap]
        if not any(o[0] < g[2] and g[0] < o[2] and o[1] < g[3] and g[1] < o[3] for o in boxes):
          return x, y
  return None

class TestFreeRingSpot(unittest.TestCase):

  def boxes(self, rng:random.Random, n:int, span:float) -> list[list[float]]:
    ret = []
    for _ in range(n):
      x, y = rng.uniform(-span, span), rng.uniform(-span, span)
      ret.append([x, y, x + rng.uniform(5, 120), y + rng.uniform(5, 60)])
    return ret

  def check(self, rng:random.Random, n:int, span:float, limited:bool, maxRings:int) -> tuple[int, int]|None:
    boxes = self.boxes(rng, n, span)
    x, y = rng.randrange(-200, 200), rng.randrange(-200, 200)
    rect = [x, y, x + rng.randrange(20, 100), y + rng.randrange(10, 50)]
    limit = [-UNBOUNDED, -UNBOUNDED, UNBOUNDED, UNBOUNDED]
    if limited: # (each side, or not: from inside the rings' reach, so they're cut off)
      for k, d in ((0, -1), (1, -1), (2, 1), (3, 1)):
        if rng.random() < 0.5:
          limit[k] = rect[k % 2] + d * rng.randrange(0, 300)
      if limit[0] > limit[2] or limit[1] > limit[3]:
        return None
    gap = rng.choice((0, 5, 15))
    want = freeRingSpotBefore(rect, boxes, gap, limit=limit, maxRings=maxRings)
    got = freeRingSpot(rect, _BoxIndex(boxes), gap, limit=limit, maxRings=maxRings)
    self.assertEqual(got, want, (rect, limit, gap, n, span))
    return got

  def test_sameAsBefore(self):
    rng = random.Random(3)
    found = notFound = 0
    for case in range(400):
      crowded = case % 2 == 0
      got = self.check(rng, n=300 if crowded else 40, span=400 if crowded else 1500,
                       limited=case % 3 == 0, maxRings=rng.choice((9, 30, 100)))
      if got is None:
        notFound += 1
      else:
        found += 1
    self.assertGreater(found, 100)  # (mostly somewhere,
    self.assertGreater(notFound, 0) #  but sometimes nowhere: crowded, few rings, or limited)

  def test_staysPut(self):
    'Somewhere free stays where it is.'
    self.assertEqual(freeRingSpot([0, 0, 50, 20], _BoxIndex([[100, 100, 150, 150]]), 15), (0, 0))

  def test_withinLimit(self):
    'Never outside its limit -- even if the nearest free place is.'
    boxes = [[-40, -40, 90, 60]]
    limit = [0, 0, UNBOUNDED, UNBOUNDED]
    x, y = freeRingSpot([0, 0, 50, 20], _BoxIndex(boxes), 15, limit=limit) or (None, None)
    self.assertIsNotNone(x)
    self.assertGreaterEqual(x, 0)
    self.assertGreaterEqual(y, 0)

if __name__ == "__main__":
  unittest.main()
