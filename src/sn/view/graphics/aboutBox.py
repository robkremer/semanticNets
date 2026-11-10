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
Semantic Nets' About box (see *showAbout()*): "About Semantic Nets", first in
the app's own menu on the Mac -- the packaged app's, and when it's run from
source (where Tk's own would show Python's) -- and last in the Help menu
elsewhere (see *util.aboutDialog.installAbout()*, called by
*guiApp.Application*).

What it acknowledges is *credits()*: the people, the reasoner engines, the
libraries and the tools. The licences' texts that don't come with the
libraries' own metadata (Semantic Nets' own, Python's, Tcl/Tk's and Nemo's)
are package data, in sn/about/licences/, with the box's icon (sn/about/icon.png,
drawn by packaging/makeIcon.py); the others are read from the installed
distributions' metadata, which the packaged apps carry (see
packaging/semanticNets.spec).

Created on Nov 9, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import importlib.resources
import platform
import tkinter as tk
from typing import Optional
import sn
from util.aboutDialog import AboutDialog, Credit, showAbout as _showAbout
from util.platformSupport import MAC

COPYRIGHT = "© 2023-2026 Rob Kremer"
"(As in the LICENSE file, and the Mac app's Info.plist: see packaging/semanticNets.spec.)"

URL = "https://robkremer.github.io/semanticNets/"
"Its web site: the documentation."

INTRO = ("An editor for typed semantic networks (graphs of nodes and relations, organised by types), "
         "with a reasoner that draws conclusions from them.")

def resource(*parts:str) -> Optional[bytes]:
  '''
  :param parts: A file's path in sn/about/ (eg: "licences", "python.txt").
  :returns: Its contents (None if it's missing): it's package data, so it's
    read the same way from the source, the .pyz and the packaged apps.
  '''
  try:
    return importlib.resources.files("sn").joinpath("about", *parts).read_bytes()
  except (FileNotFoundError, NotADirectoryError, OSError):
    return None

def licence(name:str) -> Optional[str]:
  '''
  :param name: A licence's file in sn/about/licences/ (eg: "python.txt").
  :returns: Its text, if it's there, its lines ending with just a line feed
    (a Windows checkout's copy ends them with a carriage return too).
  '''
  data = resource("licences", name)
  return data.decode("utf-8").replace("\r\n", "\n") if data is not None else None

def tkVersion(root:Optional[tk.Misc]=None) -> str:
  '''
  :returns: The version of Tk the program's running with (eg: "8.6.16").
  '''
  try:
    return str((root or tk._default_root).tk.call("info", "patchlevel")) #type: ignore[union-attr,attr-defined] # @UndefinedVariable
  except (AttributeError, tk.TclError):
    return str(tk.TkVersion)

