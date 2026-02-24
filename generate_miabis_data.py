#!/usr/bin/env python3
"""
Synthetic MIABIS-on-FHIR data generator.

Conforms to the BBMRI-cz MIABIS-on-FHIR Implementation Guide v1.0.0
  Canonical:  https://fhir.bbmri-eric.eu
  Source:     https://github.com/BBMRI-cz/miabis-on-fhir
  Published:  https://fhir.miabis.bbmri-eric.eu

Generates a FHIR R4 Transaction Bundle containing:
  JuristicPerson     (Organization)  — legal owner of the biobank
  Biobank            (Organization)  — miabis-biobank profile
  CollectionOrg      (Organization)  — miabis-collection-organization profile
  Collection         (Group)         — miabis-collection profile
  Donor              (Patient)       — miabis-sample-donor profile
  Sample             (Specimen)      — miabis-sample profile
  Condition          (Condition)     — miabis-condition profile

Requirements:
    pip install faker

Usage:
    python generate_miabis_data.py
    python generate_miabis_data.py --donors 50 --collections 3 --output bundle.json
    python generate_miabis_data.py --donors 20 --seed 42 --country CZ
"""

import argparse
import json
import random
import uuid
from datetime import date, timedelta

from faker import Faker

# ── MIABIS-on-FHIR canonical base (https://github.com/BBMRI-cz/miabis-on-fhir) ──
CANONICAL = "https://fhir.bbmri-eric.eu"
SD  = f"{CANONICAL}/StructureDefinition"   # StructureDefinition base
CS  = f"{CANONICAL}/CodeSystem"            # CodeSystem base

# ── Standard external code systems ────────────────────────────────────────────
ICD10       = "http://hl7.org/fhir/sid/icd-10"
ADMIN_GENDER = "http://hl7.org/fhir/administrative-gender"
# FHIR R5 extension for Group.member.entity (used in FHIR R4 via cross-version ext)
EXT_MEMBER_ENTITY = "http://hl7.org/fhir/5.0/StructureDefinition/extension-Group.member.entity"

# ── Profile canonical URLs ─────────────────────────────────────────────────────
PROFILE = {
    "biobank":        f"{SD}/miabis-biobank",
    "collection_org": f"{SD}/miabis-collection-organization",
    "collection":     f"{SD}/miabis-collection",
    "sample":         f"{SD}/miabis-sample",
    "donor":          f"{SD}/miabis-sample-donor",
    "condition":      f"{SD}/miabis-condition",
}

# ── Extension canonical URLs ───────────────────────────────────────────────────
EXT = {
    # Biobank extensions
    "description":             f"{SD}/miabis-organization-description-extension",
    "infra_cap":               f"{SD}/miabis-infrastructural-capabilities-extension",
    "org_cap":                 f"{SD}/miabis-organisational-capabilities-extension",
    "bio_cap":                 f"{SD}/miabis-bioprocessing-and-analytical-capabilities-extension",
    "quality_std":             f"{SD}/miabis-quality-management-standard-extension",
    # CollectionOrg extensions
    "col_dataset_type":        f"{SD}/miabis-collection-dataset-type-extension",
    "sample_source":           f"{SD}/miabis-sample-source-extension",
    "col_setting":             f"{SD}/miabis-sample-collection-setting-extension",
    "col_design":              f"{SD}/miabis-collection-design-extension",
    "use_access":              f"{SD}/miabis-use-and-access-conditions-extension",
    "publications":            f"{SD}/miabis-publications-extension",
    # Collection (Group) extensions
    "num_subjects":            f"{SD}/miabis-number-of-subjects-extension",
    "inclusion_criteria":      f"{SD}/miabis-inclusion-criteria-extension",
    # Donor (Patient) extension
    "dataset_type":            f"{SD}/miabis-dataset-type-extension",
    # Sample (Specimen) extensions
    "storage_temp":            f"{SD}/miabis-sample-storage-temperature-extension",
    "sample_collection":       f"{SD}/miabis-sample-collection-extension",
}

# ── Controlled vocabularies ────────────────────────────────────────────────────

