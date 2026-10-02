
Architecture
============

*Semantic Nets* is a model-view-controller program, held together by two
patterns from pythonUtils: **observers**, which keep the views in step with
the models, and **commands**, through which every change is made (and so can
be undone, and typed).

.. graphviz::

   digraph mvc {
     rankdir=LR;
     node [shape=box, style=rounded, fontname="Helvetica", fontsize=11];
     edge [fontname="Helvetica", fontsize=9];
     user [label="user", shape=plaintext];
     terminal [label="terminal pane\n(typed commands)"];
     canvas [label="canvas\n(mouse, menus)"];
     context [label="SNGContext\n(commands, undo list)"];
     model [label="Model\n(Subject)"];
     view [label="SNGView\n(Observer)"];
     vobj [label="VObjects"];
     user -> terminal; user -> canvas;
     terminal -> context [label="parse"];
     canvas -> context [label="call"];
     context -> model [label="do / undo"];
     context -> view [label="do / undo\n(view commands)"];
     model -> view [label="notify\n(new, del, reasoned, ...)", style=dashed];
     model -> vobj [label="notify\n(object changes)", style=dashed];
     view -> vobj -> canvas;
   }

Models and views
----------------

A :py:class:`~sn.model.model.Model` is a database of
:py:class:`~sn.model.model.GraphObject`\ s (see :doc:`model`), and a
:py:class:`~util.observer.Subject`. A view,
:py:class:`~sn.view.graphics.sngView.SNGView`, is another database -- of
:py:class:`~sn.view.graphics.vobjects.VObject`\ s, one per model object it
shows -- and an :py:class:`~util.observer.Observer` of its model. Each
VObject also observes the GraphObject it shows.

So the model never refers to its views: it just announces its changes
("new", "del", "reasoned", "reasoning cleared", and changes to objects), and
every view of it brings itself up to date. Several views of a model (in
several windows) stay consistent this way, and the model can be used, and
tested, with no GUI at all.

Changes are announced in batches. A change made inside a
``Subject.ChangeMgr`` block is recorded, not sent; when the outermost block
ends, all its topics are sent together. A compound change (eg: making a
relation and its isa link) is then seen by the views only once it's
complete.

Commands
--------

Everything that changes a model or a view is a
:py:class:`~util.command.Command`, with ``do()`` and ``undo()``, run through
a :py:class:`~util.command.DoList` -- the undo history. The commands are
defined on **context** classes:

.. graphviz::

   digraph contexts {
     rankdir=BT;
     node [shape=box, style=rounded, fontname="Helvetica", fontsize=11];
     CommandContext [label="util.commandParser.CommandContext\n(undo, redo, help, ...)"];
     ModelContext [label="sn.controller.modelInterface.ModelContext\n(new node, set attribute, reason, ...)"];
     UIContext [label="sn.view.textUserInterface.UIContext\n(format)"];
     SNGContext [label="sn.view.graphics.sngView.SNGContext\n(move, resize, collapse, represent, ...)"];
     SNGContext -> UIContext -> ModelContext -> CommandContext;
   }

A command is declared as a pair:

- a public **signature method** (eg: ``move(self, obj, x, y)``), whose
  parameters and docstring define the command -- its typed arguments, its
  options and its help; and
- a nested **Command class** named after it (``_Move``), which does the work.

:py:class:`~util.commandParser.CommandContext` turns each signature method
into a command-line command (``new_node`` becomes ``new node``; its
parameters without defaults become its arguments, and those with defaults its
options, eg: ``--name`` -- unless they're positional-only, before the ``/``),
and wraps calls to it: calling
``context.move(vo, 10, 20)`` constructs a ``_Move`` and runs it through the
undo list. Arguments are converted by the context's **decoders** (eg: an
object's name typed at the terminal becomes the GraphObject), and missing
ones are filled from its **defaults** (eg: the current model, or view). A
method with no Command class is just a function: callable and typable, but
not undoable (eg: ``show``, ``query``).

So the canvas and the terminal use the very same commands: a drag on the
canvas calls ``context.move()``; typing ``move ...`` parses into the same
call. Either can be undone by either.

Undo is per view
~~~~~~~~~~~~~~~~

Each view has its own context, and so its own undo history -- even when
several views (windows) show the same model. This is deliberate:

- Many commands are about a view (move, resize, collapse, hide, ...). An
  undo history kept with the *model* would have to know which view each of
  those belongs to, and could undo a change in a view the user isn't looking
  at -- which makes no sense to them.
- Models are expected to be shared: several users, on different machines,
  editing one model (eg: on the web). There, a single undo history can't
  work in any case: one user's undo would take back another's work. The
  likely answer then is to give write access to one user at a time.

The cost is that the histories of two views of one model can clash: view A
changes an object, view B changes or deletes it, and then A's undo applies
to a model that has moved on. Commands should therefore be *robust* when
undone: check that what they're undoing still makes sense (the object still
exists, and is still where the command left it), and refuse with a message,
rather than fail or corrupt the model, when it doesn't.

Several commands that make up one action (eg: making a relation and putting
it into a context window) are grouped with a
:py:class:`~util.commandParser.CompositeCommandMgr`: inside its ``with``
block, commands are queued rather than run, and on leaving it they run as a
single :py:class:`~util.command.CompositeCommand` -- one entry in the undo
history, undone in reverse order. Because they're queued, a command in the
group can't see the results of the ones before it: if it needs one (eg: the
relation the previous command will create), it's written to look it up when
it runs (see ``_ContainCreated`` in :py:mod:`sn.view.graphics.sngView`).

The application and its windows
-------------------------------

.. graphviz::

   digraph windows {
     rankdir=TB;
     node [shape=box, style=rounded, fontname="Helvetica", fontsize=11];
     app [label="Application (tk.Tk)\nmenu bar, open/new, settings, quit"];
     win [label="AppWindow (tk.Toplevel)\none per view"];
     toolbar [label="AnimationToolbar\n(optional)"];
     paned [label="AppPanedWidget (tk.PanedWindow)"];
     frame [label="SNGViewFrame\ncanvas + scrollbars"];
     term [label="SNTerminalWidget\nmessages + typed commands"];
     view [label="SNGView\n(owns the window; draws on the canvas)", style="rounded,dashed"];
     app -> win [label=" *"];
     win -> toolbar; win -> paned;
     paned -> frame; paned -> term;
     view -> win [style=dashed, arrowhead=none];
   }

:py:class:`~sn.view.graphics.guiApp.Application` is the Tk root: there's one,
holding the menu bar and the open windows. Each view opens in an
:py:class:`~sn.view.graphics.guiApp.AppWindow`: an
:py:class:`~sn.view.graphics.guiApp.AppPanedWidget` with the canvas above
and the window's terminal below, and the animation toolbar (when shown)
above them both. The window's SNGView draws on the canvas, owns the window's
SNGContext, and routes the terminal's input to it; output (``print`` and
logging) goes to the terminal of the window that has the focus.

Focus also decides the menu bar: when a window gets the focus, its view puts
its own items (eg: **View | Animation toolbar**) into the shared menu bar,
and takes them out when it loses it.

Persistence
-----------

Models and views are both :py:class:`~util.persistence.pRef.PRDb`\ s:
persistent databases of objects, each kept in a file named by a URL. Objects
refer to one another with :py:class:`~util.persistence.pRef.PReference`\ s
-- a URL and an id, or just an id within the same database -- which are
resolved lazily, so a view refers to its model's objects, and a model to the
system model's, across files. See :doc:`model`.
