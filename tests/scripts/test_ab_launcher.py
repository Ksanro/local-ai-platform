"""Tests for scripts/ab_launcher.py.

Nothing here starts a process or opens a connection: the launcher is
configuration and validation only, and these tests keep it that way by running
every surface in-process against temporary directories.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import scripts.ab_launcher as ab_launcher
from scripts.ab_launcher import (
    HARNESS_TIMEOUT_MARGIN_SECONDS,
    REQUIRED_SHARED_ENV_KEYS,
    REQUIRED_WORKTREE_PATHS,
    TEMPLATE_HARNESS_TIMEOUT_SECONDS,
    TEMPLATE_MEASUREMENT_ENV,
    TEMPLATE_PORTS,
    TEMPLATE_PROVIDER_REQUEST_TIMEOUT_SECONDS,
    UV_COMMAND,
    AbArm,
    AbExperiment,
    AbLaunchError,
    arm_environment,
    experiment_document,
    experiment_from_dict,
    experiment_to_dict,
    load_experiment,
    main,
    render_arm_script,
    render_diff,
    render_environment_block,
    render_gateway_command,
    render_harness_command,
    render_launch_script,
    save_experiment,
    template_experiment,
    validate_experiment,
)

SECRET_VALUE = "sk-should-never-be-printed"

#: The settings that used to be inherited from whichever terminal started an arm.
MEASUREMENT_ENV_KEYS = (
    "APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS",
    "APP_CONTEXT_INTENT_RULES",
    "APP_CONTEXT_DELTA_CACHE_SIZE",
    "RELATIONSHIP_RANKING_ENABLED",
    "RELATIONSHIP_EXPANSION_ENABLED",
)

#: A commit id, because that is what ``git worktree add --detach`` leaves in HEAD.
DETACHED_HEAD = "4330e8f3521d7a4b9525bb62008b3f3b716a6e7f"


def _make_worktree(root: Path, *, detached: bool = True) -> Path:
    """Create the smallest tree the launcher accepts as an isolated worktree.

    The launcher never runs Git, so a fixture has to leave behind exactly what Git
    leaves behind: the tracked files both rendered commands start from, a ``.git``
    file whose ``gitdir:`` line reaches an administration directory, and a ``HEAD``
    in that directory holding a commit rather than a branch.

    Args:
        root: The worktree to build.
        detached: ``False`` builds a worktree checked out on a branch instead.

    Returns:
        The tree, ready to be named as an experiment's ``worktree``.
    """
    root.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_WORKTREE_PATHS:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    git_dir = root.parent / "clone" / ".git" / "worktrees" / root.name
    git_dir.mkdir(parents=True, exist_ok=True)
    head = DETACHED_HEAD if detached else "ref: refs/heads/ab/experiment"
    (git_dir / "HEAD").write_text(f"{head}\n", encoding="utf-8")
    (root / ".git").write_text(f"gitdir: {git_dir}\n", encoding="utf-8")
    return root


def _shared_env(worktree: Path) -> dict[str, str]:
    """Return the runbook's shared block pointed at one isolated tree."""
    return {
        "DEFAULT_MODEL": "qwen38-27b",
        "APP_LOG_LEVEL": "INFO",
        "APP_DEFAULT_MODEL": "qwen38-27b",
        "APP_DEFAULT_PROVIDER": "openai",
        "APP_MODELS_CONFIG": json.dumps(
            [
                {
                    "model": "qwen38-27b",
                    "backend_model": "qwen3.8-flash-next",
                    "provider": "openai",
                    "base_url": "http://127.0.0.1:18300/v1",
                    "context_window": 262144,
                    "max_output_tokens": 8192,
                }
            ],
            separators=(",", ":"),
        ),
        "APP_REPOSITORY_PATH": str(worktree),
        "APP_REPOSITORY_CONTEXT_ENABLED": "true",
        "APP_REPOSITORY_CONTEXT_MAX_TOKENS": "4096",
        "APP_REPOSITORY_CONTEXT_INTENT_BUDGETS": "SEARCH:2048,DEBUG:2048",
        "APP_REPOSITORY_EXCLUDE_TESTS": "false",
        "APP_REPOSITORY_EXCLUDE_GLOBS": "scripts/**",
        "APP_CONTEXT_DELTA_INJECTION": "true",
        "APP_SESSION_LOG_ENABLED": "true",
        "APP_HISTORY_CAP_ENABLED": "true",
        "APP_HISTORY_CAP_TOKENS": "3000",
        **TEMPLATE_MEASUREMENT_ENV,
    }


