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
import sn
'''
GUI specific utilities.

Created on Jan 18, 2025

.. codeauthor:: Rob Kremer <robkremer@me.com>

-----------
'''

import logging
import tkinter as tk
from tkinter import ttk
from typing import Optional, Iterable, Callable
import subprocess

logger:sn.SNLogger = sn.getLogger(__name__)

# State bits in events
def s_CMD(s:int) -> bool:
  '''
  :return: *True* iff *s* has the Command key bit set.

  :param s:
  :type s: int
  :rtype: bool
  '''
  return (s&0x18) != 0
def s_SHIFT(s:int) -> bool: 
  '''
  :return: *True* iff *s* has the Shift key bit set.

  :param s:
  :type s: int
  :rtype: bool
  '''
  return (s&0x1)  != 0
def s_CTL(s:int) -> bool: 
  '''
  :return: *True* iff *s* has the Control key bit set.

  :param s:
  :type s: int
  :rtype: bool
  '''
  return (s&0x4)  != 0
def s_ALT(s:int) -> bool: 
  '''
  :return: *True* iff *s* has the Alt or Option key bits set.

  :param s:
  :type s: int
  :rtype: bool
  '''
  return (s&0x88) != 0
s_OPT = s_ALT

# Graphical representations for control keys
CHAR_SHIFT = u'\u21E7'
CHAR_CTL   = u'\u2388'
CHAR_ALT   = u'\u2387'
CHAR_CMD   = u'\u2318'

##########################################################################################
########## GRAPHIC UtiLItiES #############################################################
##########################################################################################

def pointInRect(pt:Iterable[float], rect:Iterable[float]) -> bool:
  """
  :param pt: (x,y) 
  :type pt: Iterable[float]
  :param rect: (x,y,x1,y1)
  :type rect: Iterable[float]
  :return: *True* iff the give *pt* lies inside *rect*.
  :rtype: bool
  """
  return pointInPoly(pt, [(rect[0], rect[1]),
              (rect[2], rect[1]),
              (rect[2], rect[3]),
              (rect[0], rect[3])])
              
def shiftRectToPoint(rect:Iterable[float], point:Iterable[float]) -> list[float]:
  """
  :param pt: (x,y) 
  :param rect: (x,y,x1,y1)
  :type rect: Iterable[float]
  :param point:
  :type point: Iterable[float]
  :return: A new rectangle if the same size and aspect ratio as *rect*, but with the 
    upper left corner at *pt*.
  :rtype: list[float]
  """
  
  return [point[0], point[1], point[0]+rect[2]-rect[0], point[1]+rect[3]-rect[1]]
                    
def overlaps(rect1:Iterable[float], rect2:Iterable[float]) -> bool:
  """
  :param rect1: (x,y,x1,y1)
  :type rect1: Iterable[float]
  :param rect2: (x,y,x1,y1)
  :type rect2: Iterable[float]
  :return: *True* iff the two rectangles overlap.
  :rtype: bool
  """
  def overlapDim(a1, a2, b1, b2):
    return not(a2 < b1 or b2 < a1)
  return overlapDim(rect1[0], rect1[2], rect2[0], rect2[2]) and \
          overlapDim(rect1[1], rect1[3], rect2[1], rect2[3])

def pointInPoly(pt:Iterable[float], poly:Iterable[float]) -> bool:
  """
  :param pt: (x,y) 
  :type pt: Iterable[float]
  :param poly: (x,y [,x1,y1]...)
  :type poly: Iterable[float]
  :return: *True* iff the give *pt* lies inside *poly*.
  :rtype: bool
  """
  #import numpy as np
  import matplotlib.path as mplPath
  arr = []
  for i in range(0, len(poly), 2):
    arr.append((poly[i], poly[i+1]))
  #bbPath = mplPath.Path(np.array(arr))
  bbPath = mplPath.Path(arr)
  return bbPath.contains_point(pt)

def midpoint(pt1:Iterable[float], pt2:Iterable[float]) -> list[float]:
  """
  :param pt1: (x,y)
  :type pt1: Iterable[float]
  :param pt2: (x,y)
  :type pt2: Iterable[float]
  :return: The point midway between the two points.
  :rtype: list[float]
  """
  return ((pt1[0]+pt2[0])/2, (pt1[1]+pt2[1])/2)
  
def expandRect(rect:Iterable[float], spacing:Iterable[float]) -> list[float]:
  """
  :param rect: The rectangle to expand.
  :type rect: Iterable[float]
  :param spacing: The vector of points to expand *rect* as [left, top, right, bottom].
  :type spacing: Iterable[float]
  :return: A new rectangle representing the expansion of *rect*.
  :rtype: list[float]
  """ 
  return  [rect[0]-spacing[0],
       rect[1]-spacing[1],
       rect[2]+spacing[2],
       rect[3]+spacing[3]]
  
