#################################################################################
# (c) Copyright 2024-2025, Rob Kremer, MIT open source license.                 #
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
"""
Defines:

  - *AppWindow*: the singleton invisible *Tk* window for the app.
  - *LoggingPanedTopWindow*: the child *tk.Toplevel* windows of *AppWindow*.
  - *LoggingPanedWindow*: a *tk.PanedWindow* contained within *LoggingPanedTopWindow*.
  - *CommandEntryWidget*: a *tk.Widget* as part of *LoggingPanedWindow*.

..  inheritance-diagram:: sn.view.graphics.loggingPanedWindow
    :top-classes: tkinter.Tk, tkinter.Toplevel, tkinter.PanedWindow, tkinter.Entry
    :parts: 1
    
---------------
"""

import tkinter as tk
from tkinter.constants import BOTTOM
from typing import Optional, override
import sys

import logging
import urllib
import os
import webbrowser
import requests
from tkinter.filedialog import askopenfilename, asksaveasfilename
from abc import abstractmethod
import weakref
from types import NoneType

import sn
from util.utils import fileToUrl, urlExists, urlToFile
from sn.model.model import Model
#from util.commandParser import CommandParser
from sn.view.textUserInterface import ModelContext #snc, tgparsablecommands
from sn.view.graphics.attributeEditor import getEditedAttrsCommandObj
from util.utils import getSubMenu
from sn.view.graphics.loggingWidget import LoggingWidget
from util.persistence.pRef import PRDb
from sn import snPrefs
#from sn.commandline.tygrac import snCommandParser

logger:sn.SNLogger = sn.getLogger(__name__)

APP_WINDOW = None
"The ultimate Toplevel *Tk* window for the application."

def onAppExit():
  """
  Called on the app exiting. 
  
    - Save each open view and it's geometry in snPrefs as a "views" dict
    - Save the root's geometry in snPrefs as "rootGeometry"
  """
  snPrefs["views"] = dict()
  #TODO: get rid of TGBiewWindow.openViews in favour of scanning Toplevel windows
  logger.debug(f'recent open: {snPrefs["views"]}')
  for v in TGViewWindow.openViews:
    try:
      snPrefs["views"][v.url] = v.canvas.winfo_toplevel().geometry()
    except:
      logger.exception(f'Failed to save view geometry for {v.url}.')
  try: #TODO: Can probably dispense with root geometry now
    import __main__
    root = __main__.root
    assert isinstance(root, AppWindow), f'Expected root to be an AppWindow, got "{root.__class__.__name__}".'
    if root is not None:
      root.update()
      geom = root.winfo_geometry()
      snPrefs["rootGeometry"] = geom
      logger.debug(f'Saved rootGeometry as "{geom}"')
  except:
    logger.exception(f'Prefs.save(): failed to save rootGeometry')
  #snPrefs.save() # done by the Prefs save being registered with the atexit module.
    
