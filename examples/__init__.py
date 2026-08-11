# Make `examples/` a proper package so probes under `qa/` can
# do `from examples._env import load_env` after adding the repo
# root to `sys.path`. The file is intentionally empty — examples
# remain a flat directory of runnable scripts; the package marker
# only enables cross-directory imports.
