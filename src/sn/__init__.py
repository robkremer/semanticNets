#from util.utils import setupLogger
import atexit
from typing import override, cast
import logging
import os
import sys
from util import setupLogger

#setupLogger()

NAME = "Semantic Nets"
SHORT_NAME = "sn"
VERSION = "1.0"

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

from util.prefs import Prefs
from util.attribute import AttributedObject, Attribute, UNRESTRICTED,\
  VAR_DEFAULTED
from util.persistence.serialize import SerializationStrategy
SerializationStrategy.appName = f'{NAME} ({SHORT_NAME})'
SerializationStrategy.appVerion = VERSION

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
                                                           logger.print(f'Updated {key} to {level} ({logging.getLevelName(logger.getEffectiveLevel())}={logger.getEffectiveLevel()})') # type: ignore[attr-defined]
                                                          ))
if "loggingLevel" not in snPrefs:
  snPrefs['loggingLevel'] = Attribute('INFO',
              'choices[DEBUG,INFO,WARNING,ERROR,CRITICAL]',
              VAR_DEFAULTED)

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