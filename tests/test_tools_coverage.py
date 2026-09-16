import os
import subprocess


ROOT = os.path.dirname(os.path.dirname(__file__))
COVERAGE_COMMAND = os.path.join(ROOT, "tools", "coverage")


def test_coverage_command_is_executable_and_configures_html_contexts(tmp_path):
    executable = tmp_path / "python"
    arguments = tmp_path / "arguments"
    executable.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$@" > "$FAKE_PYTHON_ARGS"\n'
    )
    executable.chmod(0o755)

    environment = os.environ.copy()
    environment["PATH"] = f"{tmp_path}:{environment['PATH']}"
    environment["FAKE_PYTHON_ARGS"] = str(arguments)
    result = subprocess.run(
        [COVERAGE_COMMAND, "tests/test_tools_coverage.py"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert os.access(COVERAGE_COMMAND, os.X_OK)
    assert arguments.read_text().splitlines() == [
        "-m",
        "pytest",
        "-q",
        "--cov=tools/atlas_agent",
        "--cov-branch",
        "--cov-context=test",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "tests/test_tools_coverage.py",
    ]
