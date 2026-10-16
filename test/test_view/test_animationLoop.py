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
The animation layout's run (see *sn.view.graphics.animatedLayouts.FieldsLayout*):
starting, stepping, stopping -- the part that needs no screen. The steps run on
a stand-in view whose after() just queues them, so a test runs them one by one.

A run used to hang for good -- "running", T not falling, the button stuck on
"stop", and nothing moving whatever was pressed: a click on an object left the
view's local layout suppressed (as during a drag), and the layout stood still,
waiting for the drag to end; and a step that failed left the run "running"
with no next step queued.

Created on Oct 15, 2026

@author: robkremer
'''
import logging
import threading
import unittest
from types import SimpleNamespace
from sn.view.graphics.animatedLayouts import FieldsLayout, FieldsLayout_threaded
from sn.view.graphics.vobjects import VObject

class FakeTop:
  def __init__(self):
    self.queue:list = []
  def after(self, _ms, fn):
    self.queue.append(fn)

class FakeView:
  def __init__(self):
    self.top = FakeTop()
    self.canvas = SimpleNamespace(winfo_toplevel=lambda: self.top)
    self.suppressed = False
  def suppressLocalLayout(self, suppress=None):
    if suppress is not None:
      self.suppressed = suppress
    return self.suppressed
  def values(self): return []

class FakeObject:
  "Something the layout moves."
  def __init__(self):
    self.bb = [0, 0, 10, 10]
    self.fail = False
  def _isConnected(self): return True
  def boundingBox(self): return list(self.bb)
  def moveBy(self, dx, dy, **_kw):
    if self.fail:
      raise RuntimeError("a move that fails")
    self.bb = [self.bb[0] + dx, self.bb[1] + dy, self.bb[2] + dx, self.bb[3] + dy]

class Layout(FieldsLayout):
  "Moves its one object a little every step, for ever (at step *failAt*, its move fails; at *snapAt*, its snapshot)."
  def __init__(self, view):
    super().__init__(view)
    self.obj = FakeObject()
    self.steps = 0
    self.failAt:int|None = None
    self.snapAt:int|None = None
  def _snapshot(self):
    self.steps += 1
    self.obj.fail = self.steps == self.failAt
    if self.steps == self.snapAt:
      raise RuntimeError("a snapshot that fails")
    return None
  def _work(self, snap):
    return [(self.obj, (5.0, 0.0))], None, set(), set()
  def _finish(self):
    self.active = False # (no undo: the stand-in view has no context)

class ThreadedLayout(Layout, FieldsLayout_threaded):
  "The same, with each step's forces worked out in a thread -- which waits for *go*."
  def __init__(self, view):
    super().__init__(view)
    self.go = threading.Event()
  def _work(self, snap):
    self.go.wait(5)
    return super()._work(snap)

def run(view, steps):
  "Run the queued steps (and the steps they queue), up to *steps* of them."
  for _ in range(steps):
    if not view.top.queue:
      return
    view.top.queue.pop(0)()

class Test(unittest.TestCase):

  def setUp(self):
    logging.disable(logging.CRITICAL) # (a failing step is logged: expected here)
    self.addCleanup(logging.disable, logging.NOTSET)
    self.view = FakeView()

  def test0100runsUntilStopped(self):
    layout = Layout(self.view)
    layout(autoOff=True)
    run(self.view, 10)
    self.assertTrue(layout.active)
    self.assertEqual(layout.obj.bb[0], 55)                     # each step moved it
    layout.kill()
    self.assertFalse(layout.active)                            # stopped at once
    run(self.view, 10)
    self.assertEqual(layout.obj.bb[0], 55)                     # the step still queued did nothing
    self.assertEqual(self.view.top.queue, [])

  def test0200aFailingStepStops(self):
    layout = Layout(self.view)
    layout.failAt = 4
    layout(autoOff=True)
    run(self.view, 10)
    self.assertFalse(layout.active)                            # stopped (not "running", with nothing queued)
    self.assertEqual(self.view.top.queue, [])
    self.assertEqual(layout.obj.bb[0], 15)                     # three steps, then the fourth's move failed
    layout.failAt = None
    layout(autoOff=True)                                       # ... and it starts again
    run(self.view, 3)
    self.assertTrue(layout.active)
    self.assertEqual(layout.obj.bb[0], 15 + 4 * 5)             # (the first step at once, then three queued)

  def test0300theFirstStepFailing(self):
    for cls in (Layout, ThreadedLayout):
      with self.subTest(cls=cls.__name__):
        layout = cls(self.view)
        if cls is ThreadedLayout:
          layout.go.set()
        layout.snapAt = 1
        layout(autoOff=True)                                   # (raises nothing: it's the button's command)
        run(self.view, 50)
        self.assertFalse(layout.active)
        layout(autoOff=True)
        run(self.view, 50)
        self.assertTrue(layout.active)
        layout.kill()

  def test0350aThreadedStepFailing(self):
    layout = ThreadedLayout(self.view)
    layout.go.set()
    layout.failAt = 3
    layout(autoOff=True)
    for _ in range(200):
      run(self.view, 1)
      if not layout.active:
        break
      threading.Event().wait(0.002) # (the thread)
    self.assertFalse(layout.active)
    self.assertEqual(layout.obj.bb[0], 10)                     # two steps, then the third's move failed

  def test0400startingClearsAStaleDrag(self):
    layout = Layout(self.view)
    self.view.suppressed = True # (a press never put back)
    layout(autoOff=True)
    run(self.view, 3)
    self.assertFalse(self.view.suppressed)
    self.assertGreater(layout.obj.bb[0], 0)                    # it moves

  def test0500standsStillWhileDragging(self):
    layout = Layout(self.view)
    layout(autoOff=True)
    run(self.view, 2)
    x = layout.obj.bb[0]
    self.view.suppressed = True # (the user's dragging something)
    run(self.view, 5)
    self.assertEqual(layout.obj.bb[0], x)
    self.assertTrue(layout.active)                             # waiting, not ended
    self.view.suppressed = False
    run(self.view, 2)
    self.assertGreater(layout.obj.bb[0], x)

  def test0600stopWhileAThreadWorks(self):
    layout = ThreadedLayout(self.view)
    layout(autoOff=True)                                       # a thread's working out the first step
    run(self.view, 3)                                          # (polling: not done)
    self.assertTrue(layout.active)
    layout.kill()
    self.assertFalse(layout.active)                            # stopped at once, not when the thread's done
    layout.go.set()
    layout.go = threading.Event() # (the next run's thread waits again)
    layout(autoOff=True)                                       # a new run, while the old thread finishes
    for t in [t for t in threading.enumerate() if t is not threading.current_thread() and t.daemon]:
      t.join(0.5)
    run(self.view, 20)
    self.assertEqual(layout.obj.bb[0], 0)                      # the old thread's step was dropped
    self.assertTrue(layout.active)
    layout.go.set()
    for t in [t for t in threading.enumerate() if t is not threading.current_thread() and t.daemon]:
      t.join(0.5)
    run(self.view, 2)
    self.assertEqual(layout.obj.bb[0], 5)                      # the new run's step
    layout.kill()

  def test0700slowCooling(self):
    from math import log10
    from sn.view.graphics.animationToolbar import SCALED, SLIDERS, DEFAULTS, coolingLoss
    toPos, fromPos = SCALED["cooling"]
    lo, hi = next((lo, hi) for _, attr, lo, hi, _, _ in SLIDERS if attr == "cooling")
    self.assertEqual(fromPos(lo), 0.999)                       # the slowest: 0.1% lost at each cool-down
    self.assertEqual(fromPos(hi), 0.5)                         # the fastest: half
    self.assertTrue(lo < toPos(DEFAULTS["cooling"]) < hi)
    self.assertEqual(fromPos(toPos(0.7)), 0.7)                 # (no 0.7000000000000001 saved with the view)
    self.assertEqual([coolingLoss(c) for c in (0.7, 0.999, 0.975)], ["30%", "0.1%", "2.5%"])
    self.assertAlmostEqual(fromPos(log10(0.02)), 0.98)
    layout = Layout(self.view)
    layout.cooling = 1.5 # (eg: a hand-edited view file: it'd never cool)
    layout.temperature, layout._best, layout._stalled = 1.0, 0.0, layout.patience
    layout._cool(1.0)
    self.assertLess(layout.temperature, 1.0)

  def test0800leaps(self):
    from sn.view.graphics.animatedLayouts import Snapshot, leap, forces, LEAP_MIN, LEAP_REACH, PANE_MARGIN
    # a (with its leaf l) stuck behind a wall (b, c, d) from its friend f; the wall's own links are slack
    snap = Snapshot.__new__(Snapshot)
    snap.positions = [(100.0, 100.0), (200.0, 80.0), (200.0, 100.0), (200.0, 120.0), (700.0, 100.0), (80.0, 100.0)]
    n = len(snap.positions)
    snap.objects = [FakeObject() for _ in range(n)]
    snap.halfSizes = [(10.0, 10.0)] * n
    snap.owners, snap.regions, snap.pinned = [None] * n, [None] * n, set()
    snap.chains, snap.passengers = [[i] for i in range(n)], {}
    snap.links = [(0, 4, 1.0), (1, 2, 1.0), (2, 3, 1.0), (0, 5, 1.0)]
    snap.directed, snap.ranks = [], {}
    w, h = 710.0 - 70.0, 130.0 - 70.0 # (the graph's extent)
    for _ in range(50):
      jumpers, dx, dy = leap(snap, 0.0)
      i = jumpers[0]
      self.assertIn(i, (0, 4, 5))                               # only what's stretched leaps
      if i == 0:
        self.assertEqual(jumpers, [0, 5])                       # with its leaf
      self.assertGreaterEqual((dx * dx + dy * dy) ** 0.5, LEAP_MIN * (w * w + h * h) ** 0.5) # a big change
      x, y = snap.positions[i][0] + dx, snap.positions[i][1] + dy
      self.assertTrue(70.0 - LEAP_REACH * w <= x <= 710.0 + LEAP_REACH * w)  # in or around the graph
      self.assertTrue(10.0 + PANE_MARGIN <= x and 10.0 + PANE_MARGIN <= y <= 130.0 + LEAP_REACH * h) # (not off the top or left)
    self.assertEqual(snap.positions[0], (100.0, 100.0))         # (it's only worked out)
    moves = forces(snap, 1000.0, 200.0, 0.005, 0.0, 10.0, leaps={0: (500.0, 30.0)})
    self.assertEqual(moves[0], (500.0, 30.0))                   # uncapped
    snap.positions[4], snap.positions[5] = (120.0, 100.0), (100.0, 120.0)
    snap.links = [(1, 2, 1.0), (2, 3, 1.0), (0, 4, 1.0), (0, 5, 1.0)]
    self.assertIsNone(leap(snap, 30.0))                         # nothing stretched: no leap

  def test0900aLeapIsntCountedAsMovement(self):
    layout = Layout(self.view)
    jumper = FakeObject()
    layout._work = lambda snap: ([(layout.obj, (5.0, 0.0)), (jumper, (400.0, 0.0))], None, set(), {id(jumper)})
    energies = []
    layout._cool = energies.append
    layout() # (its first step)
    self.assertEqual(energies, [5.0])
    self.assertEqual(layout.leapCount, 1)
    self.assertEqual(jumper.bb[0], 400)
    layout.kill()


class FakeDragView:
  def __init__(self):
    self.suppressed = False
  def suppressLocalLayout(self, suppress=None):
    if suppress is not None:
      self.suppressed = suppress
    return self.suppressed
  def addEventHandled(self, _event): pass

class FakeVObject:
  "Stands in for a *VObject*, after *onButton_1()*: the parts *onB1_ButtonRelease()* uses for a click."
  def __init__(self, view):
    self.view = view
    self.resizeInfo = None
    self.dragInfo = (0, 0, 5, 5, False)
    self._selected = False
  def selected(self, value=None, _multi=False):
    if value is not None:
      self._selected = value
    return self._selected

class TestRelease(unittest.TestCase):

  def press(self, obj):
    "What *VObject.onButton_1()* does to the view's local layout."
    obj.old_suppressLocalLayout = obj.view.suppressLocalLayout()
    obj.view.suppressLocalLayout(True)

  def test0100aClickPutsItBack(self):
    view = FakeDragView()
    obj = FakeVObject(view)
    self.press(obj)
    VObject.onB1_ButtonRelease(obj, SimpleNamespace(x=5, y=5, state=0)) #type: ignore[arg-type]
    self.assertTrue(obj.selected())                            # a click: selected
    self.assertFalse(view.suppressed)                          # ... and not left suppressed

  def test0200aDoubleClickPutsItBack(self):
    view = FakeDragView()
    obj = FakeVObject(view)
    self.press(obj)
    obj.dragInfo = None # (what onDouble_1() does)
    VObject.onB1_ButtonRelease(obj, SimpleNamespace(x=5, y=5, state=0)) #type: ignore[arg-type]
    self.assertFalse(view.suppressed)

if __name__ == "__main__":
  unittest.main()
