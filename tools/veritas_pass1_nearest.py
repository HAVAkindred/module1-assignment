#!/usr/bin/env python3
"""Fast public-source and nearest-Wayback recovery for VERITAS Pass 1."""
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
TOKEN = os.environ.get("GITHUB_TOKEN", "")

SPECIAL = {
    "JP_2-0_Joint_Intelligence_Public_Edition.pdf": [
        "https://raw.githubusercontent.com/hslatman/awesome-threat-intelligence/main/docs/jp2_0.pdf"
    ],
}


def download(url: str) -> bytes | None:
    try:
        r = base.SESSION.get(url, timeout=24, allow_redirects=True)
        if r.status_code == 200 and r.content.lstrip().startswith(b"%PDF"):
            return r.content
    except requests.RequestException:
        pass
    return None


def public_variants(target: dict) -> list[str]:
    urls = list(target.get("urls", [])) + SPECIAL.get(target["filename"], [])
    for name in target.get("names", [])[:3]:
        if name.lower().endswith(".pdf"):
            urls.extend([
                f"https://www.jcs.mil/Portals/36/Documents/Doctrine/pubs/{quote(name)}",
                f"https://www.jcs.mil/Portals/36/Documents/Doctrine/pubs/{quote(name.lower())}",
                f"https://irp.fas.org/doddir/dod/{quote(name.lower())}",
            ])
    return list(dict.fromkeys(urls))


def nearest(url: str) -> list[str]:
    # The Wayback replay service selects the nearest available capture to each timestamp.
    years = ["20260101000000", "20250101000000", "20240101000000", "20220101000000", "20200101000000", "20180101000000"]
    variants = [url]
    if url.startswith("https://"):
        variants.append("http://" + url[8:])
    elif url.startswith("http://"):
        variants.append("https://" + url[7:])
    return [f"https://web.archive.org/web/{stamp}id_/{u}" for u in variants for stamp in years]


def github_candidates(names: list[str]) -> list[str]:
    if not TOKEN:
        return []
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}
    urls: list[str] = []
    seen: set[str] = set()
    for name in names[:3]:
        try:
            r = requests.get("https://api.github.com/search/code", params={"q": f"filename:{name}", "per_page": 20}, headers=headers, timeout=20)
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
                        seen.add(u); urls.append(u)
        except requests.RequestException:
            continue
    return urls[:20]


def save(target: dict, urls: list[str], label: str, hashes: dict[str, str]) -> dict | None:
    for url in urls:
        data = download(url)
        if data is None:
            continue
        ok, _, pages = fast.validate_pdf(data, target)
        if not ok:
            continue
        digest = hashlib.sha256(data).hexdigest()
        if digest in hashes:
            continue
        (OUT / target["filename"]).write_bytes(data)
        hashes[digest] = target["filename"]
        print(f"PASS1_RESULT\tSUCCESS\t{target['filename']}\t{pages}\t{len(data)}\t{label}\t{url}", flush=True)
        return {"filename": target["filename"], "url": url, "pages": pages, "sha256": digest}
    return None


def main() -> int:
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    ZIP_PATH.unlink(missing_ok=True)
    hashes: dict[str, str] = {}
    successes, failures = [], []
    for i, target in enumerate(base.TARGETS, 1):
        print(f"[{i:02d}/{len(base.TARGETS):02d}] {target['title']}", flush=True)
        direct = public_variants(target)
        result = save(target, direct, "public-direct", hashes)
        if result is None:
            wb = []
            for u in direct[:7]: wb.extend(nearest(u))
            result = save(target, wb[:84], "nearest-wayback", hashes)
        if result is None:
            result = save(target, github_candidates(target.get("names", [])), "github-public-mirror", hashes)
        if result: successes.append(result)
        else:
            failures.append({"filename": target["filename"], "title": target["title"], "url": (target.get("urls") or [""])[0]})
            print(f"PASS1_RESULT\tINCOMPLETE\t{target['filename']}", flush=True)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in sorted(OUT.glob("*.pdf"), key=lambda x: x.name.lower()):
            zf.write(p, arcname=f"{OUT.name}/{p.name}")
    print("PASS1_SUMMARY_JSON=" + json.dumps({"requested": len(base.TARGETS), "downloaded": len(successes), "incomplete": failures, "zip_bytes": ZIP_PATH.stat().st_size}, separators=(",", ":")), flush=True)
    return 0

if __name__ == "__main__": raise SystemExit(main())
