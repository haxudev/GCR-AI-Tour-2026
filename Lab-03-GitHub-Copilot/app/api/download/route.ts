import * as fs from "node:fs/promises";

import { NextResponse } from "next/server";

import { resolveDownloadPath } from "@/lib/ppt-files";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const sessionId = searchParams.get("session")?.trim();
  const fileName = searchParams.get("file")?.trim();

  if (!sessionId) {
    return NextResponse.json({ error: "Missing session parameter." }, { status: 400 });
  }

  if (!fileName) {
    return NextResponse.json({ error: "Missing file parameter." }, { status: 400 });
  }

  let absolutePath: string;
  try {
    absolutePath = resolveDownloadPath(sessionId, fileName);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Invalid file path." },
      { status: 400 },
    );
  }

  try {
    const file = await fs.readFile(absolutePath);
    return new NextResponse(file, {
      status: 200,
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "Content-Disposition": `attachment; filename="${encodeURIComponent(fileName)}"`,
      },
    });
  } catch {
    return NextResponse.json({ error: "File not found." }, { status: 404 });
  }
}