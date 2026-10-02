
Overview
========

Repositories
------------

*Semantic Nets* lives in two repositories, checked out side by side:

``semanticNets``
  The application: the ``sn`` package (in ``src/``), its tests (``test/``),
  this documentation (``sphinx/``), and the launch scripts.

``pythonUtils``
  A general-purpose library the application builds on, the ``util``
  package: persistence (databases of objects, serialization), attributes
  with inheritance, the command/undo framework and command-line parser, the
  observer pattern, the terminal widget, the attribute editor, tooltips and
  preferences. None of it knows about semantic networks. Its documentation
  is separate, and linked to from here.

Everything runs on **Python 3.14**, with Tkinter for the GUI and the `clingo
<https://potassco.org/clingo/>`_ Python package for the reasoner.

Packages
--------

.. graphviz::

   digraph packages {
     rankdir=TB;
     node [shape=box, style=rounded, fontname="Helvetica", fontsize=11];
     sn [label="sn\n(logging, preferences, saving at exit)"];
     model [label="sn.model\nModel, GraphObject, Node, Relation\nreasoner, clingoReasoner, constraints"];
     controller [label="sn.controller\nModelContext: the commands"];
     view [label="sn.view\nUIContext, terminals"];
     graphics [label="sn.view.graphics\nApplication, SNGView, VObjects,\ndecorators, shapes, layouts"];
     util [label="util (pythonUtils)", style="rounded,dashed"];
     graphics -> view -> controller -> model -> sn;
     graphics -> model;
     {model controller view graphics} -> util [style=dotted];
   }

``sn``
  The package's ``__init__``: the logger, the preferences (``snPrefs``, kept
  in ``~/.sn.xml``), and the offer to save modified models at exit.

``sn.model``
  The data: :py:class:`~sn.model.model.Model` (a database of
  :py:class:`~sn.model.model.GraphObject`\ s), its nodes and relations, the
  system model (:py:class:`~sn.model.TopModel`), variable constraints, and
  the reasoner. It has no user interface.

``sn.controller``
  :py:class:`~sn.controller.modelInterface.ModelContext`: every operation on
  a model, as a command -- callable from code, parsable from a command line,
  and undoable.

``sn.view``
  The text interface: :py:class:`~sn.view.textUserInterface.UIContext`
  (adds output formatting to the commands) and the terminals.

``sn.view.graphics``
  The graphical editor: the application and its windows, the view
  (:py:class:`~sn.view.graphics.sngView.SNGView`) and its objects
  (:py:class:`~sn.view.graphics.vobjects.VObject`), their decorations and
  shapes, and the layouts.

Running it
----------

From the project's top directory:

``./sng [file]``
  The graphical editor: ``python3.14 -m sn.view.graphics.guiApp``.

``./sn [file]``
  The text interface: ``python3.14 -m sn.view.textUserInterface``.

Both need ``src`` and ``../pythonUtils/src`` on ``PYTHONPATH`` (the scripts
set it up).

Set the environment variable ``SN_NO_SAVE_PROMPT`` (to anything) to stop the
program offering to save modified models and views at exit -- for automated
runs such as the tests, which would otherwise ask once for every model they
touch. (It doesn't save them either.)

Building the documentation
--------------------------

The documentation is built with Sphinx (under Python 3.14, with the *furo*
theme and graphviz) by two targets of ``build.xml``:

``rebuildAutoDoc``
  Regenerates the API reference, ``sphinx/source/dev/``, from the code with
  ``sphinx-apidoc``. The directory is wiped and rewritten each time, so don't
  put anything else there.

``doc``
  Builds the HTML, into ``sphinx/build/html``.

The rest of ``sphinx/source`` -- this guide and the User Guide -- is written
by hand. Images go in ``sphinx/source/images``. The pythonUtils documentation
is linked through intersphinx, from its own build's ``objects.inv``: build
that first.

Packaging
---------

``build.xml`` also packages the program, using the files in ``packaging/``:

``app``
  ``dist/Semantic Nets.app``: a stand-alone macOS app, with its own Python,
  Tk and clingo, made by PyInstaller (``packaging/semanticNets.spec``). It
  bundles the HTML documentation (for its Help menu) and the example models,
  ``src/sn/examples/``, which it copies to *~/Documents/Semantic Nets
  Examples* and opens on its first launch. It's built for the building Mac's
  architecture: on an Apple silicon Mac, it runs on Apple silicon Macs with
  macOS 11 or later. It's signed *ad hoc*: on another Mac, it has to be opened
  the first time with Control-click | Open.

``appUniversal``
  ``dist/universal/Semantic Nets.app``: the same, *universal* -- for Intel
  Macs (macOS 10.15 or later) and Apple silicon Macs (11 or later) both, and
  so about half as big again. Python and Tk are universal already, but PyPI
  has only separate Intel and Apple silicon builds of clingo and cffi: the
  ``universalWheels`` target (``packaging/makeUniversalWheels.py``) fuses them
  and installs the results in the build venv. The self-test runs it twice:
  natively, and as Intel under Rosetta.

``dmg``, ``dmgUniversal``
  ``dist/SemanticNets-<version>.dmg`` and ``...-universal.dmg``: the
  installers -- disk images with the app, an Applications folder to drag it
  to, and a Read Me (``packaging/dmgSettings.py``,
  ``packaging/ReadMeFirst.txt``, whose ``@REQUIREMENTS@`` line each target
  fills in).

``pyz``
  ``dist/SemanticNets-<version>.pyz``: the program as one zip file, for
  people who already have Python 3.14 (and the packages in
  ``packaging/requirements.txt``, eg: clingo, which is compiled, so can't be
  zipped): ``python3.14 SemanticNets-1.0.pyz``.

``dist``
  All of these (and the documentation).

The tools (PyInstaller, dmgbuild, delocate, Pillow) are kept in a build-only
virtualenv, ``.venv-build``, which the ``venv`` target makes the first time
(this needs the network). After building the app and the .pyz, the targets
run them with ``--selftest``, which reasons over the family example without
opening a window, and fails the build if the conclusions aren't right. That
catches anything the build left out (eg: clingo's compiled parts).

Because the program's data files are read as *package data*
(:py:mod:`importlib.resources`) -- the clingo rule base, the examples -- they
are found the same way in the source tree, in the .pyz, and in the app.
``sn.resourcePath()`` finds the rest (the bundled documentation). A packaged
app runs in ``/``, so its log goes to *~/Library/Logs/Semantic Nets/*.

The app's icon, ``packaging/sn.icns``, is a placeholder, drawn by
``packaging/makeIcon.py`` (the ``icon`` target).
