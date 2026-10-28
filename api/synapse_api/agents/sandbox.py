"""Dépôt, copie de travail et bac à sable d'une tâche (lot 3b).

- Chaque projet a un dépôt Git géré par Synapse (`<git_dir>/repos/<projet>.git`, branche main).
  GitLab viendra avec les environnements ; seule cette classe changera.
- Chaque tâche travaille sur sa branche (`synapse/feat-001`), dans sa copie de travail.
  Synapse y lit et y écrit des fichiers, mais n'y exécute jamais le code généré.
- Le code généré s'exécute seulement dans un conteneur jetable, propre à la tâche : sans réseau
  (sauf pour installer les dépendances), sans secret, sans capacité système, ressources bornées.
"""

import json
import os
import shutil
import stat
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from pydantic import BaseModel, Field

from synapse_api.config import get_settings
from synapse_api.schemas import FileChange

CONFIG_FILE = "synapse.json"
GIT_IDENTITY = ["-c", "user.name=Synapse", "-c", "user.email=synapse@localhost", "-c", "core.autocrlf=false"]
OUTPUT_LIMIT = 20_000  # caractères de sortie gardés par commande (la fin, où sont les erreurs)
DIFF_LINES = 400  # lignes de diff gardées par fichier dans le livrable


class SandboxError(Exception):
    pass


class ProjectConfig(BaseModel):
    """Déclaré par le dépôt dans synapse.json (écrit par le Développeur au premier besoin)."""

    image: str | None = None
    install: str | None = Field(default=None, description="Installation des dépendances (réseau ouvert).")
    test: str | None = Field(default=None, description="Lancement de tous les tests (sans réseau).")


@dataclass(frozen=True)
class RunResult:
    command: str
    exit_code: int
    output: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class Sandbox(Protocol):
    def run(self, workspace: Path, command: str, *, image: str, network: bool, label: str) -> RunResult: ...


class DockerSandbox:
    def run(self, workspace: Path, command: str, *, image: str, network: bool, label: str) -> RunResult:
        settings = get_settings()
        name = f"synapse-{label}-{uuid.uuid4().hex[:8]}"
        args = [
            "docker", "run", "--rm", "--name", name,
            "--label", f"synapse.task={label}",
            "--cpus", settings.sandbox_cpus,
            "--memory", settings.sandbox_memory,
            "--pids-limit", "512",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "-e", "HOME=/tmp", "-e", "CI=1",
            "-v", f"{workspace.resolve()}:/workspace",
            "-w", "/workspace",
        ]  # fmt: skip
        if not network:
            args += ["--network", "none"]
        args += [image, "sh", "-c", command]
        try:
            done = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=settings.sandbox_timeout,
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
            return RunResult(command, 124, f"Arrêté après {settings.sandbox_timeout} s.", timed_out=True)
        except FileNotFoundError as exc:
            raise SandboxError("Docker est introuvable : le bac à sable ne peut pas démarrer.") from exc
        return RunResult(command, done.returncode, (done.stdout + done.stderr)[-OUTPUT_LIMIT:])


def safe_path(path: str) -> str:
    """Chemin relatif dans le dépôt ; refuse tout ce qui sortirait de la copie de travail."""
    clean = PurePosixPath(path.replace("\\", "/").strip())
    if (
        not clean.parts
        or clean.is_absolute()
        or ".." in clean.parts
        or clean.parts[0] == ".git"
        or ":" in path
    ):
        raise SandboxError(f"Chemin refusé : {path}")
    return clean.as_posix()


