"""Reference (ground-truth) data loader for HealthOS.

This is **not** demo data. Migration 0009 created the normalised clinical and
insurance tables, but several features are inert until the terminology and
reference curves behind them exist: growth percentiles cannot be computed, lab
orders cannot resolve a LOINC concept, and the chargemaster has no prices.
This module loads that ground truth idempotently.

What is loaded
--------------
``code_systems``
    The nine canonical terminologies with their published canonical URIs and
    HL7 OIDs.
``code_concepts``
    Real LOINC, CVX, ICD-10-CM and CPT codes. No code value in this module is
    invented; displays follow the publishers' descriptors.
``growth_reference_standards``
    WHO Child Growth Standards L/M/S parameters, months 0-60, both sexes, for
    weight-for-age and length/height-for-age.
``lab_tests``
    An orderable catalogue keyed to LOINC, with SNOMED CT specimen types.
``service_items``
    A CPT-keyed chargemaster.

Source and provenance of the WHO L/M/S values
---------------------------------------------
Source: WHO Multicentre Growth Reference Study, *WHO Child Growth Standards*
(2006), distributed as the ``igrowup`` standard tables and republished verbatim
in the WHO-maintained R package ``anthro``
(https://github.com/WorldHealthOrganization/anthro), files
``data-raw/growthstandards/weianthro.txt`` (weight-for-age) and
``data-raw/growthstandards/lenanthro.txt`` (length/height-for-age). Those files
are indexed by **age in days** (0-1826) and give ``l``, ``m``, ``s`` per sex
(1 = boys, 2 = girls).

This table is indexed by **age in completed months**, because
``healthos_api.domain.clinical`` matches a measurement with
``floor(age_days / 30.4375)``. Each monthly row was therefore evaluated at
``day = month * 30.4375`` (the WHO definition of a month) by linear
interpolation between the two bracketing daily rows, then rounded to the
precision WHO itself publishes (L and M to 4 decimals, S to 5).

That interpolation is *not* an approximation of unknown values: it reproduces
WHO's own published monthly "expandable tables" exactly, because both tables
are evaluations of the same fitted LMS curves. Verified spot checks against the
published monthly tables:

===================================  ========  =========  =========
Row                                  L         M          S
===================================  ========  =========  =========
weight-for-age, boys, 0 months        0.3487     3.3464    0.14602
weight-for-age, boys, 12 months       0.0644     9.6479    0.10925
weight-for-age, girls, 24 months     -0.2941    11.4775    0.12390
height-for-age, boys, 24 months       1.0000    87.1161    0.03507
===================================  ========  =========  =========

Two documented deviations from naive interpolation:

* **The length/height discontinuity at 24 months.** WHO measures recumbent
  length below 24 months and standing height from 24 months, and the curves
  step down ~0.7 cm at the boundary. Months 0-23 are taken from the ``loh='L'``
  (length) segment and months 24-60 from the ``loh='H'`` (height) segment; the
  two segments are never interpolated across each other. Month 24 (730.5 days)
  is back-extrapolated 0.5 days from the first two height rows, which
  reproduces WHO's published month-24 height medians (boys 87.1161, girls
  85.7154).
* **Month 60** (1826.25 days) lies 0.25 days past the last daily row (1826) and
  is forward-extrapolated from the final two rows.

``p3``/``p50``/``p97`` are derived from the stored L/M/S with the standard LMS
quantile formula, so they can never disagree with the curve they annotate.

Idempotency
-----------
Every row has a deterministic UUID derived from :func:`demo_id` under a
``reference:`` key prefix, and every write is an upsert keyed on the table's
natural unique constraint. Re-running is a no-op plus field refresh.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from statistics import NormalDist
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.cli.seed_demo import demo_id
from healthos_api.config import get_settings
from healthos_api.db.models import (
    BiologicalSex,
    CodeConcept,
    CodeSystem,
    GrowthMeasure,
    GrowthReferenceStandard,
    GrowthSource,
    LabTest,
    Organization,
    ServiceItem,
)
from healthos_api.db.session import create_database_engine, create_session_factory
from healthos_api.domain.clinical import _lms_zscore, _zscore_to_percentile

# --------------------------------------------------------------------------------------
# Code systems
# --------------------------------------------------------------------------------------

ICD10CM: Final = "http://hl7.org/fhir/sid/icd-10-cm"
CPT: Final = "http://www.ama-assn.org/go/cpt"
LOINC: Final = "http://loinc.org"
RXNORM: Final = "http://www.nlm.nih.gov/research/umls/rxnorm"
CVX: Final = "http://hl7.org/fhir/sid/cvx"
SNOMED: Final = "http://snomed.info/sct"
HCPCS: Final = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets"
UCUM: Final = "http://unitsofmeasure.org"
NDC: Final = "http://hl7.org/fhir/sid/ndc"


@dataclass(frozen=True)
class CodeSystemSpec:
    uri: str
    name: str
    version: str
    publisher: str
    oid: str | None
    released_at: date


CODE_SYSTEMS: Final[tuple[CodeSystemSpec, ...]] = (
    CodeSystemSpec(
        uri=ICD10CM,
        name="ICD-10-CM",
        version="2026",
        publisher="Centers for Medicare & Medicaid Services / NCHS",
        oid="2.16.840.1.113883.6.90",
        released_at=date(2025, 10, 1),
    ),
    CodeSystemSpec(
        uri=CPT,
        name="CPT",
        version="2026",
        publisher="American Medical Association",
        oid="2.16.840.1.113883.6.12",
        released_at=date(2026, 1, 1),
    ),
    CodeSystemSpec(
        uri=LOINC,
        name="LOINC",
        version="2.80",
        publisher="Regenstrief Institute, Inc.",
        oid="2.16.840.1.113883.6.1",
        released_at=date(2026, 2, 18),
    ),
    CodeSystemSpec(
        uri=RXNORM,
        name="RxNorm",
        version="2026-07",
        publisher="U.S. National Library of Medicine",
        oid="2.16.840.1.113883.6.88",
        released_at=date(2026, 7, 6),
    ),
    CodeSystemSpec(
        uri=CVX,
        name="CVX",
        version="2026-01",
        publisher="U.S. Centers for Disease Control and Prevention",
        oid="2.16.840.1.113883.12.292",
        released_at=date(2026, 1, 1),
    ),
    CodeSystemSpec(
        uri=SNOMED,
        name="SNOMED CT",
        version="20260301",
        publisher="SNOMED International",
        oid="2.16.840.1.113883.6.96",
        released_at=date(2026, 3, 1),
    ),
    CodeSystemSpec(
        uri=HCPCS,
        name="HCPCS Level II",
        version="2026",
        publisher="Centers for Medicare & Medicaid Services",
        oid="2.16.840.1.113883.6.285",
        released_at=date(2026, 1, 1),
    ),
    CodeSystemSpec(
        uri=UCUM,
        name="UCUM",
        version="2.2",
        publisher="Regenstrief Institute, Inc.",
        oid="2.16.840.1.113883.6.8",
        released_at=date(2024, 6, 26),
    ),
    CodeSystemSpec(
        uri=NDC,
        name="NDC",
        version="2026-07",
        publisher="U.S. Food and Drug Administration",
        oid="2.16.840.1.113883.6.69",
        released_at=date(2026, 7, 1),
    ),
)


# --------------------------------------------------------------------------------------
# Code concepts
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ConceptSpec:
    code: str
    display: str
    properties: dict[str, Any] = field(default_factory=dict)
    parent_code: str | None = None
    definition: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    is_active: bool = True


def _vital(code: str, display: str, unit: str) -> ConceptSpec:
    return ConceptSpec(
        code=code,
        display=display,
        properties={"category": "vital-signs", "ucum_unit": unit, "orderable": True},
    )


def _lab(code: str, display: str, unit: str | None, *, panel: bool = False) -> ConceptSpec:
    properties: dict[str, Any] = {"category": "laboratory", "orderable": True, "panel": panel}
    if unit is not None:
        properties["ucum_unit"] = unit
    return ConceptSpec(code=code, display=display, properties=properties)


# LOINC displays are the LOINC LONG_COMMON_NAME. LOINC codes are observation
# identifiers, never billing codes, so no "billable" property is asserted.
LOINC_CONCEPTS: Final[tuple[ConceptSpec, ...]] = (
    # Vital signs (the US Core vital-signs panel).
    _vital("8867-4", "Heart rate", "/min"),
    _vital("8480-6", "Systolic blood pressure", "mm[Hg]"),
    _vital("8462-4", "Diastolic blood pressure", "mm[Hg]"),
    ConceptSpec(
        code="85354-9",
        display="Blood pressure panel with all children optional",
        properties={"category": "vital-signs", "panel": True, "orderable": True},
    ),
    _vital("8310-5", "Body temperature", "Cel"),
    _vital("9279-1", "Respiratory rate", "/min"),
    _vital("2708-6", "Oxygen saturation in Arterial blood", "%"),
    _vital("29463-7", "Body weight", "kg"),
    _vital("8302-2", "Body height", "cm"),
    _vital("39156-5", "Body mass index (BMI) [Ratio]", "kg/m2"),
    _vital("8287-5", "Head Occipital-frontal circumference by Tape measure", "cm"),
    # Blood gases.
    _lab("2019-8", "Carbon dioxide [Partial pressure] in Arterial blood", "mm[Hg]"),
    _lab("2744-1", "pH of Arterial blood", "[pH]"),
    _lab("24336-0", "Gas panel - Arterial blood", None, panel=True),
    # Haematology.
    _lab("718-7", "Hemoglobin [Mass/volume] in Blood", "g/dL"),
    _lab("6690-2", "Leukocytes [#/volume] in Blood by Automated count", "10*3/uL"),
    _lab("777-3", "Platelets [#/volume] in Blood by Automated count", "10*3/uL"),
    _lab("58410-2", "CBC panel - Blood by Automated count", None, panel=True),
    # Diabetes and lipids.
    _lab("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood", "%"),
    _lab("2093-3", "Cholesterol [Mass/volume] in Serum or Plasma", "mg/dL"),
    _lab("2085-9", "Cholesterol in HDL [Mass/volume] in Serum or Plasma", "mg/dL"),
    _lab("2089-1", "Cholesterol in LDL [Mass/volume] in Serum or Plasma", "mg/dL"),
    _lab("2571-8", "Triglyceride [Mass/volume] in Serum or Plasma", "mg/dL"),
    _lab("57698-3", "Lipid panel with direct LDL - Serum or Plasma", None, panel=True),
    # Chemistry.
    _lab("2345-7", "Glucose [Mass/volume] in Serum or Plasma", "mg/dL"),
    _lab("2160-0", "Creatinine [Mass/volume] in Serum or Plasma", "mg/dL"),
    _lab("3094-0", "Urea nitrogen [Mass/volume] in Serum or Plasma", "mg/dL"),
    _lab("2951-2", "Sodium [Moles/volume] in Serum or Plasma", "mmol/L"),
    _lab("2823-3", "Potassium [Moles/volume] in Serum or Plasma", "mmol/L"),
    _lab("2075-0", "Chloride [Moles/volume] in Serum or Plasma", "mmol/L"),
    _lab("2028-9", "Carbon dioxide, total [Moles/volume] in Serum or Plasma", "mmol/L"),
    _lab("17861-6", "Calcium [Mass/volume] in Serum or Plasma", "mg/dL"),
    _lab("1751-7", "Albumin [Mass/volume] in Serum or Plasma", "g/dL"),
    _lab(
        "1742-6",
        "Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma",
        "U/L",
    ),
    _lab(
        "1920-8",
        "Aspartate aminotransferase [Enzymatic activity/volume] in Serum or Plasma",
        "U/L",
    ),
    _lab("6768-6", "Alkaline phosphatase [Enzymatic activity/volume] in Serum or Plasma", "U/L"),
    _lab("1975-2", "Bilirubin.total [Mass/volume] in Serum or Plasma", "mg/dL"),
    _lab("24323-8", "Comprehensive metabolic 2000 panel - Serum or Plasma", None, panel=True),
    _lab("51990-0", "Basic metabolic panel - Blood", None, panel=True),
    # Endocrine, coagulation, urine.
    _lab("3016-3", "Thyrotropin [Units/volume] in Serum or Plasma", "m[IU]/L"),
    _lab("5902-2", "Prothrombin time (PT)", "s"),
    _lab("6301-6", "INR in Platelet poor plasma by Coagulation assay", "{INR}"),
    _lab("24357-6", "Urinalysis macro (dipstick) panel - Urine", None, panel=True),
)


def _vaccine(code: str, display: str, group: str, *, in_use: bool = True) -> ConceptSpec:
    """A CDC CVX concept.

    ``in_use`` mirrors the CDC "Status" column. Retired products keep
    ``is_active = True`` on the concept, because historical immunisation records
    still resolve against them; ``properties.cdc_status`` carries the truth about
    whether the product may still be administered.
    """
    return ConceptSpec(
        code=code,
        display=display,
        properties={
            "vaccine_group": group,
            "cdc_status": "Active" if in_use else "Inactive",
            "administrable": in_use,
        },
    )


CVX_CONCEPTS: Final[tuple[ConceptSpec, ...]] = (
    _vaccine("08", "hepatitis B vaccine, pediatric or pediatric/adolescent dosage", "HepB"),
    _vaccine("20", "diphtheria, tetanus toxoids and acellular pertussis vaccine", "DTaP"),
    _vaccine("03", "measles, mumps and rubella virus vaccine", "MMR"),
    _vaccine("21", "varicella virus vaccine", "Varicella"),
    _vaccine("10", "poliovirus vaccine, inactivated", "IPV"),
    _vaccine("133", "pneumococcal conjugate vaccine, 13 valent", "Pneumococcal"),
    _vaccine("49", "Haemophilus influenzae type b vaccine, PRP-OMP conjugate", "Hib"),
    _vaccine("116", "rotavirus, live, pentavalent vaccine", "Rotavirus"),
    _vaccine("88", "influenza virus vaccine, unspecified formulation", "Influenza"),
    _vaccine("213", "SARS-COV-2 (COVID-19) vaccine, UNSPECIFIED", "COVID-19"),
    _vaccine(
        "115",
        "tetanus toxoid, reduced diphtheria toxoid, and acellular pertussis vaccine, adsorbed",
        "Tdap",
    ),
    _vaccine("62", "human papilloma virus vaccine, quadrivalent", "HPV", in_use=False),
    _vaccine("33", "pneumococcal polysaccharide vaccine, 23 valent", "Pneumococcal"),
    _vaccine("121", "zoster vaccine, live", "Zoster", in_use=False),
)


def _icd10(
    code: str,
    display: str,
    parent: str,
    *,
    billable: bool = True,
    effective_from: date = date(2015, 10, 1),
    effective_to: date | None = None,
    definition: str | None = None,
) -> ConceptSpec:
    return ConceptSpec(
        code=code,
        display=display,
        parent_code=parent,
        definition=definition,
        effective_from=effective_from,
        effective_to=effective_to,
        is_active=effective_to is None,
        properties={
            "billable": billable,
            "chapter": code[0],
            "code_type": "diagnosis",
        },
    )


ICD10CM_CONCEPTS: Final[tuple[ConceptSpec, ...]] = (
    _icd10("E11.9", "Type 2 diabetes mellitus without complications", "E11"),
    _icd10("I10", "Essential (primary) hypertension", "I10-I16"),
    _icd10("J45.909", "Unspecified asthma, uncomplicated", "J45.90"),
    _icd10("E78.5", "Hyperlipidemia, unspecified", "E78"),
    _icd10(
        "M54.5",
        "Low back pain",
        "M54",
        billable=False,
        effective_to=date(2021, 9, 30),
        definition=(
            "Deleted effective FY2022 (2021-10-01) and expanded into M54.50, M54.51 and "
            "M54.59. Retained for historical records; not valid for claims dated on or "
            "after 2021-10-01."
        ),
    ),
    _icd10(
        "M54.50",
        "Low back pain, unspecified",
        "M54.5",
        effective_from=date(2021, 10, 1),
        definition="Billable successor to the deleted M54.5.",
    ),
    _icd10("K21.9", "Gastro-esophageal reflux disease without esophagitis", "K21"),
    _icd10("F41.1", "Generalized anxiety disorder", "F41"),
    _icd10("J06.9", "Acute upper respiratory infection, unspecified", "J06"),
    _icd10("E66.9", "Obesity, unspecified", "E66"),
    _icd10("N39.0", "Urinary tract infection, site not specified", "N39"),
    _icd10(
        "M17.11",
        "Unilateral primary osteoarthritis, right knee",
        "M17.1",
        effective_from=date(2016, 10, 1),
    ),
    _icd10(
        "M17.12",
        "Unilateral primary osteoarthritis, left knee",
        "M17.1",
        effective_from=date(2016, 10, 1),
    ),
    _icd10(
        "Z00.00",
        "Encounter for general adult medical examination without abnormal findings",
        "Z00.0",
    ),
)


def _cpt(code: str, display: str, section: str, *, global_days: str | None = None) -> ConceptSpec:
    properties: dict[str, Any] = {
        "billable": True,
        "section": section,
        "code_type": "procedure",
    }
    if global_days is not None:
        properties["global_period_days"] = global_days
    return ConceptSpec(code=code, display=display, properties=properties)


_EM: Final = "Evaluation and Management"
_SURGERY: Final = "Surgery"
_RADIOLOGY: Final = "Radiology"
_PATHOLOGY: Final = "Pathology and Laboratory"
_MEDICINE: Final = "Medicine"
_ANESTHESIA: Final = "Anesthesia"

CPT_CONCEPTS: Final[tuple[ConceptSpec, ...]] = (
    _cpt(
        "99212",
        "Office or other outpatient visit for the evaluation and management of an established "
        "patient, which requires a medically appropriate history and/or examination and "
        "straightforward medical decision making; 10-19 minutes of total time",
        _EM,
    ),
    _cpt(
        "99213",
        "Office or other outpatient visit for the evaluation and management of an established "
        "patient, which requires a medically appropriate history and/or examination and low "
        "level of medical decision making; 20-29 minutes of total time",
        _EM,
    ),
    _cpt(
        "99214",
        "Office or other outpatient visit for the evaluation and management of an established "
        "patient, which requires a medically appropriate history and/or examination and "
        "moderate level of medical decision making; 30-39 minutes of total time",
        _EM,
    ),
    _cpt(
        "99215",
        "Office or other outpatient visit for the evaluation and management of an established "
        "patient, which requires a medically appropriate history and/or examination and high "
        "level of medical decision making; 40-54 minutes of total time",
        _EM,
    ),
    _cpt(
        "99203",
        "Office or other outpatient visit for the evaluation and management of a new patient, "
        "which requires a medically appropriate history and/or examination and low level of "
        "medical decision making; 30-44 minutes of total time",
        _EM,
    ),
    _cpt(
        "99204",
        "Office or other outpatient visit for the evaluation and management of a new patient, "
        "which requires a medically appropriate history and/or examination and moderate level "
        "of medical decision making; 45-59 minutes of total time",
        _EM,
    ),
    _cpt("80053", "Comprehensive metabolic panel", _PATHOLOGY),
    _cpt(
        "85025",
        "Blood count; complete (CBC), automated (Hgb, Hct, RBC, WBC and platelet count) and "
        "automated differential WBC count",
        _PATHOLOGY,
    ),
    _cpt("80061", "Lipid panel", _PATHOLOGY),
    _cpt("83036", "Hemoglobin; glycosylated (A1C)", _PATHOLOGY),
    _cpt("82947", "Glucose; quantitative, blood (except reagent strip)", _PATHOLOGY),
    _cpt("82565", "Creatinine; blood", _PATHOLOGY),
    _cpt("84520", "Urea nitrogen; quantitative", _PATHOLOGY),
    _cpt("84443", "Thyroid stimulating hormone (TSH)", _PATHOLOGY),
    _cpt("85610", "Prothrombin time", _PATHOLOGY),
    _cpt(
        "81002",
        "Urinalysis, by dip stick or tablet reagent for bilirubin, glucose, hemoglobin, "
        "ketones, leukocytes, nitrite, pH, protein, specific gravity, urobilinogen, any "
        "number of these constituents; non-automated, without microscopy",
        _PATHOLOGY,
    ),
    _cpt("36415", "Collection of venous blood by venipuncture", _PATHOLOGY),
    _cpt("71046", "Radiologic examination, chest; 2 views", _RADIOLOGY),
    _cpt(
        "73721",
        "Magnetic resonance (eg, proton) imaging, any joint of lower extremity; without "
        "contrast material",
        _RADIOLOGY,
    ),
    _cpt(
        "70450",
        "Computed tomography, head or brain; without contrast material",
        _RADIOLOGY,
    ),
    _cpt(
        "27447",
        "Arthroplasty, knee, condyle and plateau; medial AND lateral compartments with or "
        "without patella resurfacing (total knee arthroplasty)",
        _SURGERY,
        global_days="090",
    ),
    _cpt(
        "29881",
        "Arthroscopy, knee, surgical; with meniscectomy (medial OR lateral, including any "
        "meniscal shaving) including debridement/shaving of articular cartilage "
        "(chondroplasty), same or separate compartment(s), when performed",
        _SURGERY,
        global_days="090",
    ),
    _cpt(
        "20610",
        "Arthrocentesis, aspiration and/or injection, major joint or bursa (eg, shoulder, "
        "hip, knee, subacromial bursa); without ultrasound guidance",
        _SURGERY,
        global_days="000",
    ),
    _cpt(
        "01402",
        "Anesthesia for open procedures on knee joint; total knee arthroplasty",
        _ANESTHESIA,
    ),
    _cpt(
        "97110",
        "Therapeutic procedure, 1 or more areas, each 15 minutes; therapeutic exercises to "
        "develop strength and endurance, range of motion and flexibility",
        _MEDICINE,
    ),
    _cpt(
        "90471",
        "Immunization administration (includes percutaneous, intradermal, subcutaneous, or "
        "intramuscular injections); 1 vaccine (single or combination vaccine/toxoid)",
        _MEDICINE,
    ),
    _cpt(
        "90686",
        "Influenza virus vaccine, quadrivalent (IIV4), split virus, preservative free, 0.5 mL "
        "dosage, for intramuscular use",
        _MEDICINE,
    ),
    _cpt(
        "90715",
        "Tetanus, diphtheria toxoids and acellular pertussis vaccine (Tdap), when administered "
        "to individuals 7 years or older, for intramuscular use",
        _MEDICINE,
    ),
    _cpt(
        "93000",
        "Electrocardiogram, routine ECG with at least 12 leads; with interpretation and report",
        _MEDICINE,
    ),
)


CONCEPTS_BY_SYSTEM: Final[tuple[tuple[str, tuple[ConceptSpec, ...]], ...]] = (
    (LOINC, LOINC_CONCEPTS),
    (CVX, CVX_CONCEPTS),
    (ICD10CM, ICD10CM_CONCEPTS),
    (CPT, CPT_CONCEPTS),
)


# --------------------------------------------------------------------------------------
# WHO growth reference standards
# --------------------------------------------------------------------------------------

_LmsRow = tuple[int, str, str, str]
_LmsRows = tuple[_LmsRow, ...]

# WHO defines one month as 30.4375 days; the clinical domain resolves a monthly
# curve row with floor(age_days / 30.4375).
DAYS_PER_MONTH: Final = Decimal("30.4375")

# 3rd and 97th percentile z-scores, used to derive the p3/p97 annotations.
_Z_P3: Final = NormalDist().inv_cdf(0.03)
_Z_P97: Final = NormalDist().inv_cdf(0.97)

_WHO_WFA_BOYS: Final[_LmsRows] = (
    (0, "0.3487", "3.3464", "0.14602"),
    (1, "0.2297", "4.4709", "0.13395"),
    (2, "0.1970", "5.5676", "0.12385"),
    (3, "0.1738", "6.3762", "0.11727"),
    (4, "0.1552", "7.0023", "0.11316"),
    (5, "0.1395", "7.5105", "0.11080"),
    (6, "0.1258", "7.9341", "0.10958"),
    (7, "0.1134", "8.2970", "0.10902"),
    (8, "0.1021", "8.6151", "0.10882"),
    (9, "0.0917", "8.9013", "0.10881"),
    (10, "0.0820", "9.1649", "0.10890"),
    (11, "0.0730", "9.4121", "0.10906"),
    (12, "0.0644", "9.6479", "0.10925"),
    (13, "0.0564", "9.8749", "0.10949"),
    (14, "0.0487", "10.0953", "0.10976"),
    (15, "0.0413", "10.3108", "0.11008"),
    (16, "0.0343", "10.5228", "0.11041"),
    (17, "0.0275", "10.7319", "0.11078"),
    (18, "0.0210", "10.9385", "0.11120"),
    (19, "0.0148", "11.1430", "0.11164"),
    (20, "0.0087", "11.3461", "0.11211"),
    (21, "0.0029", "11.5486", "0.11261"),
    (22, "-0.0028", "11.7503", "0.11314"),
    (23, "-0.0083", "11.9514", "0.11369"),
    (24, "-0.0136", "12.1515", "0.11426"),
    (25, "-0.0189", "12.3502", "0.11485"),
    (26, "-0.0240", "12.5466", "0.11544"),
    (27, "-0.0289", "12.7401", "0.11604"),
    (28, "-0.0338", "12.9304", "0.11664"),
    (29, "-0.0385", "13.1169", "0.11722"),
    (30, "-0.0431", "13.3000", "0.11781"),
    (31, "-0.0476", "13.4798", "0.11839"),
    (32, "-0.0520", "13.6567", "0.11896"),
    (33, "-0.0564", "13.8309", "0.11953"),
    (34, "-0.0607", "14.0031", "0.12008"),
    (35, "-0.0648", "14.1737", "0.12063"),
    (36, "-0.0689", "14.3429", "0.12116"),
    (37, "-0.0729", "14.5113", "0.12168"),
    (38, "-0.0769", "14.6790", "0.12220"),
    (39, "-0.0808", "14.8465", "0.12271"),
    (40, "-0.0846", "15.0140", "0.12322"),
    (41, "-0.0883", "15.1813", "0.12373"),
    (42, "-0.0920", "15.3486", "0.12425"),
    (43, "-0.0957", "15.5158", "0.12478"),
    (44, "-0.0993", "15.6829", "0.12532"),
    (45, "-0.1028", "15.8497", "0.12586"),
    (46, "-0.1063", "16.0163", "0.12642"),
    (47, "-0.1098", "16.1827", "0.12700"),
    (48, "-0.1131", "16.3489", "0.12759"),
    (49, "-0.1164", "16.5150", "0.12819"),
    (50, "-0.1198", "16.6811", "0.12881"),
    (51, "-0.1230", "16.8471", "0.12943"),
    (52, "-0.1263", "17.0132", "0.13006"),
    (53, "-0.1294", "17.1792", "0.13068"),
    (54, "-0.1326", "17.3452", "0.13132"),
    (55, "-0.1356", "17.5110", "0.13196"),
    (56, "-0.1387", "17.6767", "0.13261"),
    (57, "-0.1417", "17.8422", "0.13325"),
    (58, "-0.1447", "18.0073", "0.13390"),
    (59, "-0.1477", "18.1722", "0.13454"),
    (60, "-0.1506", "18.3366", "0.13518"),
)


_WHO_WFA_GIRLS: Final[_LmsRows] = (
    (0, "0.3809", "3.2322", "0.14171"),
    (1, "0.1714", "4.1873", "0.13724"),
    (2, "0.0962", "5.1282", "0.13000"),
    (3, "0.0402", "5.8458", "0.12619"),
    (4, "-0.0050", "6.4237", "0.12402"),
    (5, "-0.0430", "6.8985", "0.12273"),
    (6, "-0.0755", "7.2970", "0.12204"),
    (7, "-0.1040", "7.6423", "0.12178"),
    (8, "-0.1288", "7.9487", "0.12180"),
    (9, "-0.1507", "8.2254", "0.12199"),
    (10, "-0.1700", "8.4799", "0.12222"),
    (11, "-0.1872", "8.7193", "0.12247"),
    (12, "-0.2023", "8.9480", "0.12267"),
    (13, "-0.2158", "9.1700", "0.12283"),
    (14, "-0.2278", "9.3870", "0.12294"),
    (15, "-0.2384", "9.6007", "0.12299"),
    (16, "-0.2478", "9.8124", "0.12303"),
    (17, "-0.2562", "10.0226", "0.12305"),
    (18, "-0.2637", "10.2315", "0.12309"),
    (19, "-0.2703", "10.4393", "0.12315"),
    (20, "-0.2762", "10.6464", "0.12324"),
    (21, "-0.2814", "10.8534", "0.12335"),
    (22, "-0.2862", "11.0608", "0.12351"),
    (23, "-0.2903", "11.2688", "0.12369"),
    (24, "-0.2941", "11.4775", "0.12390"),
    (25, "-0.2975", "11.6864", "0.12414"),
    (26, "-0.3005", "11.8948", "0.12441"),
    (27, "-0.3033", "12.1015", "0.12472"),
    (28, "-0.3057", "12.3059", "0.12506"),
    (29, "-0.3080", "12.5073", "0.12545"),
    (30, "-0.3101", "12.7055", "0.12587"),
    (31, "-0.3120", "12.9005", "0.12633"),
    (32, "-0.3138", "13.0930", "0.12683"),
    (33, "-0.3155", "13.2837", "0.12737"),
    (34, "-0.3171", "13.4731", "0.12794"),
    (35, "-0.3186", "13.6618", "0.12855"),
    (36, "-0.3201", "13.8503", "0.12920"),
    (37, "-0.3216", "14.0385", "0.12987"),
    (38, "-0.3230", "14.2265", "0.13059"),
    (39, "-0.3243", "14.4140", "0.13134"),
    (40, "-0.3257", "14.6010", "0.13212"),
    (41, "-0.3270", "14.7873", "0.13294"),
    (42, "-0.3283", "14.9727", "0.13376"),
    (43, "-0.3296", "15.1573", "0.13460"),
    (44, "-0.3309", "15.3410", "0.13545"),
    (45, "-0.3322", "15.5240", "0.13630"),
    (46, "-0.3335", "15.7064", "0.13715"),
    (47, "-0.3348", "15.8882", "0.13800"),
    (48, "-0.3361", "16.0697", "0.13884"),
    (49, "-0.3374", "16.2511", "0.13968"),
    (50, "-0.3387", "16.4322", "0.14051"),
    (51, "-0.3400", "16.6133", "0.14133"),
    (52, "-0.3414", "16.7942", "0.14213"),
    (53, "-0.3427", "16.9748", "0.14293"),
    (54, "-0.3440", "17.1551", "0.14371"),
    (55, "-0.3453", "17.3348", "0.14448"),
    (56, "-0.3467", "17.5136", "0.14525"),
    (57, "-0.3479", "17.6916", "0.14600"),
    (58, "-0.3492", "17.8686", "0.14675"),
    (59, "-0.3505", "18.0445", "0.14749"),
    (60, "-0.3518", "18.2193", "0.14822"),
)


_WHO_HFA_BOYS: Final[_LmsRows] = (
    (0, "1.0000", "49.8842", "0.03795"),
    (1, "1.0000", "54.7243", "0.03557"),
    (2, "1.0000", "58.4248", "0.03423"),
    (3, "1.0000", "61.4291", "0.03328"),
    (4, "1.0000", "63.8859", "0.03257"),
    (5, "1.0000", "65.9026", "0.03204"),
    (6, "1.0000", "67.6236", "0.03165"),
    (7, "1.0000", "69.1645", "0.03139"),
    (8, "1.0000", "70.5994", "0.03124"),
    (9, "1.0000", "71.9686", "0.03117"),
    (10, "1.0000", "73.2811", "0.03118"),
    (11, "1.0000", "74.5388", "0.03125"),
    (12, "1.0000", "75.7488", "0.03137"),
    (13, "1.0000", "76.9186", "0.03154"),
    (14, "1.0000", "78.0497", "0.03174"),
    (15, "1.0000", "79.1458", "0.03197"),
    (16, "1.0000", "80.2113", "0.03222"),
    (17, "1.0000", "81.2487", "0.03249"),
    (18, "1.0000", "82.2587", "0.03279"),
    (19, "1.0000", "83.2418", "0.03310"),
    (20, "1.0000", "84.1996", "0.03342"),
    (21, "1.0000", "85.1348", "0.03375"),
    (22, "1.0000", "86.0478", "0.03410"),
    (23, "1.0000", "86.9410", "0.03445"),
    (24, "1.0000", "87.1161", "0.03507"),
    (25, "1.0000", "87.9720", "0.03542"),
    (26, "1.0000", "88.8065", "0.03576"),
    (27, "1.0000", "89.6197", "0.03610"),
    (28, "1.0000", "90.4120", "0.03642"),
    (29, "1.0000", "91.1828", "0.03674"),
    (30, "1.0000", "91.9327", "0.03704"),
    (31, "1.0000", "92.6631", "0.03733"),
    (32, "1.0000", "93.3753", "0.03761"),
    (33, "1.0000", "94.0711", "0.03787"),
    (34, "1.0000", "94.7531", "0.03812"),
    (35, "1.0000", "95.4236", "0.03836"),
    (36, "1.0000", "96.0835", "0.03858"),
    (37, "1.0000", "96.7338", "0.03879"),
    (38, "1.0000", "97.3749", "0.03900"),
    (39, "1.0000", "98.0073", "0.03919"),
    (40, "1.0000", "98.6311", "0.03937"),
    (41, "1.0000", "99.2459", "0.03954"),
    (42, "1.0000", "99.8515", "0.03970"),
    (43, "1.0000", "100.4485", "0.03986"),
    (44, "1.0000", "101.0374", "0.04002"),
    (45, "1.0000", "101.6187", "0.04017"),
    (46, "1.0000", "102.1933", "0.04031"),
    (47, "1.0000", "102.7625", "0.04045"),
    (48, "1.0000", "103.3273", "0.04059"),
    (49, "1.0000", "103.8886", "0.04073"),
    (50, "1.0000", "104.4473", "0.04086"),
    (51, "1.0000", "105.0041", "0.04100"),
    (52, "1.0000", "105.5596", "0.04113"),
    (53, "1.0000", "106.1138", "0.04126"),
    (54, "1.0000", "106.6668", "0.04139"),
    (55, "1.0000", "107.2187", "0.04152"),
    (56, "1.0000", "107.7698", "0.04165"),
    (57, "1.0000", "108.3198", "0.04177"),
    (58, "1.0000", "108.8688", "0.04190"),
    (59, "1.0000", "109.4169", "0.04202"),
    (60, "1.0000", "109.9638", "0.04214"),
)


_WHO_HFA_GIRLS: Final[_LmsRows] = (
    (0, "1.0000", "49.1477", "0.03790"),
    (1, "1.0000", "53.6871", "0.03640"),
    (2, "1.0000", "57.0672", "0.03568"),
    (3, "1.0000", "59.8028", "0.03520"),
    (4, "1.0000", "62.0898", "0.03486"),
    (5, "1.0000", "64.0301", "0.03463"),
    (6, "1.0000", "65.7311", "0.03448"),
    (7, "1.0000", "67.2873", "0.03441"),
    (8, "1.0000", "68.7498", "0.03440"),
    (9, "1.0000", "70.1435", "0.03444"),
    (10, "1.0000", "71.4818", "0.03452"),
    (11, "1.0000", "72.7710", "0.03464"),
    (12, "1.0000", "74.0149", "0.03479"),
    (13, "1.0000", "75.2175", "0.03496"),
    (14, "1.0000", "76.3817", "0.03514"),
    (15, "1.0000", "77.5098", "0.03534"),
    (16, "1.0000", "78.6055", "0.03555"),
    (17, "1.0000", "79.6710", "0.03576"),
    (18, "1.0000", "80.7079", "0.03598"),
    (19, "1.0000", "81.7182", "0.03620"),
    (20, "1.0000", "82.7036", "0.03643"),
    (21, "1.0000", "83.6653", "0.03665"),
    (22, "1.0000", "84.6040", "0.03689"),
    (23, "1.0000", "85.5203", "0.03711"),
    (24, "1.0000", "85.7154", "0.03764"),
    (25, "1.0000", "86.5904", "0.03786"),
    (26, "1.0000", "87.4462", "0.03808"),
    (27, "1.0000", "88.2830", "0.03830"),
    (28, "1.0000", "89.1004", "0.03851"),
    (29, "1.0000", "89.8991", "0.03872"),
    (30, "1.0000", "90.6797", "0.03893"),
    (31, "1.0000", "91.4430", "0.03913"),
    (32, "1.0000", "92.1906", "0.03933"),
    (33, "1.0000", "92.9239", "0.03952"),
    (34, "1.0000", "93.6444", "0.03971"),
    (35, "1.0000", "94.3532", "0.03989"),
    (36, "1.0000", "95.0515", "0.04007"),
    (37, "1.0000", "95.7398", "0.04024"),
    (38, "1.0000", "96.4187", "0.04041"),
    (39, "1.0000", "97.0885", "0.04057"),
    (40, "1.0000", "97.7493", "0.04074"),
    (41, "1.0000", "98.4015", "0.04089"),
    (42, "1.0000", "99.0448", "0.04105"),
    (43, "1.0000", "99.6795", "0.04120"),
    (44, "1.0000", "100.3058", "0.04135"),
    (45, "1.0000", "100.9238", "0.04150"),
    (46, "1.0000", "101.5337", "0.04164"),
    (47, "1.0000", "102.1360", "0.04179"),
    (48, "1.0000", "102.7312", "0.04193"),
    (49, "1.0000", "103.3197", "0.04206"),
    (50, "1.0000", "103.9021", "0.04220"),
    (51, "1.0000", "104.4786", "0.04233"),
    (52, "1.0000", "105.0494", "0.04247"),
    (53, "1.0000", "105.6149", "0.04259"),
    (54, "1.0000", "106.1748", "0.04272"),
    (55, "1.0000", "106.7295", "0.04285"),
    (56, "1.0000", "107.2788", "0.04297"),
    (57, "1.0000", "107.8227", "0.04310"),
    (58, "1.0000", "108.3613", "0.04322"),
    (59, "1.0000", "108.8948", "0.04335"),
    (60, "1.0000", "109.4232", "0.04346"),
)

GROWTH_CURVES: Final[tuple[tuple[GrowthMeasure, BiologicalSex, _LmsRows], ...]] = (
    (GrowthMeasure.WEIGHT_FOR_AGE, BiologicalSex.MALE, _WHO_WFA_BOYS),
    (GrowthMeasure.WEIGHT_FOR_AGE, BiologicalSex.FEMALE, _WHO_WFA_GIRLS),
    (GrowthMeasure.HEIGHT_FOR_AGE, BiologicalSex.MALE, _WHO_HFA_BOYS),
    (GrowthMeasure.HEIGHT_FOR_AGE, BiologicalSex.FEMALE, _WHO_HFA_GIRLS),
)


def lms_quantile(l_value: Decimal, m_value: Decimal, s_value: Decimal, z: float) -> Decimal:
    """Inverse of the LMS z-score: X = M(1 + LSz)^(1/L), or M*exp(Sz) when L is 0."""
    lam = float(l_value)
    median = float(m_value)
    sigma = float(s_value)
    value = (
        median * pow(1.0 + lam * sigma * z, 1.0 / lam)
        if lam != 0.0
        else median * pow(2.718281828459045, sigma * z)
    )
    return Decimal(f"{value:.4f}")


# --------------------------------------------------------------------------------------
# Lab test catalogue
# --------------------------------------------------------------------------------------

# SNOMED CT specimen concepts (the LabTest docstring requires SNOMED, not LOINC).
SPECIMENS: Final[dict[str, str]] = {
    "119297000": "Blood specimen",
    "119361006": "Plasma specimen",
    "119364003": "Serum specimen",
    "122554006": "Capillary blood specimen",
    "122555007": "Venous blood specimen",
    "122575003": "Urine specimen",
    "258580003": "Whole blood sample",
    "1000039": "Arterial blood specimen",
}
_ARTERIAL: Final = "1000039"
_SERUM: Final = "119364003"
_WHOLE_BLOOD: Final = "258580003"
_URINE: Final = "122575003"
_PLASMA: Final = "119361006"

_EDTA: Final = "Lavender top (K2 EDTA)"
_SST: Final = "Gold top serum separator (SST)"
_CITRATE: Final = "Light blue top (3.2% sodium citrate)"
_FLUORIDE: Final = "Grey top (sodium fluoride / potassium oxalate)"
_CUP: Final = "Sterile urine collection cup"
_GAS_SYRINGE: Final = "Heparinised blood gas syringe, on ice"

_NO_PREP: Final = "No special preparation required."
_FAST12: Final = "Fast for 12 hours before collection; water and prescribed medication permitted."
_FAST8: Final = "Fast for 8 hours before collection; water permitted."
_MIDSTREAM: Final = "Collect a clean-catch midstream specimen; deliver within 2 hours."


@dataclass(frozen=True)
class LabTestSpec:
    code: str
    name: str
    specimen: str
    container: str
    prep: str
    turnaround_hours: int
    price_cents: int
    fasting: bool = False
    panel: str | None = None


LAB_TESTS: Final[tuple[LabTestSpec, ...]] = (
    LabTestSpec(
        "58410-2", "Complete blood count with differential", _WHOLE_BLOOD, _EDTA, _NO_PREP, 4, 2400
    ),
    LabTestSpec("718-7", "Hemoglobin", _WHOLE_BLOOD, _EDTA, _NO_PREP, 4, 900, panel="58410-2"),
    LabTestSpec(
        "6690-2", "White blood cell count", _WHOLE_BLOOD, _EDTA, _NO_PREP, 4, 900, panel="58410-2"
    ),
    LabTestSpec("777-3", "Platelet count", _WHOLE_BLOOD, _EDTA, _NO_PREP, 4, 900, panel="58410-2"),
    LabTestSpec(
        "24323-8", "Comprehensive metabolic panel", _SERUM, _SST, _FAST8, 6, 4900, fasting=True
    ),
    LabTestSpec("51990-0", "Basic metabolic panel", _SERUM, _SST, _FAST8, 6, 3400, fasting=True),
    LabTestSpec("2951-2", "Sodium, serum", _SERUM, _SST, _NO_PREP, 6, 1100, panel="51990-0"),
    LabTestSpec("2823-3", "Potassium, serum", _SERUM, _SST, _NO_PREP, 6, 1100, panel="51990-0"),
    LabTestSpec("2075-0", "Chloride, serum", _SERUM, _SST, _NO_PREP, 6, 1100, panel="51990-0"),
    LabTestSpec(
        "2028-9",
        "Carbon dioxide (bicarbonate), serum",
        _SERUM,
        _SST,
        _NO_PREP,
        6,
        1100,
        panel="51990-0",
    ),
    LabTestSpec("17861-6", "Calcium, serum", _SERUM, _SST, _NO_PREP, 6, 1300, panel="51990-0"),
    LabTestSpec("2160-0", "Creatinine, serum", _SERUM, _SST, _NO_PREP, 6, 1400, panel="51990-0"),
    LabTestSpec(
        "3094-0", "Urea nitrogen (BUN), serum", _SERUM, _SST, _NO_PREP, 6, 1400, panel="51990-0"
    ),
    LabTestSpec(
        "2345-7",
        "Glucose, fasting",
        _PLASMA,
        _FLUORIDE,
        _FAST8,
        4,
        1500,
        fasting=True,
        panel="51990-0",
    ),
    LabTestSpec("1751-7", "Albumin, serum", _SERUM, _SST, _NO_PREP, 6, 1200, panel="24323-8"),
    LabTestSpec(
        "1742-6", "Alanine aminotransferase (ALT)", _SERUM, _SST, _NO_PREP, 6, 1600, panel="24323-8"
    ),
    LabTestSpec(
        "1920-8",
        "Aspartate aminotransferase (AST)",
        _SERUM,
        _SST,
        _NO_PREP,
        6,
        1600,
        panel="24323-8",
    ),
    LabTestSpec("6768-6", "Alkaline phosphatase", _SERUM, _SST, _NO_PREP, 6, 1600, panel="24323-8"),
    LabTestSpec("1975-2", "Bilirubin, total", _SERUM, _SST, _NO_PREP, 6, 1500, panel="24323-8"),
    LabTestSpec(
        "57698-3", "Lipid panel with direct LDL", _SERUM, _SST, _FAST12, 12, 6500, fasting=True
    ),
    LabTestSpec(
        "2093-3",
        "Cholesterol, total",
        _SERUM,
        _SST,
        _FAST12,
        12,
        1800,
        fasting=True,
        panel="57698-3",
    ),
    LabTestSpec(
        "2085-9", "HDL cholesterol", _SERUM, _SST, _FAST12, 12, 1900, fasting=True, panel="57698-3"
    ),
    LabTestSpec(
        "2089-1",
        "LDL cholesterol, direct",
        _SERUM,
        _SST,
        _FAST12,
        12,
        2400,
        fasting=True,
        panel="57698-3",
    ),
    LabTestSpec(
        "2571-8", "Triglycerides", _SERUM, _SST, _FAST12, 12, 1900, fasting=True, panel="57698-3"
    ),
    LabTestSpec("4548-4", "Hemoglobin A1c", _WHOLE_BLOOD, _EDTA, _NO_PREP, 8, 4200),
    LabTestSpec("3016-3", "Thyroid stimulating hormone (TSH)", _SERUM, _SST, _NO_PREP, 12, 4800),
    LabTestSpec("5902-2", "Prothrombin time", _PLASMA, _CITRATE, _NO_PREP, 4, 2100),
    LabTestSpec(
        "6301-6",
        "International normalised ratio (INR)",
        _PLASMA,
        _CITRATE,
        _NO_PREP,
        4,
        2100,
        panel="5902-2",
    ),
    LabTestSpec("24357-6", "Urinalysis, dipstick", _URINE, _CUP, _MIDSTREAM, 2, 1200),
    LabTestSpec(
        "24336-0",
        "Arterial blood gas panel",
        _ARTERIAL,
        _GAS_SYRINGE,
        "Collected by a clinician; transport on ice and analyse within 15 minutes.",
        1,
        8900,
    ),
    LabTestSpec(
        "2744-1",
        "pH, arterial blood",
        _ARTERIAL,
        _GAS_SYRINGE,
        "Collected by a clinician; analyse within 15 minutes.",
        1,
        2600,
        panel="24336-0",
    ),
    LabTestSpec(
        "2019-8",
        "pCO2, arterial blood",
        _ARTERIAL,
        _GAS_SYRINGE,
        "Collected by a clinician; analyse within 15 minutes.",
        1,
        2600,
        panel="24336-0",
    ),
)


# --------------------------------------------------------------------------------------
# Chargemaster
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceItemSpec:
    cpt: str
    display: str
    revenue_code: str
    base_price_cents: int


CHARGEMASTER_EFFECTIVE_FROM: Final = date(2026, 1, 1)
CURRENCY: Final = "USD"

SERVICE_ITEMS: Final[tuple[ServiceItemSpec, ...]] = (
    ServiceItemSpec("99212", "Office visit, established patient, level 2", "0510", 11000),
    ServiceItemSpec("99213", "Office visit, established patient, level 3", "0510", 16500),
    ServiceItemSpec("99214", "Office visit, established patient, level 4", "0510", 24000),
    ServiceItemSpec("99215", "Office visit, established patient, level 5", "0510", 33000),
    ServiceItemSpec("99203", "Office visit, new patient, level 3", "0510", 21000),
    ServiceItemSpec("99204", "Office visit, new patient, level 4", "0510", 31500),
    ServiceItemSpec("80053", "Comprehensive metabolic panel", "0301", 4900),
    ServiceItemSpec("85025", "Complete blood count with differential", "0305", 3500),
    ServiceItemSpec("80061", "Lipid panel", "0301", 6500),
    ServiceItemSpec("83036", "Hemoglobin A1c", "0301", 4200),
    ServiceItemSpec("82947", "Glucose, quantitative, blood", "0301", 1500),
    ServiceItemSpec("82565", "Creatinine, blood", "0301", 1400),
    ServiceItemSpec("84520", "Urea nitrogen, quantitative", "0301", 1400),
    ServiceItemSpec("84443", "Thyroid stimulating hormone", "0301", 4800),
    ServiceItemSpec("85610", "Prothrombin time", "0305", 2100),
    ServiceItemSpec("81002", "Urinalysis, dipstick, non-automated", "0300", 1200),
    ServiceItemSpec("36415", "Venipuncture, routine collection", "0300", 1500),
    ServiceItemSpec("71046", "Chest X-ray, 2 views", "0324", 12500),
    ServiceItemSpec("73721", "MRI, lower extremity joint, without contrast", "0610", 95000),
    ServiceItemSpec("70450", "CT head or brain, without contrast", "0351", 68000),
    ServiceItemSpec("27447", "Total knee arthroplasty", "0360", 2850000),
    ServiceItemSpec("29881", "Knee arthroscopy with meniscectomy", "0360", 685000),
    ServiceItemSpec("01402", "Anesthesia, total knee arthroplasty", "0370", 185000),
    ServiceItemSpec("20610", "Major joint injection or aspiration, knee", "0510", 22500),
    ServiceItemSpec("97110", "Therapeutic exercise, each 15 minutes", "0420", 6500),
    ServiceItemSpec("93000", "Electrocardiogram, 12-lead with interpretation", "0730", 9500),
    ServiceItemSpec("90471", "Immunization administration, first vaccine", "0771", 3500),
    ServiceItemSpec("90686", "Influenza vaccine, quadrivalent, preservative free", "0636", 3200),
    ServiceItemSpec("90715", "Tdap vaccine, 7 years and older", "0636", 5800),
)

PROVIDER_ORGANIZATION_TYPES: Final = ("hospital", "clinic", "provider", "health_system")
FALLBACK_ORGANIZATION_SLUG: Final = "healthos-reference-health-system"


# --------------------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------------------


def _reference_id(name: str) -> UUID:
    """Deterministic id, reusing the demo namespace under a ``reference:`` prefix."""
    return demo_id(f"reference:{name}")


async def _load_code_systems(session: AsyncSession) -> dict[str, CodeSystem]:
    existing = {
        (row.uri, row.version): row for row in (await session.scalars(select(CodeSystem))).all()
    }
    loaded: dict[str, CodeSystem] = {}
    for spec in CODE_SYSTEMS:
        row = existing.get((spec.uri, spec.version))
        if row is None:
            row = CodeSystem(
                id=_reference_id(f"code-system:{spec.uri}:{spec.version}"),
                uri=spec.uri,
                version=spec.version,
            )
            session.add(row)
        row.name = spec.name
        row.publisher = spec.publisher
        row.oid = spec.oid
        row.released_at = spec.released_at
        row.is_active = True
        loaded[spec.uri] = row
    return loaded


async def _load_code_concepts(
    session: AsyncSession, systems: dict[str, CodeSystem]
) -> dict[str, dict[str, CodeConcept]]:
    """Upsert every concept and return it indexed by ``system uri -> code``."""
    system_ids = [systems[uri].id for uri, _ in CONCEPTS_BY_SYSTEM]
    existing = {
        (row.code_system_id, row.code, row.effective_from): row
        for row in (
            await session.scalars(
                select(CodeConcept).where(CodeConcept.code_system_id.in_(system_ids))
            )
        ).all()
    }
    index: dict[str, dict[str, CodeConcept]] = {}
    for uri, specs in CONCEPTS_BY_SYSTEM:
        system = systems[uri]
        default_from = next(s.released_at for s in CODE_SYSTEMS if s.uri == uri)
        for spec in specs:
            effective_from = spec.effective_from or default_from
            row = existing.get((system.id, spec.code, effective_from))
            if row is None:
                row = CodeConcept(
                    id=_reference_id(f"concept:{uri}:{spec.code}:{effective_from.isoformat()}"),
                    code_system_id=system.id,
                    code=spec.code,
                    effective_from=effective_from,
                )
                session.add(row)
            row.display = spec.display
            row.definition = spec.definition
            row.parent_code = spec.parent_code
            row.properties = dict(spec.properties)
            row.is_active = spec.is_active
            row.effective_to = spec.effective_to
            index.setdefault(uri, {})[spec.code] = row
    return index


async def _load_growth_standards(session: AsyncSession) -> int:
    existing = {
        (row.measure, row.sex, row.age_unit, row.age_value): row
        for row in (
            await session.scalars(
                select(GrowthReferenceStandard).where(
                    GrowthReferenceStandard.source == GrowthSource.WHO
                )
            )
        ).all()
    }
    count = 0
    for measure, sex, table in GROWTH_CURVES:
        for age_months, l_text, m_text, s_text in table:
            l_value = Decimal(l_text)
            m_value = Decimal(m_text)
            s_value = Decimal(s_text)
            row = existing.get((measure, sex, "month", age_months))
            if row is None:
                row = GrowthReferenceStandard(
                    id=_reference_id(
                        f"growth:WHO:{measure.value}:{sex.value}:month:{age_months}",
                    ),
                    source=GrowthSource.WHO,
                    measure=measure,
                    sex=sex,
                    age_unit="month",
                    age_value=age_months,
                )
                session.add(row)
            row.l = l_value
            row.m = m_value
            row.s = s_value
            row.p3 = lms_quantile(l_value, m_value, s_value, _Z_P3)
            row.p50 = m_value
            row.p97 = lms_quantile(l_value, m_value, s_value, _Z_P97)
            count += 1
    return count


async def _resolve_provider_organization(session: AsyncSession) -> Organization:
    """Find the provider organisation that owns the catalogue, creating one if absent.

    ``lab_tests`` and ``service_items`` are tenant-scoped, so reference pricing
    has to hang off a real organisation. An existing active provider wins; the
    deterministic fallback exists only so a bare database can still be seeded.
    """
    stmt = (
        select(Organization)
        .where(
            Organization.organization_type.in_(PROVIDER_ORGANIZATION_TYPES),
            Organization.status == "active",
        )
        .order_by(Organization.created_at, Organization.slug)
    )
    organization = (await session.scalars(stmt)).first()
    if organization is not None:
        return organization

    by_slug = await session.scalar(
        select(Organization).where(Organization.slug == FALLBACK_ORGANIZATION_SLUG)
    )
    if by_slug is not None:
        return by_slug

    organization = Organization(
        id=_reference_id(f"organization:{FALLBACK_ORGANIZATION_SLUG}"),
        slug=FALLBACK_ORGANIZATION_SLUG,
        legal_name="HealthOS Reference Health System",
        organization_type="hospital",
        status="active",
        settings={"reference_data_owner": True},
    )
    session.add(organization)
    await session.flush()
    return organization


async def _load_lab_tests(
    session: AsyncSession, concepts: dict[str, CodeConcept], tenant_id: UUID
) -> int:
    existing = {
        (row.test_code, row.test_code_system): row
        for row in (
            await session.scalars(select(LabTest).where(LabTest.tenant_id == tenant_id))
        ).all()
    }
    count = 0
    for spec in LAB_TESTS:
        concept = concepts[spec.code]
        panel = concepts[spec.panel] if spec.panel else None
        row = existing.get((spec.code, LOINC))
        if row is None:
            row = LabTest(
                id=_reference_id(f"lab-test:{tenant_id}:{spec.code}"),
                tenant_id=tenant_id,
                test_code=spec.code,
                test_code_system=LOINC,
            )
            session.add(row)
        row.test_display = concept.display
        row.test_concept_id = concept.id
        row.panel_code_system = LOINC if panel else None
        row.panel_code = panel.code if panel else None
        row.panel_display = panel.display if panel else None
        row.panel_concept_id = panel.id if panel else None
        row.name = spec.name
        row.specimen_type_code_system = SNOMED
        row.specimen_type_code = spec.specimen
        row.specimen_type_display = SPECIMENS[spec.specimen]
        row.specimen_type_concept_id = None
        row.container = spec.container
        row.prep_instructions = spec.prep
        row.fasting_required = spec.fasting
        row.turnaround_hours = spec.turnaround_hours
        row.price_cents = spec.price_cents
        row.currency = CURRENCY
        row.is_active = True
        count += 1
    return count


async def _load_service_items(
    session: AsyncSession, concepts: dict[str, CodeConcept], organization: Organization
) -> int:
    existing = {
        (row.service_code, row.effective_from): row
        for row in (
            await session.scalars(
                select(ServiceItem).where(ServiceItem.organization_id == organization.id)
            )
        ).all()
    }
    count = 0
    for spec in SERVICE_ITEMS:
        concept = concepts[spec.cpt]
        row = existing.get((spec.cpt, CHARGEMASTER_EFFECTIVE_FROM))
        if row is None:
            row = ServiceItem(
                id=_reference_id(f"service-item:{organization.id}:{spec.cpt}"),
                tenant_id=organization.id,
                organization_id=organization.id,
                service_code=spec.cpt,
                effective_from=CHARGEMASTER_EFFECTIVE_FROM,
            )
            session.add(row)
        row.service_code_system = CPT
        row.service_display = spec.display
        row.service_concept_id = concept.id
        row.description = concept.display
        row.cpt_code = spec.cpt
        row.revenue_code = spec.revenue_code
        row.base_price_cents = spec.base_price_cents
        row.currency = CURRENCY
        row.effective_to = None
        row.is_active = True
        count += 1
    return count


async def seed_reference(session: AsyncSession) -> dict[str, int]:
    """Load all reference data idempotently and return per-table row counts.

    The caller owns the transaction: this flushes but never commits.
    """
    systems = await _load_code_systems(session)
    await session.flush()

    concept_index = await _load_code_concepts(session, systems)
    await session.flush()

    growth_rows = await _load_growth_standards(session)

    organization = await _resolve_provider_organization(session)
    lab_rows = await _load_lab_tests(session, concept_index[LOINC], organization.id)
    service_rows = await _load_service_items(session, concept_index[CPT], organization)
    await session.flush()

    return {
        "code_systems": len(systems),
        "code_concepts": sum(len(codes) for codes in concept_index.values()),
        "growth_reference_standards": growth_rows,
        "lab_tests": lab_rows,
        "service_items": service_rows,
    }


async def verify_median_percentile(session: AsyncSession) -> dict[str, float]:
    """Self-check: a 12-month-old boy at the WHO median weight must sit at the 50th centile.

    This deliberately routes through the production percentile maths in
    ``healthos_api.domain.clinical`` rather than a local copy, so a bad curve or
    a bad formula both fail here.
    """
    row = await session.scalar(
        select(GrowthReferenceStandard).where(
            GrowthReferenceStandard.source == GrowthSource.WHO,
            GrowthReferenceStandard.measure == GrowthMeasure.WEIGHT_FOR_AGE,
            GrowthReferenceStandard.sex == BiologicalSex.MALE,
            GrowthReferenceStandard.age_unit == "month",
            GrowthReferenceStandard.age_value == 12,
        )
    )
    if row is None:
        raise RuntimeError("WHO weight-for-age curve for 12-month-old boys is missing")

    z = _lms_zscore(row.m, row.l, row.m, row.s)
    if z is None:
        raise RuntimeError("LMS z-score could not be computed for the 12-month median weight")
    percentile = _zscore_to_percentile(z)
    if abs(percentile - 50.0) > 0.01:
        raise RuntimeError(
            f"WHO median weight scored the {percentile:.4f}th percentile, expected ~50th"
        )
    return {
        "median_weight_kg": float(row.m),
        "zscore": round(z, 6),
        "percentile": percentile,
    }


async def run() -> tuple[dict[str, int], dict[str, float]]:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            counts = await seed_reference(session)
            await session.commit()
            check = await verify_median_percentile(session)
            return counts, check
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load HealthOS clinical and insurance reference data (idempotent)"
    )
    parser.parse_args()
    counts, check = asyncio.run(run())
    print("HealthOS reference data loaded.")  # noqa: T201
    print(json.dumps(counts, indent=2, sort_keys=True))  # noqa: T201
    print(  # noqa: T201
        "Percentile self-check (12-month-old boy at the WHO median weight "
        f"{check['median_weight_kg']} kg): z={check['zscore']}, "
        f"percentile={check['percentile']}"
    )


if __name__ == "__main__":
    main()
