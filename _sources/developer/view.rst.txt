
The Graphical View
==================

The graphical editor is in :py:mod:`sn.view.graphics`. Its centre is the
view, :py:class:`~sn.view.graphics.sngView.SNGView`, and the view objects it
holds.

Views and view objects
----------------------

.. inheritance-diagram:: sn.view.graphics.vnodes.VNode sn.view.graphics.vrelations.VRelation
   :parts: 1

An :py:class:`~sn.view.graphics.sngView.SNGView` is a persistent database
(a :py:class:`~util.persistence.pRef.PRDb`, saved as a ``.snv`` file) of
:py:class:`~sn.view.graphics.vobjects.VObject`\ s, each showing one
GraphObject of the view's model (or of a model it builds on). The view
observes its model, making and removing VObjects as model objects come and
go; each VObject observes its GraphObject, redrawing when it changes. What a
view saves is what isn't in the model: which objects are shown, their
positions and sizes, whether windows are collapsed, the hidden categories,
the animation settings.

:py:class:`~sn.view.graphics.vobjects.VObject`
  Most of the behaviour: drawing, selection, moving and resizing, menus,
  the attribute editor, markers, context windows, hiding.

:py:class:`~sn.view.graphics.vnodes.VNode`
  A node: little more than a VObject, so that nodes and relations are
  distinct classes.

:py:class:`~sn.view.graphics.vrelations.VRelation`
  A relation: a label (a VObject in its own right, so it can be selected,
  moved and related) and a connector from its source, through the label, to
  its destination. A *floating* label keeps itself midway between its ends
  (at the midpoint of the gap between the ends' edges, so it isn't hidden
  by a large object); dragging it pins it. A relation type never floats: it
  has a place of its own, as a node does (see ``VRelation.floating()``); one
  read from an older view that floated is pinned once the view's drawn
  (``SNGView._pinRelationTypes()``).

Every canvas item a VObject draws carries the VObject's own unique tag
(``vo.tag``), so its items can be found, moved, raised and hidden together.

How a VObject looks is read from its GraphObject's ``vis/`` attributes, with
defaults, through a :py:class:`~sn.view.graphics.vobjects.Cache` (the
effective values are computed once, and refreshed when an attribute
changes).

The view's parts
----------------

.. inheritance-diagram:: sn.view.graphics.sngView.SNGView
   :parts: 1
   :top-classes: sn.view.graphics.viewBase.ViewBase, util.abstractGraph.AbstractGraph, util.observer.Observer, util.dirtyable.Dirtyable

:py:class:`~sn.view.graphics.sngView.SNGView` itself is the view as a
database: making it, saving and reading it, observing its model, and
finding the VObjects that show a model object. Everything else it does is in
parts -- mixins, each a module of its own, that it inherits:

:py:class:`~sn.view.graphics.viewViewport.ViewportMixin`
  Zooming, scrolling, window and view coordinates, painting.

:py:class:`~sn.view.graphics.viewReasoning.ReasoningMixin`
  The reasoning toolbar, and showing what was inferred (below).

:py:class:`~sn.view.graphics.viewLayouts.LayoutsMixin`
  The dynamic, static and animated layouts, and the layout panel (see
  :doc:`layout`).

:py:class:`~sn.view.graphics.viewFiles.FilesMixin`
  Saving, super-models, the model's preferences, the window's menu items,
  locking the view.

:py:class:`~sn.view.graphics.viewVisibility.VisibilityMixin`
  Hidden and erased categories (below).

:py:class:`~sn.view.graphics.viewContainment.ContainmentMixin`
  Context windows: what belongs in each, and keeping the rest out (below).

:py:class:`~sn.view.graphics.viewEditing.EditingMixin`
  New objects and relations, cut, copy and paste, erasing and removing,
  searching.

:py:class:`~sn.view.graphics.viewInput.InputMixin`
  The mouse, keys and menus (below).

