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
Dragging an object (*VObject.onButton_1()* and *onB1_Motion()*) when zoomed
and scrolled: the part that needs no screen. *onB1_Motion()* runs on a
stand-in object whose stand-in canvas scrolls (canvasx() adds an offset); the
objects it moves are in view units, which the view's zoom scales onto the canvas.

Created on Oct 15, 2026

@author: robkremer
'''
import unittest
from types import SimpleNamespace
from sn.view.graphics.sngView import SNGView
from sn.view.graphics.vobjects import VObject

class FakeCanvas:
  def __init__(self, scrollX:float, scrollY:float):
    self.scrollX, self.scrollY = scrollX, scrollY
  def canvasx(self, x): return x + self.scrollX
  def canvasy(self, y): return y + self.scrollY

class FakeView:
  def __init__(self, scale:float, scrollX:float, scrollY:float):
    self._scale = scale
    self.canvas = FakeCanvas(scrollX, scrollY)
  def addEventHandled(self, _event): pass
  def freshPaint(self): pass
  def windowToView(self, *args): return SNGView.windowToView(self, *args) #type: ignore[arg-type]
  def viewToWindow(self, *args): return SNGView.viewToWindow(self, *args) #type: ignore[arg-type]

class FakeObject:
  "Stands in for a *VObject*: positions are whole view units, as *boundingBox()* keeps them."
  def __init__(self, view, bbox):
    self.view, self.canvas = view, view.canvas
    self.bb = list(bbox)
    self.resizeInfo = None
    self.dragInfo = None
  def boundingBox(self): return self.bb
  def moveTo(self, x, y, **_kw):
    w, h = self.bb[2] - self.bb[0], self.bb[3] - self.bb[1]
    self.bb = [int(x), int(y), int(x) + w, int(y) + h]

def event(x, y): return SimpleNamespace(x=x, y=y, state=0)

class Test(unittest.TestCase):

  def startDrag(self, view, grabbed, others, at):
    "What *VObject.onButton_1()* records at the press (the parts *onB1_Motion()* uses)."
    x, y = view.canvas.canvasx(at[0]), view.canvas.canvasy(at[1])
    grabbed.dragInfo = (grabbed.bb[0], grabbed.bb[1], x, y, False)
    grabbed.dragStartPositions = {n: n.boundingBox() for n in [grabbed, *others]}

  def test0100objectStaysUnderThePointer(self):
    for scale in (1.0, 2.0, 0.5, 1.25 ** 3, 0.05):
      for scroll in ((0, 0), (300, -120)):
        with self.subTest(scale=scale, scroll=scroll):
          view = FakeView(scale, *scroll)
          obj = FakeObject(view, [100, 50, 160, 80])
          other = FakeObject(view, [-40, 200, 0, 230])
          press = (40, 30)
          self.startDrag(view, obj, [other], press)
          # a pixel at a time, as a slow drag goes
          for i in range(1, 121):
            VObject.onB1_Motion(obj, event(press[0] + i, press[1] + i // 2)) #type: ignore[arg-type]
          self.assertTrue(obj.dragInfo[4])
          # the object's moved (on the screen) as far as the pointer has
          dx, dy = 120 / scale, 60 / scale
          self.assertAlmostEqual(obj.bb[0], 100 + dx, delta=0.5)
          self.assertAlmostEqual(obj.bb[1], 50 + dy, delta=0.5)
          self.assertEqual(obj.bb[2] - obj.bb[0], 60)
          # ... and so has the other selected one
          self.assertAlmostEqual(other.bb[0], -40 + dx, delta=0.5)
          self.assertAlmostEqual(other.bb[1], 200 + dy, delta=0.5)

  def test0200backToWhereItWas(self):
    view = FakeView(2.0, 50, 50)
    obj = FakeObject(view, [100, 50, 160, 80])
    self.startDrag(view, obj, [], (10, 10))
    VObject.onB1_Motion(obj, event(77, -33)) #type: ignore[arg-type]
    VObject.onB1_Motion(obj, event(10, 10)) #type: ignore[arg-type]
    self.assertEqual(obj.bb, [100, 50, 160, 80])

if __name__ == "__main__":
  unittest.main()
