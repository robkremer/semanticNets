'''
The Developer Guide's example program (see sphinx/source/developer/extending.rst,
which includes these files): a model of pets made in code (*build*), with a
menu item and a tooltip from hooks (*hooks*), a layout of its own
(*gridLayout*), and a program that makes the model and opens it in the editor
(*__main__*):

  PYTHONPATH=tools/docExamples:src:../pythonUtils/src python3.14 -m petsapp /tmp/pets.snm

tools/docExamples/checkPetsapp.py runs it, and checks that it does what the
guide says.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
