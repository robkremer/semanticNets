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
The XMLreader plugin's dialog (*view.ReaderDialog*): the model, view and
ontology files follow the XML file (the view and ontology following the
model) until they're changed by hand, and again once emptied; what's said
about the ontology, and whether it can be replaced, follows what it is; and
Go needs all four. An ontology given by hand is offered again next time (a
plugin preference), until one's made beside the model again. (Nothing's
made: *convert()* is stubbed.)

Created on Oct 19, 2026

@author: robkremer
'''
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import tkinter as tk
from sn.plugins import importBundled

class TestReaderDialog(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.view = importBundled("XMLreader", "view")
    try:
      cls.root = tk.Tk()
    except tk.TclError as ex:
      raise unittest.SkipTest(f"no display: {ex}")
    cls.root.withdraw()

  @classmethod
  def tearDownClass(cls):
    cls.root.destroy()

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.folder = Path(self.tmp.name).resolve()
    self.dialog = self.view.ReaderDialog(self.root) # (any window will do: it's only its parent)
    self.dialog.withdraw()

  def tearDown(self):
    if self.dialog.winfo_exists():
      self.dialog.destroy()
    self.tmp.cleanup()

  def files(self) -> tuple[str, str, str, str]:
    v = self.dialog.vars
    return v["xml"].get(), v["model"].get(), v["view"].get(), v["ontology"].get()

  def type(self, key:str, value:str) -> None:
    "As if typed into its field."
    self.dialog.vars[key].set(value)

  def go(self) -> bool:
    return not self.dialog.goButton.instate(["disabled"])

  def test_defaults(self):
    'The files made follow the XML file, as before.'
    self.assertFalse(self.go())
    xml = str(self.folder / "books.xml")
    self.type("xml", xml)
    self.assertEqual(self.files()[1:], self.view.outputPaths(xml))
    self.assertTrue(self.go())

  def test_byHand(self):
    'Changed by hand, a file stops following (but those following it follow it); emptied, it follows again.'
    self.type("xml", str(self.folder / "a.xml"))
    shared = str(self.folder / "shared.snm")
    self.type("ontology", shared)
    self.type("model", str(self.folder / "out" / "m.snm"))
    self.assertEqual(self.files()[1:], (str(self.folder / "out" / "m.snm"), str(self.folder / "out" / "m.snv"), shared))
    self.type("xml", str(self.folder / "b.xml"))
    self.assertEqual(self.files()[1:], (str(self.folder / "out" / "m.snm"), str(self.folder / "out" / "m.snv"), shared))
    self.type("model", "")
    self.assertTrue(self.go()) # (filled in again at once)
    self.assertEqual(self.files()[1:3], self.view.outputPaths(str(self.folder / "b.xml"))[:2]) # (the ontology's still by hand)
    self.assertEqual(self.files()[3], shared)
    self.type("ontology", "")
    self.assertEqual(self.files()[1:], self.view.outputPaths(str(self.folder / "b.xml")))

  def test_folder(self):
    'Defaults somewhere else (eg: for the plugin\'s own examples).'
    out = str(self.folder / "examples")
    d = self.view.ReaderDialog(self.root, str(self.folder / "c.xml"), defaults=lambda xml: self.view.defaultPaths(xml, out))
    try:
      self.assertEqual(d.vars["model"].get(), os.path.join(out, "c_xml.snm"))
      self.assertEqual(d.vars["ontology"].get(), os.path.join(out, "c_xml_ontology.snm"))
    finally:
      d.destroy()

  def test_ontologyNote(self):
    'What\'s said about the ontology, and whether "Replace it" can be ticked.'
    d = self.dialog
    self.type("xml", str(self.folder / "a.xml"))
    self.assertIn("it's made", d.ontologyNote.get())
    self.assertTrue(d.replaceButton.instate(["disabled"]))
    Path(d.vars["ontology"].get()).write_text("")
    self.type("ontology", d.vars["ontology"].get() + " ") # (as if changed: the same file)
    self.assertIn("is added to it", d.ontologyNote.get())
    self.assertFalse(d.replaceButton.instate(["disabled"]))
    d.replaceOntology.set(True)
    d.refresh()
    self.assertIn("made afresh", d.ontologyNote.get())
    self.assertTrue(d.files().replaceOntology)
    self.type("ontology", "https://example.com/books_ontology.snm")
    self.assertIn("on the web", d.ontologyNote.get())
    self.assertTrue(d.replaceButton.instate(["disabled"]))
    self.assertEqual(d.files().ontology, "https://example.com/books_ontology.snm")

  def test_startWith(self):
    'An ontology to start with is as if given by hand: it stays, and is reported so after Go.'
    shared = str(self.folder / "shared.snm")
    xml = str(self.folder / "a.xml")
    went = []
    d = self.view.ReaderDialog(self.root, xml, ontology=shared, onGo=lambda files, byHand: went.append((files.ontology, byHand)))
    try:
      self.assertEqual(d.vars["ontology"].get(), shared)
      self.assertEqual(d.vars["model"].get(), self.view.outputPaths(xml)[0])
      with mock.patch.object(self.view, "convert", return_value=True) as convert:
        d.go()
      self.assertEqual(convert.call_args.args[1].ontology, shared)
      self.assertEqual(went, [(shared, True)])
    finally:
      if d.winfo_exists():
        d.destroy()

  def test_remembered(self):
    '''The plugin remembers the ontology given by hand, and offers it next time
    (if it's still there); one made beside the model is forgotten.'''
    package = importBundled("XMLreader")
    prefs:dict = {}
    items:dict = {}
    ctx = SimpleNamespace(app=SimpleNamespace(EXAMPLES_FOLDER=str(self.folder / "ex")), folder=str(self.folder / "plugin"),
                          pref=lambda k, default=None: prefs.get(k, default), setPref=prefs.__setitem__,
                          addMenuItem=items.__setitem__)
    Dialog = self.view.ReaderDialog
    with mock.patch.object(self.view, "ReaderDialog", side_effect=lambda app, **kw: Dialog(self.root, **kw)): # (over the test's window: ctx.app's a stand-in)
      package.register(ctx)
      def open():
        items["XML Reader..."]()
        d = package._dialog
        d.withdraw()
        return d
      def go(d):
        with mock.patch.object(self.view, "convert", return_value=True):
          d.go()
        self.assertIsNone(package._dialog)
      xml = str(self.folder / "a.xml")
      d = open()
      d.vars["xml"].set(xml)
      self.assertEqual(d.vars["ontology"].get(), self.view.outputPaths(xml)[2])
      shared = self.folder / "shared.snm"
      shared.write_text("")
      d.vars["ontology"].set(str(shared))
      go(d)
      self.assertEqual(prefs["lastOntology"], str(shared))
      d = open()
      d.vars["xml"].set(str(self.folder / "b.xml"))
      self.assertEqual(d.vars["ontology"].get(), str(shared))
      d.vars["ontology"].set("") # (back to beside the model)
      go(d)
      self.assertEqual(prefs["lastOntology"], "")
      prefs["lastOntology"] = str(self.folder / "gone.snm") # (not there any more: not offered)
      d = open()
      d.vars["xml"].set(xml)
      self.assertEqual(d.vars["ontology"].get(), self.view.outputPaths(xml)[2])
      d.close()

if __name__ == "__main__":
  unittest.main()