class CommandEntryWidget(tk.Entry):
  '''
  A specialized *tk.Entry* widget that take executes tygra commands.
  '''

  def __init__(self, parent,
               loggingWidget:LoggingWidget,
               commandParser:CommandParser,
               promptLabel:tk.Label):
    self.enteredText:tk.StringVar = tk.StringVar()
    super().__init__(parent, textvariable=self.enteredText)
    self.loggingWidget = loggingWidget
    self.commandParser:TygraCommandParser = commandParser
    assert isinstance(self.commandParser, TygraCommandParser)
    self.promptLabel:tk.Label = promptLabel
    self.model:Optional[Model] = None

    self.commandBuffer:list[str] = []
    self.commandBufferIndex:int = -1

    self.bind("<Return>", self.onReturnKey)
    self.bind("<KP_Enter>", self.onReturnKey)
    self.bind("<Up>", self.onUpKey)
    self.bind("<Down>", self.onDownKey)

  def onReturnKey(self, _event):
    if len(self.enteredText.get().strip()) > 0:
      userInput = self.enteredText.get()
      self.loggingWidget.write(userInput, tag="userInput")
      self.commandBuffer.append(userInput)
      try:
        result = self.commandParser.parseLine(userInput)
        # args = self.commandParser.lastArgs()
        # model = args["model"]
        # model = self.commandParser._defaultModel if model is None else Model.getStore(args["model"]) 
        tygrac.printLists(result, contextModel=self.model)
      except SyntaxError as ex:
        logger.print(str(ex), file=sys.stderr)
      # except SystemExit as ex:
      #   if str(ex) == "tygra":
      #     break
      except Exception as ex:
        logger.exception('While attempt the execute command "%s"', userInput)
      if hasattr(self.commandParser, "getPrompt"):
        self.promptLabel.config(text=self.commandParser.getPrompt())
    self.enteredText.set("")
    self.commandBufferIndex = len(self.commandBuffer) - 1

  def onUpKey(self, _event):
    if self.commandBufferIndex < 0:
      return
    self.enteredText.set(self.commandBuffer[self.commandBufferIndex])
    self.commandBufferIndex -= 1

  def onDownKey(self, _event):
    if self.commandBufferIndex + 1 == len(self.commandBuffer):
      self.enteredText.set("")
      return
    if self.commandBufferIndex + 1 > len(self.commandBuffer):
      return
    self.commandBufferIndex += 1
    self.enteredText.set(self.commandBuffer[self.commandBufferIndex])


class LoggingPanedTopWindow(tk.Toplevel):
  """
  A simple *tk.Toplevel* window to contain a *TGViewWindow :> LoggingPanedWindow*.
  """
  def __init__(self, master, slave):
    assert isinstance(slave, TGViewWindow)
    super().__init__(master)
    self._slave:weakref[TGViewWindow] = weakref.ref(slave)
    
  @property
  def slave(self): 
    '''
    :return: The *TGViewWindow* (<:LoggingPanedWindow) pane of this *tk.TopLevel*
    '''
    return self._slave()
  
  # @override
  # def destroy(self)->None:
  #   #self.slave.destroy()
  #   #tk.Toplevel.destroy(self)
  #   pass


# class LoggingPanedRootWindow(tk.Tk):
#   def __init__(self, slave):
#     assert isinstance(slave, AppWindow)
#     super().__init__()
#     self._slave:AppWindow = weakref.ref(slave)
#
#   @property
#   def slave(self): 
#     '''
#     :return: The *AppWindow* (<:LoggingPanedWindow) pane of this *tk.TopLevel*
#     '''
#     return self._slave()
#
#   # @override
#   # def destroy(self)->None:
#   #   for v in self.winfo_children():
#   #     if isinstance(v, LoggingPanedTopWindow):
#   #       v.destroy()
#   #   self.slave.destroy()
#   #   tk.Tk.destroy(self)