# StorageTemperatureCS  (miabis-storage-temperature-cs)
STORAGE_TEMPS = [
    ("RT",       "Room temperature"),
    ("2to10",    "between 2 and 10 degrees Celsius"),
    ("-18to-35", "between -18 and -35 degrees Celsius"),
    ("-60to-85", "between -60 and -85 degrees Celsius"),
    ("LN",       "liquid nitrogen, -150 to -196 degrees Celsius"),
    ("Other",    "any other temperature or long time storage information"),
]

# DetailedSampleTypeCS  (miabis-detailed-samply-type-cs — note upstream typo)
DETAILED_SAMPLE_TYPES = [
    ("BuffyCoat",          "Buffy coat"),
    ("DNA",                "DNA"),
    ("RNA",                "RNA"),
    ("Plasma",             "Plasma"),
    ("Serum",              "Serum"),
    ("Urine",              "Urine"),
    ("WholeBlood",         "Whole blood"),
    ("CerebrospinalFluid", "Cerebrospinal fluid"),
    ("Saliva",             "Saliva"),
    ("Faeces",             "Faeces"),
    ("PBMC",               "Peripheral blood mononuclear cells"),
    ("TissueFreshFrozen",  "Tissue (fresh frozen)"),
    ("TissueFixed",        "Tissue (fixed)"),
    ("BoneMarrowAspirate", "Bone marrow aspirate"),
    ("LiquidBiopsy",       "Liquid biopsy"),
    ("Sputum",             "Sputum"),
]

# CollectionSampleTypeCS  (miabis-collection-sample-type-cs) — used in Collection characteristics
COLLECTION_SAMPLE_TYPES = [
    ("Blood",        "Blood"),
    ("BuffyCoat",    "Buffy Coat"),
    ("DNA",          "DNA"),
    ("Plasma",       "Plasma"),
    ("RNA",          "RNA"),
    ("Saliva",       "Saliva"),
    ("Serum",        "Serum"),
    ("TissueFrozen", "Tissue (frozen)"),
    ("TissueFFPE",   "Tissue (FFPE)"),
    ("Urine",        "Urine"),
    ("Other",        "Other"),
]

# DatasetTypeCS  (miabis-dataset-type-CS) — Donor extension
DATASET_TYPES = [
    "BiologicalSamples",
    "SurveyData",
    "ImagingData",
    "MedicalRecords",
    "NationalRegistries",
    "GenealogicalRecords",
    "PhysioBiochemicalData",
]

# InfrastructuralCapabilitiesCS  (miabis-infrastructural-capabilities-cs)
INFRA_CAPS = [
    ("SampleStorage", "Sample Storage"),
    ("DataStorage",   "Data Storage"),
    ("Biosafety",     "Bio safety Abilities"),
]

# OrganisationalCapabilitiesCS  (miabis-organisational-capabilities-cs)
ORG_CAPS = [
    ("RecontactDonors",       "Recontact with donors"),
    ("ClinicalTrials",        "Facilitating clinical trials"),
    ("ProspectiveCollections","Setting up prospective collections"),
    ("OmicsData",             "Access to omics data"),
    ("LabAnalysisData",       "Access to laboratory analysis data"),
    ("ClinicalData",          "Access to donors' clinical data"),
    ("Other",                 "Other"),
]

# BioprocessingAndAnalyticalCapabilitiesCS  (miabis-bioprocessing-and-analytical-capabilities-cs)
BIO_CAPS = [
    ("BioChemAnalyses",            "Biochemical analyses"),
    ("Genomics",                   "Genomics"),
    ("NucleicAcidExtraction",      "Nucleic acid extraction"),
    ("Proteomics",                 "Proteomics"),
    ("Metabolomics",               "Metabolomics"),
    ("Histology",                  "Histology"),
    ("SampleProcessing",           "Sample processing"),
    ("SampleQualityControlServices","Sample quality control services"),
    ("Other",                      "Other"),
]

# CollectionDatasetTypeCS  (miabis-collection-dataset-typeCS)
COL_DATASET_TYPES = [
    ("Genomic",     "Genomic dataset"),
    ("Clinical",    "Clinical dataset"),
    ("Biochemical", "Biochemical dataset"),
    ("Proteomic",   "Proteomic dataset"),
    ("BodyImage",   "Body (Radiological) image"),
    ("Other",       "Other"),
]

