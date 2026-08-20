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
Created on Aug 17, 2026

@author: robkremer
'''
from __future__ import annotations
import sn
import tkinter as tk
from typing import Optional
from sn.view.textUserInterface import SNTerminalWidget
from tkinter import ttk
from sn import snPrefs
from util.attribute import Attribute, VAR_DEFAULTED
from util.utils import expandRect

logger:sn.SNLogger = sn.getLogger(__name__)

class Application(tk.Tk):
  """The invisible root Tk window and manages one or more Toplevel windows.

  :param appName: Name used for the hidden root window's title (mostly cosmetic,
    since it's never shown).
  :type appName: str
  """

  def __init__(self, appName: str = "app") -> None:
    super().__init__()
    self.withdraw()          # hide before it can ever flash visible
    self.title(appName)
    self.defaultChildLocation:tuple[int,int] = (20,60)

    self.windows: dict[str, tk.Toplevel] = {}

    # If every hosted window is closed, there's nothing left to interact with —
    # decide here whether that should end the app.
    self.protocol("WM_DELETE_WINDOW", self._noOp)  # root itself is never closed by the user

  def _noOp(self) -> None:
    """Root window has no close button the user can reach, but guard anyway.

    :rtype: None
    """
    pass

  def openWindow(self, name: str, title: str = "") -> tk.Toplevel:
    """Create and show a new Toplevel window hosted under the invisible root.

    :param name: A key to refer to this window by (e.g. for closing it later).
    :type name: str
    :param title: Window title. Defaults to name if not given.
    :type title: str
    :returns: The newly created Toplevel window.
    :rtype: tk.Toplevel
    """
    if name in self.windows:
      self.windows[name].lift()
      return self.windows[name]

    window:AppWindow = AppWindow(self, name, title, geometry=f'300x400+{self.defaultChildLocation[0]}+{self.defaultChildLocation[1]}')
    self.defaultChildLocation = (self.defaultChildLocation[0]+40, self.defaultChildLocation[1]+40)
    self.windows[name] = window
    return window

  def _closeWindow(self, name: str) -> None:
    """Close a specific hosted window and check whether the app should exit.

    :param name: The window's key, as passed to openWindow.
    :type name: str
    :rtype: None
    """
    window = self.windows.pop(name, None)
    if window is not None:
      window.destroy()

    if not self.windows:
      self.quit()  # or: leave the (invisible) root running headless, your choice

  def quit(self) -> None:
    """Tear down the entire application, including the hidden root.

    :rtype: None
    """
    self.destroy()

  def run(self) -> None:
    """Start the Tk event loop.

    :rtype: None
    """
    self.mainloop()


class AppWindow(tk.Toplevel):
  def __init__(self, tkdottk:tk.Tk, name:str, title:str="", geometry:str="300x400+20+20", **kwargs):
    super().__init__(tkdottk, **kwargs)
    self.geometry(geometry)
    self.title(title or name)
    self.protocol("WM_DELETE_WINDOW", lambda name=name: self._root()._closeWindow(name))
    app = AppPanedWidget(self)
    app.pack(fill=tk.BOTH, side=tk.RIGHT, expand=True, padx=0, pady=0)
    
    self.option_add('*tearOff', tk.FALSE)
    #self.tkTop.protocol("WM_DELETE_WINDOW", self.onClosing)
    self.bind("<FocusIn>", self.onFocusIn)
    self.bind("<Enter>", self.onEnter)

  def onFocusIn(self, _event):
    #loggingWidget.loggingWidget = self.loggingWidget
    pass
    
  def onEnter(self, _event): # because <FocusIn> doesn't seem to always work.
    #loggingWidget.loggingWidget = self.loggingWidget
    pass


class AppPanedWidget(tk.PanedWindow):
  '''
  A (tkinter.PanedWindow) with two panes: above, and application widget according the
  *frame* parameter of the constructor, and below, a disabled text widget which is used
  by this class's various service methods to display messages such as logging info:

    +-------------------------+
    |                         |
    |AppPanedWidget (graphics)|
    |                         |
    +-------------------------+
    | SNTerminalWidget (text) |
    +-------------------------+
  '''

  def __init__(self, parent,
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
    # fix up kwargs to contain the necessary defaults and create the PanedWindow (super).
    if "orient" not in kwargs: kwargs["orient"] = tk.VERTICAL
    if "showhandle" not in kwargs: kwargs["showhandle"] = False
    if "sashwidth" not in kwargs: kwargs["sashwidth"] = 6
    if "sashrelief" not in kwargs: kwargs["sashrelief"] = "ridge"#"groove"#"sunken"#
    if "bd" not in kwargs: kwargs["bd"] = 4
    if "bg" not in kwargs: kwargs["bg"] = "lightgrey"
    if "borderwidth" not in kwargs: kwargs["borderwidth"] = 0
    
    # super constructor
    super().__init__(parent, **kwargs)

    # set up the textDisplayFrame (contains the *loggingWidget* , *commandEntryWidget* and *promptLabel*
    self.textDisplayFrame = SNTerminalWidget(None, self)
    self.textDisplayFrame.pack(fill=tk.NONE, side=tk.BOTTOM, expand=False)
    stretch = 'always' #if fixedAppFrame else 'never'
    sticky = 'news' #if fixedAppFrame else 'new'
    self.add(self.textDisplayFrame, stretch=stretch, sticky=sticky)
    self.paneconfigure(self.textDisplayFrame, stretch=stretch)

    self.appFrame = SNGFrame(self)
    self.appFrame.pack(fill=tk.BOTH, # if self.fixedAppFrame else tk.BOTH,
                        side=tk.TOP,
                        expand=False) # if self.fixedAppFrame else True)

    stretch = 'never' #if self.fixedAppFrame else 'always'
    sticky = 'new' #if self.fixedAppFrame else 'news'
    self.add(self.appFrame, before=self.textDisplayFrame, stretch=stretch, sticky=sticky)  # 'always', 'first', 'last', 'middle', and 'never'.
    self.paneconfigure(self.appFrame, stretch=stretch)
   
    self.pack(fill=tk.BOTH, expand=True)


class SNGFrame(tk.Frame):
  def __init__(self, parent, **kwargs):
    '''
    :param parent: The master Widget.
    :param kwargs: Passed to *Canvas*.
    '''
    #self.scrollRegion:list = [0,0,1000,1000]
    tk.Frame.__init__(self, parent)

    self.hScroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL)
    self.vScroll = ttk.Scrollbar(self, orient=tk.VERTICAL)
    kwargs["yscrollcommand"] = self.vScroll.set
    kwargs["xscrollcommand"] = self.hScroll.set
    if "bg" not in kwargs: kwargs["bg"] = snPrefs.get('view_backgroundColor', storeDefault="grey95", storeType="color")

    # Call the tk.Canvas and PRDb constructors
    self.canvas = tk.Canvas(self, **kwargs)
    
    self.hScroll['command'] = self.canvas.xview
    self.vScroll['command'] = self.canvas.yview

    self.canvas.grid(column=0, row=0, sticky=tk.N+tk.W+tk.E+tk.S)
    self.hScroll.grid(column=0, row=1, sticky=tk.W+tk.E)
    self.vScroll.grid(column=1, row=0, sticky=tk.N+tk.S)
    self.grid_columnconfigure(0, weight=1)
    self.grid_rowconfigure(0, weight=1)
    
    # test code **********************
    self.canvas.create_rectangle(500, 500, 700, 650, outline="black", fill="lightblue", width=2)
    self.canvas.create_rectangle(50, 500, 150, 700, outline="black", fill="purple", width=2)
    self.resetScrollRegion()
    print("Hello world!")
    #**********************
    
  def resetScrollRegion(self):
    self.canvas.configure({"scrollregion":expandRect(self.canvas.bbox("all"),10)})

if __name__ == "__main__":
  app = Application("MyApp")
  win1 = app.openWindow("main", title="Main Window")
  win2 = app.openWindow("settings", title="Settings")
  app.run()

