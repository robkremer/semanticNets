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
      ConnectorTerminators
      ConnectorIDs
    :parts: 2

Draws a source/label/destination connector: two lines (source-to-label,
label-to-destination) that terminate at the edges of their respective
VObjects and, together, trace a single smooth curve from the center of
source's bounding box through the center of label's, to the center of
destination's. source and/or destination may be None -- see
drawSmoothConnector()'s docstring for how a missing endpoint degrades the
shape (a single straight segment to whichever is present, or a no-op if
neither is).

Deliberately kept as free functions rather than methods on any class (a
Strategy/"behaviour" pattern): drawSmoothConnector() and
drawStraightConnector() below share an identical signature, so calling code
can hold a function pointer and swap implementations — e.g. the straight
variant during animation, the smooth one for a settled layout — without
knowing which one it's using. Add further variants the same way.

Redraws update canvas items IN PLACE rather than delete-and-recreate: pass
the ConnectorIDs a previous call returned back in via *ids* and each item
that already exists gets coords()/itemconfigure()'d rather than replaced —
no leaked duplicates if a caller refreshes every animation frame, no z-order
reset, and colours/arrowheads/diameters are picked up fresh from *every*
call (nothing is assumed to stay fixed after the first draw). Pass ids=None
(or omit it) to draw fresh items; ConnectorIDs.deleteAll() is there for
when the connector itself is going away for good.

Created on Aug 28, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>

