import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

export function checkJwsParity({ root, api, python }) {
  const paths = readdirSync(resolve(root, "jws_samples/native")).filter(n => n.endsWith(".jws"))
    .sort().map(n => resolve(root, "jws_samples/native", n));
  const code = String.raw`
import hashlib, json, sys
import ezjww
def canonical(value):
    if isinstance(value, list): return [canonical(v) for v in value]
    if isinstance(value, dict): return {k:canonical(v) for k,v in value.items() if k != 'block_name'}
    return value
out=[]
for path in json.loads(sys.argv[1]):
    out.append({
        'document':canonical(ezjww.read_jws_document(path)),
        'dxf':ezjww.read_dxf_document(path),
        'hashes':[hashlib.sha256(ezjww.read_dxf_string(path, explode, 32, version, 1.0).encode()).hexdigest()
                  for explode in (False, True) for version in ('AC1015', 'AC1024')],
    })
print(json.dumps(out,ensure_ascii=False))
`;
  const expected = JSON.parse(execFileSync(python, ["-c", code, JSON.stringify(paths)], { encoding: "utf8" }));
  // Python enriches block references with names; raw WASM retains def_number.
  const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object"
    ? Object.fromEntries(Object.entries(value).filter(([k]) => k !== "block_name").map(([k, v]) => [k, canonical(v)])) : value;
  const actual = paths.map(path => {
    const bytes = readFileSync(path);
    return {
      document: canonical(api.readJwsDocument(bytes)),
      dxf: api.readDxfDocument(bytes),
      hashes: [false, true].flatMap(explodeInserts => ["AC1015", "AC1024"].map(targetVersion =>
        createHash("sha256").update(api.readDxfString(bytes, { explodeInserts, targetVersion })).digest("hex"))),
    };
  });
  assert.deepEqual(actual, expected);
  return { inputs: paths.length, dxf_hashes: paths.length * 4 };
}
