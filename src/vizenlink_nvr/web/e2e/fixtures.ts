import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const E2E_OWNER = {
  username: "e2e-owner",
  password: "e2e-password-123",
  confirmPassword: "e2e-password-123",
};

export function absRecordingsDir(name: string): string {
  return path.resolve(__dirname, "..", ".e2e", name, "recordings");
}