class Workspace:
    def __init__(self, root: Path, project_id: uuid.UUID, task_id: uuid.UUID, branch: str) -> None:
        self.repo = root / "repos" / f"{project_id}.git"
        self.path = root / "workspaces" / str(task_id)
        self.branch = branch

    def _git(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        done = subprocess.run(
            ["git", *GIT_IDENTITY, *args],
            cwd=cwd or self.path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if check and done.returncode != 0:
            raise SandboxError(f"git {' '.join(args)} : {done.stderr.strip()}")
        return done.stdout

    def ensure(self) -> None:
        """Crée au besoin le dépôt du projet, la copie de travail et la branche de la tâche."""
        if not self.repo.exists():
            self.repo.parent.mkdir(parents=True, exist_ok=True)
            self._git("init", "--bare", "-b", "main", str(self.repo), cwd=self.repo.parent)
            seed = self.repo.parent / f".seed-{uuid.uuid4().hex[:8]}"
            self._git("init", "-b", "main", str(seed), cwd=self.repo.parent)
            self._git("commit", "--allow-empty", "-m", "Dépôt créé par Synapse", cwd=seed)
            self._git("push", str(self.repo), "main", cwd=seed)
            _remove_tree(seed)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._git("clone", str(self.repo), str(self.path), cwd=self.path.parent)
        self._git("fetch", "origin")
        if self._git("branch", "--list", self.branch).strip():
            self._git("checkout", self.branch)
        elif self._git("ls-remote", "--heads", "origin", self.branch).strip():
            self._git("checkout", "-b", self.branch, f"origin/{self.branch}")
        else:
            self._git("checkout", "-b", self.branch, "origin/main")

    def config(self) -> ProjectConfig:
        file = self.path / CONFIG_FILE
        if not file.exists():
            return ProjectConfig()
        try:
            return ProjectConfig.model_validate(json.loads(file.read_text(encoding="utf-8")))
        except ValueError as exc:
            raise SandboxError(f"{CONFIG_FILE} illisible : {exc}") from exc

    def files(self) -> list[str]:
        out = self._git("ls-files", "--cached", "--others", "--exclude-standard")
        return sorted(line for line in out.splitlines() if line)

    def read(self, path: str) -> str:
        return (self.path / safe_path(path)).read_text(encoding="utf-8", errors="replace")

    def write(self, path: str, content: str) -> None:
        file = self.path / safe_path(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8", newline="\n")

    def delete(self, path: str) -> None:
        (self.path / safe_path(path)).unlink(missing_ok=True)

    def commit(self, message: str) -> str | None:
        """Commite tout et pousse la branche ; None s'il n'y avait rien à commiter."""
        self._git("add", "-A")
        if not self._git("status", "--porcelain").strip():
            return None
        self._git("commit", "-m", message)
        self._git("push", "origin", self.branch)
        return self._git("rev-parse", "HEAD").strip()

    def has_commit(self, marker: str) -> bool:
        return bool(
            self._git(
                "log", "origin/main..HEAD", "--fixed-strings", f"--grep={marker}", "--format=%H"
            ).strip()
        )

    def diff(self) -> str:
        """Diff complet de la branche par rapport à main, travail non commité compris."""
        self._git("add", "-A")
        return self._git("diff", "--cached", "origin/main")

    def changes(self) -> list[FileChange]:
        """Livrable : un résumé par fichier modifié depuis main."""
        self._git("add", "-A")
        result = []
        for line in self._git("diff", "--cached", "--numstat", "origin/main").splitlines():
            added, deleted, path = line.split("\t", 2)
            patch = self._git("diff", "--cached", "--unified=3", "origin/main", "--", path).splitlines()
            body = [p for p in patch if p[:1] in "+- " and not p.startswith(("+++", "---"))]
            binary = added == "-"
            result.append(
                FileChange(
                    path=path,
                    additions=0 if binary else int(added),
                    deletions=0 if binary else int(deleted),
                    diff=body[:DIFF_LINES],
                    note="Fichier binaire." if binary else None,
                )
            )
        return result

    def merge_into_main(self, message: str) -> str:
        """Fusionne la branche de la tâche dans main (tâche en Done) et renvoie le commit."""
        self._git("fetch", "origin")
        self._git("checkout", "-B", "main", "origin/main")
        try:
            self._git("merge", "--no-ff", "-m", message, self.branch)
        except SandboxError as exc:
            self._git("merge", "--abort", check=False)
            self._git("checkout", self.branch)
            raise SandboxError(f"Fusion de {self.branch} dans main impossible (conflit ?) : {exc}") from exc
        self._git("push", "origin", "main")
        commit = self._git("rev-parse", "HEAD").strip()
        self._git("checkout", self.branch)
        return commit


def _remove_tree(path: Path) -> None:
    # Les objets Git sont en lecture seule sous Windows : rendre inscriptible avant de supprimer.
    def unlock(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onexc=unlock)
