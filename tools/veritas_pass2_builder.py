#!/usr/bin/env python3
"""Build a flat, validated VERITAS Pass 2 PDF corpus.

Only PDFs that pass title/date checks are admitted. Doctrine entries also require
an official proponent-hosted final URL. Existing project-source SHA-256 hashes are
excluded to prevent re-ingestion.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import sys
import time
import unicodedata
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

OUT_DIR = Path("PASS_02_Current_Relevant")
ZIP_PATH = Path("VERITAS_PASS_02_Current_Relevant_Corpus.zip")
REPORT_PATH = Path("pass2_validation_report.json")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 VERITAS-Corpus/2.0"

EXISTING_HASHES = {
    "8417256f2eb1d4c4132540bd1ae431d155c0879cbed1bec81ab92f3d09572c76",
    "5d18560e15144474e4fe5c516a976c00c71dc62840476d8b33f2d57a9d6c38f6",
    "e7473901a62365b6b4804b3a3b3a229654bfcb7d092ab576759448816f845bf5",
    "82c18a5816c4a343f238076bc7de7fd808ab4e069a3d4ff5003b3877663e496f",
    "5560c44df8c3cbd8d16123f25e0b2d34fc140c77834de4689efaea33fefc3eea",
    "115657093e6822440dec65212bbdffff8cc0c7cc22b6872aa11184110d0822d4",
    "95db93261c8551dc7bcad348706e7155ef235cd423c2605a12367b51238a4c70",
    "ca9a369159b66d351a41e28a40c7ad260094351557155a1f059161a40681fa66",
    "82cc30edeae116240932bcb25631513896fbeb775614c06d157f8c8f40ec2b26",
    "3f58223d4a871677209d53fb0b40445557865fdfc83f2d3d306889eec80890f7",
    "606dd3eaa40f9b21762f10331897f5b821337599f60816eecd0e697045cd2f84",
    "47fcd6fd0aee3bd7a4cae9c7fd28f51914a5a05e2a8b610905ed64d0dd4c1f11",
    "25f3c9d42d62da71f6942ebe592211e385a442bd8a012dd08d64fc4b27e37436",
    "aa773a31e7ed7c0b9722f3a5c128a08a17c87a44b6e12dcb7458ca75424709ec",
    "9365eadd020072c51adfcd47860e877eec06e84702a4373fc8636b3520b27335",
    "d097e7c123c9476b951d8ab48aea2b96015ffc39389393a705d003b5a564dfee",
    "b40d208ac91f8634db158ea0a9faa805f369e0812125b0b5c4f34c50cad9ee04",
    "aaab1f42669477a7f427761a884d38fa0d7d1869d13de280ff4d0bc81c80a4a9",
    "b5305db1c6a29542d6f4b0ad33740c53d5c56ec78addba6cdee3889e95f95d30",
    "253f7f22a685a997f11b3ad680432e3783861fa224fb725ca1a1ab34e18a4a04",
    "02d3e8653d0da94613814743af08487a72e660a2efba3991c9c30796806ad5ad",
    "e6c77d239a0fec130b2aee588b231dfd3aebcbb24652bc25054cc6dda1570163",
    "7576edb531d9848825814ee88e28b1795d3a84b435b4b797d3670eafdc4a89f1",
}

@dataclass(frozen=True)
class Entry:
    filename: str
    title: str
    year: int
    category: str
    urls: tuple[str, ...]
    required: tuple[str, ...]
    preferred_terms: tuple[str, ...] = ()
    official_hosts: tuple[str, ...] = ()
    min_pages: int = 2
    min_bytes: int = 12_000
    max_bytes: int = 250_000_000

ENTRIES: tuple[Entry, ...] = (
    Entry("FM_1-02.1_Operational_Terms_2026.pdf", "FM 1-02.1 Operational Terms", 2026, "Doctrine-Army", ("https://checkmyregs.com/pub/fm-1-02-1",), ("fm 1-02.1", "operational terms", "2026"), ("fm 1-02.1", "operational terms"), ("armypubs.army.mil",)),
    Entry("FM_2-0_Intelligence_2023.pdf", "FM 2-0 Intelligence", 2023, "Doctrine-Army", ("https://checkmyregs.com/pub/fm-2-0",), ("fm 2-0", "intelligence", "2023"), ("fm 2-0", "intelligence"), ("armypubs.army.mil",)),
    Entry("FM_3-01_US_Army_Air_and_Missile_Defense_Operations_2025.pdf", "FM 3-01 U.S. Army Air and Missile Defense Operations", 2025, "Doctrine-Army", ("https://checkmyregs.com/pub/fm-3-01",), ("fm 3-01", "air and missile defense", "2025"), ("fm 3-01", "air missile defense"), ("armypubs.army.mil",)),
    Entry("FM_3-04_Army_Aviation_2025.pdf", "FM 3-04 Army Aviation", 2025, "Doctrine-Army", ("https://checkmyregs.com/pub/fm-3-04",), ("fm 3-04", "army aviation", "2025"), ("fm 3-04", "army aviation"), ("armypubs.army.mil",)),
    Entry("FM_3-09_Fire_Support_and_Field_Artillery_Operations_2024.pdf", "FM 3-09 Fire Support and Field Artillery Operations", 2024, "Doctrine-Army", ("https://checkmyregs.com/pub/fm-3-09",), ("fm 3-09", "fire support", "2024"), ("fm 3-09", "fire support", "field artillery"), ("armypubs.army.mil",)),
    Entry("FM_3-14_Army_Space_Operations_2026.pdf", "FM 3-14 Army Space Operations", 2026, "Doctrine-Army", ("https://checkmyregs.com/pub/fm-3-14",), ("fm 3-14", "army space operations", "2026"), ("fm 3-14", "army space operations"), ("armypubs.army.mil",)),
    Entry("FM_4-0_Sustainment_Operations_2026.pdf", "FM 4-0 Sustainment Operations", 2026, "Doctrine-Army", ("https://armypubs.army.mil/epubs/DR_pubs/DR_a/ARN46157-FM_4-0-000-WEB-1.pdf", "https://checkmyregs.com/pub/fm-4-0"), ("fm 4-0", "sustainment operations", "2026"), ("fm 4-0", "sustainment operations"), ("armypubs.army.mil",)),
    Entry("FM_5-0_Planning_and_Orders_Production_2024.pdf", "FM 5-0 Planning and Orders Production", 2024, "Doctrine-Army", ("https://checkmyregs.com/pub/fm-5-0",), ("fm 5-0", "planning and orders production", "2024"), ("fm 5-0", "planning orders production"), ("armypubs.army.mil",)),
    Entry("AFDP_3-0_Operations_2025.pdf", "AFDP 3-0 Operations", 2025, "Doctrine-Air-Force", ("https://www.doctrine.af.mil/Portals/61/documents/AFDP_3-0/AFDP3-0Operations.pdf", "https://www.doctrine.af.mil/Operational-Level-Doctrine/AFDP-3-0-Operations/"), ("air force doctrine publication 3-0", "operations", "2025"), ("afdp 3-0", "operations"), ("doctrine.af.mil", "media.defense.gov")),
    Entry("AFDP_5-0_Planning_2025.pdf", "AFDP 5-0 Planning", 2025, "Doctrine-Air-Force", ("https://www.doctrine.af.mil/Portals/61/documents/AFDP_5-0/AFDP5-0Planning.pdf", "https://www.doctrine.af.mil/Operational-Level-Doctrine/AFDP-5-0-Planning/"), ("air force doctrine publication 5-0", "planning", "2025"), ("afdp 5-0", "planning"), ("doctrine.af.mil", "media.defense.gov")),
    Entry("AFDP_3-01_Counterair_Operations_2023.pdf", "AFDP 3-01 Counterair Operations", 2023, "Doctrine-Air-Force", ("https://www.doctrine.af.mil/Portals/61/documents/AFDP_3-01/3-01-AFDP-COUNTERAIR.pdf", "https://www.doctrine.af.mil/Operational-Level-Doctrine/AFDP-3-01-Counterair-Ops/"), ("air force doctrine publication 3-01", "counterair", "2023"), ("afdp 3-01", "counterair"), ("doctrine.af.mil", "media.defense.gov")),
    Entry("AFDN_1-21_Agile_Combat_Employment_2022_Current.pdf", "AFDN 1-21 Agile Combat Employment", 2022, "Doctrine-Air-Force", ("https://www.doctrine.af.mil/Operational-Level-Doctrine/AFDN-1-21-Agile-Combat-Employment/hss_channel/lcp-33207510/", "https://www.doctrine.af.mil/Operational-Level-Doctrine/AFDN-21-01-Agile-Combat-Employment/"), ("air force doctrine note 1-21", "agile combat employment", "2022"), ("afdn 1-21", "agile combat employment"), ("doctrine.af.mil", "media.defense.gov")),
    Entry("AFDP_3-14_Space_Support_2025.pdf", "AFDP 3-14 Space Support", 2025, "Doctrine-Air-Force", ("https://www.doctrine.af.mil/Operational-Level-Doctrine/AFDP-3-14-Space-Support/",), ("air force doctrine publication 3-14", "space support", "2025"), ("afdp 3-14", "space support"), ("doctrine.af.mil", "media.defense.gov")),
    Entry("USAF_Doctrine_Smart_Book_2026.pdf", "USAF Doctrine Smart Book", 2026, "Doctrine-Reference", ("https://www.doctrine.af.mil/Operational-Level-Doctrine/SmartBook/",), ("usaf doctrine smart book", "2026"), ("doctrine smart book",), ("doctrine.af.mil", "media.defense.gov")),

    Entry("CASI_Exploring_PRC_Research_on_Kill_Chains_and_Kill_Webs_2026.pdf", "Exploring PRC Research on Kill Chains and Kill Webs", 2026, "Adversary-Kill-Webs", ("https://www.airuniversity.af.edu/CASI/Display/Article/4528498/exploring-prc-research-on-kill-chains-and-kill-webs/",), ("exploring prc research", "kill chains", "kill webs", "2026"), ("kill chains", "kill webs", "full report"), ("airuniversity.af.edu", "media.defense.gov")),
    Entry("CASI_PLA_Concepts_of_UAV_Swarms_and_Manned_Unmanned_Teaming_2025.pdf", "PLA Concepts of UAV Swarms and Manned/Unmanned Teaming", 2025, "Adversary-Autonomy", ("https://www.airuniversity.af.edu/CASI/Display/Article/4147751/pla-concepts-of-uav-swarms-and-mannedunmanned-teaming/",), ("pla concepts", "uav swarms", "manned", "unmanned teaming", "2025"), ("uav swarms", "manned unmanned teaming"), ("airuniversity.af.edu", "media.defense.gov")),
    Entry("Air_University_Human_Machine_War_2025.pdf", "Human, Machine, War: How the Mind-Tech Nexus Will Win Future Wars", 2025, "Professional-Book", ("https://media.defense.gov/2025/Apr/18/2003694020/-1/-1/1/B-188%20HMW%20FINAL%204.8.25%20-%20WITH%20508%20CHECK.PDF", "https://www.airuniversity.af.edu/AUPress/Display/Article/4162241/human-machine-war-how-the-mind-tech-nexus-will-win-future-wars/"), ("human, machine, war", "mind-tech nexus", "2025"), ("human machine war", "mind tech nexus"), ("media.defense.gov", "airuniversity.af.edu"), min_pages=100),
    Entry("Army_University_Defining_Swarm_2025.pdf", "Defining Swarm: A Critical Step Toward Harnessing the Power of Autonomous Systems", 2025, "Professional-Article", ("https://www.armyupress.army.mil/journals/military-review/online-exclusive/2025-ole/defining-swarm/",), ("defining swarm", "autonomous systems", "2025"), ("download", "defining swarm"), ("armyupress.army.mil", "media.defense.gov")),
    Entry("Army_University_Unmanned_Aircraft_Revolution_in_Operational_Warfare_2025.pdf", "Unmanned Aircraft and the Revolution in Operational Warfare", 2025, "Professional-Article", ("https://www.armyupress.army.mil/Journals/Military-Review/English-Edition-Archives/July-August-2025/Unmanned-Aircraft-Revolution/",), ("unmanned aircraft", "revolution in operational warfare", "2025"), ("download", "unmanned aircraft revolution"), ("armyupress.army.mil", "media.defense.gov")),
    Entry("Army_University_Cunning_Tools_of_War_sUAS_Infiltration_2024.pdf", "Cunning Tools of War: Moving Beyond a Technology-Driven Understanding of sUAS Infiltration", 2024, "Professional-Article", ("https://www.armyupress.army.mil/Journals/Military-Review/English-Edition-Archives/Nov-Dec-2024/Cunning-Tools-of-War/",), ("cunning tools of war", "suas infiltration", "2024"), ("download", "cunning tools"), ("armyupress.army.mil", "media.defense.gov")),
    Entry("Army_University_Transforming_Multidomain_Battlefield_with_AI_2024.pdf", "Transforming the Multidomain Battlefield with AI", 2024, "Professional-Article", ("https://www.armyupress.army.mil/Journals/Military-Review/Online-Exclusive/2024-OLE/Multidomain-Battlefield-AI/",), ("transforming the multidomain battlefield with ai", "autonomous systems", "2024"), ("download", "multidomain battlefield ai"), ("armyupress.army.mil", "media.defense.gov")),
    Entry("Army_University_Restoring_Fires_and_Maneuver_2025.pdf", "Restoring Fires and Maneuver: An All-Arms Wave-Based Approach at the Tactical Edge", 2025, "Professional-Article", ("https://www.armyupress.army.mil/Journals/Military-Review/Online-Exclusive/2025-OLE/Restoring-Fires-and-Maneuver/",), ("restoring fires and maneuver", "tactical edge", "2025"), ("download", "restoring fires maneuver"), ("armyupress.army.mil", "media.defense.gov")),
    Entry("Army_University_Bayraktars_and_Grenade_Dropping_Quadcopters_II_2024.pdf", "Bayraktars and Grenade-Dropping Quadcopters II", 2024, "Professional-Article", ("https://www.armyupress.army.mil/Journals/Military-Review/Online-Exclusive/2024-OLE/Grenade-Dropping-Quadcopters-II/",), ("bayraktars", "grenade-dropping quadcopters", "2024"), ("download", "quadcopters"), ("armyupress.army.mil", "media.defense.gov")),
    Entry("NDU_Fabrication_at_the_Tactical_Edge_2025.pdf", "Fabrication at the Tactical Edge", 2025, "Industrial-Scaling", ("https://ndupress.ndu.edu/Media/News/News-Article-View/Article/4366244/fabrication-at-the-tactical-edge/",), ("fabrication at the tactical edge", "2025"), ("download pdf", "fabrication tactical edge"), ("ndupress.ndu.edu", "media.defense.gov")),

    Entry("CRS_DOD_Replicator_Initiative_2026.pdf", "DOD Replicator Initiative: Background and Issues for Congress", 2026, "Autonomy-at-Scale", ("https://crsreports.congress.gov/product/pdf/IF/IF12611", "https://www.congress.gov/crs-product/IF12611"), ("dod replicator initiative", "updated january 21, 2026"), ("replicator initiative",), ("crsreports.congress.gov", "congress.gov")),
    Entry("CRS_DoD_Counter_Unmanned_Aircraft_Systems_2025.pdf", "Department of Defense Counter Unmanned Aircraft Systems", 2025, "Counter-UAS", ("https://crsreports.congress.gov/product/pdf/R/R48477", "https://www.congress.gov/crs-product/R48477"), ("department of defense counter unmanned aircraft systems", "march 31, 2025"), ("counter unmanned aircraft systems",), ("crsreports.congress.gov", "congress.gov")),
    Entry("CRS_US_Army_Small_Uncrewed_Aircraft_Systems_Programs_2025.pdf", "U.S. Army Small Uncrewed Aircraft Systems Programs", 2025, "UAS-Programs", ("https://crsreports.congress.gov/product/pdf/IF/IF12668", "https://www.congress.gov/crs-product/IF12668"), ("u.s. army small uncrewed aircraft systems programs", "august 15, 2025"), ("army small uncrewed aircraft",), ("crsreports.congress.gov", "congress.gov")),
    Entry("CRS_Implementing_National_Defense_Industrial_Strategy_2024.pdf", "Implementing the National Defense Industrial Strategy", 2024, "Industrial-Base", ("https://crsreports.congress.gov/product/pdf/IN/IN12459", "https://www.congress.gov/crs-product/IN12459"), ("implementing the national defense industrial strategy", "november 19, 2024"), ("national defense industrial strategy",), ("crsreports.congress.gov", "congress.gov")),
    Entry("CRS_The_Defense_Innovation_Ecosystem_2025.pdf", "The Defense Innovation Ecosystem", 2025, "Innovation-Scaling", ("https://crsreports.congress.gov/product/pdf/IF/IF12869", "https://www.congress.gov/crs-product/IF12869"), ("the defense innovation ecosystem", "january 8, 2025"), ("defense innovation ecosystem",), ("crsreports.congress.gov", "congress.gov")),

    Entry("GAO_Defense_Acquisition_Reform_Iterative_Approaches_2025.pdf", "Defense Acquisition Reform: Persistent Challenges Require New Iterative Approaches", 2025, "Acquisition-Scaling", ("https://www.gao.gov/assets/gao-25-108528.pdf", "https://www.gao.gov/products/gao-25-108528"), ("defense acquisition reform", "iterative approaches", "2025"), ("full report", "gao-25-108528"), ("gao.gov",)),
    Entry("GAO_Modular_Open_Systems_Weapon_Systems_2025.pdf", "Weapon Systems Acquisition: DOD Needs Better Planning to Attain Benefits of Modular Open Systems", 2025, "Open-Architecture", ("https://www.gao.gov/assets/gao-25-106931.pdf", "https://www.gao.gov/products/gao-25-106931"), ("weapon systems acquisition", "modular open systems", "2025"), ("full report", "gao-25-106931"), ("gao.gov",)),
    Entry("GAO_Advanced_Manufacturing_2025.pdf", "Advanced Manufacturing: Aligning Strategies and Improving Agency Reviews", 2025, "Industrial-Scaling", ("https://www.gao.gov/assets/gao-25-107369.pdf", "https://www.gao.gov/products/gao-25-107369"), ("advanced manufacturing", "aligning strategies", "2025"), ("full report", "gao-25-107369"), ("gao.gov",)),
    Entry("GAO_Defense_Production_Act_Information_Sharing_2025.pdf", "Defense Production Act: Information Sharing Needed to Improve Use of Authorities", 2025, "Industrial-Mobilization", ("https://www.gao.gov/assets/gao-25-107688.pdf", "https://www.gao.gov/products/gao-25-107688"), ("defense production act", "information sharing", "2025"), ("full report", "gao-25-107688"), ("gao.gov",)),
    Entry("GAO_DoD_Satellite_Communications_Enterprise_2025.pdf", "DOD Satellite Communications: Reporting on Progress Needed", 2025, "Resilient-Networks", ("https://www.gao.gov/assets/gao-25-107034.pdf", "https://www.gao.gov/products/gao-25-107034"), ("dod satellite communications", "reporting on progress", "2025"), ("full report", "gao-25-107034"), ("gao.gov",)),
    Entry("DoD_National_Defense_Industrial_Strategy_2024.pdf", "National Defense Industrial Strategy", 2024, "Industrial-Base", ("https://www.businessdefense.gov/docs/ndis/2023-NDIS.pdf", "https://www.businessdefense.gov/NDIS.html", "https://www.defense.gov/News/Releases/Release/Article/3643326/dod-releases-first-defense-industrial-strategy/"), ("national defense industrial strategy", "2024"), ("download", "industrial strategy"), ("businessdefense.gov", "media.defense.gov", "defense.gov")),
    Entry("DoD_NDIS_Implementation_Plan_FY2025.pdf", "National Defense Industrial Strategy Implementation Plan for FY2025", 2024, "Industrial-Base", ("https://www.govinfo.gov/app/details/GOVPUB-D-PURL-gpo234260", "https://www.defense.gov/News/News-Stories/Article/Article/3949630/dod-lays-out-plan-to-implement-national-defense-industrial-strategy/"), ("national defense industrial strategy implementation plan", "fy2025"), ("download pdf", "implementation plan"), ("govinfo.gov", "media.defense.gov", "defense.gov")),
    Entry("DoD_Intellectual_Property_Guidebook_for_Acquisition_2025.pdf", "Intellectual Property Guidebook for DoD Acquisition", 2025, "Acquisition-Open-Architecture", ("https://www.acq.osd.mil/asda/dpc/api/docs/intellectual%20property%20guidebook%20for%20dod%20acquisition%20signed.pdf",), ("intellectual property guidebook", "dod acquisition", "2025"), ("intellectual property guidebook",), ("acq.osd.mil",)),
    Entry("PPBE_Commission_Defense_Resourcing_for_the_Future_Final_Report_2024.pdf", "Defense Resourcing for the Future: Final Report", 2024, "Resourcing-Scaling", ("https://ppbereform.senate.gov/wp-content/uploads/2024/03/Commission-on-PPBE-Reform_Full-Report_6-March-2024_FINAL.pdf", "https://budget.house.gov/press-release/ppbe-commission-releases-final-report-defense-resourcing-for-the-future"), ("defense resourcing for the future", "final report", "2024"), ("ppbe reform", "final report"), ("ppbereform.senate.gov", "budget.house.gov")),
    Entry("Defense_Innovation_Board_Pathway_to_Scaling_Unmanned_Weapon_Systems_2025.pdf", "A Pathway to Scaling Unmanned Weapon Systems", 2025, "Autonomy-at-Scale", ("https://stib.cto.mil/products-dib/",), ("pathway to scaling unmanned weapon systems", "2025"), ("pathway scaling unmanned weapon systems",), ("stib.cto.mil", "media.defense.gov")),
    Entry("Defense_Innovation_Board_Scaling_Nontraditional_Defense_Innovation_2025.pdf", "Scaling Nontraditional Defense Innovation", 2025, "Innovation-Scaling", ("https://stib.cto.mil/products-dib/",), ("scaling nontraditional defense innovation", "2025"), ("scaling nontraditional defense innovation",), ("stib.cto.mil", "media.defense.gov")),
    Entry("Defense_Innovation_Board_Building_a_DoD_Data_Economy_2024.pdf", "Building a DoD Data Economy", 2024, "Data-Architecture", ("https://stib.cto.mil/products-dib/",), ("building a dod data economy", "2024"), ("building dod data economy",), ("stib.cto.mil", "media.defense.gov")),

    Entry("RUSI_Tactical_Developments_Third_Year_Russo_Ukrainian_War_2025.pdf", "Tactical Developments During the Third Year of the Russo-Ukrainian War", 2025, "Operational-Lessons", ("https://www.rusi.org/explore-our-research/publications/special-resources/tactical-developments-during-third-year-russo-ukrainian-war",), ("tactical developments", "third year", "russo-ukrainian war", "2025"), ("download", "tactical developments"), ("rusi.org", "static.rusi.org")),
    Entry("RUSI_Mass_Precision_Strike_Designing_UAV_Complexes_2024.pdf", "Mass Precision Strike: Designing UAV Complexes for Land Forces", 2024, "UAS-Mass", ("https://www.rusi.org/explore-our-research/publications/occasional-papers/mass-precision-strike-designing-uav-complexes-land-forces",), ("mass precision strike", "uav complexes", "2024"), ("download", "mass precision strike"), ("rusi.org", "static.rusi.org")),
    Entry("RUSI_Winning_the_Industrial_War_2025.pdf", "Winning the Industrial War: Comparing Russia, Europe and Ukraine, 2022-24", 2025, "Industrial-Warfare", ("https://www.rusi.org/explore-our-research/publications/occasional-papers/winning-industrial-war-comparing-russia-europe-and-ukraine-2022-24",), ("winning the industrial war", "russia", "europe", "ukraine", "2025"), ("download", "industrial war"), ("rusi.org", "static.rusi.org")),
    Entry("RUSI_Drones_Decoupling_Supply_Chains_from_China_2025.pdf", "Drones: Decoupling Supply Chains from China", 2025, "UAS-Supply-Chain", ("https://www.rusi.org/explore-our-research/publications/research-papers/drones-decoupling-supply-chains-china",), ("drones", "decoupling supply chains", "china", "2025"), ("download", "decoupling supply chains"), ("rusi.org", "static.rusi.org")),
    Entry("CNAS_Countering_the_Swarm_2025.pdf", "Countering the Swarm: Protecting the Joint Force in the Drone Age", 2025, "Counter-UAS", ("https://www.cnas.org/publications/reports/countering-the-swarm",), ("countering the swarm", "joint force", "drone age", "2025"), ("download", "countering swarm"), ("cnas.org", "files.cnas.org")),
    Entry("CNAS_Hellscape_for_Taiwan_2026.pdf", "Hellscape for Taiwan: Rethinking Asymmetric Defense", 2026, "UAS-Mass", ("https://www.cnas.org/publications/reports/hellscape-for-taiwan",), ("hellscape for taiwan", "asymmetric defense", "2026"), ("download", "hellscape taiwan"), ("cnas.org", "files.cnas.org")),
    Entry("CSIS_Unleashing_US_Military_Drone_Dominance_2025.pdf", "Unleashing U.S. Military Drone Dominance", 2025, "UAS-Industrial-Base", ("https://www.csis.org/analysis/unleashing-us-military-drone-dominance-what-united-states-can-learn-ukraine",), ("unleashing u.s. military drone dominance", "ukraine", "2025"), ("download", "drone dominance"), ("csis.org", "csis-website-prod.s3.amazonaws.com")),
    Entry("CSIS_Ukraine_AI_Enabled_Autonomous_Warfare_2025.pdf", "Ukraine's Future Vision and Current Capabilities for Waging AI-Enabled Autonomous Warfare", 2025, "Autonomy-Lessons", ("https://www.csis.org/analysis/ukraines-future-vision-and-current-capabilities-waging-ai-enabled-autonomous-warfare",), ("ukraine", "ai-enabled autonomous warfare", "2025"), ("download", "autonomous warfare"), ("csis.org", "csis-website-prod.s3.amazonaws.com")),
    Entry("Atlantic_Council_Software_Defined_Warfare_Final_Report_2025.pdf", "Commission on Software-Defined Warfare Final Report", 2025, "Software-Defined-Warfare", ("https://www.atlanticcouncil.org/in-depth-research-reports/report/atlantic-council-commission-on-software-defined-warfare/",), ("software-defined warfare", "final report", "2025"), ("download", "software defined warfare"), ("atlanticcouncil.org", "acus.org")),
    Entry("Belfer_Autonomous_Arsenal_in_Defense_of_Taiwan_2025.pdf", "The Autonomous Arsenal in Defense of Taiwan", 2025, "Autonomy-at-Scale", ("https://www.belfercenter.org/replicator-autonomous-weapons-taiwan",), ("autonomous arsenal", "defense of taiwan", "2025"), ("download full report", "autonomous arsenal"), ("belfercenter.org",)),
)

def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").replace("–", "-").replace("—", "-").replace("‑", "-").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9.]+", " ", text)).strip()

def hostname(url: str) -> str:
    try: return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception: return ""

def host_allowed(url: str, allowed: tuple[str, ...]) -> bool:
    if not allowed: return True
    host = hostname(url)
    return any(host == x or host.endswith("." + x) for x in allowed)

class Downloader:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,application/xhtml+xml,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"})

    def get(self, url: str, timeout: int = 75) -> requests.Response:
        last = None
        for attempt in range(4):
            try:
                r = self.session.get(url, timeout=timeout, allow_redirects=True)
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** attempt); continue
                return r
            except Exception as exc:
                last = exc; time.sleep(2 ** attempt)
        raise RuntimeError(f"GET failed {url}: {last}")

    def candidate_links(self, html: str, base_url: str, entry: Entry) -> list[tuple[int, str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        candidates: dict[str, tuple[int, str]] = {}
        target_terms = [norm(x) for x in (entry.preferred_terms or entry.required)]
        def add(raw: str | None, label: str = "", base_score: int = 0) -> None:
            if not raw: return
            raw = raw.strip().replace("&amp;", "&")
            if raw.startswith(("javascript:", "mailto:", "#")): return
            u = urllib.parse.urljoin(base_url, raw)
            if not u.startswith(("http://", "https://")): return
            blob = norm(label + " " + u); score = base_score
            if ".pdf" in u.lower() or "format=pdf" in u.lower() or "/product/pdf/" in u.lower(): score += 120
            if any(k in blob for k in ("download pdf", "download full", "full report", "read full", "download report", "download")): score += 45
            score += sum(18 for t in target_terms if t and t in blob)
            if host_allowed(u, entry.official_hosts): score += 20
            if any(bad in blob for bad in ("privacy", "accessibility", "annual report")) and not any(t in blob for t in target_terms): score -= 100
            old = candidates.get(u)
            if old is None or score > old[0]: candidates[u] = (score, label)
        for meta_name in ("citation_pdf_url", "dc.identifier", "eprints.document_url", "pdf_url"):
            for tag in soup.find_all("meta", attrs={"name": re.compile(f"^{re.escape(meta_name)}$", re.I)}): add(tag.get("content"), meta_name, 160)
        for tag in soup.find_all("meta", attrs={"property": re.compile(r"(pdf|document)", re.I)}): add(tag.get("content"), str(tag.get("property")), 130)
        for tag in soup.find_all(["a", "iframe", "embed", "object", "link"]):
            raw = tag.get("href") or tag.get("src") or tag.get("data")
            label = " ".join(tag.stripped_strings) if hasattr(tag, "stripped_strings") else ""
            add(raw, label)
        for m in re.finditer(r"https?:\\?/\\?/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+?\.pdf(?:\?[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?", html, re.I): add(m.group(0).replace("\\/", "/"), "script pdf", 125)
        for m in re.finditer(r"(?:href|src|url)[\"'=: ]{1,8}([^\"'<> ]+\.pdf(?:\?[^\"'<> ]*)?)", html, re.I): add(m.group(1), "regex pdf", 120)
        ranked = [(score, url, label) for url, (score, label) in candidates.items()]
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked

    def resolve(self, entry: Entry) -> tuple[bytes, str, list[str]]:
        errors: list[str] = []; visited: set[str] = set()
        def probe(url: str, depth: int):
            if url in visited or depth > 2: return None
            visited.add(url)
            try: r = self.get(url)
            except Exception as exc: errors.append(f"{url}: {exc}"); return None
            data = r.content; ctype = (r.headers.get("content-type") or "").lower()
            if data[:5] == b"%PDF-" or "application/pdf" in ctype:
                if data[:5] != b"%PDF-": errors.append(f"{url}: PDF content-type without PDF magic"); return None
                return data, r.url
            if r.status_code >= 400: errors.append(f"{url}: HTTP {r.status_code}"); return None
            text = data.decode(r.encoding or "utf-8", errors="replace")
            links = self.candidate_links(text, r.url, entry)
            if not links and depth == 0:
                try:
                    jr = self.get("https://r.jina.ai/http://" + r.url.split("://", 1)[-1])
                    links = self.candidate_links(jr.text, r.url, entry)
                except Exception as exc: errors.append(f"jina {r.url}: {exc}")
            for score, candidate, _ in links[:35]:
                if score < 10: continue
                out = probe(candidate, depth + 1)
                if out is not None: return out
            errors.append(f"{url}: no usable PDF candidate ({len(links)} links inspected)")
            return None
        for source in entry.urls:
            out = probe(source, 0)
            if out is not None: return out[0], out[1], errors
        raise RuntimeError(" | ".join(errors[-12:]) or "no source succeeded")

def pdf_text_and_pages(data: bytes, page_limit: int = 16):
    reader = PdfReader(io.BytesIO(data), strict=False); pages = len(reader.pages); metadata = reader.metadata or {}
    meta_text = " ".join(str(v) for v in metadata.values() if v); chunks = [meta_text]
    for page in reader.pages[:min(page_limit, pages)]:
        try: chunks.append(page.extract_text() or "")
        except Exception: pass
    return "\n".join(chunks), pages, meta_text

def validate(entry: Entry, data: bytes, final_url: str) -> dict:
    if not data.startswith(b"%PDF-"): raise ValueError("missing PDF signature")
    if len(data) < entry.min_bytes: raise ValueError(f"file too small: {len(data)} bytes")
    if len(data) > entry.max_bytes: raise ValueError(f"file too large: {len(data)} bytes")
    if entry.official_hosts and not host_allowed(final_url, entry.official_hosts): raise ValueError(f"final host is not approved: {hostname(final_url)}")
    text, pages, metadata = pdf_text_and_pages(data)
    if pages < entry.min_pages: raise ValueError(f"only {pages} pages")
    ntext = norm(text); missing = [token for token in entry.required if norm(token) not in ntext]
    if missing: raise ValueError(f"content check failed; missing {missing}")
    sha = hashlib.sha256(data).hexdigest()
    if sha in EXISTING_HASHES: raise ValueError("binary duplicate of an existing Project Source")
    return {"sha256": sha, "bytes": len(data), "pages": pages, "final_url": final_url, "metadata": metadata[:500]}

def main() -> int:
    shutil.rmtree(OUT_DIR, ignore_errors=True); OUT_DIR.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists(): ZIP_PATH.unlink()
    dl = Downloader(); accepted = []; rejected = []; batch_hashes = set()
    for idx, entry in enumerate(ENTRIES, 1):
        print(f"\n[{idx}/{len(ENTRIES)}] {entry.title}", flush=True)
        try:
            data, final_url, notes = dl.resolve(entry); info = validate(entry, data, final_url)
            if info["sha256"] in batch_hashes: raise ValueError("duplicate PDF within Pass 2")
            batch_hashes.add(info["sha256"]); (OUT_DIR / entry.filename).write_bytes(data)
            accepted.append({"filename": entry.filename, "title": entry.title, "year": entry.year, "category": entry.category, **info, "resolver_notes": notes[-5:]})
            print(f"ACCEPTED: {entry.filename} | {info['pages']} pp | {info['bytes']/1e6:.1f} MB | {final_url}", flush=True)
        except Exception as exc:
            rejected.append({"filename": entry.filename, "title": entry.title, "year": entry.year, "category": entry.category, "error": str(exc), "sources": list(entry.urls)})
            print(f"REJECTED: {exc}", flush=True)
    doctrine_count = sum(1 for r in accepted if r["category"].startswith("Doctrine"))
    if len(accepted) < 20 or doctrine_count < 6:
        REPORT_PATH.write_text(json.dumps({"accepted": accepted, "rejected": rejected}, indent=2), encoding="utf-8")
        print(f"Insufficient corpus: {len(accepted)} total, {doctrine_count} doctrine", file=sys.stderr); return 2
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for pdf in sorted(OUT_DIR.glob("*.pdf"), key=lambda p: p.name.lower()): zf.write(pdf, arcname=f"{OUT_DIR.name}/{pdf.name}")
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = zf.namelist(); assert names and len(names) == len(accepted) and len(names) == len(set(names))
        assert all(n.startswith(f"{OUT_DIR.name}/") and n.lower().endswith(".pdf") for n in names)
        for name in names:
            with zf.open(name) as member: assert member.read(5) == b"%PDF-"
    report = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "candidate_count": len(ENTRIES), "accepted_count": len(accepted), "rejected_count": len(rejected), "doctrine_count": doctrine_count, "zip": str(ZIP_PATH), "zip_bytes": ZIP_PATH.stat().st_size, "zip_sha256": hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest(), "accepted": accepted, "rejected": rejected}
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nPASS2_SUMMARY_JSON=" + json.dumps({"accepted": len(accepted), "rejected": len(rejected), "doctrine": doctrine_count, "zip_bytes": ZIP_PATH.stat().st_size, "zip_sha256": report["zip_sha256"], "filenames": [r["filename"] for r in accepted], "rejections": [{"filename": r["filename"], "error": r["error"]} for r in rejected]}), flush=True)
    return 0

if __name__ == "__main__": raise SystemExit(main())