class LoggingPanedWindow(tk.PanedWindow):
  """
  A (tkinter.PanedWindow) with two panes: above, and application widget according the
  *frame* parameter of the constructor, and below, a disabled text widget which is used
  by this class's various service methods to display messages such as logging info:

    +-------------------------+
    |                         |
    |         appFame         |
    |                         |
    +-------------------------+
    |       loggingWidget     |
    +-+-----------------------+
    |>|  commandEntryWidget   |
    +-+-----------------------+
    
     ^promptLabel
  """

  # def __init__(self, parent, frame=lambda p: tk.Frame(p),
  #              fixedAppFrame:bool=False,
  #              commandParser:CommandParser=None,
  #              topType=lambda p, s: LoggingPanedTopWindow(master=p, slave=s),
  #              **kwargs):
  def __init__(self, parent,
               fixedAppFrame:bool=False,
               commandParser:CommandParser=None,
               **kwargs):
    r"""
    :param parent: The parent *AppWindow*.
    :param fixedAppFrame: [bool, default:False] Specifies whether the application *frame*
      is fixed-size or stretchable.
    :param commandParser: [CommandParser , default: an new *TygraCommandParser()* ] User input
      from the *commmandEntryWidget* is sent to this parser.
    :param \*\*kwargs: An arguments *dict* to passed to the *tk.PanedWindow* constructor.
      The following arguments are defaulted if not present:
      
        - "orient" default = tk.VERTICAL
        - "showhandle" default = False
        - "sashwidth" default = 3
        - "bd" default = 4
        - "bg" default = "grey"
        - "borderwidth" default = 0
        
    """
    from sn.commandline.tygrac import snCommandParser
    
    assert isinstance(parent, AppWindow), f'Expected AppWindow or None, but got "{parent}:{parent.__class__.__name__}"'
    assert isinstance(fixedAppFrame, bool)
    assert isinstance(commandParser, (TygraCommandParser, NoneType))

    # fix up kwargs to contain the necessary defaults and create the PanedWindow (super).
    if "orient" not in kwargs: kwargs["orient"] = tk.VERTICAL
    if "showhandle" not in kwargs: kwargs["showhandle"] = False
    if "sashwidth" not in kwargs: kwargs["sashwidth"] = 6
    if "bd" not in kwargs: kwargs["bd"] = 4
    if "bg" not in kwargs: kwargs["bg"] = "grey"
    if "borderwidth" not in kwargs: kwargs["borderwidth"] = 0

    # set up tkRoot and tkTop
    self._tkRoot = None if parent is None else weakref.ref(parent)#.master)
    'The (unique and always existent) app window *weakref*'
    self._tkTop = weakref.ref(self.makeTopWindow(None if self._tkRoot is None else self.tkRoot))
    'The top window *wearkref*, NOT the app window'
    assert isinstance(self.tkRoot, AppWindow)
    
    # super constructor
    super().__init__(self.tkTop, **kwargs)

    self.tkTop.option_add('*tearOff', tk.FALSE)
    self.tkTop.protocol("WM_DELETE_WINDOW", self.onClosing)
    self.tkTop.bind("<FocusIn>", self.onFocusIn)
    self.tkTop.bind("<Enter>", self.onEnter)

    # set up the textDisplayFrame (contains the *loggingWidget* , *commandEntryWidget* and *promptLabel*
    self.textDisplayFrame = tk.Frame(self)
    self.textDisplayFrame.pack(fill=tk.NONE, side=BOTTOM, expand=False)
    stretch = 'always' if fixedAppFrame else 'never'
    sticky = 'news' if fixedAppFrame else 'new'
    self.add(self.textDisplayFrame, stretch=stretch, sticky=sticky)
    self.paneconfigure(self.textDisplayFrame, stretch=stretch)

    # set up the *loggingWidget*
    self.loggingWidget = LoggingWidget(self.textDisplayFrame, state='disabled', wrap='none', width=80, height=6, borderwidth=0)
    'The text logging display, automatically capturing output from the sysout, syserr, and the logging package.'
    self.loggingWidget.pack(fill=tk.BOTH, expand=True)
    loggingWidget.loggingWidget = self.loggingWidget

    #deferred until after the window is created so messages from the load can appear in the proper window
    # set up commandParser
    if commandParser is None:
      commandParser = TygraCommandParser(loadCommandModules=[])
    assert isinstance(commandParser, TygraCommandParser)
    self.commandParser:TygraCommandParser = commandParser
    'The command parser used by *commandEntryWidget*'
    self.commandParser.loadModule(tgparsablecommands, commandFilter=lambda func: func.__name__.endswith("Command") or func.__name__.endswith("Query"))
    
    # set up the *commandEntryWidget*
    inputframe = tk.Frame(self.textDisplayFrame)
    inputframe.pack(fill=tk.BOTH, side=tk.BOTTOM, expand=False)
    # prompt = tygrac.CARRET+" "
    # if hasattr(self.commandParser, "getPrompt"):
    #   prompt = self.commandParser.getPrompt()
    self.promptLabel = tk.Label(inputframe, text=tygrac.CARRET+" ")
    self.promptLabel.pack(fill=tk.NONE, side=tk.LEFT, expand=False)
    self.commandEntryWidget = CommandEntryWidget(inputframe, self.loggingWidget, self.commandParser, self.promptLabel)
    self.commandEntryWidget.pack(fill=tk.BOTH, side=tk.RIGHT, expand=True)

    # set up the *appFrame*
    self.fixedAppFrame:bool = fixedAppFrame
    '[bool] *True* indicates *self.appFrame* is fixed size.'
    self.appFrame = None
    'The application Frame. Usually the "view" or graphics display of the model.'
    self.setAppFrame()
    
    self.pack(fill=tk.BOTH, expand=True)

    # menus
    self.tkTop.menu = self.makeMenu()
    self.tkTop.config(menu=self.tkTop.menu)

  @property # weak ref property
  def tkTop(self):
    "The *tk.Toplevel* window frame (referent of the weakref *_tkTop*)." 
    return self._tkTop()
    
  @property # weak ref property
  def tkRoot(self): 
    "The *tk.Tk* window frame, which must be an *AppWindow* object (referent of the weakref *_tkRoot*)." 
    return self._tkRoot()  
    
  @property
  def doList(self):
    return self.commandParser.doList
    
  @override
  def destroy(self)->None:
    "Call *tkRoot.onChildTopWindowClosing()* before passing to *super*."
    if self.tkRoot is not None:
      self.tkRoot.onChildTopWindowClosing(self)
    super().destroy()
      
  @abstractmethod
  def makeTopWindow(self, root) -> LoggingPanedTopWindow:
    "Abstract class. Create a *tk.Toplevel* frame for this window"
    assert False
    
  def makeMenu(self) -> tk.Menu:
    "Construct and return the menubar menu for the app. This method does NOT add the menu to the app menu bar."
    menubar:tk.Menu = self.tkRoot.makeMenu() #tk.Menu(self)
    filemenu = getSubMenu(menubar, "File")
    filemenu.add_separator()
    filemenu.add_command(label="Save", accelerator="cmd-s", command=self.onSaveFile)
    filemenu.add_command(label="Save as...", command=lambda: self.onSaveFile(askForFileName=True))
    
    editmenu = tk.Menu()
    menubar.insert_cascade(2, label="Edit", menu=editmenu)
    editmenu.add_command(label="Undo", accelerator="cmd-z", command=self.doList.undo)
    editmenu.add_command(label="Redo", accelerator="shift-cmd-z", command=self.doList.redo)
    
    return menubar

  def setAppFrame(self):
    if self.appFrame is not None:
      self.forget(self.appFrame)
      self.appFrame.destroy()

    self.appFrame = tk.Frame(self)
    self.appFrame.pack(fill=tk.BOTH if self.fixedAppFrame else tk.BOTH,
                        side=tk.TOP,
                        expand=False if self.fixedAppFrame else True)

    stretch = 'never' if self.fixedAppFrame else 'always'
    sticky = 'new' if self.fixedAppFrame else 'news'
    self.add(self.appFrame, before=self.textDisplayFrame, stretch=stretch, sticky=sticky)  # 'always', 'first', 'last', 'middle', and 'never'.
    self.paneconfigure(self.appFrame, stretch=stretch)

  def setPrompt(self, text:str):
    self.promptLabel.config(text=text)

  ### tkTop interface methods ##################################################

  def onFocusIn(self, _event):
    loggingWidget.loggingWidget = self.loggingWidget
    #logger.print(f'Got focus at {self.tkTop.title()}.')
    
  def onEnter(self, _event): # because <FocusIn> doesn't seem to always work.
    loggingWidget.loggingWidget = self.loggingWidget

  def onClosing(self):
    """
    :param quitting: if True and this is the last file window to be closed,
      calls *self.prefs.save()* to save the preferences and the open
      window (a geometry info); if False calls *self.onSaveFile()*.
      
    The "close" button on the file window has been chosen, so (user optionally)
    save the file, and if this the last window standing, then save the
    preferences too.
    """
    #global APP_WINDOW
    # if len(TygraContainer._instances) < 2:
    #   self.prefs.save()
    # else:
    #   self.saveFile()
    # self.destroy()
    # if isinstance(self.appFrame, PRDb):
    #   if self.appFrame.dirty:
    #     self.appFrame.askSaveFile(self.appFrame)
    #raise NotImplementedError("LoggingPainedWindow.onClosing()")
    # if self.tkRoot is not None:
    #   self.tkRoot.onChildTopWindowClosing(self)
    self.tkTop.destroy()
    #APP_WINDOW.focus_force()

  def onSaveFile(self):
    raise NotImplementedError("LoggingPainedWindow.onSaveFile()")


