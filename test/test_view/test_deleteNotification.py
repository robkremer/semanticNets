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
A model's "del" notification (and an undo's "new") names the object by its id
in that model only (*PRDb._unregister()*), and every model numbers its objects
from 256: a view shows its model's super-models' objects too, so *SNGView.update()*
must take away, and later bring back, the box of the notifying model's object,
not another model's with the same id. Runs *update()* on a stand-in view.

Created on Oct 17, 2026

@author: robkremer
'''
import unittest
import tempfile
from pathlib import Path
from sn.model.model import Model, Node
from sn.view.graphics.sngView import SNGView

class FakeVObject:
  "Stands in for a *VObject*: just whether it's in the view."
  def __init__(self, modelObject):
    self.modelObject = modelObject
    self.connected = True
  def _isConnected(self): return self.connected
  def _disconnect(self): self.connected = False
  def _reconnect(self): self.connected = True
  def isInferred(self): return False

class FakeView:
  "Stands in for an *SNGView*: what *update()* uses for \"new\" and \"del\"."
  def __init__(self, vos):
    self.vos = vos
    self._deletedGraphObjectsCache = {}
  def values(self): return [vo for vo in self.vos if vo.connected]
  def findViewObjectForGraphObject(self, f): return SNGView.findViewObjectForGraphObject(self, f) #type: ignore[arg-type]
  def structureChanged(self): pass
  def isDirty(self): return False
  def setDirty(self, dirty=True): pass

class Test(unittest.TestCase):

  def setUp(self):
    self.folder = tempfile.TemporaryDirectory()
    folder = str(Path(self.folder.name).resolve()) # (macOS: /var is /private/var)
    Model._initCache()
    self.base = Model(str(Path(folder, "base.snm")))
    self.person = Node(self.base, [self.base.NODE], name="person")
    self.main = Model(str(Path(folder, "main.snm")))
    self.main.setSuperModels(["base.snm"])
    self.fred = Node(self.main, [self.person], individual=True, name="fred")
    self.assertEqual(self.person.id, self.fred.id) # (both #256)
    self.vPerson, self.vFred = FakeVObject(self.person), FakeVObject(self.fred) # (person's first: found first)
    self.view = FakeView([self.vPerson, self.vFred])

  def tearDown(self):
    Model._initCache()
    self.folder.cleanup()

  def update(self, model, *topics):
    SNGView.update(self.view, model, *topics) #type: ignore[arg-type]

  def test0100delTakesAwayTheNotifyingModelsObject(self):
    self.update(self.main, ("del", (self.fred.id,)))
    self.assertFalse(self.vFred.connected)
    self.assertTrue(self.vPerson.connected)

  def test0200newBringsBackTheSameBox(self):
    self.update(self.main, ("del", (self.fred.id,)))
    self.update(self.main, ("new", (self.fred.id, self.fred)))
    self.assertTrue(self.vFred.connected)
    self.assertTrue(self.vPerson.connected)

  def test0300deletedBoxesKeptByModel(self):
    # both gone (as if the view heard from both models): each comes back with its own model's "new"
    self.update(self.main, ("del", (self.fred.id,)))
    self.update(self.base, ("del", (self.person.id,)))
    self.assertFalse(self.vPerson.connected or self.vFred.connected)
    self.update(self.main, ("new", (self.fred.id, self.fred)))
    self.assertTrue(self.vFred.connected)
    self.assertFalse(self.vPerson.connected)
    self.update(self.base, ("new", (self.person.id, self.person)))
    self.assertTrue(self.vPerson.connected)

if __name__ == "__main__":
  unittest.main()
