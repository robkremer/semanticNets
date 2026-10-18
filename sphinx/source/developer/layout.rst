Layout
======

A layout arranges a view's objects. They're all in
:py:mod:`sn.view.graphics`, built on one framework,
:py:class:`~sn.view.graphics.layout.LayoutHeuristic`
(:py:mod:`~sn.view.graphics.layout`), and come in three kinds -- a layout may
be more than one:

**static** (``STATIC``)
  Done once, at once, as one undoable command: the **arrange now** menu.
  Eg: :py:class:`~sn.view.graphics.treeLayout.TreeLayout`, "gather nodes".

**dynamic** (``DYNAMIC``)
  The view's current layout (``SNGView.localLayout``: one at a time), which
  keeps it arranged as it changes: the **keep arranged** menu. It places
  what's made or dropped, and after each command adjusts the rest -- in the
  same undo entry. The default is
  :py:class:`~sn.view.graphics.layout.FindFree` ("avoid overlaps").

**animated** (``ANIMATED``)
  Runs in the background until things settle:
  :py:class:`~sn.view.graphics.animatedLayouts.FieldsLayout`, the animation
  layout (below).

.. graphviz::

   digraph layouts {
     rankdir=BT;
     node [shape=box, style=rounded, fontname="Helvetica", fontsize=10];
     edge [arrowhead=empty];
     LayoutHeuristic [label="LayoutHeuristic\n(layout)"];
     FindFree [label="FindFree\n\"avoid overlaps\": dynamic"];
     NoLayout [label="NoLayout\n\"none\": dynamic"];
     GatherLayout [label="GatherLayout\n\"gather nodes\": static"];
     TreeLayout [label="TreeLayout\n\"tree\": static, dynamic\n(treeLayout)"];
     Round [label="_RoundLayout\n(balloonLayout)"];
     TreeRound [label="_TreeRoundLayout"];
     Balloon [label="BalloonLayout\n\"balloon\""];
     Radial [label="RadialLayout\n\"radial\""];
     Hub [label="HubLayout\n\"hubs\""];
     FindFree -> LayoutHeuristic; NoLayout -> LayoutHeuristic; GatherLayout -> LayoutHeuristic;
     TreeLayout -> LayoutHeuristic; Round -> LayoutHeuristic;
     TreeRound -> Round; Hub -> Round; Balloon -> TreeRound; Radial -> TreeRound;
   }

The framework
-------------

A subclass says what it is, and implements what its kinds need:

``NAME``
  What it's called: in the menus, in :py:data:`~sn.view.graphics.layout.LAYOUTS`,
  and in the view's file.

``CATEGORIES``
  The kinds it is: of ``STATIC``, ``DYNAMIC``, ``ANIMATED``.

``PARAMETERS``
  The keyword arguments its constructor takes, as
  :py:class:`~sn.view.graphics.layout.LayoutParameter`\ s: each one's name,
  label, kind (``"relation"``, ``"relations"`` -- a table of relation
  types: see below -- ``"choice"``, ``"int"`` or ``"bool"``), default,
  choices and note, and which kinds of use it matters for. A program
  constructs a layout with them directly (eg: ``TreeLayout(view,
  relations=table)``; or, for the layouts that take a table, the simple way
  for a single relation type: ``TreeLayout(view, relation="includes",
  parentEnd="source")`` -- a relation can be given by name); the user sets
  them in a form made from the list
  (:py:class:`~sn.view.graphics.layoutDialog.LayoutForm`: a table is edited by
  its ``RelationTableEditor``), on the layout's page in the layout panel
  (:py:mod:`~sn.view.graphics.layoutPanel`: see below) -- or, for a program
  that asks, in a modal dialog
  (:py:meth:`~sn.view.graphics.layout.LayoutHeuristic.askParameters`) --
  which
  :py:meth:`~sn.view.graphics.layout.LayoutHeuristic.parameterChanged` can
  adjust as the user changes it.