def normalizeRect(rect:Iterable[float]) -> list[float]:
  """
  Fix up a rect (x,y,x1,y1) such that x<x1 and y<y1, in conformance to tk rules.
  
  :param: rect:
  :param rect:
  :type rect: Iterable[float]
  :return: A new rectangle same as *rect*, but s/t x<x1 and y<y1.
  :rtype: list[float]
  """
  return [rect[0] if rect[0]<rect[2] else rect[2],
      rect[1] if rect[1]<rect[3] else rect[3],
      rect[2] if rect[0]<rect[2] else rect[0],
      rect[3] if rect[1]<rect[3] else rect[1]]
    
##########################################################################################
########## USER INTERFACE ################################################################
##########################################################################################

def bindRightMouse(window, func):
  '''
  :param window:
  :type window:
  :param func:
  :type func:
  '''
  if window.winfo_toplevel().tk.call("tk", "windowingsystem") == 'aqua':
    window.bind("<2>", func)
    window.bind("<Control-1>", func)
  else:
    window.bind("<3>", func)

def tag_bindRightMouse(window, id_, func):
  '''
  :param window:
  :type window:
  :param id_:
  :type id_:
  :param func:
  :type func:
  '''
  if window.tk.call("tk", "windowingsystem") == 'aqua':
    window.tag_bind(id_, "<2>", func)
    window.tag_bind(id_, "<Control-1>", func)
  else:
    window.tag_bind(id_, "<3>", func)

def tag_unbindRightMouse(window, id_):
  '''
  :param window:
  :type window:
  :param id_:
  :type id_:
  '''
  if window.tk.call("tk", "windowingsystem") == 'aqua':
    window.tag_unbind(id_, "<2>")
    window.tag_unbind(id_, "<Control-1>")
  else:
    window.tag_unbind(id_, "<3>")

def eventEqual(e1, e2):
  '''
  :param e1:
  :type e1:
  :param e2:
  :type e2:
  :returns:
  :rtype:
  '''
  return isinstance(e1, tk.Event) and isinstance(e2, tk.Event) and \
      e1.x_root == e2.x_root and \
      e1.y_root == e2.y_root and \
      e1.type   == e2.type

##########################################################################################
########## MENUS ########################################################################
##########################################################################################

def getSubMenu(menu:tk.Menu, name:str, makeIfNone:int|str|None=tk.END) -> Optional[tk.Menu]:
  """
  Find a submenu in *menu* with label *name* .

  :param menu: The menu to search
  :type menu: tk.Menu
  :param name: The label of the item we are searching for
  :type name: str
  :param makeIfNone: [default: tk.END (insert at end)] if not *None* and *menu* does not
      contain any menu items named *name* then insert a new menu named *name* at position
      *makeIfNone* -- either an *int* index or one of Tkinter's symbolic index constants
      (e.g. *tk.END*, which is itself just the *str* "end"; this is what *insert_cascade()*
      itself accepts, so we just pass it straight through).
  :type makeIfNone: int | str | None
  :return: Return a *tk.Menu* if it is found or created; if it is not found and
      *makeIfNone* is *None*, return *None* .
  :rtype: Optional[tk.Menu]
  """
  submenu = None
  try:
    index = menu.index(name)
    assert menu.type(index) == "cascade"
    submenu = menu.entrycget(index,'menu')
    submenu = menu.winfo_toplevel().nametowidget(submenu)
  except Exception as ex:
    if makeIfNone is not None:
      assert isinstance(makeIfNone, (int, str))
      submenu = tk.Menu(menu) #TODO: should probably make an effort to put this in the right place
      menu.insert_cascade(makeIfNone, label=name, menu=submenu)
  return submenu


def getToplevelWindows(root:tk.Tk):
  '''
  :param root:
  :type root: tk.Tk
  :returns:
  :rtype:
  '''
  return [x for x in root.winfo_children() if isinstance(x , tk.Toplevel)]

def _getMenuBar() -> Optional[tk.Menu]:
  """
  Resolve the app's menu bar -- the configured menu of ``tk._default_root``.

  :return: The resolved *tk.Menu*, or *None* if there's no default root, or
      it has no menu bar configured.
  :rtype: Optional[tk.Menu]
  """
  root = tk._default_root  # type: ignore[attr-defined] # @UndefinedVariable
  if root is None:
    return None
  menuName = root.cget("menu")
  if not menuName:
    return None
  return root.nametowidget(menuName)

