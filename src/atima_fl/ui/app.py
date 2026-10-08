"""Loopback-only GUI: metadata, validation, portable plans and local results."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from urllib.parse import urlparse, unquote
from atima_fl.core.configuration import ExperimentConfig
from atima_fl.core.registry import Registry
from atima_fl.engine.plans import save_plan, save_defense_study
from atima_fl.ui.cluster_results import (
    connection_settings, read_local_history, sync_cluster_results,
)

STATIC = Path(__file__).parent / "static"


def child(root, name):
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Path outside workspace")
    return target


def deployment_defaults(workspace):
    """Load optional execution paths locally, never from tracked source.

    These paths are configuration references, not proof that the remote data
    exist. Validation/export on Windows must not read or mount cluster data.
    """
    path = Path(workspace) / "deployment_defaults.json"
    if not path.is_file():
        return {}
    if path.stat().st_size > 16 * 1024:
        raise ValueError("deployment_defaults.json exceeds 16 KiB")
    try:
        values = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid deployment_defaults.json: {error}") from error
    if not isinstance(values, dict) or set(values) - {"dataset_root", "output_root"}:
        raise ValueError(
            "deployment_defaults.json must contain only dataset_root and output_root"
        )
    if any(not isinstance(value, str) or not value.strip() or chr(0) in value for value in values.values()):
        raise ValueError("Deployment paths must be non-empty strings without null bytes")
    return values


def results(workspace):
    values = []
    root = workspace / "results"
    for path in sorted(root.glob("*/manifest.json")):
        path = child(root, str(path.relative_to(root)))
        manifest = json.loads(path.read_text(encoding="utf-8"))
        final_path = path.parent / "final_metrics.json"
        final = json.loads(final_path.read_text(encoding="utf-8")) if final_path.exists() else {}
        config = manifest.get("config", {})
        values.append({
            "id": path.parent.name,
            "status": manifest.get("status", "unknown"),
            "round": manifest.get("last_valid_round"),
            "config": config,
            "metrics": final,
            "pair_id": manifest.get("pair_id"),
            "classes": manifest.get("dataset_audit", {}).get("classes", []),
            "history": read_local_history(path.parent / "validation_history.json"),
            "baseline_id": None,
            "_identity": json.dumps(
                [manifest["source_identity"], manifest["runtime"]], sort_keys=True
            ) if (
                isinstance(manifest.get("source_identity"), dict)
                and manifest["source_identity"]
                and isinstance(manifest.get("runtime"), dict)
                and manifest["runtime"]
            ) else None,
        })
    # Only make comparisons between explicitly paired, complete runs from
    # identical software/runtime identities and with equal valid round caps.
    baselines = {}
    for value in values:
        if value["status"] == "complete" and value["config"].get("attack") == "none":
            if value["pair_id"] and value["_identity"]:
                key = (value["pair_id"], value["_identity"], value["round"])
                baselines.setdefault(key, []).append(value["id"])
    for value in values:
        if (
            value["status"] == "complete" and value["config"].get("attack") != "none"
            and value["pair_id"] and value["_identity"]
        ):
            key = (value["pair_id"], value["_identity"], value["round"])
            candidates = baselines.get(key, [])
            if len(candidates) == 1:
                value["baseline_id"] = candidates[0]
        del value["_identity"]
    return values


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, value, content_type="application/json"):
        body = (
            json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            if content_type == "application/json"
            else value
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def allowed_host(self):
        return self.headers.get("Host") in {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        }

    def do_GET(self):
        if not self.allowed_host():
            return self.respond(403, {"error": "Loopback host required"})
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/api/catalog":
                return self.respond(
                    200,
                    {
                        "catalog": Registry(self.server.plugins).catalog(),
                        "token": self.server.token,
                    },
                )
            if path == "/api/dataset-tasks":
                registry = Registry(self.server.plugins)
                tasks = {}
                for component in registry.catalog()["dataset"]:
                    plugin = registry.get("dataset", component["id"])
                    hook = plugin.hooks.get("task_catalog")
                    if hook:
                        tasks[component["id"]] = hook()
                return self.respond(200, tasks)
            if path == "/api/defaults":
                values = {
                    "output_root": str(self.server.workspace / "results"),
                    "plugin_directory": str(self.server.plugins or ""),
                }
                values.update(deployment_defaults(self.server.workspace))
                config = ExperimentConfig(**values)
                return self.respond(200, config.resolved())
            if path == "/api/cluster-status":
                settings = connection_settings(self.server.workspace)
                return self.respond(200, {
                    "configured": settings is not None,
                    "host": settings["ssh_host"] if settings else None,
                    "workspace": str(self.server.workspace),
                    "config_path": str(self.server.workspace / "cluster_connection.json"),
                })
            if path == "/api/results":
                return self.respond(200, results(self.server.workspace))
            if path.startswith("/api/plans/") and path.endswith("/plan.zip"):
                name = path.removeprefix("/api/plans/").removesuffix("/plan.zip")
                file = child(self.server.workspace / "plans", name + "/plan.zip")
                return self.respond(200, file.read_bytes(), "application/zip")
            assets = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
            }
            if path in assets:
                name, kind = assets[path]
                return self.respond(200, (STATIC / name).read_bytes(), kind)
            return self.respond(404, {"error": "Not found"})
        except (ValueError, OSError) as error:
            return self.respond(422, {"error": str(error)})

    def do_POST(self):
        origin = self.headers.get("Origin")
        origins = {
            f"http://127.0.0.1:{self.server.server_port}",
            f"http://localhost:{self.server.server_port}",
        }
        if (
            not self.allowed_host()
            or (origin and origin not in origins)
            or self.headers.get("X-ATIMA-Token") != self.server.token
        ):
            return self.respond(403, {"error": "Local session token required"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if (
                not 0 < length <= 1024 * 1024
                or self.headers.get("Content-Type", "").split(";")[0] != "application/json"
            ):
                raise ValueError("Expected a JSON request within 1 MiB")
            body = json.loads(self.rfile.read(length))
            if self.path == "/api/sync-cluster-results":
                if body != {}:
                    raise ValueError("Cluster sync takes no client-side parameters")
                return self.respond(200, sync_cluster_results(self.server.workspace))
            config = ExperimentConfig.from_dict(body)
            if str(config.plugin_directory or "") != str(self.server.plugins or ""):
                raise ValueError("Use the plugin directory chosen when starting the GUI")
            if self.path == "/api/inspect-dataset":
                registry = config.registry()
                plugin = registry.get("dataset", config.dataset)
                dataset = plugin.hooks["open"](
                    config, registry.parameters("dataset", config.dataset, config.dataset_params)
                )
                inspect = getattr(dataset, "inspect", None)
                if inspect is None:
                    raise ValueError(f"Dataset {config.dataset} does not provide label inspection")
                return self.respond(200, inspect())
            if self.path == "/api/validate":
                warnings = []
                if config.minimum_rounds > config.rounds:
                    warnings.append(
                        "Minimum early stopping rounds exceed the cap; the run will finish at the cap."
                    )
                if config.attack != "none" and not config.paired_clean:
                    warnings.append("A completed, paired clean baseline is required before launch.")
                plugin = config.registry().get("attack", config.attack)
                if "warnings" in plugin.hooks:
                    warnings.extend(plugin.hooks["warnings"](config, config.parameters("attack")))
                return self.respond(
                    200,
                    {
                        "config": config.resolved(),
                        "warnings": warnings,
                        "checks": {
                            "configuration": "valid",
                            "dataset": "not_checked",
                            "scheduler": "not_checked",
                            "cuda": "not_checked",
                        },
                    },
                )
            if self.path in {"/api/plans", "/api/defense-study"}:
                exporter = save_defense_study if self.path == "/api/defense-study" else save_plan
                directory = exporter(config, self.server.workspace)
                return self.respond(
                    201,
                    {
                        "name": directory.name,
                        "directory": str(directory),
                        "download": f"/api/plans/{directory.name}/plan.zip",
                    },
                )
            return self.respond(404, {"error": "Not found"})
        except FileExistsError:
            return self.respond(
                409, {"error": "This experiment name is already saved; choose a different name."}
            )
        except (ValueError, KeyError, TypeError, OSError) as error:
            return self.respond(422, {"error": str(error)})


def create_server(workspace, port=8765, plugins=None):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.workspace = Path(workspace).resolve()
    server.plugins = str(Path(plugins).resolve()) if plugins else None
    server.token = secrets.token_urlsafe(32)
    return server


def serve(workspace, port=8765, plugins=None):
    server = create_server(workspace, port, plugins)
    print(f"ATIMA-FL · http://127.0.0.1:{server.server_port}", flush=True)
    print(f"Workspace: {server.workspace}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
