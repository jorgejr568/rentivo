import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendRoot = resolve(frontendRoot, "../backend");
const outputPath = join(frontendRoot, "openapi.json");
const check = process.argv.includes("--check");
const temporaryDirectory = check ? mkdtempSync(join(tmpdir(), "rentivo-openapi-")) : null;
const generatedPath = temporaryDirectory ? join(temporaryDirectory, "openapi.json") : outputPath;

const result = spawnSync(
  "uv",
  [
    "run",
    "--project",
    backendRoot,
    "python",
    "-m",
    "rentivo.api.export_openapi",
    generatedPath
  ],
  {
    cwd: backendRoot,
    encoding: "utf8",
    env: {
      ...process.env,
      UV_CACHE_DIR: process.env.UV_CACHE_DIR || join(tmpdir(), "rentivo-uv-cache")
    }
  }
);

if (result.status !== 0) {
  process.stderr.write(result.stderr || "Falha ao exportar o OpenAPI.\n");
  if (temporaryDirectory) rmSync(temporaryDirectory, { force: true, recursive: true });
  process.exit(result.status || 1);
}

if (check) {
  const current = readFileSync(outputPath, "utf8");
  const generated = readFileSync(generatedPath, "utf8");
  rmSync(temporaryDirectory, { force: true, recursive: true });
  if (current !== generated) {
    process.stderr.write("frontend/openapi.json está desatualizado. Execute npm run api:snapshot.\n");
    process.exit(1);
  }
}
