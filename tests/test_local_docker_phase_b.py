from pathlib import Path

import pytest

from scripts.prepare_phase_b_secrets import prepare
from scripts.phase_b_topology_probe import _wait_for_file, _wait_for_status


ROOT = Path(__file__).resolve().parents[1]


def test_phase_b_artifacts_are_pinned_secret_free_and_non_root():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    edge = (ROOT / "deploy" / "Dockerfile.edge").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "deploy" / "python-entrypoint.sh").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "FROM python@sha256:" in dockerfile
    assert "FROM node@sha256:" in frontend and "FROM caddy@sha256:" in frontend
    assert "FROM caddy@sha256:" in edge
    assert "USER app" in dockerfile
    assert "USER 10001:10001" in edge and "USER 10001:10001" in frontend
    assert "setcap -r /usr/bin/caddy" in edge and "setcap -r /usr/bin/caddy" in frontend
    assert "ARG SUPABASE" not in dockerfile and "ARG SUPABASE" not in frontend
    assert "_FILE" in entrypoint and "/run/secrets" not in dockerfile
    assert all(pattern in dockerignore for pattern in ("*.xlsx", "*.xls", "*.xlsm", "*.xlsb"))


def test_phase_b_compose_has_only_edge_ingress_and_hard_resource_boundaries():
    compose = (ROOT / "compose.phase-b.yaml").read_text(encoding="utf-8")
    for service in ("edge", "frontend", "bff-a", "bff-b", "worker", "maintenance"):
        assert f"  {service}:" in compose
    assert compose.count("ports:") == 1
    assert "127.0.0.1:8443:8443" in compose
    assert "mem_limit:" in compose and "cpus:" in compose and "pids_limit:" in compose
    assert "cap_add:" not in compose
    assert "size=536870912" in compose and "BFF_TEMP_ROOT: /var/tmp/pnl" in compose
    assert compose.count("/app/data:rw,noexec,nosuid,nodev,size=268435456") == 3
    assert 'BFF_PARSER_MAX_CONCURRENCY: "1"' in compose
    assert "mem_limit: 1536m" in compose
    assert "0.0.0.0/0" not in compose and "::/0" not in compose
    assert "BFF_TRUSTED_PROXY_CIDRS: 172.30.0.10/32" in compose
    assert "phase-b.localhost:172.30.0.10" in compose
    assert "SUPABASE_SECRET_KEY_FILE: /run/secrets/supabase_secret_key" in compose
    assert "SUPABASE_SECRET_KEY:" not in compose


def test_phase_b_https_edge_load_balances_bffs_and_frontend_is_same_origin():
    caddy = (ROOT / "deploy" / "Caddyfile.phase-b").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "phase-b.localhost:8443" in caddy and "tls internal" in caddy
    assert "reverse_proxy bff-a:8000 bff-b:8000" in caddy
    assert "lb_policy round_robin" in caddy and "health_uri /health/ready" in caddy
    assert "response_header_timeout 180s" in caddy
    assert 'ARG VITE_BFF_BASE_URL=""' in frontend


def test_phase_b_files_contain_no_company_workbook_or_private_key_material():
    paths = [
        ROOT / "Dockerfile",
        ROOT / "compose.phase-b.yaml",
        ROOT / "deploy" / "Dockerfile.edge",
        ROOT / "deploy" / "Caddyfile.phase-b",
        ROOT / "deploy" / "phase-b.env.example",
        ROOT / "docs" / "local_docker_phase_b.md",
    ]
    content = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "Golden_Model" not in content
    assert "BEGIN PRIVATE KEY" not in content
    assert "service_role" not in content.casefold()


def test_phase_b_secret_preparation_requires_supabase_key_and_never_overwrites(tmp_path: Path):
    with pytest.raises(RuntimeError, match="supabase_secret_key"):
        prepare(tmp_path)
    (tmp_path / "supabase_secret_key").write_text("controlled-value\n", encoding="utf-8")
    names = prepare(tmp_path)
    assert set(names) == {
        "viewer_code", "admin_code", "actor_namespace_secret", "csrf_secret",
    }
    assert all((tmp_path / name).stat().st_size >= 32 for name in names)
    with pytest.raises(RuntimeError, match="overwrite"):
        prepare(tmp_path)


def test_phase_b_probe_waits_for_ca_and_readiness(tmp_path: Path, monkeypatch):
    ca = tmp_path / "root.crt"
    ca.write_text("test-only", encoding="utf-8")
    _wait_for_file(str(ca), timeout_seconds=0.1)

    class Client:
        calls = 0

        def get(self, _path):
            self.calls += 1
            return type("Response", (), {"status_code": 503 if self.calls == 1 else 200})()

    monkeypatch.setattr("scripts.phase_b_topology_probe.time.sleep", lambda _seconds: None)
    client = Client()
    response = _wait_for_status(client, "/health/ready", 200, timeout_seconds=0.1)
    assert response.status_code == 200 and client.calls == 2
