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
from typing import override, cast
import logging
import os
import sys

from util import setupLogger

NAME = "Semantic Nets"
SHORT_NAME = "sn"
VERSION = "1.0"

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
from util.prefs import Prefs

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
  
prefsfilename = f'{os.path.expanduser("~")}/.{SHORT_NAME}.xml'
try:
  snPrefs:Prefs = SNPrefs.read(prefsfilename)
except:
  snPrefs = SNPrefs()
  SNPrefs.prefsFileName = prefsfilename
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
  from util.utils import askUser
  if os.environ.get("SN_NO_SAVE_PROMPT"): # eg: automated test runs -- don't ask, don't save
    return
  if not obj.writeLocked() and obj.isDirty():
    ans:str|None = askUser(f'Save modified {kind}?\n  {url}\n(Y/N):', f'Save modified {kind.capitalize()}?')
    if ans is not None and ans.upper() in ["Y", "YES", "T", "TRUE"]:
      obj.save()

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
