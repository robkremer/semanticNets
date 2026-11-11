# Job jar

Done one at a time, top to bottom (the order matters: each builds on the ones
above it). Started 2026-10-13.

## 1. Hooks: functions named in attributes (sn) -- DONE (sn/hooks.py)

The base for most of the rest: a way for an attribute's value to name a Python
function so that it still works after the model is saved and read back.

- The value is a string, not a pickled function: `module.path:function` (eg:
  `sn.exampleApps.pythonParser.hooks:showSource`), resolved with *importlib*
  only when it's first used, and then cached.
- **Trust.** Models can now come from the web (shared ontologies, Open URL...),
  so a value can't be allowed to name just any function (eg: `os:system`). Only
  *registered* functions can be called: a module makes its functions callable
  with a decorator (eg: `@sn.hooks.hook`), and a module is imported to find them
  only if it's on an allowlist (sn's own packages, plus a preference the user
  can add to). Anything else: a plain warning in the log, and a disabled menu
  item / plain text tooltip -- never an error dialog on hover.
- A single calling convention for every hook: `fn(obj, context)`, where *obj*
  is the model object (Node or Relation) and *context* holds the VObject, the
  view, and the menu path or tooltip key used; it returns a value (a string,
  for tooltips) or None.
- Where: a new `sn/hooks.py` (registry, resolve, call); its tests.

## 2. Menu items from `.menu/...` attributes (sn) -- DONE (with `.doubleClick`, `@hook(appliesTo=...)`)

- Any `.menu/<path>` attribute an object has (its own, or inherited: eg: set
  on a type in an ontology, for all its instances) adds an item to its
  right-click menu (*VObject.makeMenu()*), calling the hook named by its value.
  `/` in the path makes submenus (eg: `.menu/Source/Open in BBEdit`), as
  "vis/label" and the preferences do -- not `.`.
- Items are in their own section of the menu, sorted by path.
- Maybe also: `.doubleClick` -- a hook run on double-click instead of the
  usual (to check: what double-click does now).
