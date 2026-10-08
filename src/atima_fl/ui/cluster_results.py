"""Opt-in read-only SSH import of small cluster result summaries.

The cluster runs no ATIMA service and receives no credentials from ATIMA.
The user's OS OpenSSH client handles previously trusted hosts and keys.
Only manifest.json and final_metrics.json are imported; no model or dataset data.
"""

import json
from pathlib import Path
import re
import subprocess

_HOST = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,252}\Z")
_USER = re.compile(r"[a-zA-Z_][a-zA-Z0-9_.-]{0,62}\Z")
_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")


def connection_settings(workspace):
    path = Path(workspace) / "cluster_connection.json"
    if not path.is_file():
        return None
    if path.stat().st_size > 8192:
        raise ValueError("Cluster connection config exceeds 8 KiB")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid cluster_connection.json") from exc
    if not isinstance(data, dict) or set(data) != {
        "ssh_host", "ssh_user", "remote_results_root"
    }:
        raise ValueError("Cluster connection config requires ssh_host, ssh_user, remote_results_root")
    host, user, root = (data[k] for k in ("ssh_host", "ssh_user", "remote_results_root"))
    if not isinstance(host, str) or not _HOST.fullmatch(host) or host.startswith("-"):
        raise ValueError("Invalid SSH hostname")
    if not isinstance(user, str) or not _USER.fullmatch(user) or user.startswith("-"):
        raise ValueError("Invalid SSH username")
    if not isinstance(root, str) or not root.startswith("/") or chr(0) in root:
        raise ValueError("Remote results directory must be an absolute Linux path")
    if ".." in Path(root).parts or "\n" in root or "\r" in root:
        raise ValueError("Invalid remote results directory")
    return data


def password_ssh(settings, script):
    """Execute the same read-only summary script using a stored Windows password."""
    from atima_fl.ui.cluster_credentials import get_password

    password = get_password(settings["ssh_user"], settings["ssh_host"])
    if password is None:
        return None
    try:
        import paramiko
    except ImportError as exc:
        raise ValueError("Install cluster support: pip install -e '.[cluster]'") from exc
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.load_host_keys(str(Path.home() / ".ssh" / "known_hosts")) if (
        Path.home() / ".ssh" / "known_hosts"
    ).is_file() else None
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect(
            settings["ssh_host"], username=settings["ssh_user"], password=password,
            look_for_keys=False, allow_agent=False, timeout=8, auth_timeout=8,
            banner_timeout=8,
        )
        stdin, stdout, stderr = client.exec_command("python3 -", timeout=20)
        stdin.write(script)
        stdin.flush()
        stdin.channel.shutdown_write()
        output = stdout.read(12 * 1024 * 1024 + 1).decode("utf-8")
        code = stdout.channel.recv_exit_status()
        if code:
            raise ValueError("Cluster SSH read failed; verify password and results path")
        return output
    except (OSError, EOFError, paramiko.SSHException) as exc:
        raise ValueError("Cluster SSH password connection failed; check known_hosts and credentials") from exc
    finally:
        client.close()


def sync_cluster_results(workspace, runner=subprocess.run):
    """Fetch read-only JSON summaries and copy atomically into local workspace.

    SSH must already work with keys and a verified known_hosts entry. No shell
    authentication prompts, password fields, host-key auto-accept or remote writes.
    """
    settings = connection_settings(workspace)
    if not settings:
        raise ValueError("Set up cluster_connection.json in the local ATIMA workspace")
    root = settings["remote_results_root"]
    remote_script = f"""
import json
from pathlib import Path
base = Path({root!r})
if not base.is_dir():
    raise ValueError("Configured cluster results directory does not exist")
out = []
for file in sorted(base.glob("*/manifest.json"))[:101]:
    if len(out) >= 100:
        raise ValueError("More than 100 experiments: narrow remote results directory")
    folder = file.parent
    if folder.is_symlink() or not folder.is_dir():
        continue
    if file.stat().st_size > 1048576:
        raise ValueError("Experiment manifest too large")
    manifest = json.loads(file.read_text(encoding="utf-8"))
    final = folder / "final_metrics.json"
    metrics = None
    if final.is_file() and not final.is_symlink():
        if final.stat().st_size > 1048576:
            raise ValueError("Final metrics too large")
        metrics = json.loads(final.read_text(encoding="utf-8"))
    out.append({{"id":folder.name,"manifest":manifest,"final_metrics":metrics}})
print(json.dumps(out,allow_nan=False))
"""
    command = [
        "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=8", "-o", "NumberOfPasswordPrompts=0",
        "--", settings["ssh_user"] + "@" + settings["ssh_host"], "python3", "-",
    ]
    output = None
    # Preserve injected runner behavior for isolated tests.
    if runner is subprocess.run:
        output = password_ssh(settings, remote_script)
    if output is None:
        try:
            response = runner(command, input=remote_script, text=True,
                              capture_output=True, timeout=35, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("SSH connection failed or timed out; verify VPN, SSH keys and cluster access") from exc
        if response.returncode != 0:
            raise ValueError("Cluster SSH read failed; verify VPN, trusted host key, keys and result path")
        output = response.stdout
    if len(output) > 12 * 1024 * 1024:
        raise ValueError("Cluster response too large")
    try:
        entries = json.loads(output)
    except (ValueError, TypeError) as exc:
        raise ValueError("Cluster returned invalid JSON results") from exc
    if not isinstance(entries, list) or len(entries) > 100:
        raise ValueError("Invalid number of cluster results")
    target = Path(workspace) / "results"
    imported = 0
    # Fully validate all summaries before writing any.
    validated = []
    for row in entries:
        if not isinstance(row, dict) or set(row) != {"id", "manifest", "final_metrics"}:
            raise ValueError("Unexpected result structure from cluster")
        name = row["id"]
        if not isinstance(name, str) or not _RUN.fullmatch(name) or name in {".", ".."}:
            raise ValueError("Invalid cluster experiment name")
        manifest, final = row["manifest"], row["final_metrics"]
        if not isinstance(manifest, dict) or not isinstance(manifest.get("status"), str):
            raise ValueError("Invalid cluster experiment manifest")
        if final is not None and not isinstance(final, dict):
            raise ValueError("Invalid cluster final metrics")
        validated.append((name, manifest, final))
    for name, manifest, final in validated:
        folder = target / name
        if folder.is_symlink():
            raise ValueError("Local results destination is a symlink")
        folder.mkdir(parents=True, exist_ok=True)
        for filename, obj in (("manifest.json", manifest), ("final_metrics.json", final)):
            if obj is None:
                continue
            dest = folder / filename
            if dest.is_symlink():
                raise ValueError("Local result file is a symlink")
            temp = folder / (filename + ".importing")
            if temp.is_symlink():
                raise ValueError("Local staging file is a symlink")
            temp.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            temp.replace(dest)
        imported += 1
    return {"imported": imported, "source": "cluster SSH", "files": ["manifest.json", "final_metrics.json"]}
