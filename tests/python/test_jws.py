import hashlib
import json
import struct
from pathlib import Path

import pytest

import ezjww

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "jws_samples"


def sample(name="basic", version=700):
    return str(SAMPLES / "native" / f"{name}_v{version}.jws")


def test_native_fixture_integrity_and_public_dispatch():
    manifest = json.loads((SAMPLES / "manifest.json").read_text())
    for case in manifest["cases"]:
        path = SAMPLES / case["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == case["sha256"]
        source = SAMPLES / case["source"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == case["source_sha256"]
        doc = ezjww.read_jws_document(str(path))
        assert doc["header"]["version"] == case["version"]
        assert doc["header"] == ezjww.read_jws_header(str(path))
        assert doc["diagnostics"] == []
        assert ezjww.read_cad_document(str(path)) == {"format": "jws", "document": doc}
        assert ezjww.detect_file_format(str(path)) == "jws"
        assert ezjww.is_jws_file(str(path)) and not ezjww.is_jww_file(str(path))
        drawing = ezjww.readfile(path)
        assert drawing.source_format == "jws"
        assert drawing.source_document == doc
        assert drawing.jww_document is None
        assert drawing.header == doc["header"]
        assert drawing.images == []
        assert drawing.modelspace()
        assert drawing.bbox() is not None


def test_signature_detection_and_dedicated_jww_contract(tmp_path):
    path = tmp_path / "symbol.dat"
    path.write_bytes(Path(sample()).read_bytes())
    assert ezjww.readfile(path).source_format == "jws"
    for read in (ezjww.read_document, ezjww.read_header):
        with pytest.raises(ValueError):
            read(str(path))
    path.write_bytes(b"JwsData.")
    assert ezjww.is_jws_file(str(path))
    with pytest.raises(ValueError, match="truncated"):
        ezjww.read_jws_document(str(path))
    with pytest.raises(OSError):
        ezjww.read_jws_document(str(tmp_path / "missing.jws"))


def test_native_read_and_place_preserves_geometry_after_translation():
    manifest = json.loads((SAMPLES / "manifest.json").read_text())
    case = manifest["placement_checks"][0]
    path = SAMPLES / case["output"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == case["output_sha256"]
    source = ezjww.read_jws_document(str(SAMPLES / case["source"]))["entities"]
    placed = [e for e in ezjww.read_document(str(path))["entities"] if e["type"] != "TEXT"][3:]
    assert len(placed) == len(source) == 3
    dx, dy = case["placement_point_from_saved_geometry"]
    for before, after in zip(source, placed):
        assert before["type"] == after["type"]
        for x, y in (("start_x", "start_y"), ("end_x", "end_y"), ("center_x", "center_y")):
            if x in before:
                assert after[x] == pytest.approx(before[x] - 10 + dx)
                assert after[y] == pytest.approx(before[y] - 20 + dy)
        if "radius" in before:
            assert before["radius"] == after["radius"] == 5


def test_native_unicode_geometry_blocks_and_external_image_reference():
    unicode = ezjww.read_jws_document(sample("unicode"))
    assert unicode["entities"][2]["content"] == "日本語𠮷ｶﾅ ABC"
    assert unicode["entities"][3]["angle"] == 90
    geometry = ezjww.readfile(sample("geometry"))
    assert geometry.source_document["entity_counts"] == {
        "LINE": 2, "CIRCLE": 2, "ARC": 1, "POINT": 1,
        "SOLID": 1, "CIRCLE_SOLID": 1, "DIMENSION": 1,
    }
    assert geometry.stats()["by_type"]["ELLIPSE"] == 1
    blocks = ezjww.readfile(sample("blocks"))
    assert blocks.audit()["total_references"] == 3
    assert not blocks.audit()["has_issues"]
    assert len(blocks.to_dxf()["blocks"]) == 2
    exploded = blocks.to_dxf(explode_inserts=True)
    assert len(exploded["entities"]) == 6
    assert all(e["type"] != "INSERT" for e in exploded["entities"])
    image = ezjww.read_jws_document(sample("image"))
    assert image["entities"][2]["image"]["file_name"] == "symbol.bmp"
    assert image["images"] == []  # Native registration did not embed the bitmap.
    drawing = ezjww.readfile(sample("image"))
    assert len(drawing.to_dxf()["entities"]) == 2
    assert drawing.to_dxf()["jws_conversion_report"]["omitted_image_references"] == 1
    assert drawing.audit()["unsupported_entities"] == ["IMAGE_REFERENCE"]
    assert drawing.audit()["has_issues"]


def test_origin_scale_bbox_and_dxf_report(tmp_path):
    drawing = ezjww.readfile(sample("scales"))
    assert drawing.header["origin"] == {"x": 10, "y": 20}
    assert drawing.header["group_scales"][:2] == [50, 100]
    dxf = drawing.to_dxf()
    assert (dxf["entities"][0]["x1"], dxf["entities"][0]["y1"]) == (10, 20)
    assert dxf["entities"][2]["x1"] == -40
    report = dxf["jws_conversion_report"]
    assert report["coordinate_space"] == "paper_millimeters"
    assert report == drawing.report()["jws_conversion_report"]
    assert report == drawing.audit()["jws_conversion_report"]
    assert drawing.bbox()["min_x"] == -40
    for version in ("AC1015", "AC1024"):
        output = tmp_path / (version + ".dxf")
        drawing.save_dxf(output, target_version=version)
        written = ezjww.write_dxf_with_report(sample("scales"), str(output), target_version=version)
        assert output.read_text() == drawing.to_dxf_string(target_version=version)
        assert written["source_format"] == "jws"
        assert written["jws_conversion_report"] == report
        assert version in output.read_text()


@pytest.mark.parametrize("name", ["basic", "blocks", "unicode", "geometry"])
def test_invalid_input_propagates_through_all_readers(name, tmp_path):
    data = Path(sample(name)).read_bytes()
    path = tmp_path / "broken.jws"
    for value in (data[:451], data[:-1], data + b"\0\0\0\0"):
        path.write_bytes(value)
        for read in (ezjww.read_jws_document, ezjww.read_cad_document,
                     ezjww.readfile, ezjww.read_dxf_document, ezjww.read_dxf_string):
            with pytest.raises(ValueError):
                read(str(path))


def test_synthetic_empty_symbol(tmp_path):
    data = Path(sample()).read_bytes()[:452] + struct.pack("<HH", 0, 0)
    path = tmp_path / "empty.jws"
    path.write_bytes(data)
    drawing = ezjww.readfile(path)
    assert len(drawing.modelspace()) == 0
    assert drawing.bbox() is None
    assert not drawing.audit()["has_issues"]


@pytest.mark.parametrize("command", ["info", "audit", "bbox", "stats", "report"])
def test_cli_json(command, capsys):
    assert ezjww._run([command, sample("blocks"), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result
    if command in {"info", "audit", "report"}:
        assert result["source_format"] == "jws"


def test_cli_directory_and_plot(tmp_path, capsys):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "symbol.JWS").write_bytes(Path(sample()).read_bytes())
    assert ezjww._run(["to-dxf-dir", str(inputs), "-o", str(tmp_path / "dxf")]) == 0
    capsys.readouterr()
    assert (tmp_path / "dxf/symbol.dxf").is_file()
    pytest.importorskip("matplotlib")
    preview = tmp_path / "preview.png"
    assert ezjww._run(["plot", sample("geometry"), "-o", str(preview)]) == 0
    assert preview.read_bytes().startswith(b"\x89PNG")
