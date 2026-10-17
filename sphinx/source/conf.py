# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
print('**********', os.getcwd())
#from objc._convenience import __call__
sys.path.insert(0, os.path.abspath('../..'))
sys.path.insert(0, os.path.abspath('..'))
sys.path.insert(0, os.path.abspath('../src'))
#sys.path.insert(0, os.path.abspath('../src/util'))
sys.path.insert(0, os.path.abspath('../../../pythonUtils/src'))
sys.path.insert(0, os.path.abspath('../../src'))
#sys.path.insert(0, os.path.abspath('../../src/util'))
sys.path.insert(0, os.path.abspath('/opt/homebrew/bin'))
print(f'python version {sys.version}, cwd="{os.getcwd()}"')
import typing

# The plugins (see sn.plugins): their API pages (plugins/) document them as
# snplugins.<name>, imported from the project's plugins/ folder.
import sn.plugins
sn.plugins.namespace(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "plugins")))
typing.TYPE_CHECKING = False


# -- Project information -----------------------------------------------------

project = 'Semantic Nets'
#copyright = '\u00A9 2023-2025, Rob Kremer'
copyright = '2023-2026, Rob Kremer'
author = 'Rob Kremer'

# The full version, including alpha/beta/rc tags
release = '1.0'

show_authors = True

# -- General configuration ---------------------------------------------------

html_show_sourcelink = True

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
				"sphinx.ext.autodoc",
        "sphinx.ext.graphviz",
        "sphinx.ext.inheritance_diagram",
        "sphinx.ext.intersphinx",
#        'autodocsumm',
]

graphviz_output_format = 'svg'
graphviz_dot = '/opt/homebrew/bin/dot'

intersphinx_mapping = {
    "pythonUtils": (
        "http://192.168.1.102:8080/dev/pythonUtils",           # link target readers actually click through to
        "../../../pythonUtils/sphinx/build/html/objects.inv",  # read locally at build time -- no server dependency
    ),
}
# ... and use links like ":py:class:`pythonUtils:util.persistence.pRef.PRef`"

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["dev/test*", "*_deprecated*", "dev/modules.rst"] # (modules.rst: sphinx-apidoc's own table of contents -- index.rst uses dev/sn)


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
# html_theme = 'alabaster'
# html_theme = "bizstyle"
# html_theme = "pyramid"
# html_theme = "traditional"
# html_theme = "classic"
# html_theme = "agogo"
# html_theme = "nature"
# html_theme = "haiku"
html_theme = 'furo'

html_theme_options = {}
if html_theme == "traditional":
	html_theme_options = {
    	"sidebarwidth": 300
		}
elif html_theme == "classic":
	html_theme_options = {
		  "sidebarwidth": 300,
    	"rightsidebar": False,
    	"collapsiblesidebar": True,
		}
elif html_theme == "alabaster":
  html_theme_options = {
      "logo": "../_images/sn-logo.png",
      "logo_name": True,
      "sidebar_collapse": True,
      "fixed_sidebar": True,
      "description": "Semantic Nets: Typed graphs editor with inferencing.",
      "logo_text_align": "center",
      "show_relbars": True,
      "show_related": True,
      "sidebar_includehidden": True,
      "sidebar_hr": "#FF8800",
      "body_max_width" : 'none',
      "page_width": 'auto',
    }

html_logo = "./images/sn-logo.png" # (drawn by packaging/makeIcon.py, like the app's icon)
html_favicon = "./images/sn-favicon.png"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".

autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__,__call__,__str__,__getitem__,__setitem__',
    'no-undoc-members': True,
    'private-members': True,
    'show-inheritance': True,
#    'autosummary': True,
} 

# rst_prolog = """.. image:: /images/tygra-logo-small.png
#    :align: left
#    :height: 43
#    :width: 43
#    :alt: TyGra
# """