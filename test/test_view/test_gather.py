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
from sn.view.graphics.layout import gatherShifts, gatherAxisShifts, freeSpotIn, clearOf


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

  # ---- freeSpotIn: gathering into a context window's pane ---------------------

  def test1000alreadyInsideAndClear(self):
    self.assertEqual(freeSpotIn([50, 50, 110, 80], [0, 0, 400, 300], []), (0, 0))

  def test1100nearestEdge(self):
    'Outside, with nothing in the way: just inside the nearest edge (as intoRect()).'
    dx, dy = freeSpotIn([500, 50, 560, 80], [0, 0, 400, 300], [])
    self.assertEqual((500 + dx + 60, 50 + dy), (390, 50))

  def test1200avoidsObstacles(self):
    rect = [0, 0, 400, 300]
    obstacles = [[320, 30, 390, 90]]                                       # where intoRect() would put it
    box = [500, 50, 560, 80]
    dx, dy = freeSpotIn(box, rect, obstacles, gap=10)
    b = [box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy]
    self.assertTrue(10 <= b[0] and b[2] <= 390 and 10 <= b[1] and b[3] <= 290)  # inside, margin in
    o = obstacles[0]
    self.assertTrue(b[2] + 10 <= o[0] or o[2] + 10 <= b[0] or b[3] + 10 <= o[1] or o[3] + 10 <= b[1])
    self.assertLess(abs(b[0] - 330) + abs(b[1] - 50), 150)                       # near where it was headed

  def test1300noRoom(self):
    self.assertIsNone(freeSpotIn([0, 0, 60, 30], [0, 0, 400, 300], [[0, 0, 400, 300]]))  # full
    self.assertIsNone(freeSpotIn([0, 0, 600, 30], [0, 0, 400, 300], []))                 # too wide

  def test1400manyFit(self):
    'Gathering several, one after another, each clear of those before.'
    rect, placed = [0, 0, 400, 300], []
    for i in range(12):
      box = [1000 + 70 * i, 2000, 1060 + 70 * i, 2030]
      dx, dy = freeSpotIn(box, rect, placed, topMargin=22)
      placed.append([box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy])
    for i, a in enumerate(placed):
      self.assertTrue(10 <= a[0] and a[2] <= 390 and 22 <= a[1] and a[3] <= 290)
      for b in placed[:i]:
        self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

  # ---- clearOf: keeping out of windows ---------------------------------------

  def test2000alreadyClear(self):
    self.assertEqual(clearOf([0, 0, 20, 20], [[100, 100, 300, 300]]), (0, 0))

  def test2100leastWayOut(self):
    'Just inside the left edge: out to the left, clear by the gap.'
    dx, dy = clearOf([105, 150, 125, 170], [[100, 100, 300, 300]], gap=10)
    self.assertEqual((105 + dx + 20, dy), (90, 0))

  def test2200avoidsObstaclesOutside(self):
    'The nearest way out is taken (by something else): the next nearest.'
    dx, dy = clearOf([105, 150, 125, 170], [[100, 100, 300, 300]], [[60, 140, 89, 180]], gap=10)
    b = [105 + dx, 150 + dy, 125 + dx, 170 + dy]
    self.assertFalse(b[0] < 310 and 90 < b[2] and b[1] < 310 and 90 < b[3])         # out of the window
    self.assertFalse(b[0] < 94 and 55 < b[2] and b[1] < 185 and 135 < b[3])        # off the obstacle

  def test2300staysWithin(self):
    'In its own pane, out of a window nested in it: it stays in the pane.'
    pane, inner = [0, 0, 400, 300], [100, 100, 380, 280]
    dx, dy = clearOf([300, 150, 320, 170], [inner], within=pane, gap=10)
    b = [300 + dx, 150 + dy, 320 + dx, 170 + dy]
    self.assertTrue(pane[0] <= b[0] and pane[1] <= b[1] and b[2] <= pane[2] and b[3] <= pane[3])
    self.assertFalse(b[0] < 390 and 90 < b[2] and b[1] < 290 and 90 < b[3])

  def test2400noPlace(self):
    self.assertIsNone(clearOf([10, 10, 30, 30], [[0, 0, 100, 100]], within=[0, 0, 100, 100]))


if __name__ == "__main__":
  unittest.main()