class TGViewWindow(LoggingPanedWindow):
  """
  A *LoggingPanedWindow* containing a *SNView* in its appFrame. 
  """

  openViews:list = list()
  "list of SNView widgets currently open"

  def __init__(self, parent, view):
    """
    :param parent: A parent *AppWindow*
    :param view: [*SNView*] The view in the window
    """
    from sn.view.graphics.view import SNView

    assert isinstance(view, SNView)
    assert isinstance(parent, AppWindow), f'TGViewWindow(): Expanded parent of AppWindow, got {parent.__class__.__name__}'

    #tkTop = tk.Tk()
    #self.tkRoot = parent
    super().__init__(parent)
    #commandParser=TygraCommandParser(doList=self.doList, loadCommandModules=[]))

    self.view:SNView = view
    #self.view.makeFrame(self)
    self.view.doList = self.doList

    self.openViews.append(self.view)
    
    model = self.view.model

    self.commandParser.defaultModel = model
    self.setPrompt("@" + model.name + tygrac.CARRET)
    self.commandEntryWidget.model = model

    self.tkTop.geometry(snPrefs["views"][self.view.url] \
                   if "views" in snPrefs and self.view.url in snPrefs["views"] \
                   else "800x900")
    self.setWindowTitle()
    self.tkTop.focus_force()

    # self.view._instantiate()
    # if len(self.view._objects) == 0:
    #   VNode(self.view, model[1], "Hexagon", 10, 10, 50, 30)
      
  @override
  def destroy(self)->None:
    "Remove the *view* from the class list *openViews* before passing to *view* and *super*."
    if self.view in self.openViews: 
      self.openViews.remove(self.view)
    self.view.destroy()
    super().destroy()

  def setWindowTitle(self):
    self.tkTop.title(f'tygra3: view "{self.view.name}" of model "{self.view.model.name}"')
    
  @override
  def makeTopWindow(self, root) -> LoggingPanedTopWindow: #tk.Tk or tk.Toplevel
    assert isinstance(root, AppWindow)#LoggingPanedRootWindow)
    return LoggingPanedTopWindow(root, self)

  @override
  def onSaveFile(self, askForFileName=False):
    self.view.saveFile(askForFileName=askForFileName)

          