def _experiment(tmp_path: Path, *, worktree: Path | None = None, **overrides: Any) -> AbExperiment:
    """Return a sound experiment whose worktree is an isolated detached worktree.

    A tree handed in is left exactly as it is, so a test can break one on purpose.
    """
    tree = worktree if worktree is not None else _make_worktree(tmp_path / "tree")
    logs = tree / "logs"
    experiment = AbExperiment(
        name="changed_files_benefit",
        worktree=str(tree),
        shared_env=_shared_env(tree),
        arms=(
            AbArm(
                arm_id="off",
                port=8011,
                session_log_path=str(logs / "sessions_off.jsonl"),
                changed_files_enabled=False,
            ),
            AbArm(
                arm_id="on",
                port=8012,
                session_log_path=str(logs / "sessions_on.jsonl"),
                changed_files_enabled=True,
            ),
        ),
        provider_request_timeout_seconds=300.0,
        harness_timeout_seconds=345.0,
        harness_repeat=3,
        harness_max_tokens=8192,
    )
    return dataclasses.replace(experiment, **overrides)


def _problems(experiment: AbExperiment) -> str:
    """Return the validation verdict as one lowercase string to search."""
    return "\n".join(validate_experiment(experiment)).lower()


def test_sound_experiment_has_no_problems(tmp_path: Path) -> None:
    assert validate_experiment(_experiment(tmp_path)) == ()


def test_template_validates_once_the_worktree_is_a_detached_checkout(
    tmp_path: Path,
) -> None:
    worktree = _make_worktree(tmp_path / "ab-tree")
    experiment = template_experiment(name="tmpl", worktree=str(worktree))

    assert validate_experiment(experiment) == ()
    assert experiment.provider_request_timeout_seconds == TEMPLATE_PROVIDER_REQUEST_TIMEOUT_SECONDS
    assert experiment.harness_timeout_seconds == TEMPLATE_HARNESS_TIMEOUT_SECONDS
    assert tuple(arm.port for arm in experiment.arms) == TEMPLATE_PORTS
    assert Path(experiment.worktree).is_absolute()
    assert all(Path(arm.session_log_path).is_absolute() for arm in experiment.arms)


def test_template_resolves_a_relative_worktree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "ab-tree").mkdir()
    monkeypatch.chdir(tmp_path)
    experiment = template_experiment(name="rel", worktree="ab-tree")

    assert Path(experiment.worktree) == tmp_path.resolve() / "ab-tree"
    assert experiment.shared_env["APP_REPOSITORY_PATH"] == experiment.worktree


def test_worktree_and_repository_path_must_name_the_same_tree(tmp_path: Path) -> None:
    """``APP_REPOSITORY_PATH`` is what the gateway indexes, and the worktree is what
    both arms run from; one edited without the other measures unvalidated code."""
    experiment = _experiment(tmp_path)
    elsewhere = _make_worktree(tmp_path / "elsewhere")
    shared = dict(experiment.shared_env)
    shared["APP_REPOSITORY_PATH"] = str(elsewhere)

    assert "same tree" in _problems(dataclasses.replace(experiment, shared_env=shared))


def test_one_directory_written_two_ways_is_one_tree(tmp_path: Path) -> None:
    """The two are compared after resolving, because Windows reaches one directory
    through a junction, a ``subst`` drive, or a trailing ``\\.``.
    """
    tree = _make_worktree(tmp_path / "tree")
    experiment = _experiment(tmp_path)
    shared = dict(experiment.shared_env)
    shared["APP_REPOSITORY_PATH"] = str(tree) + os.sep + os.pardir + os.sep + tree.name

    assert _problems(dataclasses.replace(experiment, shared_env=shared)) == ""


def test_missing_provider_timeout_is_reported(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path, provider_request_timeout_seconds=None)

    assert "provider_request_timeout_seconds" in _problems(experiment)


def test_missing_harness_timeout_is_reported(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path, harness_timeout_seconds=None)

    assert "harness_timeout_seconds" in _problems(experiment)


def test_missing_required_shared_setting_is_reported(tmp_path: Path) -> None:
    shared = _shared_env(Path(tmp_path / "tree"))
    shared.pop(REQUIRED_SHARED_ENV_KEYS[1])
    experiment = _experiment(tmp_path, shared_env=shared)

    assert "missing required shared setting" in _problems(experiment)


