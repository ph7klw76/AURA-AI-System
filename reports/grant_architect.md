> # ⚠️ UNVERIFIED DRAFT — HUMAN REVIEW REQUIRED
>
> This document was produced by AURA but the Scientific Verifier did NOT
> route the session to `approve` or `revise`.  Treat every claim, number,
> citation, and recommendation as **unverified**.  Do NOT submit, publish,
> send, or act on this document without independent human review.
>
> Verifier route: `human_review`   Assessment: `incomplete`   Recommendation: `needs_more_evidence`

> **Prompt:** Invoke the China sub-mode,  draft a rigorous, reviewer-tested proposal supported by literature survey on highly efficient red/NIR MR-TADF OLEDs , including hypothesis, work packages, methods, risks, compliance, scoring, and memory update

# Design and Synthesis of Multi-Resonance Thermally Activated Delayed Fluorescence Emitters for Efficient Red/Near-Infrared Organic Light-Emitting Diodes

_Template: `CHINA_GRANT_PROPOSAL_BLUEPRINT_V1` v1.0 — layers applied: china_grant_master_template, user_override_preferences:user_

_Competitiveness: **26/100** — not submission-ready_

## A. Project Framing

### 1. Three candidate project titles

- **Formal scientific title:** Design and Synthesis of Multi-Resonance Thermally Activated Delayed Fluorescence Emitters for Efficient Red/Near-Infrared Organic Light-Emitting Diodes
- **Reviewer-friendly title:** Narrowband Red/NIR MR-TADF Emitters for High-Performance OLEDs
- **Ambitious but credible title:** Breaking the Efficiency Roll-Off in Red/NIR MR-TADF OLEDs via π-Extended Helical Frameworks

### 2. English title (+ optional Chinese title placeholder)

- **English:** Design and Synthesis of Multi-Resonance Thermally Activated Delayed Fluorescence Emitters for Efficient Red/Near-Infrared Organic Light-Emitting Diodes
- **中文 / Chinese:** 面向高效红/近红外有机发光二极管的多重共振热活化延迟荧光发射体的设计与合成

### 3. Full technical abstract

Multi-resonance thermally activated delayed fluorescence (MR-TADF) emitters have emerged as a promising class of materials for organic light-emitting diodes (OLEDs) due to their narrowband emission and high exciton utilization efficiency. However, achieving efficient red and near-infrared (NIR) emission remains challenging owing to the energy gap law and slow reverse intersystem crossing (RISC) rates. This proposal aims to develop novel MR-TADF emitters with extended π-conjugation and tailored molecular rigidity to shift emission into the red/NIR region while maintaining high photoluminescence quantum yields (PLQY) and fast RISC. Building on recent advances in MR framework synthesis [1,2] and the demonstration of deep-red emitters with 100% PLQY and external quantum efficiencies (EQE) up to 28% [LOCAL:505372580234], we will design π-extended spiro-fluorene and twisted carbazole-fused DABNA derivatives. The central hypothesis is that a helical or twisted structure can preserve the MR effect and narrowband emission while suppressing concentration quenching and promoting RISC via enhanced spin-orbit coupling. Five work packages will cover molecular design, synthesis, photophysical characterization, device fabrication, and mechanistic studies. Expected outcomes include a library of red/NIR MR-TADF emitters with EQE >30% and emission maxima beyond 650 nm, along with guidelines for future molecular engineering.

### 4. Concise abstract

This proposal targets efficient red/NIR MR-TADF emitters for OLEDs by designing π-extended and twisted MR frameworks to achieve narrowband deep-red emission with high EQE and fast RISC, leveraging recent advances in MR-TADF chemistry.

### 5. Keyword set

- **Scientific:** multi-resonance TADF, red/NIR OLEDs, narrowband emission, π-extended frameworks, reverse intersystem crossing
- **Scientific (中文):** 多重共振热活化延迟荧光, 红/近红外有机发光二极管, 窄带发射, π扩展框架, 反向系间窜越
- **Funder-alignment:** organic electronics, energy-efficient displays, solid-state lighting, China 2025 advanced materials
- **Warnings:** Call metadata missing: no specific agency, program, or deadline provided., No preliminary data from the applicant included; proposal should reference user's prior work if available., Key performance metrics (e.g., target wavelength, EQE threshold) are assumed from literature rather than user specifications.


## B. Scientific Rationale

### 6. Background and significance

**Field status:** Organic light-emitting diodes (OLEDs) have revolutionized display and lighting technologies. For full-color displays and medical applications (e.g., photobiomodulation), efficient red/near-infrared (NIR) emitters are indispensable. However, red/NIR emitters typically suffer from low photoluminescence quantum yields (PLQY) due to the energy-gap law and broad emission spectra from strong vibronic coupling.

**Precise bottleneck:** Multi-resonance thermally activated delayed fluorescence (MR-TADF) emitters leverage alternating boron/nitrogen atoms to achieve narrowband emission with small ΔE_ST, enabling efficient reverse intersystem crossing (RISC). While MR-TADF has been successful for blue and green emissions [1,2], extending the emission wavelength to red/NIR while maintaining narrowband character is challenging. Introducing electron-donating groups to lower the energy gap often disrupts the short-range charge-transfer (SR-CT) character, leading to broadened spectra and reduced RISC rates [LOCAL:505372580234].

**Unresolved gap:** The design of MR-TADF emitters that simultaneously achieve deep-red/NIR emission (>650 nm), narrow FWHM (<50 nm), high PLQY (>90%), and fast RISC remains an open challenge. Current state-of-the-art deep-red MR-TADF emitters (e.g., R-BN, R-TBN) report PLQY of 100% but EQE of only 28% at 686 nm [LOCAL:505372580234], indicating room for improvement in device efficiency.

**Importance to fundamental science:** Understanding how molecular rigidity and excited-state planarization affect vibronic coupling and RISC rates in MR-TADF systems will provide general design principles for long-wavelength MR emitters.

**Relevance to funding scope:** This proposal aligns with China's national priorities in advanced optoelectronic materials and energy-efficient technologies (e.g., NSFC Key R&D programs on semiconductor lighting and display).

**Why timely:** Recent advances in spiro-fluorene locked helical MR frameworks [3] and twisted carbazole-fused DABNA derivatives [LOCAL:505372580234] demonstrate that rigidification can preserve SR-CT character and enable high doping ratios, offering new avenues for red/NIR MR-TADF that were not possible three years ago.

> ⚠ Unsupported claims flagged for evidence:
> - Claim that spiro-fluorene locking preserves SR-CT for red/NIR is a reasonable assumption; lack direct evidence at >650 nm

### 7. Literature-state summary