-------------
'''
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Callable, Sequence

import tkinter as tk

import sn
from sn.view.graphics.vobjects import VObject
from util.utils import midpoint

logger: sn.SNLogger = sn.getLogger(__name__)

PointType = tuple[float, float]


# =============================================================================
# Terminator specs
# =============================================================================

@dataclass
class ConnectorTerminators:
  """The four terminator specs for a connector, one per line end.

  Each is either None/"" (no terminator) or a string in the same format
  VRelation.parseEndShape() already uses elsewhere in this package —
  "arrow(width, length, thickness)" or "circle(diameter)", with the
  parenthesized args optional and defaulted if omitted — kept consistent
  deliberately, even though this module doesn't share code with
  VRelation.parseEndShape()/drawEndShape() (those are instance methods
  entangled with VRelation's own state; duplicating the small amount of
  parsing/drawing logic here as free functions was less risky than
  refactoring already-working code to share it). Provisional: the terminator
  spec format itself is still being designed — this just needs to accept
  something for source/labelNear/labelFar/destination now. "arrow" and
  "circle" are implemented below; add more kinds in parseTerminatorSpec()/
  _drawEndTerminator() as they're defined.

  :param source: Terminator at the source end of the source→label line.
  :param labelNear: Terminator at the label end of the source→label line
    (the side facing source).
  :param labelFar: Terminator at the label end of the label→destination line
    (the side facing destination).
  :param destination: Terminator at the destination end of the
    label→destination line.
  """
  source: Optional[str] = None
  labelNear: Optional[str] = None
  labelFar: Optional[str] = None
  destination: Optional[str] = None


@dataclass
class ConnectorIDs:
  """Canvas item ids created by a connector-drawing function. Returned so the
  caller can track/delete them; pass a previous result back in via *ids* to
  have the next call update these items in place (coords()/itemconfigure())
  rather than delete-and-recreate them.

  :rtype: None
  """
  sourceLineID: Optional[int] = None
  destLineID: Optional[int] = None
  sourceTerminatorID: Optional[int] = None
  labelNearTerminatorID: Optional[int] = None
  labelFarTerminatorID: Optional[int] = None
  destTerminatorID: Optional[int] = None

  def deleteAll(self, canvas) -> None:
    """Delete every item this result holds an id for, e.g. before a redraw.

    :param canvas: The canvas the items were created on.
    :rtype: None
    """
    for fieldID in (self.sourceLineID, self.destLineID, self.sourceTerminatorID,
                    self.labelNearTerminatorID, self.labelFarTerminatorID, self.destTerminatorID):
      if fieldID is not None:
        canvas.delete(fieldID)


# A drawSmoothConnector()/drawStraightConnector()-shaped function: the
# common signature that lets a caller hold a swappable function pointer.
ConnectorDrawFn = Callable[..., ConnectorIDs]


# =============================================================================
# Geometry helpers — quadratic Bezier through 3 points, and boundary clipping
# =============================================================================

def _sub(a: PointType, b: PointType) -> PointType:
  return (a[0] - b[0], a[1] - b[1])


def _labelControlPoint(cs: PointType, cl: PointType, cd: PointType) -> PointType:
  """The middle control point P1 of the quadratic Bezier [cs, P1, cd] that
  passes through *cl* exactly at t=0.5.

  Solved from B(0.5) = 0.25*cs + 0.5*P1 + 0.25*cd = cl.

  :rtype: PointType
  """
  return (2 * cl[0] - 0.5 * (cs[0] + cd[0]),
          2 * cl[1] - 0.5 * (cs[1] + cd[1]))


def _bezierPoint(p0: PointType, p1: PointType, p2: PointType, t: float) -> PointType:
  """Evaluate the quadratic Bezier [p0, p1, p2] at parameter *t* (0..1).

  :rtype: PointType
  """
  mt = 1 - t
  return (mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
          mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1])


def _bezierBlossom(p0: PointType, p1: PointType, p2: PointType, ta: float, tb: float) -> PointType:
  """The middle control point of the EXACT quadratic-Bezier sub-arc spanning
  parameters [ta, tb] of the curve [p0, p1, p2] — i.e. Q1 such that
  [_bezierPoint(p0,p1,p2,ta), Q1, _bezierPoint(p0,p1,p2,tb)] is a quadratic
  Bezier tracing precisely that portion of the original curve (not an
  approximation). This is the symmetric bilinear "blossom"/polar form of a
  quadratic Bezier, b(x,y), evaluated at (ta,tb); b(t,t) == _bezierPoint(t).

  :rtype: PointType
  """
  w0 = (1 - ta) * (1 - tb)
  w1 = ta * (1 - tb) + tb * (1 - ta)
  w2 = ta * tb
  return (w0 * p0[0] + w1 * p1[0] + w2 * p2[0],
          w0 * p0[1] + w1 * p1[1] + w2 * p2[1])


def _findBoundaryParam(vobj: VObject, p0: PointType, p1: PointType, p2: PointType,
                        tInside: float, tOutside: float, iterations: int = 24) -> float:
  """Bisect the Bezier's parameter *t* between a point known to be inside
  *vobj* (tInside) and one known to be outside it (tOutside) to find where
  the curve [p0,p1,p2] crosses *vobj*'s boundary — the curved-path analogue
  of VRelation.findIntersection()'s straight-line bisection, but operating
  directly on the curve's parameter instead of on a straight line between
  two points, so the result is an exact point ON the curve rather than a
  straight-line approximation.

  24 iterations halves the search interval 24 times (~1 part in 16 million
  of the full curve) — comfortably sub-pixel for any on-screen curve length,
  so a fixed count is used rather than a pixel-distance stopping condition.

  :param vobj: The shape being clipped against (needs .containsPt()).
  :param tInside: A parameter value where _bezierPoint(...) is inside vobj.
  :param tOutside: A parameter value where _bezierPoint(...) is outside vobj.
  :rtype: float
  """
  for _ in range(iterations):
    tMid = (tInside + tOutside) / 2
    if vobj.containsPt(_bezierPoint(p0, p1, p2, tMid)):
      tInside = tMid
    else:
      tOutside = tMid
  return tOutside


def _clippedArc(vobj0: VObject, vobj2: VObject, p0: PointType, p1: PointType, p2: PointType,
                 granularity: int = 1) -> Optional[tuple[PointType, PointType, PointType]]:
  """Clip the quadratic Bezier [p0,p1,p2] (p0 == vobj0.centerPt(), p2 ==
  vobj2.centerPt()) to the portion that lies between vobj0's and vobj2's
  boundaries, returning the exact sub-arc's own [Q0, Q1, Q2] control points
  (via _bezierBlossom) — ready to hand straight to a 3-point smooth Tk line.

  Assumes vobj0/vobj2 don't overlap and each contains its own center (true
  for any reasonably-shaped, reasonably-separated pair of nodes); returns
  None — logging a warning — if that assumption looks violated, rather than
  producing a nonsensical clip.

  :rtype: Optional[tuple[PointType, PointType, PointType]]
  """
  if not vobj0.containsPt(p0):
    # logger.debug(f'_clippedArc(): {vobj0} does not contain its own center point; skipping clip.')
    return None
  if not vobj2.containsPt(p2):
    # logger.debug(f'_clippedArc(): {vobj2} does not contain its own center point; skipping clip.')
    return None
  if vobj0.containsPt(p2) or vobj2.containsPt(p0):
    # logger.debug(f'_clippedArc(): {vobj0} and {vobj2} appear to overlap; clip may look wrong.')
    pass

  t0 = _findBoundaryParam(vobj0, p0, p1, p2, tInside=0.0, tOutside=1.0)
  t2 = _findBoundaryParam(vobj2, p0, p1, p2, tInside=1.0, tOutside=0.0)
  if t0 >= t2:
    # logger.debug(f'_clippedArc(): boundary crossings out of order (t0={t0}, t2={t2}); skipping clip.')
    return None

  q0 = _bezierPoint(p0, p1, p2, t0)
  q2 = _bezierPoint(p0, p1, p2, t2)
  q1 = _bezierBlossom(p0, p1, p2, t0, t2)
  return (q0, q1, q2)


def _farPointAlong(vobj: VObject, direction: PointType) -> PointType:
  """A point guaranteed to be outside *vobj*'s shape, out along *direction*
  from its center — used by the straight-line ("fast") connector's edge
  clipping, which (unlike the curved one) bisects between two literal
  points rather than a curve parameter, so it needs an outside point to
  bisect toward.

  :rtype: PointType
  """
  cx, cy = vobj.centerPt()
  dx, dy = direction
  mag = math.hypot(dx, dy)
  if mag == 0:
    dx, dy, mag = 1.0, 0.0, 1.0  # degenerate (coincident centers): arbitrary direction
  bb = vobj.boundingBox()
  diag = math.hypot(bb[2] - bb[0], bb[3] - bb[1])
  k = diag * 2 + 1  # comfortably outside; +1 guards a zero-size bounding box
  return (cx + dx / mag * k, cy + dy / mag * k)


def _clipToEdgeStraight(vobj: VObject, farPt: PointType, granularity: int = 1) -> PointType:
  """Find where the straight line from *farPt* (outside vobj) to vobj's
  center crosses vobj's boundary — the same bisection VRelation.
  findIntersection()/arePtsClose() already do, reimplemented here as a free
  function so it doesn't need a VRelation instance.

  :rtype: PointType
  """
  p1, p2 = farPt, vobj.centerPt()
  while not (abs(p1[0] - p2[0]) < granularity and abs(p1[1] - p2[1]) < granularity):
    pc = midpoint(p1, p2)
    if vobj.containsPt(pc):
      p2 = pc
    else:
      p1 = pc
  return p1


# =============================================================================
# Terminators
# =============================================================================

def parseTerminatorSpec(spec: Optional[str]) -> Optional[tuple[str, list[float]]]:
  """Parse a terminator spec string ("arrow(8,10,3)", "circle(5)", "arrow",
  None, "") into (kind, args). Mirrors VRelation.parseEndShape()'s format.

  :rtype: Optional[tuple[str, list[float]]]
  """
  if not spec:
    return None
  sep = len(spec)
  for i, c in enumerate(spec):
    if not (c.isalpha() or c == ' '):
      sep = i
      break
  kind = spec[:sep].strip().lower()
  if kind not in ('arrow', 'circle'):
    logger.warning(f'parseTerminatorSpec(): unknown terminator kind "{kind}" in spec "{spec}"; ignoring.')
    return None
  try:
    from ast import literal_eval
    args = literal_eval(spec[sep:]) if spec[sep:] else []
    if not isinstance(args, (list, tuple)):
      args = [args]
    args = list(args)
  except Exception:
    logger.warning(f'parseTerminatorSpec(): malformed args in spec "{spec}"; using defaults.')
    args = []
  return kind, args


def _arrowLineOptions(spec: Optional[str], end: str) -> dict:
  """If *spec* is an "arrow" terminator, the create_line() options
  (arrow=/arrowshape=) that draw it at line end *end* ("first" or "last").
  Otherwise {}. Native Tk arrowheads are drawn as part of the line item
  itself — no separate canvas item needed, which is why this returns
  options to merge into the line's own kwargs rather than an id.

  :rtype: dict
  """
  parsed = parseTerminatorSpec(spec)
  if parsed is None or parsed[0] != 'arrow':
    return {}
  args = parsed[1]
  if len(args) == 0:
    args = [8, 10, 3]
  elif len(args) == 1:
    args = [args[0], args[0] * 1.25, args[0] * 0.375]
  elif len(args) == 2:
    args = [args[0], args[1], args[0] * 0.375]
  else:
    args = args[:3]
  return {'arrowKind': end, 'arrowshapeValue': tuple(args)}


def _mergeArrowOptions(nearSpec: Optional[str], farSpec: Optional[str]) -> dict:
  """Combine a line's two possible arrow terminators (at its "first"/near and
  "last"/far ends) into the single arrow=/arrowshape= pair create_line()
  takes — tk.BOTH if both ends want one (using the near end's sizing;
  they're expected to match), tk.FIRST/tk.LAST if only one does.

  Always returns an explicit 'arrow' key — tk.NONE (never a bare {}) when
  neither end wants one — because these options get re-applied via
  itemconfigure() on every redraw: an omitted key would leave a
  previously-set arrowhead in place instead of clearing it when a caller's
  terminator spec changes to "no arrow" on a later call.

  :rtype: dict
  """
  near = _arrowLineOptions(nearSpec, 'first')
  far = _arrowLineOptions(farSpec, 'last')
  if near and far:
    return {'arrow': tk.BOTH, 'arrowshape': near['arrowshapeValue']}
  if near:
    return {'arrow': tk.FIRST, 'arrowshape': near['arrowshapeValue']}
  if far:
    return {'arrow': tk.LAST, 'arrowshape': far['arrowshapeValue']}
  return {'arrow': tk.NONE}


def _drawCircleTerminator(view, spec: Optional[str], atPt: PointType, existingID: Optional[int],
                           lineColor: str, fillColor: str, tags: Optional[Sequence[str]]) -> Optional[int]:
  """Draw (or update, or remove) a "circle" terminator centered at *atPt*.
  Non-circle specs (arrow, None) are handled by the line itself, so this
  always deletes *existingID* and returns None for anything else.

  :rtype: Optional[int]
  """
  canvas = view.canvas
  parsed = parseTerminatorSpec(spec)
  if parsed is None or parsed[0] != 'circle':
    if existingID is not None:
      canvas.delete(existingID)
    return None
  args = parsed[1]
  diam = args[0] if len(args) > 0 else 5
  r = diam / 2.0
  coords = view.viewToWindow([atPt[0] - r, atPt[1] - r, atPt[0] + r, atPt[1] + r])
  if existingID is not None and canvas.type(existingID) == 'oval':
    canvas.coords(existingID, coords)
    canvas.itemconfigure(existingID, fill=fillColor, outline=lineColor)
    return existingID
  if existingID is not None:
    canvas.delete(existingID)
  newID = canvas.create_oval(coords, fill=fillColor, outline=lineColor, tags=list(tags) if tags else [])
  return newID


def _upsertLine(canvas:tk.Canvas, existingID: Optional[int], coords: Sequence[float],
                 tags: Sequence[str], opts: dict) -> int:
  """Create a line item, or update one in place if *existingID* is still a
  live "line" item — coords() to move/reshape it, itemconfigure() to apply
  every option in *opts* fresh (fill, width, arrow, arrowshape, smooth,
  dash, ...), so nothing from a prior draw silently survives a redraw where
  the caller changed it. If *existingID* is set but isn't a line any more
  (or doesn't exist), it's deleted first and a fresh item is created —
  should not normally happen, but is handled rather than raising.

  coords() and itemconfigure(smooth=...) both correctly handle the item's
  point count changing between calls (verified empirically), so this also
  works when *existingID* is being handed between drawSmoothConnector's
  3-point arcs and drawStraightConnector's 2-point segments.

  :param canvas: The canvas the item lives (or will be created) on.
  :param existingID: A previous call's item id for this line, or None to
    always create a new item.
  :param coords: Coordinate sequence for canvas.coords()/create_line().
  :param tags: Canvas tags to (re)apply.
  :param opts: create_line()/itemconfigure() keyword options — fill, width,
    arrow, arrowshape, smooth, dash, etc. — re-specified in full every call.
  :rtype: int
  """
  coords4 = list(coords)
  if existingID is not None and canvas.type(existingID) == 'line':
    canvas.coords(existingID, coords4)
    canvas.itemconfigure(existingID, tags=list(tags) if tags else [], **opts)
    return existingID
  if existingID is not None:
    canvas.delete(existingID)
  return canvas.create_line(coords4, tags=list(tags) if tags else [], **opts)


def _drawSingleSegment(label: VObject, other: VObject, otherIsSource: bool,
                        terminators: ConnectorTerminators, prior: ConnectorIDs,
                        lineColor: str, fillColor: str, tagList: list, lineOpts: dict) -> ConnectorIDs:
  """Draw (or update) the one straight segment from *label* to *other*, with
  its terminators, for when the connector's other endpoint (source or
  destination) is missing entirely.

  With only two points there's nothing left to curve, so this single-
  segment case is the same regardless of whether the caller wanted
  drawSmoothConnector() or drawStraightConnector() — both delegate here for
  it rather than duplicating the clip/line/terminator logic.

  The OTHER side of the connector — whichever of source/destination has no
  VObject at all this call — is left exactly as *prior* had it, the same
  "leave whatever was there before untouched" convention _clippedArc()'s
  failure path already uses above, rather than being deleted: a caller
  that flips back and forth between one- and two-endpoint calls doesn't
  lose track of ids it may still want.

  :param label: One end of the single line actually drawn (the end both
    lines of a full connector would otherwise pass through).
  :param other: The one present endpoint — whichever of source/destination
    isn't *None*.
  :param otherIsSource: *True* if *other* is standing in for *source* (so
    the terminators.source/labelNear slots, and the sourceLineID/
    sourceTerminatorID/labelNearTerminatorID result fields, apply); *False*
    if it's standing in for *destination* (labelFar/destination slots and
    destLineID/labelFarTerminatorID/destTerminatorID fields).
  :param terminators: Same terminators the caller was given.
  :param prior: The caller's *ids* (or an empty ConnectorIDs() if *ids*
    was *None*).
  :param lineColor: Same as drawSmoothConnector()'s *lineColor*.
  :param fillColor: Same as drawSmoothConnector()'s *fillColor*.
  :param tagList: Canvas tags, already coerced to a list by the caller.
  :param lineOpts: The base {'fill': lineColor, **lineKwargs} dict the
    caller already built.
  :rtype: ConnectorIDs
  """
  canvas = label.canvas
  view = label.view
  cl, co = label.centerPt(), other.centerPt()
  labelEdge = _clipToEdgeStraight(label, _farPointAlong(label, _sub(co, cl)))
  otherEdge = _clipToEdgeStraight(other, _farPointAlong(other, _sub(cl, co)))

  labelTerm = terminators.labelNear if otherIsSource else terminators.labelFar
  otherTerm = terminators.source if otherIsSource else terminators.destination
  priorLineID = prior.sourceLineID if otherIsSource else prior.destLineID
  priorLabelTermID = prior.labelNearTerminatorID if otherIsSource else prior.labelFarTerminatorID
  priorOtherTermID = prior.sourceTerminatorID if otherIsSource else prior.destTerminatorID

  opts = dict(lineOpts)
  opts['smooth'] = False
  if otherIsSource:
    # [otherEdge, labelEdge] / (source, labelNear) -- matches the ordering
    # the full two-object case uses for this same (source-to-label) line.
    opts.update(_mergeArrowOptions(otherTerm, labelTerm))
    coords = [otherEdge[0], otherEdge[1], labelEdge[0], labelEdge[1]]
  else:
    # [labelEdge, otherEdge] / (labelFar, destination) -- matches the
    # ordering the full two-object case uses for the label-to-destination line.
    opts.update(_mergeArrowOptions(labelTerm, otherTerm))
    coords = [labelEdge[0], labelEdge[1], otherEdge[0], otherEdge[1]]

  lineID = _upsertLine(canvas, priorLineID, label.view.viewToWindow(coords), tagList, opts)
  labelTermID = _drawCircleTerminator(view, labelTerm, labelEdge, priorLabelTermID, lineColor, fillColor, tagList)
  otherTermID = _drawCircleTerminator(view, otherTerm, otherEdge, priorOtherTermID, lineColor, fillColor, tagList)

  result = ConnectorIDs()
  if otherIsSource:
    result.sourceLineID = lineID
    result.labelNearTerminatorID = labelTermID
    result.sourceTerminatorID = otherTermID
    result.destLineID = prior.destLineID
    result.labelFarTerminatorID = prior.labelFarTerminatorID
    result.destTerminatorID = prior.destTerminatorID
  else:
    result.destLineID = lineID
    result.labelFarTerminatorID = labelTermID
    result.destTerminatorID = otherTermID
    result.sourceLineID = prior.sourceLineID
    result.labelNearTerminatorID = prior.labelNearTerminatorID
    result.sourceTerminatorID = prior.sourceTerminatorID
  return result


# =============================================================================
# The connector-drawing functions
# =============================================================================

def drawSmoothConnector(source: Optional[VObject], label: VObject, destination: Optional[VObject],
                         terminators: Optional[ConnectorTerminators] = None,
                         ids: Optional[ConnectorIDs] = None, *,
                         lineColor: str = 'black', fillColor: str = '',
                         tags: Optional[Sequence[str]] = None,
                         **lineKwargs) -> ConnectorIDs:
  """Draw source→label and label→destination as two lines that terminate at
  the edges of their respective VObjects and together trace ONE smooth
  quadratic-Bezier curve running from the center of source's bounding box,
  through the center of label's, to the center of destination's.

  The curve is a single quadratic Bezier [Cs, P1, Cd] chosen so it passes
  exactly through Cl (label's center) at t=0.5 (see _labelControlPoint), then
  split at that point into two Bezier arcs — mathematically the same curve,
  so there's no kink at the join even though it's drawn as two line items.
  Each arc is then clipped to the exact portion between its two shapes'
  boundaries (_clippedArc, via boundary-parameter bisection against
  VObject.containsPt() — the curved-path analogue of VRelation.
  findIntersection()'s straight-line bisection) and rendered as a Tk
  create_line() with exactly 3 points and smooth=True — Tk's documented
  control-point quadratic-bezier behaviour for a 3-point smoothed line,
  so the rendered curve matches this function's own math exactly.

  Assumes source, label and destination don't overlap each other and share
  the same canvas (source.canvas is used).

  *source* and/or *destination* may be *None*. If exactly one is *None*,
  only a single straight-line segment is drawn -- from *label* to whichever
  of the two is actually present, complete with that segment's own
  terminators -- since a curve needs a third point to bend around; with
  only two points there's nothing to smooth either way, so
  drawStraightConnector() behaves identically in this case. The OTHER
  side's previous canvas items (if any) are left untouched, exactly as
  when a boundary clip fails elsewhere in this module -- see
  _drawSingleSegment(). If *both* are *None* there's nothing to connect to
  at all, so the call is a silent no-op: nothing is drawn or deleted, and
  *ids* (or an empty ConnectorIDs() if *ids* was also *None*) is returned
  unchanged.

  :param source: The VObject the first line starts from, or *None* if
    there is no source object.
  :param label: The VObject both lines connect through.
  :param destination: The VObject the second line ends at, or *None* if
    there is no destination object.
  :param terminators: The four terminator specs (source/labelNear/labelFar/
    destination), or None for no terminators at all.
  :param ids: A previous call's ConnectorIDs, to update those exact items in
    place instead of creating new ones. None (the default) draws fresh
    items. Every colour/terminator/line option is re-applied from this
    call's arguments regardless — nothing is assumed to carry over from
    whatever *ids* was drawn with.
  :param lineColor: Passed as create_line()'s "fill" (and terminators'
    outline colour) unless overridden via **lineKwargs.
  :param fillColor: Fill colour for "circle" terminators.
  :param tags: Canvas tags applied to every item this call touches.
  :param lineKwargs: Extra options merged into both create_line() calls
    (width, dash, etc.).
  :returns: The ids of everything drawn, for passing back in on the next
    call (or deleting).
  :rtype: ConnectorIDs
  """
  if terminators is None:
    terminators = ConnectorTerminators()
  prior = ids if ids is not None else ConnectorIDs()
  tagList = list(tags) if tags else []
  lineOpts = {'fill': lineColor, **lineKwargs}

  if source is None and destination is None:
    # logger.debug('drawSmoothConnector(): source and destination are both None; nothing to connect -- no-op.')
    return prior
  if source is None:
    assert destination is not None
    return _drawSingleSegment(label, destination, False, terminators, prior, lineColor, fillColor, tagList, lineOpts)
  if destination is None:
    return _drawSingleSegment(label, source, True, terminators, prior, lineColor, fillColor, tagList, lineOpts)

  canvas = source.canvas
  view = source.view

  cs, cl, cd = source.centerPt(), label.centerPt(), destination.centerPt()
  p1 = _labelControlPoint(cs, cl, cd)
  m1 = midpoint(cs, p1)  # control point of the source→label half-arc
  m2 = midpoint(p1, cd)  # control point of the label→destination half-arc

  arcA = _clippedArc(source, label, cs, m1, cl)
  arcB = _clippedArc(label, destination, cl, m2, cd)

  result = ConnectorIDs()

  if arcA is not None:
    q0, q1, q2 = arcA
    opts = dict(lineOpts)
    opts.update(_mergeArrowOptions(terminators.source, terminators.labelNear))
    opts['smooth'] = True
    result.sourceLineID = _upsertLine(
        canvas, prior.sourceLineID,
        source.view.viewToWindow([q0[0], q0[1], q1[0], q1[1], q2[0], q2[1]]),
        tagList, opts)
    result.sourceTerminatorID = _drawCircleTerminator(
        view, terminators.source, q0, prior.sourceTerminatorID, lineColor, fillColor, tagList)
    result.labelNearTerminatorID = _drawCircleTerminator(
        view, terminators.labelNear, q2, prior.labelNearTerminatorID, lineColor, fillColor, tagList)
  else:
    # Boundary clip failed (logged already by _clippedArc) — leave whatever
    # was there before untouched rather than losing track of its id.
    result.sourceLineID = prior.sourceLineID
    result.sourceTerminatorID = prior.sourceTerminatorID
    result.labelNearTerminatorID = prior.labelNearTerminatorID

  if arcB is not None:
    q0, q1, q2 = arcB
    opts = dict(lineOpts)
    opts.update(_mergeArrowOptions(terminators.labelFar, terminators.destination))
    opts['smooth'] = True
    result.destLineID = _upsertLine(
        canvas, prior.destLineID,
        source.view.viewToWindow([q0[0], q0[1], q1[0], q1[1], q2[0], q2[1]]),
        tagList, opts)
    result.labelFarTerminatorID = _drawCircleTerminator(
        view, terminators.labelFar, q0, prior.labelFarTerminatorID, lineColor, fillColor, tagList)
    result.destTerminatorID = _drawCircleTerminator(
        view, terminators.destination, q2, prior.destTerminatorID, lineColor, fillColor, tagList)
  else:
    result.destLineID = prior.destLineID
    result.labelFarTerminatorID = prior.labelFarTerminatorID
    result.destTerminatorID = prior.destTerminatorID

  return result


def drawStraightConnector(source: Optional[VObject], label: VObject, destination: Optional[VObject],
                           terminators: Optional[ConnectorTerminators] = None,
                           ids: Optional[ConnectorIDs] = None, *,
                           lineColor: str = 'black', fillColor: str = '',
                           tags: Optional[Sequence[str]] = None,
                           **lineKwargs) -> ConnectorIDs:
  """Same signature and result shape as drawSmoothConnector() — a drop-in
  "fast" alternative that draws two straight lines (source-to-label,
  label-to-destination) instead of a smooth curve. Intended for contexts
  where the curve's cost isn't worth it, e.g. every frame of a drag/animation,
  with a swap to drawSmoothConnector() once things settle — hence the
  identical signature: calling code can hold either as a plain function
  pointer and not care which one it has.

  Like drawSmoothConnector(), passing a previous call's ConnectorIDs back in
  via *ids* updates those items in place (and works even if *ids* was last
  drawn by drawSmoothConnector() — the same items just get reshaped from a
  3-point smoothed arc to a 2-point straight segment).

  *source* and/or *destination* may be *None*, with exactly the same
  behaviour as drawSmoothConnector(): a single terminator-and-all straight
  segment from *label* to whichever one is present if only one is *None*
  (see _drawSingleSegment()), or a silent no-op returning *ids* (or a fresh,
  empty ConnectorIDs()) unchanged if both are.

  :rtype: ConnectorIDs
  """
  if terminators is None:
    terminators = ConnectorTerminators()
  prior = ids if ids is not None else ConnectorIDs()
  tagList = list(tags) if tags else []
  lineOpts = {'fill': lineColor, **lineKwargs}

  if source is None and destination is None:
    # logger.debug('drawStraightConnector(): source and destination are both None; nothing to connect -- no-op.')
    return prior
  if source is None:
    assert destination is not None
    return _drawSingleSegment(label, destination, False, terminators, prior, lineColor, fillColor, tagList, lineOpts)
  if destination is None:
    return _drawSingleSegment(label, source, True, terminators, prior, lineColor, fillColor, tagList, lineOpts)

  canvas = source.canvas
  view = source.view

  cs, cl, cd = source.centerPt(), label.centerPt(), destination.centerPt()

  sourceEdge = _clipToEdgeStraight(source, _farPointAlong(source, _sub(cl, cs)))
  labelNearEdge = _clipToEdgeStraight(label, _farPointAlong(label, _sub(cs, cl)))
  labelFarEdge = _clipToEdgeStraight(label, _farPointAlong(label, _sub(cd, cl)))
  destEdge = _clipToEdgeStraight(destination, _farPointAlong(destination, _sub(cl, cd)))

  result = ConnectorIDs()

  opts = dict(lineOpts)
  opts.update(_mergeArrowOptions(terminators.source, terminators.labelNear))
  opts['smooth'] = False
  result.sourceLineID = _upsertLine(
      canvas, prior.sourceLineID,
      source.view.viewToWindow([sourceEdge[0], sourceEdge[1], labelNearEdge[0], labelNearEdge[1]]),
      tagList, opts)
  result.sourceTerminatorID = _drawCircleTerminator(
      view, terminators.source, sourceEdge, prior.sourceTerminatorID, lineColor, fillColor, tagList)
  result.labelNearTerminatorID = _drawCircleTerminator(
      view, terminators.labelNear, labelNearEdge, prior.labelNearTerminatorID, lineColor, fillColor, tagList)

  opts = dict(lineOpts)
  opts.update(_mergeArrowOptions(terminators.labelFar, terminators.destination))
  opts['smooth'] = False
  result.destLineID = _upsertLine(
      canvas, prior.destLineID,
      source.view.viewToWindow([labelFarEdge[0], labelFarEdge[1], destEdge[0], destEdge[1]]),
      tagList, opts)
  result.labelFarTerminatorID = _drawCircleTerminator(
      view, terminators.labelFar, labelFarEdge, prior.labelFarTerminatorID, lineColor, fillColor, tagList)
  result.destTerminatorID = _drawCircleTerminator(
      view, terminators.destination, destEdge, prior.destTerminatorID, lineColor, fillColor, tagList)

  return result
