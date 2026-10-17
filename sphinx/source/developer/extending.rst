Building on Semantic Nets
=========================

*Semantic Nets* can be the front end of another program: the program makes
a model -- of a file, a program, a database -- and opens it in the editor,
where the user can look round it, arrange it and reason over it. This page
works through a small example, *petsapp*, step by step; then how such a
program becomes a *plugin*, loaded by the editor and run from its menus --
as the two that come with it are (see the User Guide's
:doc:`../user/exampleApps`).

The example's files are in ``tools/docExamples/petsapp/``, and are included
here as they are. ``tools/docExamples/checkPetsapp.py`` runs them, and checks
that they do what this page says -- run it after changing either:

.. code-block:: bash

   python3.14 tools/docExamples/checkPetsapp.py

To run the program itself (it opens a window on the model it makes):

.. code-block:: bash

   PYTHONPATH=tools/docExamples:src:../pythonUtils/src python3.14 -m petsapp /tmp/pets.snm

Making a model in code
----------------------

A model is made by constructing its objects (see :doc:`model`):
:py:class:`~sn.model.model.Model` with a file's path (or URL), then
:py:class:`~sn.model.model.Node`\ s and
:py:class:`~sn.model.model.Relation`\ s in it, each with its types -- its
*parents*: the system model's are attributes of every model (``m.NODE``,
``m.RELATION``, ``m.ISA``, ``m.RULE``, ...). An object is a type unless it's
made with ``individual=True``. A relation type's ends are its signature (its
domain and range); an individual relation's are what it relates. Attributes
are set by subscript: the object's own data (``rex["age"] = 3``), the
relational properties (``hasAncestor["transitive"] = True``: see
:py:mod:`sn.model.snAttribute`), and its look (the ``vis/`` attributes, set on
a type so that its instances inherit them).

.. literalinclude:: ../../../tools/docExamples/petsapp/build.py
   :caption: petsapp/build.py

Making objects directly, like this, isn't a command (see
:doc:`architecture`): it can't be undone, which is what's wanted for a model
made from scratch. Code that changes a model the user is working on should go
through the commands instead -- eg: ``view.context.new_node(...)`` -- so the
user can undo it.

Saving puts the model in its file (``.snm`` is the usual extension): make it
in a file that isn't there yet -- the program checks, before it starts.
:py:meth:`Model.getDB() <util.persistence.pRef.PRDb.getDB>` reads a model --
or returns it, if it's in memory already.

Reasoning in code
-----------------

The reasoner (see :doc:`reasoner`) needs no window either:
:py:func:`sn.model.reasoner.reason` returns an
:py:class:`~sn.model.reasoner.Inferences`, whose ``report()`` is what the
terminal prints, and whose lists (``inferred``, ``inherited``, ``fired``,
``violations``, ...) and methods (eg: ``related()``) are there for programs
to use. This is the start of ``checkPetsapp.py``:

.. code-block:: python

   from sn.model.model import Model
   from sn.model.reasoner import reason

   m = Model.getDB("file://" + path)
   byName = {o.name: o for o in m.values() if o.name and not (o.isIndividual() and o.isa(m.RELATION))}
   result = reason(m)
   print(result.report(m))
   for rel, src, dst in result.inferred:          # fido -has-ancestor-> rover
     print(f"{src.name} -{rel.name}-> {dst.name}")
   result.related(byName["fido"], byName["has-ancestor"])   # rex, rover

(Individual relations are named after their types, so a lookup by name
leaves them out.) The report says:

.. code-block:: text

   Violations: 0 error(s), 0 warning(s)
   Inferred relations: 1
     fido#268 -has-ancestor-> rover#270
   Rule conclusions: 0
   Inherited relations: 0
   Suggested classifications: 0

Behaviour that lasts: hooks
---------------------------

A model's objects can have menu items, parts of their tooltips and labels,
and double-click actions of the program's own -- which still work when the
model's saved, and opened again later. They're *hooks*
(:py:mod:`sn.hooks`): functions made hooks by the
:py:func:`~sn.hooks.hook` decorator, named in attributes as
``module:function``:

==========================  ===================================================
attribute                   is
==========================  ===================================================
``.menu/<path>``            a menu item (``/`` in *path* makes submenus): the
                            hook's called when it's chosen
``.doubleClick``            what a double-click does, instead of showing the
                            attributes
``$(module:function)``      in a ``vis/label`` or ``vis/tooltip`` template
                            (see :doc:`view`): what the hook returns
==========================  ===================================================

Set on a type, they're inherited by its instances. Each hook is called as
``fn(obj, context)``: the model object, and a
:py:class:`~sn.hooks.HookContext` -- the view object and the view it's used
from, and (for a menu item) the selection it acts on.
``@hook(appliesTo=...)`` makes one that's only offered for some objects:
here, *sayHello* is on the menus of the animals, not of the types.

.. literalinclude:: ../../../tools/docExamples/petsapp/hooks.py
   :caption: petsapp/hooks.py