def test_worktree_holding_an_env_file_is_refused(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path)
    (Path(experiment.worktree) / ".env").write_text("APP_MODELS_CONFIG={}\n", encoding="utf-8")

    problems = _problems(experiment)
    assert ".env" in problems
    assert "app_models_config" in problems


def test_missing_worktree_is_refused(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path)
    experiment = dataclasses.replace(experiment, worktree=str(Path(experiment.worktree) / "gone"))

    assert "not a directory" in _problems(experiment)


def test_unexpected_arm_difference_is_reported(tmp_path: Path) -> None:
    arms = list(_experiment(tmp_path).arms)
    arms[1] = dataclasses.replace(arms[1], env={"APP_CONTEXT_DELTA_CACHE_SIZE": "64"})

    problems = _problems(_experiment(tmp_path, arms=tuple(arms)))
    assert "unexpected arm difference" in problems
    assert "app_context_delta_cache_size" in problems


def test_shared_setting_must_not_be_overridden_per_arm(tmp_path: Path) -> None:
    arms = list(_experiment(tmp_path).arms)
    arms[1] = dataclasses.replace(arms[1], env={"APP_LOG_LEVEL": "DEBUG"})

    assert "must be identical in both arms" in _problems(_experiment(tmp_path, arms=tuple(arms)))


def test_both_arm_differences_have_to_differ(tmp_path: Path) -> None:
    arms = list(_experiment(tmp_path).arms)
    arms[1] = dataclasses.replace(arms[1], changed_files_enabled=False)

    assert "nothing to compare" in _problems(_experiment(tmp_path, arms=tuple(arms)))


def test_duplicate_ports_are_reported(tmp_path: Path) -> None:
    arms = list(_experiment(tmp_path).arms)
    arms[1] = dataclasses.replace(arms[1], port=arms[0].port)

    assert "both use port" in _problems(_experiment(tmp_path, arms=tuple(arms)))


def test_duplicate_session_logs_are_reported(tmp_path: Path) -> None:
    arms = list(_experiment(tmp_path).arms)
    arms[1] = dataclasses.replace(arms[1], session_log_path=arms[0].session_log_path)

    assert "share the session log" in _problems(_experiment(tmp_path, arms=tuple(arms)))


def test_relative_session_log_path_is_reported(tmp_path: Path) -> None:
    arms = list(_experiment(tmp_path).arms)
    arms[0] = dataclasses.replace(arms[0], session_log_path="logs/sessions_off.jsonl")

    assert "must be absolute" in _problems(_experiment(tmp_path, arms=tuple(arms)))


def test_credentials_never_reach_a_rendered_command(tmp_path: Path) -> None:
    shared = dict(_experiment(tmp_path).shared_env)
    shared["OPENAI_API_KEY"] = SECRET_VALUE
    experiment = _experiment(tmp_path, shared_env=shared)

    assert "credential" in _problems(experiment)
    for arm in experiment.arms:
        assert SECRET_VALUE not in render_environment_block(experiment, arm)
        assert SECRET_VALUE not in arm_environment(experiment, arm)
    assert SECRET_VALUE not in json.dumps(experiment_document(experiment))


def test_harness_timeout_must_clear_the_provider_timeout_by_a_margin(tmp_path: Path) -> None:
    experiment = _experiment(
        tmp_path,
        harness_timeout_seconds=300.0 + HARNESS_TIMEOUT_MARGIN_SECONDS - 1,
    )

    assert "harness_timeout_seconds" in _problems(experiment)


def test_bad_setting_values_are_reported(tmp_path: Path) -> None:
    cases = {
        "APP_SESSION_LOG_ENABLED": "sure",
        "APP_REPOSITORY_CONTEXT_MAX_TOKENS": "many",
        "APP_HISTORY_CAP_TOKENS": "-1",
        "APP_REPOSITORY_PATH": "relative/tree",
        "APP_REPOSITORY_CONTEXT_INTENT_BUDGETS": "SEARCH=lots",
        "APP_MODELS_CONFIG": '[{"model": "x"}]',
    }
    for key, value in cases.items():
        shared = dict(_experiment(tmp_path).shared_env)
        shared[key] = value
        problems = _problems(_experiment(tmp_path, shared_env=shared))
        assert key.lower() in problems, f"{key}={value} was accepted"


def test_default_model_outside_the_registry_is_reported(tmp_path: Path) -> None:
    shared = dict(_experiment(tmp_path).shared_env)
    shared["DEFAULT_MODEL"] = "not-a-real-alias"

    assert "is not one of the aliases" in _problems(_experiment(tmp_path, shared_env=shared))


