from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"


def test_reachable_management_route_uses_trusted_ingestion_not_legacy_mock():
    app = (FRONTEND / "App.tsx").read_text(encoding="utf-8")
    management = (FRONTEND / "integration" / "ModelManagementView.tsx").read_text(encoding="utf-8")
    upload_area = (
        FRONTEND / "integration" / "management" / "ModelUploadArea.tsx"
    ).read_text(encoding="utf-8")
    upload_start = management.index("async function upload")
    upload_end = management.index("function requestPublication", upload_start)
    upload = management[upload_start:upload_end]
    assert "ModelManagementView" in app
    assert "DataManagementView" not in app
    assert "setTimeout" not in upload
    assert 'accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"' in upload_area
    assert "bffClient.uploadModel" in management


def test_browser_integration_has_no_privileged_supabase_or_retired_upload_path():
    integration = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (FRONTEND / "integration").glob("*.ts*")
    )
    forbidden = (
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_SECRET_KEY",
        "createSignedUploadUrl",
        "/uploads/init",
        "models/{model_id}/source.xlsx",
    )
    assert all(value not in integration for value in forbidden)
