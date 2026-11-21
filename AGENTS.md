# Repository Guidelines

## Project Structure

Nefes is a memory-pressure manager for Pardus 25 Xfce/X11. The Python daemon lives in `nefesd/`. Keep decision policy in `karar.py`, cgroup v2 access in `cgroups.py`, and PSI parsing and trigger formatting in `psi.py`. `tests/` contains pytest unit and VM integration tests. `deneyler/` contains Bash scripts for kernel experiments. Start with `notlar/00 Ana Sayfa.md` for the Obsidian project notes, architecture, and design decisions.

## Development Commands

Run these commands from the repository root with Python 3.13. Install `pytest` in your development environment first.

- `python3 -m pytest -q` runs the default suite on your development machine.
- `python3 -m nefesd --help` lists the daemon options.
- `python3 -m nefesd` starts the prototype as the desktop user in the Pardus VM with cgroup v2, PSI, and access to the X11 session. See `notlar/01 Proje/Test Ortamı.md` for VM setup.

## Coding Style and Naming

Use four spaces for Python indentation, `snake_case` for functions and variables, and `PascalCase` for classes. Follow existing type annotations and keep user-facing text in Turkish. Prefer the standard library and check with maintainers before adding a PyPI dependency, since the project targets Debian packaging. Keep `karar.py` pure and use event-driven PSI monitoring with `poll()` and `POLLPRI`.

## Testing Guidelines

Put tests in `tests/test_*.py` and give each `test_*` function a descriptive behavior name. Use pytest’s `tmp_path` fixture for fake cgroup trees. Cover changes to candidate selection with tests that protect focused apps and excluded scopes, including `session-*.scope`. Exercise real `cgroup.freeze` and `memory.reclaim` only in the Pardus VM. Run `NEFES_VM=1 python3 -m pytest -q tests/test_vm.py` there as the desktop user.

## Commits and Pull Requests

Use a Conventional Commit prefix and a short Turkish summary, following history such as `feat: nefesd karar motoru`. Use `fix:`, `test:`, `docs:`, or `chore:` as appropriate. In pull requests, explain the behavior change, link related issues when available, and report the checks you ran. Include VM results for changes to kernel-facing behavior.
