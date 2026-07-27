#!/usr/bin/env python3
"""Harden the VERITAS Pass 2 builder without admitting stale doctrine."""
from __future__ import annotations

import hashlib
import io
import json
import re
import time
import urllib.parse
from dataclasses import replace

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

import veritas_pass2_builder as b

requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

_ORIGINAL_CANDIDATE_LINKS = b.Downloader.candidate_links


def robust_get(self: b.Downloader, url: str, timeout: int = 55) -> requests.Response:
    """Browser-like GET with SSL and transient-error fallbacks."""
    headers = {
        "User-Agent": b.USER_AGENT,
        "Accept": "application/pdf,text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": urllib.parse.urlunparse((urllib.parse.urlparse(url).scheme, urllib.parse.urlparse(url).netloc, "/", "", "", "")),
    }
    last: Exception | None = None
    for verify in (True, False):
        for attempt in range(3):
            try:
                response = self.session.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    headers=headers,
                    verify=verify,
                )
                if response.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return response
            except requests.exceptions.SSLError as exc:
                last = exc
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed {url}: {last}")


def candidate_links(self: b.Downloader, text: str, base_url: str, entry: b.Entry):
    """Extend the original HTML parser to understand Markdown/Jina output."""
    ranked = list(_ORIGINAL_CANDIDATE_LINKS(self, text, base_url, entry))
    found: dict[str, tuple[int, str]] = {url: (score, label) for score, url, label in ranked}
    terms = [b.norm(x) for x in (entry.preferred_terms or entry.required)]

    def add(raw: str, label: str = "", base_score: int = 0) -> None:
        raw = raw.strip().strip("<>[](){}\"'.,;")
        raw = raw.replace("\\/", "/").replace("&amp;", "&")
        if not raw or raw.startswith(("javascript:", "mailto:", "#")):
            return
        url = urllib.parse.urljoin(base_url, raw)
        if not url.startswith(("http://", "https://")):
            return
        blob = b.norm(label + " " + urllib.parse.unquote(url))
        score = base_score
        if ".pdf" in url.lower() or "/product/pdf/" in url.lower() or "format=pdf" in url.lower():
            score += 130
        if any(k in blob for k in ("download pdf", "download full", "full report", "download report", "pdf")):
            score += 35
        score += sum(20 for term in terms if term and term in blob)
        if b.host_allowed(url, entry.official_hosts):
            score += 20
        old = found.get(url)
        if old is None or score > old[0]:
            found[url] = (score, label)

    for match in re.finditer(r"\[([^\]]{0,180})\]\((https?://[^)\s]+)\)", text, re.I):
        add(match.group(2), match.group(1), 80)
    for match in re.finditer(r"https?://[^\s<>\"']+", text, re.I):
        add(match.group(0), "absolute url", 25)
    for match in re.finditer(r"(?:href|src|data|url)[\"'=: ]{1,10}([^\"'<>\s]+)", text, re.I):
        add(match.group(1), "embedded url", 20)

    out = [(score, url, label) for url, (score, label) in found.items()]
    out.sort(key=lambda item: item[0], reverse=True)
    return out


def _wayback_candidates(dl: b.Downloader, url: str, want_pdf: bool) -> list[str]:
    """Return a few recent public captures without treating archives as authority."""
    if "web.archive.org" in url:
        return []
    params = {
        "url": url,
        "output": "json",
        "fl": "timestamp,original,mimetype,statuscode",
        "filter": ["statuscode:200", f"mimetype:{'application/pdf' if want_pdf else 'text/html'}"],
        "collapse": "digest",
        "from": "2023",
        "limit": "8",
    }
    try:
        r = dl.session.get(
            "https://web.archive.org/cdx/search/cdx",
            params=params,
            timeout=35,
            headers={"User-Agent": b.USER_AGENT},
        )
        if r.status_code != 200:
            return []
        rows = r.json()
        captures = []
        for row in rows[1:] if isinstance(rows, list) else []:
            if len(row) >= 2:
                captures.append(f"https://web.archive.org/web/{row[0]}id_/{row[1]}")
        return list(reversed(captures))
    except Exception:
        return []


