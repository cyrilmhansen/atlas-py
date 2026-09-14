import os
import subprocess


ROOT = os.path.dirname(os.path.dirname(__file__))
TEST_COMMAND = os.path.join(ROOT, "tools", "test")


def fake_python(tmp_path, status=0):
    log = tmp_path / "arguments"
    executable = tmp_path / "python"
    executable.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$@" > "$FAKE_PYTHON_ARGS"\n'
        'printf "fake stdout\\n"\n'
        'printf "fake stderr\\n" >&2\n'
        f"exit {status}\n"
    )
    executable.chmod(0o755)
    return executable, log


def run_with_fake_python(tmp_path, status=0):
    _, log = fake_python(tmp_path, status)
    environment = os.environ.copy()
    environment["PATH"] = f"{tmp_path}:{environment['PATH']}"
    environment["FAKE_PYTHON_ARGS"] = str(log)
    return subprocess.run(
        [TEST_COMMAND],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    ), log


def test_canonical_test_command_is_executable_and_invokes_pytest(tmp_path):
    assert os.path.isfile(TEST_COMMAND)
    assert os.access(TEST_COMMAND, os.X_OK)

    result, arguments = run_with_fake_python(tmp_path)

    assert result.returncode == 0
    assert arguments.read_text().splitlines() == ["-m", "pytest", "-q"]
    assert result.stdout == "fake stdout\n"
    assert result.stderr == "fake stderr\n"


def test_canonical_test_command_propagates_pytest_failure(tmp_path):
    result, _ = run_with_fake_python(tmp_path, status=7)

    assert result.returncode == 7