static: ``targets()``
  Where to move things: each object's new top left corner.
  :py:meth:`~sn.view.graphics.layout.LayoutHeuristic.arrange` makes them a
  :py:class:`~sn.view.graphics.layout.LayoutMoves` command and does it. (Or
  override ``arrange()`` itself, as "gather nodes" does.)

dynamic: ``placeNode()``, ``adjust()``, ``activate()``
  ``placeNode()`` says where something new, or dropped, goes. ``adjust()``
  is called after each command that changed the view, with the command, and
  returns a *LayoutMoves* of what else to move (not done yet), or None.
  ``activate()`` is called when it's made the view's layout
  (``SNGView.setDynamicLayout()``): eg: to arrange things as it will keep
  them.

:py:func:`~sn.view.graphics.layout.registerLayout` (a class decorator) adds
it to *LAYOUTS*, from which the **layout** menu is made, so a program's own
layout is offered with the rest once its module's imported. (See the
Developer Guide's example, :doc:`extending`, for one.)

Moving things
~~~~~~~~~~~~~

:py:class:`~sn.view.graphics.layout.LayoutMoves` is one undoable command of
moves: each object from where it was to where it's going. The first time
it's done, it *tweens* (:py:func:`~sn.view.graphics.layout.tween`): the
objects glide there in a few steps (``TWEEN_STEPS``), unless there are too
many of them, or of their relations, or a step is slow -- then they're moved
at once. Redone or undone, they're moved at once. A tween under way is
finished (:py:func:`~sn.view.graphics.layout.finishTween`) before anything
else is done, undone or saved. A relation label a layout moves is pinned
(stops floating), and floats again when it's undone. ``LayoutMoves.also``
holds anything else it does and undoes -- eg: a tree layout's pins.

Keeping a view arranged
~~~~~~~~~~~~~~~~~~~~~~~