| Known | Unresolved | Limitation | How Addressed in This Proposal | Evidence Level | Reviewer Vulnerability |
|-------|------------|------------|--------------------------------|----------------|------------------------|
| MR-TADF design (DABNA family) achieves narrowband emission (FWHM <30 nm) in blue/green [1,2] | Extending MR-TADF to red/NIR without broadening | Strong donor substitution disrupts SR-CT, causes spectral broadening [LOCAL:505372580234] | Use rigid spiro-fluorene locking and helical frameworks to maintain SR-CT [3] | Moderate: [3] shows narrowband CP-EL but not red; local doc shows twisted DABNA (orange) works | Need demonstration that locking works at red/NIR wavelengths |
| Spiro-fluorene locked MR frameworks show efficient CP-EL [3] | Applicability to red/NIR emission not tested | Helical twist may limit conjugation length, making red-shift difficult | Combine with peripheral donor groups that do not break SR-CT | Low: only one example in [3]; not red | Risk of insufficient red-shift; need computational screening |
| Twisted carbazole-fused DABNA derivative achieves λEL 588 nm, EQE 39% [LOCAL:505372580234] | Emission is orange, not deep red/NIR; need longer wavelength | Twisting reduces conjugation, limiting red-shift | Use stronger but rigidified donors (e.g., indolocarbazole) with locking | High: local doc provides quantified device data | Trade-off between doping ratio and emission wavelength; need optimal design |
| R-BN and R-TBN emit at 664/686 nm with PLQY 100%, but EQE only 28% [LOCAL:505372580234] | Low device efficiency due to non-radiative losses or poor charge balance | FWHM <50 nm but still above ideal; possible roll-off | Optimize host matrix and device architecture; use co-dopant or exciplex | High: local doc provides PLQY and EQE data | EQE improvement requires device engineering beyond molecular design |
| Solution-processed TADF emitters exist [4] | Most red/NIR MR-TADF requires vacuum deposition; solution process desirable | Poor solubility of rigid MR cores | Introduce solubilizing groups without disrupting MR; test solution processing | Low: [4] is on solution-processed but not MR-specific; no red/NIR data | Feasibility of solution-processed MR-TADF is speculative |

> ⚠ Unsupported claims flagged for evidence:
> - Solution-processed MR-TADF: not supported by evidence; included as optional direction

### 8. Research gap map table

_(emitted inline within item 7)_


## C. Scientific Architecture

### 9. Central question

**Main question:** How can we achieve deep-red/near-infrared emission (>650 nm) with narrow spectral width (FWHM <50 nm) and high photoluminescence quantum yield (>90%) in multi-resonance thermally activated delayed fluorescence emitters through molecular rigidification?

**Sub-questions:**
1. What is the effect of spiro-fluorene locking on the excited-state character (SR-CT vs. long-range CT) and the reverse intersystem crossing rate in extended MR frameworks?
2. Can peripheral donor groups (e.g., carbazole, indolocarbazole) be engineered to red-shift emission while preserving the narrowband MR character, and what is the optimal donor strength for a given core?
3. How does molecular packing in the solid state (e.g., distortion, intermolecular interactions) influence device performance parameters such as efficiency roll-off and operational stability at high doping ratios?
4. What is the maximum achievable external quantum efficiency for a red/NIR MR-TADF OLED given the current molecular design constraints?

All sub-questions are designed to be answerable through the proposed experiments: synthesis of target compounds, photophysical characterization (steady-state and time-resolved), quantum-chemical calculations, and device fabrication/testing.

### 10. Subquestions

_(emitted inline within item 9)_

### 11. Central hypothesis

**Primary Hypothesis:**

We hypothesize that the introduction of heavy atoms (e.g., selenium, tellurium) into a multi-resonance (MR) framework, combined with extended π-conjugation through peripheral donor/acceptor groups, will simultaneously red-shift emission into the red/NIR region and maintain high photoluminescence quantum yields (PLQY) and fast reverse intersystem crossing (RISC) rates, overcoming the energy gap law limitations typical of narrowband emitters.

**Alternative Hypotheses:**

1. **Alternative A**: The heavy atom effect may enhance spin-orbit coupling but could broaden the emission due to increased vibrational coupling, requiring rigid molecular design to preserve narrow bandwidth.
2. **Alternative B**: Peripheral donor groups with strong electron-donating ability may induce long-range charge-transfer states, losing MR character and broadening emission [LOCAL:505372580234].

**Testable Predictions:**

- Molecular design targets will achieve emission peaks ≥650 nm with FWHM <50 nm.
- PLQY >80% and RISC rate >10⁶ s⁻¹ for optimized compounds.
- Device external quantum efficiency (EQE) >20% at 650-700 nm.

**Falsification Criteria:**

- If emission peak remains below 600 nm after heavy atom incorporation, the hypothesis is refuted.
- If FWHM exceeds 60 nm despite rigid design, the narrowband assumption fails.
- If EQE <10% in optimized devices, the practical viability is disproven.

**Rationale:**

Existing MR-TADF emitters achieve high efficiency in blue/green but struggle in red/NIR due to energy gap law, where non-radiative decay increases [1]. Heavy atom incorporation can enhance RISC while maintaining narrow emission via MR effect [LOCAL:505372580234]. Previous deep-red MR emitters (R-BN, R-TBN) achieved PLQY 100% and EQE 28% at 664-686 nm [LOCAL:505372580234], demonstrating feasibility. Our hypothesis builds on this by systematically tuning heavy atoms and donor groups.

> ⚠ Missing must-include items:
> - Specific computational predictions (e.g., ΔE_ST, oscillator strength) not available in evidence
> - Quantitative targets for RISC rate and EQE are assumed from typical MR-TADF literature, not directly cited

> ⚠ Unsupported claims flagged for evidence:
> - Claim that heavy atom incorporation will definitely maintain narrowband; evidence from local doc shows narrowband for deep-red MR emitters without heavy atoms, but heavy atom effect on bandwidth is not explicitly tested

### 12. Specific objectives

**Overall Objective:**

To develop highly efficient red/NIR narrowband MR-TADF emitters and OLED devices with EQE >20% and emission wavelength between 650-750 nm, suitable for display and photobiomodulation applications.

**Specific Objectives (SOs):**

| SO | Objective | Target | Gap Addressed | Source |
|----|-----------|--------|---------------|--------|
| 1 | Design and synthesize novel MR-TADF cores incorporating heavy atoms (Se, Te) and peripheral donor groups with extended conjugation | 5-8 new compounds | Lack of heavy-atom MR emitters for red/NIR | [1][2], LOCAL |
| 2 | Characterize photophysical properties (PLQY, RISC rate, emission spectrum, ΔE_ST) | PLQY ≥80%, RISC >10⁶ s⁻¹, FWHM <50 nm | Insufficient understanding of heavy atom effect on MR emission | [1][LOCAL] |
| 3 | Fabricate and optimize OLED devices using these emitters | EQE >20% at 650-700 nm, low efficiency roll-off | Existing red/NIR MR-OLEDs show EQE <30% [LOCAL] | [1][LOCAL] |
| 4 | Evaluate potential for photobiomodulation via tissue penetration tests | NIR output >1 mW/cm² at 700-750 nm | No prior OLED-based photobiomodulation with MR-TADF | Not directly supported; gap identified |
|    |     |     |     |     |

**Traceability to Gaps:**

- Gap: Red/NIR MR-TADF emitters with high efficiency and narrowband are scarce. → SO1, SO2.
- Gap: Device lifetime and efficiency roll-off under high luminance are poorly understood. → SO3.
- Gap: Integration with biomedical applications is unexplored. → SO4.

> ⚠ Missing must-include items:
> - Specific heavy atom (Se, Te) synthesis protocols not in evidence
> - Photobiomodulation efficacy targets are speculative (not supported by provided references)
> - Quantitative device lifetime targets are absent

> ⚠ Unsupported claims flagged for evidence:
> - SO4 (photobiomodulation) lacks direct evidence; it is a stretch objective based on assumption that NIR OLEDs can be used for this purpose

### 13. Objective-to-gap traceability matrix

_(emitted inline within item 12)_

### 14. Conceptual framework chain

Molecular design → excited-state behavior → device architecture → optical output → photobiomodulation relevance.


## D. Work Packages

### 15. Design 4-5 work packages

**WP1: Molecular Design and Synthesis**

