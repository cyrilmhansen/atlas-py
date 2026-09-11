"""The deliberately small PVC prepare consumer of the one-shot boundary."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .one_shot import OneShotExecutor, ProcessResult
from .toolchains import CapabilityPlan


class PvcRequestError(ValueError):
    pass


def _validated_sources(root: Path, sources: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    root = Path(root).resolve()
    result = []
    for value in sources:
        if not isinstance(value, str) or not value:
            raise PvcRequestError("PVC_SOURCE_INVALID")
        path = Path(value)
        if (path.is_absolute() or ".." in path.parts or value.startswith("-")
                or any(char in value for char in "*?[")):
            raise PvcRequestError("PVC_SOURCE_INVALID")
        candidate = root / path
        try:
            # Reject symlinks in every component, including a symlink source.
            current = root
            for part in path.parts:
                current /= part
                if current.is_symlink():
                    raise PvcRequestError("PVC_SOURCE_SYMLINK")
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(root) or not candidate.is_file():
                raise PvcRequestError("PVC_SOURCE_INVALID")
        except FileNotFoundError as error:
            raise PvcRequestError("PVC_SOURCE_INVALID") from error
        result.append(path.as_posix())
    return tuple(result)


@dataclass(frozen=True)
class PvcPrepareRequest:
    project_root: Path
    sources: tuple[str, ...]
    profile: str | None = None

    def __post_init__(self):
        if self.profile not in (None, "normal", "conservative"):
            raise PvcRequestError("PVC_PROFILE_INVALID")
        object.__setattr__(self, "project_root", Path(self.project_root).resolve())
        if not self.sources:
            raise PvcRequestError("PVC_SOURCE_REQUIRED")
        object.__setattr__(self, "sources",
                           _validated_sources(self.project_root, self.sources))

    def argv(self) -> tuple[str, ...]:
        args = ["prepare", "--cwd", str(self.project_root),
                "--output", "/var/tmp/bundle",
                "--work-root", "/var/tmp/work",
                "--state-root", "/var/tmp/state"]
        if self.profile is not None:
            args += ["--profile", self.profile]
        return tuple(args + list(self.sources))


def build_prepare_command(command,
                          request: PvcPrepareRequest) -> tuple[str, ...]:
    """Return the complete explicit argv, including the qualified executable."""
    return (str(command.guest_path), *request.argv())


@dataclass(frozen=True)
class PvcPrepareResult:
    """The non-durable result of one qualified PVC prepare operation.

    The scratch directory is intentionally retained on successful execution.
    These paths describe where this invocation wrote (or was expected to
    write) its output; they are not a claim that the output is a valid PVC
    bundle.  The next slice can therefore validate these exact bytes without
    invoking PVC again.
    """

    process: ProcessResult
    request: PvcPrepareRequest

    @property
    def scratch_path(self) -> Path:
        """Private operation scratch retained for a subsequent validator."""
        if self.process.scratch_path is None:
            raise RuntimeError("PVC result has no retained scratch")
        return self.process.scratch_path

    @property
    def bundle_path(self) -> Path:
        return self.scratch_path / "bundle"

    @property
    def work_path(self) -> Path:
        return self.scratch_path / "work"

    @property
    def stdout_path(self) -> Path:
        return self.process.stdout_path

    @property
    def stderr_path(self) -> Path:
        return self.process.stderr_path

    @property
    def process_succeeded(self) -> bool:
        return self.process.succeeded

    @property
    def bundle_validated(self) -> bool:
        """Process success is deliberately not bundle validation."""
        return False

    @property
    def output_interpreted(self) -> bool:
        return self.bundle_validated


def execute_prepare(
    request: PvcPrepareRequest,
    *,
    capability_plan: CapabilityPlan,
    executor: OneShotExecutor,
) -> PvcPrepareResult:
    """Execute PVC with process output retained in its private scratch."""
    if not isinstance(capability_plan, CapabilityPlan):
        raise TypeError("capability_plan is required")
    command = capability_plan.command("pvc")
    return PvcPrepareResult(
        executor.run(command, request.argv(), cwd=request.project_root,
                     capability_plan=capability_plan,
                     stdout_path=None, stderr_path=None),
        request,
    )
