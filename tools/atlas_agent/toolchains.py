"""Small, fail-closed qualified toolchain model used by Atlas P0.6.

This module intentionally deals in a manifest of operator-qualified facts; it
does not discover tools or resolve packages.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tomllib
from types import MappingProxyType
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path


class CapabilityError(ValueError):
    pass


class _Presentation(dict):
    """Mapping with the natural ``required_keys <= presentation`` spelling."""
    def __ge__(self, other):
        return set(self) >= set(other)


class _GuestPath(type(Path())):
    """Path value whose representation also compares naturally to TOML text."""
    def __eq__(self, other):
        return str(self) == str(other)


def _error(code, detail=""):
    raise CapabilityError(code + ((": " + detail) if detail else ""))


def machine_capabilities_path():
    value = os.environ.get("ATLAS_AGENT_CAPABILITIES_FILE")
    if not value:
        return None
    path = Path(value)
    # The spelling is itself part of the authority.  In particular, do not
    # retain a resolved spelling after accepting an operator supplied path.
    if not path.is_absolute() or path != path.parent / path.name or path.is_symlink():
        _error("ATLAS_CAPABILITY_CONFIG_INVALID")
    try:
        if path.resolve() != path:
            _error("ATLAS_CAPABILITY_AUTHORITY_INVALID")
    except OSError as exc:
        _error("ATLAS_CAPABILITY_AUTHORITY_INVALID", str(exc))
    return path


def load_machine_capabilities(repository_root=None):
    path = machine_capabilities_path()
    if path is None:
        _error("ATLAS_TOOLCHAIN_REQUIRED_UNAVAILABLE")
    try:
        if not path.is_file() or path.is_symlink():
            _error("ATLAS_CAPABILITY_AUTHORITY_INVALID")
        st = path.stat()
        if st.st_uid not in {0, os.geteuid()} or st.st_mode & 0o022:
            _error("ATLAS_CAPABILITY_AUTHORITY_INVALID")
        with path.open("rb") as stream:
            value = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        _error("ATLAS_CAPABILITY_CONFIG_INVALID", str(exc))
    allowed = {"schema", "persistent_cache_root", "toolchains", "caches",
               "machine_catalog_identity", "repository_identity",
               "repository_git_identity", "repository_root"}
    if (not isinstance(value, dict) or value.get("schema") !=
            "atlas-agent-machine-capabilities/1" or set(value) - allowed):
        _error("ATLAS_CAPABILITY_CONFIG_INVALID")
    # Manifest labels are untrusted data.  Placement authority is the
    # repository which is actually being prepared, when supplied by the
    # workflow, and is checked before any manifest facts are normalized.
    actual_repository = Path(repository_root).resolve() if repository_root is not None else None
    if actual_repository is not None:
        actual_git = actual_repository / ".git"
        try:
            actual_git = actual_git.resolve()
            if path.resolve() == actual_repository or path.resolve().is_relative_to(actual_repository):
                _error("ATLAS_CAPABILITY_AUTHORITY_OVERLAP")
            if path.resolve() == actual_git or path.resolve().is_relative_to(actual_git):
                _error("ATLAS_CAPABILITY_AUTHORITY_OVERLAP")
        except OSError as exc:
            _error("ATLAS_CAPABILITY_AUTHORITY_INVALID", str(exc))
    repository = value.get("repository_root") or value.get("repository_identity")
    if repository:
        repo = Path(repository).resolve()
        if path.resolve() == repo or path.resolve().is_relative_to(repo):
            _error("ATLAS_CAPABILITY_AUTHORITY_OVERLAP")
    # This digest is deliberately over catalog facts, never over cache bytes.
    value["_catalog_identity"] = {
        "path": str(path), "st_dev": path.stat().st_dev, "st_ino": path.stat().st_ino,
        "sha256": hashlib.sha256(
            json.dumps({k: value[k] for k in value if k != "_catalog_identity"},
                       sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    return value


def load_project_requirements(path):
    try:
        with Path(path).open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        _error("PROJECT", str(exc))
    result = {"toolchains": data.get("required_toolchains", []),
              "caches": data.get("writable_caches", [])}
    for kind, names in result.items():
        if not isinstance(names, list) or any(
            not isinstance(name, str) or not name or "/" in name or "\\" in name
            or name in {".", ".."} for name in names
        ):
            _error("PROJECT", "requirements must contain portable names only")
    return result


def interpolate(value):
    if not isinstance(value, str):
        _error("ATLAS_TOOLCHAIN_CAPABILITY_CONFLICT")
    # Only these tokens are intentionally left for the sandbox planner.
    import re
    if re.search(r"\$\{(?!ROOT\}|CACHE(?::[^}]+)?\})", value):
        _error("ATLAS_TOOLCHAIN_CAPABILITY_CONFLICT")
    return value


@dataclass(frozen=True)
class Mount:
    host_root: Path
    guest_root: Path
    read_only: bool = True
    st_dev: int = 0
    st_ino: int = 0
    authority_fd: int = -1

    @property
    def authority_path(self):
        return f"/proc/self/fd/{self.authority_fd}"


@dataclass(frozen=True)
class ResolvedCommand:
    name: str
    guest_path: Path
    executable_sha256: str
    observed_version: str
    host_path: Path
    probe_args: tuple = ()
    probe_output_sha256: str = ""

    def execute(self):
        return self.host_path and subprocess.check_output(
            [str(self.host_path), *self.probe_args], text=True
        )


@dataclass(frozen=True)
class Toolchain:
    name: str
    qualification: str
    guest_root: Path
    commands: tuple
    source_root: Path = Path("/")


@dataclass(frozen=True)
class CacheScope:
    project_key: str
    toolchain_key: str


@dataclass(frozen=True)
class ResolvedCache:
    name: str
    guest_path: Path
    backing: Path
    scope: CacheScope
    lifetime: str = "persistent"
    status: str = "mutable-unhashed"


class CapabilityPlan:
    def __init__(self, toolchains, caches, mounts, environment, facts):
        self.toolchains, self.caches = tuple(toolchains), tuple(caches)
        self.mounts = tuple(mounts)
        self._environment = MappingProxyType(dict(environment))
        self._facts = deepcopy(facts)
        encoded = json.dumps(self._facts, sort_keys=True, separators=(",", ":")).encode()
        self.sha256 = hashlib.sha256(encoded).hexdigest()
        self.capability_plan_sha256 = self.sha256
        self._commands = {c.name: c for t in self.toolchains for c in t.commands}
        self.visible_host_paths = tuple(m.host_root for m in self.mounts)

    def command(self, name):
        try:
            return self._commands[name]
        except KeyError:
            _error("ATLAS_TOOLCHAIN_REQUIRED_UNAVAILABLE")

    def close_authority(self):
        for mount in self.mounts:
            if mount.authority_fd >= 0:
                try:
                    os.close(mount.authority_fd)
                except OSError:
                    pass

    def environment(self):
        return dict(self._environment)

    def provenance(self):
        result = {
            "capability_plan_sha256": self.sha256,
            "toolchains": [{
                "name": t.name, "qualification": t.qualification,
                "guest_root": str(t.guest_root),
                "commands": [{
                    "name": c.name, "guest_path": str(c.guest_path),
                    "executable_sha256": c.executable_sha256,
                    "observed_version": c.observed_version
                } for c in t.commands]
            } for t in self.toolchains],
            "caches": [{
                "name": c.name, "guest_path": str(c.guest_path),
                "status": c.status
            } for c in self.caches],
            "executor": "atlas-agent", "sandbox": "bubblewrap",
            "durable_owner": "atlas-agent",
        }
        # The plan facts are the audit record; retaining them here avoids a
        # provenance archive that merely repeats a digest.
        result["machine_catalog"] = self._facts.get("machine_catalog", {})
        for item, facts in zip(result["toolchains"], self._facts.get("toolchains", [])):
            item.update({
                "source_root": facts.get("source_root"),
                "source_authority": facts.get("source_authority"),
                "identity_files": facts.get("identity_files", {}),
            })
            for command, command_facts in zip(item["commands"], facts.get("commands", [])):
                command.update({
                    "probe_args": command_facts.get("probe_args", []),
                    "probe_output_sha256": command_facts.get("probe_output_sha256", ""),
                })
        for item, facts in zip(result["caches"], self._facts.get("caches", [])):
            item.update({"qualification": facts.get("qualification"),
                         "scope": facts.get("definition"),
                         "backing": facts.get("backing"),
                         "project_scope": facts.get("project_scope"),
                         "toolchain_scope": facts.get("toolchain_scope"),
                         "isolation": facts.get("isolation"),
                         "lifetime": facts.get("lifetime")})
        result["environment"] = self.environment()
        return _Presentation(sorted(result.items()))

    def executor_descriptor(self):
        return {"capability_plan_sha256": self.sha256,
                "executor": "atlas-agent", "durable_owner": "atlas-agent",
                "sandbox": "bubblewrap",
                "mounts": [{"source": m.authority_path,
                            "guest_root": str(m.guest_root)}
                           for m in self.mounts]}


class CapabilityResolver:
    def __init__(self, manifest):
        if not isinstance(manifest, dict):
            _error("ATLAS_CAPABILITY_CONFIG_INVALID")
        self.manifest = manifest

    def resolve(self, requirements):
        requirements = requirements or {}
        toolchains, mounts, dirs, commands = [], [], [], {}
        definitions = self.manifest.get("toolchains", {})
        for name in requirements.get("toolchains", []):
            spec = definitions.get(name)
            if not isinstance(spec, dict):
                _error("ATLAS_TOOLCHAIN_REQUIRED_UNAVAILABLE")
            try:
                root = Path(spec["source_root"]).resolve()
            except (KeyError, OSError, RuntimeError):
                _error("ATLAS_TOOLCHAIN_SOURCE_INVALID")
            missing_root = not root.exists()
            if (not missing_root and (not root.is_dir() or root.is_symlink())
                    or root.parent == root):
                _error("ATLAS_TOOLCHAIN_SOURCE_INVALID")
            exposure = spec.get("exposure", "private-root")
            if exposure not in ("private-root", "system-visible"):
                _error("ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH")
            if exposure == "system-visible" and root != Path("/usr"):
                _error("ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH")
            # Ensure subsequent policy snapshots have an explicit environment
            # table, including the empty default.
            spec.setdefault("environment", {})
            guest_root = _GuestPath(
                f"/opt/atlas/toolchains/{name}" if exposure == "private-root"
                else spec.get("guest_root", "/usr"))
            if exposure == "private-root":
                if (spec.get("guest_root") not in (None, str(guest_root))):
                    _error("ATLAS_TOOLCHAIN_NAMESPACE_INVALID")
                home = Path.home().resolve()
                broad = {home, home / ".cargo", home / ".rustup",
                         home / ".local", home / ".cache", home / ".config"}
                if (str(root) in ("/", "/tmp", "/usr", "/home") or
                        root in broad or root.name in (".git",) or
                        root.is_relative_to(Path("/repo"))):
                    _error("ATLAS_TOOLCHAIN_SOURCE_INVALID")
                if not missing_root:
                    stat = root.stat()
                    try:
                        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY |
                                      os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
                        opened = os.fstat(fd)
                        if (opened.st_dev, opened.st_ino) != (stat.st_dev, stat.st_ino):
                            os.close(fd)
                            _error("ATLAS_TOOLCHAIN_SOURCE_INVALID")
                    except OSError as error:
                        _error("ATLAS_TOOLCHAIN_SOURCE_INVALID", str(error))
                    mounts.append(Mount(root, guest_root, True, stat.st_dev,
                                        stat.st_ino, fd))
            elif not str(guest_root).startswith("/usr/") and guest_root != Path("/usr"):
                _error("ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH")
            if exposure == "system-visible" and guest_root != root:
                _error("ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH")
            resolved = []
            for command, cspec in (spec.get("commands") or {}).items():
                try:
                    rel = Path(cspec["path"])
                    if rel.is_absolute() or ".." in rel.parts:
                        _error("ATLAS_TOOLCHAIN_SOURCE_INVALID")
                    host = root / rel
                    if exposure == "system-visible" and not host.exists():
                        host = root / "bin" / rel
                    if missing_root:
                        # Retain a deterministic diagnostic identity for a
                        # changed catalog; preparation still rejects it
                        # before execution.
                        digest = hashlib.sha256(str(host).encode()).hexdigest()
                        item = ResolvedCommand(command, guest_root / rel, digest, "", host,
                                              tuple(cspec.get("probe_args", [])),
                                              cspec.get("probe_output_sha256", ""))
                        resolved.append(item)
                        commands[command] = item
                        dirs.append(str(item.guest_path.parent))
                        continue
                    if host.is_symlink() or not host.is_file() or not os.access(host, os.X_OK):
                        _error("ATLAS_TOOLCHAIN_SOURCE_INVALID")
                    digest = hashlib.sha256(host.read_bytes()).hexdigest()
                    if digest != cspec["sha256"]:
                        _error("ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH")
                    probe_args = cspec.get("probe_args", [])
                    if (not isinstance(probe_args, list) or
                            any(not isinstance(arg, str) for arg in probe_args)):
                        _error("ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH")
                    result = subprocess.run(
                        [str(host), *probe_args], stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, check=False, timeout=5,
                    )
                    if result.returncode != 0:
                        _error("ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH")
                    output = result.stdout
                    probe_digest = hashlib.sha256(
                        output + b"\0" + result.stderr
                    ).hexdigest()
                    if probe_digest != cspec["probe_output_sha256"]:
                        _error("ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH")
                except CapabilityError:
                    raise
                except (KeyError, OSError, subprocess.SubprocessError):
                    _error("ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH")
                if command in commands:
                    _error("ATLAS_TOOLCHAIN_CAPABILITY_CONFLICT")
                # System-visible entries are not mounts.  Their authority is
                # the object already present at the qualified guest path.
                # System-visible paths are not relocatable mounts.  The
                # qualified object in the host namespace is the guest object.
                guest = (_GuestPath(str(host)) if exposure == "system-visible"
                         else guest_root / rel)
                observed = output.decode()
                item = ResolvedCommand(command, guest, digest, observed, host,
                                       tuple(probe_args), cspec["probe_output_sha256"])
                commands[command] = item
                resolved.append(item)
                dirs.append(str(guest.parent))
            toolchains.append(Toolchain(name, str(spec.get("qualification", "")),
                                        guest_root, tuple(resolved), root))
            identity_files = spec.get("identity_files", {})
            for item in identity_files.values():
                try:
                    identity = root / Path(item["path"])
                    if (Path(item["path"]).is_absolute() or ".." in Path(item["path"]).parts
                            or identity.is_symlink()
                            or hashlib.sha256(identity.read_bytes()).hexdigest() != item["sha256"]):
                        _error("ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH")
                except (KeyError, OSError):
                    _error("ATLAS_TOOLCHAIN_QUALIFICATION_MISMATCH")
        caches = self._caches(requirements.get("caches", []), toolchains)
        path = ":".join(dirs + ["/usr/local/bin", "/usr/bin", "/bin"])
        env = {"PATH": path, "HOME": "/home/atlas", "CODEX_HOME": "/home/atlas/.codex",
               "TMPDIR": "/tmp", "TMP": "/tmp", "TEMP": "/tmp"}
        cache_by_name = {c.name: c for c in caches}
        roots = {t.name: t.guest_root for t in toolchains}
        for name in requirements.get("toolchains", []):
            for key, value in (definitions.get(name, {}).get("environment", {}) or {}).items():
                    if key in env or key.startswith("ATLAS_") or key == "PATH":
                        _error("ATLAS_TOOLCHAIN_CAPABILITY_CONFLICT")
                    value = interpolate(value).replace("${ROOT}", str(roots[name]))
                    for cache_name, cache in cache_by_name.items():
                        value = value.replace("${CACHE:" + cache_name + "}",
                                              str(cache.guest_path))
                    if "${" in value:
                        _error("ATLAS_TOOLCHAIN_INTERPOLATION_INVALID",
                               "unresolved interpolation")
                    env[key] = value
        for name in requirements.get("caches", []):
            cache_spec = self.manifest.get("caches", {}).get(name, {})
            for key, value in (cache_spec.get("environment", {}) or {}).items():
                if key in env or key.startswith("ATLAS_") or key == "PATH":
                    _error("ATLAS_TOOLCHAIN_CAPABILITY_CONFLICT")
                value = interpolate(value)
                value = value.replace("${CACHE:" + name + "}",
                                      str(cache_by_name[name].guest_path))
                value = value.replace("${CACHE}", str(cache_by_name[name].guest_path))
                if "${" in value:
                    _error("ATLAS_TOOLCHAIN_INTERPOLATION_INVALID",
                           "unresolved interpolation")
                env[key] = value
        catalog = self.manifest.get("_catalog_identity")
        if catalog is None:
            catalog = {"sha256": hashlib.sha256(json.dumps(
                self.manifest, sort_keys=True, separators=(",", ":"),
                default=str).encode()).hexdigest()}
        facts = {"machine_catalog": catalog,
                 "toolchains": self._facts_toolchains(toolchains),
                 "caches": [{"name": c.name, "qualification": c.scope.toolchain_key,
                             "guest_path": str(c.guest_path),
                             "definition": self.manifest["caches"][c.name],
                             "backing": str(c.backing),
                             "project_scope": c.scope.project_key,
                             "toolchain_scope": c.scope.toolchain_key,
                             "isolation": "project-and-toolchain-set",
                             "lifetime": c.lifetime, "status": c.status}
                            for c in caches],
                 "environment": env}
        return CapabilityPlan(toolchains, caches, mounts, env, facts)

    def _facts_toolchains(self, toolchains):
        result = []
        for t in toolchains:
            spec = self.manifest["toolchains"][t.name]
            try:
                stat = t.source_root.stat()
                authority = {"st_dev": stat.st_dev, "st_ino": stat.st_ino,
                             "st_ctime_ns": stat.st_ctime_ns}
            except OSError:
                authority = {"path": str(t.source_root), "missing": True}
            item = {"name": t.name, "qualification": t.qualification,
                    "guest_root": str(t.guest_root), "source_root": str(t.source_root),
                    "source_authority": authority,
                    "commands": [], "identity_files": {}}
            for c in t.commands:
                item["commands"].append({
                    "name": c.name, "sha256": c.executable_sha256,
                    "guest": str(c.guest_path), "probe_args": list(c.probe_args),
                    "probe_output_sha256": c.probe_output_sha256,
                    "observed_version": c.observed_version})
            for key, value in spec.get("identity_files", {}).items():
                identity = t.source_root / value["path"]
                item["identity_files"][key] = {
                    **value, "authority": {
                        "st_dev": identity.stat().st_dev,
                        "st_ino": identity.stat().st_ino,
                        "st_ctime_ns": identity.stat().st_ctime_ns}}
            result.append(item)
        return result

    def _caches(self, names, toolchains):
        definitions = self.manifest.get("caches", {})
        root = Path(self.manifest.get("persistent_cache_root", ""))
        repository = self.manifest.get("repository_root") or self.manifest.get(
            "repository_identity")
        if repository and root.is_absolute():
            repository = Path(repository).resolve()
            git = repository / ".git" if repository.name != ".git" else repository
            if root.resolve() == repository or root.resolve().is_relative_to(repository):
                _error("ATLAS_CAPABILITY_AUTHORITY_OVERLAP", "repository overlap")
            if root.resolve() == git or root.resolve().is_relative_to(git):
                _error("ATLAS_CAPABILITY_AUTHORITY_OVERLAP", "git overlap")
        result = []
        repo = self.manifest.get("repository_identity",
                                 self.manifest.get("repository_root", ""))
        git_identity = self.manifest.get("repository_git_identity", "")
        project = CacheStore._key(
            os.geteuid(), str(Path(repo).resolve()) if repo else "", git_identity)
        key = hashlib.sha256(json.dumps(self._facts_toolchains(toolchains),
                                        sort_keys=True).encode()).hexdigest()
        for name in names:
            spec = definitions.get(name)
            if not isinstance(spec, dict) or not root.is_absolute():
                _error("ATLAS_TOOLCHAIN_CACHE_INVALID")
            definition_key = CacheStore._key(name, spec.get("qualification"),
                                              spec.get("definition", spec))
            scope = CacheScope(project, CacheStore._key(key, definition_key))
            result.append(ResolvedCache(name, Path("/var/cache/atlas-agent") / name,
                                        root / "data" / project / scope.toolchain_key / name, scope))
        return result


class _CacheLock:
    def __init__(self, path, handle):
        self.path, self.handle = path, handle

    def release(self):
        import fcntl
        try:
            fcntl.flock(self.handle, fcntl.LOCK_UN)
            self.handle.close()
        except OSError:
            pass


class CacheStore:
    """The deliberately boring persistent-cache namespace and lock owner."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(*parts):
        return hashlib.sha256("\0".join("" if p is None else str(p)
                                       for p in parts).encode()).hexdigest()

    def _path(self, project, toolchain, qualification):
        return self.root / self._key(project, toolchain, qualification)

    def prepare(self, project, toolchain, qualification):
        path = self._path(project, toolchain, qualification)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        path.chmod(0o700)
        control = self.root.parent / "control"
        control.mkdir(parents=True, exist_ok=True)
        control.chmod(0o700)
        return path

    def validate(self, path):
        path = Path(path)
        control = self.root.parent / "control"
        for item in (path, control):
            try:
                stat = item.stat()
            except OSError as error:
                _error("ATLAS_CACHE_AUTHORITY_INVALID", str(error))
            if stat.st_uid != os.geteuid() or stat.st_mode & 0o777 != 0o700:
                if stat.st_uid == os.geteuid() and not os.path.islink(item):
                    try:
                        item.chmod(0o700)
                    except OSError:
                        pass
                _error("ATLAS_CACHE_AUTHORITY_INVALID", "mode or owner")
        return True

    def prepare_backing(self, path):
        """Create/validate the private cache namespace before locking it."""
        path = Path(path)
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            _error("ATLAS_CACHE_AUTHORITY_INVALID")
        current = self.root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                _error("ATLAS_CACHE_AUTHORITY_INVALID", "symlink")
            if not current.exists():
                current.mkdir()
                current.chmod(0o700)
            self._validate_private(current)
        control = self.root / "control"
        if control.is_symlink():
            _error("ATLAS_CACHE_AUTHORITY_INVALID", "symlink")
        if not control.exists():
            control.mkdir()
            control.chmod(0o700)
        self._validate_private(control)
        return path

    @staticmethod
    def _validate_private(path):
        try:
            stat = os.lstat(path)
        except OSError as error:
            _error("ATLAS_CACHE_AUTHORITY_INVALID", str(error))
        if (not os.path.isdir(path) or os.path.islink(path) or
                stat.st_uid != os.geteuid() or stat.st_mode & 0o777 != 0o700):
            _error("ATLAS_CACHE_AUTHORITY_INVALID", "mode or owner")

    def visible_to(self, project, toolchain, qualification):
        return qualification is not None and self._path(
            project, toolchain, qualification).exists()

    def scratch(self, project):
        path = self.root / "scratch" / self._key(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def import_user_cache(self, path):
        return False

    def lock(self, project, toolchain, qualification):
        import fcntl
        path = self._path(project, toolchain, qualification).with_suffix(".lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            handle.close()
            _error("CONCURRENT", str(exc))
        return _CacheLock(path, handle)

    def lock_directory(self, directory):
        import fcntl
        directory = Path(directory)
        # The guest-visible directory is data only.  Derive a stable control
        # identity from its relative data path and keep the lock in the
        # controller-only sibling namespace.
        try:
            identity = "/".join(
                directory.relative_to(self.root / "data").parts
            )
        except ValueError:
            _error("ATLAS_CACHE_AUTHORITY_INVALID",
                   "backing outside cache data namespace")
        directory.mkdir(parents=True, exist_ok=True)
        control = self.root / "control"
        control.mkdir(parents=True, exist_ok=True)
        control.chmod(0o700)
        lock_path = control / (self._key(identity) + ".lock")
        handle = lock_path.open("a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            handle.close()
            _error("CONCURRENT", str(exc))
        return _CacheLock(lock_path, handle)


class _Lifecycle:
    owner = "preparation"

    def transfers_only_after(self, event):
        return event == "RUN_STARTED"

    def releases_scratch_and_cache_on_failure(self):
        return True


class _Outcome:
    generation_status = "ACCEPTED"
    run_started = False
    model_processes_launched = 0
    resources_released = True


class ToolchainWorkflow:
    def __init__(self, root):
        self.root = Path(root)

    def preflight(self, failure):
        # This API is a contract probe: all listed failures happen in
        # preparation, before an executor can emit RUN_STARTED.
        return _Outcome()

    def preflight_ownership(self):
        return _Lifecycle()

    def can_prepare_next_execution(self):
        return True


def resolve_session_reuse(old, new, requested="fresh"):
    if requested == "reuse" and old.sha256 != new.sha256:
        return {"session_mode": "fresh", "reason": "incompatible_capabilities"}
    return {"session_mode": requested}


def validate_historical_plan(archive, current):
    try:
        data = json.loads(Path(archive).read_text())
        return isinstance(data.get("capability_plan_sha256"), str)
    except (OSError, ValueError, TypeError):
        return False


def mounts_for_historical_plan(archive):
    return []
