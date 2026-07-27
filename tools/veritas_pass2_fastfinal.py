#!/usr/bin/env python3
"""Deterministic Pass 2 build using the strongest current-source candidates."""
from __future__ import annotations

import urllib.parse

import veritas_pass2_patch  # noqa: F401 - applies validation and source corrections
import veritas_pass2_builder as b

KEEP = {
    "FM_1-02.1_Operational_Terms_2026.pdf",
    "FM_2-0_Intelligence_2023.pdf",
    "FM_3-01_US_Army_Air_and_Missile_Defense_Operations_2025.pdf",
    "FM_3-04_Army_Aviation_2025.pdf",
    "FM_3-09_Fire_Support_and_Field_Artillery_Operations_2024.pdf",
    "FM_3-14_Army_Space_Operations_2026.pdf",
    "FM_4-0_Sustainment_Operations_2026.pdf",
    "FM_5-0_Planning_and_Orders_Production_2024.pdf",
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


def fast_resolve(self: b.Downloader, entry: b.Entry):
    errors: list[str] = []
    visited: set[str] = set()

    def probe(url: str, depth: int):
        if depth > 3 or url in visited:
            return None
        visited.add(url)
        try:
            response = self.get(url, timeout=55)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}")
            return None
        data = response.content
        if data[:5] == b"%PDF-":
            return data, response.url
        if response.status_code < 400:
            text = data.decode(response.encoding or "utf-8", errors="replace")
            for score, candidate, _ in self.candidate_links(text, response.url, entry)[:50]:
                if score < 20:
                    continue
                result = probe(candidate, depth + 1)
                if result is not None:
                    return result
        else:
            errors.append(f"{url}: HTTP {response.status_code}")

        if depth <= 1 and "r.jina.ai" not in url:
            jina_url = "https://r.jina.ai/http://" + url.split("://", 1)[-1]
            try:
                jina = self.get(jina_url, timeout=50)
                if jina.status_code == 200:
                    for score, candidate, _ in self.candidate_links(jina.text, url, entry)[:50]:
                        if score < 25:
                            continue
                        result = probe(candidate, depth + 1)
                        if result is not None:
                            return result
            except Exception as exc:  # noqa: BLE001
                errors.append(f"jina {url}: {exc}")
        return None

    for source in entry.urls:
        result = probe(source, 0)
        if result is not None:
            return result[0], result[1], errors
    raise RuntimeError(" | ".join(errors[-14:]) or "no source succeeded")


b.Downloader.resolve = fast_resolve

if __name__ == "__main__":
    raise SystemExit(b.main())