What one part uses of another -- the attributes the view sets up, and the
methods one part calls on another -- is declared, for the type checker, in
:py:class:`~sn.view.graphics.viewBase.ViewBase`, which every part inherits;
at run time it adds nothing. A part's module mustn't import
:py:mod:`sn.view.graphics.sngView` (which imports it), except while type
checking: where a part hands the view to something else, it casts itself
to *SNGView*, which it is. The view's commands are in
:py:class:`~sn.view.graphics.sngContext.SNGContext` (see :doc:`architecture`),
and its undo list, :py:class:`~sn.view.graphics.viewCommands.ViewDoList`,
in :py:mod:`sn.view.graphics.viewCommands`.

Drawing: shapes, decorators and connectors
------------------------------------------

A VObject's body is a :py:class:`~sn.view.graphics.shapes.Shape` (rectangle,
rounded rectangle, oval, hexagon, ...: its ``vis/shape``). Everything else
it draws is a :py:class:`~sn.view.graphics.decorators.Decorator`, drawn in
priority order:

- :py:class:`~sn.view.graphics.decorators.WrappingText`: the label, from its
  template (below), wrapped to fit;
- :py:class:`~sn.view.graphics.decorators.MarkerContainer`: the **E**,
  **S**, **T**, **R** and **{}** markers, with tooltips;
