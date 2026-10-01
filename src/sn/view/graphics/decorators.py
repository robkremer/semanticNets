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
        Decorator
        Marker
        MarkerContainer
        MarkerWithTooltip
        Selected
        WrappingText
      :parts: 3
      :private-bases:
      :top-classes: util.commandParser.ParsableCommandDef, util.commandParser.ParsableQuery

Created on Feb 3, 2025

.. codeauthor:: Rob Kremer <robkremer@me.com>

------------------
'''

import weakref
from abc import ABC, abstractmethod
from math import log
import tkinter.font as tkfont
from typing import override, Callable, Optional, Union, Any
import sn
from sn import snPrefs
#from sn.view import tooltip
from util.tooltip import CreateToolTip

logger:sn.SNLogger = sn.getLogger(__name__)

DOT = '\u23FA'

##########################################################################################
################################ D E C O R A T O R S #####################################
##########################################################################################

class Decorator(ABC):
  def __init__(self, owner, priority:int=0):
    '''
    :param owner: The *VObject* this decorator is attached to.
    :param priority: [int, default=0] Where this decorator draws relative to
      the owner's other decorators, lowest first -- see *VObject.draw()*,
      which draws *self.decorators.values()* sorted by this. Ties keep
      insertion order (Python's sort is stable), so existing decorators are
      unaffected by just leaving this at its default.

      This only orders decorators *within one VObject's own draw() call* --
      it can't reach across to order against a *different* VObject's items,
      since canvas stacking is one global list, not per-object (see
      *ShadowDecorator*, which needs exactly that and uses
      *canvas.tag_lower()* instead).
    :type priority: int
    '''
    from sn.view.graphics.vobjects import VObject
    assert isinstance(owner, VObject)

    super().__init__()

    self._owner = weakref.ref(owner)
    self.kind = type(self).__name__
    self.deleted:bool = False
    self.priority:int = priority

  @property
  def owner(self):
    return self._owner()

  def delete(self):
    if self.deleted: return
    self.deleted = True
    self.owner.notifyDecoratorDeletion(self)

  @abstractmethod
  def draw(self, fast=False, **kwargs):
    pass

class Text(Decorator):
  def __init__(self, owner, **kwargs):
    super().__init__(owner)
    self.id = None # The id of the canvas item
    self.kwargs = kwargs
    if "justify" not in self.kwargs: self.kwargs["justify"] = "center"
    if "anchor"  not in self.kwargs: self.kwargs["anchor"]  = "center"
    if "font"    not in self.kwargs: self.kwargs["font"]    = (self.owner.view._fontFace, int(self.owner.view._fontSize*self.owner.view._scale))
    if "fill"    not in self.kwargs: self.kwargs["fill"]    = "black"

  def updateKwargs(self):
    self.kwargs["fill"] = self.owner.cache["vis/textColor"]
      
  @override
  def draw(self, fast=False, **kwargs):
    if not fast:
      self.updateKwargs() # first update from the GraphObject.
    self.kwargs.update(kwargs) # then from the parameters
    self.setText(fast=fast)
    self.setFontToScale()
    x, y = self.getCoords()
    if self.id is None:
      self.kwargs["state"] = "disabled"
      self.kwargs["tags"] = [self.owner.tag, 'text']
      self.id = self.owner.canvas.create_text(x, y, **self.kwargs)
    else:
      self.owner.canvas.coords(self.id, x, y)
      self.owner.canvas.itemconfigure(self.id, **self.kwargs)
      
  def getCoords(self) -> tuple[int, int]:
    x, y = self.owner.centerPt() # centred exactly (with anchor and justify "center")
    return self.owner.view.viewToWindow(x,y)
      
  def setText(self, fast=False) -> str:
    text = self.owner.labelText()
    self.kwargs['text'] = text
    return text
          
  def setFontToScale(self):
    self.kwargs["font"] = (self.owner.view._fontFace, int(self.owner.view._fontSize * self.owner.view._scale))

  @override
  def delete(self):
    if self.deleted: return
    super().delete()
    self.owner.canvas.delete(self.id)
    self.kwargs = None #type: ignore[assignment]
  
NOMINAL_ASPECT = 0.6
"The height/width used where vis/aspectRatio is 0 (ie: free): a box's starting shape, and its minimum height (see *VObject.minHeight()*)."

BREAK_AFTER = frozenset(" -_./\\,;:|+&)]}>")
"Characters a line of *WrappingText* may break after (spaces at a break are dropped)."

_fonts:dict[tuple, tkfont.Font] = {}
_layoutCache:dict[tuple, tuple[list[str], int, int]] = {}

def _font(canvas, font:tuple) -> tkfont.Font:
  f = _fonts.get(font)
  if f is None:
    f = _fonts[font] = tkfont.Font(root=canvas, family=font[0], size=font[1])
  return f

def textPieces(text:str) -> list[str]:
  '''
  Split *text* after each character in *BREAK_AFTER* -- but not just before a
  non-breaking space (eg: "age:\u00a030" stays together): the units a line is
  built from.
  '''
  pieces:list[str] = []
  cur = ""
  for i, ch in enumerate(text):
    cur += ch
    if ch in BREAK_AFTER and text[i+1:i+2] != "\u00a0":
      pieces.append(cur)
      cur = ""
  if cur:
    pieces.append(cur)
  return pieces

def layoutText(canvas, text:str, font:tuple, wrap:float=0) -> tuple[list[str], int, int]:
  '''
  Break *text* into lines no wider than *wrap* pixels (0: only at newlines),
  breaking only after spaces and the punctuation in *BREAK_AFTER* -- never
  inside a piece, so a piece wider than *wrap* gets a line to itself and
  overflows. Cached.

  :returns: (lines, width, height) in pixels of *font*.
  '''
  key = (text, font, int(wrap))
  ret = _layoutCache.get(key)
  if ret is None:
    f = _font(canvas, font)
    lines:list[str] = []
    for para in text.split("\n"):
      line = ""
      for piece in textPieces(para):
        if line and wrap > 0 and f.measure((line + piece).rstrip()) > wrap:
          lines.append(line.rstrip())
          line = piece.lstrip()
        else:
          line += piece
      lines.append(line.rstrip())
    width = max((f.measure(l) for l in lines), default=0)
    ret = (lines, width, len(lines) * f.metrics("linespace"))
    if len(_layoutCache) > 5000:
      _layoutCache.clear()
    _layoutCache[key] = ret
  return ret

class WrappingText(Text):
  '''
  The owner's name, centred in its bounding box and wrapped to the usable
  width of its shape (see *Shape.textInset()*).

  If the owner's "vis/textModifiesBB" is set, *fitOwner()* also sizes the
  owner's bounding box to the text (see *preferredSize()*), within
  "vis/minSize"/"vis/maxSize" (box width) and close to "vis/aspectRatio"
  (height/width).
  '''

  PAD = 3
  "Space (view units) between the text and the edge of the shape's usable area."

  def __init__(self, owner, **kwargs):
    super().__init__(owner, **kwargs)
    self._fitted:tuple|None = None
    "What the box was last sized for (see *fitOwner()*); refit when it changes."
    self._wrap:float|None = None
    "The text wrap width chosen when the box was last sized automatically (see *preferredLayout()*)."

  def baseFont(self) -> tuple:
    'The font at zoom 1.0 -- ie: in view units, which is what boxes are measured in.'
    return (self.owner.view._fontFace, int(self.owner.view._fontSize))

  def textInset(self) -> tuple[float, float]:
    fx, fy = self.owner._shape.textInset() if self.owner._shape is not None else (1.0, 1.0)
    return max(fx, 0.1), max(fy, 0.1)

  def innerWidth(self) -> float:
    'The usable width (view units) for text in the current box.'
    bb = self.owner.boundingBox()
    return max(1.0, (bb[2] - bb[0]) * self.textInset()[0] - 2 * self.PAD)

  def wrapWidth(self, text:str) -> float:
    '''
    The width (view units) the text is wrapped to: for an automatically sized
    box, the width chosen with it (see *preferredLayout()*), which may be
    wider than the box; otherwise (eg: sized by the user) the box's usable
    width. Text that doesn't fit overflows the shape, centred.
    '''
    owner = self.owner
    if self._wrap is not None and not owner.userSized and owner.cache["vis/textModifiesBB"]:
      return self._wrap
    return self.innerWidth()

  def longestWord(self, text:str, font:tuple) -> int:
    'The width of the widest unbreakable piece of *text* (see *textPieces()*), 0 if none.'
    f = _font(self.owner.canvas, font)
    return max((f.measure(p.strip()) for p in textPieces(text.replace("\n", " "))), default=0)

  def preferredLayout(self, text:str) -> tuple[int, int, float]:
    '''
    :returns: (box width, box height, text wrap width), in view units, for
      *text* when the box is sized automatically:

      1. The text is broken into lines (see *layoutText()*) so that the text
         block's own shape is as close as possible to "vis/aspectRatio"
         (height/width) -- ties going to the smaller block.
      2. The box is sized to that block, but its width is kept within
         "vis/minSize".."vis/maxSize", and its height is width *
         "vis/aspectRatio". Text too big for a "vis/maxSize" box overflows the
         shape, evenly on all sides.
      3. If "vis/aspectRatio" is 0 (free), the block is shaped to
         *NOMINAL_ASPECT*, and the box height is whatever the text needs (at
         least width * *NOMINAL_ASPECT*), capped at "vis/maxSize".
      4. If "vis/minSize" == "vis/maxSize" the box is a fixed size.
    '''
    cache = self.owner.cache
    minW = float(cache["vis/minSize"])
    maxW = max(float(cache["vis/maxSize"]), minW)
    free = not cache["vis/aspectRatio"]
    aspect = float(cache["vis/aspectRatio"]) or NOMINAL_ASPECT
    fx, fy = self.textInset()
    font = self.baseFont()
    canvas = self.owner.canvas
    if not text:
      return int(minW), int(round(minW * aspect)), max(1.0, minW * fx - 2 * self.PAD)

    # 1: the line breaks that best give the text block the aspect ratio
    _, naturalW, _ = layoutText(canvas, text, font)
    longest = max(1, min(self.longestWord(text, font), naturalW))
    def trial(wrap:int) -> tuple[float, float, int, float, float]: # (badness, area, wrap, block w, block h)
      _, tw, th = layoutText(canvas, text, font, 0 if wrap >= naturalW else wrap)
      bw, bh = (tw + 2 * self.PAD) / fx, (th + 2 * self.PAD) / fy
      return (round(abs(log((bh / bw) / aspect)), 3), bw * bh, wrap, bw, bh)
    # wrap widths spaced geometrically from the longest piece to one line (so
    # long texts are sampled as finely as short ones), then refined around the best
    steps = 16
    ratio = naturalW / longest
    wraps = {naturalW} | {int(longest * ratio ** (k / steps)) for k in range(steps + 1)}
    best = min(trial(w) for w in wraps if 0 < w <= naturalW)
    lo, hi = int(best[2] / ratio ** (1 / steps)), int(best[2] * ratio ** (1 / steps))
    best = min([best] + [trial(lo + (hi - lo) * k // 8) for k in range(9) if 0 < lo + (hi - lo) * k // 8 <= naturalW])
    _, _, wrap, bw, bh = best

    # 2-4: the box
    w = min(max(bw, minW), maxW)
    h = min(max(bh, w * aspect), maxW) if free else w * aspect
    if maxW == minW:
      w, h = minW, minW * aspect
    return int(round(w)), int(round(h)), float(wrap)

  def preferredSize(self, text:str) -> tuple[int, int]:
    'The (width, height) of the automatically sized box for *text* (see *preferredLayout()*).'
    w, h, _ = self.preferredLayout(text)
    return w, h

  def lineHeight(self) -> float:
    'The height (view units) of a box holding one line of text: the smallest useful box.'
    return (_font(self.owner.canvas, self.baseFont()).metrics("linespace") + 2 * self.PAD) / self.textInset()[1]

  def preferredBoundingBox(self) -> list[int]:
    'The owner\'s bounding box resized, about its centre, to *preferredSize()*.'
    w, h, _ = self.preferredLayout(super().setText())
    bb = self.owner.boundingBox()
    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
    x, y = int(cx - w / 2), int(cy - h / 2)
    return [x, y, x + w, y + h]

  def fitOwner(self) -> None:
    '''
    Resize the owner's bounding box, about its centre, to *preferredSize()* --
    but only if "vis/textModifiesBB" is set, the user hasn't sized the box by
    hand (*owner.userSized*), and something the size depends on (the text, the
    size attributes, the shape or the font) has changed since last time, so a
    box isn't refitted on every redraw.
    '''
    owner = self.owner
    if owner.modelObject is None or owner.userSized or not owner.cache["vis/textModifiesBB"]:
      return
    text = super().setText()
    sig = (text, owner.cache["vis/minSize"], owner.cache["vis/maxSize"], owner.cache["vis/aspectRatio"],
           type(owner._shape).__name__, self.baseFont())
    if sig == self._fitted:
      return
    self._fitted = sig
    w, h, self._wrap = self.preferredLayout(text)
    bb = owner.boundingBox()
    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
    x, y = int(cx - w / 2), int(cy - h / 2)
    new = [x, y, x + w, y + h]
    if new != bb:
      owner.boundingBox(new)
      # relations connect to the edge of the (new) shape
      for r in owner.relations:
        r.notifyNodeMove(owner, adjustPos=False)

  @override
  def setText(self, fast=False):
    text = super().setText(fast=fast)
    # Our own line breaks (Tk would only break at spaces), laid out at the base
    # font so they're the same at every zoom; Tk's own wrapping is turned off.
    lines, _, _ = layoutText(self.owner.canvas, text, self.baseFont(), self.wrapWidth(text))
    self.kwargs["text"] = "\n".join(lines)
    self.kwargs["width"] = 0
    return text

class Marker:
  SIZE = [6,6]
  def __init__(self, owner, label:str, fg:str, bg:str, condition:Callable):
    self.owner = owner
    self.label:str = label
    self.fg:str = fg
    self.bg:str = bg
    self.condition:Callable = condition
    self.kwargs:dict[str, Any] = dict()
    self.kwargs2:dict[str, Any] = dict()
    self.id = None # The id of the shape canvas item
    self.id2 = None # The id of the text canvas item
    self.deleted = False
    
  def draw(self, at:list[int]) -> bool:
    '''
    :return: *True* iff the item actually drew (ie: *self.condition()* returns *True*
    '''
    if not self.condition(self.owner):
      self.erase()
      return False
      
    if self.id is None:       
      self.kwargs["state"] = "normal"
      self.kwargs["tags"] = [self.owner.tag, 'text']
      if "justify" not in self.kwargs: self.kwargs["justify"] = "center"
      if "anchor"   not in self.kwargs: self.kwargs["anchor"]  = "center"
      if "font"     not in self.kwargs: self.kwargs["font"]    = ("TkSmallCaptionFont", int(self.owner.view._fontSize * self.owner.view._scale))
      self.kwargs["text"] = self.label if self.label != 'E' else str(len(self.owner.statusReport()))
      self.kwargs["fill"] = self.fg
      if "fill"     not in self.kwargs2: self.kwargs2["fill"]    = self.bg
      if "outline"  not in self.kwargs2: self.kwargs2["outline"] = ""
      self.kwargs2["tags"] = [self.owner.tag]
      self.id2 = self.owner.canvas.create_oval(
                  self.owner.view.viewToWindow(
                  [at[0]-Marker.SIZE[0], 
                   at[1]-Marker.SIZE[1], 
                   at[0]+Marker.SIZE[0], 
                   at[1]+Marker.SIZE[1]]),
                   **self.kwargs2)
      self.id   = self.owner.canvas.create_text(self.owner.view.viewToWindow(at[0])[0], self.owner.view.viewToWindow(at[1])[0], **self.kwargs)
      #self.id   = self.owner.canvas.create_text(at[0], at[1], **self.kwargs)
    else:   
      #self.kwargs.update(kwargs)
      if self.id is not None:
        self.owner.canvas.coords(self.id2, 
                  self.owner.view.viewToWindow(
                  [at[0]-Marker.SIZE[0], 
                   at[1]-Marker.SIZE[1], 
                   at[0]+Marker.SIZE[0], 
                   at[1]+Marker.SIZE[1]]))
        self.owner.canvas.coords(self.id, self.owner.view.viewToWindow(at[0], at[1]))
        self.kwargs["font"] = ("TkSmallCaptionFont", int(self.owner.view._fontSize * self.owner.view._scale))
        self.owner.canvas.itemconfigure(self.id, **self.kwargs)
        self.owner.canvas.itemconfigure(self.id2, **self.kwargs2)
    return True
    
  def erase(self):
    if self.id is not None:
      self.owner.canvas.delete(self.id)
      self.id = None
    if self.id2 is not None:
      self.owner.canvas.delete(self.id2)
      self.id2 = None

  def delete(self):
    if self.deleted: return
    self.owner.canvas.delete(self.id)
    self.owner.canvas.delete(self.id2)
    self.deleted = True

    
class MarkerWithTooltip(Marker):
  
  def __init__(self, owner, label:str, fg:str, bg:str, condition:Callable, tooltipFunc:Union[Callable,str]):
    super().__init__(owner, label, fg, bg, condition)
    self.tooltipFunc = tooltipFunc

  def draw(self, at:list[int]) -> bool:
    '''
    :return: *True* iff the item actually drew (ie: *self.condition()* returns *True*
    '''
    self.tooltip:Optional[CreateToolTip] = None
    new = True if self.id is None else False
    ret = super().draw(at)
    if not ret:
      return ret
    if new:
      self.tooltip = CreateToolTip(self.owner.canvas, self.tooltipFunc, self.id, 
                                 waitTime=1000, wrapLength=250, background="#FFFFC0")
    return ret

  def erase(self):
    if self.tooltip is not None:
      self.tooltip.delete()
      self.tooltip = None
    super().erase()

  def delete(self):
    if self.deleted: return
    if self.tooltip is not None:
      self.tooltip.delete()
      self.tooltip = None
    super().delete()


class ConstraintMarker(MarkerWithTooltip):
  '''
  "{}": a variable's constraints live here (see *sn.model.constraints*) --
  shown in red, "{!}", if they can't be read. The tooltip says what they are
  (or what's wrong). Shown if "gui/showConstraintMarker" is set.
  '''
  OK = ("{}", "white", "dark orchid")
  BAD = ("{!}", "white", "red")

  def __init__(self, owner):
    super().__init__(owner, *self.OK, condition=self.shown, tooltipFunc=self.tip)

  @staticmethod
  def shown(owner) -> bool:
    mo = owner.modelObject
    return mo is not None and mo.isVariable() and bool(mo.constraintsText()) \
           and bool(snPrefs.get("gui/showConstraintMarker", storeDefault=True, storeType=bool,
                           note="Mark each variable that has constraints with a \"{}\" marker."))

  def tip(self) -> str:
    mo = self.owner.modelObject
    err = mo.constraintsError()
    return f'Constraints that can\'t be read: {err}\n{mo.constraintsText()}' if err else f'Constraints: {mo.constraintsText()}'

  @override
  def draw(self, at:list[int]) -> bool:
    mo = self.owner.modelObject
    look = self.BAD if mo is not None and mo.constraintsError() else self.OK
    if (self.label, self.fg, self.bg) != look: # (the text and colours are set when the items are made)
      self.erase()
      self.label, self.fg, self.bg = look
      self.kwargs2.pop("fill", None)
    return super().draw(at)

class MarkerContainer(Decorator):

  def __init__(self, owner):
    Decorator.__init__(self, owner)
    self.markers = [
        MarkerWithTooltip(owner, "E", "white", "red", 
               lambda owner=self.owner: len(owner._statusReport)>0,
               lambda owner=self.owner: DOT + ' ' + (f'\n{DOT} '.join(owner.statusReport()))),
        MarkerWithTooltip(owner, "S", "yellow", "gray50", 
               lambda owner=self.owner: owner.modelObject is not None and owner.modelObject.isSystemObject() and snPrefs.get("gui/showSystemTags", storeDefault=True),
               "System: Object is a fixed system object"),
        MarkerWithTooltip(owner, "T", "lawn green", "gray50", 
               lambda owner=self.owner: owner.modelObject is not None and owner.modelObject.isType() and snPrefs.get("gui/showTypeTags", storeDefault=True),
               "Type: object is a Type object (as opposed to an Individual)"),
        MarkerWithTooltip(owner, "R", "cyan", "gray50", 
               lambda owner=self.owner: owner.modelObject is not None and owner.view.model != owner.modelObject.model and snPrefs.get("gui/showRemoteTags", storeDefault=True),
               lambda owner=self.owner: f'Remote: Object is from another model: {owner.modelObject.model.url}'),
        ConstraintMarker(owner),
        ]

  @override
  def delete(self):
    for m in self.markers:
      m.delete()
    return Decorator.delete(self)

  @override
  def draw(self, fast=False, **kwargs):
    bb = self.owner.boundingBox()
    pt = [bb[0]-Marker.SIZE[0], bb[1]-Marker.SIZE[1]]
    for m in self.markers:
      if m.draw(pt):
        pt[0] += (2*Marker.SIZE[0])
    return Decorator.draw(self, fast, **kwargs)

  
# class Marker2(Decorator):
#   def __init__(self, owner, **kwargs):
#     super().__init__(owner)
#     self.kwargs = kwargs
#     self.offset = (-3,-3)
#     self.size = (6,6) # actually, this is half of the size
#
#   def delete(self):
#     if self.deleted: return
#     super().delete()
#     self.kwargs = None
#
#   def getOffset(self) -> list:
#     offset = [self.offset[0]+self.owner.markerDecoratorOffset, self.offset[1]]
#     self.owner.markerDecoratorOffset += (2 * self.size[0] + 1)
#     return offset
#
# class CircleMarker(Marker):
#   def __init__(self, owner, **kwargs):
#     super().__init__(owner, **kwargs)
#     self.id2 = None
#
#   @abstractmethod
#   def setArgs(self):
#     pass
#
#   def draw(self, fast=False, **kwargs):
#     if self.id is None:       
#       self.kwargs["state"] = "normal"
#       self.kwargs["tags"] = [self.owner.tag, 'text']
#       if "justify" not in self.kwargs: self.kwargs["justify"] = "center"
#       if "anchor"   not in self.kwargs: self.kwargs["anchor"]  = "center"
#       if "font"     not in self.kwargs: self.kwargs["font"]    = ("TkSmallCaptionFont", int(self.owner.view._fontSize * self.owner.view._scale))
#       if "fill"     not in self.kwargs: self.kwargs["fill"]    = "white"
#       self.setArgs()
#       x, y, _, _ = self.owner.boundingBox(fast=fast)
#       offset = self.getOffset()
#       self.id2 = self.owner.canvas.create_oval(
#                   self.owner.view.viewToWindow(
#                   [x+offset[0]-self.size[0], 
#                    y+offset[1]-self.size[1], 
#                    x+offset[0]+self.size[0], 
#                    y+offset[1]+self.size[1]]),
#                    **self.kwargs2)
#       self.id   = self.owner.canvas.create_text(x+offset[0], y+offset[1], **self.kwargs)
#     else:   
#       self.kwargs.update(kwargs)
#       if self.id is not None:
#         self.setArgs()
#         x, y, _, _ = self.owner.boundingBox(fast=fast)
#         offset = self.getOffset()
#         self.owner.canvas.coords(self.id2, 
#                   self.owner.view.viewToWindow(
#                   [x+offset[0]-self.size[0], 
#                    y+offset[1]-self.size[1], 
#                    x+offset[0]+self.size[0], 
#                    y+offset[1]+self.size[1]]))
#         self.owner.canvas.coords(self.id, self.owner.view.viewToWindow([x+offset[0], y+offset[1]]))
#         self.kwargs["font"] = ("TkSmallCaptionFont", int(self.owner.view._fontSize * self.owner.view._scale))
#         self.owner.canvas.itemconfigure(self.id, **self.kwargs)
#         self.owner.canvas.itemconfigure(self.id2, **self.kwargs2)
#
#   def delete(self):
#     if self.deleted: return
#     super().delete()
#     self.owner.canvas.delete(self.id)
#     self.owner.canvas.delete(self.id2)
#     self.kwargs2 = None
#
# class TypeMarker(CircleMarker):
#   def __init__(self, owner, **kwargs):
#     super().__init__(owner, **kwargs)
#     self.kwargs2 = {"tags": [self.owner.tag], "fill": "grey", "outline": ""}
#
#   def setArgs(self):
#     label = ""
#     if self.owner.modelObject.isSystemObject():
#       label += "S"
#     if self.owner.modelObject.isType():
#       label += "T"
#     self.kwargs["text"] = label
#     self.kwargs["fill"] = "lawn green"
#
#     self.kwargs2["fill"] = "black" if self.owner.modelObject.isSystemObject else "grey"
#
# class ErrorMarker(CircleMarker):
#   def __init__(self, owner, **kwargs):
#     super().__init__(owner, **kwargs)
#     self.kwargs2 = {"tags": [self.owner.tag], "fill": "red", "outline": ""}
#
#   def setArgs(self):
#     self.kwargs["text"] = "X"      
#     self.kwargs2["fill"] = "red"
    
class Selected(Decorator):
  '''
  Marks the owner as selected with a small square handle at each corner of
  its bounding box. Dragging a handle resizes the owner (see
  *VObject.onButton_1()*); the handles stay the same size on screen at any zoom.
  An owner that can't be resized (see *VObject.isResizable()*) gets hollow
  handles that can't be grabbed.
  '''
  HALF = 4
  "Half the handle size, in screen pixels."
  GRAB = 2
  "Extra screen pixels around a handle that still count as grabbing it."
  CORNERS = ("nw", "ne", "se", "sw")

  def __init__(self, owner, **kwargs):
    super().__init__(owner)
    self.ids:dict[str, int] = {}
    self.kwargs = kwargs
    if "fill"    not in self.kwargs: self.kwargs["fill"]    = "blue"
    if "outline" not in self.kwargs: self.kwargs["outline"] = "white"
    if "width"   not in self.kwargs: self.kwargs["width"]   = 1

  def cornerPoints(self) -> dict[str, tuple[float, float]]:
    'The corners of the owner\'s bounding box, in window (canvas) coordinates.'
    x1, y1, x2, y2 = self.owner.view.viewToWindow(self.owner.boundingBox())
    return {"nw": (x1, y1), "ne": (x2, y1), "se": (x2, y2), "sw": (x1, y2)}

  def handleAt(self, x:float, y:float) -> str|None:
    '''
    :param x: Canvas (window) coordinates.
    :param y: See *x*.
    :returns: The corner ("nw", "ne", "se" or "sw") whose handle is at (x, y),
      or None -- always None if the owner can't be resized.
    '''
    if not self.owner.isResizable():
      return None
    r = self.HALF + self.GRAB
    for corner, (cx, cy) in self.cornerPoints().items():
      if abs(x - cx) <= r and abs(y - cy) <= r:
        return corner
    return None

  def draw(self, fast=False, **kwargs):
    self.kwargs.update(kwargs)
    style = dict(self.kwargs)
    if not self.owner.isResizable(): # hollow: selected, but not resizable
      style["outline"] = style.get("fill") or "blue"
      style["fill"] = ""
    canvas = self.owner.canvas
    h = self.HALF
    for corner, (cx, cy) in self.cornerPoints().items():
      rect = [cx - h, cy - h, cx + h, cy + h]
      if corner not in self.ids:
        self.ids[corner] = canvas.create_rectangle(rect, tags=[self.owner.tag, 'selection', 'handle'], **style)
      else:
        canvas.coords(self.ids[corner], rect)
        canvas.itemconfigure(self.ids[corner], **style)
      canvas.tag_raise(self.ids[corner])

  def delete(self):
    if self.deleted: return
    super().delete()
    for i in self.ids.values():
      self.owner.canvas.delete(i)
    self.ids = {}
    self.kwargs = None #type: ignore[assignment]


class ContextFrame(Decorator):
  '''
  Draws a context (a rule, query, ...) as a window: a title banner with its
  name and, for a rule, a divider between its antecedent (left) and
  consequent (right) panes, each labelled. The owner's shape is the window
  body. The window is kept beneath everything else, so what it contains sits
  on top of it, and its body is left out of overlap avoidance (it's retagged
  from "vis/shape" to "context-frame"), so objects can be placed inside it.
  See *VObject.isContextWindow()*.
  '''

  def __init__(self, owner):
    super().__init__(owner, priority=-5)
    self.ids:dict[str, int] = {}

  def _item(self, key:str, create, coords, **opts) -> int:
    canvas = self.owner.canvas
    if key not in self.ids:
      self.ids[key] = create(coords, state="disabled", tags=[self.owner.tag, "context-frame"], **opts)
    else:
      canvas.coords(self.ids[key], coords)
      canvas.itemconfigure(self.ids[key], **opts)
    return self.ids[key]

  def _drop(self, key:str) -> None:
    if key in self.ids:
      self.owner.canvas.delete(self.ids.pop(key))

  @override
  def draw(self, fast=False, **kwargs):
    o = self.owner
    canvas, view = o.canvas, o.view
    x1, y1, x2, y2 = o.boundingBox(fast=fast)
    bh = o.bannerHeight()
    border = o.cache['vis/borderColor'] or "black"
    scale = view._scale
    # the banner, and the title in it
    self._item("banner", canvas.create_rectangle, view.viewToWindow([x1, y1, x2, y1 + bh]),
               fill=_blend(canvas, border, 0.18), outline=border)
    # the collapse/expand triangle (see VObject.setCollapsed()), the title, and
    # (right-aligned, in italics) what kind of context it is: rule, query, ...
    fontSize = max(6, int(view._fontSize * scale))
    self._item("toggle", lambda c, **k: canvas.create_text(*c, **k), view.viewToWindow([x1 + o.TOGGLE_WIDTH / 2, y1 + bh / 2]),
               text="\u25b6" if o.collapsed else "\u25bc", anchor="center", fill=o.cache["vis/textColor"] or "black",
               font=(view._fontFace, max(5, int(fontSize * 0.8))))
    self._item("title", lambda c, **k: canvas.create_text(*c, **k), view.viewToWindow([x1 + o.TOGGLE_WIDTH + 2, y1 + bh / 2]),
               text=o.name, anchor="w", fill=o.cache["vis/textColor"] or "black",
               font=(view._fontFace, fontSize, "bold"))
    kinds = ", ".join(p.name for p in o.modelObject.getParents()) if o.modelObject is not None else ""
    self._item("kind", lambda c, **k: canvas.create_text(*c, **k), view.viewToWindow([x2 - 6, y1 + bh / 2]),
               text=kinds, anchor="e", fill="gray35", font=(view._fontFace, fontSize, "italic"))
    # a rule's (or definition's) two panes, left and right
    panes = o.panes()
    if len(panes) == 2 and not o.collapsed:
      left, right = panes
      mid = panes[right][0]
      self._item("divider", canvas.create_line, view.viewToWindow([mid, y1 + bh, mid, y2]), fill=border, dash=(4, 3))
      font = (view._fontFace, max(5, int(view._fontSize * 0.8 * scale)), "italic")
      for key, pane in (("anteLabel", left), ("consLabel", right)):
        px, py = panes[pane][0], panes[pane][1]
        self._item(key, lambda c, **k: canvas.create_text(*c, **k), view.viewToWindow([px + 4, py + 2]),
                   text=pane, anchor="nw", fill="gray50", font=font)
    else:
      for key in ("divider", "anteLabel", "consLabel"):
        self._drop(key)
    # the body isn't an obstacle for overlap avoidance, and the whole window is beneath everything
    if o._shape is not None and o._shape.id is not None:
      canvas.dtag(o._shape.id, "vis/shape")
      canvas.addtag_withtag("context-frame", o._shape.id)
    canvas.tag_lower(o.tag)

  def delete(self):
    if self.deleted: return
    super().delete()
    for key in list(self.ids):
      self._drop(key)


def _blend(canvas, color:str, amount:float) -> str:
  '''*color* mixed *amount* of the way from white (0: white, 1: *color*).'''
  try:
    r, g, b = canvas.winfo_rgb(color)
  except Exception:
    return color
  mix = lambda c: int((c / 257) * amount + 255 * (1 - amount))
  return f'#{mix(r):02x}{mix(g):02x}{mix(b):02x}'


class Highlight(Decorator):
  '''
  A "glow": a filled shape a little larger than the owner, drawn beneath
  everything -- eg: to mark a query's matches (see *VObject.highlight()*). An
  oval for an Oval-shaped owner, a rectangle otherwise. The colour is the
  "gui/highlightColor" preference.
  '''
  PAD = 6
  "How far (screen pixels) the glow extends beyond the owner."

  def __init__(self, owner):
    super().__init__(owner, priority=-20)
    self.id:int|None = None
    self._oval:bool|None = None

  @override
  def draw(self, fast=False, **kwargs):
    from sn.view.graphics.shapes import Oval
    canvas = self.owner.canvas
    color = snPrefs.get("gui/highlightColor", storeDefault="#ffd966", storeType="color",
                        note="The colour of the glow marking highlighted objects (eg: a query's answers).")
    x1, y1, x2, y2 = self.owner.view.viewToWindow(self.owner.boundingBox(fast=fast))
    p = self.PAD
    rect = [x1 - p, y1 - p, x2 + p, y2 + p]
    oval = isinstance(self.owner._shape, Oval)
    if self.id is not None and oval != self._oval: # the owner's shape changed kind
      canvas.delete(self.id)
      self.id = None
    opts = dict(fill=color, outline=color)
    if self.id is None:
      create = canvas.create_oval if oval else canvas.create_rectangle
      self.id = create(rect, state="disabled", tags=[self.owner.tag, "highlight"], **opts)
      self._oval = oval
    else:
      canvas.coords(self.id, rect)
      canvas.itemconfigure(self.id, **opts)
    canvas.tag_lower(self.id) # beneath everything

  def delete(self):
    if self.deleted: return
    super().delete()
    if self.id is not None:
      self.owner.canvas.delete(self.id)
      self.id = None


class ShadowDecorator(Decorator):
  '''
  Draws a plain "duplicate shape, grey, one z-order lower" drop shadow behind
  the owner's own shape -- the standard tk drop-shadow technique, rather than
  anything Pillow/raster-based (too costly to redraw/rescale for this).

  Only drawn for snPrefs["gui/showIndividualShadow"] is True.

  Does NOT yet support "vis/shadowColor" or any other attribute-driven
  customization -- the constructor *kwargs* are the only knob for now. See
  *Shape.shapeOptionsMap* / *Shape.updateKwargs()* for the pattern to follow
  if/when that's added later.
  '''
  def __init__(self, owner, offset:tuple[int,int]=(4,4), **kwargs):
    '''
    :param owner: The *VObject* this decorator is attached to.
    :param offset: [tuple[int,int], default=(4,4)] The (dx, dy) the shadow is
      shifted from the real shape, added directly to the coordinates
      *Shape.points()* / *Oval.boundingBox()* themselves work in -- see
      *draw()*, which otherwise mirrors *Shape.draw()* / *Oval.draw()*
      coordinate handling exactly so the shadow tracks the real shape.
    :type offset: tuple[int,int]
    :param kwargs: extra tk canvas item options for the shadow item; "fill"
      and "outline" default to a plain grey/none if not given.
    '''
    # priority=-10 only orders this decorator among the owner's *own*
    # decorators (see Decorator.priority) -- the actual "always at the very
    # back of the whole canvas" guarantee comes from tag_lower() in draw(),
    # below, not from priority.
    super().__init__(owner, priority=-10)
    self.id:int|None = None # the id of the canvas item
    self.offset = offset
    self.kwargs = kwargs
    
    if "fill"    not in self.kwargs: self.kwargs["fill"]    = "" if owner.cache['vis/fillColor'] == "" else "gray70"
    if "outline" not in self.kwargs: self.kwargs["outline"] = "" if owner.cache['vis/borderColor'] == "" else "gray70"

  def _offsetPoints(self, points:list[float]) -> list[float]:
    dx, dy = self.offset
    return [p + (dx if i%2==0 else dy) for i, p in enumerate(points)]

  def _erase(self):
    if self.id is not None:
      self.owner.canvas.delete(self.id)
      self.id = None

  @override
  def draw(self, fast=False, **kwargs):
    '''
    Shadow visibility isn't a persisted attribute -- like *MarkerContainer*'s
    marker *condition*\\ s, it's just re-derived every draw: Individuals get
    a shadow, Types don't. If *self.owner.modelObject.isType()*, any existing
    shadow item is erased and we return immediately.
    '''
    if not snPrefs.get("gui/showIndividualShadow", storeDefault=True, storeType=bool):
      self._erase()
      return

    self.kwargs.update(kwargs)
    shape = self.owner._shape

    # Oval.draw() renders a true ellipse via create_oval() (unlike the other
    # Shapes, which are all polygons) and applies viewToWindow() consistently
    # on both create and redraw -- mirror that exactly rather than using
    # Oval.points(), which is only a 24-vertex polygon *approximation* used
    # for hit-testing, not what actually gets drawn.
    from sn.view.graphics.shapes import Oval
    if isinstance(shape, Oval):
      bb = self.owner.boundingBox(fast=fast)
      bb = [bb[0]+self.offset[0], bb[1]+self.offset[1], bb[2]+self.offset[0], bb[3]+self.offset[1]]
      if self.id is None:
        self.id = self.owner.canvas.create_oval(self.owner.view.viewToWindow(bb), **self.kwargs)
        self.owner.canvas.itemconfigure(self.id, tags=[self.owner.tag, 'shadow'])
      else:
        self.owner.canvas.coords(self.id, self.owner.view.viewToWindow(bb))
        self.owner.canvas.itemconfigure(self.id, **self.kwargs)
    else:
      # Shape.draw() itself has a create/redraw asymmetry -- create_polygon()
      # gets raw points() with no viewToWindow(), while the redraw coords()
      # call applies viewToWindow() -- mirror it exactly so the shadow stays
      # pixel-aligned with the real shape at any zoom/scroll.
      if self.id is None:
        pts = self._offsetPoints(shape.points(fast=fast))
        self.id = self.owner.canvas.create_polygon(pts, **self.kwargs)
        self.owner.canvas.itemconfigure(self.id, tags=[self.owner.tag, 'shadow'])
      else:
        pts = self._offsetPoints(shape.points(fast=fast))
        self.owner.canvas.coords(self.id, self.owner.view.viewToWindow(pts))
        self.owner.canvas.itemconfigure(self.id, **self.kwargs)

    # Always re-assert absolute-bottom stacking: tag_lower() with a single
    # argument moves this item to the bottom of the *whole* canvas, so this
    # is enough to keep every shadow behind every real shape and decorator,
    # with no need to coordinate across VObjects.
    self.owner.canvas.tag_lower(self.id)

  @override
  def delete(self):
    if self.deleted: return
    super().delete()
    self._erase()
    self.kwargs = None #type: ignore[assignment]

