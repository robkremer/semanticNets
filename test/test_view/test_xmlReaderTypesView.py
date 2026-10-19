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
The XMLreader plugin's view of a model too big to show all at once
(*view.showTypes()*): just the types -- the ontology's, and the model's own --
with the isa links between them, arranged as a tree, none on another; each
can be expanded to bring in its elements.

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
import tkinter as tk
import sn
from util import terminal
from util.utils import fixURL
from sn.model.model import Model, Node
from sn.plugins import importBundled

XML = '''<library id="lib">
  <book id="b1" kind="novel"><title>Dune</title><author name="Herbert"/></book>
  <book id="b2" kind="poetry"><title>Odes</title><author name="Keats"/></book>
  <magazine id="byte" issue="5"/>
</library>'''

class TestTypesView(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    cls.reader = importBundled("XMLreader", "reader")
    cls.xmlView = importBundled("XMLreader", "view")
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
    cls.app.destroy()
    cls.restore()
    Model._initCache()
    if not cls.prefsWereDirty:
      sn.snPrefs.setDirty(False)

  def setUp(self):
    from sn.view.graphics.sngView import SNGView
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snXMLTypes-")
    folder = Path(self.tmp.name).resolve()
    xml = folder / "lib.xml"
    xml.write_text(XML)
    modelPath = self.reader.outputPaths(str(xml))[0]
    self.model, self.ontology = self.reader.buildModel(str(xml), modelPath)
    self.view = v = SNGView(fixURL(self.model.url, ".snv", replaceExt=True, mode="w")[0], model=self.model)
    self.assertTrue(v.url.startswith(folder.as_uri()), v.url)
    v.window.withdraw()
    v.context.visibility("system objects", "hide")

  def tearDown(self):
    v = self.view
    if not v._closed:
      v.detachFromModel()
      self.app.terminalRegistry.unregisterWindow(v.window)
      v.window.destroy()
    Model._initCache()
    self.tmp.cleanup()

  def shown(self) -> dict[str, object]:
    from sn.view.graphics.vnodes import VNode
    return {str(vo.modelObject.name): vo for vo in self.view.values()
            if isinstance(vo, VNode) and vo._isConnected() and not vo.isHidden()}

  def test_types(self):
    'Just the types, with their isa links, none on another.'
    from sn.view.graphics.vrelations import VRelation
    self.assertEqual(self.xmlView.elementCount(self.model), 4) # (title and author: properties of the books)
    self.xmlView.showTypes(self.view, self.model)
    shown = self.shown()
    self.assertEqual(set(shown), {"library", "book", "novel", "poetry", "magazine"})
    self.assertTrue(all(vo.modelObject.model is self.ontology for vo in shown.values()))
    isa = [vo for vo in self.view.values() if isinstance(vo, VRelation) and vo._isConnected()]
    self.assertEqual(sorted((str(r.src.modelObject.name), str(r.dst.modelObject.name)) for r in isa),
                     [("novel", "book"), ("poetry", "book")])
    boxes = [vo.boundingBox() for vo in shown.values()]
    for i, a in enumerate(boxes):
      for b in boxes[i + 1:]:
        self.assertFalse(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3], (a, b))
    self.assertGreater(shown["novel"].boundingBox()[1], shown["book"].boundingBox()[3]) # (subtypes below)

  def test_expand(self):
    'Expanding a type brings in its elements.'
    self.xmlView.showTypes(self.view, self.model)
    self.shown()["novel"].expand()
    self.assertIn("Dune", self.shown())
    self.assertNotIn("Odes", self.shown()) # (poetry)
    self.assertNotIn("b1", self.shown())

if __name__ == "__main__":
  unittest.main()