# SampleSourceCS  (miabis-sample-source-cs)
SAMPLE_SOURCES = [
    ("Human",       "Human"),
    ("Animal",      "Animal"),
    ("Environment", "Environment"),
]

# SampleCollectionSettingCS  (miabis-sample-collection-setting-cs)
COLLECTION_SETTINGS = [
    ("RoutineHealthCare", "Routine health care setting"),
    ("ClinicalTrial",     "Clinical trial"),
    ("ResearchStudy",     "Research study"),
    ("Public",            "Public health/population based study"),
    ("Unknown",           "Unknown"),
    ("Other",             "Other"),
]

# CollectionDesignCS  (miabis-collection-design-cs)
COLLECTION_DESIGNS = [
    ("CaseControl",          "Case-control"),
    ("CrossSectional",       "Cross-sectional"),
    ("LongitudinalCohort",   "Longitudinal cohort"),
    ("PopulationBasedCohort","Population-based cohort"),
    ("DiseaseSpecificCohort","Disease-specific cohort"),
    ("BirthCohort",          "Birth cohort"),
    ("Other",                "Other"),
]

# UseAndAccessConditionsCS  (miabis-use-and-access-conditions-cs)
USE_ACCESS_CONDITIONS = [
    ("CommercialUse",       "Commercial use"),
    ("Collaboration",       "Collaboration"),
    ("SpecificResearchUse", "Specific research use"),
    ("GeneticDataUse",      "Genetic data use"),
    ("OutsideEUAccess",     "Outside EU access"),
    ("Other",               "Other"),
]

# InclusionCriteriaCS  (miabis-inclusion-criteria-cs)
INCLUSION_CRITERIA = [
    ("HealthStatus",    "Health status"),
    ("HospitalPatient", "Hospital patient"),
    ("AgeGroup",        "Age group"),
    ("Sex",             "Sex"),
    ("Lifestyle",       "Lifestyle/Exposure"),
    ("Other",           "Other"),
]

# ICD-10 diagnosis codes  (http://hl7.org/fhir/sid/icd-10)
ICD10_CODES = [
    ("C18",   "Malignant neoplasm of colon"),
    ("C50",   "Malignant neoplasm of breast"),
    ("C61",   "Malignant neoplasm of prostate"),
    ("C34",   "Malignant neoplasm of bronchus and lung"),
    ("C25",   "Malignant neoplasm of pancreas"),
    ("C91",   "Lymphoid leukaemia"),
    ("E11",   "Type 2 diabetes mellitus"),
    ("I21",   "Acute myocardial infarction"),
    ("J45",   "Asthma"),
    ("K50",   "Crohn disease"),
    ("G20",   "Parkinson disease"),
    ("G35",   "Multiple sclerosis"),
    ("F20",   "Schizophrenia"),
    ("M05",   "Seropositive rheumatoid arthritis"),
]

# ICD-O-3 topography + version (used for Sample.collection.bodySite)
ICDO3_SITES = [
    ("C18.0", "Cecum"),
    ("C50.1", "Central portion of breast"),
    ("C61.9", "Prostate gland"),
    ("C34.1", "Upper lobe of lung"),
    ("C25.0", "Head of pancreas"),
    ("C16.9", "Stomach, NOS"),
    ("C22.0", "Liver"),
    ("C56.9", "Ovary"),
    ("C80.9", "Unknown primary site"),
]
ICDO3_SYSTEM  = "http://terminology.hl7.org/CodeSystem/icd-o-3"
ICDO3_VERSION = "2000"

# Administrative gender codes
GENDERS = ["male", "female", "other", "unknown"]

# ── Low-level FHIR dict builders ───────────────────────────────────────────────

fake = Faker()


def new_id() -> str:
    return str(uuid.uuid4())


def coding(system: str, code: str, display: str = "") -> dict:
    c: dict = {"system": system, "code": code}
    if display:
        c["display"] = display
    return c


def codeable_concept(system: str, code: str, display: str = "") -> dict:
    return {"coding": [coding(system, code, display)]}