The view's undo list, :py:class:`~sn.view.graphics.viewCommands.ViewDoList`, is
where a dynamic layout gets its say: after each command that changes the
view, it pushes out of context windows whatever doesn't belong in them, and
then asks the view's layout to ``adjust()`` -- and adds the moves to the same
undo entry, so one undo takes back both. Not during a drag (it isn't a
command until it's dropped), nor after a layout's own moves
(``LayoutMoves.isLayout``).

One thing complicates it: the view objects a command makes are drawn *after*
the command is done -- when the model announces what it made
(``SNGView._placeNew()``) -- so at ``adjust()`` time they aren't there yet.
``ViewDoList.adjustAgain()``, called for each new one, lets the layout adjust
once more, when they all are, into the same undo entry.

Saved with the view
~~~~~~~~~~~~~~~~~~~

A view saves its dynamic layout (its ``layout`` property:
:py:meth:`~sn.view.graphics.layout.LayoutHeuristic.state`, read back by
:py:meth:`~sn.view.graphics.layout.LayoutHeuristic.fromState`) -- its name,
its parameters, and anything else it keeps
(:py:meth:`~sn.view.graphics.layout.LayoutHeuristic.extraState`: eg: a tree
layout's pins) -- as text:
``name=tree;relations=includes:shapes:source;direction=right;pins=12,40``.
It also saves the parameters each layout was last used with
(``layoutParameters``), which the dialogs start from
(``SNGView.lastLayoutParameters()``). What an older version saved is
converted as it's read
(:py:meth:`~sn.view.graphics.layout.LayoutHeuristic.upgradeParameters`: eg:
a single ``relation`` and ``parentEnd``, to a table).

Placing one object
------------------

:py:class:`~sn.view.graphics.layout.FindFree`, the default dynamic layout,
finds a clear spot for a new object, near where it was asked for (or below
its supertype), and nudges a dropped object off whatever it landed on.
:py:func:`~sn.view.graphics.layout.gatherShifts` (**gather nodes**) finds
outliers, axis by axis -- gaps between clusters far wider than is typical of
the drawing -- and works out how far to shift them back.

What's arranged
---------------

The tree, balloon, radial and hubs layouts arrange the nodes shown and the
relation types shown alike (:py:func:`~sn.view.graphics.treeLayout.isMember`):
a relation type has a place of its own, as a node does (it never floats:
see :doc:`view`), and is related to others by the relations it's an end of
-- mostly *isa*, between relation types. The relations that relate what's
arranged are the individual relations shown
(:py:func:`~sn.view.graphics.treeLayout.isLink`); a relation type's own ends
-- its domain and range -- aren't, unless the relation table says so, as if
by a relation from the relation type to each
(:py:class:`~sn.view.graphics.treeLayout.Terminal`: a link with no label).

The relation table
~~~~~~~~~~~~~~~~~~

The tree, balloon and radial layouts (and hubs, if asked) follow an ordered
table of relation types,
:py:class:`~sn.view.graphics.relationTable.RelationTable` (their
``relations`` parameter): each row names a relation type -- or ``TERMINALS``,
the relation types' own ends -- and says what its relations do: shape the
trees (``SHAPES``, with which end is the parent), pull things together
(``PULLS``: only for joining trees, and putting the nodes in no tree near
what they're related to), or nothing (``IGNORED``). A row covers its
relation type's subtypes too, unless a subtype has a row of its own: the
most specific row wins, and a relation no row covers pulls together.
:py:class:`~sn.view.graphics.relationTable.RelationRoles` is a table for a
model: each relation's row, role, rank (the row's index: lower wins) and
parent end. ``RelationTable.single()`` is the table that's like a single
relation type -- it shapes the trees, everything else pulls together, the
relation types' ends last -- which is what the layouts start with (for
*isa*), and what an old ``relation`` and ``parentEnd`` become. The dialog
shows a row for each relation type shown in the view
(``RelationTable.expanded()``: a new row does what the row that covered it
did, so nothing changes until the user changes it).

Trees
-----

:py:class:`~sn.view.graphics.treeLayout.TreeLayout` arranges nodes as trees
by the relations whose rows shape them. ``structure()`` finds the trees in
the view: the roots, each node's children (grouped by the row they're
related by, then by which of its relation type's direct subtypes), the
relation to each child, and the nodes in no tree. A node with two parents
goes under the one related by the highest row (then the first made); a
relation that would make a cycle is left out.
:py:meth:`~sn.view.graphics.treeLayout.TreeLayout.related` says what else
something's related to by the rows that aren't ignored. The geometry is a pure function,
:py:func:`~sn.view.graphics.treeLayout.treePositions`, of the trees and the
nodes' sizes: each depth in a line, each parent level with the middle of its
children -- or, *compact*, each subtree tucked in beside the one before
wherever its contour leaves room (much as in Reingold-Tilford). The nodes in
no tree are left, put in rows, or put near what they're related to
(:py:func:`~sn.view.graphics.treeLayout.placeNear`: the nearest free spot,
costing more against the way the trees grow).

Kept arranged, it lays the trees out again after each command, each from
where its root is, keeping children in the order they're in (new ones after,
by name) -- so a tree opens up for what's added, and closes up over what's
removed, and what's beside it moves along by as much. A node the user drops
is *pinned* (``pins``, saved with the view): the root of a tree of its own,
until the next static tree layout clears them.

Round layouts: balloon, radial and hubs
---------------------------------------

