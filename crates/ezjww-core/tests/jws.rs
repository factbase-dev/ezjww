use ezjww_core::{
    convert_jws_document, detect_format, parse_cad_document, parse_document, parse_jws_document,
    parse_jws_header, CadDocument, CadFormat, ConvertOptions, Entity,
};

const BASIC: &[u8] = include_bytes!("../../../jws_samples/native/basic_v700.jws");
const LEGACY: &[u8] = include_bytes!("../../../jws_samples/native/basic_v600.jws");
const GEOMETRY: &[u8] = include_bytes!("../../../jws_samples/native/geometry_v700.jws");
const UNICODE: &[u8] = include_bytes!("../../../jws_samples/native/unicode_v700.jws");
const BLOCKS: &[u8] = include_bytes!("../../../jws_samples/native/blocks_v700.jws");
const IMAGE: &[u8] = include_bytes!("../../../jws_samples/native/image_v700.jws");
const SCALES: &[u8] = include_bytes!("../../../jws_samples/native/scales_v700.jws");

#[test]
fn native_symbols_have_separate_header_and_shared_geometry() {
    for (data, count) in [
        (BASIC, 3),
        (LEGACY, 3),
        (GEOMETRY, 9),
        (UNICODE, 4),
        (BLOCKS, 4),
        (IMAGE, 3),
        (SCALES, 3),
    ] {
        let doc = parse_jws_document(data).unwrap();
        assert_eq!(detect_format(data), Some(CadFormat::Jws));
        assert!(matches!(
            parse_cad_document(data).unwrap(),
            CadDocument::Jws(_)
        ));
        assert!(parse_document(data).is_err());
        assert_eq!(doc.header, parse_jws_header(&data[..452]).unwrap());
        assert_eq!((doc.header.origin.x, doc.header.origin.y), (10., 20.));
        assert_eq!(doc.entities.len(), count);
        assert!(doc.diagnostics.is_empty());
        assert!(doc.images.is_empty());
    }
    let doc = parse_jws_document(BLOCKS).unwrap();
    assert_eq!(doc.block_defs.len(), 2);
    assert_eq!(doc.validate_block_references().total_references, 3);
    assert!(!doc.validate_block_references().has_unresolved());
    assert!(doc.block_defs[0].name.starts_with("部品𠮷"));
    let doc = parse_jws_document(UNICODE).unwrap();
    let Entity::Text(text) = &doc.entities[2] else {
        panic!("expected text")
    };
    assert_eq!(text.content, "日本語𠮷ｶﾅ ABC");
    let doc = parse_jws_document(IMAGE).unwrap();
    let Entity::Text(text) = &doc.entities[2] else {
        panic!("expected image reference")
    };
    assert_eq!(text.image_reference().unwrap().file_name, "symbol.bmp");
}

#[test]
fn read_and_conversion_preserve_source_coordinates_and_scales() {
    let doc = parse_jws_document(SCALES).unwrap();
    assert_eq!(&doc.header.group_scales[..2], &[50., 100.]);
    let converted = convert_jws_document(&doc, ConvertOptions::default()).unwrap();
    let value = serde_json::to_value(converted).unwrap();
    assert_eq!(value["entities"][0]["x1"], 10.);
    assert_eq!(value["entities"][0]["y1"], 20.);
    assert_eq!(value["entities"][2]["x1"], -40.);
    assert_eq!(
        value["jws_conversion_report"]["coordinate_space"],
        "paper_millimeters"
    );
}

#[test]
fn every_truncated_native_prefix_fails_including_nested_block_lists() {
    for data in [BASIC, LEGACY, GEOMETRY, UNICODE, BLOCKS, IMAGE, SCALES] {
        for end in 0..data.len() {
            assert!(
                parse_jws_document(&data[..end]).is_err(),
                "accepted prefix {end}/{}",
                data.len()
            );
        }
    }
}

#[test]
fn invalid_headers_counts_classes_numbers_and_trailers_fail() {
    for (offset, replacement) in [
        (0, b"BadData.".to_vec()),
        (200, 999u32.to_le_bytes().to_vec()),
        (204, f64::NAN.to_le_bytes().to_vec()),
        (220, 0f64.to_le_bytes().to_vec()),
        (220, (-1f64).to_le_bytes().to_vec()),
        (420, f64::INFINITY.to_le_bytes().to_vec()),
        (452, vec![0xff; 6]),    // extended count cannot fit in the input
        (454, vec![0xff, 0x8f]), // unknown archive class reference
        (456, 999u16.to_le_bytes().to_vec()), // schema mismatch
        (460, b"NoSuchXX".to_vec()),
        (483, f64::NAN.to_le_bytes().to_vec()), // first line's x
    ] {
        let mut data = BASIC.to_vec();
        data[offset..offset + replacement.len()].copy_from_slice(&replacement);
        assert!(
            parse_jws_document(&data).is_err(),
            "accepted mutation at {offset}"
        );
    }
    for suffix in [&[0u8][..], &[0, 0, 0, 0][..], b"JWW image archive"] {
        let mut data = BASIC.to_vec();
        data.extend_from_slice(suffix);
        assert!(parse_jws_document(&data).is_err());
    }
    // Declared huge UTF-16 CString length must fail before allocating.
    let mut data = UNICODE.to_vec();
    let start = data
        .windows(4)
        .position(|v| v == [0xff, 0xfe, 0xff, 7])
        .unwrap();
    data.splice(
        start..start + 4,
        [0xff, 0xfe, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x7f],
    );
    assert!(parse_jws_document(&data).is_err());
}

#[test]
fn empty_body_and_old_schema_branches_are_synthetic_not_native_fixtures() {
    let mut empty = BASIC[..452].to_vec();
    empty.extend_from_slice(&[0, 0, 0, 0]);
    assert!(parse_jws_document(&empty).unwrap().entities.is_empty());
    for version in [351u32, 420] {
        let mut data = LEGACY.to_vec();
        data[200..204].copy_from_slice(&version.to_le_bytes());
        for index in 452..data.len() - 3 {
            if data[index..index + 4] == [0xff, 0xff, 0xbc, 0x02] {
                data[index + 2..index + 4].copy_from_slice(&(version as u16).to_le_bytes());
            }
        }
        assert_eq!(parse_jws_document(&data).unwrap().entities.len(), 3);
    }
}