def _findEntry(menu:tk.Menu, label:str) -> tuple[Optional[int], Optional[str]]:
  """
  :param menu: The menu to search.
  :type menu: tk.Menu
  :param label: The label of the item we are searching for.
  :type label: str
  :return: *(index, type)* of the entry in *menu* labelled *label*, or
      *(None, None)* if there is no such entry.
  :rtype: tuple[Optional[int], Optional[str]]
  """
  try:
    # Menu.index(label) raises TclError (not "returns None") when no entry
    # matches -- e.g. on an otherwise-empty menu -- so absence has to be
    # caught, not tested for. Same gotcha getSubMenu() above works around.
    index = menu.index(label)
  except tk.TclError:
    return None, None
  if index is None:
    return None, None
  return index, menu.type(index)

def addToMenuBar(path:str, command:Optional[Callable]=None, *, menu:Optional[tk.Menu]=None,
    accelerator:Optional[str]=None) -> None:
  """
  Add -- or, if already present, replace -- an entry in the app's menu bar.

  Pass exactly one of *command* or *menu*: *command* adds/replaces a plain
  command entry that invokes *command* when chosen; *menu* adds/replaces a
  cascade entry whose submenu is *menu*. The top-level menu bar itself is
  always the app's own -- resolved from ``tk._default_root``'s configured
  menu -- there's no need to look it up and pass it in.

  :param path: A ``"|"``-separated path of cascade labels ending in the
      item's own label, e.g. ``"File|Save view"``. All but the last segment
      name cascade submenus, created via *getSubMenu()* if they don't
      already exist; the last segment is the item's own label.
  :type path: str
  :param command: The callable to invoke when the item is chosen. Give this
      to add/replace a plain command item; mutually exclusive with *menu*.
  :type command: Optional[Callable]
  :param menu: The submenu to show as a cascade. Give this to add/replace a
      cascade item; mutually exclusive with *command*.
  :type menu: Optional[tk.Menu]
  :param accelerator: Optional accelerator string to display (e.g. "Cmd+S").
  :type accelerator: Optional[str]
  :note: Safe to call repeatedly with the same *path* -- e.g. every time a
      window gains focus -- since an existing entry with the same final
      label is reconfigured in place rather than duplicated (and, if it was
      previously the other kind of entry -- command vs. cascade -- it's
      replaced in place, at the same position). This is what makes it safe
      for callers like *SNGView.onWindowFocusIn()* to call unconditionally.
  :rtype: None
  """
  assert (command is None) != (menu is None), \
      'addToMenuBar(): pass exactly one of command= (add/replace a command item) or menu= (add/replace a cascade item).'
  segments = path.split("|")
  assert len(segments) >= 1, f'addToMenuBar(): empty path.'
  target = _getMenuBar()
  assert target is not None, \
      f'addToMenuBar(): no default menu bar could be resolved (no default root, or it has no menu configured).'
  for seg in segments[:-1]:
    target = getSubMenu(target, seg)
  label = segments[-1]
  kwargs = {} if accelerator is None else {"accelerator": accelerator}
  wantType = "command" if command is not None else "cascade"
  index, existingType = _findEntry(target, label)
  if index is not None and existingType != wantType:
    target.delete(index)  # entry exists but as the other kind -- replace it in place
  elif index is None:
    index = tk.END
  if command is not None:
    if existingType == wantType:
      target.entryconfig(index, command=command, state=tk.NORMAL, **kwargs)
    else:
      target.insert_command(index, label=label, command=command, state=tk.NORMAL, **kwargs)
  else:
    if existingType == wantType:
      target.entryconfig(index, menu=menu, state=tk.NORMAL, **kwargs)
    else:
      target.insert_cascade(index, label=label, menu=menu, state=tk.NORMAL, **kwargs)

def addCheckToMenuBar(path:str, variable:tk.Variable, command:Optional[Callable]=None, *,
                      cascadePositions:Optional[dict[str, int]]=None) -> None:
  """
  Add -- or, if already present, replace -- a check item in the app's menu
  bar: it shows (and sets) the boolean *variable*, and calls *command* when
  chosen. Like *addToMenuBar()*, safe to call repeatedly with the same *path*
  (eg: each time a window gains focus, rebinding it to that window's variable),
  and removed with *removeFromMenuBar()*.

  :param path: A ``"|"``-separated path of cascade labels ending in the
      item's own label, e.g. ``"View|Animation toolbar"``.
  :type path: str
  :param variable: The (boolean) variable the item shows and sets.
  :type variable: tk.Variable
  :param command: Called (after *variable* is set) when the item is chosen.
  :type command: Optional[Callable]
  :param cascadePositions: Where to put any cascade that has to be made, by
      label, eg: ``{"View": 1}`` (just after "File"); by default, at the end.
  :type cascadePositions: Optional[dict[str, int]]
  :rtype: None
  """
  segments = path.split("|")
  target = _getMenuBar()
  assert target is not None, \
      f'addCheckToMenuBar(): no default menu bar could be resolved (no default root, or it has no menu configured).'
  for seg in segments[:-1]:
    target = getSubMenu(target, seg, makeIfNone=(cascadePositions or {}).get(seg, tk.END))
  label = segments[-1]
  index, existingType = _findEntry(target, label)
  if index is not None:
    target.delete(index) # (rebuilt: a check item's variable can't be rebound by entryconfig on every platform)
  else:
    index = tk.END
  target.insert_checkbutton(index, label=label, variable=variable, onvalue=True, offvalue=False,
                            command=command, state=tk.NORMAL)

