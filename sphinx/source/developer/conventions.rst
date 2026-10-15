
Conventions and Testing
=======================

Code style
----------

- Two-space indentation; ``camelCase`` for methods, functions and
  variables, ``CapWords`` for classes, ``UPPER_CASE`` for constants. (The
  commands are the exception: ``new_node`` and the like, because their names
  are the command-line words.)
- Type hints throughout, checked with mypy; ``@override`` on overriding
  methods. From the project directory:

  .. code-block:: bash

     MYPYPATH=../pythonUtils/src python3.14 -m mypy src/sn

  Keep *sn*'s own modules free of errors (those it reports in pythonUtils'
  modules are that project's). Where a check can't be satisfied, a ``#
  type: ignore[code]`` names the error it ignores.
- A leading underscore marks what's private to a class or module -- and, on
  a context, keeps a method from becoming a command.
- Imports that would be circular (eg: the view classes, from each other) are
  made inside the functions that need them.

Docstrings
----------

Docstrings are reStructuredText, and are the API reference (see
:doc:`overview`), so every module, class and public function has one. They
say what something is *for* and *why* it is the way it is; the parameters
are given in Sphinx's field lists:

.. code-block:: python

   def gap(snap:Snapshot, i:int, j:int) -> tuple[float, float, float]:
     '''
     The gap between two objects' edges ...

     :param snap: The layout's snapshot.
     :type snap: Snapshot
     :param i: An object's index in *snap*.
     :type i: int
     :returns: ...
     :rtype: tuple[float, float, float]
     '''

Names of other things are in *italics* (eg: *SNGView.shouldHide()*), or
cross-referenced (``:py:meth:`...```) where the link is worth having. A
constant or attribute is documented by a string just after it.

Changes go through commands
---------------------------

Anything that changes a model or a view, and that the user can do, is a
command on a context (see :doc:`architecture`), not a direct call -- so it
can be undone, and typed. Several steps that make one user action are
grouped in a :py:class:`~util.commandParser.CompositeCommandMgr`, so they're
undone together. Code that only computes or displays (eg: a query, a
report) needn't be a command.

Tests
-----

The tests are in ``test/``, one package per layer (``test_model``,
``test_controller``, ``test_view``, ...), written with :py:mod:`unittest`.
Run them with Python 3.14, with ``src`` and ``../pythonUtils/src`` on the
path, and ``SN_NO_SAVE_PROMPT`` set so nothing asks to save at exit. Eg,
from the project directory:

.. code-block:: bash

   SN_NO_SAVE_PROMPT=1 PYTHONPATH=src:../pythonUtils/src python3.14 -m unittest discover -s test

``test/test_model/test_reasoner.py`` is the reasoner's specification: any
reasoner engine must pass it (see :doc:`reasoner`). ``test_rules.py`` covers
rules and definitions (symmetry, transitivity, attributes, isa conclusions,
new objects, and examples such as *brother*, *bachelor* and
*grandparent*).

Tests that save models must save them somewhere of their own: build the
model under a fresh temporary directory, and check its URL is there before
calling ``save()`` -- never save to a path that could be a real file.

The documentation's examples
----------------------------

The User Guide's screenshots, the example models, and the Developer Guide's
example program are made or checked by the scripts in ``tools/docExamples/``
(see :doc:`overview`). When a change alters what they show, rerun them --
``makeExamples.py``, ``showScene.py <scene> --capture
sphinx/source/images/user``, ``checkPetsapp.py`` -- rather than editing the
pictures or the guide's code by hand.
