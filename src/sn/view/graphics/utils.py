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
from typing import Optional, Iterable
import subprocess

logger:sn.SNLogger = sn.getLogger(__name__)

# State bits in events
def s_CMD(s:int) -> bool:
  ":return: *True* iff *s* has the Command key bit set."
  return (s&0x18) != 0
def s_SHIFT(s:int) -> bool: 
  ":return: *True* iff *s* has the Shift key bit set."
  return (s&0x1)  != 0
def s_CTL(s:int) -> bool: 
  ":return: *True* iff *s* has the Control key bit set."
  return (s&0x4)  != 0
def s_ALT(s:int) -> bool: 
  ":return: *True* iff *s* has the Alt or Option key bits set."
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
  :param rect: (x,y,x1,y1)
  :return: *True* iff the give *pt* lies inside *rect*.
  """
  return pointInPoly(pt, [(rect[0], rect[1]),
              (rect[2], rect[1]),
              (rect[2], rect[3]),
              (rect[0], rect[3])])
              
def shiftRectToPoint(rect:Iterable[float], point:Iterable[float]) -> list[float]:
  """
  :param pt: (x,y) 
  :param rect: (x,y,x1,y1)
  :return: A new rectangle if the same size and aspect ratio as *rect*, but with the 
    upper left corner at *pt*.
  """
  
  return [point[0], point[1], point[0]+rect[2]-rect[0], point[1]+rect[3]-rect[1]]
                    
def overlaps(rect1:Iterable[float], rect2:Iterable[float]) -> bool:
  """
  :param rect1: (x,y,x1,y1)
  :param rect2: (x,y,x1,y1)
  :return: *True* iff the two rectangles overlap.
  """
  def overlapDim(a1, a2, b1, b2):
    return not(a2 < b1 or b2 < a1)
  return overlapDim(rect1[0], rect1[2], rect2[0], rect2[2]) and \
          overlapDim(rect1[1], rect1[3], rect2[1], rect2[3])

def pointInPoly(pt:Iterable[float], poly:Iterable[float]) -> bool:
  """
  :param pt: (x,y) 
  :param poly: (x,y [,x1,y1]...)
  :return: *True* iff the give *pt* lies inside *poly*.
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
  :param pt2: (x,y)
  :return: The point midway between the two points.
  """
  return ((pt1[0]+pt2[0])/2, (pt1[1]+pt2[1])/2)
  
def expandRect(rect:Iterable[float], spacing:Iterable[float]) -> list[float]:
  """
  :param rect: The rectangle to expand.
  :param spacing: The vector of points to expand *rect* as [left, top, right, bottom].
  :return: A new rectangle representing the expansion of *rect*.
  """ 
  return  [rect[0]-spacing[0],
       rect[1]-spacing[1],
       rect[2]+spacing[2],
       rect[3]+spacing[3]]
  
def normalizeRect(rect:Iterable[float]) -> list[float]:
  """
  Fix up a rect (x,y,x1,y1) such that x<x1 and y<y1, in conformance to tk rules.
  
  :param: rect:
  :return: A new rectangle same as *rect*, but s/t x<x1 and y<y1.
  """
  return [rect[0] if rect[0]<rect[2] else rect[2],
      rect[1] if rect[1]<rect[3] else rect[3],
      rect[2] if rect[0]<rect[2] else rect[0],
      rect[3] if rect[1]<rect[3] else rect[1]]
    
##########################################################################################
########## USER INTERFACE ################################################################
##########################################################################################

def bindRightMouse(window, func):
  if window.winfo_toplevel().tk.call("tk", "windowingsystem") == 'aqua':
    window.bind("<2>", func)
    window.bind("<Control-1>", func)
  else:
    window.bind("<3>", func)

def tag_bindRightMouse(window, id_, func):
  if window.tk.call("tk", "windowingsystem") == 'aqua':
    window.tag_bind(id_, "<2>", func)
    window.tag_bind(id_, "<Control-1>", func)
  else:
    window.tag_bind(id_, "<3>", func)

def tag_unbindRightMouse(window, id_):
  if window.tk.call("tk", "windowingsystem") == 'aqua':
    window.tag_unbind(id_, "<2>")
    window.tag_unbind(id_, "<Control-1>")
  else:
    window.tag_unbind(id_, "<3>")

def eventEqual(e1, e2):
  return isinstance(e1, tk.Event) and isinstance(e2, tk.Event) and \
      e1.x_root == e2.x_root and \
      e1.y_root == e2.y_root and \
      e1.type   == e2.type

##########################################################################################
########## MENUS ########################################################################
##########################################################################################

def getSubMenu(menu:tk.Menu, name:str, makeIfNone:Optional[int]=tk.END) -> Optional[tk.Menu]:
  """
  Find a submenu in *menu* with label *name* .
  
  :param menu: The menu to search
  :param name: The label of the item we are searching for
  :param makeIfNone: [default: tk.END (insert at end)] if an *int* and *menu* does not contain any
      menu items named *name* then insert a new menu named *name* at position 
      *makeIfNone* .
  :return: Return a *tk.Menu* if it is found or created; if it is not found and
      *makeIfNone* is *None*, return *None* .
  """
  submenu = None      
  try:
    index = menu.index(name)
    assert menu.type(index) == "cascade"
    submenu = menu.entrycget(index,'menu')
    submenu = menu.winfo_toplevel().nametowidget(submenu)
  except Exception as ex:
    if makeIfNone is not None:
      assert isinstance(makeIfNone, int)
      submenu = tk.Menu(menu) #TODO: should probably make an effort to put this in the right place
      menu.insert_cascade(makeIfNone, label=name, menu=submenu)
  return submenu


def getToplevelWindows(root:tk.Tk): 
  return [x for x in root.winfo_children() if isinstance(x , tk.Toplevel)]
  
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
