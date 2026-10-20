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
Expanding something that brings in many objects (see *VObject.expand()*):
more than *VObject.BATCH_PLACED* new nodes are placed all at once -- in rows
below what's expanded, none on another nor on what was there (see
*layout.LayoutHeuristic.placeBatch()*) -- and their relations' labels after
them (see *layout.FindFree.placeLabels()*), not one by one; fewer are placed
one by one, as before. Either way it's one undo. And *clearBelow()*, which
finds where the rows go.

The view's window is never shown, and nothing is saved outside a temporary
folder (as in test_viewSmoke).

Created on Oct 19, 2026

@author: robkremer
'''
import builtins
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import tkinter as tk
import sn
from util import terminal
from util.utils import fixURL
from sn.model.model import Model, Node
from sn.view.graphics import layout
from sn.view.graphics.layout import clearBelow

def overlap(a, b) -> bool:
  return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

class TestClearBelow(unittest.TestCase):

  def test_clearBelow(self):
    'The highest band from y down that clears every box (by the gap) across its width.'
    self.assertEqual(clearBelow([], 0, 100, 50, 30, 10), 50)
    self.assertEqual(clearBelow([[200, 0, 300, 500]], 0, 100, 50, 30, 10), 50)          # (beside it: not in the way)
    self.assertEqual(clearBelow([[50, 60, 80, 90]], 0, 100, 50, 30, 10), 100)           # (in the way: below it)
    self.assertEqual(clearBelow([[50, 200, 80, 220]], 0, 100, 50, 30, 10), 50)          # (far enough below)
    self.assertEqual(clearBelow([[50, 60, 80, 90], [0, 105, 10, 140]], 0, 100, 50, 30, 10), 150) # (the next one's in the way then)
    self.assertEqual(clearBelow([[0, 60, 10, 200], [50, 100, 60, 110]], 0, 100, 50, 30, 10), 210) # (a tall one's bottom, not the last's)

class TestExpandBatch(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    cls.saved = (sys.stdout, sys.stderr, builtins.input, sys.excepthook,
                 list(logging.getLogger().handlers), terminal._installedIORoutingRegistry,
                 Application.current, progress.listener)
    cls.prefsWereDirty = sn.snPrefs.isDirty()
    from sn.view.graphics import decorators
    decorators._fonts.clear() # (made for an application an earlier test made, and destroyed: eg: test_viewSmoke's)
    try:
      cls.app = Application()
    except tk.TclError as ex:
      cls.restore()
      raise unittest.SkipTest(f"no display: {ex}")

  @classmethod
  def restore(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    (sys.stdout, sys.stderr, builtins.input, sys.excepthook, handlers, terminal._installedIORoutingRegistry,
     Application.current, progress.listener) = cls.saved
    logging.getLogger().handlers[:] = handlers

  @classmethod
  def tearDownClass(cls):
    from sn.view.graphics import decorators
    cls.app.destroy()
    decorators._fonts.clear() # (made for this application: no good to a later test's -- eg: test_viewSmoke's)
    cls.restore()
    Model._initCache()
    if not cls.prefsWereDirty:
      sn.snPrefs.setDirty(False)

  def setUp(self):
    from sn.view.graphics.sngView import SNGView
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snExpandBatch-")
    folder = Path(self.tmp.name).resolve()
    self.model = m = Model(str(folder / "batch.snm"))
    self.many = Node(m, [m.NODE], name="many")
    self.few = Node(m, [m.NODE], name="few")
    for i in range(60):
      Node(m, [self.many], individual=True, name=f"m{i}")
    for i in range(5):
      Node(m, [self.few], individual=True, name=f"f{i}")
    self.view = v = SNGView(fixURL(str(folder / "batch.snv"), ".snv", replaceExt=True, mode="w")[0], model=m)
    self.assertTrue(v.url.startswith(folder.as_uri()), v.url)
    v.window.withdraw()
    v.context.visibility("system objects", "hide")
    self.assertIsInstance(v.localLayout, layout.FindFree)
    v._askName = lambda mo: None
    self.manyVO = v.makeViewObjectForGraphObject(self.many, atPoint=(400, 50))
    self.fewVO = v.makeViewObjectForGraphObject(self.few, atPoint=(50, 50))
    v.canvas.update()

  def tearDown(self):
    v = self.view
    if not v._closed:
      v.detachFromModel()
      self.app.terminalRegistry.unregisterWindow(v.window)
      v.window.destroy()
    Model._initCache()
    self.tmp.cleanup()

  def shown(self, prefix:str) -> list:
    ':returns: The individuals shown whose names start with *prefix*.'
    from sn.view.graphics.vnodes import VNode
    return [vo for vo in self.view.values() if isinstance(vo, VNode) and vo._isConnected() and not vo.isHidden()
            and vo.modelObject.isIndividual() and str(vo.modelObject.name).startswith(prefix)]

  def labels(self) -> list:
    from sn.view.graphics.vrelations import VRelation
    return [vo for vo in self.view.values() if isinstance(vo, VRelation) and vo._isConnected()]

  def expand(self, vo) -> tuple[int, int]:
    ':returns: How many times the dynamic layout placed a batch, and placed something one by one.'
    v = self.view
    calls = {"batch": 0, "one": 0}
    FindFree = layout.FindFree
    placeBatch, placeNode = FindFree.placeBatch, FindFree.placeNode
    def batch(slf, *a, **k):
      calls["batch"] += 1
      return placeBatch(slf, *a, **k)
    def one(slf, node, *a, **k):
      calls["one"] += 1
      return placeNode(slf, node, *a, **k)
    with mock.patch.object(FindFree, "placeBatch", batch), mock.patch.object(FindFree, "placeNode", one):
      v.context.expand(vo)
      v.canvas.update()
    return calls["batch"], calls["one"]

  def test_batch(self):
    'Many: placed at once, in rows below what was expanded, none on another, nor on what was there; one undo.'
    v = self.view
    batches, ones = self.expand(self.manyVO)
    self.assertEqual(batches, 1)
    self.assertEqual(ones, 0) # (not one by one: neither the nodes nor their labels -- see FindFree.placeLabels())
    new = self.shown("m")
    self.assertEqual(len(new), 60)
    self.assertEqual(len(self.labels()), 60) # (an isa link each)
    below = self.manyVO.boundingBox()[3]
    boxes = [vo.boundingBox() for vo in new]
    self.assertTrue(all(b[1] > below for b in boxes))
    self.assertGreater(len({b[1] for b in boxes}), 1) # (rows: not all in one)
    others = [self.manyVO.boundingBox(), self.fewVO.boundingBox()]
    for i, a in enumerate(boxes):
      self.assertFalse(any(overlap(a, o) for o in others), a)
      for b in boxes[i + 1:]:
        self.assertFalse(overlap(a, b), (a, b))
    self.assertFalse(any(r.__dict__.get("_placedLater") for r in self.labels())) # (placed: they follow their ends again)
    v.context.undo()
    v.canvas.update()
    self.assertEqual(self.shown("m"), [])
    self.assertEqual(self.labels(), [])
    v.context.redo()
    v.canvas.update()
    self.assertEqual(len(self.shown("m")), 60)
    self.assertEqual([vo.boundingBox() for vo in self.shown("m")], boxes) # (back where they were)

  def test_few(self):
    'Few: placed one by one, as anything new is, none on another.'
    batches, ones = self.expand(self.fewVO)
    self.assertEqual(batches, 0)
    self.assertGreaterEqual(ones, 5)
    new = self.shown("f")
    self.assertEqual(len(new), 5)
    boxes = [vo.boundingBox() for vo in new] + [self.fewVO.boundingBox(), self.manyVO.boundingBox()]
    for i, a in enumerate(boxes):
      for b in boxes[i + 1:]:
        self.assertFalse(overlap(a, b), (a, b))

  def test_noLayout(self):
    'With no dynamic layout, nothing is placed: they stay where they were made.'
    v = self.view
    v.localLayout = None
    batches, ones = self.expand(self.manyVO)
    self.assertEqual((batches, ones), (0, 0))
    self.assertEqual(len(self.shown("m")), 60)

if __name__ == "__main__":
  unittest.main()
