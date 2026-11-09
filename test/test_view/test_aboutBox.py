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
The About box (*sn.view.graphics.aboutBox*): its licences' texts and icon are
there (and Semantic Nets' own is the LICENSE file's); it acknowledges every
reasoner engine and every library the apps include (with their dependencies);
and "About Semantic Nets" is in the menus -- the app's own menu on the Mac,
the Help menu elsewhere.

Created on Nov 9, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import builtins
import importlib.metadata as metadata
import logging
import os
import re
import sys
import unittest
import tkinter as tk
try:
  from packaging.requirements import Requirement # (read as pip and PyInstaller read them)
except ImportError:
  try:
    from pip._vendor.packaging.requirements import Requirement # type: ignore[no-redef]
  except ImportError:
    Requirement = None # type: ignore[assignment,misc]

import sn
from util import terminal
from util.aboutDialog import AboutDialog
from util.platformSupport import MAC
from sn.view.graphics import aboutBox

PACKAGING = os.path.join(os.path.dirname(__file__), "..", "..", "packaging")

def normal(name:str) -> str:
  ':returns: A distribution\'s name as pip compares them (eg: "docstring_parser" -> "docstring-parser").'
  return re.sub(r"[-_.]+", "-", name).lower()

def bundled() -> set[str]:
  '''
  :returns: The distributions the apps include (see packaging/semanticNets.spec):
    what requirements.txt and requirements-nemo.txt name for this platform, and
    what they need (those that are installed), as pip names them.
  '''
  todo = []
  for name in ("requirements.txt", "requirements-nemo.txt"):
    with open(os.path.join(PACKAGING, name), encoding="utf-8") as f:
      for line in f:
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
          r = Requirement(line)
          if r.marker is None or r.marker.evaluate():
            todo.append(r.name)
  ret:set[str] = set()
  while todo:
    name = normal(todo.pop())
    if name in ret:
      continue
    ret.add(name)
    try:
      requires = metadata.requires(name) or []
    except metadata.PackageNotFoundError:
      continue
    for spec in requires:
      r = Requirement(spec)
      if r.marker is None or r.marker.evaluate({"extra": ""}):
        todo.append(r.name)
  return ret

class TestCredits(unittest.TestCase):

  def test0100licences(self):
    'The licences\' texts that aren\'t in the libraries\' metadata are there; Semantic Nets\' own is the LICENSE file\'s.'
    for name in ("semanticNets.txt", "python.txt", "tcl-tk.txt", "nemo.txt"):
      self.assertTrue(aboutBox.licence(name), name)
    with open(os.path.join(os.path.dirname(__file__), "..", "..", "LICENSE"), encoding="utf-8") as f:
      self.assertEqual(aboutBox.licence("semanticNets.txt"), f.read())
    self.assertTrue(aboutBox.resource("icon.png", ).startswith(b"\x89PNG")) #type: ignore[union-attr]

  def test0200everythingAcknowledged(self):
    'Every reasoner engine, and every library the apps include, is a credit, with a web page; and the ones with no licence files in their metadata have their licences named.'
    credits = [c for _heading, cs in aboutBox.credits() for c in cs]
    dists = {normal(c.dist) for c in credits if c.dist}
    from sn.model.reasoner import ENGINES
    for e in ENGINES.values():
      self.assertIn(normal(e.package), dists, f"the {e.name} engine")
    if Requirement is None:
      self.skipTest("needs packaging (pip install packaging), to read the requirements")
    for name in bundled():
      self.assertIn(name, dists, f"{name} (in the apps)")
    for c in credits:
      self.assertTrue(c.url, c.name)
      if c.dist is None:
        self.assertTrue(c.licence or c.licenceText or c.name.startswith(("Brian", "Claude")), c.name)

class TestAboutBox(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    from sn.view.graphics.sngView import SNGView
    cls.saved = (sys.stdout, sys.stderr, builtins.input, sys.excepthook,
                 list(logging.getLogger().handlers), terminal._installedIORoutingRegistry,
                 Application.current, progress.listener, SNGView.askForMissingModel)
    cls.prefsWereDirty = sn.snPrefs.isDirty()
    try:
      cls.app = Application()
    except tk.TclError as ex:
      cls.restore()
      raise unittest.SkipTest(f"no display: {ex}")

  @classmethod
  def restore(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    from sn.view.graphics.sngView import SNGView
    (sys.stdout, sys.stderr, builtins.input, sys.excepthook, handlers, terminal._installedIORoutingRegistry,
     Application.current, progress.listener, SNGView.askForMissingModel) = cls.saved
    logging.getLogger().handlers[:] = handlers

  @classmethod
  def tearDownClass(cls):
    if AboutDialog.current is not None and AboutDialog.current.winfo_exists():
      AboutDialog.current.destroy()
    AboutDialog.current = None
    cls.app.destroy()
    cls.restore()
    if not cls.prefsWereDirty:
      sn.snPrefs.setDirty(False)

  def test0100inTheMenus(self):
    '"About Semantic Nets" is first in the app\'s own menu (Tk\'s "apple" cascade, first in the menu bar) on the Mac; last in the Help menu elsewhere.'
    label = f"About {sn.NAME}"
    if MAC:
      apple = self.app.nametowidget(self.app.menubar.entrycget(0, "menu"))
      self.assertEqual(str(apple).rsplit(".", 1)[-1], "apple")
      self.assertEqual(apple.entrycget(0, "label"), label)
    else:
      menu = self.app.helpmenu
      self.assertEqual(menu.entrycget(menu.index(tk.END), "label"), label) #type: ignore[arg-type]

  def test0200shows(self):
    'It shows Semantic Nets\' name, version, and licence first; with clingo\'s, read from its metadata, when it\'s installed.'
    self.app.showAbout()
    d = AboutDialog.current
    assert d is not None
    self.assertEqual(d.title(), f"About {sn.NAME}")
    self.assertEqual(d.licences[0].name, sn.NAME)
    self.assertIn("MIT License", d.licenceView.get("1.0", tk.END))
    names = [c.name for c in d.licences]
    for name in ("clingo", "Nemo", "Python", "Tcl/Tk", "pythonUtils"):
      self.assertIn(name, names)
    try:
      metadata.distribution("clingo")
    except metadata.PackageNotFoundError:
      return
    d.licenceList.selection_clear(0, tk.END)
    d.licenceList.selection_set(names.index("clingo"))
    d._showLicence()
    self.assertIn("Permission is hereby granted", d.licenceView.get("1.0", tk.END))

if __name__ == "__main__":
  unittest.main()