class InvisibleAppWindow(tk.Tk):
  """
  A *tk.Tk* window that never shows itself, but allows a menubar.
  
  :note: For this to work naturally, all child *tk.Toplevel* windows should notify
    this window that they area closing using the *OnChildTopWindowClosing()* method.
  """
  def __init__(self):
    super().__init__()
    
    self.bind("<FocusIn>", self.onFocusIn)   # Disable the menubar's Window submenu 
    self.bind("<FocusOut>", self.onFocusOut) # Enable the menubar's Window submenu 

    # make the window invisible
    self.geometry("0x0+0+0") # make this a 0x0 window tucked away in the top left corner.
    #self.overrideredirect(True) # Using overridedirect will disable the menubar
    self.attributes("-alpha", 0.0)
    self.focus_force()
    
  def onFocusIn(self, _event):
    self.geometry("0x0+0+0") # make this a 0x0 window tucked away in the top left corner.

  def onFocusOut(self, _event):
    self.geometry("0x0+0+0") # make this a 0x0 window tucked away in the top left corner.

  def onChildTopWindowClosing(self, _childWindow:tk.Toplevel):
    """
    Handle a child window notifying this app that it is closing.
    
      - Force focus on the app window, which displays the app menubar.
    """
    self.focus_force()
    
    