def credits(root:Optional[tk.Misc]=None) -> list[tuple[str, list[Credit]]]:
  '''
  :returns: What the About box acknowledges, by section: thanks, the reasoner
    engines (see *sn.model.reasoner.ENGINES*), the libraries (those the
    packaged apps include: see packaging/requirements.txt; Pillow and
    pypdfium2 only off the Mac), and the tools.
  '''
  python = licence("python.txt")
  return [
    ("Thanks to", [
      Credit("Brian R. Gaines", "Professor Emeritus, University of Calgary (his archives: Knowledge Science & Technology).",
             url="https://gaines.library.uvic.ca/BRGsite/"),
      Credit("Claude, by Anthropic", "An AI model: much of Semantic Nets was written with its help, in Claude Code.",
             url="https://www.anthropic.com/claude"),
    ]),
    ("Reasoner engines", [
      Credit("clingo", "Answer set programming, from Potassco (the Potsdam Answer Set Solving Collection): "
             "the default engine, included in the apps.", url="https://potassco.org/clingo/", dist="clingo"),
      Credit("Nemo", "A Datalog rule engine, from the Knowledge-Based Systems group at TU Dresden: included in the "
             "apps, and it explains why a conclusion holds.", url="https://github.com/knowsys/nemo",
             licence="Apache-2.0 OR MIT", dist="nemo-python", licenceText=licence("nemo.txt")),
      Credit("CLIPS", "A rule-based programming language, first made at NASA: optional (see \"Installing an engine\" "
             "in the User Guide).", url="https://www.clipsrules.net/", licence="public domain"),
      Credit("clipspy", "CLIPS for Python, by Matteo Cafasso.", url="https://github.com/noxdafox/clipspy",
             licence="BSD-3-Clause", dist="clipspy"),
      Credit("SWI-Prolog", "Prolog: optional (see \"Installing an engine\" in the User Guide).",
             url="https://www.swi-prolog.org/", licence="BSD-2-Clause"),
      Credit("janus-swi", "SWI-Prolog's Python interface (Janus).", url="https://pypi.org/project/janus-swi/",
             licence="BSD-2-Clause", dist="janus-swi"),
    ]),
    ("Libraries", [
      Credit("Python", "The language and its standard library: included in the apps.", url="https://www.python.org/",
             licence="PSF-2.0", version=platform.python_version(),
             licenceText=("The licences of the software Python includes (eg: OpenSSL, libffi,\n"
                          "expat, zlib) are at https://docs.python.org/3/license.html.\n\n" + python) if python else None),
      Credit("Tcl/Tk", "The windows and their graphics (through Python's tkinter): included in the apps.",
             url="https://www.tcl-lang.org/", licence="TCL (BSD-style)", version=tkVersion(root),
             licenceText=licence("tcl-tk.txt")),
      Credit("pythonUtils", "Rob Kremer's Python utilities: saving and reading files, attributes, commands, "
             "and Tk widgets (this box among them).", url="https://github.com/robkremer/pythonUtils",
             licence="MIT", licenceText=licence("semanticNets.txt")),
      Credit("requests", "Reading models from the web.", url="https://requests.readthedocs.io/", dist="requests"),
      Credit("urllib3", "HTTP, for requests.", url="https://urllib3.readthedocs.io/", dist="urllib3"),
      Credit("charset-normalizer", "Text encodings, for requests.", url="https://github.com/jawah/charset_normalizer",
             dist="charset-normalizer"),
      Credit("idna", "International domain names, for requests.", url="https://github.com/kjd/idna", dist="idna"),
      Credit("certifi", "Mozilla's root certificates, for requests.", url="https://github.com/certifi/python-certifi",
             dist="certifi"),
      Credit("cffi", "Calling C, for clingo.", url="https://cffi.readthedocs.io/", dist="cffi"),
      Credit("pycparser", "Parsing C, for cffi.", url="https://github.com/eliben/pycparser", dist="pycparser"),
      Credit("docstring_parser", "Reading functions' documentation, for the terminal's commands.",
             url="https://github.com/rr-/docstring_parser", dist="docstring-parser"),
      *([] if MAC else [
        Credit("Pillow", "Pictures, for Copy as picture.", url="https://python-pillow.org/", dist="pillow"),
        Credit("pypdfium2", "PDFium, for Copy as picture.", url="https://github.com/pypdfium2-team/pypdfium2",
               dist="pypdfium2"),
      ]),
    ]),
    ("Tools", [
      Credit("PyInstaller", "Makes the apps (and starts them).", url="https://pyinstaller.org/",
             licence="GPL-2.0-or-later, with an exception for the programs it makes"),
      Credit("Sphinx", "Makes the documentation (in the Help menu).", url="https://www.sphinx-doc.org/",
             licence="BSD-2-Clause"),
      Credit("Furo", "The documentation's look.", url="https://github.com/pradyunsg/furo", licence="MIT"),
    ]),
  ]

def showAbout(parent:Optional[tk.Misc]=None) -> AboutDialog:
  '''
  Show the About box (or bring it to the front, if it's shown).

  :param parent: What it's opened from, if anything.
  :returns: The About box.
  '''
  return _showAbout(parent, sn.NAME, version=sn.VERSION, icon=resource("icon.png"),
                    details=[f"Python {platform.python_version()}, Tk {tkVersion(parent)}"],
                    copyright=COPYRIGHT, url=URL, intro=INTRO, sections=credits(parent),
                    licence="MIT", licenceText=licence("semanticNets.txt"))