- Maybe also: a model's own `.menu/...` on the view's background menu. (Not
  done: a Model has no attributes of its own -- it'd need some first.)

## 3. Tooltip templates (sn) -- DONE (vis/tooltip, vis/tooltipFont, vis/tooltipWrap, $(hook), gui/tooltipMaxLines; no caching: a hook runs each time a tooltip's shown)

- A "vis/tooltip" attribute (eg: on a type), else a "gui/tooltip" preference,
  in the same template language as labels (*sn.view.graphics.labels*); the
  default gives today's tooltip (name, then the note).
- Add a call to the language: `$(hookName)` -- the hook's result, called only
  when the tooltip is shown (and cached until the object changes). Uses
  job 1's registry. Also in labels, since it's the same language (but labels are
  drawn often: maybe a warning about slow hooks in the docs).
- Code in a tooltip needs a monospace font and a length limit (a long method
  shouldn't fill the screen): eg: `${=mono:...}` or a "vis/tooltipFont"
  attribute; to decide when we get there.
- The debug part (the cache dump) is still added after it, when debugging.

## 4. Finding a chunk of source again (pythonParser) -- DONE (pythonParser/source.py: locate(), locateNode())

- Store, besides "line": "end-line", the chunk's first line as written
  ("signature-line"), and a short hash of its text ("source-hash"); all
  hidden (`.`) unless they're useful to see.
- Locate a class / function / `__main__` block in its file now: re-parse and
  look it up by its qualified name (Class.method); failing that (the file
  doesn't parse just now), grep for `def name` / `class name` nearest the
  stored line; failing that, fuzzy-match the stored first line; failing that,
  the stored line, marked as a guess. Members find their file through their
  module (*defines* upwards).
- Report "changed since the model was made" when the hash differs.

## 5. Opening source in an editor (pythonParser, with a pref in sn?) -- DONE (sn/view/graphics/sourceWindow.py: openSource(); gui/editorCommand)

- A command template preference: eg: `bbedit +{line} {path}` (BBEdit's free
  mode includes its command line tool: BBEdit > Install Command Line Tools).
- Eclipse: works (user-confirmed 2026-10-14) via AppleScript to the running
  Eclipse, "path:line" as the file: see the gui/editorCommand note. (Its
  launcher starts a second Eclipse: "workspace in use".)
- A built-in read-only source window (scrolled to the chunk, chunk highlighted)
  as the fallback when no editor's set up.

## 6. Wire pythonParser up to it (pythonParser) -- DONE (pythonParser/hooks.py; ontology)

- Declare "end-line" in pythonOntology.snm (on python-code-block, beside
  "line"), with a note: job 4 sets it, but the ontology wasn't touched.

- In pythonOntology.snm: `.menu/Show source` (and `.menu/Open in editor`) on
  class, function and code; `vis/tooltip` with `$(source)` on the function
  types (and maybe the doc string's text on doc-string).
- Module / package: `.menu/Reveal in Finder`, `.menu/Open in editor`.

## 7. "Erase everything else" (sn; independent of the rest: any time) -- DONE

- A VObject menu item (next to "erase from view") that erases from the view
  everything except this object -- or, if there's a selection, except the
  selection (as "erase from view" uses *selectionOrSelf()*). For working on
  a small part of a very large graph.
- Keeps: the relations among the kept objects, and whatever contains a kept
  object (its context window / container), so they still make sense. To
  decide: whether relations count as "kept" when only their ends are.
- One undoable step (as *doErase()* is); maybe also "hide everything else"
  if "hide" (as in "hide by category") is the better fit -- to check what
  hiding does there vs erasing.

## 8. Plugins: the example apps become plugins (sn) -- decided 2026-10-17

pythonParser and XMLreader are separate programs now (`python -m
sn.exampleApps...`, each making its own Application): the packaged app can't
reach them, and their hook references and ontology path name the source tree.
Instead, each becomes a plugin the editor loads at start-up.

Decisions (Rob, 2026-10-17):
- **Where:** `~/.sn/plugins/<name>/` (beside prefs.xml and cache/).
- **Bundled plugins are copied** there (not loaded from the app), on start-up,
  when missing or older than the bundled version -- so the ontologies models
  are built on stay at a fixed path across app moves and updates.
- **Menus: both** -- a shared "Tools" menu by default, and a plugin may add
  its own top-level menus.
- **No command line** for the plugins: their start-up will change; a `__main__`
  would only be upkeep.

Design:
- A plugin is a folder: a Python package (its `__init__.py` defines
  `register(ctx)`) and a `plugin.toml` (name, version, description,
  sn-version: the oldest sn it works with).
- Imported as `snplugins.<folder>`: a namespace whose path is the plugins
  folder, so hook references are the same on every machine (eg:
  `snplugins.pythonParser.hooks:showSource`). A loaded plugin's package is
  trusted for hooks (installed = trusted).
- A failing plugin is logged and skipped; "plugins/disabled" turns one off.
- *PluginContext*: app, folder, logger, its own prefs (`plugins/<name>/...`),
  `addMenuItem("Tools/Python Parser...", command)`. Later: panels, view menus,
  text commands.
- Bundled plugin sources live in the project's top folder, `plugins/` (not
  under src/, so they aren't importable as anything but the installed copies);
  the app bundles them as data, and the stdlib modules they need as hidden imports.

Steps (a commit each):
1. DONE (d56533a) sn/plugins.py: loader, manifest, PluginContext (menus), trust; tests.
2. DONE pythonParser -> plugins/pythonParser (the Tools menu; hooks.MOVED; installBundled() relocates .snm/.snv URLs; sn.plugins.importBundled() for tests and tools): a menu item opens ParserDialog; hook
   references renamed (an alias for the old `sn.exampleApps.pythonParser.hooks`
   ones); ontology in the plugin; tools/docExamples updated.
3. DONE XMLreader the same way (view.py; its examples read into ~/Documents/Semantic Nets Examples; plugin.toml exclude).
4. DONE Packaging: bundle plugins/ (app and .pyz: packaging/bundledPlugins.py; --selftest covers them); Help > Reveal Plugins Folder; check the
   universal build.
5. DONE Docs: user/exampleApps.rst is "Plugins"; extending.rst "Plugins" (writing one) and "The plugins that come with it"; API pages in sphinx/source/plugins/ (conf.py sets up snplugins).

## Maybe later

- Re-parse: bring an existing model up to date with its source (needs nodes
  matched by qualified name; keeps the user's layout and edits).
- Hooks for other events: eg: on select, on model load (a controlling app
  setting things up when its model is opened without it).
