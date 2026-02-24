# MIABIS-on-FHIR Synthetic Data Generator

A Python script that generates synthetic [MIABIS-on-FHIR](https://github.com/BBMRI-cz/miabis-on-fhir) data as a FHIR R4 transaction Bundle (JSON).

Conforms to the **BBMRI-cz MIABIS-on-FHIR Implementation Guide**
- Canonical: `https://fhir.bbmri-eric.eu`
- Source: <https://github.com/BBMRI-cz/miabis-on-fhir>

---

## Generated resources

Each bundle run produces one biobank hierarchy plus configurable numbers of donors and samples:

| FHIR resource | MIABIS concept | Profile |
|---|---|---|
| `Organization` (no profile) | JuristicPerson | — |
| `Organization` | Biobank | `miabis-biobank` |
| `Organization` | CollectionOrganization | `miabis-collection-organization` |
| `Group` | Collection | `miabis-collection` |
| `Patient` | SampleDonor | `miabis-sample-donor` |
| `Condition` | Condition (diagnosis) | `miabis-condition` |
| `Specimen` | Sample | `miabis-sample` |

Relationships:

```
JuristicPerson ← Biobank.partOf
Biobank        ← CollectionOrganization.partOf
CollectionOrganization ← Collection.managingEntity
Collection ←── (MemberEntity ext) ── Specimen
Patient    ←── Condition.subject
Patient    ←── Specimen.subject
```

---

## Requirements

```
pip install faker
```

Python 3.10+ is required (uses `tuple[...]` type hints).

---

## Usage

```
python generate_miabis_data.py [options]
```

| Option | Default | Description |
|---|---|---|
| `--donors N` | 10 | Number of sample donors to generate |
| `--collections N` | 2 | Number of collection organisations (each gets one Collection Group) |
| `--samples-per-donor N` | 3 | Maximum samples per donor (actual count is random 1..N) |
| `--country CODE` | `DE` | ISO 3166-1 alpha-2 country code for addresses |
| `--output FILE` | `miabis_bundle.json` | Output file path |
| `--seed N` | _(none)_ | Random seed for reproducible output |
| `--no-validate` | _(off)_ | Skip the built-in structural sanity check |

### Examples

```bash
# Default: 10 donors, 2 collections → ~50 bundle entries
python generate_miabis_data.py

# Larger dataset, Czech country code, fixed seed
python generate_miabis_data.py --donors 100 --collections 5 --country CZ --seed 42

# Write to a custom file, skip sanity check
python generate_miabis_data.py --output test_bundle.json --no-validate
```

The script prints a summary on completion:

```
Generating MIABIS-on-FHIR synthetic data …
Validating …
  [ok] structural validation passed

Written: miabis_bundle.json
Total bundle entries: 50
  Condition                   10
  Group                        2
  Organization                 4
  Patient                     10
  Specimen                    24
```

---

## Validation against the HL7 FHIR Validator

The generated bundle can be validated against the official HL7 FHIR validator CLI together with the locally built Czech MIABIS-on-FHIR IG package.

### 1. Download the validator

```bash
curl -L https://github.com/hapifhir/org.hl7.fhir.core/releases/latest/download/validator_cli.jar \
     -o validator_cli.jar
```

### 2. Build the Czech IG package with SUSHI

The Czech IG is not published to the FHIR package registry, so it must be compiled locally.

```bash
# Install SUSHI (Node.js required)
npm install -g fsh-sushi

# Clone the IG source
git clone https://github.com/BBMRI-cz/miabis-on-fhir.git miabis-on-fhir-ig

# Compile FSH → FHIR resources
cd miabis-on-fhir-ig
sushi .
cd ..

# Assemble a validator-compatible package directory
mkdir -p miabis-on-fhir-ig/local-package
cp miabis-on-fhir-ig/fsh-generated/resources/*.json miabis-on-fhir-ig/local-package/

cat > miabis-on-fhir-ig/local-package/package.json <<'EOF'
{
  "name": "fhir.bbmri-eric.eu",
  "version": "1.0.0",
  "description": "MIABIS on FHIR Implementation Guide",
  "fhirVersions": ["4.0.1"],
  "dependencies": {
    "hl7.fhir.r4.core": "4.0.1"
  }
}
EOF
```

### 3. Run the validator

```bash
python generate_miabis_data.py --seed 42

java -jar validator_cli.jar miabis_bundle.json \
  -version 4.0.1 \
  -ig miabis-on-fhir-ig/local-package \
  -output validation_report.json
```

### Validation results

| Severity | Count | Notes |
|---|---|---|
| fatal | 0 | |
| error | 0 | |
| warning | 26 | See below |
| information | 44 | Informational only |

**Remaining warnings (not fixable):**

- **24 × ICD-O-3 "unknown code"** — The public terminology server (`tx.fhir.org`) only holds a fragment of ICD-O-3 and does not recognise sub-codes such as `C50.1`. The codes are valid ICD-O-3 topography codes; this is a server-side limitation.
- **2 × MemberEntity R5 extension advisory** — The Czech IG intentionally uses the FHIR R5 cross-version extension `http://hl7.org/fhir/5.0/StructureDefinition/extension-Group.member.entity` to link `Specimen` resources to a `Group` (Collection) in FHIR R4. The validator flags this as advisory but it is correct by design.

---

## Key implementation notes

### Collection as Group (not Organization)
The Czech MIABIS-on-FHIR IG models a Collection as a FHIR `Group` resource (not `Organization`). The Collection Group holds population-level characteristics (sex, material type, age range, storage temperature, diagnosis) and links individual specimens via the MemberEntity cross-version extension.

### StorageTemperature placement
On `Specimen` resources, storage temperature lives in `Specimen.processing[].extension`, not at the top level.

### ICD-O-3 SpecimenOntologyInvariant
The profile requires that `Specimen.collection.bodySite.coding` entries include all four fields — `system`, `version`, `code`, and `display`. The ICD-O-3 version string recognised by the terminology server is `"2000"` (not `"3.2"`).

### DatasetType on Patient
The `miabis-dataset-type-extension` on `Patient` uses `valueCode` (a plain code string), not `valueCodeableConcept`.

### fhir.resources library
`fhir.resources` v8.x (installed by default with Pydantic v2) validates against FHIR R5, not R4, and will produce false positives on R4 resources. This script generates plain Python dicts and does not use `fhir.resources` for generation. For authoritative R4 validation use the HL7 FHIR validator CLI as described above.
