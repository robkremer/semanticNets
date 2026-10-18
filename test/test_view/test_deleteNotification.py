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
from 256: a view shows its model's super-models' objects too, and hears from
them (see *SNGView._observeModel()*), so *SNGView.update()* must take away, and
later bring back, the box of the notifying model's object, not another model's
with the same id. And a notification that takes out, or puts back, many of a
view's boxes has their canvas items hidden or shown in one pass (see
*SNGView.batchedItemStates()*). Runs *update()* on a stand-in view.

Created on Oct 17, 2026

@author: robkremer
'''
import unittest
import tempfile
from pathlib import Path
from sn.model.model import Model, Node
from sn.view.graphics.sngView import SNGView
from util.observer import Observer

class FakeVObject:
  "Stands in for a *VObject*: just whether it's in the view (and whether it went, or came back, within a batch)."
  def __init__(self, modelObject):
    self.modelObject = modelObject
    self.connected = True
    self.view:FakeView|None = None
    self.batched:bool|None = None
  def _isConnected(self): return self.connected
  def _disconnect(self): self._connect(False)
  def _reconnect(self): self._connect(True)
  def _connect(self, connected:bool):
    self.connected = connected
    assert self.view is not None
    self.batched = self.view.__dict__.get("_pendingItemStates") is not None # (see SNGView.batchedItemStates())
  def isInferred(self): return False

class FakeView:
  "Stands in for an *SNGView* of *model*: what *update()* uses for \"new\" and \"del\"."
  _indexKeys = staticmethod(SNGView._indexKeys)
  update = SNGView.update
  _changesManyBoxes = SNGView._changesManyBoxes
  batchedItemStates = SNGView.batchedItemStates # (with nothing to hide or show: the stand-ins don't)
  BATCHED_UPDATE_BOXES = 3
  def __init__(self, model, vos):
    self.model = model
    self.vos = vos
    for vo in vos:
      vo.view = self
    self._db = {}
    self._deletedGraphObjectsCache = {}
  def values(self): return [vo for vo in self.vos if vo.connected]
  def _viewObjectIndex(self):
    self.__dict__.pop("_byModelObject", None) # (made afresh: the stand-ins don't keep it up to date)
    return SNGView._viewObjectIndex(self) #type: ignore[arg-type]
  def _viewObjectsForID(self, model, modelID): return SNGView._viewObjectsForID(self, model, modelID) #type: ignore[arg-type]
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
    self.view = FakeView(self.main, [self.vPerson, self.vFred])

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
    # both gone (the view hears from main's super-model too): each comes back with its own model's "new"
    self.update(self.main, ("del", (self.fred.id,)))
    self.update(self.base, ("del", (self.person.id,)))
    self.assertFalse(self.vPerson.connected or self.vFred.connected)
    self.update(self.main, ("new", (self.fred.id, self.fred)))
    self.assertTrue(self.vFred.connected)
    self.assertFalse(self.vPerson.connected)
    self.update(self.base, ("new", (self.person.id, self.person)))
    self.assertTrue(self.vPerson.connected)

  def test0400superModelsOtherNewsIgnored(self):
    # (its reasoning, and an object added to it: not shown here -- the stand-in has no _showReasoning() or _askName())
    other = Node(self.base, [self.base.NODE], name="animal")
    self.update(self.base, ("reasoned", ((), False)), ("reasoning cleared", ()), ("new", (other.id, other)))
    self.assertTrue(self.vPerson.connected and self.vFred.connected)

  def test0500superModelsDependentsAreViewsOfIt(self):
    # a view observing a model whose objects it shows isn't a view of that model (see Model.unload())
    class Watcher(Observer):
      def __init__(self, model, url): self.model, self.url = model, url
      def update(self, subject, *topics): pass
    watcher = Watcher(self.main, "file:///main.snv")
    self.main.addObserver(watcher)
    self.base.addObserver(watcher)
    self.assertIn(("view", watcher.url), self.main.dependents())
    self.assertNotIn(("view", watcher.url), self.base.dependents())

  def manyFreds(self, n:int) -> list[FakeVObject]:
    '''
    :param n:
    :type n: int
    :returns: The boxes of *n* more of main's individuals, shown in the view.
    :rtype: list[FakeVObject]
    '''
    vos = [FakeVObject(Node(self.main, [self.person], individual=True, name=f"fred{i}")) for i in range(n)]
    for vo in vos:
      vo.view = self.view
    self.view.vos += vos
    return vos

  def test0600manyBoxesInOneBatch(self):
    vos = self.manyFreds(2) + [self.vFred] # (BATCHED_UPDATE_BOXES)
    self.update(self.main, *[("del", (vo.modelObject.id,)) for vo in vos])
    self.assertEqual([(vo.connected, vo.batched) for vo in vos], [(False, True)] * 3)
    self.update(self.main, *[("new", (vo.modelObject.id, vo.modelObject)) for vo in vos])
    self.assertEqual([(vo.connected, vo.batched) for vo in vos], [(True, True)] * 3)
    self.assertTrue(self.vPerson.connected and self.vPerson.batched is None)
    self.assertNotIn("_pendingItemStates", self.view.__dict__)

  def test0700fewBoxesEachOnItsOwn(self):
    vos = self.manyFreds(1) + [self.vFred]
    self.update(self.main, *[("del", (vo.modelObject.id,)) for vo in vos])
    self.assertEqual([(vo.connected, vo.batched) for vo in vos], [(False, False)] * 2)
    self.update(self.main, *[("new", (vo.modelObject.id, vo.modelObject)) for vo in vos])
    self.assertEqual([(vo.connected, vo.batched) for vo in vos], [(True, False)] * 2)

  def test0800onlyTheViewsBoxesCount(self):
    # many "del"s, but of objects it doesn't show (a super-model's, and its own), and "new"s of ones it never showed
    vos = self.manyFreds(1) + [self.vFred]
    unshown = [Node(self.base, [self.person], individual=True, name=f"bob{i}") for i in range(5)] + \
              [Node(self.main, [self.person], individual=True, name=f"sam{i}") for i in range(5)]
    self.update(self.base, *[("del", (o.id,)) for o in unshown[:5]])
    self.update(self.main, *[("del", (o.id,)) for o in unshown[5:]] + [("del", (vo.modelObject.id,)) for vo in vos])
    self.assertEqual([(vo.connected, vo.batched) for vo in vos], [(False, False)] * 2)
    self.update(self.base, *[("new", (o.id, o)) for o in unshown[:5]])
    self.assertTrue(self.vPerson.connected and self.vPerson.batched is None)

if __name__ == "__main__":
  unittest.main()
