#!/usr/bin/env python3
"""Fast, sequential VERITAS Pass 1 corpus builder.

Direct official/public URLs are tried before narrowly scoped fallbacks. The emitted
ZIP contains one flat folder of validated PDFs and nothing else.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

import requests
from pypdf import PdfReader

import veritas_pass1_download as base

OUT = Path("PASS_01_Joint_Doctrine")
ZIP_PATH = Path("VERITAS_PASS_01_Joint_Doctrine.zip")
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def validate_pdf(data: bytes, target: dict) -> tuple[bool, str, int]:
    if not data.lstrip().startswith(b"%PDF") or len(data) < 20_000:
        return False, "not a substantive PDF", 0
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        pages = len(reader.pages)
        if pages < 3:
            return False, f"only {pages} pages", pages
        chunks: list[str] = []
        for page in reader.pages[: min(15, pages)]:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                pass
        text = norm(" ".join(chunks))
        phrases: list[str] = []
        for phrase in target.get("expected", []):
            p = norm(phrase)
            if p:
                phrases.append(p)
                phrases.append(p.replace("jp ", "joint publication ", 1))
                phrases.append(p.replace("fm ", "field manual ", 1))
                phrases.append(p.replace("adp ", "army doctrine publication ", 1))
        distinctive = [p for p in phrases if len(p) >= 8]
        if text and not any(p in text for p in distinctive):
            return False, "publication identity mismatch", pages
        return True, "validated", pages
    except Exception as exc:
        return False, f"PDF parse failure: {exc}", 0


def download(url: str) -> bytes | None:
    for attempt in range(2):
        try:
            r = base.SESSION.get(url, timeout=35, allow_redirects=True)
            if r.status_code == 200 and r.content.lstrip().startswith(b"%PDF"):
                return r.content
            if r.status_code in {401, 403, 429, 500, 502, 503, 504}:
                time.sleep(1 + attempt)
        except requests.RequestException:
            time.sleep(1 + attempt)
    return None


def github_fallback(names: list[str]) -> list[str]:
    if not TOKEN or not names:
        return []
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    found: list[str] = []
    seen: set[str] = set()
    for name in names[:2]:
        try:
            r = requests.get(
                "https://api.github.com/search/code",
                params={"q": f"filename:{name}", "per_page": 10},
                headers=headers,
                timeout=25,
            )
            if r.status_code != 200:
                continue
            for item in r.json().get("items", []):
                repo = item.get("repository", {}).get("full_name")
                path = item.get("path")
                if not repo or not path or not path.lower().endswith(".pdf"):
                    continue
                api = f"https://api.github.com/repos/{repo}/contents/{quote(path)}"
                rr = requests.get(api, headers=headers, timeout=20)
                if rr.status_code == 200:
                    url = rr.json().get("download_url")
                    if url and url not in seen:
                        seen.add(url)
                        found.append(url)
        except requests.RequestException:
            continue
    return found[:12]


def archive_fallback(title: str) -> list[str]:
    try:
        r = requests.get(
            "https://archive.org/advancedsearch.php",
            params={
                "q": f'title:"{title}" AND mediatype:texts',
                "fl[]": "identifier,title",
                "rows": 4,
                "page": 1,
                "output": "json",
            },
            timeout=25,
            headers={"User-Agent": base.SESSION.headers["User-Agent"]},
        )
        if r.status_code != 200:
            return []
        urls: list[str] = []
        for doc in r.json().get("response", {}).get("docs", []):
            ident = doc.get("identifier")
            if not ident:
                continue
            meta = requests.get(
                f"https://archive.org/metadata/{quote(ident)}",
                timeout=25,
                headers={"User-Agent": base.SESSION.headers["User-Agent"]},
            )
            if meta.status_code != 200:
                continue
            pdfs = [
                f for f in meta.json().get("files", [])
                if str(f.get("name", "")).lower().endswith(".pdf")
            ]
            pdfs.sort(key=lambda f: int(f.get("size", 0) or 0), reverse=True)
            for f in pdfs[:2]:
                urls.append(
                    f"https://archive.org/download/{quote(ident)}/{quote(str(f['name']))}"
                )
        return urls[:8]
    except (requests.RequestException, ValueError, KeyError):
        return []


def try_urls(target: dict, urls: list[str], label: str, hashes: dict[str, str]) -> dict | None:
    for url in urls:
        data = download(url)
        if data is None:
            continue
        ok, reason, pages = validate_pdf(data, target)
        if not ok:
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in hashes:
            continue
        out = OUT / target["filename"]
        out.write_bytes(data)
        hashes[digest] = target["filename"]
        result = {
            "filename": target["filename"],
            "title": target["title"],
            "url": url,
            "source_path": label,
            "sha256": digest,
            "pages": pages,
            "bytes": len(data),
        }
        print(
            f"PASS1_RESULT\tSUCCESS\t{target['filename']}\t{pages} pages\t{len(data)} bytes\t{label}\t{url}",
            flush=True,
        )
        return result
    return None


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    ZIP_PATH.unlink(missing_ok=True)

    successes: list[dict] = []
    failures: list[dict] = []
    hashes: dict[str, str] = {}

    for i, target in enumerate(base.TARGETS, 1):
        print(f"\n[{i:02d}/{len(base.TARGETS):02d}] {target['title']}", flush=True)
        result = try_urls(target, target.get("urls", []), "direct", hashes)
        if result is None:
            result = try_urls(
                target,
                github_fallback(target.get("names", [])),
                "github-fallback",
                hashes,
            )
        if result is None:
            result = try_urls(
                target,
                archive_fallback(target["title"]),
                "archive-fallback",
                hashes,
            )
        if result:
            successes.append(result)
        else:
            failure = {
                "filename": target["filename"],
                "title": target["title"],
                "official_or_access_url": (target.get("urls") or [""])[0],
            }
            failures.append(failure)
            print(
                f"PASS1_RESULT\tINCOMPLETE\t{target['filename']}\t{failure['official_or_access_url']}",
                flush=True,
            )

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for pdf in sorted(OUT.glob("*.pdf"), key=lambda p: p.name.lower()):
            zf.write(pdf, arcname=f"{OUT.name}/{pdf.name}")

    summary = {
        "requested": len(base.TARGETS),
        "downloaded": len(successes),
        "incomplete": failures,
        "zip_bytes": ZIP_PATH.stat().st_size,
    }
    print("PASS1_SUMMARY_JSON=" + json.dumps(summary, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
