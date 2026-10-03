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
Classes here will be loaded by the Tygra command parser. Criteria:

  - subclass of commandParser.ParsableCommandDef
  - class name ends with "Command" (useful it you want to filter some out in debugging)

Created on May 15, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>

-----------------
'''

from __future__ import annotations
import sn
from sn import snPrefs
from util.terminal import TerminalRegistry
from util.utils import strToBool, quoteIfNecessary
import sys
from sn.model.model import Model, GraphObject
from sn.controller.modelInterface import ModelContext
import logging
from typing import Any, Callable, cast
import readline  # noqa: F401 — importing enables input() line editing
import argparse
import tkinter as tk
from util.terminal import TerminalWidget, PlainTextTerminal

logger:sn.SNLogger = sn.getLogger(__name__)

# CARRET      = "\u298A"
# BACK_CARRET = "\u2989"
CARRET      = "\u23F5"      
BACK_CARRET = "\u23F4"
RIGHT_ARROW = "\u279C"


INDIVIDUAL_MARKER = '\u24D8'  # circled i
"Marks an individual (as opposed to tyoe) in *GraphObject* name string"
TYPE_MARKER = '\u24C9'        # circled T
"Marks a type (as opposed to individual) in *GraphObject* name string"
SYSTEM_MARKER = '\u24C8'      # circled S
"Marks an object as a system object in *GraphObject* name string"
RELATION_MARKER = '\u24E1'    # circled r
NODE_MARKER = '\u24DD'        # circled n

modelFormatter:Callable[[Model],str] = str
graphObjectFormatter:Callable[[GraphObject],str] = str

KM = TYPE_MARKER
kindMarkerStr:str = ""

formatters:dict[str,str] = {
  "Model": "str",
  "GraphObject": "str"}

formatOptions:dict[str, dict[str,Callable[[GraphObject],str]]] = {
  "Model": 
    {
    "str"    : str,
    "tostring": lambda m: m.tostring(relativeTo=context.defaults["model"]),
    "repr"   : repr,
    "torepr" : lambda m: m.torepr(relativeTo=context.defaults["model"]),
    "members": lambda m: str(m) + "\n  " + ("\n  ".join([(getKindMarkStr(go)+getFormatter("GraphObject")(go)) for go in m.values()])),
    },
  "GraphObject": 
    {
    "str"   : str,
    "tostring": lambda go: go.tostring(relativeTo=context.defaults["model"]),
    "repr"  : repr,
    "torepr": lambda go: go.torepr(relativeTo=context.defaults["model"]),
    "name"  : lambda go: quoteIfNecessary(go.name),
    "quotedname" : lambda go: f'"{go.name}"',
    "id"    : lambda go: str(go.id),
    "simple": lambda go: f'{quoteIfNecessary(go.name)}:{go.id}',
    }
  }

def getFormatter(typeName:str) -> Callable:
  '''
  :param typeName:
  :type typeName: str
  :returns:
  :rtype: Callable
  '''
  return formatOptions[typeName][formatters[typeName]]

def getKindMarkStr(go:GraphObject):
  '''
  :param go:
  :type go: GraphObject
  :returns:
  :rtype:
  '''
  if go.isType():
    return kindMarkerStr
  return ""
  
class UIContext(ModelContext):
  
  commandHelp:dict[str,str] = ModelContext.commandHelp | {
    "format": "Define the output format when objects are returned from commands."
    }
  
  def _format(self, typeName:str|None=None, format:str|None=None, /) -> str|list[str]|None: # @ReservedAssignment
    '''
    :param typeName:
    :type typeName: str | None
    :param format:
    :type format: str | None
    :returns:
    :rtype: str | list[str] | None
    '''
    global formatters
    global formatOptions
    assert typeName is None or typeName in formatOptions, \
      f'"{typeName}" is not a known object type. Use one of {list(formatters.keys())}.'
    if typeName is None:
      print(f'formats are available for the following types: {list(formatters.keys())}.')
      return list(formatters.keys())

    assert format is None or format in formatOptions[typeName], \
      f'"{typeName}" does not have option "{format}". Use one of {list(formatOptions[typeName].keys())}.'
    if format is None:
      print(f'The format for {typeName} is set to {formatters[typeName]} and\nhas the following options: {list(formatOptions[typeName].keys())}.')
      return list(formatOptions[typeName].keys())
    else:
      formatters[typeName] = format
      return format
    
  def format_object(self, format:str|None=None, /, kindMarker:str|None=None): # @ReservedAssignment
    '''
    Set the output format for graphObjects.
    
    :param format: one of str, repr, name, qname, id, simple.
    :type format: str
    :param kindMarker:
    :type kindMarker: str | None
    :returns:
    :rtype:
    '''
    global graphObjectFormatter
    global kindMarkerStr
    if kindMarker is not None:
      kindMarkerStr = KM if strToBool(kindMarker) else ""
      
    return self._format("GraphObject", format)
  
  def print(self, string:str, stderr:bool=False) -> None:
    '''
    For debugging.
    
    :param string: prints this string to stdout.
    :type string: str
    :param stderr:
    :type stderr: bool
    '''
    if stderr:
      print(string, file=sys.stderr)
    else:    
      print(string)
    
  def log(self, string:str) -> None:
    '''
    For debugging.
    
    :param string: Sends this string to the logger as a WARNING.
    :type string: str
    '''    
    logger.print(logging.WARNING, string)
    
  def throw(self, string:str) -> None:
    '''
    For debugging.
    
    :param string: raises an exception with this string as the message.
    :type string: str
    '''    
    raise Exception(string)
    
  def input(self, string:str) -> str:
    '''
    For debugging.
    
    :param string: raises an exception with this string as the message.
    :type string: str
    :returns:
    :rtype: str
    '''    
    return input(string)
    
  def format_model(self, format:str|None=None): # @ReservedAssignment
    '''
    Set the output format for Models.
    
    :param format: one of str, repr.
    :type format: str
    :returns:
    :rtype:
    '''      
    return self._format("Model", format)
      
def printLists(obj:Any, nCarrets=1, contextModel=None) -> str|None:
  '''
  :param obj:
  :type obj: Any
  :param nCarrets:
  :type nCarrets:
  :param contextModel:
  :type contextModel:
  :returns:
  :rtype: str | None
  '''
  buf:str = ""
  
  def printx(s:str|None, end="\n"):
    if s:
      nonlocal buf
      buf += (s + end)
    
  if obj is None:
    return None
  if isinstance(obj, (Model)):
    printx(f'{BACK_CARRET*nCarrets} {getFormatter("Model")(obj)}')
  elif isinstance(obj, (GraphObject)):
    printx(f'{BACK_CARRET*nCarrets} {getKindMarkStr(obj)}{getFormatter("GraphObject")(obj)}')
  elif isinstance(obj, str):
    lines = obj.split('\n')
    if len(lines) == 1:
      printx(f'{BACK_CARRET*nCarrets} "{lines[0]}"')
    else:
      printx(f'{BACK_CARRET*nCarrets} """\n', end="")
      for i in lines:
        printx(f'{" "*nCarrets} {i}')
      printx(f'{" "*nCarrets} """')
  elif isinstance(obj, list):
    for i in obj:
      printx(printLists(i, nCarrets=nCarrets+1, contextModel=contextModel), end="")
  elif isinstance(obj, dict):
    for k,v in obj.items():
      printx(printLists(k, nCarrets=nCarrets+1, contextModel=contextModel), end="")
      printx(printLists(v, nCarrets=nCarrets+2, contextModel=contextModel), end="")
  elif isinstance(obj, tuple):
    printx(f'{BACK_CARRET*nCarrets} (')#{len(obj)}-tuple:')
    for i in obj:
      printx(printLists(i, nCarrets=nCarrets+1, contextModel=contextModel), end="")
    printx(f'{BACK_CARRET*nCarrets} )')#{len(obj)}-tuple:')
  else: # either an iterable if that works or print the __str__ representation
    try:
      for i in obj:
        printx(printLists(i, nCarrets=nCarrets+1, contextModel=contextModel), end="")
    except:
      printx(f'{BACK_CARRET*nCarrets} {str(obj)}')
  return buf
  

class SNAbstractTerminal:
  
  def __init__(self, model:Model|str, context:ModelContext|None=None):
    # # interpret the command line
    # args:dict = {"suggest_on_error":True} if sys.version_info[0]>=3 and sys.version_info[1]>=14 else dict()
    # commandLineParser = argparse.ArgumentParser(**args, description=\
    #   '''Command line interface for Semantic Nets. Running this program (without
    #   the "--" argument to execute a subcommand) runs in interactive command environment.''')
    # commandLineParser.add_argument("--model", "-m", help=\
    #   '''Set the default model for all commands. Default is whatever was last 
    #   used by the program, or if that's not available, "temp.xml" in the 
    #   current directory if it exists or created in memory if it doesn't exist.''')
    # commandLineParser.add_argument("--verbose", "-v", action='store_true', 
    #                                help="Print helpful info to debug the command line.")
    # commandLineParser.add_argument("command", nargs="*", \
    #                                help='Execute the command that follows "--" and exit.')
    # commandLineParser.add_argument("--gui", "-g", action='store_true', 
    #                                help=\
    #   'Rather than run directy on the present terminal, run it in it\'s own separate window.')
    # namespace:argparse.Namespace = commandLineParser.parse_args()
    #
    # if namespace.verbose:
    #   print("Command line:")
    #   for k,v in vars(namespace).items():
    #     if k == "command":
    #       v = " ".join(v)
    #     print(f'  {k:>10}: {v}')
    
    # get *modelName*: the default model from command line or prefs
    
    
    '''
    :param model:
    :type model: Model | str
    :param context:
    :type context: ModelContext | None
    '''
    if model is None:
      model = cast(str, sn.snPrefs.get("model/defaultModel", storeDefault="temp.xml", storeType=str))
    if isinstance(model, str):
      model = Model(model)
    assert isinstance(model, Model)
        
    # initialize the parser
    if context is None:
      self.context:UIContext = UIContext(model)
    else:
      assert isinstance(context, ModelContext)
      assert context.defaults["model"] == model
      self.context = context
  
    #  if there is an command after "--" on the command line, execute it and exit.
    # command = namespace.command
    # if len(command) > 0:
    #   if namespace.verbose:
    #     printBanner()
    #   result = context.parser.parse(command)
    #   printLists(result, contextModel=context.defaults["model"])
    #   exit()
    
    self.printBanner()
    #context.defaults["model"].isDirty()

  def printBanner(self):
    print(f'{sn.NAME} {sn.VERSION} command line interface under Python {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}') #type: ignore[attr-defined]
    print(f'Using default model "{self.context.defaults["model"]}".') #type: ignore[attr-defined]

  def getPrompt(self):
    '''
    :returns:
    :rtype:
    '''
    return f'{"" if self.context.defaults["model"] is None else ("@"+self.context.defaults["model"].name)}{CARRET} '

  
class SNTerminalWidget(SNAbstractTerminal, TerminalWidget):
  def __init__(self, model:Model|str,
                     master: tk.Widget,
                     context:ModelContext|None=None,
                     registry:TerminalRegistry|None=None,
                     stderrfg:str="red",
                     stdoutfg:str="black",
                     promptfg:str="darkgreen",
                     queryfg:str="violet red",
                     resultfg:str="purple4",
                     queryFont: tuple[str, int, str]|None = None,
                     queryFlashColor: str|None = "red", #DeepSkyBlue2",
                     queryFlashCount: int = 6,
                     queryFlashIntervalMs: int = 150,
                     bg="AntiqueWhite1",
                     fg="darkblue",
                     **kwargs):
    '''
    :param model:
    :type model: Model | str
    :param master:
    :type master: tk.Widget
    :param context:
    :type context: ModelContext | None
    :param registry:
    :type registry: TerminalRegistry | None
    :param stderrfg:
    :type stderrfg: str
    :param stdoutfg:
    :type stdoutfg: str
    :param promptfg:
    :type promptfg: str
    :param queryfg:
    :type queryfg: str
    :param resultfg:
    :type resultfg: str
    :param queryFont:
    :type queryFont: tuple[str, int, str] | None
    :param queryFlashColor:
    :type queryFlashColor: str | None
    :param queryFlashCount:
    :type queryFlashCount: int
    :param queryFlashIntervalMs:
    :type queryFlashIntervalMs: int
    :param bg:
    :type bg:
    :param fg:
    :type fg:
    :param kwargs:
    :type kwargs:
    '''
    SNAbstractTerminal.__init__(self, model, context)
    if "wrap" not in kwargs:
      kwargs["wrap"] = tk.WORD if snPrefs.get("text/wrap", storeDefault=False, storeType=bool) else tk.NONE
    TerminalWidget.__init__(self, master, self.context.parser.parseLine, self.getPrompt, #type: ignore[arg-type]
                            resultToStringFun=lambda obj: printLists(obj, contextModel=self.context.defaults["model"]), 
                            registry=registry, 
                            bg=bg, fg=fg, stderrfg=stderrfg, queryfg=queryfg,
                            stdoutfg=stdoutfg, promptfg=promptfg, resultfg=resultfg,
                            queryFont=queryFont, queryFlashColor=queryFlashColor, queryFlashCount=queryFlashCount, queryFlashIntervalMs=queryFlashIntervalMs,
                            background=snPrefs.get("text/backgroundColor", storeDefault="white", storeType="color"),
                            **kwargs) 


class SNPlainTextTerminal(SNAbstractTerminal, PlainTextTerminal):
  def __init__(self, model:Model|str,
                     context:ModelContext|None=None,
                     stderrfg:str="red",
                     stdoutfg:str="black",
                     promptfg:str="yellow",
                     queryfg:str="green",
                     resultfg:str="blue",
                     **kwargs):
    '''
    :param model:
    :type model: Model | str
    :param context:
    :type context: ModelContext | None
    :param stderrfg:
    :type stderrfg: str
    :param stdoutfg:
    :type stdoutfg: str
    :param promptfg:
    :type promptfg: str
    :param queryfg:
    :type queryfg: str
    :param resultfg:
    :type resultfg: str
    :param kwargs:
    :type kwargs:
    '''
    SNAbstractTerminal.__init__(self, model, context=context)
    PlainTextTerminal.__init__(self, self.context.parser.parseLine, prompt=self.getPrompt, #type: ignore[arg-type]
                              resultToStringFun=lambda obj: printLists(obj, contextModel=self.context.defaults["model"]), 
                              stderrfg=stderrfg, queryfg=queryfg,
                              stdoutfg=stdoutfg, promptfg=promptfg, resultfg=resultfg, **kwargs) 
  
if __name__ == '__main__':

  # interpret the command line
  args:dict = {"suggest_on_error":True} if sys.version_info[0]>=3 and sys.version_info[1]>=14 else dict()
  commandLineParser = argparse.ArgumentParser(**args, description=\
    '''Command line interface for Semantic Nets. Running this program (without
    the "--" argument to execute a subcommand) runs in interactive command environment.''')
  commandLineParser.add_argument("--model", "-m", help=\
    '''Set the default model for all commands. Default is whatever was last 
    used by the program, or if that's not available, "temp.xml" in the 
    current directory if it exists or created in memory if it doesn't exist.''')
  commandLineParser.add_argument("--verbose", "-v", action='store_true', 
                                 help="Print helpful environment info.")
  commandLineParser.add_argument("--debug", "-d", action='store_true', 
                                 help="Print helpful info to debug the command line.")
  commandLineParser.add_argument("command", nargs="*", \
                                 help='Execute the command that follows "--" and exit.')
  commandLineParser.add_argument("--gui", "-g", action='store_true', 
                                 help=\
    'Rather than run directy on the present terminal, run it in it\'s own separate window.')
  namespace:argparse.Namespace = commandLineParser.parse_args()
  
  if namespace.debug:
    print("Command line:")
    for k,v in vars(namespace).items():
      if k == "command":
        v = " ".join(v)
      print(f'  {k:>10}: {v}')
  
  # if there is an command after "--" on the command line, execute it and exit.
  m = getattr(namespace, "model", None)
  if m is None:
    m = snPrefs.get("model/defaultModel", storeDefault="temp.xml", storeType=str)
  if not isinstance(m, (Model,str)):
    raise ValueError(f'No model found on the command line (--model or -m) and no default model found in preferences.')
  model:Model|str = m
  command = namespace.command
  if len(command) > 0:
    if namespace.verbose:
      print(f'{sn.NAME} {sn.VERSION} command line interface under Python {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}') #type: ignore[attr-defined]
      print(f'Using default model {model}.')
    if isinstance(model, str):
      model = Model(model)
    assert isinstance(model, Model), f'Expected a type Model object, got {type(model)}:{model}.' 
    context:UIContext = UIContext(model)
    result = context.parser.parse(command)
    s = printLists(result, contextModel=context.defaults["model"])
    if s is not None:
      print(s)
    exit()
    
  if namespace.gui:
    root = tk.Tk()
    # No registry passed — a single-TerminalWidget app like this one doesn't
    # need to know TerminalRegistry exists; SNTerminalWidget defaults to the
    # module-level singleton in util.terminal.
    terminal = SNTerminalWidget(model, root,
                              bg="AntiqueWhite1", fg="darkblue", #insertbackground="purple",
                              stdoutfg="darkblue", promptfg="darkgreen", resultfg="purple4")
    terminal.pack(fill="both", expand=True)
    root.mainloop()
  else:
    SNPlainTextTerminal(model)

    
  logger.print("bye")