def removeFromMenuBar(path:str) -> None:
  """
  Remove an entry (as added by *addToMenuBar()*) from the app's menu bar.

  Safe to call even when the item (or an intervening cascade) isn't
  currently present -- this is simply a no-op in that case, so callers
  like *SNGView.onWindowFocusOut()* don't need to track whether they
  actually added the item first.

  :param path: Same ``"|"``-separated path as passed to *addToMenuBar()*.
  :type path: str
  :rtype: None
  """
  segments = path.split("|")
  assert len(segments) >= 1, f'removeFromMenuBar(): empty path.'
  target = _getMenuBar()
  if target is None:
    return
  for seg in segments[:-1]:
    target = getSubMenu(target, seg, makeIfNone=None)
    if target is None:
      return
  label = segments[-1]
  index, _ = _findEntry(target, label)
  if index is not None:
    target.delete(index)
  
##########################################################################################
########## SOUNDS ########################################################################
##########################################################################################

def play(soundFile:Optional[str]=None):
  """
  Plays a sound file. So far, this is only implemented for mac.
  
  :param soundFile: May have the following values:
    - None: plays "/System/Library/Sounds/Sosumi.aiff" (an error beep).
    - Just a file name: (not containing any slashes ("/")) looks in /System/Library/Sounds/ for the file.
    - A path: (containing slashes ("/")) just tries to play that file.
  :type soundFile: Optional[str]
  """
  if soundFile is None or len(soundFile)==0:
    soundFile = '/System/Library/Sounds/Sosumi.aiff'
  elif soundFile.find('/') < 0:
    soundFile = '/System/Library/Sounds/'+soundFile
  subprocess.Popen(["afplay", soundFile])

##########################################################################################
########## LIST MANIPULATION #############################################################
##########################################################################################

def flattenPairs(pairs):
  """
  From a vector of pairs, return a simple vector. [(1,2),(3,4)] -> [1,2,3,4]

  :param pairs:
  :type pairs:
  :returns:
  :rtype:
  """
  ret = []
  for p in pairs:
    ret.append(p[0])
    ret.append(p[1])
  return ret
  
class VerticalScrolledFrame(ttk.Frame):
    """A pure Tkinter scrollable frame that actually works!
    * Use the 'interior' attribute to place widgets inside the scrollable frame.
    * Construct and pack/place/grid normally.
    * This frame only allows vertical scrolling.
    """
    def __init__(self, parent, *args, **kw):
        '''
        :param parent:
        :type parent:
        :param args:
        :type args:
        :param kw:
        :type kw:
        '''
        ttk.Frame.__init__(self, parent, *args, **kw)

        # Create a canvas object and a vertical scrollbar for scrolling it.
        vscrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL)
        vscrollbar.pack(fill=tk.Y, side=tk.RIGHT, expand=tk.FALSE)
        canvas = tk.Canvas(self, bd=0, highlightthickness=0,
                           yscrollcommand=vscrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=tk.TRUE)
        vscrollbar.config(command=canvas.yview)

        # Reset the view
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)

        # Create a frame inside the canvas which will be scrolled with it.
        self.interior = interior = ttk.Frame(canvas)
        interior_id = canvas.create_window(0, 0, window=interior,
                                           anchor=tk.NW)

        # Track changes to the canvas and frame width and sync them,
        # also updating the scrollbar.
        def _configure_interior(event):
            # Update the scrollbars to match the size of the inner frame.
            size = (interior.winfo_reqwidth(), interior.winfo_reqheight())
            canvas.config(scrollregion="0 0 %s %s" % size)
            if interior.winfo_reqwidth() != canvas.winfo_width():
                # Update the canvas's width to fit the inner frame.
                canvas.config(width=interior.winfo_reqwidth())
        interior.bind('<Configure>', _configure_interior)

        def _configure_canvas(event):
            if interior.winfo_reqwidth() != canvas.winfo_width():
                # Update the inner frame's width to fill the canvas.
                canvas.itemconfigure(interior_id, width=canvas.winfo_width())
        canvas.bind('<Configure>', _configure_canvas)