def test_a_model_timeout_must_be_declared_as_the_experiment_field(tmp_path: Path) -> None:
    shared = dict(_experiment(tmp_path).shared_env)
    shared["APP_MODELS_CONFIG"] = shared["APP_MODELS_CONFIG"].replace(
        '"provider":', '"timeout": 5, "provider":'
    )

    assert "per-model timeout" in _problems(_experiment(tmp_path, shared_env=shared))


def test_harness_inputs_are_checked(tmp_path: Path) -> None:
    assert "harness_repeat" in _problems(_experiment(tmp_path, harness_repeat=0))
    assert "harness_probes" in _problems(_experiment(tmp_path, harness_probes=("  ",)))
    assert "harness_max_tokens" in _problems(_experiment(tmp_path, harness_max_tokens=0))


def test_render_guard_refuses_an_undeclared_timeout(tmp_path: Path) -> None:
    experiment = dataclasses.replace(_experiment(tmp_path), harness_timeout_seconds=None)

    with pytest.raises(AbLaunchError, match="cannot render a command"):
        render_harness_command(experiment, experiment.arms[0])


def test_environment_block_is_sorted_and_holds_the_declared_values(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path)
    block = render_environment_block(experiment, experiment.arms[1])
    keys = [line.split("=")[0].removeprefix("$env:") for line in block.splitlines()]

    assert keys == sorted(keys)
    assert "$env:REQUEST_TIMEOUT='300'" in block
    assert "$env:APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED='true'" in block
    assert "OPENAI_API_KEY" not in block


def test_gateway_command_is_the_documented_uvicorn_line(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path)
    command = render_gateway_command(experiment, experiment.arms[0])

    assert "apps.gateway.main:create_app --factory" in command
    assert command.endswith("--host 127.0.0.1 --port 8011")


def test_harness_command_carries_every_validated_setting(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path, harness_probes=("code_search", "test_intent"))
    command = render_harness_command(experiment, experiment.arms[1])

    assert "--base-url http://127.0.0.1:8012/v1" in command
    assert "--probe 'code_search' --probe 'test_intent'" in command
    assert "--repeat 3" in command
    assert "--max-tokens 8192" in command
    assert "--model 'qwen38-27b'" in command
    assert "--session-log-path" in command and "sessions_on.jsonl" in command
    assert "--timeout '345'" in command
    assert command.endswith("--json")


def test_launch_script_covers_both_arms_in_order(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path)
    script = render_launch_script(experiment)

    assert script.index("arm 'off'") < script.index("arm 'on'")
    assert "8011" in script and "8012" in script
    assert "--timeout '345'" in script


def test_render_diff_lists_only_the_allowed_differences(tmp_path: Path) -> None:
    diff = render_diff(_experiment(tmp_path))

    assert "APP_SESSION_LOG_PATH" in diff
    assert "APP_REPOSITORY_CONTEXT_CHANGED_FILES_ENABLED" in diff
    assert "APP_MODELS_CONFIG" not in diff


def test_config_file_round_trips(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path)
    path = save_experiment(experiment, tmp_path / "ab.json")

    assert load_experiment(path) == experiment
    assert experiment_to_dict(experiment)["schema"] == ab_launcher.CONFIG_SCHEMA_VERSION
    assert json.loads(path.read_text(encoding="utf-8")) == experiment_to_dict(experiment)


def test_load_reports_a_file_that_is_not_an_experiment(tmp_path: Path) -> None:
    broken = [
        "[]",
        json.dumps({"schema": 999, "arms": [], "harness_repeat": 3}),
        json.dumps({"arms": [{"arm_id": "off", "port": "8011"}], "harness_repeat": 3}),
        json.dumps(
            {
                "arms": [{"arm_id": "off", "port": 8011, "changed_files_enabled": "yes"}],
                "harness_repeat": 3,
            }
        ),
    ]
    for index, text in enumerate(broken):
        path = tmp_path / f"broken{index}.json"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(AbLaunchError):
            load_experiment(path)


def test_load_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AbLaunchError):
        load_experiment(tmp_path / "absent.json")


def test_document_reports_validity_without_running_anything(tmp_path: Path) -> None:
    document = experiment_document(_experiment(tmp_path))

    assert document["valid"] is True
    assert document["problems"] == []
    assert document["timeouts"]["required_margin_seconds"] == HARNESS_TIMEOUT_MARGIN_SECONDS
    assert set(document["arms"]) == {"off", "on"}


