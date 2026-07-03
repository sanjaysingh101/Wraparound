#!/usr/bin/env node
/**
 * PLY → KSPLAT converter using the official @mkkellogg/gaussian-splats-3d library
 * (the library defines the .ksplat format). Invoked by the Python backend.
 *
 *   node convert-ksplat.mjs <input.ply> <output.ksplat> [compressionLevel=1] [sphericalHarmonicsDegree=0]
 */
import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const [, , input, output, compression = "1", shDegree = "0"] = process.argv;
if (!input || !output) {
  console.error("usage: convert-ksplat.mjs <input.ply> <output.ksplat> [compression] [shDegree]");
  process.exit(2);
}

// Resolve the library from the app's node_modules (installed by npm install in app/).
const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "..", "app", "package.json"));
const GaussianSplats3D = await import(
  require.resolve("@mkkellogg/gaussian-splats-3d/build/gaussian-splats-3d.module.js")
);

const plyBuffer = readFileSync(input);
const splatBuffer = GaussianSplats3D.PlyLoader.loadFromFileData
  ? await GaussianSplats3D.PlyLoader.loadFromFileData(
      plyBuffer.buffer.slice(plyBuffer.byteOffset, plyBuffer.byteOffset + plyBuffer.byteLength),
      0.01, // minimumAlpha
      Number(compression),
      true, // optimizeSplatData
      Number(shDegree)
    )
  : null;

if (!splatBuffer) {
  console.error("Unsupported gaussian-splats-3d version: PlyLoader.loadFromFileData missing");
  process.exit(1);
}

writeFileSync(output, Buffer.from(splatBuffer.bufferData));
console.log(`wrote ${output}`);
