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
from dataclasses import dataclass, field
from typing import Optional, Callable, Sequence

import sn
from sn.view.graphics.vobjects import VObject
from util.utils import midpoint, pointInPoly
from util.lineMarks import Mark, MarkLayout, MarkSpecError, MarkedPathIDs, MIDDLE, parseMarks, layoutMarks, \
  drawMarks, drawMarkedPath, paramAtDistance, subPath

logger: sn.SNLogger = sn.getLogger(__name__)

PointType = tuple[float|int, float|int]


# =============================================================================
# Terminator specs
# =============================================================================

@dataclass
class ConnectorTerminators:
  """The marks on a connector: a mark spec (see *util.lineMarks*) for each of
  its four line ends, and one for its middle -- eg "arrow", "o>" (a circle
  behind an arrowhead), ">>", "|||". Each is None/"" for none. A spec that
  can't be read is logged and draws nothing.

  :param source: At the source end of the source→label line.
  :param labelNear: At the label end of the source→label line
    (the side facing source).
  :param labelFar: At the label end of the label→destination line
    (the side facing destination).
  :param destination: At the destination end of the
    label→destination line.
  :param middle: Centred on the label, turned to the line.
  """
  source: Optional[str] = None
  labelNear: Optional[str] = None
  labelFar: Optional[str] = None
  destination: Optional[str] = None
  middle: Optional[str] = None


@dataclass
class ConnectorIDs:
  """Canvas item ids created by a connector-drawing function. Returned so the
  caller can track/delete them; pass a previous result back in via *ids* to
  have the next call update these items in place (coords()/itemconfigure())
  rather than delete-and-recreate them.

  Each line end's marks (and the bits of line among them) are a list of
  items; so are the middle's -- when they're drawn in the middle, that is,
  centred on the label: while the label shows text they go on the line just
  before it instead, as part of the label-near end's stack (see
  *_labelNearMarks()*), and *middleIDs* is empty. *sourceEnd*/*destEnd* are
  where the connector meets its source and destination (view coordinates):
  its lines may stop short of there, for the marks.
  """
  sourceLineID: Optional[int] = None
  destLineID: Optional[int] = None
  sourceTerminatorIDs: list[int] = field(default_factory=list)
  labelNearTerminatorIDs: list[int] = field(default_factory=list)
  labelFarTerminatorIDs: list[int] = field(default_factory=list)
  destTerminatorIDs: list[int] = field(default_factory=list)
  middleIDs: list[int] = field(default_factory=list)
  sourceEnd: Optional[PointType] = None
  destEnd: Optional[PointType] = None

  def sourceIDs(self) -> list[int]:
    """:returns: The source→label half's items: its line and its marks."""
    return ([self.sourceLineID] if self.sourceLineID is not None else []) + \
           self.sourceTerminatorIDs + self.labelNearTerminatorIDs

  def destIDs(self) -> list[int]:
    """:returns: The label→destination half's items: its line and its marks."""
    return ([self.destLineID] if self.destLineID is not None else []) + \
           self.labelFarTerminatorIDs + self.destTerminatorIDs

  def clearSource(self, canvas) -> None:
    """Delete the source→label half's items, and forget them."""
    _deleteItems(canvas, *self.sourceIDs())
    self.sourceLineID, self.sourceTerminatorIDs, self.labelNearTerminatorIDs, self.sourceEnd = None, [], [], None

  def clearDest(self, canvas) -> None:
    """Delete the label→destination half's items, and forget them."""
    _deleteItems(canvas, *self.destIDs())
    self.destLineID, self.labelFarTerminatorIDs, self.destTerminatorIDs, self.destEnd = None, [], [], None

  def deleteAll(self, canvas) -> None:
    """Delete every item this result holds an id for, e.g. before a redraw.

    :param canvas: The canvas the items were created on.
    """
    _deleteItems(canvas, *self.sourceIDs(), *self.destIDs(), *self.middleIDs)


