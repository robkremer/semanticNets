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
*Model(url)* for a model that's in memory already (eg: opening a window on a
super-model of an open model's -- see *Application.openWindow()*), or that it
reads from its file, hands back that model as it is: its observers (its views,
and views showing its objects), prefs and replaced models aren't reset.

Created on Oct 17, 2026

@author: robkremer
'''
import unittest
import tempfile
from pathlib import Path
from sn.model.model import Model, Node
from util.observer import Observer

class Watcher(Observer):
  def update(self, subject, *topics): pass

class Test(unittest.TestCase):

  def setUp(self):
    self.folder = tempfile.TemporaryDirectory()
    self.path = str(Path(Path(self.folder.name).resolve(), "a.snm")) # (macOS: /var is /private/var)
    Model._initCache()

  def tearDown(self):
    Model._initCache()
    self.folder.cleanup()

  def test0100inMemory(self):
    m = Model(self.path)
    Node(m, [m.NODE], name="x")
    watcher = Watcher()
    m.addObserver(watcher)
    m.replacedModels["file:///old.snm"] = "file:///new.snm"
    prefs = m.prefs
    self.assertIs(Model(self.path), m)
    self.assertTrue(any(o is watcher for o, _ in m._observers))
    self.assertEqual(m.replacedModels, {"file:///old.snm": "file:///new.snm"})
    self.assertIs(m.prefs, prefs)
    self.assertTrue(m.isDirty())

  def test0200read(self):
    m = Model(self.path)
    Node(m, [m.NODE], name="x")
    m.replacedModels["file:///old.snm"] = "file:///new.snm"
    m.save()
    Model._initCache()
    m = Model(self.path)
    self.assertEqual(m.replacedModels, {"file:///old.snm": "file:///new.snm"})
    self.assertEqual(m["x"].name, "x")
    self.assertEqual(m.nextID, 258) # (x, and its isa)

  def test0300readFileByPath(self):
    from util.persistence.pRef import PRDb
    m = Model(self.path)
    Node(m, [m.NODE], name="x")
    m.save()
    self.assertIs(PRDb.readFile(self.path, mode="r"), m) # (a plain path, eg: from a file dialog, is the open model)

if __name__ == "__main__":
  unittest.main()
