from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import gate_matrix as gates


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GateMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        symbols = []
        tests = []
        stdout_lines = []
        for gate_id in gates.REQUIRED_GATE_IDS:
            suffix = gate_id.replace("-", "_")
            symbols.append(f"def symbol_{suffix}():\n    return True\n")
            tests.extend(
                [
                    f"def test_positive_{suffix}():\n    pass\n",
                    f"def test_negative_{suffix}():\n    pass\n",
                ]
            )
            stdout_lines.extend(
                [f"test_positive_{suffix} ... ok", f"test_negative_{suffix} ... ok"]
            )
        self.impl = self.workspace / "impl.py"
        self.impl.write_text("\n".join(symbols), encoding="utf-8")
        self.tests = self.workspace / "test_contract.py"
        self.tests.write_text("\n".join(tests), encoding="utf-8")
        self.consumer = self.workspace / "consumer.py"
        self.consumer.write_text("print('consumer')\n", encoding="utf-8")
        self.stdout = self.workspace / "suite.stdout"
        self.stdout.write_text("\n".join(stdout_lines) + "\n", encoding="utf-8")
        self.report = self.workspace / "suite.json"
        self.report.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "command_schema": "unittest",
                    "run_id": "operational-consumer",
                    "argv": ["python", "consumer.py", "test_contract.py"],
                    "assertions": ["consumer_completed"],
                    "stdout_path": str(self.stdout),
                    "recover_result": "rolled_back",
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def row(self, gate_id: str) -> dict:
        suffix = gate_id.replace("-", "_")
        report_binding = {
            "report_path": self.report.name,
            "report_sha256": digest(self.report),
        }
        return {
            "gate_id": gate_id,
            "requirement": f"bound requirement {gate_id}",
            "implementation_symbols": [
                {"path": self.impl.name, "symbol": f"symbol_{suffix}"}
            ],
            "positive_tests": [
                {
                    "path": self.tests.name,
                    "test": f"test_positive_{suffix}",
                    **report_binding,
                }
            ],
            "negative_tests": [
                {
                    "path": self.tests.name,
                    "test": f"test_negative_{suffix}",
                    **report_binding,
                }
            ],
            "real_consumers": [
                {
                    "path": self.consumer.name,
                    "argv_contains": "consumer.py",
                    "run_id": "operational-consumer",
                    "assertion": "consumer_completed",
                    **report_binding,
                }
            ],
            "recovery_evidence": [
                {"assertion_contains": "rolled_back", **report_binding}
            ],
            "evidence_files": [
                {"path": self.report.name, "sha256": digest(self.report)}
            ],
            "status": "closed",
        }

    def matrix(self) -> dict:
        return {
            "schema": gates.SCHEMA,
            "campaign_id": "campaign",
            "rows": [self.row(gate_id) for gate_id in gates.REQUIRED_GATE_IDS],
        }

    def test_gate_matrix_requires_every_v2_section6_row(self) -> None:
        result = gates.validate_gate_matrix(self.workspace, self.matrix())
        self.assertEqual(result["status"], "closed")
        self.assertIn("V2-6-SCHEMA_SNAPSHOT", gates.REQUIRED_GATE_IDS)
        self.assertIn("V2-6-KNOWLEDGE_COMPLETION", gates.REQUIRED_GATE_IDS)

    def test_gate_row_rejects_unresolved_symbol_or_test(self) -> None:
        matrix = self.matrix()
        matrix["rows"][0]["implementation_symbols"][0]["symbol"] = "module.symbol"
        with self.assertRaisesRegex(gates.GateError, "placeholder"):
            gates.validate_gate_matrix(self.workspace, matrix)
        matrix = self.matrix()
        matrix["rows"][0]["positive_tests"][0]["test"] = "test_missing"
        with self.assertRaisesRegex(gates.GateError, "unresolved test"):
            gates.validate_gate_matrix(self.workspace, matrix)

    def test_gate_rows_cannot_share_unrelated_placeholder_evidence(self) -> None:
        matrix = self.matrix()
        first = matrix["rows"][0]
        second = matrix["rows"][1]
        for field in (
            "implementation_symbols",
            "positive_tests",
            "negative_tests",
            "real_consumers",
            "recovery_evidence",
        ):
            second[field] = json.loads(json.dumps(first[field]))
        with self.assertRaisesRegex(gates.GateError, "identical proof envelope"):
            gates.validate_gate_matrix(self.workspace, matrix)

    def test_help_only_consumer_and_unbound_tool_evidence_are_rejected(self) -> None:
        matrix = self.matrix()
        report = json.loads(self.report.read_text(encoding="utf-8"))
        report["argv"] = ["python", "consumer.py", "--help"]
        self.report.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        binding = digest(self.report)
        for row in matrix["rows"]:
            row["evidence_files"][0]["sha256"] = binding
            for field in ("positive_tests", "negative_tests", "real_consumers", "recovery_evidence"):
                row[field][0]["report_sha256"] = binding
        with self.assertRaisesRegex(gates.GateError, "help-only"):
            gates.validate_gate_matrix(self.workspace, matrix)

        report["argv"] = ["python", "consumer.py", "run"]
        report["schema"] = "t2ag.evidence_run.v1"
        report["tool_source_manifest_sha256"] = None
        self.report.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        binding = digest(self.report)
        for row in matrix["rows"]:
            row["evidence_files"][0]["sha256"] = binding
            for field in ("positive_tests", "negative_tests", "real_consumers", "recovery_evidence"):
                row[field][0]["report_sha256"] = binding
        with self.assertRaisesRegex(gates.GateError, "tool source manifest"):
            gates.validate_gate_matrix(self.workspace, matrix)

    def test_open_missing_and_tampered_evidence_fail(self) -> None:
        matrix = self.matrix()
        matrix["rows"][0]["status"] = "partial"
        with self.assertRaisesRegex(gates.GateError, "not closed"):
            gates.validate_gate_matrix(self.workspace, matrix)
        matrix = self.matrix()
        matrix["rows"].pop()
        with self.assertRaisesRegex(gates.GateError, "gate id set mismatch"):
            gates.validate_gate_matrix(self.workspace, matrix)
        matrix = self.matrix()
        matrix["rows"][0]["evidence_files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(gates.GateError, "sha mismatch"):
            gates.validate_gate_matrix(self.workspace, matrix)

    def test_freezer_requires_roles_and_binds_matrix_bytes(self) -> None:
        matrix_path = self.workspace / "matrix.json"
        matrix_path.write_text(
            json.dumps(self.matrix(), ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        members = []
        for role in sorted(gates.REQUIRED_PACKAGE_ROLES):
            if role == "closure_matrix":
                path = matrix_path
            else:
                path = self.workspace / f"{role}.json"
                path.write_text(f'{{"role":"{role}"}}\n', encoding="utf-8")
            members.append({"role": role, "path": path.name, "sha256": digest(path)})
        members_path = self.workspace / "members.json"
        members_path.write_text(
            json.dumps({"package_id": "PKG", "members": members}) + "\n",
            encoding="utf-8",
        )
        output = self.workspace / "package.json"
        package, package_sha = gates.freeze_package(
            self.workspace, matrix_path, members_path, output
        )
        self.assertEqual(package_sha, digest(output))
        self.assertEqual(package["member_count"], len(gates.REQUIRED_PACKAGE_ROLES))
        with self.assertRaisesRegex(gates.GateError, "already exists"):
            gates.freeze_package(self.workspace, matrix_path, members_path, output)


if __name__ == "__main__":
    unittest.main()