# A drawSmoothConnector()/drawStraightConnector()-shaped function: the
# common signature that lets a caller hold a swappable function pointer.
ConnectorDrawFn = Callable[..., ConnectorIDs]


# =============================================================================
# Geometry helpers — quadratic Bezier through 3 points, and boundary clipping
# =============================================================================

def _sub(a: PointType, b: PointType) -> PointType:
  '''
  *a* - *b*, as vectors.
  '''
  return (a[0] - b[0], a[1] - b[1])


def _add(a: PointType, b: PointType) -> PointType:
  '''
  *a* + *b*, as vectors.
  '''
  return (a[0] + b[0], a[1] + b[1])


_SELF_LOOP_GAP: float = 3.0
'''Target visual gap (in view units) between the two lines of a self-loop
connector (see _selfLoopOffset()) -- deliberately a rough constant ("about 3
units", per Rob) rather than anything derived, so it's the one knob to turn
if the drawn separation looks too tight or too wide.'''


def _selfLoopOffset(cs: PointType, cl: PointType, lineWidth: float) -> PointType:
  """The offset to push *source*'s and *destination*'s shared center apart by
  when *source is destination* (a self-loop) -- see the "source is
  destination" handling in drawSmoothConnector()/drawStraightConnector().

  Without this, source's and destination's centers (and therefore every
  point derived from them) are identical, so the source→label and
  label→destination lines retrace exactly the same path instead of forming
  a visible loop. Add the returned offset to *cs* for the source side and
  subtract it for the destination side (or vice versa -- only the fact that
  they're opposite matters) before doing anything else with those points, so
  every downstream boundary-clip/curve calculation sees two distinct
  "centers" a small distance apart instead of one.

  Offsetting along a true perpendicular to the source/dest→label line would
  need a normalize + rotate-90° (a sqrt and a couple of multiplies) for
  every self-loop redraw. Since this only needs to look reasonable, not be
  exact, picking a single axis -- y for a line closer to horizontal, x for
  one closer to vertical -- gets a visually-parallel-enough offset for a
  couple of comparisons instead, which matters here since redraws can
  happen every frame of a drag/animation (see drawStraightConnector()'s
  docstring).

  :param cs: source's (== destination's) true center point.
  :param cl: label's center point -- only its direction from *cs* matters,
    to decide which axis to offset along.
  :param lineWidth: The line's stroke width (create_line()'s "width" option,
    or its default of 1 if not given), so thicker lines still end up
    visibly separated rather than just touching edge-to-edge.
  :returns: An (x, y) offset with exactly one non-zero component, sized so
    that adding it to one side and subtracting it from the other leaves
    about :py:data:`_SELF_LOOP_GAP` view units of daylight between the two
    lines.
  """
  dx, dy = cl[0] - cs[0], cl[1] - cs[1]
  halfGap = (_SELF_LOOP_GAP + lineWidth) / 2.0
  if abs(dx) >= abs(dy):
    return (0.0, halfGap)  # near-horizontal line -- separate vertically
  else:
    return (halfGap, 0.0)  # near-vertical line -- separate horizontally


def _labelControlPoint(cs: PointType, cl: PointType, cd: PointType) -> PointType:
  """The middle control point P1 of the quadratic Bezier [cs, P1, cd] that
  passes through *cl* exactly at t=0.5.

  Solved from B(0.5) = 0.25*cs + 0.5*P1 + 0.25*cd = cl.
  """
  return (2 * cl[0] - 0.5 * (cs[0] + cd[0]),
          2 * cl[1] - 0.5 * (cs[1] + cd[1]))


def _bezierPoint(p0: PointType, p1: PointType, p2: PointType, t: float) -> PointType:
  """Evaluate the quadratic Bezier [p0, p1, p2] at parameter *t* (0..1).
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
  """
  w0 = (1 - ta) * (1 - tb)
  w1 = ta * (1 - tb) + tb * (1 - ta)
  w2 = ta * tb
  return (w0 * p0[0] + w1 * p1[0] + w2 * p2[0],
          w0 * p0[1] + w1 * p1[1] + w2 * p2[1])