def ext(url: str, **value_field) -> dict:
    """Return a FHIR Extension. value_field must be exactly one valueX kwarg."""
    return {"url": url, **value_field}


def ref(resource_type: str, resource_id: str) -> dict:
    return {"reference": f"{resource_type}/{resource_id}"}


def identifier(system: str, value: str) -> dict:
    return {"system": system, "value": value}


def random_past_date(min_years: float = 0, max_years: float = 10) -> str:
    lo = max(1, int(min_years * 365))
    hi = max(lo + 1, int(max_years * 365))
    days = random.randint(lo, hi)
    return (date.today() - timedelta(days=days)).isoformat()


def narrative(title: str, body: str = "") -> dict:
    """
    Build a minimal FHIR Narrative (DomainResource.text) to satisfy dom-6.
    status='generated' means the narrative is derived entirely from the structured data.
    """
    inner = f"<p><b>{title}</b></p>"
    if body:
        # escape the few characters that are unsafe inside XHTML PCDATA
        safe = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        inner += f"<p>{safe}</p>"
    return {
        "status": "generated",
        "div": f'<div xmlns="http://www.w3.org/1999/xhtml">{inner}</div>',
    }


def bundle_entry(resource: dict, method: str = "PUT") -> dict:
    rid   = resource["id"]
    rtype = resource["resourceType"]
    return {
        "fullUrl": f"urn:uuid:{rid}",
        "resource": resource,
        "request": {"method": method, "url": f"{rtype}/{rid}"},
    }


# ── Resource generators ────────────────────────────────────────────────────────

def make_juristic_person(country: str = "DE") -> tuple[dict, str]:
    """
    A plain Organization representing the legal/juristic entity that owns the
    biobank.  Not profiled by MIABIS — generated so Biobank.partOf can resolve.
    """
    rid  = new_id()
    name = fake.company()
    resource: dict = {
        "resourceType": "Organization",
        "id":   rid,
        "text": narrative("Juristic Person", name),
        "name": name,
        "address": [{"country": country}],
    }
    return resource, rid


def make_biobank(juristic_id: str, country: str = "DE") -> tuple[dict, str]:
    """
    MIABIS Biobank → FHIR Organization
    Profile: https://fhir.bbmri-eric.eu/StructureDefinition/miabis-biobank

    Required: identifier, name, address (country), partOf (juristic person)
    Extensions: infrastructuralCapabilities, organisationalCapabilities,
                bioprocessingAndAnalyticalCapabilities,
                qualityManagementStandard (string), description
    """
    rid = new_id()
    infra = random.choice(INFRA_CAPS)
    org   = random.choice(ORG_CAPS)
    bio   = random.choice(BIO_CAPS)
    name  = f"{fake.city()} Biobank"

    resource: dict = {
        "resourceType": "Organization",
        "id":   rid,
        "meta": {"profile": [PROFILE["biobank"]]},
        "text": narrative("Biobank", name),
        "extension": [
            ext(EXT["description"],
                valueString=fake.paragraph(nb_sentences=2)),
            ext(EXT["infra_cap"],
                valueCodeableConcept=codeable_concept(
                    f"{CS}/miabis-infrastructural-capabilities-cs", infra[0], infra[1])),
            ext(EXT["org_cap"],
                valueCodeableConcept=codeable_concept(
                    f"{CS}/miabis-organisational-capabilities-cs", org[0], org[1])),
            ext(EXT["bio_cap"],
                valueCodeableConcept=codeable_concept(
                    f"{CS}/miabis-bioprocessing-and-analytical-capabilities-cs",
                    bio[0], bio[1])),
            ext(EXT["quality_std"],
                valueString=random.choice(["ISO 9001", "ISO 15189", "ISO 17025", "OECD Guidelines"])),
        ],
        "identifier": [
            identifier("http://www.bbmri-eric.eu/",
                       fake.numerify("biobank-########")),
        ],
        "name":  name,
        "alias": [fake.company_suffix() + " Biobank"],
        "telecom": [
            {"system": "url", "value": f"https://{fake.domain_name()}"},
        ],
        "address": [{"country": country}],
        "partOf":  ref("Organization", juristic_id),
        "contact": [
            {
                "name": {
                    "family": fake.last_name(),
                    "given":  [fake.first_name()],
                },
                "telecom": [
                    {"system": "email", "value": fake.email()},
                    {"system": "phone", "value": fake.phone_number()},
                ],
            }
        ],
    }
    return resource, rid