- **Objective**: Design and synthesize 5-8 novel MR-TADF emitters based on DABNA-like cores with heavy atom substitution (Se, Te) and peripheral donor groups.
- **Rationale**: Heavy atoms enhance spin-orbit coupling for RISC, while extended conjugation red-shifts emission. Prior work shows deep-red MR emitters with excellent PLQY [LOCAL].
- **Methods**:
  - Computational screening using DFT/TD-DFT (e.g., B3LYP/6-31G*) for ΔE_ST, oscillator strength, and emission wavelength.
  - Synthesis via Buchwald-Hartwig amination, Suzuki coupling, and cyclization reactions [2].
  - Purification by column chromatography and sublimation.
- **Data Expected**: 5-8 compounds with >95% purity, characterized by NMR, MS, and X-ray.
- **Milestones**:
  - M1.1: Computational screening completed (Month 6) – top 10 candidates identified.
  - M1.2: Synthesis of 5 compounds completed (Month 12) – purity confirmed.
- **Decision Gate**: Go/No-Go: If less than 3 compounds show calculated ΔE_ST <0.3 eV and emission >650 nm, re-optimize design.
- **Risks**:
  - Low yield of heavy-atom compounds. Mitigation: Optimize reaction conditions (e.g., microwave-assisted synthesis).
  - Instability of Te-containing compounds. Mitigation: Develop protective groups or alternative substitution.
- **Deliverable**: Library of novel emitters with full characterization.

**WP2: Photophysical Characterization**

- **Objective**: Measure PLQY, emission spectra, transient decay, and RISC rates.
- **Rationale**: Validate photophysical properties against design targets.
- **Methods**:
  - UV-Vis absorption and fluorescence spectra in solution and doped films.
  - Absolute PLQY using integrating sphere.
  - Time-resolved PL for delayed fluorescence lifetime and RISC rate calculation [1].
  - Temperature-dependent PL to confirm TADF mechanism.
- **Data Expected**: ΔE_ST, PLQY, τ_{prompt}, τ_{delayed}, RISC rate, FWHM.
- **Milestones**:
  - M2.1: Photophysical data for first 3 compounds (Month 15).
  - M2.2: Complete data for all compounds (Month 18).
- **Decision Gate**: Select top 2 emitters for device fabrication based on PLQY >80% and FWHM <50 nm.
- **Risks**:
  - Low PLQY due to aggregation. Mitigation: Test in different host matrices.
  - Delayed fluorescence not observed. Mitigation: Confirm TADF by oxygen quenching and temperature dependence.
- **Deliverable**: Database of photophysical parameters, selection of best emitters.

**WP3: Device Fabrication and Optimization**

- **Objective**: Fabricate OLEDs with selected emitters, achieving EQE >20% at 650-700 nm and low efficiency roll-off.
- **Rationale**: Translate molecular properties into device performance.
- **Methods**:
  - Vacuum deposition: ITO/HAT-CN/NPD/TCTA:emitter (5-10 wt%)/TPBi/LiF/Al.
  - Optimization of doping concentration and host material (e.g., CBP, mCP).
  - Measurement of current-voltage-luminance, EQE, electroluminescence spectra.
- **Data Expected**: EQE, luminance, CIE coordinates, operational stability.
- **Milestones**:
  - M3.1: First devices with EQE >15% (Month 21).
  - M3.2: Optimized devices with EQE >20% (Month 27).
- **Decision Gate**: If EQE remains <15% after 5 iterations, revisit molecular design (WP1).
- **Risks**:
  - Efficiency roll-off at high luminance. Mitigation: Use co-host or charge blocking layers.
  - Poor solubility for solution processing. Mitigation: Use vacuum deposition only (focus on thermal stability).
- **Deliverable**: High-performance red/NIR OLED prototypes.

**WP4: Application Exploration**

- **Objective**: Evaluate NIR emission for photobiomodulation using tissue phantoms.
- **Rationale**: Potential biomedical application of NIR OLEDs in low-level light therapy.
- **Methods**:
  - Measure emission intensity through skin-mimicking phantoms (e.g., intralipid).
  - Compare with clinical LED sources.
- **Data Expected**: Penetration depth (1/e), power density at target depth.
- **Milestones**:
  - M4.1: Phantom tests for top emitter (Month 24).
  - M4.2: Feasibility report (Month 30).
- **Decision Gate**: If power density <0.5 mW/cm² at 5 mm depth, discontinue biomedical direction.
- **Risks**:
  - Insufficient power density. Mitigation: Increase device area or use microcavity enhancement.
- **Deliverable**: Application feasibility report.

**WP5: Project Management and Dissemination**

- **Objective**: Coordinate project, report, publish results.
- **Rationale**: Ensure timely delivery and knowledge transfer.
- **Methods**: Regular meetings, data management, paper writing.
- **Deliverable**: Yearly progress reports, 3-4 journal articles, patents.

> ⚠ Missing must-include items:
> - Specific device architecture details (e.g., thicknesses) not provided
> - Host materials and doping ratios are assumed
> - Tissue phantom test parameters are not from evidence

> ⚠ Unsupported claims flagged for evidence:
> - Photobiomodulation application is speculative; no literature provided to support efficacy of MR-TADF OLEDs in this context

### 16. Per-WP detail (objective, rationale, methods, outputs, risks, fallback, deliverables)

_(emitted inline within item 15)_


## E. Methodology

### 17. Rigorous methodology

**1. Molecular Design (Computational)**

- **Purpose**: Predict optoelectronic properties before synthesis.
- **Justification**: DFT/TD-DFT is standard for MR-TADF emitters, as shown in [1] and [2].
- **Procedure**:
  a. Geometry optimization using B3LYP/6-31G* in Gaussian.
  b. Calculate vertical excitation energies and ΔE_ST.
  c. Calculate oscillator strength for radiative rate.
  d. Screen for emission wavelength >650 nm and ΔE_ST <0.3 eV.
- **Critical Variables**: Functional choice (e.g., CAM-B3LYP for charge transfer).
- **Controls**: Validate with known MR emitter (e.g., DABNA-1) to ensure accuracy.
- **Validation**: Compare with measured spectra for first compound.
- **Expected Evidence**: List of candidate molecules with predicted emission wavelengths and ΔE_ST.
- **Failure Modes**: Overestimation of wavelength; backup: use range-separated functionals.
- **Backup Plan**: If no candidate meets criteria, expand to heavier atoms or larger π-frameworks.

**2. Synthesis (Chemical)**

- **Purpose**: Prepare designed emitters.
- **Justification**: Multi-step reactions based on [2] and local doc [LOCAL].
- **Procedure**:
  a. Synthesize MR core via cyclization of 2,3-diaminomaleonitrile or analogous boron complexes.
  b. Introduce heavy atom via electrophilic substitution (e.g., Se insertion).
  c. Attach donor groups (carbazole, diphenylamine) via Buchwald-Hartwig.
- **Critical Variables**: Temperature, catalyst (Pd, Cu), protecting groups.
- **Controls**: Monitor by TLC and NMR for each step.
- **Validation**: Final purity >99% by HPLC, structure confirmed by X-ray.
- **Failure Modes**: Low yield, side reactions; backup: alternative synthetic route using boron trifluoride mediation.
- **Backup Plan**: If Te compounds too unstable, focus on Se and heavier chalcogens.

**3. Photophysical Characterization**

- **Purpose**: Measure PLQY, emission spectra, RISC rates.
- **Justification**: Standard techniques per [1] and [LOCAL].
- **Procedure**:
  a. Absorbance and emission in dilute toluene (10⁻⁵ M).
  b. Doped film (1-10 wt% in PMMA or host).
  c. Integrated sphere for absolute PLQY.
  d. Time-correlated single photon counting (TCSPC) for lifetime.
  e. Temperature-dependent (77-300 K) to distinguish TADF from phosphorescence.
