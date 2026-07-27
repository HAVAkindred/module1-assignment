#!/usr/bin/env python3
"""VERITAS Pass 1 builder using the Wayback availability API.

The availability endpoint resolves one nearest capture per formerly public URL,
avoiding broad CDX scans. Every downloaded file is parsed and title-checked before
entry into the single flat PDF folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from urllib.parse import quote

import requests
import veritas_pass1_download as base
import veritas_pass1_fast as fast

OUT = Path("PASS_01_Joint_Doctrine")
ZIP_PATH = Path("VERITAS_PASS_01_Joint_Doctrine.zip")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

SPECIAL = {
    "JP_2-0_Joint_Intelligence_Public_Edition.pdf": [
        "https://raw.githubusercontent.com/hslatman/awesome-threat-intelligence/main/docs/jp2_0.pdf"
    ],
    "JP_3-60_Joint_Targeting_Public_Edition.pdf": [
        "https://documents2.theblackvault.com/documents/osd/19-F-1399.pdf"
    ],
}


def get_pdf(url: str, timeout: int = 30) -> bytes | None:
    try:
        r = base.SESSION.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and r.content.lstrip().startswith(b"%PDF") and len(r.content) > 20000:
            return r.content
    except requests.RequestException:
        return None
    return None


def source_urls(target: dict) -> list[str]:
    urls = list(target.get("urls", [])) + SPECIAL.get(target["filename"], [])
    for name in target.get("names", [])[:4]:
        if not name.lower().endswith(".pdf"):
            continue
        urls.extend([
            f"https://www.jcs.mil/Portals/36/Documents/Doctrine/pubs/{quote(name)}",
            f"https://www.jcs.mil/Portals/36/Documents/Doctrine/pubs/{quote(name.lower())}",
            f"https://irp.fas.org/doddir/dod/{quote(name.lower())}",
            f"https://jdeis.js.mil/jdeis/new_pubs/{quote(name.lower())}",
        ])
    return list(dict.fromkeys(urls))


def archived_url(original: str, stamp: str) -> str | None:
    variants = [original]
    if original.startswith("https://"):
        variants.append("http://" + original[8:])
    elif original.startswith("http://"):
        variants.append("https://" + original[7:])
    for url in variants:
        try:
            r = requests.get(
                "https://archive.org/wayback/available",
                params={"url": url, "timestamp": stamp},
                timeout=18,
                headers={"User-Agent": base.SESSION.headers["User-Agent"]},
            )
            if r.status_code != 200:
                continue
            snap = r.json().get("archived_snapshots", {}).get("closest", {})
            if snap.get("available") and snap.get("status") == "200" and snap.get("url"):
                replay = snap["url"]
                # id_ suppresses Wayback toolbar rewriting and returns original bytes.
                if "/web/" in replay and "id_/" not in replay:
                    left, right = replay.split("/web/", 1)
                    ts, original_part = right.split("/", 1)
                    replay = f"{left}/web/{ts}id_/{original_part}"
                return replay
        except (requests.RequestException, ValueError, KeyError):
            continue
    return None


def github_urls(names: list[str]) -> list[str]:
    if not TOKEN:
        return []
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}
    found, seen = [], set()
    for name in names[:3]:
        try:
            r = requests.get("https://api.github.com/search/code", params={"q": f"filename:{name}", "per_page": 15}, headers=headers, timeout=20)
            if r.status_code != 200:
                continue
            for item in r.json().get("items", []):
                repo = item.get("repository", {}).get("full_name")
                path = item.get("path")
                if not repo or not path or not path.lower().endswith(".pdf"):
                    continue
                rr = requests.get(f"https://api.github.com/repos/{repo}/contents/{quote(path)}", headers=headers, timeout=15)
                if rr.status_code == 200:
                    u = rr.json().get("download_url")
                    if u and u not in seen:
                        seen.add(u); found.append(u)
        except requests.RequestException:
            continue
    return found[:20]


def accept(target: dict, data: bytes, url: str, label: str, hashes: dict[str, str]) -> dict | None:
    ok, reason, pages = fast.validate_pdf(data, target)
    if not ok:
        print(f"REJECT\t{target['filename']}\t{label}\t{reason}\t{url}", flush=True)
        return None
    digest = hashlib.sha256(data).hexdigest()
    if digest in hashes:
        return None
    (OUT / target["filename"]).write_bytes(data)
    hashes[digest] = target["filename"]
    print(f"PASS1_RESULT\tSUCCESS\t{target['filename']}\t{pages}\t{len(data)}\t{label}\t{url}", flush=True)
    return {"filename": target["filename"], "url": url, "pages": pages, "sha256": digest}


def main() -> int:
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    ZIP_PATH.unlink(missing_ok=True)
    hashes, successes, failures = {}, [], []
    stamps = ["20260101", "20250101", "20240101", "20220101", "20200101", "20180101", "20160101"]

    for i, target in enumerate(base.TARGETS, 1):
        print(f"[{i:02d}/{len(base.TARGETS):02d}] {target['title']}", flush=True)
        result = None
        originals = source_urls(target)
        for url in originals:
            data = get_pdf(url, 24)
            if data:
                result = accept(target, data, url, "public-direct", hashes)
                if result: break
        if not result:
            for original in originals[:10]:
                for stamp in stamps:
                    replay = archived_url(original, stamp)
                    if not replay:
                        continue
                    data = get_pdf(replay, 35)
                    if data:
                        result = accept(target, data, replay, "wayback-available", hashes)
                        if result: break
                if result: break
        if not result:
            for url in github_urls(target.get("names", [])):
                data = get_pdf(url, 30)
                if data:
                    result = accept(target, data, url, "github-public-mirror", hashes)
                    if result: break
        if result:
            successes.append(result)
        else:
            failure = {"filename": target["filename"], "title": target["title"], "url": (target.get("urls") or [""])[0]}
            failures.append(failure)
            print(f"PASS1_RESULT\tINCOMPLETE\t{target['filename']}\t{failure['url']}", flush=True)

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(OUT.glob("*.pdf"), key=lambda p: p.name.lower()):
            zf.write(p, arcname=f"{OUT.name}/{p.name}")
    print("PASS1_SUMMARY_JSON=" + json.dumps({"requested": len(base.TARGETS), "downloaded": len(successes), "incomplete": failures, "zip_bytes": ZIP_PATH.stat().st_size}, separators=(",", ":")), flush=True)
    return 0

if __name__ == "__main__": raise SystemExit(main())