def make_collection_org(biobank_id: str, country: str = "DE") -> tuple[dict, str]:
    """
    MIABIS CollectionOrganization → FHIR Organization
    Profile: https://fhir.bbmri-eric.eu/StructureDefinition/miabis-collection-organization

    Required: identifier, name, address (country), partOf (Biobank), description (1..1)
    Extensions: datasetType, sampleSource, sampleCollectionSetting,
                collectionDesign, useAndAccessConditions, publications, description
    """
    rid = new_id()
    col_id_value = fake.numerify("collection-########")
    dataset_types = random.sample(COL_DATASET_TYPES, k=random.randint(1, 3))
    name = f"{fake.word().capitalize()} Collection"

    resource: dict = {
        "resourceType": "Organization",
        "id":   rid,
        "meta": {"profile": [PROFILE["collection_org"]]},
        "text": narrative("Collection Organization", name),
        "extension": [
            # description is required (1..1 MS)
            ext(EXT["description"],
                valueString=fake.paragraph(nb_sentences=2)),
            *[
                ext(EXT["col_dataset_type"],
                    valueCodeableConcept=codeable_concept(
                        f"{CS}/miabis-collection-dataset-typeCS", dt[0], dt[1]))
                for dt in dataset_types
            ],
            ext(EXT["sample_source"],
                valueCodeableConcept=codeable_concept(
                    f"{CS}/miabis-sample-source-cs",
                    *random.choice(SAMPLE_SOURCES))),
            ext(EXT["col_setting"],
                valueCodeableConcept=codeable_concept(
                    f"{CS}/miabis-sample-collection-setting-cs",
                    *random.choice(COLLECTION_SETTINGS))),
            ext(EXT["col_design"],
                valueCodeableConcept=codeable_concept(
                    f"{CS}/miabis-collection-design-cs",
                    *random.choice(COLLECTION_DESIGNS))),
            ext(EXT["use_access"],
                valueCodeableConcept=codeable_concept(
                    f"{CS}/miabis-use-and-access-conditions-cs",
                    *random.choice(USE_ACCESS_CONDITIONS))),
            ext(EXT["publications"],
                valueString=f"doi:10.{fake.numerify('####')}/{fake.lexify('??????????')}"),
        ],
        "identifier": [identifier("http://www.bbmri-eric.eu/", col_id_value)],
        "name":   name,
        "alias":  [fake.catch_phrase()],
        "telecom": [{"system": "url", "value": f"https://{fake.domain_name()}"}],
        "address": [{"country": country}],
        "partOf":  ref("Organization", biobank_id),
        "contact": [
            {
                "name": {
                    "family": fake.last_name(),
                    "given":  [fake.first_name()],
                },
                "telecom": [
                    {"system": "email", "value": fake.email()},
                ],
            }
        ],
    }
    return resource, rid, col_id_value