def _insideTest(vobj: VObject) -> Callable[[PointType], bool]:
  """*vobj.containsPt()*, but with its outline worked out once, not for each
  point: for testing many points while it stays put (eg: bisecting, as
  *_findBoundaryParam()* does -- for the thousands of relations an
  expansion brings in, working out the outline for each point took most of
  the time drawing them).
  """
  shape = vobj._shape
  if shape is None or type(vobj).containsPt is not VObject.containsPt:
    return vobj.containsPt
  outline = shape.points()
  return lambda pt: pointInPoly(pt, outline)


def _findBoundaryParam(vobj: VObject|Callable[[PointType], bool], p0: PointType, p1: PointType, p2: PointType,
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

  :param vobj: The shape being clipped against (needs .containsPt()) -- or
    what tests whether a point's in it (see *_insideTest()*).
  :param tInside: A parameter value where _bezierPoint(...) is inside vobj.
  :param tOutside: A parameter value where _bezierPoint(...) is outside vobj.
  """
  inside = vobj.containsPt if isinstance(vobj, VObject) else vobj
  for _ in range(iterations):
    tMid = (tInside + tOutside) / 2
    if inside(_bezierPoint(p0, p1, p2, tMid)):
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
  """
  inside0, inside2 = _insideTest(vobj0), _insideTest(vobj2)
  if not inside0(p0):
    # logger.debug(f'_clippedArc(): {vobj0} does not contain its own center point; skipping clip.')
    return None
  if not inside2(p2):
    # logger.debug(f'_clippedArc(): {vobj2} does not contain its own center point; skipping clip.')
    return None
  if inside0(p2) or inside2(p0):
    # logger.debug(f'_clippedArc(): {vobj0} and {vobj2} appear to overlap; clip may look wrong.')
    pass

  t0 = _findBoundaryParam(inside0, p0, p1, p2, tInside=0.0, tOutside=1.0)
  t2 = _findBoundaryParam(inside2, p0, p1, p2, tInside=1.0, tOutside=0.0)
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
# Marks: the terminators, and the middle's
# =============================================================================

_badSpecs: set[str] = set()
"Mark specs already warned about (see _marks())."


def _marks(spec: Optional[str]) -> tuple[Mark, ...]:
  """The marks *spec* says (see util.lineMarks.parseMarks()) -- or none, with
  a warning the first time, if it can't be read.
  """
  try:
    return parseMarks(spec)
  except MarkSpecError as ex:
    if spec not in _badSpecs:
      _badSpecs.add(str(spec))
      logger.warning(f'Connector marks: {ex}; drawing none.')
    return ()


def _unit(v: PointType, default: PointType = (1.0, 0.0)) -> PointType:
  """*v* scaled to length 1 (*default* if it has none)."""
  n = math.hypot(v[0], v[1])
  return (v[0] / n, v[1] / n) if n > 1e-9 else default


def _deleteItems(canvas, *ids:Optional[int]) -> None:
  """
  Delete canvas items: those that aren't None.

  :param canvas: The canvas.
  :param ids: Canvas item ids, or None.
  """
  for i in ids:
    if i is not None:
      canvas.delete(i)


class _Style:
  """How a connector is drawn, from a drawing function's arguments: its
  colours, its tags, its line's width (as the canvas takes it, and in view
  units, for the marks' sizes) and other line options (eg: dash).
  """

  def __init__(self, view, lineColor: str, fillColor: str, tags: Optional[Sequence[str]], lineKwargs: dict):
    self.view = view
    self.canvas = view.canvas
    self.lineColor, self.fillColor = lineColor, fillColor
    self.tags = list(tags) if tags else []
    opts = dict(lineKwargs)
    opts.pop('fill', None)
    self.strokeWidth = float(opts.pop('width', 1) or 1)
    self.lineOptions = opts
    self.width = self.strokeWidth / float(getattr(view, "_scale", 1.0) or 1.0)

  def half(self, path: Sequence[PointType], startMarks: MarksArg, endMarks: MarksArg,
           priorLine: Optional[int], priorStart: Sequence[int], priorEnd: Sequence[int]) -> MarkedPathIDs:
    """Draw (or update) one of the connector's lines, *path* (2 points, or 3:
    a smooth arc), with the marks *startMarks* and *endMarks* (specs, or
    marks already read) at its ends.
    """
    return drawMarkedPath(self.canvas, path, _asMarks(startMarks), _asMarks(endMarks),
                          MarkedPathIDs(priorLine, list(priorStart), list(priorEnd)),
                          width=self.width, strokeWidth=self.strokeWidth,
                          lineColor=self.lineColor, fillColor=self.fillColor, tags=self.tags,
                          toWindow=self.view.viewToWindow, lineOptions=self.lineOptions)

  def middle(self, layout: MarkLayout, at: PointType, direction: PointType, prior: Sequence[int],
             through: bool) -> list[int]:
    """Draw (or update, or remove) the middle's marks: centred on *at*, turned
    to *direction* -- only while the line runs *through* the label: otherwise
    they're drawn at the label-near end instead (see *_labelNearMarks()*), and
    any drawn here before are removed.
    """
    if not through:
      _deleteItems(self.canvas, *prior)
      return []
    return drawMarks(self.canvas, layout, at, _unit(direction), width=self.width, strokeWidth=self.strokeWidth,
                     lineColor=self.lineColor, fillColor=self.fillColor, tags=self.tags, existing=prior,
                     toWindow=self.view.viewToWindow, lineOptions=self.lineOptions)


MarksArg = Optional[str] | Sequence[Mark]
"A mark spec (see *_marks()*), or marks already read from one."


def _asMarks(marks: MarksArg) -> tuple[Mark, ...]:
  """*marks* as marks: read, if it's a spec."""
  return _marks(marks) if marks is None or isinstance(marks, str) else tuple(marks)


def _labelNearMarks(terminators: ConnectorTerminators, middle: MarkLayout, through: bool) -> tuple[Mark, ...]:
  """The marks at the label end of the source→label line: its own
  (*terminators.labelNear*) -- and, before them, the middle's, while the label
  shows text (not *through*). Drawn centred on the label they'd cover the
  text, so they go on the line just before the label instead, on the source
  side (``--|||--[ text ]----``), laid out as an end stack with the label-near
  marks innermost. (With no source side at all, see *_labelFarMarks()*.)
  """
  near = _marks(terminators.labelNear)
  if through or not middle.marks:
    return near
  return tuple(p.mark for p in middle.marks) + near


def _labelFarMarks(terminators: ConnectorTerminators, middle: MarkLayout, through: bool) -> tuple[Mark, ...]:
  """The marks at the label end of the label→destination line: its own
  (*terminators.labelFar*) -- followed by the middle's, while the label shows
  text and there's no source side to put them on (``[ text ]--|||---->``; see
  *_labelNearMarks()*).
  """
  far = _marks(terminators.labelFar)
  if through or not middle.marks:
    return far
  return far + tuple(p.mark for p in middle.marks)


def _middleStops(middle: MarkLayout) -> tuple[float, float]:
  """How far before and after the label's centre the connector's two lines
  stop, when they run through the label to its middle marks (see
  *throughLabel*): 0 if a line isn't stopped (it meets the other at the centre).
  """
  return (-middle.lowStop if middle.lowStop is not None else 0.0,
          middle.highStop if middle.highStop is not None else 0.0)


def _clippedHalf(vobj: VObject, p0: PointType, p1: PointType, p2: PointType, nodeAtStart: bool,
                 stop: float) -> Optional[tuple[PointType, PointType, PointType]]:
  """The half-arc [p0, p1, p2] clipped to *vobj*'s edge at one end (its start
  if *nodeAtStart*, else its end), and cut back *stop* from its other end --
  the label's centre, when the line runs through the label (see
  *throughLabel*). None if nothing's left (or *vobj* doesn't contain its end).
  """
  inside = _insideTest(vobj)
  path = [p0, p1, p2]
  if nodeAtStart:
    if not inside(p0):
      return None
    t0: Optional[float] = _findBoundaryParam(inside, p0, p1, p2, tInside=0.0, tOutside=1.0)
    t1 = paramAtDistance(path, max(0.0, stop), fromEnd=True)
  else:
    if not inside(p2):
      return None
    t0 = paramAtDistance(path, max(0.0, stop))
    t1 = _findBoundaryParam(inside, p0, p1, p2, tInside=1.0, tOutside=0.0)
  if t0 is None or t1 is None or t0 >= t1:
    return None
  q0, q1, q2 = subPath(path, t0, t1)
  return (q0, q1, q2)


def _drawSingleSegment(label: VObject, other: VObject, otherIsSource: bool,
                        terminators: ConnectorTerminators, prior: ConnectorIDs, style: _Style,
                        middle: MarkLayout, through: bool) -> ConnectorIDs:
  """Draw (or update) the one straight segment from *label* to *other*, with
  its terminators, for when the connector's other endpoint (source or
  destination) is missing entirely -- and the middle's marks.

  With only two points there's nothing left to curve, so this single-
  segment case is the same regardless of whether the caller wanted
  drawSmoothConnector() or drawStraightConnector() — both delegate here for
  it rather than duplicating the clip/line/terminator logic.

  The OTHER side of the connector — whichever of source/destination has no
  VObject at all this call — is left exactly as *prior* had it, rather than
  being deleted: a caller that flips back and forth between one- and
  two-endpoint calls doesn't lose track of ids it may still want.

  :param label: One end of the single line actually drawn (the end both
    lines of a full connector would otherwise pass through).
  :param other: The one present endpoint — whichever of source/destination
    isn't *None*.
  :param otherIsSource: *True* if *other* is standing in for *source* (so
    the terminators.source/labelNear slots, and the source-side result
    fields, apply); *False* if it's standing in for *destination*.
  :param terminators: Same terminators the caller was given.
  :param prior: The caller's *ids* (or an empty ConnectorIDs() if *ids*
    was *None*).
  :param style: How it's drawn (from the caller's arguments).
  :param middle: The middle's marks, laid out.
  :param through: Whether the line runs through the label to its middle
    marks (see *throughLabel*), rather than stopping at its edge.
  """
  cl, co = label.centerPt(), other.centerPt()
  otherEdge = _clipToEdgeStraight(other, _farPointAlong(other, _sub(cl, co)))
  axis = _unit(_sub(cl, co) if otherIsSource else _sub(co, cl)) # (toward the destination)
  if through:
    s1, s2 = _middleStops(middle)
    labelEdge = (cl[0] - axis[0] * s1, cl[1] - axis[1] * s1) if otherIsSource else \
                (cl[0] + axis[0] * s2, cl[1] + axis[1] * s2)
  else:
    labelEdge = _clipToEdgeStraight(label, _farPointAlong(label, _sub(co, cl)))

  result = ConnectorIDs()
  if otherIsSource:
    h = style.half([otherEdge, labelEdge], terminators.source, _labelNearMarks(terminators, middle, through),
                   prior.sourceLineID, prior.sourceTerminatorIDs, prior.labelNearTerminatorIDs)
    result.sourceLineID, result.sourceTerminatorIDs, result.labelNearTerminatorIDs = h.line, h.start, h.end
    result.sourceEnd = otherEdge
    result.destLineID, result.labelFarTerminatorIDs = prior.destLineID, list(prior.labelFarTerminatorIDs)
    result.destTerminatorIDs, result.destEnd = list(prior.destTerminatorIDs), prior.destEnd
  else:
    h = style.half([labelEdge, otherEdge], _labelFarMarks(terminators, middle, through), terminators.destination,
                   prior.destLineID, prior.labelFarTerminatorIDs, prior.destTerminatorIDs)
    result.destLineID, result.labelFarTerminatorIDs, result.destTerminatorIDs = h.line, h.start, h.end
    result.destEnd = otherEdge
    result.sourceLineID, result.sourceTerminatorIDs = prior.sourceLineID, list(prior.sourceTerminatorIDs)
    result.labelNearTerminatorIDs, result.sourceEnd = list(prior.labelNearTerminatorIDs), prior.sourceEnd
  result.middleIDs = style.middle(middle, cl, axis, prior.middleIDs, through)
  return result


# =============================================================================
# The connector-drawing functions
# =============================================================================

def drawSmoothConnector(source: Optional[VObject], label: VObject, destination: Optional[VObject],
                         terminators: Optional[ConnectorTerminators] = None,
                         ids: Optional[ConnectorIDs] = None, *,
                         lineColor: str = 'black', fillColor: str = '',
                         tags: Optional[Sequence[str]] = None,
                         throughLabel: bool = False,
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

  The terminators are marks (see util.lineMarks) at each arc's ends: an arc
  is cut back (exactly, along the curve) where its marks stop it. With
  *throughLabel* (and middle marks), the middle's marks are centred on Cl,
  turned to the curve's direction there (exactly Cd - Cs, for this curve),
  and the two arcs aren't clipped at the label's edge: they run on to the
  middle marks (meeting at Cl if none of them stops the line, eg: bars).
  Without *throughLabel* -- the label shows text -- the middle's marks go on
  the source→label arc just before the label, where they don't cover the
  text (see _labelNearMarks()).

  Assumes source, label and destination don't overlap each other and share
  the same canvas (source.canvas is used).

  If *source is destination* (a self-loop -- the same VObject on both ends),
  their centers are pushed a small distance apart first (see
  _selfLoopOffset()) so the source→label and label→destination arcs come out
  as two distinct, roughly parallel loops instead of retracing the exact
  same curve on top of each other.

  *source* and/or *destination* may be *None*. If exactly one is *None*,
  only a single straight-line segment is drawn -- from *label* to whichever
  of the two is actually present, complete with that segment's own
  terminators -- since a curve needs a third point to bend around; with
  only two points there's nothing to smooth either way, so
  drawStraightConnector() behaves identically in this case. The OTHER
  side's previous canvas items (if any) are left untouched -- see
  _drawSingleSegment(). If *both* are *None* there's nothing to connect to
  at all, so the call is a silent no-op: nothing is drawn or deleted, and
  *ids* (or an empty ConnectorIDs() if *ids* was also *None*) is returned
  unchanged.

  :param source: The VObject the first line starts from, or *None* if
    there is no source object.
  :param label: The VObject both lines connect through.
  :param destination: The VObject the second line ends at, or *None* if
    there is no destination object.
  :param terminators: The mark specs at the four line ends and the middle
    (see ConnectorTerminators), or None for none at all.
  :param ids: A previous call's ConnectorIDs, to update those exact items in
    place instead of creating new ones. None (the default) draws fresh
    items. Every colour/terminator/line option is re-applied from this
    call's arguments regardless — nothing is assumed to carry over from
    whatever *ids* was drawn with.
  :param lineColor: Passed as create_line()'s "fill" (and the marks' line
    colour).
  :param fillColor: Fill colour for "circle" marks.
  :param tags: Canvas tags applied to every item this call touches.
  :param throughLabel: Whether the lines run through the label to its middle
    marks (eg: it shows no text), rather than stopping at its edge -- and so
    whether the middle's marks are drawn in the middle at all, rather than
    on the line just before the label. No effect without middle marks.
  :param lineKwargs: Extra options merged into both create_line() calls
    (width, dash, etc.).
  :returns: The ids of everything drawn, for passing back in on the next
    call (or deleting).
  """
  if terminators is None:
    terminators = ConnectorTerminators()
  prior = ids if ids is not None else ConnectorIDs()

  if source is None and destination is None:
    # logger.debug('drawSmoothConnector(): source and destination are both None; nothing to connect -- no-op.')
    return prior
  style = _Style(label.view, lineColor, fillColor, tags, lineKwargs)
  middle = layoutMarks(_marks(terminators.middle), MIDDLE, style.width)
  through = throughLabel and bool(middle.marks)
  if source is None:
    assert destination is not None
    return _drawSingleSegment(label, destination, False, terminators, prior, style, middle, through)
  if destination is None:
    return _drawSingleSegment(label, source, True, terminators, prior, style, middle, through)

  canvas = source.canvas

  cs, cl, cd = source.centerPt(), label.centerPt(), destination.centerPt()
  if source is destination:
    # A self-loop: cs and cd are the same point, so source→label and
    # label→destination would otherwise retrace the exact same curve on top
    # of each other. Push their "centers" a small distance apart (see
    # _selfLoopOffset()) before any of the curve/boundary-clip math below,
    # so the two arcs come out looking like two parallel loops instead.
    off = _selfLoopOffset(cs, cl, lineKwargs.get('width', 1))
    cs = _add(cs, off)
    cd = _sub(cd, off)
  p1 = _labelControlPoint(cs, cl, cd)
  m1 = midpoint(cs, p1)  # control point of the source→label half-arc
  m2 = midpoint(p1, cd)  # control point of the label→destination half-arc

  if through:
    s1, s2 = _middleStops(middle)
    arcA = _clippedHalf(source, cs, m1, cl, True, s1)
    arcB = _clippedHalf(destination, cl, m2, cd, False, s2)
  else:
    arcA = _clippedArc(source, label, cs, m1, cl)
    arcB = _clippedArc(label, destination, cl, m2, cd)

  result = ConnectorIDs()

  if arcA is not None:
    h = style.half(arcA, terminators.source, _labelNearMarks(terminators, middle, through),
                   prior.sourceLineID, prior.sourceTerminatorIDs, prior.labelNearTerminatorIDs)
    result.sourceLineID, result.sourceTerminatorIDs, result.labelNearTerminatorIDs = h.line, h.start, h.end
    result.sourceEnd = arcA[0]
  else:
    # Boundary clip failed (eg: the label overlaps both ends, side by side):
    # that half isn't drawn, and what was drawn before is deleted -- kept, it
    # would stay where the relation was (eg: after a layout moved
    # everything), an arrowhead on its own. (Its ids stay empty: the next draw
    # that can draw it makes it afresh.)
    _deleteItems(canvas, *prior.sourceIDs())

  if arcB is not None:
    h = style.half(arcB, terminators.labelFar, terminators.destination,
                   prior.destLineID, prior.labelFarTerminatorIDs, prior.destTerminatorIDs)
    result.destLineID, result.labelFarTerminatorIDs, result.destTerminatorIDs = h.line, h.start, h.end
    result.destEnd = arcB[-1]
  else: # (likewise)
    _deleteItems(canvas, *prior.destIDs())

  result.middleIDs = style.middle(middle, cl, _sub(cd, cs), prior.middleIDs, through) # (the curve's direction at cl, exactly)
  return result


def drawStraightConnector(source: Optional[VObject], label: VObject, destination: Optional[VObject],
                           terminators: Optional[ConnectorTerminators] = None,
                           ids: Optional[ConnectorIDs] = None, *,
                           lineColor: str = 'black', fillColor: str = '',
                           tags: Optional[Sequence[str]] = None,
                           throughLabel: bool = False,
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

  The middle's marks are turned to the average of the two lines' directions
  at the label; with *throughLabel*, the lines run on to them along that
  direction, instead of stopping at the label's edge. Without it, they go on
  the source→label line just before the label, as drawSmoothConnector()
  puts them.

  Also like drawSmoothConnector(), *source is destination* (a self-loop) is
  special-cased -- see its docstring and _selfLoopOffset() -- so the two
  segments end up offset and roughly parallel instead of drawn one on top of
  the other.

  *source* and/or *destination* may be *None*, with exactly the same
  behaviour as drawSmoothConnector(): a single terminator-and-all straight
  segment from *label* to whichever one is present if only one is *None*
  (see _drawSingleSegment()), or a silent no-op returning *ids* (or a fresh,
  empty ConnectorIDs()) unchanged if both are.
  """
  if terminators is None:
    terminators = ConnectorTerminators()
  prior = ids if ids is not None else ConnectorIDs()

  if source is None and destination is None:
    # logger.debug('drawStraightConnector(): source and destination are both None; nothing to connect -- no-op.')
    return prior
  style = _Style(label.view, lineColor, fillColor, tags, lineKwargs)
  middle = layoutMarks(_marks(terminators.middle), MIDDLE, style.width)
  through = throughLabel and bool(middle.marks)
  if source is None:
    assert destination is not None
    return _drawSingleSegment(label, destination, False, terminators, prior, style, middle, through)
  if destination is None:
    return _drawSingleSegment(label, source, True, terminators, prior, style, middle, through)

  cs, cl, cd = source.centerPt(), label.centerPt(), destination.centerPt()
  if source is destination:
    # See the identical "source is destination" handling in
    # drawSmoothConnector() -- without it, cs and cd are the same point and
    # the source→label/label→destination segments would be drawn directly
    # on top of each other instead of as two separate, roughly parallel
    # lines.
    off = _selfLoopOffset(cs, cl, lineKwargs.get('width', 1))
    cs = _add(cs, off)
    cd = _sub(cd, off)

  ua, ub = _unit(_sub(cl, cs)), _unit(_sub(cd, cl))
  axis = _unit((ua[0] + ub[0], ua[1] + ub[1]), _unit(_sub(cd, cs))) # (the middle marks' direction)
  sourceEdge = _clipToEdgeStraight(source, _farPointAlong(source, _sub(cl, cs)))
  destEdge = _clipToEdgeStraight(destination, _farPointAlong(destination, _sub(cl, cd)))
  if through:
    s1, s2 = _middleStops(middle)
    labelNearEdge = (cl[0] - axis[0] * s1, cl[1] - axis[1] * s1)
    labelFarEdge = (cl[0] + axis[0] * s2, cl[1] + axis[1] * s2)
  else:
    labelNearEdge = _clipToEdgeStraight(label, _farPointAlong(label, _sub(cs, cl)))
    labelFarEdge = _clipToEdgeStraight(label, _farPointAlong(label, _sub(cd, cl)))

  result = ConnectorIDs()
  h = style.half([sourceEdge, labelNearEdge], terminators.source, _labelNearMarks(terminators, middle, through),
                 prior.sourceLineID, prior.sourceTerminatorIDs, prior.labelNearTerminatorIDs)
  result.sourceLineID, result.sourceTerminatorIDs, result.labelNearTerminatorIDs = h.line, h.start, h.end
  result.sourceEnd = sourceEdge
  h = style.half([labelFarEdge, destEdge], terminators.labelFar, terminators.destination,
                 prior.destLineID, prior.labelFarTerminatorIDs, prior.destTerminatorIDs)
  result.destLineID, result.labelFarTerminatorIDs, result.destTerminatorIDs = h.line, h.start, h.end
  result.destEnd = destEdge
  result.middleIDs = style.middle(middle, cl, axis, prior.middleIDs, through)
  return result
