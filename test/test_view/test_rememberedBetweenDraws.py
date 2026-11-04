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
What a view remembers between draws (labels, which shape options an object has,
what the context windows contain: see *SNGView.structureChanged()*) is
forgotten when the model changes in ways its notifications don't reach the
view in time for, or at all:

- a type renamed while the view shows only its instances (their "$type"
  labels), in a real view, in a hidden window;
- a variable dragged out of its rule window: the containment is gone from the
  model before the drop's bump-out-of-windows pass reads it, though the
  model's notification of that comes later;
- a super-model replaced by another (see *SNGView.modelObjectsReplaced()*).

Created on Nov 4, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import builtins
import logging
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
import tkinter as tk

import sn
from util import terminal
from util.utils import fixURL
from util.commandParser import CompositeCommandMgr
from sn.model.model import Model, Node, Relation

class Test(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    # (the application routes stdout, stderr, input(), logging and excepthook
    # to its windows' terminals: put them all back afterwards)
    cls.saved = (sys.stdout, sys.stderr, builtins.input, sys.excepthook,
                 list(logging.getLogger().handlers), terminal._installedIORoutingRegistry,
                 Application.current, progress.listener)
    cls.prefsWereDirty = sn.snPrefs.isDirty()
    from sn.view.graphics import decorators
    decorators._fonts.clear() # (made for an application an earlier test made, and destroyed)
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
    decorators._fonts.clear() # (this application's: see setUpClass())
    cls.restore()
    Model._initCache()
    if not cls.prefsWereDirty:
      sn.snPrefs.setDirty(False)

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snRemembered-")
    self.folder = Path(self.tmp.name).resolve()
    self.views = []

  def tearDown(self):
    for v in self.views:
      if not v._closed:
        v.detachFromModel()
        self.app.terminalRegistry.unregisterWindow(v.window)
      if v.window.winfo_exists():
        v.window.destroy()
    self.pump()
    Model._initCache()
    self.tmp.cleanup()

  def pump(self, seconds:float=0.3) -> None:
    'Let the event loop run: the model\'s notifications, and what the view puts off till idle.'
    end = time.monotonic() + seconds
    while True:
      self.app.update()
      if time.monotonic() >= end:
        break
      time.sleep(0.01)

  def view(self, m:Model, name:str="v.snv"):
    'A view of *m*, in a hidden window, showing all of it.'
    from sn.view.graphics.sngView import SNGView
    v = SNGView((self.folder / name).as_uri(), model=m)
    v.window.withdraw()
    v._askName = lambda mo: None
    v.showAllModel()
    self.views.append(v)
    self.pump()
    return v

  @staticmethod
  def shown(vo) -> str:
    'The text of *vo*\'s label, as drawn.'
    return vo.canvas.itemcget(vo.decorators["text"].id, "text").replace("\n", "")

  # ---- the tests -------------------------------------------------------------

  def test0100typeRenamedWhileNotShown(self):
    'A "$type" label follows its type\'s rename though the type isn\'t in the view (erased): at the next repaint.'
    m = Model((self.folder / "m.snm").as_uri())
    T = Node(m, [m.NODE], individual=False, name="T")
    fred = Node(m, [T], individual=True, name="fred")
    fred["vis/label"] = "$type: $name"
    v = self.view(m)
    vT, vf = (v.findViewObjectForGraphObject(o) for o in (T, fred))
    self.assertEqual(self.shown(vf), "T: fred")
    v.context.erase(vT)                                                  # (the type is no longer in the view)
    self.pump()
    self.assertIsNone(v.findViewObjectForGraphObject(T))
    v.context.set_attribute(T, "name", "T2")
    self.pump()
    v.repaint()
    self.pump()
    self.assertEqual(self.shown(vf), "T2: fred")
    self.assertEqual(vf.labelText(), "T2: fred")

  def test0200variableDraggedOutOfItsWindowStaysOut(self):
    'A variable dragged out of its rule window (as the drop does it) stays where it was dropped, and the model no longer contains it.'
    m = Model((self.folder / "m.snm").as_uri())
    person = Node(m, [m.NODE], name="person")
    R = Node(m, [m.RULE], individual=True, name="R")
    x = Node(m, [person], individual=True, name="?x")
    Relation(m, [m.ANTECEDENT], R, x, individual=True)
    v = self.view(m)
    V = v.findViewObjectForGraphObject
    for i, t in enumerate((person, m.NODE, m.RULE, m.ANTECEDENT, m.CONTEXT, m.CONTAINS, m.CONSEQUENT)): # (out of the way)
      if V(t) is not None:
        V(t).moveTo(1000 + 80 * i, 800, adjustPos=False)
    vR, vx = V(R), V(x)
    vR.reshape([0, 0, 400, 300])
    vx.moveTo(40, 80, adjustPos=False)
    self.pump()
    self.assertTrue(vR.containmentOf(x))
    # the drop, as VObject.onB1_ButtonRelease() does it: the move command, then the containment brought into line
    old = {vx: vx.centerPt()}
    start = vx.boundingBox()
    vx.moveTo(40, 400, adjustPos=False)
    with CompositeCommandMgr(v.context):
      v.context.move(vx, 40, 400, _oldPos=start, _drag=True)
      v._updateContainment(old)
    self.pump()
    self.assertGreater(vx.centerPt()[1], 300, "put back in its window")
    self.assertFalse(vR.containmentOf(x))
    v.context.undo()                                                     # (and back in, with its containment)
    self.pump()
    self.assertLess(vx.centerPt()[1], 300)
    self.assertTrue(vR.containmentOf(x))

  def test0300replacedSuperModelLabels(self):
    'After a super-model is replaced by a copy, labels show the copy\'s attributes at once.'
    base = Model((self.folder / "base.snm").as_uri())
    person = Node(base, [base.NODE], name="person")
    person["note"] = "old"
    person["vis/label"] = "$name/$note"
    base.save()
    shutil.copy(self.folder / "base.snm", self.folder / "copy.snm")
    copy = Model.getDB((self.folder / "copy.snm").as_uri())
    copy["person"]["note"] = "new"
    m = Model((self.folder / "main.snm").as_uri())
    m.setSuperModels(["base.snm"])
    fred = Node(m, [person], individual=True, name="fred")
    v = self.view(m)
    vp = v.findViewObjectForGraphObject(person)
    self.assertEqual(self.shown(vp), "person/old")
    m.replaceSuperModel(base, copy)
    v.modelObjectsReplaced(base, copy)
    self.assertEqual(self.shown(vp), "person/new")                       # (its own repaint shows it: no event loop needed)
    self.assertEqual(vp.labelText(), "person/new")

if __name__ == "__main__":
  unittest.main()
