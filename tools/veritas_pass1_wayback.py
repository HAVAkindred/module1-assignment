#!/usr/bin/env python3
"""Build Pass 1 with public-source and Wayback recovery.

Many legacy public Joint Staff/FAS PDF endpoints now sit behind access controls or
bot challenges. This builder uses archived captures of those same public files,
then applies the same structural and title validation before packaging.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

import requests

import veritas_pass1_download as base
import veritas_pass1_fast as fast

OUT = Path("PASS_01_Joint_Doctrine")
ZIP_PATH = Path("VERITAS_PASS_01_Joint_Doctrine.zip")


def wayback_candidates(url: str) -> list[str]:
    candidates: list[str] = []
    variants = [url]
    if url.startswith("https://"):
        variants.append("http://" + url[len("https://"):])
    elif url.startswith("http://"):
        variants.append("https://" + url[len("http://"):])

    for variant in variants:
        try:
            r = requests.get(
                "https://web.archive.org/cdx/search/cdx",
                params={
                    "url": variant,
                    "output": "json",
                    "fl": "timestamp,original,statuscode,mimetype,digest",
                    "filter": ["statuscode:200", "mimetype:application/pdf"],
                    "collapse": "digest",
                    "from": "2012",
                    "to": "2026",
                    "limit": "8",
                },
                timeout=35,
                headers={"User-Agent": base.SESSION.headers["User-Agent"]},
            )
            if r.status_code != 200:
                continue
            rows = r.json()
            if not isinstance(rows, list) or len(rows) < 2:
                continue
            # Prefer the newest captures first.
            for row in reversed(rows[1:]):
                if len(row) < 2:
                    continue
                ts, original = row[0], row[1]
                candidates.append(f"https://web.archive.org/web/{ts}id_/{original}")
        except (requests.RequestException, ValueError, IndexError, TypeError):
            continue
    # Preserve order and cap retries.
    return list(dict.fromkeys(candidates))[:10]


def public_url_variants(target: dict) -> list[str]:
    urls: list[str] = list(target.get("urls", []))
    for name in target.get("names", [])[:3]:
        if not name.lower().endswith(".pdf"):
            continue
        urls.extend(
            [
                f"https://www.jcs.mil/Portals/36/Documents/Doctrine/pubs/{quote(name)}",
                f"https://www.jcs.mil/Portals/36/Documents/Doctrine/pubs/{quote(name.lower())}",
                f"https://irp.fas.org/doddir/dod/{quote(name.lower())}",
            ]
        )
    return list(dict.fromkeys(urls))


def broader_archive_candidates(target: dict) -> list[str]:
    """Broader Internet Archive search using title, publication number, and filename."""
    queries = [target["title"]]
    queries.extend(target.get("names", [])[:3])
    # Publication designator from the requested filename is often indexed better.
    designator = target["filename"].split("_", 2)[:2]
    if designator:
        queries.append(" ".join(designator))

    urls: list[str] = []
    seen: set[str] = set()
    for query in queries:
        try:
            r = requests.get(
                "https://archive.org/advancedsearch.php",
                params={
                    "q": f'({query}) AND mediatype:texts',
                    "fl[]": "identifier,title",
                    "rows": 8,
                    "page": 1,
                    "output": "json",
                },
                timeout=30,
                headers={"User-Agent": base.SESSION.headers["User-Agent"]},
            )
            if r.status_code != 200:
                continue
            for doc in r.json().get("response", {}).get("docs", []):
                ident = doc.get("identifier")
                if not ident:
                    continue
                meta = requests.get(
                    f"https://archive.org/metadata/{quote(ident)}",
                    timeout=30,
                    headers={"User-Agent": base.SESSION.headers["User-Agent"]},
                )
                if meta.status_code != 200:
                    continue
                pdfs = [
                    f for f in meta.json().get("files", [])
                    if str(f.get("name", "")).lower().endswith(".pdf")
                ]
                pdfs.sort(key=lambda f: int(f.get("size", 0) or 0), reverse=True)
                for f in pdfs[:3]:
                    u = f"https://archive.org/download/{quote(ident)}/{quote(str(f['name']))}"
                    if u not in seen:
                        seen.add(u)
                        urls.append(u)
                if len(urls) >= 15:
                    return urls
        except (requests.RequestException, ValueError, KeyError):
            continue
    return urls[:15]


def attempt(target: dict, urls: list[str], label: str, hashes: dict[str, str]) -> dict | None:
    for url in urls:
        data = fast.download(url)
        if data is None:
            continue
        ok, reason, pages = fast.validate_pdf(data, target)
        if not ok:
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in hashes:
            continue
        path = OUT / target["filename"]
        path.write_bytes(data)
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
        public_urls = public_url_variants(target)
        result = attempt(target, public_urls, "public-direct", hashes)

        if result is None:
            wb: list[str] = []
            # Query archived captures only for the most plausible public endpoints.
            for url in public_urls[:8]:
                wb.extend(wayback_candidates(url))
                if len(wb) >= 20:
                    break
            result = attempt(target, list(dict.fromkeys(wb))[:20], "wayback-public-capture", hashes)

        if result is None:
            result = attempt(
                target,
                fast.github_fallback(target.get("names", [])),
                "github-public-mirror",
                hashes,
            )

        if result is None:
            result = attempt(
                target,
                broader_archive_candidates(target),
                "internet-archive-public-copy",
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
