use super::{archive::ArchiveWriter, JwwWriteError, JwwWriteOptions};

// See templates/README.md for provenance and reproducible extraction.
const TEMPLATE: &[u8] = include_bytes!("templates/header_700.bin");
#[cfg(test)]
const TEMPLATE_MEMO_END: usize = 20; // pinned UTF-16LE CRLF after signature/version
const TABLE_END: usize = 28 + 16 * 148;
const NAMES_START: usize = TABLE_END + 84 + 72;
// 272 Unicode CStrings: all empty except "0" and "Defpoints".
const NAMES_END: usize = NAMES_START + 272 * 4 + 2 * (1 + 9);

pub(super) fn write(
    archive: &mut ArchiveWriter,
    options: &JwwWriteOptions,
) -> Result<(), JwwWriteError> {
    archive.bytes(b"JwwData.");
    archive.u32(options.version);
    archive.cstring(&options.memo, "options.memo")?;
    archive.u32(options.paper_size);
    archive.u32(options.write_layer_group);
    for group in &options.layer_groups {
        archive.u32(group.state);
        archive.u32(group.write_layer);
        archive.f64(group.scale);
        archive.u32(group.protect);
        for layer in &group.layers {
            archive.u32(layer.state);
            archive.u32(layer.protect);
        }
    }
    let template = configured_template(options)?;
    archive.bytes(&template[TABLE_END..NAMES_START]);
    for (g, group) in options.layer_groups.iter().enumerate() {
        for (l, layer) in group.layers.iter().enumerate() {
            archive.cstring(
                &layer.name,
                &format!("options.layer_groups[{g}].layers[{l}].name"),
            )?;
        }
    }
    for (g, group) in options.layer_groups.iter().enumerate() {
        archive.cstring(&group.name, &format!("options.layer_groups[{g}].name"))?;
    }
    archive.bytes(&template[NAMES_END..]);
    Ok(())
}