def make_collection(
    col_org_id: str,
    col_identifier_value: str,
    specimen_ids: list[str],
) -> tuple[dict, str]:
    """
    MIABIS Collection → FHIR Group
    Profile: https://fhir.bbmri-eric.eu/StructureDefinition/miabis-collection

    Required characteristics: sex (1..*), materialType (1..*)
    Optional: ageRange, storageTemperature, diagnosis
    managingEntity → CollectionOrganization
    Specimens linked via MemberEntity R5 cross-version extension.
    """
    rid = new_id()
    col_name = fake.catch_phrase()
    char_cs = f"{CS}/miabis-characteristicCS"
    age_lo   = random.randint(18, 40)
    age_hi   = random.randint(age_lo + 10, 90)

    # characteristics — sex + materialType are required
    sexes        = random.sample(GENDERS[:-2], k=random.randint(1, 2))  # male/female
    mat_types    = random.sample(COLLECTION_SAMPLE_TYPES, k=random.randint(1, 3))
    storage_type = random.choice(STORAGE_TEMPS)
    diag         = random.choice(ICD10_CODES)
    incl_crit    = random.choice(INCLUSION_CRITERIA)

    characteristics: list[dict] = []

    # ageRange (optional)
    characteristics.append({
        "code":    codeable_concept(char_cs, "Age", "Age range"),
        "exclude": False,
        "valueRange": {
            "low":  {"value": age_lo, "unit": "years"},
            "high": {"value": age_hi, "unit": "years"},
        },
    })

    # sex (1..*)
    for sex in sexes:
        characteristics.append({
            "code":                codeable_concept(char_cs, "Sex", "Sex"),
            "exclude":             False,
            "valueCodeableConcept": codeable_concept(ADMIN_GENDER, sex),
        })

    # storageTemperature (optional)
    characteristics.append({
        "code":                codeable_concept(char_cs, "StorageTemperature",
                                                "Storage temperature"),
        "exclude":             False,
        "valueCodeableConcept": codeable_concept(
            f"{CS}/miabis-storage-temperature-cs",
            storage_type[0], storage_type[1]),
    })

    # materialType (1..*)
    for mt in mat_types:
        characteristics.append({
            "code":                codeable_concept(char_cs, "MaterialType",
                                                    "Material type"),
            "exclude":             False,
            "valueCodeableConcept": codeable_concept(
                f"{CS}/miabis-collection-sample-type-cs", mt[0], mt[1]),
        })

    # diagnosis (optional)
    characteristics.append({
        "code":                codeable_concept(char_cs, "Diagnosis", "Diagnosis"),
        "exclude":             False,
        "valueCodeableConcept": codeable_concept(ICD10, diag[0], diag[1]),
    })

    # MemberEntity extensions — one per Specimen
    member_extensions: list[dict] = [
        {
            "url":            EXT_MEMBER_ENTITY,
            "valueReference": ref("Specimen", sid),
        }
        for sid in specimen_ids
    ]

    resource: dict = {
        "resourceType": "Group",
        "id":   rid,
        "meta": {"profile": [PROFILE["collection"]]},
        "text": narrative("Collection", col_name),
        "extension": [
            ext(EXT["num_subjects"],
                valueInteger=len(specimen_ids)),
            ext(EXT["inclusion_criteria"],
                valueCodeableConcept=codeable_concept(
                    f"{CS}/miabis-inclusion-criteria-cs",
                    incl_crit[0], incl_crit[1])),
            *member_extensions,
        ],
        "identifier":     [identifier("http://www.bbmri-eric.eu/", col_identifier_value)],
        "name":           col_name,
        "type":           "person",   # FHIR R4 constraint; R5 would use "specimen"
        "actual":         True,
        "active":         True,
        "managingEntity": ref("Organization", col_org_id),
        "characteristic": characteristics,
    }
    return resource, rid


def make_donor(biobank_id: str) -> tuple[dict, str]:
    """
    MIABIS Donor → FHIR Patient
    Profile: https://fhir.bbmri-eric.eu/StructureDefinition/miabis-sample-donor

    Required: identifier, gender
    Optional: birthDate, datasetType extension (valueCode)
    """
    rid = new_id()
    gender = random.choice(GENDERS)
    resource: dict = {
        "resourceType": "Patient",
        "id":   rid,
        "meta": {"profile": [PROFILE["donor"]]},
        "text": narrative("Sample Donor", f"gender: {gender}"),
        "extension": [
            # DatasetTypeExtension — value[x] is code, not CodeableConcept
            ext(EXT["dataset_type"],
                valueCode=random.choice(DATASET_TYPES)),
        ],
        "identifier": [
            identifier(
                f"http://www.bbmri-eric.eu/biobank/{biobank_id}/donor",
                fake.numerify("DONOR-########"),
            )
        ],
        "gender":    gender,
        "birthDate": random_past_date(18, 90),
    }
    return resource, rid


