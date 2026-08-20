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
  .. inheritance-diagram::
        LoggingWidgetHandler
        StdoutRedirector
        LoggingWidget
      :parts: 3
      :private-bases:
      :top-classes: util.commandParser.ParsableCommandDef, util.commandParser.ParsableQuery

Created on Jan 21, 2025

.. codeauthor:: Rob Kremer <robkremer@me.com>

---------------
'''

import tkinter as tk
from typing import Optional, Union, List, override, Self
from io import TextIOWrapper
import sys
import os
import traceback
from util.utils import play, getCallerIdInfoStr
from types import NoneType

import logging
import sn
#from sn.commandline import snc

logger:sn.SNLogger = sn.getLogger(__name__)

loggingWidget = None

class LoggingWidgetHandler(logging.Handler):
  '''
  Handler for logging package messages
  '''
  def __init__(self, level=logging.NOTSET):
    super().__init__(level=level)
    #self.loggingWidget = None
    
  @override
  def emit(self, record:logging.LogRecord)->None:
   try:
    global loggingWidget
    if loggingWidget is None:
      return
    rlevel = record.levelname # 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    msg = record.getMessage()
    level = 0
    if   rlevel in ['CRITICAL', 'ERROR']: level = -1
    elif rlevel == 'WARNING'            : level =  1  
    elif rlevel == 'INFO'               : level =  2
    elif rlevel == 'DEBUG'              : level =  3  
    ex = None
    if record.exc_info is not None:
      ex = record
    loggingWidget.write(msg, level=level, exception=ex)
   except:
     pass
    
  
# deal with capturing logging messages
loggingHandler = LoggingWidgetHandler(level=logging.DEBUG)
logger.addHandler(loggingHandler)
    

class StdoutRedirector(object):
  def __init__(self, tag, stdOutput):
    self.tag = tag
    self.stdOutput = stdOutput

  def write(self, string:str):
   try:
    string = string.rstrip()
    if len(string) == 0: return
    self.stdOutput.write(string+"\n")
    if loggingWidget is not None:
      loggingWidget._prep()
      loggingWidget.insert('end', string, self.tag)
      loggingWidget._finish()
   except:
    pass

  def flush(self):
    pass


class LoggingWidget(tk.Text):
  '''
  A terminal-like *tk.Text* widget customized to handle logger and sysout and syserr
  messages. Various types of output are captured and font-customized using tk tags. 
  '''
  
  def __init__(self, parent, state='disabled', wrap='none', width=80, height=4, borderwidth=0,
               maxLines:int=512, visibleLines:int=2, logFiles:List[str]=None, 
               useStderr:bool=True, maxLevel:int=3, 
               captureStdOutput:bool=True, 
               soundError:Optional[str]='/System/Library/Sounds/Sosumi.aiff'):
    '''
    :param maxLines: The maximum number of lines the text widget frame will maintain.
            User 0 for "infinite" [default: 24]
    :param visibleLines: the number of lines the text widget will initially display.
            [default: 2]
    :param logFiles: A open-for-write file object (or objects), like sys.stdout, 
            to write messages to. May be an open-file object, or a list of
            open-file objects. [default: None]
    :param stderr:  bool. If *True*, and sys.stdout is in *logFiles*, then sys.stderr 
            will be used for error-level messages. [default: True]
    :param maxLevel: The maximum level to print. Cannot be less than 0 (normal)
    :param captureStdOutput: Capture any output to *sys.stdout* and *sys.stderr* and
            display it before forwarding it back to *sys.stdout* and *sys.stderr*.
    :param soundError: An sound file to play when an error level message occurs.
    '''
    super().__init__(parent, state=state, wrap=wrap, width=width, height=height, borderwidth=borderwidth)
    
    self.maxLines = maxLines
    self.visibleLines = visibleLines
    self.useStderr = useStderr
    self.maxLevel = 3
    self.setMaxLevel(maxLevel)
    self.soundError = soundError
    self.lastTraceback = "<No traceback recorded>"
    self.tracebackCount = 0
    
    #self.pack(fill=tk.BOTH, side=tk.TOP, expand=True)
    #self.pack(fill=tk.BOTH, expand=True)
    self.tag_config("traceback"    , foreground="purple", font="Courier 0")
    self.tag_config("exception"    , foreground="purple", font=self.cget("font")+" 0 bold")
    self.tag_config("error"        , foreground="red")
    self.tag_config("normal"       , foreground="black")
    self.tag_config("warning"      , foreground="brown")
    self.tag_config("informational", foreground="grey")
    self.tag_config("info"         , foreground="grey")
    self.tag_config("debug"        , foreground="green")
    self.tag_config("errorTag"     , foreground="red"  , font=self.cget("font")+" 0 bold")
    self.tag_config("warningTag"   , foreground="brown", font=self.cget("font")+" 0 bold")
    self.tag_config("stdout"       , foreground="black", font="Courier 0 italic")
    self.tag_config("stderr"       , foreground="red"  , font="Courier 0 bold italic")
    self.tag_config("userInput"    , foreground="blue" , font="Courier 0 italic")
  
    # deal with capturing stdout and stderr (param captureStdOutput)
    self.realStdout = sys.stdout
    self.realStderr = sys.stderr
    if captureStdOutput and sys.stdout is sys.__stdout__:
      sys.stdout = StdoutRedirector("stdout", self.realStdout)
      sys.stderr = StdoutRedirector("stderr", self.realStderr)
      
    # deal with log files
    if logFiles is None:
      self.logFiles = []
    else:
      if not isinstance(logFiles, list): self.logFiles = [logFiles]
    # check type and writability of items in the logFiles parameter
    bad = []
    for f in self.logFiles:
      if not isinstance(f, TextIOWrapper):
        if not isinstance(f, StdoutRedirector):
          self.write(f'Unaccepted type "{type(f).__name__}" for "logFiles" argument.', level=-1)
        bad.append(f)
        continue
      if not f.writable():
        self.write(f'Got a file in "logFiles" argument that does not appear to be writable.', level=-1)
        bad.append(f)
    for f in bad: self.logFiles.remove(f)
    
  @property
  def maxLevelStr(self):
    return LoggingWidget.levelToTag[self.maxLevel]
  
  @maxLevelStr.setter
  def maxLevelStr(self, val:str):
    self.maxLevel = self._getLevel(val)

  def delete(self):
    sys.stdout = self.realStdout
    sys.stderr = self.realStderr
    for i in range(len(self.logFiles)):
      self.logFiles[i] = None
    self.logFiles = None
    
  levelToTag = {  -1: "error",
           0: "normal",
           1: "warning",
           2: "informational",
           3: "debug"}

  @staticmethod
  def _getLevel(obj):
    if isinstance(obj, int): 
      if obj < 0:  return -1
      if obj > 3:  return 3
      return obj
    if isinstance(obj, str):
      obj = obj.lower()
      n = len(obj)
      if n < 1: n = 1
      if obj == "error"        [0:n]: return -1
      if obj == "normal"       [0:n]: return 0
      if obj == "warning"      [0:n]: return 1
      if obj == "informational"[0:n]: return 2
      if obj == "debug"        [0:n]: return 3
    return 0
    
  def setMaxLevel(self, level:Union[str,int]=2) -> int:
    """
    Sets the maximum error level to print and returns the previous level. Error and
    normal messages are always printed, so *maxLevel* cannot be less than 1. """
    ret = self.maxLevel
    level = self._getLevel(level)
    if level < 0:
      self.write("Cannot set level at < 0 (normal). Using 0.", level="error")
      level = 0
    self.maxLevel = level
    return ret
    
  def _writeTraceback(self, event, tbString=None):
    self._prep()
    self.insert('end', str(tbString), ('traceback',))    
    self._finish()

  def _prep(self):
    numlines = int(self.index('end - 1 line').split('.')[0])
    self['state'] = 'normal'
    if numlines >= self.maxLines:
      super().delete('1.0', f'{self.maxLines-numlines+2}.0')
    if self.index('end-1c')!='1.0':
      self.insert('end', '\n')
      
  def _finish(self):
    self.see('end -1 lines')
    self['state'] = 'disabled'
    top = self.winfo_toplevel()
    top.update_idletasks()
#    top.update()    
        
  def write(self, msg, level:Union[str,int]=0, 
            exception:Union[Exception,logging.LogRecord,NoneType]=None, 
            tag:Union[str,list[str],NoneType]=None):
    """
    :param msg: The message to write to the logging window (and anything else this
        object might be writing to).
    :param level: A severity level for this message which may be displayed as a font
        color or font change. May be a string ("error" "normal", "warning", "informational", "debug") or
        an *int* (correspondingly -1 (or -ve), 0, 1, 2, 3).
    :param tag: [str or list[str]] A Text-tag to be applied to the output. If *tag* occurs, it will
        be applied after (takes precedence over) any level-based tags. Currently, the
        only useful tag is "userInput" which prints in blue Courier italic.
    """
    level = self._getLevel(level) # level is now guaranteed to be an int
    if level > self.maxLevel:
      return
    assert isinstance(exception, (NoneType, logging.LogRecord, Exception)), f"got {exception.__class__.__name__}"
    # make sure tag is a list[str]
    if tag is not None and isinstance(tag, str):
      tag = [tag]
      
    debug = tygra.tygraPrefs.get("debug", False)
      
    self._prep()
    
    if   level == -1: 
      self.insert('end', "ERROR: ", ("errorTag",))
      prefix = "***ERROR***: "
      if self.soundError is not None:
        play(self.soundError)
    elif level ==  1:
      self.insert('end', "WARNING: ", ("warningTag",))
      prefix = "*WARNING*: "
    elif level ==  3:
      self.insert('end', "DEBUG: ", ("debug",))
      prefix = "DEBUG: "
    elif tag is not None and "userInput" in tag:
      self.insert('end', tygrac.CARRET+" ", ("userInput",))
      prefix = tygrac.CARRET+" "
    else:
      prefix = ""
      
    method = "" if level in [0,2] and exception is None else (getCallerIdInfoStr(stack=2)+": ")
    
    output = f'{prefix}{msg}' # *output* is the version of the msg that goes to the file.
    
    # format the exception if applicable
    exc_tb = None
    if exception is not None:
      exc_type, exc_obj, exc_tb = exception.exc_info if isinstance(exception, logging.LogRecord) else sys.exc_info() 
      if isinstance(exception, logging.LogRecord):
        exception = exc_obj
      fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1] if exc_tb is not None else "<unknown>" 
      lineno = exc_tb.tb_lineno if exc_tb is not None else "<unknown>"
      self.lastTraceback = traceback.format_exc()
      m = f'\n  Exception {type(exception).__name__}: {exception}, in file {fname}, line {lineno}.'
      output += m
      msg += m

    # display the actual message
    tags = [LoggingWidget.levelToTag[level]]
    if exception is not None:
      tags.append("exception")
      tags = ["exception"]
    if tag is not None:
      tags += tag
    self.insert('end', f'{msg}', tags)

    # add the "traceback" button if applicable
    #TODO: make the traceback button replace itself with the actual traceback, rather than just appending the traceback.
    if exception is not None and exc_tb is not None:
      try:
        self.tracebackCount += 1
        tracebackTag = "tracebackLink"+str(self.tracebackCount)
        tracebackCallback = lambda e, tbString=self.lastTraceback: self._writeTraceback(e, tbString)
        self.tag_config(tracebackTag, foreground="blue")
        self.tag_bind(tracebackTag, "<Button-1>", tracebackCallback)
        self.insert('end', ' [traceback]')
        self.tag_add(tracebackTag, "end-11c", "end-2c")
      except:
        pass
      
    # add the "in <method>" line if applicable
    if len(method) > 0 and debug:
      indent = "    " if exception is not None else "  "
      self.insert('end', f'\n{indent}in {method}', (LoggingWidget.levelToTag[level],))

    self._finish()
        
    # write out to any logfiles
    for f in self.logFiles:
      if (f is sys.stdout or f is self.realStdout) and level<0:
        f = self.realStderr
      indent = "    " if exception is not None else "  "
      if len(method) > 0:
        output += f'\n{indent}in {method}'
      f.write(f'{output}\n')
      if exception is not None:
        f.write(f'{self.lastTraceback}\n')

