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
The drag-select box (*SNGView.onButton_1()*, *onB1_Motion()* and
*onB1_ButtonRelease()*) when zoomed and scrolled: the part that needs no screen.
The handlers run on a stand-in view whose stand-in canvas scrolls (canvasx()
adds an offset) and holds items in canvas coordinates, as Tk's does after
*SNGView.zoom()* has scaled them.

Created on Oct 15, 2026

@author: robkremer
'''
import unittest
from types import SimpleNamespace
from sn.view.graphics.sngView import SNGView

class FakeCanvas:
  def __init__(self, scrollX:float, scrollY:float):
    self.scrollX, self.scrollY = scrollX, scrollY
    self.items:dict[int, list[float]] = {}
    self._next = 1

  def canvasx(self, x): return x + self.scrollX
  def canvasy(self, y): return y + self.scrollY

  def create_rectangle(self, *coords, **_kw):
    _id, self._next = self._next, self._next + 1
    self.items[_id] = list(coords[0] if len(coords) == 1 else coords)
    return _id

  def coords(self, _id, *coords):
    if coords:
      self.items[_id] = list(coords[0] if len(coords) == 1 else coords)
    return list(self.items.get(_id, []))

  def delete(self, _id): self.items.pop(_id, None)

  def find(self, how, x0, y0, x1, y1):
    assert how == "overlapping"
    return tuple(i for i, (a, b, c, d) in self.items.items() if a <= x1 and c >= x0 and b <= y1 and d >= y0)

class FakeNode:
  def __init__(self, view, bbox):
    self.view = view
    self._shape = SimpleNamespace(id=view.canvas.create_rectangle(bbox))
  def selected(self, sel, _multi=False):
    (self.view.selected.add if sel else self.view.selected.discard)(self)

class FakeView:
  def __init__(self, scale:float, scrollX:float, scrollY:float):
    self._scale = scale
    self.canvas = FakeCanvas(scrollX, scrollY)
    self.selected:set = set()
    self._selectionBoxInfo = None
    self._elasticLineChoiceData = None
    self._scrolling = False
    self._dragZoom = None # (SNGView.__init__ sets it: see onButton_1(), an Option-press drag-zooms)
    self.nodes:list[FakeNode] = []
  def isEventHandled(self, _event): return False
  def removeEventHandled(self, _event): pass
  def grabTerminalNear(self, _event): return False
  def viewToWindow(self, *args): return SNGView.viewToWindow(self, *args) #type: ignore[arg-type]
  def values(self): return self.nodes

def event(x, y): return SimpleNamespace(x=x, y=y, state=0)

class Test(unittest.TestCase):

  def drag(self, view, frm, to):
    SNGView.onButton_1(view, event(*frm)) #type: ignore[arg-type]
    box = view._selectionBoxInfo[0]
    SNGView.onB1_Motion(view, event(*to)) #type: ignore[arg-type]
    return box, view.canvas.coords(box)

  def test0100boxFollowsTheMouse(self):
    for scale in (1.0, 2.0, 0.5, 1.2 ** 5):
      for scroll in ((0, 0), (300, -120)):
        with self.subTest(scale=scale, scroll=scroll):
          view = FakeView(scale, *scroll)
          _, bb = self.drag(view, (10, 20), (60, 90))
          sx, sy = scroll
          self.assertEqual(bb, [10 + sx, 20 + sy, 60 + sx, 90 + sy])

  def test0200boxBackwards(self):
    view = FakeView(2.0, 50, 50)
    _, bb = self.drag(view, (60, 90), (10, 20))
    self.assertEqual(bb, [60, 70, 110, 140])

  def test0300selectsWhatsInside(self):
    view = FakeView(2.0, 100, 100) # node bboxes are canvas coordinates (already zoomed)
    inside = FakeNode(view, [120, 130, 140, 150])
    outside = FakeNode(view, [400, 400, 420, 420])
    view.nodes = [inside, outside]
    box, _ = self.drag(view, (10, 20), (60, 90)) # canvas 110,120 .. 160,190
    SNGView.onB1_ButtonRelease(view, event(60, 90)) #type: ignore[arg-type]
    self.assertEqual(view.selected, {inside})
    self.assertNotIn(box, view.canvas.items)
    self.assertIsNone(view._selectionBoxInfo)

if __name__ == "__main__":
  unittest.main()
