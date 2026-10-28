import os
import re
import subprocess
import time

PROJECTS_DIR = os.path.expanduser("~/Área de trabalho/projetos")
WORKTREES_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                             "all-in-one-workstation", "worktrees")
CACHE_SECONDS = 60
_cache = {"at": 0, "repos": {}}


class RepoError(Exception):
    pass


def git(path, *args, timeout=20):
    try:
        result = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RepoError(f"git {' '.join(args)} failed: {error}") from error
    if result.returncode != 0:
        raise RepoError((result.stderr or result.stdout).strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def identity_from_url(url):
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", url.strip())
    return match.group(1) if match else None


def repo_identity(path):
    try:
        return identity_from_url(git(path, "remote", "get-url", "origin", timeout=5)) or f"local/{os.path.basename(path)}"
    except RepoError:
        return f"local/{os.path.basename(path)}"


def candidate_dirs():
    found = []
    try:
        names = sorted(os.listdir(PROJECTS_DIR), key=str.lower)
    except OSError:
        return found
    for name in names:
        path = os.path.join(PROJECTS_DIR, name)
        if os.path.exists(os.path.join(path, ".git")):
            found.append(path)
        elif os.path.isdir(path) and not name.startswith("."):
            try:
                found += [os.path.join(path, n) for n in sorted(os.listdir(path), key=str.lower)
                          if os.path.exists(os.path.join(path, n, ".git"))]
            except OSError:
                pass
    return found


def discover(force=False):
    """identity ("org/name") -> local clone paths, the clone named like the repo first."""
    if not force and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["repos"]
    repos = {}
    for path in candidate_dirs():
        repos.setdefault(repo_identity(path), []).append(path)
    for identity, paths in repos.items():
        name = identity.split("/")[-1]
        paths.sort(key=lambda p: (os.path.basename(p) != name, len(p)))
    _cache.update(at=time.time(), repos=repos)
    return repos


def identities():
    return sorted(discover(), key=lambda i: display(i).lower())


def display(identity):
    return identity.split("/")[-1] if identity else ""


def local_path(identity):
    if not identity:
        return None
    if identity.startswith("/"):
        return identity if os.path.isdir(identity) else None
    paths = discover().get(identity)
    return paths[0] if paths else None


def to_identity(value):
    if value and value.startswith("/") and os.path.isdir(value):
        return repo_identity(value)
    return value


def repos_with_branch(key):
    """Repos that have a local or remote branch containing the Jira key; costs no tokens."""
    needle = key.lower()
    found = []
    for identity, paths in discover().items():
        try:
            refs = git(paths[0], "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes", timeout=10)
        except RepoError:
            continue
        if any(needle in ref.lower() for ref in refs.splitlines()):
            found.append(identity)
    return sorted(found, key=lambda i: display(i).lower())


def slugify(text, limit=40):
    text = re.sub(r"[^a-z0-9]+", "-", text.lower().encode("ascii", "ignore").decode()).strip("-")
    return text[:limit].rstrip("-") or "task"


def default_base(path):
    try:
        return git(path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    except RepoError:
        pass
    for ref in ("origin/main", "origin/master", "main", "master"):
        try:
            git(path, "rev-parse", "--verify", "--quiet", ref)
            return ref
        except RepoError:
            continue
    return "HEAD"


def create_worktree(identity, workspace, branch):
    clone = local_path(identity)
    if not clone:
        raise RepoError(f"No local clone found for {identity}")
    target = os.path.join(WORKTREES_DIR, workspace, display(identity))
    base = default_base(clone)
    if os.path.isdir(target):
        return {"identity": identity, "path": target, "branch": branch, "base": base}
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        git(clone, "fetch", "--quiet", "origin", timeout=90)
        base = default_base(clone)
    except RepoError:
        pass
    try:
        git(clone, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    except RepoError:
        git(clone, "worktree", "add", "-b", branch, target, base, timeout=120)
        return {"identity": identity, "path": target, "branch": branch, "base": base}
    try:
        git(clone, "worktree", "add", target, branch, timeout=120)
    except RepoError:
        git(clone, "worktree", "add", "-b", f"{branch}-agent", target, branch, timeout=120)
        branch = f"{branch}-agent"
    return {"identity": identity, "path": target, "branch": branch, "base": base}


def remove_worktree(entry):
    clone = local_path(entry["identity"])
    if clone and os.path.isdir(entry["path"]):
        git(clone, "worktree", "remove", entry["path"], timeout=60)


def changes(entry, limit=60000):
    path, base = entry["path"], entry.get("base") or "HEAD"
    try:
        log = git(path, "log", "--oneline", f"{base}..HEAD", timeout=10)
        status = git(path, "status", "--short", timeout=10)
        diff = git(path, "diff", base, timeout=20)
    except RepoError as error:
        return f"(could not read changes: {error})"
    parts = [f"## {display(entry['identity'])} · {entry['branch']}",
             "Commits:\n" + (log or "(none)"), "Uncommitted:\n" + (status or "(clean)"), diff]
    text = "\n\n".join(parts)
    return text if len(text) <= limit else text[:limit] + "\n[… diff truncated …]"