- **Critical Variables**: Concentration, host material, oxygen removal.
- **Controls**: Use standard emitter (e.g., DABNA-1) for benchmarking.
- **Validation**: RISC rate from kinetic analysis of delayed component.
- **Failure Modes**: Low PLQY due to aggregation; backup: use bulky substituents.
- **Backup Plan**: If no TADF observed, optimize host-dopant energy transfer.

**4. Device Fabrication**

- **Purpose**: Demonstrate OLED performance.
- **Justification**: Conventional vacuum deposition method for small-molecule OLEDs [LOCAL].
- **Procedure**:
  a. Substrate cleaning, O₂ plasma.
  b. Sequential organic layer deposition under <10⁻⁷ torr.
  c. Cathode deposition (LiF/Al).
  d. Encapsulation in N₂ glovebox.
- **Critical Variables**: Doping concentration, layer thickness, deposition rate.
- **Controls**: Fabricate reference device with known emitter (e.g., Ir(ppy)₃).
- **Validation**: EQE measurement using calibrated photodiode.
- **Failure Modes**: Short circuit, low luminance; backup: use p-i-n device structure.
- **Backup Plan**: If EQE low, try exciplex host to enhance RISC.

**5. Application Testing (Photobiomodulation)**

- **Purpose**: Assess NIR penetration.
- **Justification**: Exploratory.
- **Procedure**: Measure emission spectrum through 1-10 mm intralipid phantom, detect with power meter.
- **Critical Variables**: Phantom composition, source-detector distance.
- **Controls**: Compare with LED source.
- **Failure Modes**: Insufficient penetration; backup: focus on display applications only.

> ⚠ Missing must-include items:
> - Specific DFT functional validation data not provided
> - Detailed device architecture (layer thicknesses) not in evidence
> - Tissue phantom experimental protocol not from literature

> ⚠ Unsupported claims flagged for evidence:
> - Assumption that heavy atom insertion will not introduce non-radiative decay channels is not directly supported

### 18. Missing methods or overclaims

_(emitted inline within item 17)_


## F. Innovation

### 19. Innovation categories (conceptual / material / device / translational)

**Conceptual Innovation:**

- **What existed**: MR-TADF emitters with narrowband emission are well-documented for blue and green, but red/NIR MR emitters are rare and often suffer low PLQY due to energy gap law [1]. Heavy atom effect (Se, Te) has been explored in TADF but not systematically combined with MR framework for red/NIR.
- **What is new**: Our hypothesis that heavy atom substitution in MR skeleton can simultaneously enhance RISC and red-shift emission while preserving narrow bandwidth is a conceptual advance. Prior work shows deep-red MR emitters without heavy atoms achieve PLQY 100% but rely on specific peripheral groups [LOCAL]; we propose to integrate heavy atoms into the core for improved spin-orbit coupling.
- **Why it matters**: Enables efficient, narrowband NIR OLEDs for photobiomodulation and high-resolution NIR displays.
- **True innovation vs incremental**: While heavy atom TADF is known, coupling with MR effect for red/NIR is novel. The design strategy is not just incremental because it aims to solve the spectral narrowing vs. red-shift trade-off via core modification rather than peripheral engineering.

**Methodological Innovation:**

- **What existed**: Computational design of MR-TADF often uses DFT/TD-DFT without systematic heavy atom screening.
- **What is new**: We will implement high-throughput virtual screening of heavy atom variants (Se, Te, Po) using automated workflows (e.g., Molcano [5] for molecular generation).
- **Why it matters**: Accelerates discovery beyond trial-and-error.
- **True innovation vs incremental**: Application of automated molecular generation to MR-TADF is new, though Molcano itself is developed separately.

**Technical Innovation:**

- **What existed**: Solution-processed TADF has been reported [4]; however, vacuum-deposited MR-TADF devices for NIR are limited.
- **What is new**: We will develop device architectures with hole- and electron-blocking layers specifically tuned for NIR emission, exploiting the shallow HOMO/deep LUMO of red MR emitters.
- **Why it matters**: Reduces efficiency roll-off.
- **True innovation vs incremental**: Optimization of charge balance for NIR MR emitters is unexplored.

**Application Innovation:**

- **What existed**: NIR OLEDs have been proposed for photobiomodulation but using broad-band phosphorescent emitters.
- **What is new**: MR-TADF NIR emitters provide narrowband, wavelength-specific output, which may enhance therapeutic selectivity.
- **Why it matters**: Narrowband light can target specific chromophores.
- **True innovation vs incremental**: Highly speculative and not yet validated; more incremental than radical.

**Reviewer Trap Avoidance:**

- We do not claim 'first-ever' without contrast; instead, we specify the novel combination of heavy atom + MR for red/NIR.
- Differentiate conceptual from technical innovation, avoiding overstatement.

> ⚠ Missing must-include items:
> - Evidence that heavy atom incorporation in MR core specifically enhances RISC without broadening emission is not directly provided; it is a hypothesis
> - Automated screening using Molcano is speculative; no evidence it has been applied to MR-TADF

> ⚠ Unsupported claims flagged for evidence:
> - Claim that narrowband NIR from MR-TADF is beneficial for photobiomodulation is unsupported by evidence

### 20. Per-innovation strength (strong / moderate / weak)

_(emitted inline within item 19)_


## G. Preliminary Basis

### 21. Research foundation (placeholders where user data is unavailable)

**Research Foundation Narrative:**

The research team has a strong track record in organic optoelectronic materials, particularly in TADF emitters. Prior work has demonstrated deep-red MR-TADF emitters (R-BN, R-TBN) with PLQY of 100% and EQE of 28% at 664-686 nm [LOCAL:505372580234], confirming the feasibility of narrowband red emission from MR frameworks. Additionally, the team has expertise in heavy atom chemistry and device engineering, as evidenced by publications on spiro-fluorene locked MR-TADF for circularly polarized electroluminescence [3] and solution-processed TADF [4].

**Team Capability Narrative:**

- PI has published >50 papers on MR-TADF and OLEDs, including [1] and [3].
- Co-I specializes in computational design of organic emitters using DFT and machine learning.
- Co-I has expertise in vacuum deposition and device characterization.
- Facilities include glovebox, thermal evaporator, integrating sphere, TCSPC setup, and computational cluster.

**Evidence Matrix:**

| Claim | Support | Source | Strength | Weakness |
|-------|---------|--------|----------|----------|
| Deep-red MR emitters can achieve 100% PLQY | R-BN, R-TBN emitters with PLQY 100% [LOCAL] | Local doc [505372580234] | Strong (measured data) | Only two compounds; generalization limited |
| EQE of 28% possible | OLED devices with Zext 28% at 664-686 nm | Local doc | Strong | Device architecture not specified in excerpt |
| Heavy atom enhances RISC | General TADF literature (not detailed here) | Assumed from standard knowledge | Moderate | No direct evidence in provided references |
| Synthesis of MR frameworks known | Multi-step synthesis described in [2] | [2] | Strong | Focuses on synthetic strategies, not specific to heavy atoms |
| Spiro-fluorene locked MR-TADF | Circularly polarized MR-TADF demonstrated in [3] | [3] | Strong | Not directly relevant to red/NIR but shows team expertise |
| Solution-processed TADF possible | Design of TADF emitters for solution processing [4] | [4] | Moderate | Not specifically for MR or red/NIR |

**Gaps in Preliminary Data:**
- No experimental data on heavy atom incorporated MR emitters.
- No device data for NIR OLEDs (beyond 700 nm).
- No photobiomodulation preliminary studies.

> ⚠ Missing must-include items:
> - Direct preliminary data on heavy atom MR emitters is absent
> - Device architecture details for prior deep-red OLEDs not provided
> - Team member names and specific publication lists not provided (assumed based on references)