def make_condition(donor_id: str) -> tuple[dict, str, str]:
    """
    MIABIS Condition → FHIR Condition
    Profile: https://fhir.bbmri-eric.eu/StructureDefinition/miabis-condition

    Required: subject → Donor
    Optional: identifier, code from DiagnosisVS (ICD-10)

    Note: This is for PATIENT-level diagnoses only.
    Sample-linked diagnoses should use Observation (not generated here).
    """
    rid             = new_id()
    icd_code, label = random.choice(ICD10_CODES)

    resource: dict = {
        "resourceType": "Condition",
        "id":   rid,
        "meta": {"profile": [PROFILE["condition"]]},
        "text": narrative("Condition", label),
        "identifier": [
            identifier("http://www.bbmri-eric.eu/condition",
                       fake.numerify("COND-########")),
        ],
        "clinicalStatus": codeable_concept(
            "http://terminology.hl7.org/CodeSystem/condition-clinical",
            "active", "Active"),
        "verificationStatus": codeable_concept(
            "http://terminology.hl7.org/CodeSystem/condition-ver-status",
            "confirmed", "Confirmed"),
        "code":    {"coding": [coding(ICD10, icd_code, label)]},
        "subject": ref("Patient", donor_id),
        "onsetDateTime": random_past_date(0.5, 8),
    }
    return resource, rid, icd_code


def make_sample(
    donor_id: str,
    col_identifier_value: str,
) -> tuple[dict, str]:
    """
    MIABIS Sample → FHIR Specimen
    Profile: https://fhir.bbmri-eric.eu/StructureDefinition/miabis-sample

    Required:  identifier, type (DetailedSampleTypeVS), subject → Donor
    Optional:  collection.collectedDateTime,
               collection.bodySite.coding (with system+version+code+display — SpecimenOntologyInvariant),
               processing[].extension[storageTemperature],
               extension[sampleCollection] (valueIdentifier linking to CollectionOrg),
               note.text (use restrictions)
    """
    rid        = new_id()
    stype      = random.choice(DETAILED_SAMPLE_TYPES)
    storage    = random.choice(STORAGE_TEMPS)
    body_site  = random.choice(ICDO3_SITES)

    resource: dict = {
        "resourceType": "Specimen",
        "id":   rid,
        "meta": {"profile": [PROFILE["sample"]]},
        "text": narrative("Sample", stype[1]),
        "extension": [
            # Links this specimen to a collection via identifier
            ext(EXT["sample_collection"],
                valueIdentifier=identifier(
                    "https://directory.bbmri-eric.eu/", col_identifier_value)),
        ],
        "identifier": [
            identifier("http://www.bbmri-eric.eu/sample",
                       fake.numerify("SAMPLE-########")),
        ],
        "type":    codeable_concept(
            f"{CS}/miabis-detailed-samply-type-cs", stype[0], stype[1]),
        "subject": ref("Patient", donor_id),
        "collection": {
            "collectedDateTime": random_past_date(0.1, 12),
            # SpecimenOntologyInvariant: system, version, code, and display are all required
            "bodySite": {
                "coding": [{
                    "system":  ICDO3_SYSTEM,
                    "version": ICDO3_VERSION,
                    "code":    body_site[0],
                    "display": body_site[1],
                }]
            },
        },
        # storageTemperature lives in Specimen.processing[].extension
        "processing": [{
            "extension": [
                ext(EXT["storage_temp"],
                    valueCodeableConcept=codeable_concept(
                        f"{CS}/miabis-storage-temperature-cs",
                        storage[0], storage[1])),
            ]
        }],
    }

    # Optional use restrictions note
    if random.random() < 0.4:
        resource["note"] = [{"text": random.choice([
            "Sample available for non-commercial research only.",
            "Requires Material Transfer Agreement before use.",
            "Restricted to consortium members.",
            "No restrictions on use.",
        ])}]

    return resource, rid


# ── Bundle assembly ─────────────────────────────────────────────────────────────