def test_document_reports_the_validated_tree_without_running_anything(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("validation must not reach for Git")

    for name in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, refuse)

    tree = Path(_experiment(tmp_path).worktree)
    worktree = experiment_document(_experiment(tmp_path))["worktree"]

    assert worktree["path"] == str(tree)
    assert worktree["exists"] is True
    assert worktree["marker"] == ab_launcher.WORKTREE_MARKER_LINKED
    assert worktree["git_dir"] == str(tree.parent / "clone" / ".git" / "worktrees" / tree.name)
    assert worktree["detached"] is True
    assert worktree["missing_paths"] == []
    assert worktree["can_run_an_arm"] is True


def test_secret_looking_arm_difference_is_described_without_its_value(tmp_path: Path) -> None:
    arms = list(_experiment(tmp_path).arms)
    arms[0] = dataclasses.replace(arms[0], env={"APP_ACCESS_TOKEN": SECRET_VALUE})
    arms[1] = dataclasses.replace(arms[1], env={"APP_ACCESS_TOKEN": "other"})
    experiment = _experiment(tmp_path, arms=tuple(arms))

    assert SECRET_VALUE not in json.dumps(experiment_document(experiment))
    assert SECRET_VALUE not in render_diff(experiment)


def test_from_dict_names_the_field_at_fault_rather_than_its_value() -> None:
    with pytest.raises(AbLaunchError, match="on.session_log_path"):
        experiment_from_dict(
            {
                "arms": [
                    {"arm_id": "off", "port": 8011, "session_log_path": "C:/logs/off.jsonl"},
                    {"arm_id": "on", "port": 8012},
                ],
                "harness_repeat": 3,
            }
        )