Hooks are kept in a module of their own -- not the program's ``__main__``,
which is called "__main__" whatever program it is -- so that they can be
found again by name. A model can come from anywhere (eg: the web), so a hook
can be called only if its module has been imported (here, by the program)
or is *trusted*: *sn*'s own, or listed in the user's ``hooks/trustedModules``
preference, in which case it's imported when it's first needed. Otherwise
the menu item is shown, but disabled, and the log says why.

Choose a hook with care for a label: labels are drawn often. Tooltip hooks are
called only when the tooltip is shown.

A layout of its own
-------------------

A layout (see :doc:`layout`) is a
:py:class:`~sn.view.graphics.layout.LayoutHeuristic` subclass, registered
with :py:func:`~sn.view.graphics.layout.registerLayout`, which puts it in the
view's **layout** menu. It says what it is -- its ``NAME``, which kinds of
layout it is (``CATEGORIES``), and the parameters its constructor takes
(``PARAMETERS``, from which the menu's dialog is made) -- and, for a static
layout, where things go: ``targets()``, the top left corner of each object to
move. ``arrange()`` moves them, as one undoable command.

.. literalinclude:: ../../../tools/docExamples/petsapp/gridLayout.py
   :caption: petsapp/gridLayout.py

A program can also construct a layout with its parameters directly, rather
than from the menu: eg: ``GridLayout(view, columns=3).arrange()``.

Opening it in the editor
------------------------

The program makes the model, then starts the editor
(:py:class:`~sn.view.graphics.guiApp.Application`): once it's running, it
opens a window on the model -- a new view of it, *pets.snv* -- fills the
view, arranges it, and saves the view. A view shows only what it's asked to:
here, everything (``showAllModel()``), with the system objects hidden (see
the User Guide's :doc:`../user/viewing`).

.. literalinclude:: ../../../tools/docExamples/petsapp/__main__.py
   :caption: petsapp/__main__.py

Its imports matter: *petsapp.hooks*, so the model's hooks can be called;
*petsapp.gridLayout*, so "grid" is in the layout menu. After that it's the
editor: the user can do what they like with the model, and saving it saves
everything, including the hooks' attributes.

Things a program might do to its view, all of which are commands (one undo
each), on the view (``view``) or its context (``view.context``):

=============================================  ==========================================
call                                           does
=============================================  ==========================================
``view.makeViewObjectForGraphObject(o)``       shows one object (not a command: a
                                               program's setting up)
``view.context.expand(vo, levels=1)``          shows what *vo* is related to, two levels
                                               out
``view.context.visibility(category, mode)``    hides (``"hide"``) or erases (``"erase"``)
                                               a category (eg: ``"isa individuals"``)
``TreeLayout(view, ...).arrange()``            arranges it now (see :doc:`layout`)
``view.setDynamicLayout(TreeLayout(...))``     keeps it arranged
``view.animationLayout()()``                   starts the animation layout
``view.reason()``                              reasons, as the toolbar's ▶
``view.save()``                                saves the view
=============================================  ==========================================

Plugins
-------

A program like *petsapp* runs on its own, making its own
:py:class:`~sn.view.graphics.guiApp.Application`. To be run from the
editor instead -- from a menu, alongside whatever else is open -- it's made
a *plugin* (see :py:mod:`sn.plugins`): a folder in ``~/.sn/plugins/``,
holding a Python package and a *plugin.toml* describing it::

    ~/.sn/plugins/pets/
        plugin.toml
        __init__.py       # register(ctx)
        build.py
        hooks.py

.. code-block:: toml
   :caption: plugin.toml

   name = "Pets"
   version = "1.0"
   description = "A small model of pets and their owners."
   sn-version = "1.0"                # the oldest Semantic Nets it works with
   exclude = ["examples/*.snm"]      # (optional) files not to install: see below

When the editor starts (:py:meth:`Application.startUp()
<sn.view.graphics.guiApp.Application.startUp>`), each plugin's package is
imported as ``snplugins.<folder>`` -- eg: ``snplugins.pets`` -- and its
``register(ctx)`` called, with a
:py:class:`~sn.plugins.PluginContext`: what the plugin may use of the editor,
so that it needn't know how the editor's made.

.. code-block:: python
   :caption: __init__.py

   def register(ctx):
     def makePets():
       from .build import buildModel   # (here: only once it's used -- start-up stays quick)
       ...
       ctx.app.openWindow(path)
     ctx.addMenuItem("Pets...", makePets)              # in the Tools menu
     ctx.addMenuItem("Pets/Feed them all", feed)       # a menu of its own

=======================================================  ==============================================
``ctx.app``                                              the editor (eg: ``openWindow()``)
``ctx.addMenuItem(path, command)``                       a menu item: just a label puts it in
                                                         **Tools**; ``"Menu/Sub/Label"`` in a top-level
                                                         menu of its own (before **Window**), and
                                                         submenus
``ctx.addSeparator(menu)``, ``ctx.menu(path)``           a separator; the menu itself (a ``tk.Menu``)
``ctx.pref(key, default)``, ``ctx.setPref(key, value)``  the plugin's own settings, kept with the
                                                         program's (as ``plugins/<folder>/<key>``)
``ctx.folder``, ``ctx.manifest``, ``ctx.logger``         its folder (eg: for files that come with it),
                                                         its *plugin.toml*, its log
=======================================================  ==============================================

Things to know:

- **Hooks.** Once a plugin's loaded, its package is trusted for hooks (see
  :py:func:`sn.hooks.trust`): a model's ``.menu/...``, ``vis/tooltip`` and
  ``.doubleClick`` can name its functions -- as
  ``snplugins.<folder>.<module>:<function>`` (eg:
  ``snplugins.pythonParser.hooks:showSource``), the same wherever it's
  installed.
- **Failing.** A plugin that's for a later version (``sn-version``), can't
  be imported, has no ``register()``, or raises in it, is left out, and the
  log says why (:py:data:`sn.plugins.problems`); so is one the
  ``plugins/disabled`` setting lists. A menu item's command that raises is
  logged, and shown in an error dialog.
- **Coming with the program.** The plugins in the project's ``plugins/``
  folder are bundled with the app and the .pyz, and copied to
  ``~/.sn/plugins/`` when the editor starts (see
  :py:func:`sn.plugins.installBundled`) if they aren't there, or are an
  older ``version`` there -- so raise the version when changing one. The
  copy leaves out ``exclude``'s files (eg: models made from its examples),
  and its models and views (``.snm``, ``.snv``) are made to refer to where
  they now are. It's a copy, not the files in the app, so that what's in it
  -- eg: an ontology models are built on -- stays at the same place when the
  app's moved or updated.
- **What it can import.** In the packaged app, a plugin has *Semantic
  Nets*, ``util``, and the parts of the standard library the app has: those
  the bundled plugins import are added to it when it's built (see
  ``packaging/bundledPlugins.py``), but a plugin installed later can't bring
  more (eg: pip packages). Run from the source, or the .pyz, it has whatever
  that Python has.
- **Testing.** :py:func:`sn.plugins.importBundled` imports a plugin from the
  project's ``plugins/`` where it is -- not installed, nor registered -- for
  tests and tools (eg: ``test/test_sn/test_pythonSource.py``). ``python3.14
  -m sn --selftest`` installs the bundled plugins in a scratch folder,
  imports all their modules, and makes a model with each, as the "app" and
  "pyz" builds do.

The plugins that come with it
-----------------------------

The two plugins in ``plugins/`` are built as *petsapp* is, on a bigger
scale (their API pages: :doc:`../plugins/index`).

*XMLreader* (:doc:`../plugins/snplugins.XMLreader`)
  :py:mod:`~snplugins.XMLreader.reader` turns an XML file into a model:
  a type per tag (with a look of its own: see
  :py:class:`~snplugins.XMLreader.reader.TypeLooks`), an individual per
  element, and a ``has-<tag>`` relation per nesting.
  :py:mod:`~snplugins.XMLreader.view` asks for the file, opens a window on
  the model, shows its types and expands them a few levels
  (``showTypesAndExpand()``), and starts the animation layout, saving the
  view once it's settled (``startLayout()``). It shows how to fill a view
  from a model's types, and how to wait for the animation layout. Its
  ``register()`` remembers the folder last read from (``ctx.setPref()``),
  and makes the models of its own examples outside its folder (it's
  replaced when a newer version's installed).

*pythonParser* (:doc:`../plugins/snplugins.pythonParser`)
  :py:mod:`~snplugins.pythonParser.parser` parses Python files (with
  :py:mod:`ast`) into a model built on an *ontology* -- a model of the types
  of things in Python programs, *pythonOntology.snm*, kept in the plugin's
  folder and used as the model's super-model, so that every model made from
  it shares its types. The ontology's types carry the hooks
  (:py:mod:`~snplugins.pythonParser.hooks`: **Show source**, the code as
  the tooltip, a double-click to open the editor), so the models get them by
  inheritance. :py:mod:`~snplugins.pythonParser.source` finds a class's
  or function's code in its file as it is now, by name and a hash of its
  text, so the hooks still work after the file's been edited.
  :py:mod:`~snplugins.pythonParser.dialog` shows a dialog (made with
  ``util.utils.ownDialog()``, so that macOS doesn't open it full screen),
  then shows the packages and modules (``showPackages()``) as trees by
  *includes*, kept arranged by a dynamic
  :py:class:`~sn.view.graphics.treeLayout.TreeLayout`. (Its hooks were
  ``sn.exampleApps.pythonParser.hooks:...`` before it was a plugin: models
  made then still work, through :py:data:`sn.hooks.MOVED`.)

Both save into the folder of what they read, asking before they replace
anything there.
