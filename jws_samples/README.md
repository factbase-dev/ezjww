# Original JWS reader fixtures

These symbols were created for ezjww from original geometry and text, using
Jw_cad 10.02.1 under Wine/Xvfb on Linux on 2026-10-13. The generated input
drawings and native JWS outputs are provided under this repository's MIT
license. No Jw_cad executable or installed third-party symbol library is included.

`manifest.json` records SHA-256 hashes, file versions, input drawings and the
application binary hash. `inputs/` contains the generated JWW drawings;
`native/` contains the unmodified Jw_cad registration results.

| Case | Main records | Purpose |
| --- | --- | --- |
| basic_v600, basic_v700 | 2 lines, 1 circle | Old/current save, nonzero origin |
| scales_v700 | 3 lines | Group 0 scale 50, group 1 scale 100 |
| geometry_v700 | 9 | Arc, ellipse, point, solids, dimension |
| unicode_v700 | 2 lines, 2 texts | Japanese, surrogate pair, half-width kana, rotation |
| blocks_v700 | 2 lines, 2 inserts | Two definitions, nested rotation, nonuniform scale |
| image_v700 | 2 lines, image text | Image-reference-only symbol |

To reproduce inputs, run `python scripts/jws/make_inputs.py <new-directory>`
with an installed ezjww build. In Jw_cad, open each input, choose **図形登録**,
enclose all geometry and texts, change the origin by snapping to the shared
line endpoint `(10, 20)`, confirm the selection and save a new `.jws` file.
Use the old-format checkbox for the 600 case; default output is 700.

The native old-format case has header 600 but runtime class schemas 700. The
older 420/351/300/230 save controls were disabled for JWS in this application;
they must not be used to label native fixtures for those versions.

The input image is an original generated 2x2 bitmap. Native registration
retained `%temp%symbol.bmp` as a text reference without embedding image bytes.
Native block names gained the `@@SfigorgFlag@@4` suffix, which is preserved.
Selection flags and native dimension normalization are retained in the outputs.

Tests separately identify synthetic empty bodies and schema mutations. These
are not native-produced fixtures. Unit tests also reject every truncated prefix
of the native JWS files. `placement/basic_translated.jww` records a native read-and-place check at
default scale 1. Its added two lines and circle preserve the JWS dimensions and
relative coordinates after translation. The click coordinate is inferred from
the saved geometry, not an independently typed coordinate. Cross-scale
placement is not qualified.