def resolve(self: b.Downloader, entry: b.Entry):
    errors: list[str] = []
    visited: set[str] = set()

    def probe(url: str, depth: int, allow_archive: bool = True):
        if depth > 3 or url in visited:
            return None
        visited.add(url)
        response: requests.Response | None = None
        try:
            response = self.get(url)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}")

        if response is not None:
            data = response.content
            ctype = (response.headers.get("content-type") or "").lower()
            if data[:5] == b"%PDF-":
                return data, response.url
            if "application/pdf" in ctype and data[:5] != b"%PDF-":
                errors.append(f"{url}: PDF content-type without PDF signature")
            if response.status_code < 400:
                text = data.decode(response.encoding or "utf-8", errors="replace")
                for score, candidate, _ in self.candidate_links(text, response.url, entry)[:45]:
                    if score < 20:
                        continue
                    result = probe(candidate, depth + 1, allow_archive=True)
                    if result is not None:
                        return result
            else:
                errors.append(f"{url}: HTTP {response.status_code}")

        # Jina often exposes media links from WEB.mil, Congress, GAO, and Air University pages.
        if depth <= 1 and "r.jina.ai" not in url and "web.archive.org" not in url:
            jina_url = "https://r.jina.ai/http://" + url.split("://", 1)[-1]
            try:
                jina = self.get(jina_url, timeout=45)
                if jina.status_code == 200:
                    for score, candidate, _ in self.candidate_links(jina.text, url, entry)[:45]:
                        if score < 25:
                            continue
                        result = probe(candidate, depth + 1, allow_archive=True)
                        if result is not None:
                            return result
            except Exception as exc:  # noqa: BLE001
                errors.append(f"jina {url}: {exc}")

        # Recover only captures of the same official/current source, then validate title/date in the PDF.
        if allow_archive and "web.archive.org" not in url:
            is_pdf = ".pdf" in urllib.parse.urlparse(url).path.lower() or "/product/pdf/" in url.lower()
            for capture in _wayback_candidates(self, url, is_pdf)[:4]:
                result = probe(capture, depth + 1, allow_archive=False)
                if result is not None:
                    return result

        return None

    for source in entry.urls:
        result = probe(source, 0)
        if result is not None:
            return result[0], result[1], errors
    raise RuntimeError(" | ".join(errors[-16:]) or "no source succeeded")


def pdf_text_and_pages(data: bytes, page_limit: int = 24):
    reader = PdfReader(io.BytesIO(data), strict=False)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass
    pages = len(reader.pages)
    metadata = reader.metadata or {}
    meta_text = " ".join(str(value) for value in metadata.values() if value)
    chunks = [meta_text]
    indexes = list(range(min(page_limit, pages)))
    if pages > page_limit:
        indexes.extend(range(max(page_limit, pages - 2), pages))
    for index in dict.fromkeys(indexes):
        try:
            chunks.append(reader.pages[index].extract_text() or "")
        except Exception:
            pass
    return "\n".join(chunks), pages, meta_text


def validate(entry: b.Entry, data: bytes, final_url: str):
    if not data.startswith(b"%PDF-"):
        raise ValueError("missing PDF signature")
    if not entry.min_bytes <= len(data) <= entry.max_bytes:
        raise ValueError(f"invalid file size: {len(data)} bytes")
    final_host = b.hostname(final_url)
    if entry.official_hosts and not b.host_allowed(final_url, entry.official_hosts):
        if final_host != "web.archive.org":
            raise ValueError(f"final host is not approved: {final_host}")
    text, pages, metadata = pdf_text_and_pages(data)
    if pages < entry.min_pages:
        raise ValueError(f"only {pages} pages")
    ntext = b.norm(text)
    missing = [token for token in entry.required if b.norm(token) not in ntext]
    if missing:
        raise ValueError(f"content check failed; missing {missing}")
    sha = hashlib.sha256(data).hexdigest()
    if sha in b.EXISTING_HASHES:
        raise ValueError("binary duplicate of an existing Project Source")
    return {
        "sha256": sha,
        "bytes": len(data),
        "pages": pages,
        "final_url": final_url,
        "metadata": metadata[:500],
    }


