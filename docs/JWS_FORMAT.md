# JWS registered symbols

`ezjww` reads Jw_cad's binary `.jws` registered symbols with the `JwsData.`
signature. It supports file versions **351, 420, 600 and 700**. Detection checks
the signature only; a matching signature is not a successful parse.

## APIs

```python
import ezjww

symbol = ezjww.readfile("part.jws")
assert symbol.source_format == "jws"
print(symbol.header["origin"], symbol.header["group_scales"])
print(symbol.bbox(), symbol.stats())
symbol.save_dxf("part.dxf")

source = ezjww.read_jws_document("part.jws")
header = ezjww.read_jws_header("part.jws")
```

The dedicated Python functions are `is_jws_file`, `read_jws_header` and
`read_jws_document`. TypeScript/WASM exposes `isJwsFile`, `readJwsHeader` and
`readJwsDocument`, accepting bytes and respecting `ArrayBufferView` offsets.
`readCadDocument` / `read_cad_document` returns `{format: "jws", document: ...}`.
Rust exposes `parse_jws_header`, `parse_jws_document`, their file readers and
`convert_jws_document`.

The existing JWW-only `read_document` / `readDocument` and `read_header` /
`readHeader` contracts are unchanged. A JWS document has its own header type;
it does not invent a JWW memo, paper size, palette or layer settings.

The regular modelspace, bbox, audit, plot and DXF APIs accept JWS. CLI commands
`info`, `audit`, `bbox`, `stats`, `report`, `to-dxf`, `to-dxf-dir` and `plot`
also accept it. There is no JWS writer or symbol-insertion API.

## Coordinates and conversion

Entity coordinates remain in the file's **paper millimeters**. Reading or
converting a symbol does not subtract its insertion origin or multiply by its
group scales. This preserves the same coordinate convention as the JWW reader.
Inserting into a target Jw_cad drawing, with its scale and placement settings,
is a separate operation.

The recorded bounds are exposed as `bounds_min` and `bounds_max`; `bbox()`
computes geometry bounds separately. `group_scales` has 16 scale denominators
indexed by the source entity's `layer_group`.

DXF uses generated layer names and the converter's default pen colors and line
types because JWS does not carry a drawing's palette or layer tables. The
`jws_conversion_report` returned by conversion, audit, report and
`write_dxf_with_report` records this policy, the coordinate space, insertion
origin and scales. DXF units are millimeters. Existing options for block
expansion, text sizing and AC1015/AC1024 output remain available. Dimensions
use the shared primitive conversion, and nested block transforms use the shared
block converter.

## Binary layout and error handling

All offsets below are measured from the start of the file, with little-endian
integers and IEEE-754 doubles.

| Offset | Bytes | Field |
| --- | --- | --- |
| 0 | 8 | `JwsData.` |
| 8 | 192 | Reserved prefix; observed as periods |
| 200 | 4 | File version |
| 204 | 16 | Insertion origin x, y |
| 220 | 128 | 16 group scales |
| 348 | 24 | Six reserved DWORDs |
| 372 | 48 | Six reserved doubles |
| 420 | 32 | Recorded min x, min y, max x, max y |
| 452 | variable | MFC entity list, then block-definition list |

The body shares the JWW entity decoders and one MFC class/object table across
top-level entities and block definitions. New classes and class references,
WORD/extended counts, CP932 strings and tagged UTF-16LE CStrings are supported.
Jw_cad 10.02.1's old-format save was observed to use header version 600 with
class schema 700; this specific pair is accepted in addition to matching
versions. Object-reference records remain unsupported.

JWS parsing requires complete lists and exact end of input. Truncated entities,
including nested block entities, unsupported versions/classes, invalid class
references, mismatched schemas, non-finite numbers and unexplained trailing
bytes raise an error with a byte offset. Header scales must be positive and
bounds ordered. File reads are limited to 256 MiB; string allocation is bounded
by remaining input. Decoding replacement diagnostics are retained. JWW's
existing best-effort reader behavior is unchanged.

The reserved fields are preserved without assigning them semantics. A file
using an unqualified extension or trailing record is rejected rather than
silently dropping it.

## Evidence and limits

- A local installed-symbol corpus contained 341 files (338 unique): 311 version
  351, three version 420 and 27 version 600. The production reader decoded all
  of them through EOF: 27,183 main entities and 3,796 entities in 14 block
  definitions. Those third-party symbols are not redistributed here.
- [Repository fixtures](../jws_samples/README.md) were produced from original
  generated JWW inputs by Jw_cad 10.02.1 under Wine on Linux. They cover native
  saves at 600/700, a read-and-place translation check, nonzero origin, multiple scales, lines/arcs/circles/ellipses,
  points, polygon/circle solids, dimensions, Unicode text, nested block inserts
  and image references. This is not a Windows validation claim.
- Empty-symbol framing and older schema branches have synthetic tests; an
  empty symbol has not been qualified through Jw_cad registration. Version
  230/300, arbitrary future extensions and insertion across different drawing scales are
  outside the qualification scope.
- The image case contains a `^@BM` text reference but **no bitmap archive**.
  `images` is empty. The original bitmap is not recovered from that reference,
  fetched from the filesystem or included in DXF/preview output. The control
  text is also omitted from rendered geometry. `omitted_image_references` in
  the conversion report counts source placements, and `IMAGE_REFERENCE` in
  `unsupported_entities` makes the omission visible through the existing audit
  warning. An appended
  JWW-style image archive is not accepted as a known JWS extension.
- Default rendering settings cannot reproduce custom source-drawing palettes
  or line tables that were never stored in the symbol.

The header layout is measured from files, with historical corroboration from
an [independent reader author's description](https://www.jwcad.net/log/consult2/consult2-0610-12/thread17752.htm).
It is not presented as a complete official JWS specification.
