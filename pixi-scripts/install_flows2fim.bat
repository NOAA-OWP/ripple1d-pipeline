@echo off
rem pixi activation script: ensure flows2fim is in the environment (idempotent).
if not exist "%CONDA_PREFIX%\Library\bin\flows2fim.exe" python "%~dp0install_flows2fim.py"
