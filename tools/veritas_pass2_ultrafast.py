#!/usr/bin/env python3
"""Low-latency final VERITAS Pass 2 corpus build.

Uses the already curated current-source set, caps network latency, and never falls
back to stale doctrine. Failed candidates are omitted rather than substituted.
"""
from __future__ import annotations

import urllib.parse

import requests

import veritas_pass2_patch  # applies current-source corrections and validators
import veritas_pass2_builder as b

KEEP = {
    # Current Army doctrine verified against the 2026 APD catalogue.
    "FM_1-02.1_Operational_Terms_2026.pdf",
    "FM_2-0_Intelligence_2023.pdf",
    "FM_3-01_US_Army_Air_and_Missile_Defense_Operations_2025.pdf",
    "FM_3-04_Army_Aviation_2025.pdf",
    "FM_3-09_Fire_Support_and_Field_Artillery_Operations_2024.pdf",
    "FM_3-14_Army_Space_Operations_2026.pdf",
    "FM_4-0_Sustainment_Operations_2026.pdf",
    "FM_5-0_Planning_and_Orders_Production_2024.pdf",
    # Current/recent government and professional sources.
    "Air_University_Human_Machine_War_2025.pdf",
    "NDU_Fabrication_at_the_Tactical_Edge_2025.pdf",
    "DoD_National_Defense_Industrial_Strategy_2024.pdf",
    "DoD_NDIS_Implementation_Plan_FY2025.pdf",
    "DoD_Intellectual_Property_Guidebook_for_Acquisition_2025.pdf",
    "PPBE_Commission_Defense_Resourcing_for_the_Future_Final_Report_2024.pdf",
    "Defense_Innovation_Board_Pathway_to_Scaling_Unmanned_Weapon_Systems_2025.pdf",
    "Defense_Innovation_Board_Scaling_Nontraditional_Defense_Innovation_2025.pdf",
    "Defense_Innovation_Board_Building_a_DoD_Data_Economy_2024.pdf",
    "Defense_Innovation_Board_Aligning_Incentives_to_Drive_Faster_Tech_Adoption_2024.pdf",
    "Defense_Innovation_Board_Lowering_Barriers_to_Innovation_2024.pdf",
    "RUSI_Tactical_Developments_Third_Year_Russo_Ukrainian_War_2025.pdf",
    "RUSI_Mass_Precision_Strike_Designing_UAV_Complexes_2024.pdf",
    "RUSI_Winning_the_Industrial_War_2025.pdf",
    "RUSI_Drones_Decoupling_Supply_Chains_from_China_2025.pdf",
    "CNAS_Countering_the_Swarm_2025.pdf",
    "CNAS_Hellscape_for_Taiwan_2026.pdf",
    "CSIS_Unleashing_US_Military_Drone_Dominance_2025.pdf",
    "CSIS_Ukraine_AI_Enabled_Autonomous_Warfare_2025.pdf",
    "Atlantic_Council_Software_Defined_Warfare_Final_Report_2025.pdf",
    "Belfer_Autonomous_Arsenal_in_Defense_of_Taiwan_2025.pdf",
    "DoDM_5010.12_Acquisition_and_Management_of_Contractor_Prepared_Data_2025.pdf",
}

b.ENTRIES = tuple(entry for entry in b.ENTRIES if entry.filename in KEEP)


def quick_get(self: b.Downloader, url: str, timeout: int = 18) -> requests.Response:
    headers = {
        "User-Agent": b.USER_AGENT,
        "Accept": "application/pdf,text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": urllib.parse.urlunparse((urllib.parse.urlparse(url).scheme, urllib.parse.urlparse(url).netloc, "/", "", "", "")),
    }
    errors = []
    for verify in (True, False):
        try:
            return self.session.get(url, timeout=timeout, allow_redirects=True, verify=verify, headers=headers)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors))


def quick_resolve(self: b.Downloader, entry: b.Entry):
    errors: list[str] = []
    visited: set[str] = set()

    def probe(url: str, depth: int):
        if depth > 2 or url in visited:
            return None
        visited.add(url)
        try:
            response = self.get(url)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}")
            return None
        data = response.content
        if data[:5] == b"%PDF-":
            return data, response.url
        if response.status_code >= 400:
            errors.append(f"{url}: HTTP {response.status_code}")
            return None
        text = data.decode(response.encoding or "utf-8", errors="replace")
        for score, candidate, _ in self.candidate_links(text, response.url, entry)[:35]:
            if score < 25:
                continue
            result = probe(candidate, depth + 1)
            if result is not None:
                return result
        return None

    for source in entry.urls:
        result = probe(source, 0)
        if result is not None:
            return result[0], result[1], errors
        # One bounded Jina pass to expose JS-hidden PDF URLs.
        try:
            jina = self.get("https://r.jina.ai/http://" + source.split("://", 1)[-1], timeout=20)
            if jina.status_code == 200:
                for score, candidate, _ in self.candidate_links(jina.text, source, entry)[:35]:
                    if score < 30:
                        continue
                    result = probe(candidate, 1)
                    if result is not None:
                        return result[0], result[1], errors
        except Exception as exc:  # noqa: BLE001
            errors.append(f"jina {source}: {exc}")
    raise RuntimeError(" | ".join(errors[-12:]) or "no source succeeded")


b.Downloader.get = quick_get
b.Downloader.resolve = quick_resolve

if __name__ == "__main__":
    raise SystemExit(b.main())
