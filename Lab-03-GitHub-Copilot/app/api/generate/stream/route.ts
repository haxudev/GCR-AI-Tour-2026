import { createSessionDir, extractReportedPptxName, snapshotPptxNames, waitForGeneratedPptx } from "@/lib/ppt-files";
import {
  CopilotInitializationError,
  runUrlToPptConversion,
  type CopilotStreamEvent,
} from "@/lib/copilot";
import { getPresentationStyle, MAX_PAGES, MIN_PAGES, parsePageCount } from "@/lib/styles";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function isValidHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function sseEvent(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function statusPayload(step: string, message: string) {
  return { step, message, timestamp: new Date().toISOString() };
}

function createSseResponse(body: BodyInit): Response {
  return new Response(body, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const url = searchParams.get("url")?.trim() ?? "";
  const styleId = searchParams.get("style")?.trim() ?? "";
  const pages = parsePageCount(searchParams.get("pages") ?? undefined);
  const style = getPresentationStyle(styleId);

  if (!url || !isValidHttpUrl(url)) {
    return createSseResponse(
      sseEvent("generation-error", { error: "Please provide a valid http or https URL." }),
    );
  }

  if (!style) {
    return createSseResponse(
      sseEvent("generation-error", { error: "Please choose one of the supported presentation styles." }),
    );
  }

  if (pages === null) {
    return createSseResponse(
      sseEvent("generation-error", { error: `Please provide a page count between ${MIN_PAGES} and ${MAX_PAGES}.` }),
    );
  }

  const encoder = new TextEncoder();
  const sessionDirPromise = createSessionDir();
  const startedAtMs = Date.now();

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      let closed = false;

      const write = (event: string, data: unknown) => {
        if (closed) {
          return;
        }

        controller.enqueue(encoder.encode(sseEvent(event, data)));
      };

      const close = () => {
        if (closed) {
          return;
        }

        closed = true;
        controller.close();
      };

      const abortHandler = () => {
        write("abort", statusPayload("aborted", "Client disconnected."));
        close();
      };

      request.signal.addEventListener("abort", abortHandler, { once: true });

      void (async () => {
        write("status", statusPayload("starting", "Copilot session is starting."));

        try {
          const { sessionId, sessionDir } = await sessionDirPromise;
          const previousNames = await snapshotPptxNames(sessionDir);
          const result = await runUrlToPptConversion(
            { url, style: style.label, pages, sessionDir },
            {
              onEvent: (event: CopilotStreamEvent) => {
                write("sdk-event", {
                  ...event,
                  timestamp: new Date().toISOString(),
                });
              },
            },
          );

          const reportedFileName = extractReportedPptxName(result.replyText);
          const file = await waitForGeneratedPptx({
            sessionDir,
            previousNames,
            startedAtMs,
            reportedFileName,
          });

          if (!file) {
            write("generation-error", {
              error:
                "Copilot SDK completed, but no PPTX file could be confirmed in the session directory after waiting for it to finish writing. Check the server logs for the session transcript.",
              replyText: result.replyText,
              eventLog: result.eventLog,
            });
            return;
          }

          write("result", {
            fileName: file.name,
            downloadPath: `/api/download?session=${encodeURIComponent(sessionId)}&file=${encodeURIComponent(file.name)}`,
            replyText: result.replyText,
            eventLog: result.eventLog,
          });
          write("complete", statusPayload("complete", "Presentation generation finished."));
        } catch (error) {
          if (error instanceof CopilotInitializationError) {
            write("status", statusPayload("authentication-error", error.userMessage));
          }

          write("generation-error", {
            error:
              error instanceof CopilotInitializationError
                ? error.userMessage
                : error instanceof Error
                  ? error.message
                  : "Unexpected generation failure.",
          });
        } finally {
          request.signal.removeEventListener("abort", abortHandler);
          close();
        }
      })();
    },
  });

  return createSseResponse(stream);
}