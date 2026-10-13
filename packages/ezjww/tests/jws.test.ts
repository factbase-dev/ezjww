import fs from "node:fs";
import path from "node:path";
import { describe, expect, expectTypeOf, it } from "vitest";
import * as raw from "../wasm/ezjww_wasm";
import {
  detectFileFormat, isJwsFile, readCadDocument, readDocument, readDxfDocument,
  readDxfString, readJwsDocument, readJwsHeader, type JwsHeader,
} from "../src/index";

const root = path.resolve(__dirname, "../../../jws_samples/native");
const sample = (name = "basic", version = 700) => fs.readFileSync(path.join(root, `${name}_v${version}.jws`));

describe("JWS public API", () => {
  it.each(["basic", "geometry", "unicode", "blocks", "scales", "image"])("reads native %s through all APIs", name => {
    const data = sample(name);
    const doc = readJwsDocument(data);
    expect(isJwsFile(data)).toBe(true);
    expect(detectFileFormat(data)).toBe("jws");
    expect(doc.header).toEqual(readJwsHeader(data));
    expect(doc.header.origin).toEqual({ x: 10, y: 20 });
    expect(doc.diagnostics).toEqual([]);
    expect(readCadDocument(data)).toEqual({ format: "jws", document: doc });
    expect(() => readDocument(data)).toThrow();
    const cad = readCadDocument(data);
    if (cad.format === "jws") expectTypeOf(cad.document.header).toEqualTypeOf<JwsHeader>();
    expect(readDxfDocument(data).jws_conversion_report?.coordinate_space).toBe("paper_millimeters");
    expect(readDxfString(data)).toContain("AC1015");
    expect(raw.readJwsDocument(data)).toEqual(doc);
    expect(raw.readDxfDocument(data, false, 32)).toEqual(readDxfDocument(data));
  });

  it("preserves Unicode, nested block references, image references and scales", () => {
    const unicode = readJwsDocument(sample("unicode"));
    expect(unicode.entities[2]).toMatchObject({ type: "TEXT", content: "日本語𠮷ｶﾅ ABC" });
    const blocks = readJwsDocument(sample("blocks"));
    expect(blocks.block_defs).toHaveLength(2);
    expect(blocks.validation).toMatchObject({ total_references: 3, has_unresolved: false });
    expect(readDxfDocument(sample("blocks"), { explodeInserts: true }).entities).toHaveLength(6);
    expect(readJwsDocument(sample("image")).entities[2]).toMatchObject({ image: { file_name: "symbol.bmp" } });
    const imageDxf = readDxfDocument(sample("image"));
    expect(imageDxf.entities).toHaveLength(2);
    expect(imageDxf.unsupported_entities).toEqual(["IMAGE_REFERENCE"]);
    expect(imageDxf.jws_conversion_report?.omitted_image_references).toBe(1);
    expect(readJwsHeader(sample("scales")).group_scales.slice(0, 2)).toEqual([50, 100]);
    expect(readDxfDocument(sample("scales")).entities[2]).toMatchObject({ x1: -40, y1: -20 });
    expect(readJwsHeader(sample("basic", 600)).version).toBe(600);
    expect(readJwsDocument(sample("basic", 600)).entities).toHaveLength(3);
  });

  it("honors view offsets and fails on truncation or trailing bytes", () => {
    const data = sample("blocks");
    const buffer = new Uint8Array(data.length + 16);
    buffer.set(data, 7);
    expect(readJwsDocument(new DataView(buffer.buffer, 7, data.length))).toEqual(readJwsDocument(data));
    for (const end of [0, 8, 200, 451, 452, data.length - 1]) {
      for (const read of [readJwsDocument, readCadDocument, readDxfDocument]) {
        expect(() => read(data.subarray(0, end))).toThrow();
      }
    }
    expect(() => readJwsDocument(Buffer.concat([data, Buffer.alloc(4)]))).toThrow();
    const unknown = Uint8Array.from(sample());
    new DataView(unknown.buffer).setUint32(200, 999, true);
    expect(isJwsFile(unknown)).toBe(true);
    expect(() => readJwsDocument(unknown)).toThrow(/unsupported version/);
  });
});
