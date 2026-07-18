import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourcePath = join(frontendRoot, "openapi.json");
const outputPath = join(frontendRoot, "src/lib/api/schema.d.ts");
const check = process.argv.includes("--check");
const schema = await openapiTS(pathToFileURL(sourcePath), { alphabetize: true });
const generated = astToString(schema);

if (check) {
  const current = readFileSync(outputPath, "utf8");
  if (current !== generated) {
    process.stderr.write("frontend/src/lib/api/schema.d.ts está desatualizado. Execute npm run api:generate.\n");
    process.exit(1);
  }
} else {
  writeFileSync(outputPath, generated);
}
