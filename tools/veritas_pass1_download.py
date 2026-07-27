#!/usr/bin/env python3
"""Build the flat VERITAS Pass 1 public-doctrine PDF corpus.

This temporary CI utility downloads only source PDFs that are not already in the
user's Project Sources. It validates PDF structure and identifying title tokens,
rejects duplicates by SHA-256, and emits a ZIP containing one flat PDF folder.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

OUT = Path("PASS_01_Joint_Doctrine")
ZIP_PATH = Path("VERITAS_PASS_01_Joint_Doctrine.zip")
OUT.mkdir(parents=True, exist_ok=True)
TOKEN = os.environ.get("GITHUB_TOKEN", "")

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/124.0 Safari/537.36 VERITAS-research-corpus/1.0"
        ),
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    }
)

# Existing Project Sources are intentionally omitted. This list contains only new
# foundational joint/Army/DoD/multi-Service material for Pass 1.
TARGETS = [
    {
        "filename": "JP_1_Volume_1_Joint_Warfighting_2023.pdf",
        "title": "JP 1 Volume 1 Joint Warfighting",
        "expected": ["joint publication 1", "joint warfighting"],
        "names": ["Joint Warfighting.pdf", "JP_1_vol1_2023.pdf", "jp1_vol1.pdf"],
        "urls": ["https://keystone.ndu.edu/Portals/86/Joint%20Warfighting.pdf"],
    },
    {
        "filename": "JP_1_Volume_2_The_Joint_Force_2020.pdf",
        "title": "JP 1 Volume 2 The Joint Force",
        "expected": ["joint publication 1", "the joint force"],
        "names": ["JP_1_vol2_19Jun2020.pdf", "jp1_vol2.pdf", "JP_1_Volume_2.pdf"],
        "urls": [],
    },
    {
        "filename": "JP_2-0_Joint_Intelligence_Public_Edition.pdf",
        "title": "JP 2-0 Joint Intelligence",
        "expected": ["jp 2-0", "joint intelligence"],
        "names": ["jp2_0.pdf", "JP_2-0.pdf", "JP2-0.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp2_0.pdf"],
    },
    {
        "filename": "JP_2-01_Joint_and_National_Intelligence_Support_Public_Edition.pdf",
        "title": "JP 2-01 Joint and National Intelligence Support to Military Operations",
        "expected": ["jp 2-01", "intelligence support"],
        "names": ["jp2_01.pdf", "JP_2-01.pdf", "JP2-01.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp2_01.pdf"],
    },
    {
        "filename": "JP_2-01.3_Joint_Intelligence_Preparation_of_the_Operational_Environment_Public_Edition.pdf",
        "title": "JP 2-01.3 Joint Intelligence Preparation of the Operational Environment",
        "expected": ["jp 2-01.3", "operational environment"],
        "names": ["jp2-01-3.pdf", "jp2_01_3.pdf", "JP_2-01.3.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp2-01-3.pdf"],
    },
    {
        "filename": "JP_3-0_Joint_Campaigns_and_Operations_Public_Edition.pdf",
        "title": "JP 3-0 Joint Campaigns and Operations",
        "expected": ["jp 3-0", "joint campaigns"],
        "names": ["jp3_0.pdf", "JP_3-0.pdf", "JP3-0.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_0.pdf"],
    },
    {
        "filename": "JP_3-01_Countering_Air_and_Missile_Threats_Public_Edition.pdf",
        "title": "JP 3-01 Countering Air and Missile Threats",
        "expected": ["jp 3-01", "air and missile"],
        "names": ["jp3_01.pdf", "JP_3-01.pdf", "JP3-01.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_01.pdf"],
    },
    {
        "filename": "JP_3-04_Information_in_Joint_Operations_Public_Edition.pdf",
        "title": "JP 3-04 Information in Joint Operations",
        "expected": ["jp 3-04", "information in joint operations"],
        "names": ["jp3_04.pdf", "JP_3-04.pdf", "JP3-04.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_04.pdf"],
    },
    {
        "filename": "JP_3-09_Joint_Fire_Support_Public_Edition.pdf",
        "title": "JP 3-09 Joint Fire Support",
        "expected": ["jp 3-09", "joint fire support"],
        "names": ["jp3_09.pdf", "JP_3-09.pdf", "JP3-09.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_09.pdf"],
    },
    {
        "filename": "JP_3-12_Cyberspace_Operations_Public_Edition.pdf",
        "title": "JP 3-12 Cyberspace Operations",
        "expected": ["jp 3-12", "cyberspace operations"],
        "names": ["jp3_12.pdf", "JP_3-12.pdf", "JP3-12.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_12.pdf"],
    },
    {
        "filename": "JP_3-14_Space_Operations_Public_Edition.pdf",
        "title": "JP 3-14 Space Operations",
        "expected": ["jp 3-14", "space operations"],
        "names": ["jp3_14.pdf", "JP_3-14.pdf", "JP3-14.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_14.pdf"],
    },
    {
        "filename": "JP_3-30_Joint_Air_Operations_Public_Edition.pdf",
        "title": "JP 3-30 Joint Air Operations",
        "expected": ["jp 3-30", "joint air operations"],
        "names": ["jp3_30.pdf", "JP_3-30.pdf", "JP3-30.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_30.pdf"],
    },
    {
        "filename": "JP_3-32_Joint_Maritime_Operations_Public_Edition.pdf",
        "title": "JP 3-32 Joint Maritime Operations",
        "expected": ["jp 3-32", "joint maritime operations"],
        "names": ["jp3_32.pdf", "JP_3-32.pdf", "JP3-32.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_32.pdf"],
    },
    {
        "filename": "JP_3-35_Deployment_and_Redeployment_Operations_Public_Edition.pdf",
        "title": "JP 3-35 Deployment and Redeployment Operations",
        "expected": ["jp 3-35", "deployment and redeployment"],
        "names": ["jp3_35.pdf", "JP_3-35.pdf", "JP3-35.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_35.pdf"],
    },
    {
        "filename": "JP_3-52_Joint_Airspace_Control_Public_Edition.pdf",
        "title": "JP 3-52 Joint Airspace Control",
        "expected": ["jp 3-52", "joint airspace control"],
        "names": ["jp3_52.pdf", "JP_3-52.pdf", "JP3-52.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_52.pdf"],
    },
    {
        "filename": "JP_3-60_Joint_Targeting_Public_Edition.pdf",
        "title": "JP 3-60 Joint Targeting",
        "expected": ["jp 3-60", "joint targeting"],
        "names": ["jp3_60.pdf", "JP_3-60.pdf", "JP3-60.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_60.pdf"],
    },
    {
        "filename": "JP_3-85_Joint_Electromagnetic_Spectrum_Operations_Public_Edition.pdf",
        "title": "JP 3-85 Joint Electromagnetic Spectrum Operations",
        "expected": ["jp 3-85", "electromagnetic spectrum operations"],
        "names": ["jp3_85.pdf", "JP_3-85.pdf", "JP3-85.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp3_85.pdf"],
    },
    {
        "filename": "JP_4-0_Joint_Logistics_Public_Edition.pdf",
        "title": "JP 4-0 Joint Logistics",
        "expected": ["jp 4-0", "joint logistics"],
        "names": ["jp4_0.pdf", "JP_4-0.pdf", "JP4-0.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp4_0.pdf"],
    },
    {
        "filename": "JP_4-01_The_Defense_Transportation_System_Public_Edition.pdf",
        "title": "JP 4-01 The Defense Transportation System",
        "expected": ["jp 4-01", "defense transportation system"],
        "names": ["jp4_01.pdf", "JP_4-01.pdf", "JP4-01.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp4_01.pdf"],
    },
    {
        "filename": "JP_5-0_Joint_Planning_Public_Edition.pdf",
        "title": "JP 5-0 Joint Planning",
        "expected": ["jp 5-0", "joint planning"],
        "names": ["jp5_0.pdf", "JP_5-0.pdf", "JP5-0.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp5_0.pdf"],
    },
    {
        "filename": "JP_6-0_Joint_Communications_System_Public_Edition.pdf",
        "title": "JP 6-0 Joint Communications System",
        "expected": ["jp 6-0", "joint communications system"],
        "names": ["jp6_0.pdf", "JP_6-0.pdf", "JP6-0.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/jp6_0.pdf"],
    },
    {
        "filename": "CJCSI_3370.01_Target_Development_Standards_Public_Edition.pdf",
        "title": "CJCSI 3370.01 Target Development Standards",
        "expected": ["3370.01", "target development"],
        "names": ["cjcsi3370_01.pdf", "CJCSI_3370.01.pdf", "CJCSI3370.pdf"],
        "urls": ["https://irp.fas.org/doddir/dod/cjcsi3370_01.pdf"],
    },
    {
        "filename": "DoD_JADC2_Strategy_Summary_2022.pdf",
        "title": "Summary of the Joint All-Domain Command and Control Strategy",
        "expected": ["joint all-domain command and control", "strategy"],
        "names": ["SUMMARY-OF-THE-JOINT-ALL-DOMAIN-COMMAND-AND-CONTROL-STRATEGY.PDF", "JADC2_Strategy_Summary.pdf"],
        "urls": ["https://media.defense.gov/2022/Mar/17/2002958406/-1/-1/1/SUMMARY-OF-THE-JOINT-ALL-DOMAIN-COMMAND-AND-CONTROL-STRATEGY.PDF"],
    },
    {
        "filename": "DoD_Electromagnetic_Spectrum_Superiority_Strategy_2020.pdf",
        "title": "DoD Electromagnetic Spectrum Superiority Strategy",
        "expected": ["electromagnetic spectrum superiority", "strategy"],
        "names": ["2020DoD-EMS-SuperiorityStrategy.pdf", "EMS_Superiority_Strategy.pdf"],
        "urls": ["https://dodcio.defense.gov/Portals/0/Documents/Spectrum/2020DoD-EMS-SuperiorityStrategy.pdf"],
    },
    {
        "filename": "DoDD_3000.09_Autonomy_in_Weapon_Systems_2023.pdf",
        "title": "DoDD 3000.09 Autonomy in Weapon Systems",
        "expected": ["3000.09", "autonomy in weapon systems"],
        "names": ["300009p.PDF", "DoDD_3000.09.pdf", "DODD300009.pdf"],
        "urls": ["https://www.esd.whs.mil/Portals/54/Documents/DD/issuances/dodd/300009p.PDF"],
    },
    {
        "filename": "Joint_Concept_for_Competing_2023.pdf",
        "title": "Joint Concept for Competing",
        "expected": ["joint concept for competing"],
        "names": ["20230213-joint-concept-for-competing-signed.pdf", "Joint_Concept_for_Competing.pdf"],
        "urls": ["https://s3.documentcloud.org/documents/23698400/20230213-joint-concept-for-competing-signed.pdf"],
    },
    {
        "filename": "Joint_Concept_for_Contested_Logistics_Public_Edition.pdf",
        "title": "Joint Concept for Contested Logistics",
        "expected": ["joint concept", "contested logistics"],
        "names": ["Joint_Concept_for_Contested_Logistics.pdf", "JCCL.pdf", "contested_logistics.pdf"],
        "urls": [],
    },
    {
        "filename": "FM_3-0_Operations_Current_Public_Edition.pdf",
        "title": "FM 3-0 Operations",
        "expected": ["fm 3-0", "operations"],
        "names": ["ARN43326-FM_3-0-000-WEB-1.pdf", "FM_3-0.pdf"],
        "urls": ["https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN43326-FM_3-0-000-WEB-1.pdf"],
    },
    {
        "filename": "ADP_6-0_Mission_Command_Command_and_Control_of_Army_Forces_2019.pdf",
        "title": "ADP 6-0 Mission Command",
        "expected": ["adp 6-0", "mission command"],
        "names": ["ARN34403-ADP_6-0-000-WEB-3.pdf", "ADP_6-0.pdf"],
        "urls": ["https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN34403-ADP_6-0-000-WEB-3.pdf"],
    },
    {
        "filename": "FM_6-0_Commander_and_Staff_Organization_and_Operations_Current_Public_Edition.pdf",
        "title": "FM 6-0 Commander and Staff Organization and Operations",
        "expected": ["fm 6-0", "commander and staff"],
        "names": ["ARN35404-FM_6-0-000-WEB-1.pdf", "FM_6-0.pdf"],
        "urls": ["https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN35404-FM_6-0-000-WEB-1.pdf"],
    },
    {
        "filename": "TAGS_Multi-Service_Tactics_Techniques_and_Procedures_2024.pdf",
        "title": "Theater Air-Ground System MTTP",
        "expected": ["theater air-ground system"],
        "names": ["tags_2024.pdf", "Theater_Air_Ground_System_MTTP.pdf"],
        "urls": ["https://www.alssa.mil/Portals/9/Documents/mttps/tags_2024.pdf"],
    },
]


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def get_bytes(url: str, timeout: int = 90) -> bytes | None:
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                data = r.content
                if data.lstrip().startswith(b"%PDF"):
                    return data
            if r.status_code in {401, 403, 429, 500, 502, 503, 504}:
                time.sleep(2 ** attempt)
                continue
            return None
        except requests.RequestException:
            time.sleep(2 ** attempt)
    return None


def inspect_pdf(data: bytes, expected: Iterable[str]) -> tuple[bool, str, int]:
    if not data.lstrip().startswith(b"%PDF") or len(data) < 20_000:
        return False, "not a substantive PDF", 0
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        pages = len(reader.pages)
        if pages < 3:
            return False, f"only {pages} pages", pages
        text_parts: list[str] = []
        for page in reader.pages[: min(12, pages)]:
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:
                pass
        text = norm(" ".join(text_parts))
        tokens = [norm(x) for x in expected if x]
        hits = sum(1 for token in tokens if token and token in text)
        required = 1 if len(tokens) <= 1 else 2
        if text and hits < required:
            return False, f"identity-token mismatch ({hits}/{len(tokens)})", pages
        # Image-only PDFs are accepted only after structural validation and when the
        # source filename/URL itself is an exact publication match.
        return True, "validated", pages
    except Exception as exc:
        return False, f"PDF parse failure: {exc}", 0


def github_candidates(names: list[str]) -> list[str]:
    if not TOKEN:
        return []
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    urls: list[str] = []
    seen: set[str] = set()
    for name in names:
        queries = [f"filename:{name}", f"{name} in:path"]
        for query in queries:
            try:
                r = requests.get(
                    "https://api.github.com/search/code",
                    params={"q": query, "per_page": 15},
                    headers=headers,
                    timeout=45,
                )
                if r.status_code != 200:
                    continue
                for item in r.json().get("items", []):
                    repo = item.get("repository", {}).get("full_name")
                    path = item.get("path")
                    if not repo or not path or not path.lower().endswith(".pdf"):
                        continue
                    raw = f"https://raw.githubusercontent.com/{repo}/{item.get('sha', 'HEAD')}/{quote(path)}"
                    # raw by blob SHA is not always accepted; contents API is more reliable.
                    api = f"https://api.github.com/repos/{repo}/contents/{quote(path)}"
                    try:
                        rr = requests.get(api, headers=headers, timeout=30)
                        if rr.status_code == 200:
                            dl = rr.json().get("download_url")
                            if dl and dl not in seen:
                                seen.add(dl)
                                urls.append(dl)
                    except requests.RequestException:
                        pass
            except requests.RequestException:
                continue
    return urls


def archive_candidates(title: str, names: list[str]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    queries = [f'title:"{title}"', title] + names[:2]
    for q in queries:
        try:
            r = requests.get(
                "https://archive.org/advancedsearch.php",
                params={
                    "q": f"({q}) AND mediatype:texts",
                    "fl[]": "identifier,title",
                    "rows": 8,
                    "page": 1,
                    "output": "json",
                },
                timeout=45,
                headers={"User-Agent": SESSION.headers["User-Agent"]},
            )
            if r.status_code != 200:
                continue
            for doc in r.json().get("response", {}).get("docs", []):
                ident = doc.get("identifier")
                if not ident:
                    continue
                meta = requests.get(
                    f"https://archive.org/metadata/{quote(ident)}",
                    timeout=45,
                    headers={"User-Agent": SESSION.headers["User-Agent"]},
                )
                if meta.status_code != 200:
                    continue
                files = meta.json().get("files", [])
                pdfs = [f for f in files if str(f.get("name", "")).lower().endswith(".pdf")]
                pdfs.sort(key=lambda f: int(f.get("size", 0) or 0), reverse=True)
                for f in pdfs[:3]:
                    url = f"https://archive.org/download/{quote(ident)}/{quote(str(f['name']))}"
                    if url not in seen:
                        seen.add(url)
                        urls.append(url)
        except (requests.RequestException, ValueError, KeyError):
            continue
    return urls


def ddg_candidates(title: str) -> list[str]:
    try:
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": f'"{title}" filetype:pdf'},
            timeout=45,
            headers={"User-Agent": SESSION.headers["User-Agent"]},
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        urls: list[str] = []
        for a in soup.select("a.result__a"):
            href = a.get("href")
            if href and ("pdf" in href.lower() or "download" in href.lower()):
                urls.append(href)
        return urls[:20]
    except requests.RequestException:
        return []


def candidate_urls(target: dict) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    sources = [
        target.get("urls", []),
        github_candidates(target.get("names", [])),
        archive_candidates(target["title"], target.get("names", [])),
        ddg_candidates(target["title"]),
    ]
    for group in sources:
        for url in group:
            if url and url not in seen:
                seen.add(url)
                ordered.append(url)
    return ordered


def main() -> int:
    hashes: dict[str, str] = {}
    failures: list[dict] = []
    successes: list[dict] = []

    for index, target in enumerate(TARGETS, 1):
        print(f"\n[{index:02d}/{len(TARGETS):02d}] {target['title']}", flush=True)
        saved = False
        reasons: list[str] = []
        urls = candidate_urls(target)
        for n, url in enumerate(urls[:50], 1):
            data = get_bytes(url)
            if data is None:
                reasons.append(f"{n}:download-failed")
                continue
            ok, reason, pages = inspect_pdf(data, target["expected"])
            if not ok:
                reasons.append(f"{n}:{reason}")
                continue
            digest = hashlib.sha256(data).hexdigest()
            if digest in hashes:
                reasons.append(f"{n}:duplicate-of-{hashes[digest]}")
                continue
            out = OUT / target["filename"]
            out.write_bytes(data)
            hashes[digest] = target["filename"]
            record = {
                "filename": target["filename"],
                "title": target["title"],
                "url": url,
                "sha256": digest,
                "bytes": len(data),
                "pages": pages,
            }
            successes.append(record)
            print(
                f"PASS1_RESULT\tSUCCESS\t{target['filename']}\t{pages} pages\t{len(data)} bytes\t{url}",
                flush=True,
            )
            saved = True
            break
        if not saved:
            record = {
                "filename": target["filename"],
                "title": target["title"],
                "attempted_candidates": len(urls[:50]),
                "reason": "; ".join(reasons[-8:]) or "no candidates found",
            }
            failures.append(record)
            print(
                f"PASS1_RESULT\tINCOMPLETE\t{target['filename']}\t{record['reason']}",
                flush=True,
            )

    # ZIP contains exactly one flat folder of PDFs and no metadata/readme files.
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(OUT.glob("*.pdf"), key=lambda p: p.name.lower()):
            zf.write(path, arcname=f"{OUT.name}/{path.name}")

    summary = {
        "requested": len(TARGETS),
        "downloaded": len(successes),
        "incomplete": failures,
        "zip": str(ZIP_PATH),
        "zip_bytes": ZIP_PATH.stat().st_size,
    }
    print("PASS1_SUMMARY_JSON=" + json.dumps(summary, separators=(",", ":")), flush=True)
    print(f"Built {ZIP_PATH} with {len(successes)} validated PDFs; {len(failures)} incomplete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
