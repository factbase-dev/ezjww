import { describe, expect, it } from "vitest";
import {
  imageReference, imageReferenceContent, newJwwDocument, readDocument, toJwwBytes, toWriteDocument,
  type EntityBase, type JwwWriteText,
} from "../src/index";

const base = (): EntityBase => ({
  group: 0, pen_style: 1, pen_color: 1, pen_width: 0, layer: 0, layer_group: 0, flag: 0,
});
const bytes = new Uint8Array([0x42, 0x4d, 1, 2, 3, 4, 5, 6, 7]);
const base64 = Buffer.from(bytes).toString("base64");

describe("embedded images", () => {
  it("round-trips the archive and parses placements", () => {
    const doc = newJwwDocument();
    doc.images = [{ name: "logo.bmp", data: base64 }];
    const content = imageReferenceContent("%temp%logo.bmp", 100, 64.5161);
    expect(content).toBe("^@BM%temp%logo.bmp,100,64.5161,0,0,1,0,255,255,255");
    const text: JwwWriteText = {
      type: "TEXT", base: base(), start_x: 10, start_y: 20, end_x: 110, end_y: 20,
      text_type: 0, size_x: 2, size_y: 2, spacing: 0, angle: 0, font_name: "ＭＳ ゴシック", content,
    };
    doc.entities.push(text);
    const parsed = readDocument(toJwwBytes(doc));
    expect(parsed.images).toEqual([{ name: "logo.bmp", data: base64, compressed: false }]);
    expect(parsed.entities[0].image).toEqual({
      path: "%temp%logo.bmp", file_name: "logo.bmp", width: 100, height: 64.5161,
      extra: ["0", "0", "1", "0", "255", "255", "255"],
    });
    expect(imageReference(content)).toEqual(parsed.entities[0].image);
    expect(imageReference("plain")).toBeNull();
    const converted = toWriteDocument(parsed);
    expect(converted.document?.images).toEqual(parsed.images);
    expect(readDocument(toJwwBytes(converted.document!)).images).toEqual(parsed.images);
  });

  it("rejects placements that name a missing embedded image", () => {
    const doc = newJwwDocument();
    doc.entities.push({
      type: "TEXT", base: base(), start_x: 0, start_y: 0, end_x: 10, end_y: 0, text_type: 0,
      size_x: 2, size_y: 2, spacing: 0, angle: 0, font_name: "ＭＳ ゴシック",
      content: imageReferenceContent("%temp%missing.bmp", 10, 10, ["0"]),
    });
    expect(() => toJwwBytes(doc)).toThrow(/not embedded/);
  });
});
