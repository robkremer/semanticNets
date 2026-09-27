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
Created on Sep 26, 2026

@author: robkremer
'''
import unittest
from sn.view.graphics.layout import gatherShifts, gatherAxisShifts


def grid(nx:int, ny:int, x0:int=0, y0:int=0, w:int=60, h:int=30, gapX:int=40, gapY:int=40) -> list[list[float]]:
  'A tidy nx by ny grid of boxes.'
  return [[x0 + i*(w+gapX), y0 + j*(h+gapY), x0 + i*(w+gapX) + w, y0 + j*(h+gapY) + h]
          for i in range(nx) for j in range(ny)]

def moved(boxes, shifts):
  return [[b[0]+dx, b[1]+dy, b[2]+dx, b[3]+dy] for b, (dx, dy) in zip(boxes, shifts)]


class Test(unittest.TestCase):

  def test0100tidyLayoutUntouched(self):
    boxes = grid(5, 4)
    self.assertTrue(all(s == (0, 0) for s in gatherShifts(boxes)))

  def test0200flungOnOneAxis(self):
    boxes = grid(5, 4) + [[20000, 70, 20060, 100]]  # far right, but level with the pack
    shifts = gatherShifts(boxes)
    self.assertTrue(all(s == (0, 0) for s in shifts[:-1]))  # the pack stays put
    dx, dy = shifts[-1]
    self.assertLess(dx, 0)
    self.assertEqual(dy, 0)                                  # only pulled back along x
    x1 = moved(boxes, shifts)[-1][0]
    packRight = max(b[2] for b in boxes[:-1])
    self.assertGreater(x1, packRight)                        # just beyond the pack, not on it
    self.assertLess(x1 - packRight, 200)

  def test0300flungDiagonally(self):
    boxes = grid(5, 4) + [[-9000, -7000, -8940, -6970]]
    dx, dy = gatherShifts(boxes)[-1]
    self.assertGreater(dx, 0)
    self.assertGreater(dy, 0)

  def test0400strandedGroupKeepsItsShape(self):
    group = grid(2, 2, x0=30000, y0=40)
    boxes = grid(5, 4) + group
    shifts = gatherShifts(boxes)[-4:]
    self.assertEqual(len(set(shifts)), 1)   # the whole group moves by the same amount
    self.assertLess(shifts[0][0], -25000)

  def test0500outliersOnBothSides(self):
    iv = [(0, 50), (60, 110), (120, 170), (180, 230), (-5000, -4950), (9000, 9050)]
    shifts = gatherAxisShifts(iv)
    self.assertEqual(shifts[:4], [0, 0, 0, 0])
    self.assertGreater(shifts[4], 0)
    self.assertLess(shifts[5], 0)
    after = sorted((lo+s, hi+s) for (lo, hi), s in zip(iv, shifts))
    self.assertTrue(all(b[0] > a[1] for a, b in zip(after, after[1:])))  # order kept, no overlaps

  def test0550outliersAreMostOfTheGaps(self):
    # two rows, plus two far-flung objects: the huge gaps outnumber the normal one
    iv = [(100, 114), (100, 114), (180, 194), (180, 194), (4550, 4564), (9000, 9014)]
    shifts = gatherAxisShifts(iv)
    self.assertEqual(shifts[:4], [0, 0, 0, 0])
    self.assertLess(shifts[4], -4000)
    self.assertLess(shifts[5], -8000)

  def test0560looseLayoutUntouched(self):
    boxes = grid(4, 3, gapX=150, gapY=120) + grid(3, 2, x0=900, gapX=150, gapY=120)
    self.assertTrue(all(s == (0, 0) for s in gatherShifts(boxes)))

  def test0600tooFewToJudge(self):
    self.assertEqual(gatherShifts([[0, 0, 10, 10], [5000, 5000, 5010, 5010]]), [(0, 0), (0, 0)])


if __name__ == "__main__":
  unittest.main()