class AppWindow(InvisibleAppWindow):#LoggingPanedWindow):
  def __init__(self):
    global APP_WINDOW
    assert APP_WINDOW is None, "The AppWindow should be a singleton."
    
    #from sn.commandline.tygrac import snCommandParser

    super().__init__()
    #                commandParser=TygraCommandParser(doList=self.doList, loadCommandModules=[]),
    #deferred until after the window is created so messages from the load can appear in the proper window
    #self.commandParser.loadModule(tgparsablecommands, commandFilter=lambda func: func.__name__.endswith("Command") or func.__name__.endswith("Query"))

    self.config(menu=self.makeMenu())
    self.createcommand('tk::mac::ShowPreferences', self.onShowPreferencesDialog)
    self.createcommand('tk::mac::ShowHelp', self.onShowHelp)
    self.createcommand('::tk::mac::Quit', self.onQuit)
    #self.protocol("WM_DELETE_WINDOW", self.onClosing)
    self.menubar.delete("Window")
    
    
    self.title(f'{sn.NAME}, v{sn.VERSION}') # Not really needed since we don't show the window

    # url = snPrefs.get("defaultModel", None)
    # if url is not None:
    #   try:
    #     model = Model.getStore(url)
    #     self.commandParser.defaultModel = model
    #     self.setPrompt("@" + self.commandParser.defaultModel.name + tygrac.CARRET)
    #   except:
    #     self.commandParser.defaultModel = None
    #     self.setPrompt(tygrac.CARRET)
      
    self.helpDirURL = fileToUrl("/".join(str(sn.__file__).split("/")[:-1])+"/help")
    self.helpURL = self.helpDirURL+"/index.html"
    
    APP_WINDOW = self

  @override
  def destroy(self)->None:
    tk.Tk.destroy(self)

  def makeMenu(self) -> tk.Menu:
    "Construct and return the menubar menu for the app. This method does NOT add the menu to the app menu bar."
    self.menubar = tk.Menu(self)

    appmenu = tk.Menu(self.menubar, name="apple")
    appmenu.add_command(label="About...", command=self.onShowAbout)
    appmenu.add_separator()
    self.menubar.add_cascade(menu=appmenu)

    # file menu
    filemenu = tk.Menu(self.menubar)
    filemenu.add_command(label="New Model", command=self.onNewModel)  # want to refresh
    filemenu.add_command(label="New View...", command=self.onNewView)  # want to refresh
    filemenu.add_command(label="Open...", command=self.onOpenFile)    # filemenu.add_command(label="Save...", command=self.saveFile)
    self.menubar.add_cascade(label="File", menu=filemenu)

    # MacOS automatically fills this in for us...
    windowmenu = tk.Menu(self.menubar, name='window')
    self.menubar.add_cascade(menu=windowmenu, label='Window')

    helpmenu = tk.Menu(self.menubar, name="help")  # on Mac, the "Python help" menu item automatically shows up.
    self.menubar.add_cascade(label="Help", menu=helpmenu)

    return self.menubar

  def onQuit(self):
    """
    The "quit application" menu item has been chosen. Saves the prefs (which
    itself uses the "save file" dialog to save all file data) the calls the
    *onClosing()* method on each of the files with the *quitting* flag to
    prevent the *onClosing()* methods from using the "save file" dialogs again.
    """
    onAppExit()
    self.destroy()
    sys.exit(0) #TODO: This shouldn't be necessary: self.destroy() should have existed the app, but it didn't.
    
  # @override  
  # def onClosing(self):
  #   """
  #   The window has been closed with its CLOSE button. Since this is currently
  #   a hidden window, this should never actually happen.
  #   """
  #   onAppExit()
  #   super().onClosing()

  def onShowAbout(self):
    """
    Show the about information.
    """
    tk.messagebox.showinfo(
      parent=self,
      icon="info",
      title=f'About App {sn.NAME}',
      message=f'''{sn.NAME} app, version {sn.VERSION}
              by Rob Kremer''',
      )

  # TODO: Implement application help
  def onShowHelp(self, relPagePath:str="index.html"):
    """
    :param relPagePath: the path, relative to the help root directory, of the help page requested. [default: "index.html"]
    
    Show help info for the application.
    """
    # Can't use logger here (because it's in a protocol???)
    try:
      url = urllib.parse.urljoin(self.helpURL, relPagePath)
      if str(url).startswith("file:///"):
        if os.path.exists(url[7:].replace("%20", " ")):
          webbrowser.open(url, new=0, autoraise=True)
        else:
          #self.logger.write(f'Can\'t find file {url[7:]}.', level="error")
          logger.error(f'Can\'t find file {url[7:]}.')
      else:
        r = requests.head(url)
        if r.status_code == 200:
          webbrowser.open(url, new=0, autoraise=True)
        else:
          #self.logger.write(f'Can\'t find URL {url}: Status code {r.status_code}.', level="error")
          logger.error(f'Can\'t find URL {url}: Status code {r.status_code}.')
    except Exception as ex:
      raise ex
  def onShowPreferencesDialog(self):
    """
    Bring up the preferences dialog.
    """
    command = getEditedAttrsCommandObj(self, snPrefs, title="SN Preferences")
    if command is not None:
      command.do()

  def onNewModel(self):
    from sn.view.graphics.view import SNView
    filename = asksaveasfilename(filetypes=[("SN model files", "*.xml")], 
                                 defaultextension=".xml", 
                                 title='Create a new SN model',
                                 confirmoverwrite=True)
    if filename == "": # user abort
      return
    url = fileToUrl(filename)
    if urlExists(url):
      os.remove(filename)
    
    model:Model = Model(url)
    model._instantiate()
    model.write()
    view:SNView = SNView(model=model, root=self)
    
    # display the model
    view._defaultPopulate()
  
  def onNewView(self):
    from sn.view.graphics.view import SNView
    filename = askopenfilename(filetypes=[("SN model file", "*.xml")], 
                               title='Create a new view on model ...')
    if filename == "": # user abort
      return
    url = fileToUrl(filename)
    model:Model = None
    if not filename.endswith(".tgm") or not urlExists(url):
      logger.error("Expected a valid .tgm file.")
      return
    model = Model.getDB(url)
    
    # find a new none-existant filename
    filename = filename[:-4] #take off the suffix
    i = 1
    f = f'{filename}-{str(i)}.tgv'
    while os.path.exists(f) or fileToUrl(f) in PRDb._urlCache:
      i += 1
      f = f'{filename}-{str(i)}.tgv'
    filename = f
    url = fileToUrl(filename) # make the URL of new view
    view:SNView = SNView(model=model, url=url, root=self)
    #view.makeViewObjectForGraphObject(view.model[1])
    view._defaultPopulate()
  
  def onOpenFile(self):
    from sn.view.graphics.view import SNView
    filename = askopenfilename(filetypes=[("SN model file", "*.xml"), ("SN view file", "*.xml")], 
                               title='Open a SN model or view file')
    if filename == "": # user abort
      return
    url = fileToUrl(filename)
    model:Model = None
    if filename.endswith(".tgm"):
      model:Model = Model.getStore(url)
      model._instantiate()
      url = url[:-4]+".tgv" # make the URL of the default view
      filename = filename[:-5]+".tgv" # make the file of the default view
    if url.endswith(".tgv"): # create a view, 2 cases: either because we just created a model or the user specified a .tgv file.
      if urlExists(url): # we are opening an explicit view
        view:SNView = SNView(url=url, root=self)
      else: # we are opening the default view for a chosen model
        view:SNView = SNView(model=model, root=self)
        #view.makeViewObjectForGraphObject(view.model[1])
        view._defaultPopulate()
      return
    else:
      logger.error("Expected a .tgm or a .tgv file.")
      return
  