/// The immutable template supplies fields not exposed by the writer. Patch only
/// configured tables; default drawings retain their native-qualified bytes.
fn configured_template(options: &JwwWriteOptions) -> Result<Vec<u8>, JwwWriteError> {
    use crate::reader::Reader;
    let mut data = TEMPLATE.to_vec();
    // m_nMaxDrawWid: the last DWORD of the 84 bytes after the layer tables
    // (14 dummies, 5 dimension settings, 1 dummy, then this).
    let max_draw_width = TABLE_END + (14 + 5 + 1) * 4;
    let pens = NAMES_END + 464;
    let patterns = pens + 10 * 8 + 10 * 16;
    // Eleventh of the print flags after the line types: m_nPrtDispOnlyNonDraw plus
    // 10 for 300 dpi or 20 for 600 dpi (the dpi that widths in dots refer to).
    let dpi_flag = patterns + 8 * 16 + 5 * 20 + 4 * 16 + 10 * 4;
    let extended = patterns + 8 * 16 + 5 * 20 + 4 * 16 + 44 + 20 + 40 + 32 + 8;
    let mut reader = Reader::new(TEMPLATE);
    reader.skip(extended + 257 * 8).expect("template offset");
    let mut printers = Vec::new();
    for _ in 0..257 {
        reader.read_cstring().expect("template color name");
        printers.push(reader.bytes_read());
        reader.skip(16).expect("template printer pen");
    }
    let sxf_start = reader.bytes_read();
    reader.skip(33 * 16).expect("template patterns");
    for _ in 0..33 {
        reader.read_cstring().expect("template line name");
        reader.skip(84).expect("template segments");
    }
    let sxf_end = reader.bytes_read();
    let patch_u32 = |data: &mut [u8], at: usize, value: u32| {
        data[at..at + 4].copy_from_slice(&value.to_le_bytes());
    };
    if let Some(palette) = &options.palette {
        for (i, &color) in palette.pen_colors.iter().enumerate() {
            let at = pens + i * 8;
            let old = u32::from_le_bytes(data[at..at + 4].try_into().unwrap()) & 0xffffff;
            if color != old {
                patch_u32(&mut data, at, color);
                patch_u32(&mut data, pens + 80 + i * 16, color);
            }
        }
        for (i, &color) in palette.extended_colors.as_ref().unwrap().iter().enumerate() {
            let at = extended + i * 8;
            let old = u32::from_le_bytes(data[at..at + 4].try_into().unwrap()) & 0xffffff;
            if color != old {
                patch_u32(&mut data, at, color);
                patch_u32(&mut data, printers[i], color);
            }
        }
    }
    if let Some(pens_table) = &options.pens {
        let expected = crate::header::WidthUnit::from_max_draw_width(pens_table.max_draw_width);
        if pens_table.width_unit != expected {
            return Err(JwwWriteError::invalid(
                "options.pens.width_unit",
                format!(
                    "{} does not match max_draw_width {} ({})",
                    pens_table.width_unit.as_str(),
                    pens_table.max_draw_width,
                    expected.as_str()
                ),
            ));
        }
        if !matches!(pens_table.printer_dpi, None | Some(300) | Some(600)) {
            return Err(JwwWriteError::invalid(
                "options.pens.printer_dpi",
                "expected 300, 600 or null",
            ));
        }
        let patch_pen = |data: &mut [u8], at: usize, pen: &crate::header::PrinterPen| {
            if !pen.point_radius.is_finite() || pen.point_radius < 0.0 {
                return Err(JwwWriteError::invalid(
                    "options.pens.point_radius",
                    "expected a finite, non-negative radius",
                ));
            }
            // A color still at its template value keeps whatever `palette` derived
            // from the screen color (and the template's own bytes, marker included).
            let template_color =
                u32::from_le_bytes(TEMPLATE[at..at + 4].try_into().unwrap()) & 0xffffff;
            if pen.color != template_color {
                data[at..at + 4].copy_from_slice(&pen.color.to_le_bytes());
            }
            data[at + 4..at + 8].copy_from_slice(&pen.width.to_le_bytes());
            data[at + 8..at + 16].copy_from_slice(&pen.point_radius.to_le_bytes());
            Ok(())
        };
        patch_u32(&mut data, max_draw_width, pens_table.max_draw_width as u32);
        for (i, &width) in pens_table.screen_widths.iter().enumerate() {
            patch_u32(&mut data, pens + i * 8 + 4, width);
        }
        for (i, pen) in pens_table.printer.iter().enumerate() {
            patch_pen(&mut data, pens + 80 + i * 16, pen)?;
        }
        if let Some(extended_pens) = &pens_table.extended_printer {
            if extended_pens.len() != 257 {
                return Err(JwwWriteError::invalid(
                    "options.pens.extended_printer",
                    "expected 257 entries (pen colors 100-356)",
                ));
            }
            for (i, pen) in extended_pens.iter().enumerate() {
                patch_pen(&mut data, printers[i], pen)?;
            }
        }
        let flag = u32::from_le_bytes(data[dpi_flag..dpi_flag + 4].try_into().unwrap()) % 10;
        let dpi_part = match pens_table.printer_dpi {
            Some(300) => 10,
            Some(600) => 20,
            _ => 0,
        };
        patch_u32(&mut data, dpi_flag, flag + dpi_part);
    }
    if let Some(presets) = &options.text_presets {
        for (i, preset) in presets.iter().enumerate() {
            let at = sxf_end + i * 28;
            for (j, value) in [preset.size_x, preset.size_y, preset.spacing]
                .iter()
                .enumerate()
            {
                data[at + j * 8..at + j * 8 + 8].copy_from_slice(&value.to_le_bytes());
            }
            patch_u32(&mut data, at + 24, preset.pen_color);
        }
    }
    if let Some(types) = &options.line_types {
        let defaults = crate::parse_header(TEMPLATE)
            .expect("template")
            .line_types
            .unwrap();
        if types != &defaults {
            let mut table = ArchiveWriter::new();
            for pattern in &types.standard {
                write_pattern(&mut table, pattern);
            }
            for random in &types.random {
                for value in [
                    random.pattern,
                    random.width,
                    random.pitch,
                    random.printer_width,
                    random.printer_pitch,
                ] {
                    table.u32(value);
                }
            }
            for pattern in &types.double_length {
                write_pattern(&mut table, pattern);
            }
            let table = table.into_bytes();
            data[patterns..patterns + table.len()].copy_from_slice(&table);
            let mut sxf = ArchiveWriter::new();
            let slots = types.sxf.as_ref().unwrap();
            for slot in slots {
                write_pattern(&mut sxf, &slot.pattern);
            }
            for slot in slots {
                sxf.cstring(&slot.name, "options.line_types.sxf.name")?;
                sxf.u32(slot.segments_mm.len() as u32);
                for i in 0..10 {
                    sxf.f64(slot.segments_mm.get(i).copied().unwrap_or(0.0));
                }
            }
            data.splice(sxf_start..sxf_end, sxf.into_bytes());
        }
    }
    Ok(data)
}

fn write_pattern(archive: &mut ArchiveWriter, pattern: &crate::header::LineTypePattern) {
    for value in [
        pattern.pattern,
        pattern.unit_dots,
        pattern.pitch,
        pattern.printer_pitch,
    ] {
        archive.u32(value);
    }
}

pub fn default_tables() -> crate::header::JwwHeader {
    crate::parse_header(TEMPLATE).expect("embedded header")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn template_has_a_complete_header_and_no_geometry() {
        assert_eq!(TEMPLATE.len(), 16558);
        assert_eq!(
            &TEMPLATE[12..TEMPLATE_MEMO_END],
            &[255, 254, 255, 2, 13, 0, 10, 0]
        );
        assert_eq!(
            crate::header_layout::header_end_v700(TEMPLATE).unwrap(),
            TEMPLATE.len()
        );
        let header = crate::parse_header(TEMPLATE).unwrap();
        assert_eq!(header.version, 700);
        assert_eq!(header.memo, "\r\n");
        assert!(header.layer_groups.iter().all(|group| group.scale == 1.0));
        let mut reader = crate::reader::Reader::new(TEMPLATE);
        reader.skip(NAMES_START).unwrap();
        for i in 0..272 {
            assert_eq!(
                reader.read_cstring().unwrap(),
                match i {
                    0 => "0",
                    1 => "Defpoints",
                    _ => "",
                }
            );
        }
        assert_eq!(reader.bytes_read(), NAMES_END);
    }
}
