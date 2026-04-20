import * as crypto from "node:crypto";
import * as fs from "node:fs/promises";
import * as path from "node:path";

export const OUTPUT_DIR = path.join(process.cwd(), "output");
const FILE_APPEAR_TIMEOUT_MS = 30_000;
const FILE_APPEAR_POLL_INTERVAL_MS = 5_000;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function createSessionDir(): Promise<{ sessionId: string; sessionDir: string }> {
  const sessionId = crypto.randomUUID();
  const sessionDir = path.join(OUTPUT_DIR, sessionId);
  await fs.mkdir(sessionDir, { recursive: true });
  return { sessionId, sessionDir };
}

export function resolveSessionDir(sessionId: string): string {
  if (!UUID_RE.test(sessionId)) {
    throw new Error("Invalid session ID.");
  }
  return path.join(OUTPUT_DIR, sessionId);
}

interface PptxFileInfo {
  name: string;
  absolutePath: string;
  modifiedMs: number;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function statPptxFile(absolutePath: string): Promise<PptxFileInfo | null> {
  try {
    const stats = await fs.stat(absolutePath);
    if (!stats.isFile() || !absolutePath.toLowerCase().endsWith(".pptx")) {
      return null;
    }

    return {
      name: path.basename(absolutePath),
      absolutePath,
      modifiedMs: stats.mtimeMs,
    } satisfies PptxFileInfo;
  } catch {
    return null;
  }
}

async function readPptxFiles(dir: string): Promise<PptxFileInfo[]> {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = await Promise.all(
    entries
      .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".pptx"))
      .map(async (entry) => {
        const absolutePath = path.join(dir, entry.name);
        const stats = await fs.stat(absolutePath);
        return {
          name: entry.name,
          absolutePath,
          modifiedMs: stats.mtimeMs,
        } satisfies PptxFileInfo;
      }),
  );

  return files.sort((left, right) => right.modifiedMs - left.modifiedMs);
}

export async function snapshotPptxNames(sessionDir: string): Promise<Set<string>> {
  try {
    return new Set((await readPptxFiles(sessionDir)).map((file) => file.name));
  } catch {
    return new Set();
  }
}

export async function findGeneratedPptx(options: {
  sessionDir: string;
  previousNames: Set<string>;
  startedAtMs: number;
}): Promise<PptxFileInfo | null> {
  const files = await readPptxFiles(options.sessionDir);

  const createdAfterStart = files.find(
    (file) => !options.previousNames.has(file.name) && file.modifiedMs >= options.startedAtMs - 2_000,
  );
  if (createdAfterStart) {
    return createdAfterStart;
  }

  const updatedAfterStart = files.find((file) => file.modifiedMs >= options.startedAtMs - 2_000);
  return updatedAfterStart ?? null;
}

export function extractReportedPptxName(replyText: string): string | null {
  const normalizedText = replyText.replace(/\\/g, "/");
  const pathMatch = normalizedText.match(/(?:^|[\s"'`(])(?:\.\/)?output\/([^\s"'`)]*?\.pptx)(?=$|[\s"'`)])/i);

  if (pathMatch?.[1]) {
    return path.basename(pathMatch[1]);
  }

  const fileNameMatch = normalizedText.match(/([\w.-]+\.pptx)/i);
  return fileNameMatch?.[1] ? path.basename(fileNameMatch[1]) : null;
}

export async function waitForGeneratedPptx(options: {
  sessionDir: string;
  previousNames: Set<string>;
  startedAtMs: number;
  reportedFileName?: string | null;
  timeoutMs?: number;
  pollIntervalMs?: number;
}): Promise<PptxFileInfo | null> {
  const timeoutMs = options.timeoutMs ?? FILE_APPEAR_TIMEOUT_MS;
  const pollIntervalMs = options.pollIntervalMs ?? FILE_APPEAR_POLL_INTERVAL_MS;
  const deadline = Date.now() + timeoutMs;

  do {
    if (options.reportedFileName) {
      const reportedFile = await statPptxFile(path.join(options.sessionDir, path.basename(options.reportedFileName)));
      if (reportedFile) {
        return reportedFile;
      }
    }

    const discoveredFile = await findGeneratedPptx({
      sessionDir: options.sessionDir,
      previousNames: options.previousNames,
      startedAtMs: options.startedAtMs,
    });
    if (discoveredFile) {
      return discoveredFile;
    }

    if (Date.now() >= deadline) {
      break;
    }

    await delay(pollIntervalMs);
  } while (true);

  return null;
}

export function resolveDownloadPath(sessionId: string, fileName: string): string {
  const sessionDir = resolveSessionDir(sessionId);
  const safeName = path.basename(fileName);
  if (!safeName.toLowerCase().endsWith(".pptx")) {
    throw new Error("Only .pptx files can be downloaded.");
  }

  const absolutePath = path.join(sessionDir, safeName);
  const normalizedSessionDir = path.resolve(sessionDir);
  const normalizedFilePath = path.resolve(absolutePath);

  if (!normalizedFilePath.startsWith(normalizedSessionDir + path.sep) && normalizedFilePath !== normalizedSessionDir) {
    throw new Error("Invalid file path.");
  }

  return normalizedFilePath;
}