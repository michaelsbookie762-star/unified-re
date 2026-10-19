@echo off
pushd "%~dp0"
node.exe open.mjs about:blank
if errorlevel 1 pause
popd
