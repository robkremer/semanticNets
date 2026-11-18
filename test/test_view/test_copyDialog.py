'''
The model directory's Copy To... and Move To... (several rows selected), their
dialog (sn.view.graphics.copyDialog.CopyDialog), and File | Copy model and
views to... (Application.copyModelFiles()).

Created on Nov 18, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import builtins
import logging
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path
import tkinter as tk

import sn
from util import terminal
from sn.model.model import Model, Node

VIEW = '''<?xml version='1.0' encoding='utf-8'?>
<document>
  <head>
    <property key="format" value="XML3" />
    <property key="type" value="sn.view.graphics.sngView.SNGView" />
    <property key="url" value="{url}" />
    <property key="model" value="family.snm" />
  </head>
  <object type="sn.view.graphics.sngView.SNGView" id="1">
    <property key="nextID" type="int" value="2" />
    <property key="_db">
      <object type="util.persistence.serialize.strdict">
        <property key="1"><object type="sn.view.graphics.vnodes.VNode"><property key="modelObject" type="str" value="{person}" /></object></property>
      </object>
    </property>
  </object>
</document>
'''

PREFS = ("gui/directoryPath", ".copyFolder", ".servedFolders", "model/urlAliases")

class TestCopyDialog(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    from sn.view.graphics.sngView import SNGView
    cls.saved = (sys.stdout, sys.stderr, builtins.input, sys.excepthook,
                 list(logging.getLogger().handlers), terminal._installedIORoutingRegistry,
                 Application.current, progress.listener, SNGView.askForMissingModel)
    cls.prefsWereDirty = sn.snPrefs.isDirty()
    cls.savedPrefs = {k: sn.snPrefs.getAttr(k) for k in PREFS}
    from sn.view.graphics import decorators
    decorators._fonts.clear() # (made for an application an earlier test made, and destroyed)
    try:
      cls.app = Application()
    except tk.TclError as ex:
      cls.restore()
      raise unittest.SkipTest(f"no display: {ex}")
    cls.app.noteRecent = lambda *a: None # (not in the preferences' recent files)

  @classmethod
  def restore(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    from sn.view.graphics.sngView import SNGView
    (sys.stdout, sys.stderr, builtins.input, sys.excepthook, handlers, terminal._installedIORoutingRegistry,
     Application.current, progress.listener, SNGView.askForMissingModel) = cls.saved
    logging.getLogger().handlers[:] = handlers
    for k, attr in cls.savedPrefs.items():
      if attr is None:
        sn.snPrefs.pop(k, None)
      else:
        sn.snPrefs.setAttr(k, attr)
    sn.applyURLAliases(sn.snPrefs.get("model/urlAliases", []))

  @classmethod
  def tearDownClass(cls):
    from sn.view.graphics import decorators
    cls.app.destroy()
    decorators._fonts.clear()
    cls.restore()
    Model._initCache()
    if not cls.prefsWereDirty:
      sn.snPrefs.setDirty(False)

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snCopy-")
    self.root = root = Path(self.tmp.name).resolve()
    (root / "far/away/lib").mkdir(parents=True)
    (root / "a/b/models").mkdir(parents=True)
    onto = Model(str(root / "far/away/lib/onto.snm"))
    person = Node(onto, [onto.NODE], name="person")
    onto.save()
    m = Model(str(root / "a/b/models/family.snm"))
    m.setSuperModels([onto.url])
    Node(m, [person], individual=True, name="fred")
    m.save()
    (root / "a/b/models/family.snv").write_text(VIEW.format(url=(root / "a/b/models/family.snv").as_uri(),
                                                            person=f"{onto.url}#{person._id}"))
    Model._initCache()
    sn.snPrefs["gui/directoryPath"] = str(root) + "/**"
    self.app.showDirectory()
    self.pane = self.app.directoryPane
    self.pane.rescan()
    self.scanned()

  def tearDown(self):
    self.app.windows.clear()
    self.app.showDirectory(False)
    self.pump()
    Model._initCache()
    self.tmp.cleanup()

  def pump(self, seconds:float=0.1) -> None:
    end = time.monotonic() + seconds
    while True:
      self.app.update()
      if time.monotonic() >= end:
        break
      time.sleep(0.01)

  def scanned(self) -> None:
    end = time.monotonic() + 10
    while self.pane._scanning is not None and time.monotonic() < end:
      self.pump(0.05)

  def row(self, rel:str) -> str:
    kind = "model" if rel.endswith(".snm") else "view"
    return f"{kind}:{(self.root / rel).as_uri()}"

  def test0100multipleSelected(self):
    pane = self.pane
    pane.tree.selection_set([self.row("a/b/models/family.snm")])
    self.pump()
    self.assertNotIn("disabled", pane.copyButton.state())
    self.assertNotIn("disabled", pane.moveButton.state())
    pane.tree.selection_set([self.row("a/b/models/family.snm"), self.row("a/b/models/family.snv")])
    self.pump()
    self.assertEqual(len(pane.selectedEntries()), 2)
    self.assertIsNone(pane.selectedEntry()) # (Open and Move to Trash: one at a time)
    self.assertIn("disabled", pane.openButton.state())
    self.assertIn("2 selected", pane.infoLabel.cget("text"))
    self.assertNotIn("disabled", pane.copyButton.state())

  def test0200dialog(self):
    from sn.model.fileCopies import FileSet
    from sn.view.graphics.copyDialog import CopyDialog
    family = [e for e in self.pane.directory.models() if e.name == "family"][0]
    web = self.root / "web"
    web.mkdir()
    dialog = CopyDialog(self.app, FileSet(self.pane.directory, [family]))
    dialog.folder.set(str(web))
    self.pump()
    tree = dialog.tree
    self.assertEqual([tree.item(i, "text") for i in tree.get_children()], ["family.snm", "family.snv", "onto.snm"])
    self.assertEqual(list(tree.item("2", "values")), ['used by "family.snm"', "onto.snm"])
    self.assertEqual(tree.item("2", "image")[0], str(dialog.ticked))
    self.assertIn("Everything they refer to goes with them", dialog.notes.cget("text"))
    dialog.toggle("2") # (the super-model left out)
    self.assertEqual(tree.item("2", "image")[0], str(dialog.unticked))
    self.assertFalse(dialog.files.items[2].include)
    self.assertIn("Used, but not going", dialog.notes.cget("text"))
    self.assertIn("onto.snm", dialog.notes.cget("text"))
    dialog.toggle("2")
    dialog.served.set("ftp://example.org/")
    self.assertIn("disabled", dialog.okButton.state())
    dialog.served.set("https://example.org/models/")
    self.assertNotIn("disabled", dialog.okButton.state())
    dialog.ok()
    self.assertEqual(dialog.result, (str(web), "https://example.org/models/"))
    self.assertEqual(sn.snPrefs[".copyFolder"], str(web))
    from sn.view.graphics.copyDialog import servedFrom
    self.assertEqual(servedFrom(str(web)), "https://example.org/models/") # (offered again for that folder)

  def test0300copySelected(self):
    from sn.view.graphics.copyDialog import CopyDialog
    web = self.root / "web"
    self.pane.tree.selection_set([self.row("a/b/models/family.snm")])
    self.pump()
    with mock.patch.object(CopyDialog, "show", lambda dialog: (dialog.destroy(), (str(web), None))[1]):
      self.pane.copySelected()
    self.scanned()
    self.pump()
    self.assertEqual(sorted(p.name for p in web.iterdir()), ["family.snm", "family.snv", "onto.snm"])
    self.assertTrue((self.root / "a/b/models/family.snm").exists()) # (copied: the originals stay)
    self.assertEqual(set(self.pane.tree.selection()), {self.row("web/family.snm"), self.row("web/family.snv"), self.row("web/onto.snm")})
    text = (web / "family.snm").read_text()
    self.assertIn('<item value="onto.snm" />', text)

  def test0400move(self):
    from sn.view.graphics import copyDialog
    trash = self.root / "trash"
    trash.mkdir()
    dest = self.root / "moved"
    self.pane.tree.selection_set([self.row("a/b/models/family.snm")])
    self.pump()
    with mock.patch.object(copyDialog.CopyDialog, "show", lambda dialog: (dialog.destroy(), (str(dest), None))[1]), \
         mock.patch.object(copyDialog, "moveToTrash", lambda path: shutil.move(path, trash / os.path.basename(path))):
      self.pane.copySelected(move=True)
    self.scanned()
    self.assertEqual(sorted(p.name for p in dest.iterdir()), ["family.snm", "family.snv"]) # (not what it uses, unless ticked)
    self.assertFalse((self.root / "a/b/models/family.snm").exists())
    self.assertTrue((self.root / "far/away/lib/onto.snm").exists())
    self.assertEqual(sorted(p.name for p in trash.iterdir()), ["family.snm", "family.snv"])
    aliases = sn.snPrefs.get("model/urlAliases", [])
    self.assertIn(f"{(self.root / 'a/b/models/family.snm').as_uri()} -> {(dest / 'family.snm').as_uri()}", aliases)
    m = Model.getDB((dest / "family.snm").as_uri()) # (still builds on the model it used, where it is)
    self.assertEqual([db.url for db in m.superDBs][-1], (self.root / "far/away/lib/onto.snm").as_uri())

  def test0450moveRefusesOpenFiles(self):
    from sn.model.fileCopies import FileSet
    from sn.view.graphics.copyDialog import CopyDialog
    family = [e for e in self.pane.directory.models() if e.name == "family"][0]
    view = family.views[0]
    self.app.windows[view.url] = mock.Mock(view=mock.Mock(model=mock.Mock(url=family.url))) # (as if it were open)
    blocked = []
    def show(dialog):
      dialog.folder.set(str(self.root / "moved"))
      blocked.append(("disabled" in dialog.okButton.state(), dialog.notes.cget("text")))
      dialog.destroy()
    with mock.patch.object(CopyDialog, "show", show):
      self.pane.tree.selection_set([self.row("a/b/models/family.snm")])
      self.pump()
      self.pane.copySelected(move=True)
    self.assertTrue(blocked[0][0])
    self.assertIn("close it first", blocked[0][1])
    self.assertTrue((self.root / "a/b/models/family.snm").exists())

  def test0500fileMenu(self):
    from sn.view.graphics.copyDialog import CopyDialog
    web = self.root / "web"
    with mock.patch.object(CopyDialog, "show", lambda dialog: (dialog.destroy(), (str(web), None))[1]):
      self.app.copyModelFiles((self.root / "a/b/models/family.snm").as_uri())
    self.assertEqual(sorted(p.name for p in web.iterdir()), ["family.snm", "family.snv", "onto.snm"])


if __name__ == "__main__":
  unittest.main()