b.Downloader.get = robust_get
b.Downloader.candidate_links = candidate_links
b.Downloader.resolve = resolve
b.pdf_text_and_pages = pdf_text_and_pages
b.validate = validate

replacements: dict[str, dict] = {
    "PPBE_Commission_Defense_Resourcing_for_the_Future_Final_Report_2024.pdf": {
        "urls": (
            "https://ppbereform.senate.gov/wp-content/uploads/2024/03/Commission-on-PPBE-Reform_Full-Report_6-March-2024_FINAL.pdf",
            "https://www.dmi-ida.org/knowledge-base-detail/Defense-Resourcing-for-the-Future",
        ),
        "required": ("defense resourcing for the future", "final report", "2024"),
        "official_hosts": ("ppbereform.senate.gov", "dmi-ida.org"),
        "min_pages": 80,
    },
    "Defense_Innovation_Board_Scaling_Nontraditional_Defense_Innovation_2025.pdf": {
        "urls": ("https://stib.cto.mil/wp-content/uploads/2026/01/2025-2_DIB-ScalingNontraditionalDefenseInnovation_250113PUBLISHED_9ee4ae.pdf",),
        "required": ("scaling nontraditional defense innovation",),
        "official_hosts": ("stib.cto.mil",),
        "min_pages": 40,
    },
    "Defense_Innovation_Board_Building_a_DoD_Data_Economy_2024.pdf": {
        "urls": ("https://stib.cto.mil/wp-content/uploads/2026/01/2024-4_DIB_Study_Building_a_DoD_Data_Economy.pdf",),
        "required": ("building a dod data economy",),
        "official_hosts": ("stib.cto.mil",),
        "min_pages": 20,
    },
    "CNAS_Countering_the_Swarm_2025.pdf": {
        "official_hosts": ("cnas.org", "files.cnas.org", "s3.us-east-1.amazonaws.com", "amazonaws.com"),
    },
    "CNAS_Hellscape_for_Taiwan_2026.pdf": {
        "official_hosts": ("cnas.org", "files.cnas.org", "s3.us-east-1.amazonaws.com", "amazonaws.com"),
    },
    "NDU_Fabrication_at_the_Tactical_Edge_2025.pdf": {
        "urls": (
            "https://ndupress.ndu.edu/Portals/68/Documents/jfq/jfq%20119/jfq-119-fabrication-at-the-tactical-edge.pdf",
            "https://ndupress.ndu.edu/Media/News/News-Article-View/Article/4366244/fabrication-at-the-tactical-edge/",
        ),
        "required": ("fabrication at the tactical edge", "2025"),
        "official_hosts": ("ndupress.ndu.edu",),
        "min_pages": 8,
    },
    "DoD_National_Defense_Industrial_Strategy_2024.pdf": {
        "urls": (
            "https://www.businessdefense.gov/docs/ndis/2023-NDIS.pdf",
            "https://www.defense.gov/News/News-Stories/Article/Article/3644527/dod-releases-first-defense-industrial-strategy/",
        ),
        "required": ("national defense industrial strategy", "2024"),
        "official_hosts": ("businessdefense.gov", "defense.gov", "media.defense.gov"),
        "min_pages": 45,
    },
    "DoD_Intellectual_Property_Guidebook_for_Acquisition_2025.pdf": {
        "urls": (
            "https://www.acq.osd.mil/asda/dpc/api/docs/intellectual%20property%20guidebook%20for%20dod%20acquisition%20signed.pdf",
            "https://www.dmi-ida.org/knowledge-base-detail/Intellectual-Property-Guidebook-for-DoD-Acquisition",
        ),
        "required": ("intellectual property guidebook", "dod acquisition", "2025"),
        "official_hosts": ("acq.osd.mil", "dmi-ida.org"),
        "min_pages": 70,
    },
}

