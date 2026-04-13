from __future__ import annotations

import subprocess

import pytest

from app.services.onchainos_runner import OnchainOSCommandError, OnchainOSMutatingRunner, OnchainOSReadonlyRunner


def test_runner_rejects_side_effecting_swap_execute() -> None:
    runner = OnchainOSReadonlyRunner()
    with pytest.raises(OnchainOSCommandError):
        runner.run("onchainos swap execute --from eth --to usdc --readable-amount 1 --chain xlayer")


def test_runner_rejects_shell_operators() -> None:
    runner = OnchainOSReadonlyRunner()
    with pytest.raises(OnchainOSCommandError):
        runner.run("onchainos token search --query pepe | cat")


def test_runner_executes_and_parses_json(monkeypatch) -> None:
    runner = OnchainOSReadonlyRunner(timeout_seconds=5)

    def fake_run(argv, *, capture_output, text, timeout, check):
        assert argv == ["onchainos", "token", "search", "--query", "pepe"]
        assert capture_output is True
        assert text is True
        assert timeout == 5
        assert check is False
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout='{"code":"0","data":[{"symbol":"PEPE"}]}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = runner.run("onchainos token search --query pepe")

    assert result["ok"] is True
    assert result["payload"] == {"code": "0", "data": [{"symbol": "PEPE"}]}
    assert result["exit_code"] == 0


def test_runner_surfaces_nonzero_exit(monkeypatch) -> None:
    runner = OnchainOSReadonlyRunner(timeout_seconds=5)

    def fake_run(argv, *, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="permission denied")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = runner.run("onchainos wallet status")

    assert result["ok"] is False
    assert result["error"] == "permission denied"
    assert result["exit_code"] == 2


def test_mutating_runner_allows_swap_execute(monkeypatch) -> None:
    runner = OnchainOSMutatingRunner(timeout_seconds=7)

    def fake_run(argv, *, capture_output, text, timeout, check):
        assert argv == [
            "onchainos",
            "swap",
            "execute",
            "--from",
            "ETH",
            "--to",
            "USDC",
            "--readable-amount",
            "1.0",
            "--chain",
            "xlayer",
            "--wallet",
            "0xabc",
        ]
        assert timeout == 7
        return subprocess.CompletedProcess(argv, 0, stdout='{"data":{"swapTxHash":"0xtx"}}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = runner.run("onchainos swap execute --from ETH --to USDC --readable-amount 1.0 --chain xlayer --wallet 0xabc")
    assert result["ok"] is True
    assert result["payload"] == {"data": {"swapTxHash": "0xtx"}}


def test_mutating_runner_rejects_non_whitelisted_commands() -> None:
    runner = OnchainOSMutatingRunner()
    with pytest.raises(OnchainOSCommandError):
        runner.run("onchainos market price --address 0xtoken")