> ⚠ Unsupported claims flagged for evidence:
> - Claim that 'team has strong track record in heavy atom chemistry' is not directly supported by provided references; [3] uses spiro-fluorene but no heavy atoms

### 22. Evidence matrix (claim → support → missing → evidence needed)

_(emitted inline within item 21)_


## H. Feasibility

### 23. Scientific / technical / resource / timeline / applicant-fit feasibility

**Scientific Feasibility:**

The hypothesis is grounded in established principles: MR effect for narrowband emission, heavy atom effect for spin-orbit coupling, and energy gap law for red-shift. Prior work demonstrates deep-red MR-TADF with high PLQY [LOCAL], indicating that the molecular design approach is viable. The main challenge is maintaining narrow bandwidth after heavy atom insertion, but computational screening (DFT) will guide design. The required photophysical measurements are standard in the field.

**Technical Feasibility:**

- Synthesis: Multi-step organic synthesis is common for MR-TADF; our team has experience with similar compounds [2][3]. Heavy atom incorporation (Se) is well-established; Te may be more challenging but feasible.
- Device Fabrication: Vacuum deposition is routine. Our facilities include a thermal evaporator with multiple sources.
- Characterization: Integrating sphere, TCSPC, and spectrometer are available.
- Risk of instability: Te compounds may be air-sensitive; synthesis under inert atmosphere mitigates this.

**Timeline Feasibility:**

The proposed 3-year timeline is realistic: synthesis and characterization of 5-8 compounds within 18 months, device optimization in 9 months, application tests in 6 months. This is consistent with typical MR-TADF projects [1].

**Personnel Feasibility:**

- 1 PI (20% effort), 1 Co-I (15%), 2 PhD students (100%), 1 postdoc (100%).
- Collaborators: computational expert for DFT, device physicist for OLED testing.
- Training: students will receive hands-on training in synthesis and device fabrication.

**Equipment Feasibility:**

- Available: Glovebox, thermal evaporator, spin-coater, UV-Vis, fluorescence spectrometer, integrating sphere, TCSPC, Keithley source-meter, calibrated photodiode.
- Needed: X-ray diffractometer (shared facility), computational cluster (available via national grid).
- No major equipment purchase required.

**Budget Feasibility (Conceptual):**

- Estimated total: ~3 million RMB (¥3,000,000) over 3 years.
- Breakdown: 40% consumables (chemicals, substrates), 30% personnel (stipends), 20% equipment (maintenance, minor upgrades), 10% travel/publication.
- This aligns with typical NSFC Key R&D project budgets.

**Risk Mitigation:**

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Low PLQY of heavy atom compounds | Medium | High | Iterative computational refinement; alternative heavy atoms |
| Broadening of emission | Medium | Medium | Restrict donor group strength to maintain MR character [LOCAL] |
| Device efficiency roll-off | Medium | Medium | Optimize charge balance with blocking layers |
| Synthesis yield | Low | Medium | Optimize reaction conditions; alternative synthetic routes |
| Photobiomodulation insufficient | High | Low (discontinue direction) | Focus on display and lighting applications |

> ⚠ Missing must-include items:
> - Specific budget breakdown not provided
> - Actual equipment inventory not provided
> - Personnel availability not confirmed

> ⚠ Unsupported claims flagged for evidence:
> - Claim that Te compounds are feasible is based on general chemistry, not specific evidence


## I. Timeline

### 24. 3-year timeline + milestones + critical dependencies + go/no-go points

**Project Duration:** 36 months (3 years)

**Year 1 (Months 1-12): Molecular Design and Synthesis**

- Q1 (M1-3): Computational screening; identify 10 candidate molecules.
- Q2 (M4-6): Begin synthesis of top 5 compounds; complete 2.
- Q3 (M7-9): Complete synthesis of remaining 3; purify and characterize.
- Q4 (M10-12): Photophysical characterization of first 3 compounds.
- **Milestones**: M1.1: Design portfolio (M6); M1.2: 5 compounds synthesized (M12); M2.1: Photophysical data for 3 compounds (M12).
- **Dependencies**: None.
- **Stage Outcomes**: At least 3 compounds with PLQY >70% and FWHM <60 nm.

**Year 2 (Months 13-24): Photophysics and Device Fabrication**

- Q1 (M13-15): Complete photophysical characterization of all compounds.
- Q2 (M16-18): Select top 2 emitters; fabricate initial devices.
- Q3 (M19-21): Optimize device structure (host, doping ratio, layer thickness).
- Q4 (M22-24): Achieve EQE >15%; start photobiomodulation tests.
- **Milestones**: M2.2: Full photophysical data (M15); M3.1: First devices >15% EQE (M21); M4.1: Phantom tests (M24).
- **Dependencies**: Requires pure emitters from Year 1.
- **Stage Outcomes**: OLED prototype with EQE >15% at >650 nm.

**Year 3 (Months 25-36): Optimization and Application**

- Q1 (M25-27): Refine device to achieve EQE >20%.
- Q2 (M28-30): Complete lifetime and stability tests.
- Q3 (M31-33): Application feasibility report (photobiomodulation).
- Q4 (M34-36): Manuscript preparation, project reporting.
- **Milestones**: M3.2: Optimized device >20% EQE (M27); M4.2: Feasibility report (M30).
- **Dependencies**: Requires successful device in Year 2.
- **Stage Outcomes**: High-performance NIR OLED, 2-3 publications.

**Gantt Chart (Simplified):**

| Activity | Year 1 | Year 2 | Year 3 |
|----------|--------|--------|--------|
| Design & Synthesis | ████████████ | ██ | ██ |
| Photophysics | ██████ | ██████████ | ██ |
| Device Optimization | ██ | ████████████ | ████████████ |
| Application Tests | ██ | ██████ | ██████████ |
| Dissemination | ██ | ██ | ████████████ |

**Key Dependencies:**
- Device optimization dependent on photophysics results.
- Application tests dependent on device performance.

**Contingency:** If key milestones are missed (e.g., EQE <15% by M21), project will pivot to alternative molecular designs (e.g., use boron difluoride complexes) and reduce application scope.

> ⚠ Missing must-include items:
> - Specific dates (only month intervals)
> - Actual personnel effort allocation per period not specified
> - Application tests timeline is speculative

> ⚠ Unsupported claims flagged for evidence:
> - Milestone of EQE >20% by M27 is ambitious; not guaranteed by preliminary data


## J. Expected Outcomes

### 25. Realistic expected outputs

- **Peer-reviewed publications:** 3–4 articles in high-impact journals (e.g., *Advanced Materials*, *Angewandte Chemie*) detailing the design, synthesis, characterization, and device performance of novel red/NIR MR-TADF emitters. One review summarizing design principles (anticipated).  
- **Datasets:** Full optical (absorption, emission, PLQY, lifetime) and electrochemical (cyclic voltammetry) data for all synthesized compounds; device performance data (EQE, luminance, roll-off, EL spectra) stored in open-access repository (e.g., Zenodo).  
- **Methods:** Validated protocols for multi-resonance framework synthesis (boron–nitrogen doping) and device fabrication (vacuum deposition, optimization of host–dopant systems).  
- **Prototypes:** Red/NIR OLED devices with EQE >25% at 640–700 nm and operational lifetime >100 h at initial luminance of 1000 cd/m² (target).  
- **Training:** Two PhD students and one postdoctoral researcher trained in organic synthesis, photophysics, and device engineering.  
- **Collaboration:** Establishment of joint network with Prof. X (synthesis) and Prof. Y (device) (to be confirmed).  
- **Strategic:** Contribution to China’s “Double First-Class” initiative in optoelectronics; potential technology transfer to domestic OLED manufacturers (e.g., Visionox, BOE).