def test_main_validates_and_renders_a_written_template(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = tmp_path / "tree"
    _make_worktree(worktree)
    config = tmp_path / "ab.json"

    assert main(["template", "--worktree", str(worktree), "--out", str(config)]) == 0
    assert main(["validate", "--config", str(config)]) == 0
    capsys.readouterr()

    assert main(["show", "--config", str(config), "--arm", "on"]) == 0
    assert "--timeout '345'" in capsys.readouterr().out

    assert main(["show", "--config", str(config), "--diff"]) == 0
    assert "APP_SESSION_LOG_PATH" in capsys.readouterr().out

    assert main(["show", "--config", str(config), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True


def test_template_reports_a_tree_that_cannot_run_an_arm_yet(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A starting point names a worktree that usually does not exist yet, so the
    file is written and the tree is reported rather than the command failing.
    """
    config = tmp_path / "ab.json"
    tree = tmp_path / "not-made-yet"
    capsys.readouterr()

    assert main(["template", "--worktree", str(tree), "--out", str(config)]) == 0

    captured = capsys.readouterr()
    assert config.is_file()
    assert "cannot run an arm yet" in captured.err
    assert "not a directory" in captured.err


def test_template_reports_a_tree_both_arms_can_start_from(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    worktree = _make_worktree(tmp_path / "tree")
    capsys.readouterr()

    assert main(["template", "--worktree", str(worktree), "--out", str(tmp_path / "ab.json")]) == 0

    assert "can run either arm" in capsys.readouterr().out


def test_show_refuses_to_render_an_unvalidated_tree(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing is printed for a terminal to run until the tree behind it has been
    checked, because a pasted block is taken as permission to start.
    """
    experiment = _experiment(tmp_path, worktree=tmp_path / "gone")
    config = save_experiment(experiment, tmp_path / "ab.json")
    capsys.readouterr()

    assert main(["show", "--config", str(config)]) == 2
    assert main(["show", "--config", str(config), "--arm", "off"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not a directory" in captured.err


def test_main_exits_two_and_keeps_the_reasons_off_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    experiment = _experiment(tmp_path)
    config = save_experiment(experiment, tmp_path / "ab.json")
    broken = json.loads(Path(config).read_text(encoding="utf-8"))
    broken["harness_timeout_seconds"] = broken["provider_request_timeout_seconds"]
    Path(config).write_text(json.dumps(broken), encoding="utf-8")

    assert main(["show", "--config", str(config)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "harness_timeout_seconds" in captured.err


def test_main_reports_an_unknown_arm(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = save_experiment(_experiment(tmp_path), tmp_path / "ab.json")

    assert main(["show", "--config", str(config), "--arm", "middle"]) == 2
    assert "middle" in capsys.readouterr().err


def test_the_launcher_never_starts_a_process_or_opens_a_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the launcher must only print commands")

    for name in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, refuse)
    monkeypatch.setattr(sys, "argv", ["ab_launcher.py"])
    for name in ("system", "execv", "execve", "spawnl", "spawnv"):
        if hasattr(ab_launcher.os, name):
            monkeypatch.setattr(ab_launcher.os, name, refuse)

    worktree = tmp_path / "tree"
    _make_worktree(worktree)
    config = tmp_path / "ab.json"

    assert main(["template", "--worktree", str(worktree), "--out", str(config)]) == 0
    assert main(["show", "--config", str(config)]) == 0
    capsys.readouterr()

    assert main(["show", "--config", str(config), "--arm", "off"]) == 0
    assert "Set-Location" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# ``show --arm`` must be paste-ready for the tree it validated
# ---------------------------------------------------------------------------


def test_arm_script_runs_from_the_validated_worktree_not_the_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every path an arm inherits comes from the tree, wherever `cd` left it."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    experiment = _experiment(tmp_path)
    tree = Path(experiment.worktree)
    arm = experiment.arms[1]
    script = render_arm_script(experiment, arm)
    commands = [line for line in script.splitlines() if not line.startswith("#")]
    rendered = "\n".join(commands)

    # The first thing the block does is move the terminal into the validated tree,
    # named absolutely; the directory the launcher was run from never appears.
    assert commands[0] == f"Set-Location '{tree}'"
    assert str(elsewhere) not in rendered
    assert Path.cwd().resolve() == elsewhere.resolve()
    assert Path.cwd() != tree
    # Both commands run from there, so the launcher and every relative path the
    # harness resolves belong to this experiment's tree.
    assert rendered.count(f"Set-Location '{tree}'") == 2
    assert f"{UV_COMMAND} run" in rendered
    assert str(tree / "logs" / "sessions_on.jsonl") in rendered
    assert str(tree / "logs" / "sessions_off.jsonl") not in rendered
    assert "arm 'off'" not in script


def test_arm_script_creates_the_session_log_before_the_gateway_starts(
    tmp_path: Path,
) -> None:
    experiment = _experiment(tmp_path)
    arm = experiment.arms[0]
    lines = [
        line
        for line in render_arm_script(experiment, arm).splitlines()
        if not line.startswith("#")
    ]
    log_path = Path(arm.session_log_path)
    gateway = render_gateway_command(experiment, arm)
    harness = render_harness_command(experiment, arm)

    assert lines.index(f"New-Item -ItemType Directory -Force '{log_path.parent}' | Out-Null") < (
        lines.index(f"New-Item -ItemType File -Force '{log_path}' | Out-Null")
    )
    assert lines.index(gateway) > lines.index(
        f"New-Item -ItemType File -Force '{log_path}' | Out-Null"
    )
    assert lines.index(harness) > lines.index(gateway)


def test_arm_script_separates_the_blocking_command_from_the_measuring_one(
    tmp_path: Path,
) -> None:
    """Two terminals, said plainly, because uvicorn never returns to the prompt."""
    script = render_arm_script(_experiment(tmp_path), _experiment(tmp_path).arms[1])
    lines = script.splitlines()
    split = next(i for i, line in enumerate(lines) if line.startswith("# Terminal 2"))

    assert any(line.startswith("# Terminal 1") for line in lines[:split])
    assert any("uvicorn" in line for line in lines[:split])
    assert not any("quality_harness.py" in line for line in lines[:split])
    assert any("quality_harness.py" in line for line in lines[split:])
    assert "does not return" in "\n".join(lines[:split])
    assert "/health" in "\n".join(lines[split:])
    # The second block stands on its own: it carries its own Set-Location, so a
    # person can paste it into a fresh terminal without the first one's context.
    assert any(line.startswith("Set-Location") for line in lines[split:])


def test_launch_script_holds_both_arm_blocks(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path)
    script = render_launch_script(experiment)

    assert script.index("arm 'off'") < script.index("arm 'on'")
    assert script.count("# Terminal 1") == 2
    assert script.count("# Terminal 2") == 2
    assert f"Set-Location '{Path(experiment.worktree)}'" in script
    assert "--timeout '345'" in script


# ---------------------------------------------------------------------------
# The tree must prove it is a detached worktree, without Git being asked
# ---------------------------------------------------------------------------


def test_an_arbitrary_empty_directory_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "tree"
    empty.mkdir()
    experiment = _experiment(tmp_path, worktree=empty)
    state = ab_launcher.inspect_worktree(empty)

    assert state.exists is True
    assert state.marker == ab_launcher.WORKTREE_MARKER_NONE
    assert state.detached is None
    assert state.missing_paths == REQUIRED_WORKTREE_PATHS
    assert state.can_run_an_arm is False
    problems = _problems(experiment)
    assert "holds no .git marker" in problems
    assert "does not hold" in problems


def test_a_plain_clone_is_refused(tmp_path: Path) -> None:
    tree = _make_worktree(tmp_path / "tree")
    (tree / ab_launcher.GIT_ADMIN_NAME).unlink()
    (tree / ab_launcher.GIT_ADMIN_NAME).mkdir()
    state = ab_launcher.inspect_worktree(tree)

    assert state.marker == ab_launcher.WORKTREE_MARKER_CLONE
    assert state.detached is None
    assert "clone rather than" in _problems(_experiment(tmp_path, worktree=tree))


def test_a_worktree_checked_out_on_a_branch_is_refused(tmp_path: Path) -> None:
    tree = _make_worktree(tmp_path / "tree", detached=False)
    state = ab_launcher.inspect_worktree(tree)

    assert state.marker == ab_launcher.WORKTREE_MARKER_LINKED
    assert state.detached is False
    assert state.can_run_an_arm is False
    assert "not detached" in _problems(_experiment(tmp_path, worktree=tree))


def test_a_pruned_worktree_is_refused(tmp_path: Path) -> None:
    tree = _make_worktree(tmp_path / "tree")
    shutil.rmtree(Path(str(ab_launcher.inspect_worktree(tree).git_dir)))
    state = ab_launcher.inspect_worktree(tree)

    assert state.marker == ab_launcher.WORKTREE_MARKER_STALE
    assert "no longer" in _problems(_experiment(tmp_path, worktree=tree))


def test_a_marker_pointing_at_an_ordinary_git_dir_is_refused(tmp_path: Path) -> None:
    tree = _make_worktree(tmp_path / "tree")
    submodule = tmp_path / "notworktrees" / "somewhere"
    submodule.mkdir(parents=True)
    (submodule / "HEAD").write_text(f"{DETACHED_HEAD}\n", encoding="utf-8")
    (tree / ab_launcher.GIT_ADMIN_NAME).write_text(
        f"gitdir: {submodule}\n", encoding="utf-8"
    )
    state = ab_launcher.inspect_worktree(tree)

    assert state.marker == ab_launcher.WORKTREE_MARKER_NONE
    assert "not a" in _problems(_experiment(tmp_path, worktree=tree))


@pytest.mark.parametrize("missing", REQUIRED_WORKTREE_PATHS)
def test_a_tree_missing_a_file_both_commands_need_is_refused(
    tmp_path: Path,
    missing: str,
) -> None:
    tree = _make_worktree(tmp_path / "tree")
    (tree / missing).unlink()
    state = ab_launcher.inspect_worktree(tree)

    assert state.marker == ab_launcher.WORKTREE_MARKER_LINKED
    assert state.missing_paths == (missing,)
    assert state.can_run_an_arm is False
    problems = _problems(_experiment(tmp_path, worktree=tree))
    assert "does not hold" in problems
    assert missing.lower() in problems


def test_a_directory_that_was_never_made_is_refused_by_name(tmp_path: Path) -> None:
    experiment = _experiment(tmp_path)
    gone = Path(experiment.worktree) / "not-made"

    assert ab_launcher.inspect_worktree(gone).exists is False
    assert "not a directory" in _problems(
        dataclasses.replace(experiment, worktree=str(gone))
    )


# ---------------------------------------------------------------------------
# The five settings that can change what a run measures
# ---------------------------------------------------------------------------


def test_measurement_settings_are_required_of_every_arm() -> None:
    for key in MEASUREMENT_ENV_KEYS:
        assert key in REQUIRED_SHARED_ENV_KEYS, key


def test_both_arms_receive_the_measurement_settings_identically(
    tmp_path: Path,
) -> None:
    experiment = _experiment(tmp_path)
    off = arm_environment(experiment, experiment.arms[0])
    on = arm_environment(experiment, experiment.arms[1])

    for key in MEASUREMENT_ENV_KEYS:
        assert off[key] == on[key] == TEMPLATE_MEASUREMENT_ENV[key], key
    assert set(experiment_document(experiment)["arm_differences"]) == set(
        ab_launcher.ALLOWED_ARM_ENV_KEYS
    )


def test_a_measurement_setting_left_out_is_reported(tmp_path: Path) -> None:
    base = _experiment(tmp_path)
    for key in MEASUREMENT_ENV_KEYS:
        shared = dict(base.shared_env)
        shared.pop(key)

        problems = _problems(dataclasses.replace(base, shared_env=shared))
        assert "missing required shared setting" in problems, key
        assert key.lower() in problems, key


def test_a_measurement_setting_carried_by_the_terminal_is_not_enough(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The launcher's own environment must not stand in for the experiment's."""
    monkeypatch.setenv("RELATIONSHIP_RANKING_ENABLED", "false")
    base = _experiment(tmp_path)
    shared = dict(base.shared_env)
    shared.pop("RELATIONSHIP_RANKING_ENABLED")

    assert "missing required shared setting" in _problems(
        dataclasses.replace(base, shared_env=shared)
    )


def test_the_two_relationship_switches_need_the_exact_lowercase_word(
    tmp_path: Path,
) -> None:
    """packages/context compares these with the text 'false', not a bool parse."""
    base = _experiment(tmp_path)
    for key in ab_launcher.LITERAL_BOOL_ENV_KEYS:
        for value in ("True", "TRUE", "FALSE", "1", "no"):
            shared = dict(base.shared_env)
            shared[key] = value

            assert "exact word" in _problems(
                dataclasses.replace(base, shared_env=shared)
            ), (key, value)
        for value in ab_launcher.LITERAL_BOOL_VALUES:
            shared = dict(base.shared_env)
            shared[key] = value

            assert _problems(dataclasses.replace(base, shared_env=shared)) == "", (
                key,
                value,
            )


def test_the_intent_rules_must_be_a_json_object(tmp_path: Path) -> None:
    base = _experiment(tmp_path)
    for value in ("not json", "[{}]", "null", "3"):
        shared = dict(base.shared_env)
        shared["APP_CONTEXT_INTENT_RULES"] = value

        assert "app_context_intent_rules" in _problems(
            dataclasses.replace(base, shared_env=shared)
        ), value
    for value in ("{}", '{"refactor": {"intent": "code_edit"}}'):
        shared = dict(base.shared_env)
        shared["APP_CONTEXT_INTENT_RULES"] = value

        assert _problems(dataclasses.replace(base, shared_env=shared)) == "", value


def test_the_delta_cache_must_hold_and_the_ttl_must_not_be_negative(
    tmp_path: Path,
) -> None:
    base = _experiment(tmp_path)
    for key, bad in (
        ("APP_CONTEXT_DELTA_CACHE_SIZE", "0"),
        ("APP_CONTEXT_DELTA_CACHE_SIZE", "-1"),
        ("APP_CONTEXT_DELTA_CACHE_SIZE", "wide"),
        ("APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS", "-1"),
        ("APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS", "soon"),
    ):
        shared = dict(base.shared_env)
        shared[key] = bad

        assert key.lower() in _problems(
            dataclasses.replace(base, shared_env=shared)
        ), (key, bad)
    for key, good in (
        ("APP_CONTEXT_DELTA_CACHE_SIZE", "1"),
        ("APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS", "0"),
        ("APP_REPOSITORY_CONTEXT_CHANGED_FILES_TTL_SECONDS", "300"),
    ):
        shared = dict(base.shared_env)
        shared[key] = good

        assert _problems(dataclasses.replace(base, shared_env=shared)) == "", (
            key,
            good,
        )


def test_a_measurement_setting_must_not_be_overridden_per_arm(tmp_path: Path) -> None:
    for key in MEASUREMENT_ENV_KEYS:
        arms = list(_experiment(tmp_path).arms)
        arms[1] = dataclasses.replace(arms[1], env={key: "64"})

        assert "must be identical in both arms" in _problems(
            _experiment(tmp_path, arms=tuple(arms))
        ), key


def test_template_carries_the_measurement_settings(tmp_path: Path) -> None:
    tree = _make_worktree(tmp_path / "t")
    experiment = template_experiment(name="tmpl", worktree=str(tree))

    assert validate_experiment(experiment) == ()
    for key, value in TEMPLATE_MEASUREMENT_ENV.items():
        assert experiment.shared_env[key] == value, key
    for arm in experiment_document(experiment)["arms"].values():
        for key, value in TEMPLATE_MEASUREMENT_ENV.items():
            assert arm["environment"][key] == value, key