:py:mod:`~sn.view.graphics.balloonLayout` has three, sharing
``_RoundLayout``: their groups (trees, or a hub's group) in rows, the nodes
they don't arrange after them, and the labels of the relations from parents
to children on the lines between them. Each group's geometry is again a pure
function:

:py:func:`~sn.view.graphics.balloonLayout.balloonPositions`
  Each node's children on a ring round it, each child's subtree a balloon of
  its own, in its own wedge, spread away from its parent (keeping
  ``PARENT_GAP`` clear toward it).

:py:func:`~sn.view.graphics.balloonLayout.radialPositions`
  Each root in the middle, each depth on a circle round it, each subtree in
  its own wedge: as wide as it needs at its widest depth, centred on its
  parent, and sharing what's spare of its parent's wedge, but no wider (with
  its siblings) than ``RADIAL_SPREAD`` (a half-plane) -- the circles beyond
  are moved out until they fit. So a big subtree stays out beyond its
  parent, instead of being spread round all the room its weight would get.

:py:func:`~sn.view.graphics.balloonLayout.hubForest` and :py:func:`~sn.view.graphics.balloonLayout.hubPositions`
  For a graph that isn't a tree: in each connected group, the nodes with at
  least ``minSpokes`` neighbours are hubs, each other node a spoke of the
  nearest; the hubs on a ring, each one's spokes in a balloon round it. Only
  the core hubs go on the ring (those linked to two others or more, once
  those linked to fewer are pruned, again and again; if none's left, the
  most connected one alone): the rest hang off them, out beyond them, as
  spokes do. Below a hub's own spokes, children spread over no more than
  ``HUB_SPREAD`` (a half-plane), the biggest branches in the middle, so
  branches keep going out rather than curling round the hub. The neighbours
  are by every relation shown -- or, with ``follow="as in the table"``, only
  by the rows of its table that aren't ignored (shaping and pulling together
  count the same), and the relation types' ends if their row isn't.

Balloon and radial find their trees with a *TreeLayout* (``structure()``).
With ``trees="joined"`` (the default), ``_TreeRoundLayout._join()`` then
makes a tree whose root is related, by a row that isn't ignored, to a node
in another tree one of that node's children -- from the top trees (roots
related to no other tree), biggest first -- so related trees are laid out
as one.
Kept arranged, each group is laid out again where it is -- its root (or its
hubs, on average) where it is (:py:func:`~sn.view.graphics.balloonLayout.groupOffset`)
-- and moved off any group before it to the nearest clear place
(:py:func:`~sn.view.graphics.balloonLayout.separateGroups`); a dropped node
that isn't a root is pinned as the root of a group of its own.

Writing a layout
----------------

Keep the geometry apart from the view: a function from plain data (nodes,
their sizes, their relations) to positions, which can be tested without a
window (as ``test_view/test_treeLayout.py`` and ``test_balloonLayout.py``
do); and a *LayoutHeuristic* that gathers that data from the view
(:py:func:`~sn.view.graphics.layout.layoutSize` gives the size a node will be
drawn at) and turns the positions into ``targets()``. Arrange only the nodes
shown (not hidden), and not those in context windows, which keep their own
arrangement. A dynamic layout should be cheap: ``adjust()`` runs after
every command.

The animation layout
--------------------

The animated kind has one layout, which is older than the framework above,
and isn't (yet) a *LayoutHeuristic*: the **animate** menu is its own, and
the view keeps its settings separately (its ``animation`` property).

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
- **Leaps** (:py:func:`~sn.view.graphics.animatedLayouts.leap`), with a
  chance of ``leaps`` × temperature in a step, until the temperature falls
  below ``LEAP_STOP`` -- a mutation: an object out on the canvas, picked at
  random -- for ``LEAP_ANY`` of the leaps, evenly; for the rest, by the
  square of its longest link's stretch
  (:py:func:`~sn.view.graphics.animatedLayouts.stretch`), not its number of
  links, as moving a hub is likelier a fatal mutation -- with any leaves
  near it, is thrown -- uncapped -- to a random place in or around the graph
  (up to ``LEAP_REACH`` of its size beyond its edges), at least ``LEAP_MIN``
  of its diagonal away. Its springs pull it back in by another way,
  disturbing what it's related to. A leap's own move isn't counted in the
  step's movement for cooling; the settling after it is.

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
``heat``, ``leaps``, ``cooling`` -- what the temperature is multiplied by at each
cool-down, which the toolbar shows on a log scale, as the share lost). The view changes them through ``SNGView.setAnimationSetting``,
which both the **view | layout | animate** menu and the layout panel's
**Animate** page (:py:class:`~sn.view.graphics.animationControls.AnimationControls`)
use, and saves the current settings with the view (its ``animation``
property). The panel polls the layout to show its phase and temperature.