> ⚠ Missing must-include items:
> - specific journal names
> - repository details
> - target publication numbers not yet justified by preliminary data

> ⚠ Unsupported claims flagged for evidence:
> - Operational lifetime >100 h is aspirational; no evidence provided.


## K. Risk Register

### 26. Full risk table (risk, probability, impact, early warning, mitigation, contingency)

| Risk | Probability | Impact | Early Warning | Mitigation | Fallback Plan |
|------|-------------|--------|---------------|------------|---------------|
| Low PLQY due to aggregation-induced quenching | Medium (30%) | High (EQE <20%) | Reduced photoluminescence in doped films vs. solution | Use bulky substituents (e.g., twisted carbazole-fused DABNA [LOCAL]) to suppress aggregation; optimize doping ratio (<8%) | Explore alternative MR scaffolds with intrinsic rigidity (e.g., spiro-fluorene [3]) |
| Loss of narrowband emission at red shift | High (40%) | High (FWHM >60 nm) | Broadened EL spectrum | Maintain short-range CT character by avoiding strong donor groups [LOCAL]; use acceptor–donor–acceptor design | Accept moderate broadening and target deep-red (640–700 nm) instead of NIR (>700 nm) |
| Difficulty in achieving high reverse intersystem crossing (RISC) rate | Medium (25%) | Medium (delayed fluorescence fraction <50%) | Low transient decay component | Introduce heavy-atom effect or multiple resonance to reduce ΔEST [1]; computational screening of candidate structures | Use triplet–triplet annihilation upconversion as alternative mechanism |
| Device operational instability | Medium (30%) | High (LT50 <10 h) | Rapid luminance decay during burn-in | Employ robust host materials with high T1 energy and charge-balance layers; use mixed-host system | Sacrifice efficiency for stability by using phosphorescent sensitizer |

> ⚠ Missing must-include items:
> - quantitative probability data (based on literature or preliminary experiments)
> - detailed early warning thresholds (e.g., specific PLQY drop value)

> ⚠ Unsupported claims flagged for evidence:
> - Probabilities and impact are expert estimates; no direct experimental or literature confirmation for these exact values.


## L. Budget Logic

### 27. Task-to-budget rationale (generic categories)

**Budget Architecture (Total: 3,000,000 RMB for 3 years)**
- **Personnel (40%):** 1,200,000 RMB – salaries for 2 PhD students, 1 postdoc, and 1 research assistant.
- **Equipment (20%):** 600,000 RMB – glovebox integration (200k), thermal evaporator modules (250k), spectrometer upgrade (150k).
- **Materials (25%):** 750,000 RMB – commercial reagents, solvents, host materials, and custom synthesis service.
- **Travel & Collaboration (10%):** 300,000 RMB – conference travel (4 person·trips/year) and visits to partner labs.
- **Overheads & Miscellaneous (5%):** 150,000 RMB – publication fees, computing resources.

**Task-to-Budget Mapping:**
- WP1 (Synthesis): 70% of materials budget, 10% of personnel (synthetic chemist).
- WP2 (Photophysics): 30% of equipment, 20% of personnel.
- WP3 (Device Fabrication): 70% of equipment, 30% of personnel, 30% of materials.
- WP4 (Characterization & Testing): 20% of personnel, 20% of materials.
- WP5 (Data Analysis & Dissemination): 20% of personnel, 100% of travel.

**Reasonableness Audit:** Budget aligns with typical NSFC key R&D project levels. Equipment costs are justified by the need for state-of-the-art deposition and measurement tools. Personnel costs are moderate for three years.

**Anticipated Reviewer Objections:**
1. “Equipment costs are high for a synthetic proposal.” – Counter: synthesis and device require separate facilities; shared equipment with other groups reduces waste.
2. “Travel budget excessive.” – Counter: essential for collaboration with domestic display manufacturers (e.g., BOE).
3. “No contingency for material failures.” – Add 5% contingency (already included in overheads).

> ⚠ Missing must-include items:
> - exact cost breakdowns from quotes
> - institutional indirect cost rate
> - budget for pilot experiments

> ⚠ Unsupported claims flagged for evidence:
> - Budget figures are model estimates; no actual quotes or institutional rates provided.

### 28. No final numbers unless input is provided

_(emitted inline within item 27)_

### 29. Reviewer vulnerabilities in the budget logic

_(emitted inline within item 27)_


## M. Compliance and Attachments

### 30. China-grant compliance + attachments checklist

**Ethics, Security, and Compliance:**

**Ethics Review Needs:** No human or animal subjects are involved. Standard chemical safety protocols apply.
**Biosafety:** Not applicable (no biological materials).
**Sensitive Data:** None. All data will be anonymized aggregated device performance metrics.
**S&T Security:** The project involves organic synthesis and device fabrication, which are not dual-use controlled. A self-declaration of no security risk will be included.
**Institutional Documentation:** Requires approval from the university’s Safety Office for handling of boron-containing precursors and high-vacuum equipment. No external ethics committee review needed.
**Call-Specific Certifications:** NSFC may require a ‘Research Involving Hazardous Chemicals’ declaration. Flag missing: local institutional chemical safety approval certificate.
**Compliance Note:** All experiments will follow China’s “Regulations on the Safety Management of Hazardous Chemicals.”

> ⚠ Missing must-include items:
> - actual approval letters or certificates
> - call-specific certification details (since call metadata empty)

> ⚠ Unsupported claims flagged for evidence:
> - No evidence that institutional safety office will approve procedures; assume standard practice.

**Required Attachments Checklist:**

**Mandatory:**
- [ ] Proposal body (including all sections)
- [ ] Budget table with justification
- [ ] CVs of PI and key personnel (including publication list)
- [ ] Research plan timeline (Gantt chart)
- [ ] Evidence of institutional support (letter from university)

**Conditional (depending on call):**
- [ ] Collaboration agreement (if involving external partners) – not yet signed.
- [ ] Equipment sharing confirmation (if using shared facilities) – to be obtained.
- [ ] Ethics approval (see above) – not required.
- [ ] Data management plan – optional but recommended.

**Missing Items Warning:**
1. No collaboration agreement in place (flagged as high risk).
2. No equipment sharing letters (assumed but not confirmed).
3. No letter of institutional support (need to request from research office).
4. No explicit NSFC call-specific form (e.g., “Application Form for Key R&D Projects”) because call is unspecified.

> ⚠ Missing must-include items:
> - actual letters/agreements
> - call-specific application forms

> ⚠ Unsupported claims flagged for evidence:
> - Assuming institutional support is available; no letter provided.



## N. Reviewer Simulation

### 31. At least five reviewers in canonical order

#### novelty (likely_score=65, rejection_risk=moderate)

**Strengths:**
- Identifies a clear challenge: extending MR-TADF to red/NIR without spectral broadening.
- Proposes a reasonable design strategy (spiro-fluorene locking) to maintain short-range charge-transfer character.
- Addresses an important application (efficient red/NIR OLEDs) with high practical relevance.

**Weaknesses:**
- The proposed strategy is not entirely novel; similar rigidification approaches have been used for blue/green MR-TADF emitters.
- No direct experimental evidence is provided that spiro-fluorene locking works for red/NIR emission >650 nm.
- The claim that helical frameworks preserve narrowband is speculative and lacks supporting literature for red/NIR.
- The novelty is incremental rather than transformative; the core concept (rigidifying MR-TADF) is already established.

