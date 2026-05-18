# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python tool for porting HyperOS ROMs across Xiaomi/Redmi devices. It automates: unpacking stock/port ROMs, applying patches (system, framework, firmware, APK), feature adaptation, and repacking into flashable output (payload.bin or super.img).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the tool
python main.py --stock <path> --port <path> [--ksu] [--pack-type super|payload]

# Run tests
pytest
pytest tests/test_workflow.py              # single file
pytest tests/test_workflow.py::test_name   # single test
pytest -m unit                             # only unit tests

# Lint & format
ruff check .
ruff check --fix .
black .

# Type check
mypy --config-file mypy-curated.ini src/

# Pre-commit (runs black, ruff, mypy, gitleaks)
pre-commit run --all-files
```

## Architecture

**Entry point:** `main.py` → `src/app/cli.py` (arg parsing) → `src/app/workflow.py` (orchestration)

**Core pipeline** (`src/core/`):
- `context.py` — `PortingContext`: central state object holding stock/port ROM refs, paths, tools, and config. Passed to all modifiers.
- `config_loader.py` — Loads and deep-merges JSON configs from `devices/common/` → `devices/<codename>/` (device overrides win).
- `workspace.py` — Partition layout, target directory setup, firmware image copying.
- `packer.py` — Repacks modified partitions into payload.bin or super.img output.

**Modifier system** (`src/core/modifiers/`):
- `unified_modifier.py` — Single entry point orchestrating all modifications. Loads built-in plugins in order: FileReplacement → PropertyModifier → WildBoost → FeatureUnlock → VNDKFix → EULocalization.
- `plugin_system.py` — Plugin base class (`ModifierPlugin`) and `PluginManager` for registration/execution.
- `plugins/` — Individual plugins (wild_boost, eu_localization, feature_unlock, vndk_fix, file_replacement, apk/).
- `framework_modifier.py` / `framework/` — Smali-level patches to framework JARs.
- `firmware_modifier.py` — Firmware image modifications (vbmeta, KSU injection).
- `rom_modifier.py` — ROM-level property and build.prop modifications.

**Utilities** (`src/utils/`):
- `payload_dumper.py` — Extracts partitions from payload.bin.
- `shell.py` — Shell command runner.
- `sync_engine.py` — Syncs files between stock and port ROM trees.
- `smalikit.py` — Smali patching helpers.

**Device configs** (`devices/`):
- `common/` — Default config (config.json, features.json, props_global.json, replacements.json). All devices inherit these.
- `<codename>/` — Per-device overrides. Same JSON structure, deep-merged over common.

## Key Conventions

- Python 3.10+, Linux only. Requires sudo for mount operations during actual porting.
- Line length: 100 (black + ruff).
- Tests use pytest with coverage (`--cov=src`). Markers: `unit`, `integration`, `slow`.
- Config uses layered JSON (common → device), not YAML. Keys starting with `_` are metadata/comments and skipped during merge.
- The `otatools/`, `build/`, and `out/` directories are excluded from all linting/type-checking.
