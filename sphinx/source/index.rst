Semantic Nets
=============

*Semantic Nets* is an editor for typed semantic networks -- graphs of nodes
and relations, organised by types -- with a reasoner that draws conclusions
from them: what relations follow from the ones you've drawn, what's inherited
down the type hierarchy, what your own rules and definitions conclude, and
what's inconsistent. You draw the network on a canvas (or type commands in a
terminal), and the reasoner's conclusions are shown on the same canvas.

The documentation is in two parts:

- The :doc:`User Guide <user/index>`: how to use the program.
- The :doc:`Developer Guide <developer/index>`: how it's built, how the parts
  fit together and why -- with the full API reference, generated from the
  code's documentation.

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   user/index

.. toctree::
   :maxdepth: 2
   :caption: Developer Guide

   developer/index

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   dev/sn

.. toctree::
   :maxdepth: 2
   :caption: Example Materials

   plugins/index
   modelsDoc/index
   
----------------------------------

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