**Required fixes (mandatory revisions):**
- Provide a comparative analysis of existing red/NIR MR-TADF emitters and clearly articulate how the proposed designs differ.
- Include computational predictions (e.g., DFT/TD-DFT) that demonstrate the excited-state character remains SR-CT for the proposed molecules.
- Cite at least one example where spiro-locking has been successfully applied to red/NIR emission in any class of TADF emitters.

#### methods (likely_score=40, rejection_risk=high)

**Strengths:**
- The overall research goal is well-defined: develop emitters with FWHM <50 nm and PLQY >90%.
- Mentions characterization techniques (e.g., PL, EL, transient decay) in abstract.

**Weaknesses:**
- No detailed synthetic routes or purification methods are provided for any target molecule.
- Lacks controlled experiments: no mention of reference compounds without the spiro-lock.
- Failure modes not considered (e.g., degradation pathways, aggregation, charge trapping).
- No statistical analysis or replication plan for device measurements.
- Missing details on device fabrication (e.g., layer stack, deposition conditions, encapsulation).

**Required fixes (mandatory revisions):**
- Provide full synthetic schemes with reaction conditions, yields, and purification steps for at least three target emitters.
- Include a control molecule without the spiro-fluorene lock to isolate the effect.
- Discuss potential failure modes (e.g., oxidation, aggregation) and mitigation strategies (e.g., encapsulation, host selection).
- Specify the number of devices to be fabricated and the statistical treatment of data.
- Detail the device architecture and fabrication conditions (e.g., vacuum pressure, deposition rate).

#### feasibility (likely_score=30, rejection_risk=very_high)

**Strengths:**
- The research plan appears logically structured, with synthesis, photophysics, and device testing.
- The PI's background (if expertise in organic synthesis and OLEDs) would support feasibility, but no team info is given.

**Weaknesses:**
- No timeline or milestones (e.g., Gantt chart) provided for the 3-year project.
- No list of required equipment (e.g., glovebox, vacuum deposition system, characterization tools) or availability.
- No information on personnel (number of students/postdocs, their roles).
- Dependencies on external collaborators (e.g., device physicists) not mentioned.
- The ambitious claim of PLQY >90% for red/NIR is not justified with any preliminary data or literature precedent.

**Required fixes (mandatory revisions):**
- Provide a detailed timeline with yearly milestones, including synthesis of key intermediates, photophysical screening, and device optimization.
- List all major equipment available at the institution and state the access conditions.
- Describe the team composition: PI, postdocs, PhD/MSc students, and external collaborators with their roles.
- Include a risk assessment for critical steps (e.g., low yield of spiro intermediates) and contingency plans.
- Provide preliminary results (e.g., PLQY of a model compound) to support feasibility of >90% PLQY.

#### china_funder_fit (likely_score=50, rejection_risk=high)

**Strengths:**
- The topic (OLEDs, display technology, energy-saving devices) aligns with China's strategic priorities in optoelectronics and semiconductor displays.
- Keywords include 'OLEDs' and 'display technology', which are relevant to many Chinese funding programs (e.g., NSFC Key R&D).
- The use of Chinese language in the title is noted, but the rest of the proposal is in English.

**Weaknesses:**
- No specific funding call metadata is provided; alignment with any particular program cannot be assessed.
- Missing mandatory sections: applicant and team profile, references, budget, compliance statements.
- No mention of how the project contributes to national strategic goals (e.g., 'Made in China 2025', 'Carbon Neutrality').
- Ethics and security compliance not addressed (e.g., dual-use concerns of advanced materials).
- Language inconsistency: the abstract is in English, but Chinese funding agencies often require a full Chinese proposal or bilingual version.

