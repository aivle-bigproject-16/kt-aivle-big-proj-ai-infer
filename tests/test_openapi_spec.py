"""커밋된 OpenAPI 스펙이 코드와 일치하는지 지킨다.

BE 는 `docs/openapi.json` 을 계약 사본으로 읽는다. 코드만 고치고 스펙을 안
갱신하면 조용히 어긋나므로 여기서 막는다.
"""
import json
from pathlib import Path

import pytest

from scripts.dump_openapi import OUTPUT, render


def test_committed_spec_matches_the_application():
    assert OUTPUT.exists(), "run: python -m scripts.dump_openapi"
    assert OUTPUT.read_text(encoding="utf-8") == render(), (
        "docs/openapi.json is stale; run: python -m scripts.dump_openapi"
    )


@pytest.fixture(scope="module")
def spec():
    return json.loads(Path("docs/openapi.json").read_text(encoding="utf-8"))


def test_spec_exposes_exactly_the_contract_endpoints(spec):
    assert set(spec["paths"]) == {
        "/infer/ct",
        "/infer/rgb",
        "/ai/cells/analyze",
        "/health",
    }


@pytest.mark.parametrize("path", ["/infer/ct", "/infer/rgb"])
def test_single_image_endpoints_document_every_failure_code(spec, path):
    documented = set(spec["paths"][path]["post"]["responses"])

    assert {"200", "422", "500", "502", "503"} <= documented


def test_cell_analysis_documents_acceptance_and_the_backend_callback(spec):
    operation = spec["paths"]["/ai/cells/analyze"]["post"]

    assert set(operation["responses"]) >= {"202", "400", "401", "503"}
    assert "cell_analysis_callback" in operation["callbacks"]


def test_defect_type_stays_the_four_contract_codes(spec):
    defect = spec["components"]["schemas"]["Defect"]["properties"]["defectType"]

    assert defect["enum"] == [
        "SWELLING",
        "SPOT",
        "MICRO_DEFECT",
        "CRACK",
    ]
