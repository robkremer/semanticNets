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
import util.observer as observer
from util.prefs import Prefs

#setupLogger()

NAME = "Semantic Nets"
SHORT_NAME = "sn"
VERSION = "1.0"

observer.alwaysLater = True

class SNLogger(logging.Logger):
  def print(self, *args, **kwargs):
    '''
    Intended to mimic the print system command but allowing for redirection 
    and multiple destinations if necessary.
    '''
    print(*args, **kwargs)
    
# set up the logger to log to './sn.log' and to stderr  
setupLogger(SNLogger, SHORT_NAME) 
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
    return []

  @override
  def isIndividual(self)->bool:
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

atexit.register(snPrefs.save)

def saveAtExit():
  from sn.view.graphics.sngView import SNGView
  from sn.model.model import Model
  from util.utils import askUser
  from util.persistence.pRef import PRDb
  
  url:str
  db:PRDb
  for url, db in Model.AllDBs.items():
    if isinstance(db, Model):
      model:Model = db
      if not model.writeLocked() and model.isDirty():
        ans:str|None = askUser(f'Save modified model?\n  {url}\n(Y/N):', "Save modified Model?")
        if ans is not None and ans.upper() in ["Y", "YES", "T", "TRUE"]:
          model.save()
    elif isinstance(db, SNGView):
      view:SNGView = db
      if not view.writeLocked() and view.isDirty():
        ans = askUser(f'Save modified view?\n  {url}\n(Y/N):', "Save modified Model?")
        if ans is not None and ans.upper() in ["Y", "YES", "T", "TRUE"]:
          view.save()
    else:
      print(f'Unknown DB type {db.__class__.__name__}: {url}.')
  
atexit.register(saveAtExit)
