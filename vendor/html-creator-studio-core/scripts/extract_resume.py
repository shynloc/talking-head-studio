#!/usr/bin/env python3
"""Offline, evidence-preserving resume text extraction for txt/md/docx/pdf.

This is deliberately NOT an AI CV parser: it records original source text and
locators for a human/agent to turn into reviewed RESUME-CONTENT.json. No upload.
PDF extraction requires an existing `pdftotext` command (Poppler).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

SUPPORTED = {".txt", ".md", ".docx", ".pdf"}
MAX_BYTES = 30 * 1024 * 1024
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _records(text: str, *, prefix: str, page: int | None = None) -> list[dict]:
    evidence = []
    for index, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if line:
            location = f"{prefix}:line:{index}" if page is None else f"pdf:page:{page}:line:{index}"
            evidence.append({"source_locator": location, "text": line})
    return evidence


def extract(path: pathlib.Path) -> dict:
    source = path.resolve()
    if not source.is_file():
        raise ValueError("Input is not a readable file")
    extension = source.suffix.lower()
    if extension not in SUPPORTED:
        raise ValueError(f"Unsupported resume type: {extension}")
    size = source.stat().st_size
    if size == 0 or size > MAX_BYTES:
        raise ValueError("Input is empty or exceeds 30 MiB safe extraction limit")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if extension in {".txt", ".md"}:
        evidence = _records(source.read_text(encoding="utf-8-sig"), prefix=extension.lstrip("."))
    elif extension == ".docx":
        with zipfile.ZipFile(source) as zf:
            info = zf.getinfo("word/document.xml")
            if info.file_size > MAX_BYTES:
                raise ValueError("DOCX document XML exceeds safe extraction limit")
            root = ET.fromstring(zf.read(info))
        evidence = []
        # Paragraphs embedded in table cells are included; their document order
        # is kept. This does not claim to preserve visual column positions.
        for index, para in enumerate(root.iter(WORD + "p"), start=1):
            text = "".join(element.text or "" for element in para.iter(WORD + "t")).strip()
            if text:
                evidence.append({"source_locator": f"docx:paragraph:{index}", "text": text})
    else:
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", "-enc", "UTF-8", str(source), "-"],
                capture_output=True, text=True, timeout=45, check=False,
            )
        except FileNotFoundError as exc:
            raise ValueError("PDF extraction needs local Poppler pdftotext") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError("PDF extraction exceeded 45 seconds") from exc
        if result.returncode != 0:
            raise ValueError("pdftotext failed; encrypted/scanned PDF may require consented OCR")
        evidence = []
        for page_number, page_text in enumerate(result.stdout.split("\f"), start=1):
            evidence.extend(_records(page_text, prefix="pdf", page=page_number))
    if not evidence:
        raise ValueError("No extractable text; scanned images require a separate OCR step")
    return {
        "schema_version": "1.8", "artifact_kind": "private_resume_evidence",
        "source_name": source.name, "source_type": extension.lstrip("."),
        "source_sha256": digest, "line_count": len(evidence),
        "review_state": "pending_human_fact_and_privacy_review",
        "public_sharing": "forbidden_without_explicit_user_review",
        "notes": [
            "Private source text only. Never publish or send this file to a third party automatically.",
            "PDF reading order and DOCX complex layout are not guaranteed; verify against the original.",
            "Do not invent employment dates, quantified achievements, links or contact permission.",
        ],
        "evidence": [{"id": f"R{index:04d}", **item} for index, item in enumerate(evidence, start=1)],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    try:
        source = pathlib.Path(args.input).resolve()
        dest = pathlib.Path(args.out).resolve()
        if dest.exists() or dest == source:
            raise ValueError("Refusing to overwrite an existing file or original resume")
        data = extract(source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError, UnicodeError, zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "PASS", "line_count": data["line_count"],
                      "result": str(dest), "privacy": "LOCAL_PRIVATE_REVIEW_REQUIRED"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
