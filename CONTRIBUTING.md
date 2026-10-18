# Contributing to Module 7

This repo is standalone and Python only. No Rust, npm, prettier or clippy here, and the gates differ
from the core repo.

## Before pushing

```bash
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
```

All three have to pass. If they do not, clean up first:

```bash
ruff check --fix .
ruff format .
```

## Commits and branches

- Conventional Commits, same as the core repo: `feat(detector): add opencv_watershed`.
- Branch names use `<type>/<short-kebab-description>`, for example `feat/opencv-detector`.
- One commit, one intent. Small atomic PRs get reviewed faster than one large one.
- Virtual environments and plugin output files stay out of commits, see `.gitignore`.

## Language

Code, identifiers and comments are written in English to match the core repo, and so are the
project docs (README, CONTRACT, CONTRIBUTING).

## Changing the contract

`parameters.json`, `inputs.json` and `outputs.json` are read by other modules. A new parameter
changes the Module 2 form, and a new metric or artifact changes the Module 11 dashboard. Ask first
instead of dropping it mid-sprint:

- New parameter: add it to `parameters.json`, pass it to the detector through
  `pipeline.model_config_of` if the model needs it, and say in the PR that the Module 2 form changes
  too.
- New metric or artifact: change `outputs.json` and `treedet/output.py`, then coordinate with
  Module 11 before merging.
- Anything that needs a Tauri command or a new page in core belongs to Module 2. File it as an issue
  rather than doing it from this repo.
