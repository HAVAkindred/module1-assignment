#!/usr/bin/env python3
"""Gold VERITAS Pass 2 build: exact current-source PDF URLs only.

No stale Joint Publication is substituted when the governing edition is restricted.
Every admitted PDF is title/date validated and checked against existing Project Source
hashes before the flat archive is built.
"""
from __future__ import annotations

import requests

import veritas_pass2_patch  # installs hardened PDF validation
import veritas_pass2_builder as b

E = b.Entry
b.ENTRIES = (
    # Current Army doctrine — official APD/RDL URLs, exact governing editions.
    E("ADP_3-0_Operations_2025.pdf", "ADP 3-0 Operations", 2025, "Doctrine-Army", ("https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN43323-ADP_3-0-000-WEB-1.pdf",), ("adp 3-0", "operations", "2025"), official_hosts=("armypubs.army.mil",), min_pages=100),
    E("FM_3-0_Operations_2025.pdf", "FM 3-0 Operations", 2025, "Doctrine-Army", ("https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN43326-FM_3-0-000-WEB-1.pdf",), ("fm 3-0", "operations", "2025"), official_hosts=("armypubs.army.mil",), min_pages=150),
    E("FM_3-09_Fire_Support_and_Field_Artillery_Operations_2024.pdf", "FM 3-09 Fire Support and Field Artillery Operations", 2024, "Doctrine-Army", ("https://rdl.train.army.mil/catalog-ws/view/100.atsc/9b9879f3-f213-4cd7-9d20-8d4520e8d38e-1397219978180/fm3_09.pdf",), ("fm 3-09", "fire support and field artillery operations", "2024"), official_hosts=("rdl.train.army.mil",), min_pages=150),
    E("FM_3-90_Tactics_2023.pdf", "FM 3-90 Tactics", 2023, "Doctrine-Army", ("https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN38160-FM_3-90-000-WEB-1.pdf",), ("fm 3-90", "tactics", "2023"), official_hosts=("armypubs.army.mil",), min_pages=250),
    E("FM_3-98_Reconnaissance_and_Security_Operations_2023.pdf", "FM 3-98 Reconnaissance and Security Operations", 2023, "Doctrine-Army", ("https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN37194-FM_3-98-000-WEB-1.pdf",), ("fm 3-98", "reconnaissance and security operations", "2023"), official_hosts=("armypubs.army.mil",), min_pages=150),
    E("FM_4-0_Sustainment_Operations_2026.pdf", "FM 4-0 Sustainment Operations", 2026, "Doctrine-Army", ("https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN46157-FM_4-0-000-WEB-1.pdf",), ("fm 4-0", "sustainment operations", "2026"), official_hosts=("armypubs.army.mil",), min_pages=200),
    E("FM_5-0_Planning_and_Orders_Production_2024.pdf", "FM 5-0 Planning and Orders Production", 2024, "Doctrine-Army", ("https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN42404-FM_5-0-000-WEB-1.pdf",), ("fm 5-0", "planning and orders production", "2024"), official_hosts=("armypubs.army.mil",), min_pages=150),
    E("ADP_3-13_Information_2023.pdf", "ADP 3-13 Information", 2023, "Doctrine-Army", ("https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN39736-ADP_3-13-000-WEB-1.pdf",), ("adp 3-13", "information", "2023"), official_hosts=("armypubs.army.mil",), min_pages=50),
    E("ADP_7-0_Training_2024.pdf", "ADP 7-0 Training", 2024, "Doctrine-Army", ("https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN40738-ADP_7-0-000-WEB-2.pdf",), ("adp 7-0", "training", "2024"), official_hosts=("armypubs.army.mil",), min_pages=100),

    # Current acquisition, industrial-base, data, and autonomy-at-scale sources.
    E("DoD_NDIS_Implementation_Plan_FY2025.pdf", "National Defense Industrial Strategy Implementation Plan for FY2025", 2024, "Industrial-Base", ("https://www.govinfo.gov/content/pkg/GOVPUB-D-PURL-gpo234260/pdf/GOVPUB-D-PURL-gpo234260.pdf",), ("national defense industrial strategy implementation plan", "fy2025"), official_hosts=("govinfo.gov",), min_pages=80),
    E("DoD_Intellectual_Property_Guidebook_for_Acquisition_2025.pdf", "Intellectual Property Guidebook for DoD Acquisition", 2025, "Acquisition-Open-Architecture", ("https://www.acq.osd.mil/asda/dpc/api/docs/intellectual%20property%20guidebook%20for%20dod%20acquisition%20signed.pdf",), ("intellectual property guidebook", "dod acquisition", "2025"), official_hosts=("acq.osd.mil",), min_pages=70),
    E("Defense_Innovation_Board_Pathway_to_Scaling_Unmanned_Weapon_Systems_2025.pdf", "A Pathway to Scaling Unmanned Weapon Systems", 2025, "Autonomy-at-Scale", ("https://stib.cto.mil/wp-content/uploads/2026/01/2025-1_DIB_A-Pathway-to-Scaling-Unmanned-Weapon-Systems_250113.pdf",), ("pathway to scaling unmanned weapon systems", "2025"), official_hosts=("stib.cto.mil",), min_pages=15),
    E("Defense_Innovation_Board_Scaling_Nontraditional_Defense_Innovation_2025.pdf", "Scaling Nontraditional Defense Innovation", 2025, "Innovation-Scaling", ("https://stib.cto.mil/wp-content/uploads/2026/01/2025-2_DIB-ScalingNontraditionalDefenseInnovation_250113PUBLISHED_9ee4ae.pdf",), ("scaling nontraditional defense innovation", "2025"), official_hosts=("stib.cto.mil",), min_pages=45),
    E("Defense_Innovation_Board_Building_a_DoD_Data_Economy_2024.pdf", "Building a DoD Data Economy", 2024, "Data-Architecture", ("https://stib.cto.mil/wp-content/uploads/2026/01/2024-4_DIB_Study_Building_a_DoD_Data_Economy.pdf",), ("building a dod data economy", "2024"), official_hosts=("stib.cto.mil",), min_pages=20),
    E("Defense_Innovation_Board_Aligning_Incentives_to_Drive_Faster_Tech_Adoption_2024.pdf", "Aligning Incentives to Drive Faster Tech Adoption", 2024, "Innovation-Scaling", ("https://stib.cto.mil/wp-content/uploads/2026/01/2024-2_DIB_Report_Aligning_Incentives_PUBLISHED_STUDY.pdf",), ("aligning incentives", "faster tech adoption", "2024"), official_hosts=("stib.cto.mil",), min_pages=25),
    E("Defense_Innovation_Board_Lowering_Barriers_to_Innovation_2024.pdf", "Lowering Barriers to Innovation", 2024, "Innovation-Scaling", ("https://stib.cto.mil/wp-content/uploads/2026/01/2024-3_DIB_Study_Lowering_Barriers_to_Innovation.pdf",), ("lowering barriers to innovation", "2024"), official_hosts=("stib.cto.mil",), min_pages=10),

    # Operational lessons, UAS mass, industrial warfare, and supply-chain resilience.
    E("RUSI_Tactical_Developments_Third_Year_Russo_Ukrainian_War_2025.pdf", "Tactical Developments During the Third Year of the Russo-Ukrainian War", 2025, "Operational-Lessons", ("https://static.rusi.org/tactical-developments-third-year-russo-ukrainian-war-february-2205.pdf",), ("tactical developments", "third year", "russo-ukrainian war", "2025"), official_hosts=("static.rusi.org",), min_pages=20),
    E("RUSI_Mass_Precision_Strike_Designing_UAV_Complexes_2024.pdf", "Mass Precision Strike: Designing UAV Complexes for Land Forces", 2024, "UAS-Mass", ("https://static.rusi.org/mass-precision-strike-final.pdf",), ("mass precision strike", "uav complexes", "2024"), official_hosts=("static.rusi.org",), min_pages=45),
    E("RUSI_Winning_the_Industrial_War_2025.pdf", "Winning the Industrial War: Comparing Russia, Europe and Ukraine, 2022-24", 2025, "Industrial-Warfare", ("https://static.rusi.org/winning-the-industrial-war-comparing-russia-europe-ukraine-2022-24.pdf",), ("winning the industrial war", "2025"), official_hosts=("static.rusi.org",), min_pages=50),
    E("RUSI_Drones_Decoupling_Supply_Chains_from_China_2025.pdf", "Drones: Decoupling Supply Chains from China", 2025, "UAS-Supply-Chain", ("https://static.rusi.org/rp-drone-supply-chains-china-nov-2025_0.pdf",), ("drones", "decoupling supply chains", "china", "2025"), official_hosts=("static.rusi.org",), min_pages=30),

    # Recent UAS, counter-UAS, autonomous warfare, and software-defined warfare studies.
    E("CNAS_Countering_the_Swarm_2025.pdf", "Countering the Swarm: Protecting the Joint Force in the Drone Age", 2025, "Counter-UAS", ("https://s3.us-east-1.amazonaws.com/files.cnas.org/documents/Report_CUAS_Defense_Sep-2025_final.pdf",), ("countering the swarm", "drone age", "2025"), official_hosts=("s3.us-east-1.amazonaws.com",), min_pages=55),
    E("CNAS_Hellscape_for_Taiwan_2026.pdf", "Hellscape for Taiwan: Rethinking Asymmetric Defense", 2026, "UAS-Mass", ("https://s3.us-east-1.amazonaws.com/files.cnas.org/documents/Hellscape_DEFENSE_2026-Final.pdf",), ("hellscape for taiwan", "asymmetric defense", "2026"), official_hosts=("s3.us-east-1.amazonaws.com",), min_pages=25),
    E("CSIS_Unleashing_US_Military_Drone_Dominance_2025.pdf", "Unleashing U.S. Military Drone Dominance", 2025, "UAS-Industrial-Base", ("https://csis-website-prod.s3.amazonaws.com/s3fs-public/2025-07/250718_Bondar_Drone_Dominance.pdf",), ("unleashing u.s. military drone dominance", "2025"), official_hosts=("csis-website-prod.s3.amazonaws.com",), min_pages=25),
    E("CSIS_Ukraine_AI_Enabled_Autonomous_Warfare_2025.pdf", "Ukraine's Future Vision and Current Capabilities for Waging AI-Enabled Autonomous Warfare", 2025, "Autonomy-Lessons", ("https://csis-website-prod.s3.amazonaws.com/s3fs-public/2025-03/250306_Bondar_Autonomy_AI.pdf",), ("ukraine", "ai-enabled autonomous warfare", "2025"), official_hosts=("csis-website-prod.s3.amazonaws.com",), min_pages=35),
    E("Atlantic_Council_Software_Defined_Warfare_Final_Report_2025.pdf", "Commission on Software-Defined Warfare Final Report", 2025, "Software-Defined-Warfare", ("https://www.atlanticcouncil.org/wp-content/uploads/2025/03/Commission-on-Software-Defined-Warfare-Final-Report.pdf",), ("software-defined warfare", "final report", "2025"), official_hosts=("atlanticcouncil.org",), min_pages=30),
    E("Belfer_Autonomous_Arsenal_in_Defense_of_Taiwan_2025.pdf", "The Autonomous Arsenal in Defense of Taiwan", 2025, "Autonomy-at-Scale", ("https://www.belfercenter.org/sites/default/files/2025-02/DETS_The%20Autonomous%20Arsenal_1.pdf",), ("autonomous arsenal", "defense of taiwan", "2025"), official_hosts=("belfercenter.org",), min_pages=50),
)


def exact_get(self: b.Downloader, url: str, timeout: int = 40) -> requests.Response:
    headers = {
        "User-Agent": b.USER_AGENT,
        "Accept": "application/pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    errors = []
    for verify in (True, False):
        try:
            return self.session.get(url, timeout=timeout, allow_redirects=True, verify=verify, headers=headers)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors))


def exact_resolve(self: b.Downloader, entry: b.Entry):
    errors = []
    for url in entry.urls:
        try:
            response = self.get(url)
            if response.content[:5] == b"%PDF-":
                return response.content, response.url, errors
            errors.append(f"{url}: HTTP {response.status_code}, non-PDF content")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {exc}")
    raise RuntimeError(" | ".join(errors))


b.Downloader.get = exact_get
b.Downloader.resolve = exact_resolve

if __name__ == "__main__":
    raise SystemExit(b.main())
