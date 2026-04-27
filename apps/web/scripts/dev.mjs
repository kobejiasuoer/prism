#!/usr/bin/env node

import { execFileSync, spawn } from "node:child_process";
import { dirname, join } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const appRoot = dirname(scriptDir);
const nextBin = join(appRoot, "node_modules", ".bin", "next");
const nextBinToken = `${appRoot}/node_modules/.bin/next`;

function readProcessLines() {
  if (process.platform === "win32") {
    return [];
  }

  try {
    const output = execFileSync("ps", ["-axo", "pid=,command="], {
      cwd: appRoot,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    });
    return output
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

function inferPort(command) {
  const longMatch = command.match(/--port\s+(\d{2,5})/);
  if (longMatch) {
    return longMatch[1];
  }
  const shortMatch = command.match(/(?:^|\s)-p\s+(\d{2,5})(?:\s|$)/);
  return shortMatch?.[1] ?? "";
}

function findConflictingDevServers() {
  return readProcessLines()
    .map((line) => {
      const match = line.match(/^(\d+)\s+(.*)$/);
      if (!match) {
        return null;
      }
      const pid = Number(match[1]);
      const command = match[2];
      return { pid, command };
    })
    .filter((item) => item && item.pid !== process.pid)
    .filter((item) => item.command.includes(nextBinToken) && /\bdev\b/.test(item.command));
}

const conflicts = findConflictingDevServers();

if (conflicts.length) {
  const details = conflicts
    .map((item) => {
      const port = inferPort(item.command);
      return `pid=${item.pid}${port ? ` port=${port}` : ""}`;
    })
    .join(", ");

  console.error("[prism:web] Another Next dev server for this apps/web workspace is already running.");
  console.error(`[prism:web] Conflict: ${details}`);
  console.error("[prism:web] Stop the existing dev server first, then retry this command.");
  process.exit(1);
}

const child = spawn(nextBin, ["dev", ...process.argv.slice(2)], {
  cwd: appRoot,
  env: process.env,
  stdio: "inherit",
});

function forwardSignal(signal) {
  if (!child.killed) {
    child.kill(signal);
  }
}

process.on("SIGINT", () => forwardSignal("SIGINT"));
process.on("SIGTERM", () => forwardSignal("SIGTERM"));

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