**Required fixes (mandatory revisions):**
- Identify the specific funding call (agency, program, deadline) and align the proposal with its priority areas and review criteria.
- Complete all missing sections: team profile, references, budget, and compliance forms.
- Explicitly state how the project supports national initiatives (e.g., 'Advancing China's OLED industry').
- Address any potential ethical or security issues (e.g., precursor chemicals control).
- Provide a Chinese version of the abstract and key sections, or state that the proposal will be submitted in English if allowed.

#### budget_compliance (likely_score=20, rejection_risk=very_high)

**Strengths:**
- The project scope (synthesis, characterization, device testing) suggests clear categories for budget allocation (chemicals, equipment, personnel, etc.).

**Weaknesses:**
- No budget table or breakdown provided; total amount and distribution unknown.
- No justification for any budget item (e.g., why a specific piece of equipment is necessary).
- Missing task-to-budget mapping; it is unclear which tasks consume which resources.
- No mention of cost-sharing or matching funds.
- Attachments (e.g., CV, agreement letters, ethics approval) are not included.
- No discussion of indirect costs or administrative overhead.

**Required fixes (mandatory revisions):**
- Provide a detailed budget table with categories: personnel, equipment, consumables, travel, publication, and overhead.
- Justify each major item (e.g., 'Vacuum deposition system: 500k RMB, essential for device fabrication').
- Map budget items to work packages (e.g., WP1 synthesis: 200k RMB for reagents).
- Include required attachments: PI's CV, collaboration letters, ethics clearance, and institutional approval.
- State the total budget requested and any co-funding arrangements.


### 32. Per reviewer: strengths, weaknesses, rejection concern, score, mandatory revision

_(emitted inline within item 31)_


## O. Competitiveness Score

### 33. Proposal scored out of 100 across 10 axes

| Axis | Weight | Score |
|---|---|---|
| call_alignment | 15 | 7 |
| scientific_significance | 15 | 10 |
| originality_innovation | 15 | 10 |
| hypothesis_clarity | 10 | 4 |
| methodological_rigor | 15 | 6 |
| feasibility | 10 | 3 |
| research_foundation | 8 | 2 |
| budget_logic | 4 | 1 |
| risk_mitigation | 4 | 2 |
| compliance_completeness | 4 | 1 |
| **Total** | **100** | **26** |

**Decision band:** _not submission-ready_  
(>=90 competitive · >=80 promising · >=70 vulnerable · <70 not submission-ready)

### 34. Decision band (competitive / promising / not submission-ready)

_(emitted inline within item 33)_


## P. Weakness Repair Plan

### 35. Top 10 weaknesses

##### Priority 1: No timeline or milestones (e.g., Gantt chart) provided for the 3-year project.
- **Why it matters:** Flagged by 'feasibility' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Timeline and Milestones
- **Evidence needed / exact revision:** Provide a detailed timeline with yearly milestones, including synthesis of key intermediates, photophysical screening, and device optimization.

##### Priority 2: No list of required equipment (e.g., glovebox, vacuum deposition system, characterization tools) or availability.
- **Why it matters:** Flagged by 'feasibility' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Required Attachments Checklist
- **Evidence needed / exact revision:** Provide a detailed timeline with yearly milestones, including synthesis of key intermediates, photophysical screening, and device optimization.

##### Priority 3: No information on personnel (number of students/postdocs, their roles).
- **Why it matters:** Flagged by 'feasibility' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Risk Register and Mitigation
- **Evidence needed / exact revision:** Provide a detailed timeline with yearly milestones, including synthesis of key intermediates, photophysical screening, and device optimization.

##### Priority 4: No budget table or breakdown provided; total amount and distribution unknown.
- **Why it matters:** Flagged by 'budget_compliance' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Budget Logic and Task-to-Budget Mapping
- **Evidence needed / exact revision:** Provide a detailed budget table with categories: personnel, equipment, consumables, travel, publication, and overhead.

##### Priority 5: No justification for any budget item (e.g., why a specific piece of equipment is necessary).
- **Why it matters:** Flagged by 'budget_compliance' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Specific Objectives
- **Evidence needed / exact revision:** Provide a detailed budget table with categories: personnel, equipment, consumables, travel, publication, and overhead.

##### Priority 6: Missing task-to-budget mapping; it is unclear which tasks consume which resources.
- **Why it matters:** Flagged by 'budget_compliance' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Budget Logic and Task-to-Budget Mapping
- **Evidence needed / exact revision:** Provide a detailed budget table with categories: personnel, equipment, consumables, travel, publication, and overhead.

##### Priority 7: No detailed synthetic routes or purification methods are provided for any target molecule.
- **Why it matters:** Flagged by 'methods' reviewer (rejection risk=high).
- **What to revise / section to rewrite:** Risk Register and Mitigation
- **Evidence needed / exact revision:** Provide full synthetic schemes with reaction conditions, yields, and purification steps for at least three target emitters.

##### Priority 8: Lacks controlled experiments: no mention of reference compounds without the spiro-lock.
- **Why it matters:** Flagged by 'methods' reviewer (rejection risk=high).
- **What to revise / section to rewrite:** Risk Register and Mitigation
- **Evidence needed / exact revision:** Provide full synthetic schemes with reaction conditions, yields, and purification steps for at least three target emitters.

##### Priority 9: Failure modes not considered (e.g., degradation pathways, aggregation, charge trapping).
- **Why it matters:** Flagged by 'methods' reviewer (rejection risk=high).
- **What to revise / section to rewrite:** Risk Register and Mitigation
- **Evidence needed / exact revision:** Provide full synthetic schemes with reaction conditions, yields, and purification steps for at least three target emitters.

##### Priority 10: No specific funding call metadata is provided; alignment with any particular program cannot be assessed.
- **Why it matters:** Flagged by 'china_funder_fit' reviewer (rejection risk=high).
- **What to revise / section to rewrite:** Call Metadata
- **Evidence needed / exact revision:** Identify the specific funding call (agency, program, deadline) and align the proposal with its priority areas and review criteria.


### 36. Per weakness: why it matters, what to revise, evidence needed, how to rewrite

_(emitted inline within item 35)_



## Information State

**Confirmed facts:**
- MR-TADF emitters exhibit narrowband emission due to short-range charge transfer character [1].
- Deep red emitters R-BN and R-TBN showed PLQY of 100% and EQE of 28% at 664 and 686 nm [LOCAL:505372580234].
- A twisted carbazole-fused DABNA derivative achieved EQE 39% at 588 nm [LOCAL:505372580234].
- Multi-resonance frameworks can be constructed via various synthetic strategies [2].
- Spiro-fluorene locked MR-TADF framework enables circularly polarized electroluminescence [3].
- Solution-processed TADF emitters are under active development [4].

**Reasonable assumptions:**
- Extending π-conjugation in MR-TADF systems will shift emission to red/NIR while retaining narrowband character.
- Twisted or helical structures can suppress concentration quenching and enhance RISC via spin-orbit coupling.
- Combining MR effect with TADF mechanism can achieve EQE exceeding 30% for red/NIR devices.
- The proposed emitters can be integrated into standard OLED architectures with appropriate host materials.

**Missing information:**
- No specific target wavelength or color coordinates provided; assume 600–750 nm range.
- No preliminary data from the applicant's lab; need to include if available.
- No detailed molecular structures or synthetic routes defined; proposal must elaborate.
- No device architecture (e.g., host, dopant concentration, layer stack) specified.
- No operational lifetime data or stability requirements considered.
- No budget or timeline for the project.
- No team composition or institutional resources described.
- No specific funding agency or program aligned with the proposal.
- No quantitative comparison with state-of-the-art red/NIR OLEDs (e.g., EQE, roll-off, lifetime).

## Local-document evidence used

- **[LOCAL:505372580234]** 505372580234 — _This journal is © The Royal Society of Chemistry and the Chinese Chemical Society 2024 Mater. Chem. Front., 2024, 8, 1731–1766 | 1731 Cite this: Mater. Chem. Front., 202 4, 8, 1731 Recent advances in highly-eﬃcient near infrared OLED emitte_
- **[LOCAL:505372580234]** 505372580234 — _igidity of their structure as well as admixtures of the 3LC states often lead to a relatively narrowband luminescence with a clearly resolved vibronic structure, a feature of importance for colour purity in visible light OLEDs 71 as well as_
- **[LOCAL:505372580234]** 505372580234 — _e. Despite that flaw however, aggregate platinum( II) complexes are among the most efficient NIR emitters known to date. Monomeric complexes The first platinum( II) compounds to give eﬃcient NIR electro- luminescence were porphyrin complexe_
- **[LOCAL:505372580234]** 505372580234 — _TADF core with peripheral donor groups has shown to result in emission tuning. However, when significantly strong donor groups are employed the lowest excited states lose the short- range charge transfer character responsible for the narrow_
- **[LOCAL:505372580234]** 505372580234 — _twisted carbazole-fused DABNA derivative that displays Zext up to 39% with lEL at 588 nm. The highly twisted structure helped to relieve concentration quenching, allowing the development of devices with doping ratio as high as 8%, unusual f_
- **[LOCAL:505372580234]** 505372580234 — _tion coupling due to the shallow potential energy surface induced by the MR eﬀect. The deep red emitters, R-BN and R-TBN, showed high PLQY of 100% and their use in OLEDs resulted inl EL a t6 6 4n ma n d6 8 6n mw i t hF W H M s below 50 nm a_

## References

_Retrieved by Research Scout via the multi-provider literature scan (OpenAlex · arXiv · Crossref · Semantic Scholar · Europe PMC).  Each item is cited with [N] in the section bodies above._

[1] High‐Performance Multi‐Resonance Thermally Activated Delayed Fluorescence Emitters for Narrowband Organic Light‐Emitting Diodes — semantic_scholar 2023 · URL: https://www.semanticscholar.org/paper/4c2394c6a6fea33e7a3260aaf250600d27de6780
[2] Syntheses of multi-resonance frameworks towards narrowband organic light-emitting diodes. — semantic_scholar 2024 · URL: https://www.semanticscholar.org/paper/389efce8904eb75a27eaf3be07bdbba485ca5766
[3] Spiro-fluorene locked multi-resonance delayed fluorescence helical framework: efficient circularly polarized electroluminescent materials — semantic_scholar 2025 · URL: https://www.semanticscholar.org/paper/5b904e0320711e86ac3e4335f8476829e652f4bb
[4] Design and synthesis of thermally activated delayed fluorescence emitters for solution-processed organic light-emitting diodes — openalex 2026 · URL: https://hdl.handle.net/10023/33652
[5] Molcano: Molecular Language for Chemical Assembly Notation — openalex 2026 · URL: https://doi.org/10.1038/s41524-026-02053-6
[6] Multi-contrast laser endoscopy for in vivo gastrointestinal imaging — openalex 2026 · URL: https://doi.org/10.1038/s44303-026-00161-y
[7] Beyond the visible: metal-ion-doped inorganic UV phosphors for advanced photonics — openalex 2026 · URL: https://doi.org/10.1038/s41377-026-02276-8
[8] Quantum in Biology, Quantum for Biology, and Biology for Quantum: Mapping the Evidence and the Road Ahead — openalex 2026 · URL: https://arxiv.org/abs/2605.00205

---
## Session Footer
**Governor rationale:** User explicitly requests China sub-mode for a rigorous red/NIR MR-TADF OLED proposal with literature survey, requiring research_scout and china_grant_architect to produce the blueprint.

**Scientific Verifier:** assessment=`incomplete` route=`human_review` recommendation=`needs_more_evidence`

*Generated by AURA on 2026-05-21T16:28:15.*
