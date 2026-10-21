@echo off
rem Run Semantic Nets' command line interface from the source (Windows: see sn for macOS and Linux).
rem Needs Python 3.14 (from python.org, with the py launcher) and ..\pythonUtils beside this folder.
setlocal
set "PYTHONPATH=%~dp0src;%~dp0..\pythonUtils\src;%PYTHONPATH%"
py -3.14 -m sn.view.textUserInterface %*
