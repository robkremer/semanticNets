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
The XMLreader plugin's *freeCells()* (what its *separateNodes()* moves): over
many seeded random piles of boxes, afterwards nothing's on anything else (nor
nearer than half the gap to a box moved), what wasn't on anything doesn't
move, and a box moved goes to a free cell near where it was -- and quickly,
with thousands.

Created on Oct 18, 2026

@author: robkremer
'''
import random
import time
import unittest
from sn.plugins import importBundled

class TestFreeCells(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.freeCells = staticmethod(importBundled("XMLreader", "view").freeCells)

  def pile(self, rng:random.Random, n:int, span:float) -> list[list[float]]:
    ret = []
    for _ in range(n):
      x, y = rng.uniform(-span, span), rng.uniform(-span, span)
      ret.append([x, y, x + rng.uniform(20, 120), y + rng.uniform(15, 50)])
    return ret

  def after(self, boxes:list[list[float]], moves:dict[int, tuple[int, int]]) -> list[list[float]]:
    ret = []
    for k, b in enumerate(boxes):
      if k in moves:
        x, y = moves[k]
        ret.append([x, y, x + b[2] - b[0], y + b[3] - b[1]])
      else:
        ret.append(list(b))
    return ret

  @staticmethod
  def apart(a:list[float], b:list[float], gap:float) -> bool:
    return a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1]

  def test_nothingOnAnything(self):
    rng = random.Random(5)
    gap = 40.0
    for case in range(60):
      boxes = self.pile(rng, rng.randrange(2, 120), rng.choice((100, 400, 2000)))
      moves = self.freeCells(boxes, gap)
      out = self.after(boxes, moves)
      for i in range(len(out)):
        for j in range(i + 1, len(out)):
          moved = i in moves or j in moves
          self.assertTrue(self.apart(out[i], out[j], gap / 2 if moved else 0), (case, i, j, out[i], out[j]))

  def test_staysPutIfOnNothing(self):
    'Just the boxes on one before them that stays are moved.'
    rng = random.Random(6)
    for _ in range(20):
      boxes = self.pile(rng, 80, 300)
      staying:list[list[float]] = []
      moved = set()
      for k, b in enumerate(boxes):
        if any(not self.apart(b, s, 0) for s in staying):
          moved.add(k)
        else:
          staying.append(b)
      self.assertEqual(set(self.freeCells(boxes)), moved)
    self.assertEqual(self.freeCells([[0, 0, 50, 20], [100, 0, 150, 20]]), {}) # (apart already: nothing moves)

  def test_nearby(self):
    'One box on another goes to a cell next to where it was.'
    moves = self.freeCells([[0, 0, 60, 20], [10, 5, 70, 25]], 40)
    self.assertEqual(list(moves), [1])
    x, y = moves[1]
    self.assertLessEqual(abs(x - 10) + abs(y - 5), 2 * (60 + 40))

  def test_quickWithThousands(self):
    rng = random.Random(7)
    boxes = self.pile(rng, 4000, 1500) # (most of them on others)
    t = time.monotonic()
    moves = self.freeCells(boxes)
    self.assertLess(time.monotonic() - t, 10.0)
    self.assertGreater(len(moves), 1000)

if __name__ == "__main__":
  unittest.main()
