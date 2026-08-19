from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESOURCE = "forecast/bff/resources/PNL_REPORTING_TEMPLATE_V1.xlsx"
ALLOW_RULE = f"!{RESOURCE}"


def _ignore_lines(name: str) -> list[str]:
    return [
        line.strip()
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_build_contexts_keep_generic_xlsx_exclusion_and_allow_only_approved_resource():
    for name in (".dockerignore", ".gcloudignore"):
        lines = _ignore_lines(name)
        assert "*.xlsx" in lines
        assert ALLOW_RULE in lines
        assert lines.index(ALLOW_RULE) > lines.index("*.xlsx")
        assert [line for line in lines if line.startswith("!") and line.endswith(".xlsx")] == [
            ALLOW_RULE
        ]


def test_template_is_backend_only_and_root_runtime_copy_owns_it():
    resource = ROOT / RESOURCE
    assert resource.is_file()
    assert list((ROOT / "frontend").rglob("*.xlsx")) == []
    assert not (ROOT / "frontend" / "public" / resource.name).exists()

    root_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY --chown=app:app forecast ./forecast" in root_dockerfile

    frontend_images = (
        ROOT / "frontend" / "Dockerfile",
        ROOT / "deploy" / "gcp" / "Dockerfile.web",
        ROOT / "deploy" / "Dockerfile.edge",
    )
    for dockerfile in frontend_images:
        text = dockerfile.read_text(encoding="utf-8")
        assert RESOURCE not in text
        assert resource.name not in text


def test_production_frontend_uses_authenticated_endpoint_not_static_artifact():
    client = (ROOT / "frontend" / "src" / "integration" / "client.ts").read_text(
        encoding="utf-8"
    )
    assert "securedFetch('/api/admin/pnl-reporting/template'" in client
    assert f"/{resource_name()}" not in client
    assert "createObjectURL" in client
    assert "revokeObjectURL" in client


def resource_name() -> str:
    return Path(RESOURCE).name
