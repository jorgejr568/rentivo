import { render } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { ApiError } from "../../lib/api/client";
import {
  errorMessage, firstFieldError, formatDateTime, formatFileSize, multipartBodySerializer,
  normalizedFieldErrors, parseDateInput, useDocumentTitle
} from "./billSupport";

afterEach(() => {
  document.title = "";
});
it("normalizes API errors while retaining safe fallbacks", () => {
  const error = new ApiError(new Response(null, { status: 422 }), {
    code: "validation_error",
    detail: "Confira os campos.",
    fields: { "body.subject": "Obrigatório.", plain: "Inválido." }
  });
  expect(errorMessage(error, "fallback")).toBe("Confira os campos.");
  expect(errorMessage(new Error("offline"), "fallback")).toBe("fallback");
  expect(normalizedFieldErrors(error)).toEqual({ plain: "Inválido.", subject: "Obrigatório." });
  expect(normalizedFieldErrors(new Error("offline"))).toEqual({});
  expect(firstFieldError({ body: "x", subject: "x" }, ["subject"])).toBe("subject");
  expect(firstFieldError({ body: "x" }, ["subject"])).toBe("body");
  expect(firstFieldError({}, ["subject"])).toBeUndefined();
});

it("parses blank, Brazilian, ISO, malformed, and impossible dates", () => {
  expect(parseDateInput(" ")).toBeNull();
  expect(parseDateInput("10/08/2026")).toBe("2026-08-10");
  expect(parseDateInput("2026-08-10")).toBe("2026-08-10");
  expect(parseDateInput("10.08.2026")).toBeUndefined();
  expect(parseDateInput("31/02/2026")).toBeUndefined();
});

it("serializes all multipart value shapes and formats files and timestamps", () => {
  expect(Array.from((multipartBodySerializer(null) as FormData).entries())).toEqual([]);
  expect(Array.from((multipartBodySerializer("text") as FormData).entries())).toEqual([]);
  const file = new File(["pdf"], "a.pdf", { type: "application/pdf" });
  const form = multipartBodySerializer({ files: [file, "tail"], ignored: undefined, nil: null, payload: "{}" }) as FormData;
  expect(form.getAll("files")).toEqual([file, "tail"]);
  expect(form.get("payload")).toBe("{}");
  expect(form.has("ignored")).toBe(false);
  expect(formatFileSize(1536)).toBe("1.5 KB");
  expect(formatDateTime(null)).toBe("—");
  expect(formatDateTime("not-a-date")).toBe("not-a-date");
  expect(formatDateTime("2026-07-18T10:00:00Z")).toMatch(/18\/07\/2026/);
});

function TitleProbe({ title }: { title: string }) {
  useDocumentTitle(title);
  return null;
}

it("updates and restores the page title across rerenders", () => {
  document.title = "Anterior";
  const view = render(<TitleProbe title="Primeiro" />);
  expect(document.title).toBe("Primeiro");
  view.rerender(<TitleProbe title="Segundo" />);
  expect(document.title).toBe("Segundo");
  view.unmount();
  expect(document.title).toBe("Anterior");
});
