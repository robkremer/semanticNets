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
*LayoutHeuristic.findOverlapping()* finds the same 'vis/shape' items whether
it asks Tk for each overlapping item's tags or is given the view's shapes up
front, as *FindFree.placeNode()* gives them (and with either, leaves out
*exclude*): on a real Tk canvas, in a withdrawn root.

Created on Oct 18, 2026

@author: robkremer
'''
import random
import unittest
import tkinter as tk
from types import SimpleNamespace
from sn.view.graphics.sngView import SNGView
from sn.view.graphics.layout import FindFree

class TestFindOverlapping(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    try:
      cls.root = tk.Tk()
    except tk.TclError as ex:
      raise unittest.SkipTest(f"no display: {ex}")
    cls.root.withdraw()

  @classmethod
  def tearDownClass(cls):
    cls.root.destroy()

  def setUp(self):
    self.canvas = tk.Canvas(self.root, width=600, height=600)
    rng = random.Random(7)
    self.shapeIds:list[int] = []
    for _ in range(120): # boxes (some overlapping), and other items over them: text, lines, untagged boxes
      x, y = rng.uniform(0, 550), rng.uniform(0, 550)
      w, h = rng.uniform(10, 60), rng.uniform(10, 40)
      match rng.randrange(4):
        case 0 | 1:
          self.shapeIds.append(self.canvas.create_rectangle(x, y, x + w, y + h, tags=("vis/shape", f"obj{_}")))
        case 2:
          self.canvas.create_text(x, y, text="label", tags=("vis/text", f"obj{_}"))
        case 3:
          self.canvas.create_line(x, y, x + w, y + h, tags=("vis/line",))
    view = SimpleNamespace(canvas=self.canvas)
    view.intersectTag = lambda ids, tag, exclude=[]: SNGView.intersectTag(view, ids, tag, exclude) # type: ignore[arg-type]
    self.layout = object.__new__(FindFree) # (just findOverlapping(): the constructor wants a real view)
    self.layout.view = view # type: ignore[assignment]

  def tearDown(self):
    self.canvas.destroy()

  def rects(self):
    rng = random.Random(11)
    for _ in range(200):
      x, y = rng.uniform(-20, 600), rng.uniform(-20, 600)
      yield [x, y, x + rng.uniform(1, 150), y + rng.uniform(1, 150)]
    yield [0, 0, 600, 600]    # everything
    yield [-50, -50, -40, -40] # nothing

  def test_sameWithAndWithoutShapes(self):
    shapes = set(self.canvas.find_withtag("vis/shape"))
    self.assertEqual(shapes, set(self.shapeIds))
    found = 0
    for rect in self.rects():
      without = self.layout.findOverlapping(rect)
      withShapes = self.layout.findOverlapping(rect, shapes=shapes)
      self.assertEqual(without, withShapes, rect)
      self.assertTrue(set(without) <= shapes)
      found += len(without)
    self.assertGreater(found, 100) # (the rectangles do find things)
    self.assertEqual(sorted(self.layout.findOverlapping([0, 0, 600, 600], shapes=shapes)), sorted(self.shapeIds))

  def test_exclude(self):
    shapes = set(self.canvas.find_withtag("vis/shape"))
    rect = [0, 0, 600, 600]
    exclude = self.shapeIds[::3]
    without = self.layout.findOverlapping(rect, exclude)
    withShapes = self.layout.findOverlapping(rect, exclude, shapes)
    self.assertEqual(without, withShapes)
    self.assertEqual(sorted(without), sorted(set(self.shapeIds) - set(exclude)))

if __name__ == "__main__":
  unittest.main()
