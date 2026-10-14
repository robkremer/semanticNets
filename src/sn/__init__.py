#################################################################################
# (c) Copyright 2024-2026, Rob Kremer, MIT open source license.                 #
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
The Semantic Nets package is a tool for ... 
'''
import atexit
from typing import Any, override, cast
import logging
import os
import sys

from util import setupLogger

NAME = "Semantic Nets"
SHORT_NAME = "sn"
VERSION = "1.0"
"The program's version: written in the files it saves (see *SerializationStrategy.appVersion*)."

SCHEMA = "sn"
SCHEMA_VERSION = "1"
'''The version of the structures of models and views, as they're saved:
written in their files' heads ("schema", "schemaVersion": see
*Model.serializationHeader()*), so that a file saved with older ones can be
recognised and brought up to date when it's read. Change it whenever they
change (eg: a property's renamed, or its meaning changes).'''

class SNLogger(logging.Logger):
  def print(self, *args, **kwargs):
    '''
    Intended to mimic the print system command but allowing for redirection 
    and multiple destinations if necessary.

    :param args:
    :type args:
    :param kwargs:
    :type kwargs:
    '''
    print(*args, **kwargs)
    
# Log to "sn.log" (in the current directory; a packaged app logs in ~/Library/Logs/:
# see util.setupLogger()) and to stderr. This must come before anything else of
# util's is imported: util's modules get their loggers as they're imported, and
# util.getLogger() sets up logging its own way (to "<program>.log") if it finds
# it isn't set up yet.
setupLogger(SNLogger, SHORT_NAME)

import util.observer as observer
from util.persistence.serialize import SerializationStrategy
SerializationStrategy.appName, SerializationStrategy.appVersion = NAME, VERSION # (an application built on it says what it is itself, after importing sn)
from util.prefs import Prefs
from util.attribute import Attribute, VAR_DEFAULTED

observer.alwaysLater = True

def resourcePath(*parts:str) -> str:
  '''
  :param parts: A path relative to the project's top folder (eg: "sphinx"),
    or, in a packaged app, to its bundled resources (where the build puts the
    same things under the same names).
  :type parts: str
  :returns: The full path (which may not exist).
  :rtype: str
  '''
  base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
  return os.path.join(base, *parts)

EXAMPLES_PLACEHOLDER = "file:///SEMANTIC_NETS_EXAMPLES"
"The folder the example models are stored as being in (see *copyExamples()*)."

def exampleNames() -> list[str]:
  '''
  :returns: The example models' files that come with the program (package data:
    *sn/examples/*), eg: ["animals.snm", "animals.snv", ...].
  :rtype: list[str]
  '''
  import importlib.resources
  try:
    folder = importlib.resources.files("sn").joinpath("examples")
    return sorted(f.name for f in folder.iterdir() if f.name.endswith((".snm", ".snv")))
  except (FileNotFoundError, NotADirectoryError):
    return []

def copyExamples(target:str, names:list[str]|None=None) -> list[str]:
  '''
  Copy the example models that come with the program (see *exampleNames()*)
  into the folder *target* (made if need be), and make each copy refer to where
  it now is -- they're stored as being in *EXAMPLES_PLACEHOLDER* -- so that it
  isn't taken to have been moved when it's opened.

  :param target: The folder to copy them to.
  :type target: str
  :param names: The files to copy (eg: ["family.snm", "family.snv"]); by default, all of them.
  :type names: list[str]|None
  :returns: The paths of the copies.
  :rtype: list[str]
  '''
  import importlib.resources
  from pathlib import Path
  folder = importlib.resources.files("sn").joinpath("examples")
  os.makedirs(target, exist_ok=True)
  ret = []
  for f in names if names is not None else exampleNames():
    text = folder.joinpath(f).read_text(encoding="utf-8")
    path = os.path.join(target, f)
    with open(path, "w", encoding="utf-8") as fd:
      fd.write(text.replace(EXAMPLES_PLACEHOLDER, Path(target).as_uri()))
    ret.append(path)
  return ret
# logging.setLoggerClass(SNLogger)
# logFileName = SHORT_NAME+'.log'
# if os.path.isfile(logFileName): os.remove(logFileName)
# fileHandler = logging.FileHandler(logFileName)
# fileHandler.setFormatter(logging.Formatter('**%(levelname)s: %(name)s: %(message)s\n  at %(filename)s, func=%(funcName)s, line=%(lineno)d', style='%'))
# errStreamHandler = logging.StreamHandler(sys.stderr)
# logging.basicConfig(force=True, level=logging.INFO, handlers=[fileHandler, errStreamHandler]) #output to file and stderr 

def getLogger(name:str) -> SNLogger:
  '''
  Return a properly typed SNLogger for the molule who's __name__ is given in *name*.
  This may be either created of just returned, depending on if it exists already.
  
  :param name: Always call this with the __name__ variable for the file.
  :type name: str
  :returns: The properly typed SNLogger for created.
  :rtype: SNLogger
  '''
  if name == "__main__":
    mainModuleFile = sys.modules["__main__"].__file__
    assert mainModuleFile is not None
    path = os.path.splitext(os.path.basename(mainModuleFile))[0]
    path = 'sn.'+path
  else:
    path = name
  logger = logging.getLogger(path)
  assert type(logger) is SNLogger, f'Expected type SNLogger, got {type(logger)}.'
  return logger

logger = getLogger(__name__)

# load Prefs
class SNPrefs(Prefs):

  @override
  def getSupers[T:AttributedObject](self)->list[T]:
    '''
    :returns:
    :rtype: list[T]
    '''
    return []

  @override
  def isIndividual(self)->bool:
    '''
    :returns:
    :rtype: bool
    '''
    return False
  
from sn.view.graphics.labels import DEFAULT_LABEL, LABEL_NOTE, DEFAULT_TOOLTIP, TOOLTIP_NOTE # (a plain module: nothing of sn's)

PREFS:dict[str, tuple[Any, Any, str]] = {
  # key: (type, default, note)
  "loggingLevel": ("choices[DEBUG,INFO,WARNING,ERROR,CRITICAL]", "DEBUG",
    "How much detail goes into the program's log and messages: from DEBUG (the most) to CRITICAL (the least)."),
  "debug": (bool, False,
    "For developers: show objects' ids in their tooltips, and extra debugging items on their menus."),
  "debug_popupCache": (bool, True,
    "For developers, when debug is on: show an object's cached drawing attributes in its tooltip."),
  "model/defaultModel": (str, "temp.xml",
    "The model the text interface (sn) uses when it's started without one (eg: by --model)."),
  "reasoner/showSysRules": (bool, False,
    "Show the base rules (the meaning of symmetric, transitive, ...: see sn.model.reasoner.BASE_RULES) in the "
    "reasoner's results: their objects as data, and what they conclude as rule conclusions rather than plain "
    "inferences. For debugging the base rules; best left off."),
  "text/wrap": (bool, False,
    "Whether long lines wrap in the terminal pane (else it scrolls sideways)."),
  "text/backgroundColor": ("color", "white",
    "The terminal pane's background colour."),
  "gui/recentFiles": (int, 10,
    "How many of the views (or models) opened most recently File | Open Recent lists (0 for none)."),
  "model/urlAliases": ("list[str]", [],
    "Where models (and views) have moved to, so that references to them where they were are taken to be to them "
    "where they are now -- eg: an ontology moved to another web site. Each is \"old -> new\": two URLs (or paths). "
    "One ending in \"/\" moves everything under it: eg, \"http://old.org/onto/ -> https://new.org/ontologies/\"."),
  "hooks/trustedModules": ("list[str]", [],
    "The Python modules and packages, besides sn's own, whose hooks models may use: functions named by objects' "
    "attributes (eg: a menu item's .menu/... attribute), as \"module:function\" (see sn.hooks). A hook whose "
    "program isn't running is found by importing its module -- running its code -- so only list ones you trust: "
    "eg, \"mytools\" trusts mytools and the modules in it (mytools.hooks, ...)."),
  "gui/directoryPath": (str, "",
    "Where the model directory (Window | Model Directory) looks for models and views, separated by \";\": folders "
    "(paths or \"file:\" URLs) -- one ending in \"/**\" includes the folders below it -- and the URLs of models "
    "and views elsewhere (eg: \"https://...\"). The folders of the models and views opened, made or saved are added."),
  "gui/backgroundColor": ("color", "grey95",
    "The canvas's background colour."),
  "gui/highlightColor": ("color", "#ffd966",
    "The colour of the glow marking highlighted objects (eg: a query's answers, and the query)."),
  "gui/highlightColorNegative": ("color", "#f4a3a3",
    "The colour of the glow marking a query that has no answers (\"no\")."),
  "gui/label": (str, DEFAULT_LABEL,
    "The label template for nodes, unless one has a vis/label of its own. " + LABEL_NOTE),
  "gui/relationLabel": (str, DEFAULT_LABEL,
    "The label template for relations, unless one has a vis/label of its own. " + LABEL_NOTE),
  "gui/tooltip": (str, DEFAULT_TOOLTIP,
    "The tooltip template, unless an object has a vis/tooltip of its own. " + TOOLTIP_NOTE),
  "gui/tooltipMaxLines": (int, 40,
    "The most lines a tooltip shows: a longer one (eg: a long function's source) is cut short, saying how many "
    "more lines there are (0: no limit)."),
  "gui/editorCommand": (str, "",
    "The command that opens a file at a line in your editor -- eg, to show a class or function's source "
    "(pythonParser) -- with {path}, {line} and {url} (the file's file: URL) filled in. Empty: it's shown in a "
    "window here instead (as it is if the command can't be run). Eg:\n"
    "  BBEdit (or TextMate):  open \"txmt://open?url={url}&line={line}\"\n"
    "  BBEdit's command line tools:  bbedit +{line} {path}\n"
    "  VS Code:  code -g {path}:{line}\n"
    "  Sublime Text:  subl {path}:{line}\n"
    "  Eclipse (to try: it takes path:line):  .../Eclipse.app/Contents/MacOS/eclipse --launcher.openFile {path}:{line}"),
  "gui/NodeMinSize": (int, 30,
    "The width (before zooming) of a new node's shape, unless its vis/minSize says otherwise."),
  "gui/NodeAspectRatio": (float, 1.5,
    "The height-to-width ratio of a new node's shape, unless its vis/aspectRatio says otherwise."),
  "gui/shadowTypes": (bool, True,
    "Draw a shadow around all Type objects (as opposed to Individual objects)."),
  "gui/showSystemTags": (bool, True,
    "Mark the system model's objects (node, relation, isa, ...) with an \"S\" tag."),
  "gui/showTypeTags": (bool, True,
    "Mark types (as opposed to individuals) with a \"T\" tag."),
  "gui/showRemoteTags": (bool, True,
    "Mark objects from other models (not the view's own model) with an \"R\" (remote) tag."),
  "gui/showConstraintMarker": (bool, True,
    "Mark each variable that has constraints with a \"{}\" marker."),
  "gui/allowEditingSystemObjects": (bool, False,
    "Allow editing the system model's objects. They're reset each time the program starts, so changes don't last; "
    "best left off."),
  "gui/debugMenus": (bool, False,
    "For developers: add debugging items (validate, repaint, ...) to the canvas's menus."),
  "gui/optimization/aggressiveLabelPlacement": (int, 3,
    "How hard to look for a free spot for a relation's label when placing it, from 0 (not at all: it stays "
    "midway between the relation's ends) to 10 (up to 100 steps out; n: up to n*n steps). Higher values take "
    "longer -- a lot longer in a crowded view, as when showing a big model."),
}
'''
The preferences: key -> (type, default, note). Each is in the preferences
(*snPrefs*) from the start, with its default if the file doesn't have it --
so a missing preferences file (the first run, or deleted to start afresh) is
made from these -- and with its note (unless the user has written their own:
see *Attribute.userNote*). A preference can still be made on the fly (by
*snPrefs.get(key, storeDefault=...)*), but it should be added here, so it has
a note. Keys starting with "." -- kept by the program for itself -- aren't
here: the settings editor doesn't show them.
'''

RENAMED_PREFS:dict[str, str] = {
  "gui/openWindows": ".openWindows",
  "gui/examplesInstalled": ".examplesInstalled",
  "defaultModel": "model/defaultModel",
  "gui/showIndividualShadow": "gui/shadowTypes",
  }
"Preferences that have been renamed or merged into others: old name -> new name (see *renamePrefs()*)."

def renamePrefs(prefs:Prefs) -> None:
  '''
  Move preferences saved under old names (see *RENAMED_PREFS*) to their new
  ones -- eg: the internal ones that once showed in the Settings dialog, now
  hidden by a name starting with ".", or ones merged into another. A value
  already under the new name is kept (and the old one dropped).

  :param prefs: The preferences.
  :type prefs: Prefs
  '''
  for old, new in RENAMED_PREFS.items():
    if old not in prefs.keys():
      continue
    attr = prefs.getLocalAttr(old)
    if new not in prefs.keys() and attr is not None:
      prefs.setAttr(new, attr)
    del prefs[old]

def initPrefs(prefs:Prefs) -> None:
  '''
  Put each of *PREFS* in *prefs*: with its default, if it isn't there; and its
  note, unless the user has written their own. (Notes aren't saved -- only the
  user's: see *Attribute.userNote* -- so adding them doesn't change the file.)

  :param prefs: The preferences.
  :type prefs: Prefs
  '''
  for key, (typ, default, note) in PREFS.items():
    attr = dict.get(prefs, key) # (the stored Attribute itself: getAttr() gives a copy)
    if attr is None:
      prefs.setAttr(key, Attribute(default, typ, VAR_DEFAULTED, note))
    elif not (getattr(attr, "userNote", False) and attr.note): # (an empty "user's" note: from a file written before notes were left out of it)
      attr.note = note
      attr.userNote = False

SN_FOLDER = os.path.join(os.path.expanduser("~"), f".{SHORT_NAME}")
'''Where the program keeps its own files: the preferences (*prefs.xml*), the
copies of models and views read from the web (*cache/*: see
*SerializationStrategy.cacheFolder*), ...'''

def snFolder(*parts:str) -> str:
  '''
  :param parts: A path within *SN_FOLDER* (eg: "cache").
  :type parts: str
  :returns: It -- made, if it isn't there.
  :rtype: str
  '''
  path = os.path.join(SN_FOLDER, *parts)
  os.makedirs(path, exist_ok=True)
  return path

import util.utils
util.utils.webCacheFolder = os.path.join(SN_FOLDER, "cache") # (copies of what's read from the web: used when it can't be reached)

prefsfilename = os.path.join(SN_FOLDER, "prefs.xml")
_oldPrefs = os.path.join(os.path.expanduser("~"), f".{SHORT_NAME}.xml") # (where they were kept before SN_FOLDER)
if not os.path.exists(prefsfilename) and os.path.exists(_oldPrefs):
  try:
    snFolder()
    os.replace(_oldPrefs, prefsfilename)
    logger.info(f'The preferences have moved: from "{_oldPrefs}" to "{prefsfilename}".')
  except OSError:
    logger.warning(f'Couldn\'t move the preferences from "{_oldPrefs}" to "{prefsfilename}": using them where they are.', exc_info=True)
    prefsfilename = _oldPrefs
try:
  snPrefs:Prefs = SNPrefs.read(prefsfilename)
except:
  snPrefs = SNPrefs()
  SNPrefs.prefsFileName = prefsfilename
renamePrefs(snPrefs) # (first: a renamed preference's value is kept, not replaced by its default)
initPrefs(snPrefs)

_userAliases:list[str] = []
"The aliases added from the \"model/urlAliases\" preference (see *applyURLAliases()*)."

def applyURLAliases(entries:Any) -> list[str]:
  '''
  Make the aliases in *entries* -- the "model/urlAliases" preference: each
  "old -> new" -- the URL aliases (see *PRDb.aliases*), in place of those it
  made before.

  :param entries:
  :type entries: Any
  :returns: The entries that couldn't be made sense of.
  :rtype: list[str]
  '''
  from util.persistence.pRef import PRDb
  from util.utils import fixURL
  def url(text:str) -> str:
    text = text.strip()
    if "://" in text or text.startswith(("sn:", "file:")):
      return text
    folder = text.endswith("/")
    ret = fixURL(os.path.expanduser(text), replaceExt=None, mode="")[0]
    return ret + "/" if folder and not ret.endswith("/") else ret
  for old in _userAliases:
    PRDb.aliases.pop(old, None)
  _userAliases.clear()
  bad:list[str] = []
  for entry in entries if isinstance(entries, list) else []:
    old, arrow, new = str(entry).partition("->")
    if not arrow or not old.strip() or not new.strip():
      bad.append(str(entry))
      continue
    try:
      o, n = url(old), url(new)
    except Exception:
      bad.append(str(entry))
      continue
    PRDb.aliases[o] = n
    _userAliases.append(o)
  for b in bad:
    logger.warning(f'The URL alias "{b}" (in the model/urlAliases setting) isn\'t "old -> new": it\'s ignored.')
  return bad

applyURLAliases(snPrefs.get("model/urlAliases", []))
def _onURLAliases(_key:str, value:Any) -> None:
  applyURLAliases(value)
snPrefs.addCallback("model/urlAliases", _onURLAliases)
snPrefs.addCallback("loggingLevel", lambda key, level: (logger.setLevel(logging.getLevelNamesMapping()[level.upper()]), # type: ignore[func-returns-value,arg-type]
                                                           logger.info(f'Updated {key} to {level} ({logging.getLevelName(logger.getEffectiveLevel())}={logger.getEffectiveLevel()})') # type: ignore[attr-defined]
                                                          ))
logger.setLevel(logging.getLevelNamesMapping()[snPrefs.get("loggingLevel", 
                                                           storeDefault="DEBUG", 
                                                           storeType='choices[DEBUG,INFO,WARNING,ERROR,CRITICAL]').upper()
                                              ])

# # insure PYTHONPATH includes Tygra's directory (required to resolve classes at runtime, eg: Roles as types in Attributes)
# thisDir = str(pathlib.Path(__file__).parent.parent.resolve())
# if thisDir not in sys.path:
#   sys.path.append(thisDir)
#   logger.warning(f'Added "{thisDir}" to PYTHONPATH:\n  {sys.path}')
# else:
#   logger.debug(f'PYTHONPATH already contains "{thisDir}":\n  {sys.path}')
#
# def registerAtExit(): # prevent circular imports
#   from util.persistence import PRDb
#   atexit.register(PRDb.atexit)
#   atexit.register(tygraPrefs.save)
#   atexit.register(fileHandler.close)
#
# registerAtExit()

def savePrefsIfChanged() -> None:
  '''
  Save the preferences -- but only if they've changed, so that merely running
  (or importing) the program -- eg: the documentation build, or a self-test --
  doesn't rewrite the user's preferences file.
  '''
  if snPrefs.isDirty():
    snPrefs.save()

atexit.register(savePrefsIfChanged)

def checkSaveModified(obj, url:str, kind:str) -> None:
  '''
  Check whether *obj* has unsaved changes and, if so, ask the user whether to
  save it before it's discarded -- either because its window is being closed
  (see *sn.view.graphics.guiApp.Application._closeWindow()*) or because the
  whole app is exiting (see *saveAtExit()* below).

  Pulled out of *saveAtExit()* as a shared helper so both call sites -- the
  whole-app-exit path and the individual-window-close path -- prompt with
  exactly the same writeLocked()/isDirty()/save() logic instead of drifting
  apart.

  :param obj: The database-backed object to check -- a *Model* or *SNGView*
    (anything exposing *writeLocked()*, *isDirty()* and *save()*).
  :type obj: util.persistence.pRef.PRDb
  :param url: *obj*'s URL, used only in the confirmation dialog's message.
  :type url: str
  :param kind: A lowercase human-readable noun for the confirmation dialog,
    e.g. "model" or "view".
  :type kind: str
  :rtype: None

  If the environment variable SN_NO_SAVE_PROMPT is set (to anything), nothing
  is asked and nothing is saved -- for automated runs, such as tests, which
  would otherwise put a dialog on the screen for every modified model.
  '''
  if os.environ.get("SN_NO_SAVE_PROMPT"): # eg: automated test runs -- don't ask, don't save
    return
  if not obj.writeLocked() and obj.isDirty() and askYesNo(f'Save the changes to this {kind}?\n\n{_displayPath(url)}', f'Save modified {kind}?'):
    obj.save()

def _displayPath(url:str) -> str:
  '''
  :param url:
  :type url: str
  :returns: *url* as the user knows it: a local file's path (eg: "~/models/family.snv"), or else the URL.
  :rtype: str
  '''
  from urllib.parse import urlparse, unquote
  parsed = urlparse(url)
  if parsed.scheme != "file":
    return url
  path = unquote(parsed.path)
  home = os.path.expanduser("~")
  return "~" + path[len(home):] if path.startswith(home + os.sep) else path

def askYesNo(question:str, title:str) -> bool:
  '''
  Ask the user a yes-or-no question: in a Yes/No dialog over the focused
  window, if the GUI is running; otherwise (eg: the terminal interface, or
  once the windows are gone at exit) as text (see *util.utils.askUser()*).

  :param question:
  :type question: str
  :param title: The dialog's title.
  :type title: str
  :returns: True iff the answer is yes.
  :rtype: bool
  '''
  import tkinter as tk
  root = tk._default_root # type: ignore[attr-defined]
  if root is not None:
    from tkinter import messagebox
    try:
      focused = root.focus_get()
    except KeyError: # (eg: a menu's popdown, which isn't a Python widget)
      focused = None
    return bool(messagebox.askyesno(title, question, parent=focused.winfo_toplevel() if focused is not None else root))
  from util.utils import askUser
  ans = askUser(f'{question}\n(Y/N):', title)
  return ans is not None and ans.strip().upper() in ("Y", "YES", "T", "TRUE")

_savedAtExit = False
"Set once saveAtExit() has run, so the atexit call after an explicit one doesn't ask again."

def saveAtExit():
  '''
  Offer to save every modified model and any still-open view. Runs at most
  once per process: eg: the Quit handler calls it explicitly and then exits,
  which would otherwise run it again (via atexit) and repeat every question
  the user already answered "no" to.
  '''
  global _savedAtExit
  if _savedAtExit:
    return
  _savedAtExit = True
  from sn.view.graphics.guiApp import Application
  from sn.model.model import Model
  from util.persistence.pRef import PRDb
  import tkinter as tk

  url:str
  db:PRDb
  print("saving at exit", file=sys.__stdout__)
  for url, db in Model.AllDBs.items():
    if isinstance(db, Model):
      checkSaveModified(db, url, "model")
    else:
      print(f'Unknown DB type {db.__class__.__name__}: {url}.')

  # SNGViews are deliberately constructed with memoryResident=False (see
  # SNGView.__new__()/__init__() in sn.view.graphics.sngView), so they never
  # land in PRDb.AllDBs -- the loop above will never see one. The only
  # reliable way to find the ones currently open is via the live
  # Application's own window registry (tk._default_root is that Application,
  # the same lookup SNGView.__init__() itself uses).
  root = tk._default_root
  if isinstance(root, Application):
    for url, window in root.windows.items():
      if window.view is not None:
        checkSaveModified(window.view, url, "view")

atexit.register(saveAtExit)