entries = []
for entry in b.ENTRIES:
    changes = replacements.get(entry.filename)
    entries.append(replace(entry, **changes) if changes else entry)

entries.extend(
    [
        b.Entry(
            "Defense_Innovation_Board_Aligning_Incentives_to_Drive_Faster_Tech_Adoption_2024.pdf",
            "Aligning Incentives to Drive Faster Tech Adoption",
            2024,
            "Innovation-Scaling",
            ("https://stib.cto.mil/wp-content/uploads/2026/01/2024-2_DIB_Report_Aligning_Incentives_PUBLISHED_STUDY.pdf",),
            ("aligning incentives", "faster tech adoption"),
            ("aligning incentives", "tech adoption"),
            ("stib.cto.mil",),
            min_pages=25,
        ),
        b.Entry(
            "Defense_Innovation_Board_Lowering_Barriers_to_Innovation_2024.pdf",
            "Lowering Barriers to Innovation",
            2024,
            "Innovation-Scaling",
            ("https://stib.cto.mil/wp-content/uploads/2026/01/2024-3_DIB_Study_Lowering_Barriers_to_Innovation.pdf",),
            ("lowering barriers to innovation",),
            ("lowering barriers", "innovation"),
            ("stib.cto.mil",),
            min_pages=10,
        ),
        b.Entry(
            "DoDM_5010.12_Acquisition_and_Management_of_Contractor_Prepared_Data_2025.pdf",
            "DoDM 5010.12 Acquisition and Management of Contractor-Prepared Data",
            2025,
            "Acquisition-Open-Architecture",
            ("https://www.esd.whs.mil/Directives/issuances/dodm/",),
            ("dodm 5010.12", "acquisition and management of contractor-prepared data", "2025"),
            ("5010.12", "contractor-prepared data"),
            ("esd.whs.mil",),
            min_pages=30,
        ),
        b.Entry(
            "CJCSM_5123.01_Joint_Requirements_Oversight_Council_Process_2026.pdf",
            "CJCSM 5123.01 Manual for the Joint Requirements Oversight Council and the Joint Force Requirements Process",
            2026,
            "Doctrine-Joint-Process",
            ("https://www.jcs.mil/Library/CJCS-Manuals/udt_48785_param_orderby/Info/udt_48785_param_direction/ascending/FileID/304515/",),
            ("cjcsm 5123.01", "joint force requirements process", "2026"),
            ("5123.01", "requirements process"),
            ("jcs.mil",),
            min_pages=20,
        ),
        b.Entry(
            "CJCSM_3320.01D_Joint_Electromagnetic_Spectrum_Operations_2025.pdf",
            "CJCSM 3320.01D Joint Electromagnetic Spectrum Operations",
            2025,
            "Doctrine-Joint-Process",
            ("https://www.jcs.mil/Library/CJCS-Manuals/FileID/178603/FileID/178603/udt_48785_param_direction/ascending/udt_48785_param_orderby/Title/",),
            ("cjcsm 3320.01d", "joint electromagnetic spectrum operations", "2025"),
            ("3320.01d", "electromagnetic spectrum operations"),
            ("jcs.mil",),
            min_pages=20,
        ),
        b.Entry(
            "CJCSM_3105.01C_Joint_Risk_Analysis_Methodology_2026.pdf",
            "CJCSM 3105.01C Joint Risk Analysis Methodology",
            2026,
            "Doctrine-Joint-Process",
            ("https://www.jcs.mil/Library/CJCS-Manuals/udt_48785_param_orderby/Pub_x0020_Date_UDT_Value/udt_48785_param_direction/descending/",),
            ("cjcsm 3105.01c", "joint risk analysis methodology", "2026"),
            ("3105.01c", "risk analysis methodology"),
            ("jcs.mil",),
            min_pages=15,
        ),
    ]
)

# Preserve order while rejecting duplicate filenames introduced by page revisions.
seen: set[str] = set()
b.ENTRIES = tuple(entry for entry in entries if not (entry.filename in seen or seen.add(entry.filename)))

if __name__ == "__main__":
    raise SystemExit(b.main())
