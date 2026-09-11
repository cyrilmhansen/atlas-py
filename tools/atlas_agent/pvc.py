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
                "--work-root", "/var/tmp/work"]
        if self.profile is not None:
            args += ["--profile", self.profile]
        return tuple(args + list(self.sources))


def build_prepare_command(command,
                          request: PvcPrepareRequest) -> tuple[str, ...]:
    """Return the complete explicit argv, including the qualified executable."""
    return (str(command.guest_path), *request.argv())


@dataclass(frozen=True)
class PvcPrepareResult:
    process: ProcessResult
    request: PvcPrepareRequest

    @property
    def output_interpreted(self) -> bool:
        # This slice executes PVC only; snapshot/bundle interpretation is a
        # separate operation and must never be inferred from exit status.
        return False


def execute_prepare(
    request: PvcPrepareRequest,
    *,
    capability_plan: CapabilityPlan,
    executor: OneShotExecutor,
    stdout_path: Path,
    stderr_path: Path,
) -> PvcPrepareResult:
    if not isinstance(capability_plan, CapabilityPlan):
        raise TypeError("capability_plan is required")
    command = capability_plan.command("pvc")
    return PvcPrepareResult(
        executor.run(command, request.argv(), cwd=request.project_root,
                     capability_plan=capability_plan,
                     stdout_path=Path(stdout_path), stderr_path=Path(stderr_path)),
        request,
    )
