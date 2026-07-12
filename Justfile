# basher task runner

venv_dir := ".venv"
venv_bin := venv_dir / "bin"
python := env_var_or_default("BASHER_PYTHON", "3.11")

default:
    @just --list

_venv:
    @[ -x {{ venv_bin }}/python ] || uv venv --python {{ python }} {{ venv_dir }}

install: _venv
    uv pip install --python {{ venv_bin }}/python -e ".[dev]"

fmt: install
    {{ venv_bin }}/ruff format src tests
    {{ venv_bin }}/ruff check --fix src tests

fmt-check: install
    {{ venv_bin }}/ruff format --check src tests

lint: install
    {{ venv_bin }}/ruff check src tests
    {{ venv_bin }}/mypy
    {{ venv_bin }}/symvision src/basher
    {{ venv_bin }}/toobig src 1000 850 700
    {{ venv_bin }}/toobig tests 1000 850 700
    {{ venv_bin }}/shellcheck --exclude=SC2034 src/basher/data/bugyi.sh

[positional-arguments]
test *args: install
    {{ venv_bin }}/pytest "$@"

check: fmt-check lint test