- :py:class:`~sn.view.graphics.decorators.ShadowDecorator`: a type's shadow;
- :py:class:`~sn.view.graphics.decorators.Selected`: the selection handles;
- :py:class:`~sn.view.graphics.decorators.Highlight`: a highlight (eg: a
  query's answers);
- :py:class:`~sn.view.graphics.decorators.ContextFrame`: a context window's
  title bar, collapse triangle and panes.

Connectors (:py:mod:`sn.view.graphics.connectors`) are free functions with a
common signature -- smooth or straight -- so the drawing style can be
swapped without the VRelation knowing.

Context windows
---------------

A VObject whose GraphObject is a context (a rule, query, definition, ...) is
drawn as a window (:py:meth:`~sn.view.graphics.vobjects.VObject.isContextWindow`).
The window has *panes*, one per kind of containment it has
(:py:meth:`~sn.view.graphics.vobjects.VObject.panes`): a rule's antecedent
and consequent, a definition's definiendum and definiens, or a single
*contains* pane.

Containment is in the model -- relations from the context, of type
*contains* or a subtype -- and the window keeps it in step with position:
after a move, ``SNGView._updateContainment`` compares where each moved
object was with where it is now, and makes or removes containment relations
(or switches their type, between panes) to match. It's all done with
commands in the same composite command as the move, so a move into a window
and its containment are undone together. A relation drawn whose label lands
in a pane is contained the same way (``_containNewRelation``).

Containment that position shows isn't drawn: a contains arc to an object
inside its window is hidden
(:py:meth:`~sn.view.graphics.vrelations.VRelation.inWindow`). Dragging a
window drags its contents along; collapsing it hides them.

Visibility
----------

Whether a VObject is drawn is decided in one place,
:py:meth:`SNGView.shouldHide() <sn.view.graphics.viewVisibility.VisibilityMixin.shouldHide>`:
it's in a hidden category; or it's a relation to something hidden; or it's a
containment shown by position; or it's inside a collapsed (or hidden)
window. :py:meth:`~sn.view.graphics.vobjects.VObject._applyHidden` applies
the answer, and passes it on to the relations and window contents that
depend on it.

Some canvas items are deliberately ``disabled`` (eg: so they don't take the
mouse). Hiding records each item's state on the VObject (``_priorStates``)
and showing restores it. (The state is kept on the VObject and not in canvas
tags, because redrawing an item resets its tags -- which once made line
segments disappear.)

The categories (system objects, types, rules, ...) are
:py:class:`~util.utils.Categories`: named predicates on model objects. The
view's ``hides`` maps each hidden category to "hide" (not drawn) or "erase"
(taken out of the view), and is saved with the view. Hiding is soft: an
object that's made, or asked for, while its category is hidden is marked
``categoryExempt`` and shown, with a message.

Labels
------

A label is expanded from a template (:py:mod:`sn.view.graphics.labels`), in
the style of shell parameter expansion: ``$name${constraints:+
{$constraints}}``. :py:func:`~sn.view.graphics.labels.expand` does the
expansion, with nested braces; :py:func:`~sn.view.graphics.labels.labelLookup`
supplies the values (attributes, plus ``name``, ``type``, ``constraints``,
...). The template comes from the object's ``vis/label`` attribute, so a type
can set it for all its instances, or else from the preferences.
Tooltips are templates too (``VObject.tooltipFunc()``): ``vis/tooltip``, else
the ``gui/tooltip`` preference, shown in ``vis/tooltipFont`` and wrapped at
``vis/tooltipWrap``. ``$(module:function)`` in a template is replaced by what
a hook returns (see below): ``expand()`` is given a *call* for it
(``VObject.templateCall()``); :py:mod:`~sn.view.graphics.labels` itself knows
nothing of hooks. A hook in a label runs each time the label's drawn; in a
tooltip, only when it's shown.

Hooks: menu items and double-clicks
-----------------------------------

A program that makes a model (eg: pythonParser) can give its objects
behaviour that lasts when the model's saved and read back, through
attributes naming *hooks* (:py:mod:`sn.hooks`): functions, as
``module:function``, made hooks by the ``@hook`` decorator. Only those can be
called, and a hook's module is imported only if it's sn's own or listed in the
``hooks/trustedModules`` preference -- models can come from the web.

- Each ``.menu/<path>`` attribute an object has (its own, or one it inherits:
  eg: set on a type, for all its instances) adds an item to its menu
  (``VObject.addHookMenuItems()``), in a section of their own at the top,
  sorted by path; a ``/`` in the path makes a submenu (eg: ``.menu/Source/Open
  in editor``). An item whose hook can't be called is there, but disabled.
- A ``.doubleClick`` attribute names a hook run on a double-click, instead of
  showing the attributes.

A hook is called as ``fn(obj, context)``: the model object, and a
:py:class:`~sn.hooks.HookContext` -- the attribute that named it, the view
object and view, and what the menu item acts on (the selection, if the object
is selected). ``@hook(appliesTo=...)`` makes one that only applies to some
objects: eg: one set on a type for its instances is left off the type's own
menu. The attributes start with ``.``, so the attribute editor doesn't show
them. (A worked example: :doc:`extending`.)

A hook that shows a file at a line (eg: a function's source) calls
:py:func:`sn.view.graphics.sourceWindow.openSource`: the ``gui/editorCommand``
preference -- a command with ``{path}``, ``{line}`` and ``{url}`` filled in,
run without a shell -- or, if that's empty or can't be run, a read-only
``SourceWindow`` here, scrolled to the line and highlighting the lines asked for.
Eg, to open it at the line in an Eclipse that's running, on a Mac (Eclipse's
launcher would start a second Eclipse, which finds the workspace in use; this
sends the running one the file as "path:line", which it takes apart -- give
your Eclipse app's own path; the first time, macOS asks whether this may
control Eclipse)::

  osascript -e "on run a" -e "tell application \"/Applications/Eclipse.app\" to open (POSIX file (item 1 of a))" -e "end run" {path}:{line}

Reasoning results
-----------------

When the model announces "reasoned", the view refreshes its objects' status
reports (the **E** markers) and shows the model's inferred objects
(``_showInferred``: see :doc:`reasoner`): view objects like any others, drawn
in their own look but faded (``VObject.isInferred()``; the vis cache fades
their colours), relations with dashed lines (dotted if inherited). They take
part in layouts, but aren't saved with the view, and don't make it dirty. The
reasoning toolbar (``reasoningToolbar.py``) at the bottom of the window
reasons and retracts, and says what the last reason found.

Interaction
-----------

Mouse and key bindings are made by the view (``makeBindings``). Dragging is
done live on the canvas, and committed as commands on release
(``context.move``, ``context.resize``), so a drag is one undoable step.
Making a relation uses an *elastic line*
(:py:meth:`~sn.view.graphics.viewInput.InputMixin.elasticLineChoice`): a line
from the origin follows the mouse until a click picks the other end (or
empty space, or **Esc**), then a callback makes the relation.

Menus are built when they're opened, so they always reflect the current
state; the background menu is the view's (``InputMixin.makeMenu``), an object's in
``VObject.makeMenu`` and its subclasses.
