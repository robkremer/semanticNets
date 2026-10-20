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
The layout panel (see *layoutPanel.LayoutPanel*) keeps its page scrolled where
it was when a drop-down's chosen: choosing a relation's role in a tree
layout's table remakes the table's rows, which leaves the page shorter for a
moment -- and the panel's canvas used to keep the view it moved up to then.

The panel's in a hidden window (it's never shown), so its canvas is given a
size, and what happens while its rows are remade (the page laid out shorter)
is done here.

Created on Oct 19, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import builtins
import logging
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path
import _tkinter
import tkinter as tk
from tkinter import ttk

import sn
from util import terminal
from util.utils import fixURL
from sn.model.model import Model

class Test(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
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
    from sn.view.graphics.sngView import SNGView
    from sn.view.graphics.layoutPanel import LayoutPanel
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snLayoutPanel-")
    folder = Path(self.tmp.name).resolve()
    sn.copyExamples(str(folder), ["family.snm"])
    model = Model.getDB((folder / "family.snm").as_uri())
    self.assertTrue(model.url.startswith(folder.as_uri()), model.url)
    self.view = v = SNGView(fixURL(model.url, ".snv", replaceExt=True, mode="w")[0], model=model)
    v.window.withdraw()
    v.showAllModel()
    self.top = tk.Toplevel(self.app)
    self.top.withdraw()
    self.panel = LayoutPanel(self.top, v) # (not in the view's window: see SNGView.showLayoutPanel())
    self.panel.pack(fill=tk.BOTH, expand=True)
    self.pump()

  def tearDown(self):
    v = self.view
    self.top.destroy()
    if not v._closed:
      v.detachFromModel()
      self.app.terminalRegistry.unregisterWindow(v.window)
    if v.window.winfo_exists():
      v.window.destroy()
    self.pump()
    Model._initCache()
    self.tmp.cleanup()

  def pump(self, seconds:float=0.2) -> None:
    '''
    Let the event loop run, an event at a time: Tk on macOS keeps redrawing a
    never-shown window with ttk widgets at idle (see
    *SNGView.showLayoutPanel()*), so *update()* wouldn't return.
    '''
    end = time.monotonic() + seconds
    while time.monotonic() < end:
      if not self.app.tk.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT):
        time.sleep(0.01)

  def roleBoxes(self) -> list[ttk.Combobox]:
    'The page\'s relation table\'s role drop-downs, top to bottom.'
    editor = next(iter(self.panel.form.tables.values()))
    return list(editor.boxes.values())

  def test_choosingKeepsScroll(self):
    from sn.view.graphics.layout import STATIC
    p = self.panel
    canvas = p.canvas
    # (a hidden window's canvas is 1 pixel square: as if it were shown, 300 by 200)
    with mock.patch.object(canvas, "winfo_width", return_value=300), mock.patch.object(canvas, "winfo_height", return_value=200):
      p.show(STATIC, "tree")
      self.pump()
      p._fit()
      height = p.page.winfo_reqheight()
      self.assertGreater(height, 600, "the tree layout's page should be taller than the panel")
      p._scroll("moveto", 0.5) # (the scrollbar dragged half way down)
      top = canvas.canvasy(0)
      self.assertGreater(top, 300)
      for role in (IGNORED, "parent: source"): # (each remakes the table's rows)
        box = self.roleBoxes()[-1] # (the last row's: well below where the page is shortened to)
        box.set(role)
        box.event_generate("<<ComboboxSelected>>")
        with mock.patch.object(p.page, "winfo_reqheight", return_value=300):
          p._fit() # (the page laid out while its rows are remade: see the module doc)
        self.pump()
        p._fit() # (and laid out again, as it was)
        self.assertEqual(self.roleBoxes()[-1].get(), role)
        self.assertEqual(canvas.canvasy(0), top, f'choosing "{role}" scrolled the page')
      p._scroll("scroll", -2, "units") # (scrolled up: it stays there now)
      top = canvas.canvasy(0)
      p._fit()
      self.assertEqual(canvas.canvasy(0), top)

  def test_tableAsTree(self):
    '''The relation table as a tree: supertypes with their subtypes under them,
    closed unless one has a row; a subtype "as" its supertype until it's given a
    row of its own; moved among its siblings; narrow enough for the panel.'''
    from sn.model.model import Node, Relation
    from sn.view.graphics.layoutDialog import RelationTableEditor
    from sn.view.graphics.layoutPanel import LayoutPanel
    m = Model(str(Path(self.tmp.name).resolve() / "tree.snm"))
    person = Node(m, [m.NODE], name="person")
    ancestor = Relation(m, [m.RELATION], person, person, name="has-ancestor")
    parent = Relation(m, [ancestor], person, person, name="has-parent")
    mother = Relation(m, [parent], person, person, name="has-mother")
    likes = Relation(m, [m.RELATION], person, person, name="likes")
    table = RelationTable([RelationRow("has-ancestor", SHAPES, "destination"), RelationRow(TERMINALS, PULLS)])
    e = RelationTableEditor(self.top, table, m, [mother, likes], compact=True)
    e.pack()
    self.assertEqual(e.table(), table)
    self.assertEqual(list(e.boxes), ["has-ancestor", TERMINALS, "likes"]) # (has-ancestor closed: no subtype has a row; likes: no row)
    self.assertEqual(e.boxes["has-ancestor"].get(), "parent: destination")
    self.assertEqual(e.boxes["likes"].get(), f"as no row: {PULLS}")
    self.assertFalse(any(v.startswith("as ") for v in e.boxes[TERMINALS].cget("values"))) # (it's always a row)
    def node(name):
      return next(n for r in e.roots for n in r.walk() if n.name == name)
    e._toggle(node("has-ancestor"))
    e._toggle(node("has-parent"))
    self.assertEqual(list(e.boxes), ["has-ancestor", "has-parent", "has-mother", TERMINALS, "likes"])
    self.assertEqual(e.boxes["has-mother"].get(), "as has-ancestor")
    def choose(name, choice):
      box = e.boxes[name]
      box.set(choice)
      box.event_generate("<<ComboboxSelected>>")
      self.pump(0.05)
    choose("has-parent", IGNORED)
    self.assertEqual([r.relation for r in e.table().rows], ["has-ancestor", "has-parent", TERMINALS])
    self.assertEqual(e.boxes["has-mother"].get(), "as has-parent")
    choose("has-parent", "as has-ancestor") # (no row of its own again)
    self.assertEqual(e.table(), table)
    choose("likes", PULLS)
    e._move(node("likes"), e.roots, -1)
    e._move(node("likes"), e.roots, -1)
    self.assertEqual([r.relation for r in e.table().rows], ["likes", "has-ancestor", TERMINALS])
    self.pump(0.05)
    self.assertLess(e.winfo_reqwidth(), LayoutPanel.MIN_WIDTH) # (fits the panel at its narrowest, two levels in)

from sn.view.graphics.relationTable import IGNORED, PULLS, SHAPES, TERMINALS, RelationRow, RelationTable

if __name__ == "__main__":
  unittest.main()
