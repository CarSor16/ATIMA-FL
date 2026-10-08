"""Optional Windows Credential Manager integration for SSH password login.

Never persist a password in ATIMA config, Git, logs or command arguments.
Use the Windows keyring backend for the signed-in Windows user.
"""
import getpass
import os
import sys

SERVICE = "ATIMA-FL university cluster SSH"


def credential_key(user, host):
    return f"{user}@{host}"


def get_password(user, host):
    if os.name != "nt":
        return None
    try:
        import keyring
    except ImportError:
        return None
    return keyring.get_password(SERVICE, credential_key(user, host))


def main():
    if os.name != "nt":
        raise SystemExit("Credential Manager setup is supported on Windows only")
    if len(sys.argv) != 2 or sys.argv[1] not in {"set", "delete", "check"}:
        raise SystemExit("Use: python -m atima_fl.ui.cluster_credentials set|check|delete")
    from atima_fl.ui.cluster_results import connection_settings
    from pathlib import Path
    workspace = Path(os.environ.get("ATIMA_WORKSPACE", "../ATIMA-workspace")).resolve()
    settings = connection_settings(workspace)
    if not settings:
        raise SystemExit(f"No cluster_connection.json in {workspace}. Set ATIMA_WORKSPACE first.")
    try:
        import keyring
    except ImportError as exc:
        raise SystemExit("Install optional dependencies: pip install -e '.[cluster]'") from exc
    key = credential_key(settings["ssh_user"], settings["ssh_host"])
    operation = sys.argv[1]
    if operation == "set":
        password = getpass.getpass(f"Existing SSH password for {key}: ")
        if not password:
            raise SystemExit("Empty password not stored")
        keyring.set_password(SERVICE, key, password)
        print("Password saved to Windows Credential Manager for this Windows account.")
    elif operation == "delete":
        try:
            keyring.delete_password(SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass
        print("Saved ATIMA SSH password deleted.")
    else:
        print("Credential present" if keyring.get_password(SERVICE, key) else "No credential stored")


if __name__ == "__main__":
    main()
