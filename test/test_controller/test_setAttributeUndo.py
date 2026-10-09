'''
Undoing "set attribute" puts the old value back -- also for an attribute
that's inherited too (eg: "name"), whose own record setting changes in place.

Created on Oct 8, 2026

@author: robkremer
'''
import unittest
from pathlib import Path
from sn.model.model import Model, Node
from sn.controller.modelInterface import ModelContext


class Test(unittest.TestCase):

  def test0100undoRename(self):
    Path("temp_setAttributeUndo.xml").unlink(missing_ok=True)
    Model._initCache()
    m = Model("temp_setAttributeUndo.xml")
    t = Node(m, [m.NODE], name="t")
    a = Node(m, [t], individual=True, name="alpha")
    c = ModelContext(m)
    c.set_attribute(a, "name", "beta")
    self.assertEqual(a.name, "beta")
    c.undo()
    self.assertEqual(a.name, "alpha")
    c.redo()
    self.assertEqual(a.name, "beta")
    c.set_attribute(a, "colour", "red")                       # (not inherited: a new record each time)
    c.set_attribute(a, "colour", "blue")
    c.undo()
    self.assertEqual(a.get("colour", None), "red")
    Model._initCache()
    Path("temp_setAttributeUndo.xml").unlink(missing_ok=True)


if __name__ == "__main__":
  unittest.main()
