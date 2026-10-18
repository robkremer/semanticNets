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
A view locked so it can't change its model (*SNGView.setEditLocked()*, the
pencil in the reasoning toolbar): the part that needs no screen. Its do-list
(*ViewDoList*) refuses commands that change the model -- doing them, and
undoing or redoing them -- but not those that only change the view.

Created on Oct 16, 2026

@author: robkremer
'''
import unittest
from util.commandParser import Command, CompositeCommand
from sn.controller.modelInterface import ModelContext, ModelCommand, changesModel
from sn.view.graphics.sngView import SNGView
from sn.view.graphics.viewCommands import ViewDoList

class FakeModel:
  def __init__(self, writeLocked:bool=False):
    self.locked = writeLocked
    self.name = "m"
    self.nextID = 256 # (the next object's id: see ViewDoList.do())
  def writeLocked(self): return self.locked

class FakeWindow:
  def bell(self): pass

class FakeVar:
  def __init__(self): self.value = False
  def get(self): return self.value
  def set(self, value): self.value = value

class FakeView:
  def __init__(self, writeLocked:bool=False):
    self.model = FakeModel(writeLocked)
    self.window = FakeWindow()
    self.canvas = None
    self.localLayout = None
    self.dirty = False
  def setDirty(self, dirty:bool=True): self.dirty = dirty
  def bumpIntruders(self): return []
  def _editLockedVar(self): # (what "Edit | Lock view" shows: no Tk here)
    if not hasattr(self, "var"):
      self.var = FakeVar()
    return self.var
  isModelEditor = SNGView.isModelEditor
  lockedReason = SNGView.lockedReason
  editLocked = SNGView.editLocked
  setEditLocked = SNGView.setEditLocked

class Recorder(Command):
  def __init__(self, log:list, name:str):
    super().__init__(name)
    self.log = log
  def do(self):
    super().do()
    self.log.append("do " + self.name)
  def undo(self):
    super().undo()
    self.log.append("undo " + self.name)

class ModelRecorder(Recorder, ModelCommand):
  pass

class Test(unittest.TestCase):

  def doList(self, view, *commands) -> ViewDoList:
    "A do-list with *commands* done (the view unlocked)."
    dl = ViewDoList(view) #type: ignore[arg-type]
    for c in commands:
      c.do()
      dl.queue.append(c)
      dl.index += 1
    return dl

  def test0100whatChangesTheModel(self):
    for cls in (ModelContext._Set_attribute, ModelContext._Delete_attribute, ModelContext._New_node, ModelContext._New_relation,
                ModelContext._Remove, ModelContext._Cut, ModelContext._Paste, ModelContext._Reconnect, ModelContext._Set_kind,
                ModelContext._Mark_asserted, ModelContext._Assert_):
      self.assertTrue(issubclass(cls, ModelCommand), cls.__name__)
    log:list = []
    self.assertFalse(changesModel(Recorder(log, "move")))
    self.assertTrue(changesModel(ModelRecorder(log, "new")))
    self.assertTrue(changesModel(CompositeCommand([Recorder(log, "move"), ModelRecorder(log, "contain")])))
    self.assertFalse(changesModel(CompositeCommand([Recorder(log, "move")])))

  def test0200lockingAndUnlocking(self):
    view = FakeView()
    self.assertTrue(view.isModelEditor())
    self.assertTrue(view.setEditLocked(True))
    self.assertFalse(view.isModelEditor())
    self.assertTrue(view.dirty) # (it's saved with the view)
    self.assertTrue(view.var.get()) # ("Edit | Lock view" is checked)
    self.assertIn("pencil", view.lockedReason())
    self.assertTrue(view.setEditLocked(False))
    self.assertTrue(view.isModelEditor())

  def test0300writeLockedModel(self):
    view = FakeView(writeLocked=True)
    self.assertFalse(view.isModelEditor())
    self.assertFalse(view.editLocked())
    self.assertFalse(view.setEditLocked(False)) # (it can't be unlocked)
    self.assertTrue(view.var.get()) # ("Edit | Lock view" stays checked)
    self.assertIn("write-locked", view.lockedReason())

  def test0400lockedViewRefusesModelChanges(self):
    view = FakeView()
    log:list = []
    dl = self.doList(view)
    view.setEditLocked(True)
    with self.assertRaises(PermissionError):
      dl.do(ModelRecorder(log, "new"))
    with self.assertRaises(PermissionError):
      dl.do(CompositeCommand([Recorder(log, "move"), ModelRecorder(log, "contain")]))
    self.assertEqual(log, []) # (none of it's done)
    dl.do(Recorder(log, "move"))
    self.assertEqual(log, ["do move"])

  def test0500lockedViewRefusesUndoingModelChanges(self):
    view = FakeView()
    log:list = []
    dl = self.doList(view, ModelRecorder(log, "new"), Recorder(log, "move"))
    log.clear()
    view.setEditLocked(True)
    dl.undo() # (the move: it's only the view)
    dl.undo() # (the new object: refused)
    self.assertEqual(log, ["undo move"])
    self.assertEqual(dl.index, 0)
    view.setEditLocked(False)
    dl.undo()
    self.assertEqual(log, ["undo move", "undo new"])
    view.setEditLocked(True)
    dl.redo() # (refused)
    self.assertEqual(dl.index, -1)
    view.setEditLocked(False)
    dl.redo()
    self.assertEqual(log, ["undo move", "undo new", "do new"])

if __name__ == "__main__":
  unittest.main()