def generate_bundle(
    num_donors:            int = 10,
    num_collections:       int = 2,
    max_samples_per_donor: int = 3,
    country:               str = "DE",
) -> dict:
    """
    Assemble a FHIR R4 transaction Bundle with:

      JuristicPerson → Biobank → CollectionOrganization → Collection (Group)
                                                                ↑
      Donor → Condition          Sample (Specimen) ────────────┘
                   ↓subject ←── ↑subject
    """
    entries: list[dict] = []

    # ── Juristic person (legal owner)
    juristic, juristic_id = make_juristic_person(country)
    entries.append(bundle_entry(juristic))

    # ── Biobank
    biobank, biobank_id = make_biobank(juristic_id, country)
    entries.append(bundle_entry(biobank))

    # ── Collections: one CollectionOrg + one Collection Group each
    col_data: list[tuple[str, str]] = []   # (col_org_id, col_identifier_value)
    specimen_registry: dict[str, list[str]] = {}

    for _ in range(num_collections):
        col_org, col_org_id, col_id_val = make_collection_org(biobank_id, country)
        entries.append(bundle_entry(col_org))
        col_data.append((col_org_id, col_id_val))
        specimen_registry[col_id_val] = []

    # ── Donors → Conditions → Samples
    for _ in range(num_donors):
        donor, donor_id = make_donor(biobank_id)
        entries.append(bundle_entry(donor))

        condition, _cid, _icd = make_condition(donor_id)
        entries.append(bundle_entry(condition))

        n_samples = random.randint(1, max(1, max_samples_per_donor))
        for _ in range(n_samples):
            col_org_id, col_id_val = random.choice(col_data)
            sample, sample_id = make_sample(donor_id, col_id_val)
            entries.append(bundle_entry(sample))
            specimen_registry[col_id_val].append(sample_id)

    # ── Collection Groups (one per CollectionOrg)
    for col_org_id, col_id_val in col_data:
        spec_ids = specimen_registry[col_id_val]
        if spec_ids:
            collection, _ = make_collection(col_org_id, col_id_val, spec_ids)
            entries.append(bundle_entry(collection))

    return {
        "resourceType": "Bundle",
        "id":    new_id(),
        "type":  "transaction",
        "entry": entries,
    }


def validate_bundle(bundle: dict) -> bool:
    """Lightweight structural sanity check."""
    assert bundle.get("resourceType") == "Bundle"
    assert bundle.get("type") == "transaction"
    entries = bundle.get("entry", [])
    assert entries, "Bundle has no entries"
    for i, e in enumerate(entries):
        assert "resource" in e, f"entry[{i}] missing 'resource'"
        assert "request"  in e, f"entry[{i}] missing 'request'"
        assert "id" in e["resource"], f"entry[{i}].resource missing 'id'"

    types = [e["resource"]["resourceType"] for e in entries]
    assert "Organization" in types
    assert "Patient"      in types
    assert "Specimen"     in types
    assert "Condition"    in types
    assert "Group"        in types
    print("  [ok] structural validation passed")
    return True


# ── CLI ──────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a synthetic MIABIS-on-FHIR transaction Bundle (FHIR R4).\n"
            "Conforms to https://github.com/BBMRI-cz/miabis-on-fhir"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--donors",            type=int, default=10)
    parser.add_argument("--collections",       type=int, default=2)
    parser.add_argument("--samples-per-donor", type=int, default=3)
    parser.add_argument("--country",           type=str, default="DE",
                        help="ISO 3166-1 alpha-2 country code")
    parser.add_argument("--output",            type=str, default="miabis_bundle.json")
    parser.add_argument("--seed",              type=int, default=None,
                        help="Random seed for reproducibility")
    parser.add_argument("--no-validate",       action="store_true",
                        help="Skip structural validation")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        Faker.seed(args.seed)

    print("Generating MIABIS-on-FHIR synthetic data …")
    bundle = generate_bundle(
        num_donors=args.donors,
        num_collections=args.collections,
        max_samples_per_donor=args.samples_per_donor,
        country=args.country,
    )

    if not args.no_validate:
        print("Validating …")
        validate_bundle(bundle)

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2, ensure_ascii=False)

    counts: dict[str, int] = {}
    for e in bundle["entry"]:
        rt = e["resource"]["resourceType"]
        counts[rt] = counts.get(rt, 0) + 1

    print(f"\nWritten: {args.output}")
    print(f"Total bundle entries: {len(bundle['entry'])}")
    for rt, n in sorted(counts.items()):
        print(f"  {rt:<25} {n:>4}")


if __name__ == "__main__":
    main()
