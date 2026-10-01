import json
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
import zipfile

from t2ag_next import distribution as d
from t2ag_next.journal import Journal
from t2ag_next.model import DomainError


class DistributionJourneys(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "source"
        self.root.mkdir()
        (self.root / "t2ag_next").mkdir()
        for file in (Path(d.__file__).parent).glob("*.py"):
            shutil.copyfile(file, self.root / "t2ag_next" / file.name)
        (self.root / "pyproject.toml").write_text('[project]\nname="fixture"\n', encoding="utf-8")
        for name in d.PUBLIC_DOCS:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# Guide\n\n## Start\nChoose language.\n\n## Resume\nRestore actual state.\n", encoding="utf-8")
        (self.root / "instance").mkdir()
        (self.root / "instance" / "private.txt").write_text("PRIVATE STUDENT", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def package(self):
        path = self.base / "runtime.zip"
        d.build_distribution(self.root, path)
        return path

    def test_package_and_both_editions_preserve_source_exclude_instance(self):
        package = self.package()
        manifest = d.verify_distribution(package)
        self.assertFalse(any("instance" in path for path in manifest["files"]))
        for language in ("zh", "en"):
            result = d.install(package, self.base / language, language)
            student = Journal(result["instance"]).read_state()["objects"]["student/current"]["data"]
            self.assertEqual(student["language"], language)
            self.assertEqual(student["facts_status"], "not_provided")
            command = [sys.executable, "-m", "t2ag_next", "--instance", result["instance"], "context", "--entry", "entry.audit", "--lane", "maintain"]
            run = subprocess.run(command, cwd=result["path"], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["preferences"]["language"], language)
            self.assertEqual((Path(result["path"]) / "AGENTS.md").read_bytes(), (self.root / "docs/runtime-entry.md").read_bytes())
        self.assertTrue(package.exists())
        self.assertTrue((self.root / "instance" / "private.txt").exists())

    def test_upgrade_retains_both_runtimes_and_exact_same_instance(self):
        package = self.package()
        old = d.install(package, self.base / "old", "zh")
        instance = Journal(old["instance"])
        before = instance.log_path.read_bytes()
        result = d.upgrade(package, old["path"], self.base / "new")
        self.assertEqual(Path(result["instance"]), Path(old["instance"]))
        self.assertEqual(instance.log_path.read_bytes(), before)
        self.assertTrue(result["instance_unchanged"])
        self.assertFalse(result["authority_switched"])
        self.assertFalse((self.base / "new/instance").exists())
        with self.assertRaises(DomainError): d.upgrade(package, old["path"], old["path"])

    def test_no_default_language_or_existing_destination_overwrite(self):
        package = self.package()
        dest = self.base / "existing"
        dest.mkdir()
        (dest / "keep").write_bytes(b"original")
        with self.assertRaises(DomainError): d.install(package, dest, "en")
        with self.assertRaises(DomainError): d.install(package, self.base / "bad", None)
        self.assertEqual((dest / "keep").read_bytes(), b"original")

    def test_privacy_rejection_is_before_any_target_write(self):
        path = self.root / "docs/protocol.md"
        path.write_text("Personal institution: Synthetic Secret Academy", encoding="utf-8")
        dest = self.base / "bad.zip"
        with self.assertRaises(DomainError):
            d.build_distribution(self.root, dest, forbidden_terms=["Synthetic Secret Academy"])
        self.assertFalse(dest.exists())

    def test_package_tamper_and_unmanifested_file_rejected(self):
        package = self.package()
        with zipfile.ZipFile(package, "a") as archive:
            archive.writestr("private-user.txt", "not allowed")
        with self.assertRaises(DomainError): d.verify_distribution(package)
        self.assertFalse((self.base / "install").exists())

    def test_traversal_archive_rejected(self):
        archive = self.base / "malicious.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("../outside", "not runtime")
        with self.assertRaises(DomainError): d.verify_distribution(archive)
        self.assertFalse((self.base / "outside").exists())

    def test_lite_is_byte_checked_and_never_contains_personal_instance(self):
        target = self.base / "lite"
        before = d.lite_projection(self.root, target)
        self.assertTrue(before["missing"])
        d.lite_projection(self.root, target, write=True)
        after = d.lite_projection(self.root, target)
        self.assertEqual(after["missing"] + after["different"] + after["orphan"], [])
        self.assertFalse((target / "instance").exists())
        (target / "README.md").write_text("drift", encoding="utf-8")
        self.assertEqual(d.lite_projection(self.root, target)["different"], ["README.md"])

    def test_okf_mechanism_defaults_to_check_only_no_verified_claim(self):
        target = self.base / "okf"
        result = d.okf_export(self.root, target)
        self.assertFalse(result["written"])
        self.assertFalse(target.exists())
        d.okf_export(self.root, target, write=True)
        self.assertIn("okf_version: '0.2'", (target / "index.md").read_text())
        self.assertNotIn("\nverified:", (target / "docs/protocol.md").read_text())
        self.assertFalse((target / "instance").exists())

    def test_okf_rejects_personal_field_and_internal_output(self):
        with self.assertRaises(DomainError):
            d.okf_export(self.root, course_definition={"id": "C", "progress": "private"})
        with self.assertRaises(DomainError):
            d.okf_export(self.root, self.root / "bundle", write=True)
        self.assertFalse((self.root / "bundle").exists())

    def test_offline_guide_has_all_sections_and_escapes_markup(self):
        (self.root / "docs/user-guide.en.md").write_text("# Guide\n\n## Start\n<script>bad()</script>\n## Resume\nRead.\n", encoding="utf-8")
        output = self.base / "guide.html"
        d.build_guide(self.root, output, "en")
        text = output.read_text(encoding="utf-8")
        self.assertIn('href="#s2"', text)
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("<script>", text)


if __name__ == "__main__": unittest.main()
