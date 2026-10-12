use super::JwsError;
use crate::{reader::Reader, Coord2D};
use serde::Serialize;
use std::{fs::File, io::Read, path::Path};

pub(crate) const HEADER_SIZE: usize = 452;
pub const JWS_SIGNATURE: &[u8; 8] = b"JwsData.";

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct JwsHeader {
    pub version: u32,
    /// Insertion origin, in the file's paper coordinates. Not subtracted on read.
    pub origin: Coord2D,
    /// Positive scale denominators, indexed by entity layer_group.
    pub group_scales: [f64; 16],
    /// Bounds recorded by Jw_cad, not a substitute for a computed geometry bbox.
    pub bounds_min: Coord2D,
    pub bounds_max: Coord2D,
    /// Retained without assigning undocumented semantics.
    pub reserved_prefix: Vec<u8>,
    pub reserved_integers: [u32; 6],
    pub reserved_reals: [f64; 6],
}
pub fn is_jws_signature(data: &[u8]) -> bool {
    data.starts_with(JWS_SIGNATURE)
}
pub fn parse_jws_header(data: &[u8]) -> Result<JwsHeader, JwsError> {
    if !is_jws_signature(data) {
        return Err(JwsError::invalid(0, "expected JwsData. signature"));
    }
    if data.len() < HEADER_SIZE {
        return Err(JwsError::invalid(data.len(), "truncated 452-byte header"));
    }
    let mut r = Reader::new(data);
    // Fixed-width header has already been bounded above.
    let result = (|| -> Result<JwsHeader, crate::JwwError> {
        r.skip(8)?;
        let reserved_prefix = r.read_bytes(192)?;
        let version = r.read_u32()?;
        let origin = Coord2D::new(r.read_f64()?, r.read_f64()?);
        let mut group_scales = [0.; 16];
        for s in &mut group_scales {
            *s = r.read_f64()?;
        }
        let mut reserved_integers = [0; 6];
        for v in &mut reserved_integers {
            *v = r.read_u32()?;
        }
        let mut reserved_reals = [0.; 6];
        for v in &mut reserved_reals {
            *v = r.read_f64()?;
        }
        let bounds_min = Coord2D::new(r.read_f64()?, r.read_f64()?);
        let bounds_max = Coord2D::new(r.read_f64()?, r.read_f64()?);
        Ok(JwsHeader {
            version,
            origin,
            group_scales,
            bounds_min,
            bounds_max,
            reserved_prefix,
            reserved_integers,
            reserved_reals,
        })
    })();
    let h = result.map_err(|source| JwsError::Archive {
        byte_offset: r.bytes_read(),
        source,
    })?;
    if !matches!(h.version, 351 | 420 | 600 | 700) {
        return Err(JwsError::invalid(
            200,
            format!("unsupported version {}", h.version),
        ));
    }
    for (offset, p) in [(204, h.origin), (420, h.bounds_min), (436, h.bounds_max)] {
        if !p.x.is_finite() || !p.y.is_finite() {
            return Err(JwsError::invalid(offset, "non-finite coordinate"));
        }
    }
    for (i, s) in h.group_scales.iter().enumerate() {
        if !s.is_finite() || *s <= 0. {
            return Err(JwsError::invalid(
                220 + i * 8,
                "scale must be finite and positive",
            ));
        }
    }
    if h.reserved_reals.iter().any(|v| !v.is_finite()) {
        return Err(JwsError::invalid(372, "non-finite reserved real"));
    }
    if h.bounds_min.x > h.bounds_max.x || h.bounds_min.y > h.bounds_max.y {
        return Err(JwsError::invalid(420, "inverted bounds"));
    }
    Ok(h)
}
pub fn read_jws_header_from_file(path: impl AsRef<Path>) -> Result<JwsHeader, JwsError> {
    let mut data = Vec::with_capacity(HEADER_SIZE);
    File::open(path)?
        .take(HEADER_SIZE as u64)
        .read_to_end(&mut data)?;
    parse_jws_header(&data)
}
