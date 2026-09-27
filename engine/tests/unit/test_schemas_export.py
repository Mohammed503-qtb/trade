"""اختبارات المُصدّر — توليد حتمي، تحقق بايت-بايت، وكشف العبث ثم الاسترجاع.

حرس «لا رسالة بلا مخطط مُصدَّر» (build_plan §A.5): write يولّد وcheck يقارن؛
أي انحراف يفشل برمز خروج 1.
"""

from __future__ import annotations

import json
from pathlib import Path

from schemas import SCHEMA_VERSION
from schemas.export import ALL_MODELS, GENERATED_DIR, check, main, write


class TestWriteAndCheck:
    """الدورة الكاملة: write يولّد الملفات ثم check يخضرّ."""

    def test_write_creates_all_files(self) -> None:
        assert main(["write"]) == 0
        for name in ALL_MODELS:
            schema_file = GENERATED_DIR / f"{name}.schema.json"
            assert schema_file.is_file(), f"مفقود: {schema_file}"
        assert (GENERATED_DIR / "index.json").is_file()
        assert (GENERATED_DIR / "README.md").is_file()

    def test_check_passes_after_write(self) -> None:
        main(["write"])
        assert main(["check"]) == 0

    def test_write_is_idempotent_byte_for_byte(self) -> None:
        main(["write"])

        def snapshot() -> dict[str, bytes]:
            return {p.name: p.read_bytes() for p in sorted(GENERATED_DIR.iterdir()) if p.is_file()}

        before = snapshot()
        main(["write"])
        assert snapshot() == before, "التوليد ليس حتميًا — كتابتان أنتجتا اختلافًا"

    def test_index_json_lists_every_model(self) -> None:
        main(["write"])
        data = json.loads((GENERATED_DIR / "index.json").read_text(encoding="utf-8"))
        assert set(data) == set(ALL_MODELS)
        for name, entry in data.items():
            assert entry["file"] == f"{name}.schema.json"
            assert entry["schema_version"] == SCHEMA_VERSION

    def test_readme_documents_every_model(self) -> None:
        main(["write"])
        readme = (GENERATED_DIR / "README.md").read_text(encoding="utf-8")
        for name in ALL_MODELS:
            assert name in readme, f"README لا يوثق {name}"
        assert "لا تحرّره يدويًا" in readme


class TestTamperDetection:
    """العبث بأي ملف مولّد يفشل check — ثم الاسترجاع يعيدها خضراء."""

    def test_appended_line_fails_check_then_restored(self) -> None:
        main(["write"])
        target = GENERATED_DIR / "Candle.schema.json"
        original = target.read_bytes()
        try:
            target.write_bytes(original + b"\n// tampered\n")
            assert main(["check"]) == 1
        finally:
            target.write_bytes(original)
        assert main(["check"]) == 0

    def test_missing_schema_file_fails_check(self) -> None:
        main(["write"])
        target = GENERATED_DIR / "EvidenceRecord.schema.json"
        backup = target.read_bytes()
        target.unlink()
        try:
            assert main(["check"]) == 1
        finally:
            target.write_bytes(backup)
        assert main(["check"]) == 0

    def test_tampered_index_fails_check_then_restored(self) -> None:
        main(["write"])
        target = GENERATED_DIR / "index.json"
        original = target.read_bytes()
        try:
            target.write_bytes(original.replace(b'"1.0.0"', b'"9.9.9"'))
            assert main(["check"]) == 1
        finally:
            target.write_bytes(original)
        assert main(["check"]) == 0

    def test_stray_schema_file_fails_check_then_removed(self) -> None:
        main(["write"])
        stray = GENERATED_DIR / "GhostModel.schema.json"
        stray.write_text("{}\n", encoding="utf-8")
        try:
            assert main(["check"]) == 1
        finally:
            stray.unlink()
        assert main(["check"]) == 0


class TestEmptyOrMissingDir:
    """generated/ الفارغ أو المفقود يفشل check — يجب التوليد أولًا."""

    def test_check_fails_on_empty_dir(self, tmp_path: Path) -> None:
        tmp_path.mkdir(exist_ok=True)
        assert check(target_dir=tmp_path) == 1

    def test_check_fails_on_missing_dir(self, tmp_path: Path) -> None:
        assert check(target_dir=tmp_path / "nonexistent") == 1

    def test_write_then_check_on_custom_dir(self, tmp_path: Path) -> None:
        assert write(target_dir=tmp_path) == 0
        assert check(target_dir=tmp_path) == 0
        assert (tmp_path / "index.json").is_file()
