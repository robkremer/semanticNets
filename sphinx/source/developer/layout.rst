
Layout
======

There are two kinds of layout: small, local heuristics that place one object
(:py:mod:`sn.view.graphics.layout`), and the animation layout, which
arranges the whole view (:py:mod:`sn.view.graphics.animatedLayouts`).

Local layout
------------

:py:class:`~sn.view.graphics.layout.FindFree` finds a clear spot for a new
object, near where it was asked for, and nudges a dropped object off
whatever it landed on. :py:func:`~sn.view.graphics.layout.gatherShifts`
(the **gather nodes** command) finds outliers, axis by axis -- gaps between
clusters far wider than is typical of the drawing -- and works out how far
to shift them back.

The animation layout
--------------------

:py:class:`~sn.view.graphics.animatedLayouts.FieldsLayout` is a
force-directed layout, animated: each step moves every object a little, and
the view is redrawn, so the user sees the drawing sort itself out.

Each step works on a :py:class:`~sn.view.graphics.animatedLayouts.Snapshot`:
the view reduced to plain numbers -- the eligible objects' positions and
half-sizes, the links between them, and (with a current) the directed links
and their layers. (Eligible: shown nodes, context windows and relation types;
not individual relations, whose labels float, or what's inside a window,
which moves with it -- see
:py:func:`~sn.view.graphics.animatedLayouts.isEligible`.)
:py:func:`~sn.view.graphics.animatedLayouts.forces` then computes each
object's displacement from it.

The forces
~~~~~~~~~~

- **Repulsion** between every pair, like charges -- but measured between
  their *edges* (:py:func:`~sn.view.graphics.animatedLayouts.gap`), not
  their centres, so that big objects (eg: context windows) get room in
  proportion to their size.
- **Springs** along relations, pulling their ends together, again by the
  gap between their edges.
- With a **current**: a pull toward each object's *layer*. The directed
  relations (eg: isa) are ranked (:py:func:`~sn.view.graphics.animatedLayouts.rankOf`:
  a destination is upstream of its sources), and each rank has a position
  along the current, spaced by the objects' typical size.
- With a current, **heat**: random displacement, decaying with the
  temperature.

Then the mean drift is removed (so the drawing doesn't wander off), each
step is capped by the temperature, and the whole drawing is slid so that
nothing ends up off the top or left of the canvas.

Phases
~~~~~~

A plain force-directed layout gets stuck: a tree drawn upside down can't
turn over, because to get past one another, its nodes would have to pass
through each other's repulsion. So, with a current, a run has phases:

**arranging**
  Repulsion acts only *across* the current between objects in different
  layers (and fully within a layer), so the layers can slide past one
  another. The temperature is held while the drawing's
  :py:func:`~sn.view.graphics.animatedLayouts.misalignment` (how far the
  directed links are from pointing along the current) keeps falling.

**settling**
  The usual cooling: the temperature falls whenever a step makes too little
  progress, until nothing moves much.

**straightening**
  A stronger pull into the layers for a few steps, to line them up.

At the end, floating relation labels are re-placed, and the whole run is
committed as *one* composite command of moves -- each from the object's
position before the run -- so a single undo puts everything back.

Threading
~~~~~~~~~

Tk isn't thread-safe, so the GUI side and the arithmetic are separated. In
:py:class:`~sn.view.graphics.animatedLayouts.FieldsLayout_threaded`, the Tk
thread takes a Snapshot and moves the objects; a worker thread computes the
forces from the Snapshot only, and hands the result back through a queue,
which the Tk thread polls (``after()``). Nothing in the worker touches Tk.

If the user is dragging something when a step is ready, the step is put off
(``suppressLocalLayout``), so the layout never fights the mouse.

Settings
~~~~~~~~

The layout's parameters are attributes of the FieldsLayout (eg:
``flowDirection``, ``flowStrength``, ``e`` (repulsion), ``k`` (springs),
``heat``). The view changes them through ``SNGView.setAnimationSetting``,
which both the **view | animation layout** menu and the
:py:class:`~sn.view.graphics.animationToolbar.AnimationToolbar` use, and
saves the current settings with the view (its ``animation`` property). The
toolbar polls the layout to show its phase and temperature.
