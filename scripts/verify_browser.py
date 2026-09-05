"""Run browser/TLS and volume-persistence checks in a disposable Compose project.

Requires Docker, openssl, frontend npm dependencies and built API/frontend images.
Uses the production Compose configuration, with current source/build mounts. No
existing container, database or volume is reused. Secrets live in a temporary
0700 directory, and the project's containers/volumes are removed on exit.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    kwargs.setdefault("cwd", ROOT)
    return subprocess.run(args, check=True, **kwargs)


def main():
    run(["npm", "run", "build"], cwd=ROOT / "frontend")

    with tempfile.TemporaryDirectory(prefix="content-ops-e2e-") as directory:
        temp = Path(directory)
        project = temp.name
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        origin = f"https://content-ops.test:{port}"
        runtime = dict(os.environ)
        runtime.update({
            "APP_ENV": "production", "SCHEMA_MANAGEMENT": "validate",
            "AUTH_ENABLED": "true", "AUTH_USERNAME": "admin",
            "AUTH_PASSWORD": secrets.token_urlsafe(32),
            "AUTH_SECRET_KEY": secrets.token_urlsafe(48),
            "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
            "REDIS_PASSWORD": secrets.token_urlsafe(32),
            "AUTH_TOKEN_EXPIRE_MINUTES": "1",
            "ENFORCE_HTTPS": "true", "CORS_ORIGINS": origin,
            "TRUSTED_PROXY_CIDRS": "172.16.0.0/12",
            "DEBUG": "false", "API_RELOAD": "false",
            "XHS_MCP_ENABLED": "false", "MEMORY_CURATOR_ENABLED": "false",
            "SSE_KEEPALIVE_SECONDS": "1", "SSE_POLL_INTERVAL_SECONDS": "0.1",
            "SSE_STREAM_TIMEOUT_SECONDS": "8",
        })
        # Do not load a developer's .env or pass real provider credentials.
        for key in ("ANTHROPIC_API_KEY", "SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY",
                    "MOONSHOT_API_KEY", "NEWAPI_API_KEY", "SERPER_API_KEY",
                    "TAVILY_API_KEY", "BRAVE_SEARCH_API_KEY"):
            runtime[key] = ""
        env_file = temp / "empty.env"
        env_file.touch(mode=0o600)
        result = run([
            "docker", "compose", "--env-file", str(env_file),
            "-f", str(ROOT / "docker-compose.yml"), "config", "--format", "json",
        ], env=runtime, capture_output=True, text=True)
        compose = json.loads(result.stdout)
        compose["name"] = project
        compose.pop("x-app-env", None)
        # config resolves volume/network names using the original project name.
        # Remove those names so this project gets private resources of its own.
        for group in ("networks", "volumes"):
            for definition in compose.get(group, {}).values():
                definition.pop("name", None)

        api_image = os.environ.get("E2E_API_IMAGE", "content-ops-agent-api:latest")
        frontend_image = os.environ.get("E2E_FRONTEND_IMAGE", "content-ops-agent-frontend:latest")
        for name, service in compose["services"].items():
            service.pop("build", None)
            service.pop("ports", None)
            service["restart"] = "no"
            if name in {"api", "migrate", "worker"}:
                service["image"] = api_image
                service["environment"]["WEB_CONCURRENCY"] = "1"
                for path in ("src", "migrations", "alembic.ini", "gunicorn.conf.py", "worker.py"):
                    service.setdefault("volumes", []).append({
                        "type": "bind", "source": str(ROOT / path),
                        "target": f"/app/{path}", "read_only": True,
                    })
                service.setdefault("volumes", []).append({
                    "type": "bind", "source": str(ROOT / "tests/e2e/seed.py"),
                    "target": "/app/e2e_seed.py", "read_only": True,
                })
            if name == "frontend":
                service["image"] = frontend_image
                service["volumes"] = [
                    {"type": "bind", "source": str(ROOT / "frontend/dist"),
                     "target": "/usr/share/nginx/html", "read_only": True},
                    {"type": "bind", "source": str(ROOT / "frontend/nginx.conf"),
                     "target": "/etc/nginx/conf.d/default.conf", "read_only": True},
                ]

        run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(temp / "key.pem"), "-out", str(temp / "cert.pem"),
             "-days", "1", "-subj", "/CN=content-ops.test",
             "-addext", "subjectAltName=DNS:content-ops.test"], capture_output=True)
        compose["services"]["tls"] = {
            "image": frontend_image,
            "ports": [{"target": 443, "published": str(port), "host_ip": "127.0.0.1"}],
            "volumes": [
                {"type": "bind", "source": str(temp), "target": "/certs", "read_only": True},
                {"type": "bind", "source": str(ROOT / "tests/e2e/tls.conf"),
                 "target": "/etc/nginx/conf.d/default.conf", "read_only": True},
            ],
            "depends_on": {"frontend": {"condition": "service_started"}},
        }
        config_path = temp / "compose.json"
        config_path.write_text(json.dumps(compose), encoding="utf-8")
        config_path.chmod(0o600)
        command = ["docker", "compose", "-p", project, "-f", str(config_path)]
        try:
            run(command + ["up", "-d", "--wait", "--wait-timeout", "180"])
            seed = run(command + ["exec", "-T", "api", "python", "e2e_seed.py", "seed"],
                       capture_output=True, text=True)
            fixture_path = temp / "fixtures.json"
            fixture_path.write_text(seed.stdout, encoding="utf-8")
            browser_env = dict(os.environ, E2E_BASE_URL=origin,
                               E2E_PASSWORD=runtime["AUTH_PASSWORD"],
                               E2E_FIXTURES=str(fixture_path), E2E_COMPOSE=str(config_path),
                               E2E_PROJECT=project)
            # The system Chrome is optional; otherwise Playwright uses its own
            # installed Chromium (npx playwright install chromium).
            if not browser_env.get("E2E_CHROMIUM_EXECUTABLE") and Path("/opt/google/chrome/chrome").exists():
                browser_env["E2E_CHROMIUM_EXECUTABLE"] = "/opt/google/chrome/chrome"
            tests = subprocess.run(["npm", "run", "test:e2e"], cwd=ROOT / "frontend", env=browser_env)
            print(f"Browser test process exited with status {tests.returncode}", flush=True)

            # Recreate every container while retaining only this project's volumes.
            run(command + ["down", "--timeout", "10"])
            run(command + ["up", "-d", "--wait", "--wait-timeout", "180"])
            run(command + ["exec", "-T", "api", "python", "e2e_seed.py", "verify"])
            if tests.returncode:
                raise SystemExit(tests.returncode)
        except subprocess.CalledProcessError:
            logs = subprocess.run(command + ["logs", "--no-color", "--tail", "60"],
                                  capture_output=True, text=True)
            diagnostic = logs.stdout + logs.stderr
            for key in ("AUTH_PASSWORD", "AUTH_SECRET_KEY", "POSTGRES_PASSWORD", "REDIS_PASSWORD"):
                diagnostic = diagnostic.replace(runtime[key], "[REDACTED]")
            print(diagnostic, flush=True)
            raise
        finally:
            run(command + ["down", "--volumes", "--remove-orphans", "--timeout", "10"])
        print("Browser/TLS and persistence verification complete; isolated resources removed", flush=True)


if __name__ == "__main__":
    main()
