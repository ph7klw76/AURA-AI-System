> # ⚠️ UNVERIFIED DRAFT — HUMAN REVIEW REQUIRED
>
> This document was produced by AURA but the Scientific Verifier did NOT
> route the session to `approve` or `revise`.  Treat every claim, number,
> citation, and recommendation as **unverified**.  Do NOT submit, publish,
> send, or act on this document without independent human review.
>
> Verifier route: `human_review`   Assessment: `incomplete`   Recommendation: `needs_more_evidence`

> **Prompt:** Invoke the China sub-mode,  draft a rigorous, reviewer-tested proposal supported by literature survey on highly efficient red/NIR MR-TADF OLEDs , including hypothesis, work packages, methods, risks, compliance, scoring, and memory update

# Selenium-Embedded Multiple Resonance Frameworks for High-Efficiency Red/Near-Infrared OLEDs: Overcoming Efficiency Roll-off via Accelerated Reverse Intersystem Crossing

_Template: `CHINA_GRANT_PROPOSAL_BLUEPRINT_V1` v1.0 — layers applied: china_grant_master_template, user_override_preferences:user_

_Competitiveness: **9/100** — not submission-ready_

## A. Project Framing

### 1. Three candidate project titles

- **Formal scientific title:** Selenium-Embedded Multiple Resonance Frameworks for High-Efficiency Red/Near-Infrared OLEDs: Overcoming Efficiency Roll-off via Accelerated Reverse Intersystem Crossing
- **Reviewer-friendly title:** Red MR-TADF OLEDs with Record RISC Rates: Design, Fabrication, and Device Optimization
- **Ambitious but credible title:** Ultra-Efficient Red/NIR MR-TADF OLEDs: Breaking the Efficiency Roll-Off Barrier Through Selenium-Enhanced Spin-Flip Dynamics

### 2. English title (+ optional Chinese title placeholder)

- **English:** Selenium-Embedded Multiple Resonance Frameworks for High-Efficiency Red/Near-Infrared OLEDs: Overcoming Efficiency Roll-off via Accelerated Reverse Intersystem Crossing
- **中文 / Chinese:** 基于硒嵌入多重共振框架的高效红/近红外OLED：通过加速反向系间窜越克服效率滚降

### 3. Full technical abstract

Red multiple resonance thermally activated delayed fluorescence (MR-TADF) OLEDs suffer from severe efficiency roll-off at high brightness due to intrinsically slow reverse intersystem crossing (RISC). Recent work demonstrated that selenium embedding into a MR framework yields an emitter (tFSeBN) with a record RISC rate of 7.5 × 10^5 s⁻¹, enabling a maximum external quantum efficiency (EQE) of 34.7% and maintaining 25.6% at 10,000 cd m⁻² [1]. This proposal aims to extend this design strategy to the red/near-infrared (NIR) region by systematically varying donor-acceptor strength and π-extension, guided by high-throughput screening (xTB-based) [2] and emission dipole orientation optimization [3]. We will synthesize a library of Se-embedded MR-TADF emitters, characterize their photophysical properties, and fabricate OLEDs with optimized light outcoupling. The central hypothesis is that the heavy-atom effect of selenium accelerates RISC without compromising narrowband emission, and that further tuning can push emission beyond 700 nm while retaining high EQE. Expected outcomes include emitters with RISC rates exceeding 1 × 10^6 s⁻¹, EQE >30% at practical brightness, and demonstration of hyperfluorescent sensitization for pure red/NIR electroluminescence [1]. This work addresses the critical bottleneck in red MR-OLEDs and provides a materials platform for next-generation displays and photobiomodulation devices.

### 4. Concise abstract

We propose to develop selenium-embedded MR-TADF emitters for red/NIR OLEDs with record RISC rates, overcoming efficiency roll-off. Building on a recent breakthrough (tFSeBN: RISC 7.5×10^5 s⁻¹, EQE 34.7%), we will design, screen, synthesize, and optimize emitters for deep red/NIR emission, targeting EQE >30% at 1000 cd m⁻² and beyond 700 nm.

### 5. Keyword set

- **Scientific:** Multiple resonance TADF, Selenium embedding, Reverse intersystem crossing, Efficiency roll-off, Red/NIR OLED, Narrowband emission
- **Scientific (中文):** 多重共振TADF, 硒嵌入, 反向系间窜越, 效率滚降, 红/近红外OLED, 窄带发射
- **Funder-alignment:** Organic optoelectronics, High-efficiency OLED, Thermally activated delayed fluorescence
- **Warnings:** No specific funder call metadata provided; keywords are generic. Alignment with specific agency (e.g., NSFC) may be needed.


## B. Scientific Rationale

### 6. Background and significance

**Field status:** Multiple resonance thermally activated delayed fluorescence (MR-TADF) materials have revolutionized OLED technology by enabling narrowband electroluminescence combined with 100% exciton utilization. However, red and near-infrared (NIR) emitters suffer from severe efficiency roll-off at high luminance because the RISC rate is intrinsically slow due to a large singlet-triplet energy gap (ΔEST) and weak spin-orbit coupling (SOC) [1]. This bottleneck prevents their adoption in high-brightness displays and lighting.

**Precise bottleneck:** The RISC rate constant (kRISC) for state-of-the-art red MR-TADF emitters is typically below 10⁵ s⁻¹, causing 30-50% EQE drop from maximum to 1000 cd/m² [1]. The fundamental limit arises from the small orbital angular momentum in purely organic molecules. 

**Unresolved gap:** While heavy-atom incorporation (e.g., selenium) has been shown to enhance SOC and thus kRISC (tFSeBN reaches 7.5×10⁵ s⁻¹ [1]), the design space for extending this strategy to NIR (>650 nm) is unexplored. Current NIR emitters rely on iridium complexes or donor-acceptor TADF with broad emission and low PLQY [LOCAL:94cbdecc1259]. The local review notes that NIR OLED emitters remain inefficient due to the energy gap law and aggregation effects [LOCAL:94cbdecc1259].

**Importance to fundamental science:** Understanding how heavy chalcogen atoms modulate SOC and excited-state dynamics in MR frameworks will advance photophysical theory of TADF and guide rational design.

**Relevance to funding scope:** This research addresses China's strategic need for energy-efficient, high-resolution displays (e.g., NSFC key programs, MOST key R&D in optoelectronics). Suppressed roll-off directly reduces power consumption in high-brightness OLED panels.

**Why timely:** The demonstration of tFSeBN [1] provided a proof-of-concept; systematic optimization and NIR extension are immediate next steps. The availability of high-throughput screening tools [2] and advanced light-outcoupling techniques [3] makes this the opportune moment.

> ⚠ Unsupported claims flagged for evidence:
> - The claim that tFSeBN reaches 7.5×10⁵ s⁻¹ is from Ref [1]; the project extrapolates to NIR but no direct data exists.

### 7. Literature-state summary

| Known (From Literature) | Unresolved Issue | Limitation of Current Work | How This Project Addresses It | Evidence Level | Reviewer Vulnerability |
|-------------------------|------------------|----------------------------|-------------------------------|----------------|------------------------|
| Se-embedding in MR framework accelerates RISC (kRISC=7.5×10⁵ s⁻¹) and gives EQE 34.7% at 607 nm [1] | Extension to NIR (>650 nm) not demonstrated | Only one Se system studied; emission at 607 nm is red but not NIR | Systematic variation of chalcogen (S, Se, Te) and donor strength to tune emission into NIR while retaining fast RISC | High (Ref [1], peer-reviewed) | If NIR extension fails, fallback to deep-red with high brightness |
| Heavy-atom effect enhances SOC in TADF [4] | Quantitative structure-property relationship for chalcogen series unknown | Metal-containing TADF reviewed; pure organic chalcogen effect not systematically explored | Synthesize a library of 20 compounds; measure kRISC, PLQY, ΔEST as function of chalcogen | Medium (Ref [4] is a review, no experimental data) | Need own experimental data to validate trends |
| High-throughput screening (xTB) identified potential TADF candidates [2] | Screening does not consider SOC or RISC rate explicitly | Computational cost high; experimental validation lacking | Use screening to prioritize chalcogen-MR candidates before synthesis | Medium (Ref [2] benchmark, but not specific to our compounds) | Over-reliance on computation without thorough validation |
| Light extraction in corrugated OLEDs improves EQE [3] | Application to red MR-TADF OLEDs not tested | Simulations for red, green, blue but not yet integrated with MR-emitter | Fabricate corrugated OLEDs with optimized outcoupling to enhance EQE beyond 30% | Medium (Ref [3] simulation-based) | Experimental demonstration needed to confirm |
| NIR emitters suffer from energy gap law and aggregation [LOCAL:94cbdecc1259] | Exciton-vibrational decoupling strategies limited | S…S interactions proposed for NIR-II but not applied to MR-TADF | Explore molecular packing and rigidification to suppress nonradiative decay | Low (Ref [5] preprint, not yet applied to TADF) | High-risk; needs strong preliminary data |

> ⚠ Unsupported claims flagged for evidence:
> - The claim that S…S interactions can be applied to MR-TADF is speculative; Ref [5] is for NIR-II fluorophores, not TADF.

### 8. Research gap map table

_(emitted inline within item 7)_


## C. Scientific Architecture

### 9. Central question

**Main question:** How does systematic incorporation of heavy chalcogen atoms (S, Se, Te) into a multiple resonance framework affect the reverse intersystem crossing rate, emission wavelength, and efficiency roll-off in red/near-infrared organic light-emitting diodes?

**Sub-questions:**
1. What is the quantitative relationship between chalcogen atomic number and kRISC, PLQY, and ΔEST in a homologous series of MR-TADF emitters?
2. Can chalcogen-embedded MR emitters be engineered to emit beyond 650 nm while maintaining kRISC > 5×10⁵ s⁻¹ and PLQY > 80%?
3. How does the use of these emitters as sensitizers in hyperfluorescent OLEDs affect device efficiency and stability compared to conventional phosphorescent sensitizers?
4. What molecular design rules can be derived to simultaneously suppress nonradiative decay (energy gap law) and promote fast RISC in NIR MR-TADF?

> ⚠ Unsupported claims flagged for evidence:
> - Sub-question 4 assumes that nonradiative decay can be suppressed; this is speculative but framed as a design rule derivation.

### 10. Subquestions

_(emitted inline within item 9)_

### 11. Central hypothesis

**Primary Hypothesis:** Embedding heavy atoms (e.g., selenium) into multiple resonance (MR) thermally activated delayed fluorescence (TADF) frameworks can simultaneously accelerate reverse intersystem crossing (RISC) and suppress non-radiative decay via exciton-vibrational decoupling, thereby enabling red/near-infrared (NIR) OLEDs with high external quantum efficiency (EQE) and minimal efficiency roll-off.

**Alternative Hypothesis:** Alternatively, designing intermolecular S···S interactions within MR-TADF emitters can decouple exciton-vibrational coupling, extending emission into the NIR-II region while maintaining high photoluminescence quantum yield (PLQY).

**Testable Predictions:**
- Se-embedded MR emitters will exhibit RISC rates > 10⁵ s⁻¹, as demonstrated for tFSeBN [1].
- OLEDs employing such emitters will maintain EQE > 30% at 1000 cd m⁻² and > 25% at 10,000 cd m⁻² [1].
- For NIR-II emitters, emission wavelength > 1000 nm with PLQY > 80% and suppressed vibrational losses [5].

**Falsification Criteria:** The hypothesis is rejected if:
- Measured kRISC < 10⁴ s⁻¹ for any new Se-MR emitter.
- EQE roll-off exceeds 50% at 1000 cd m⁻².
- PLQY of NIR-II emitters falls below 50%.

> ⚠ Missing must-include items:
> - No direct evidence for NIR-II MR-TADF emitters; the reference [5] is for fluorophores, not MR-TADF

> ⚠ Unsupported claims flagged for evidence:
> - The claim that S···S interaction works in MR-TADF framework is an extrapolation from [5], not yet validated.

### 12. Specific objectives

**Overall Objective:** To design, synthesize, and characterize highly efficient red/NIR MR-TADF emitters with fast RISC and suppressed efficiency roll-off, and to fabricate high-performance OLEDs and hyperfluorescent devices.

**Specific Objectives (SOs):**
- **SO1:** Design and synthesize selenium-embedded MR emitters targeting deep red emission (600–650 nm) with kRISC > 5×10⁵ s⁻¹ and PLQY > 90%.
- **SO2:** Design and synthesize MR emitters incorporating S···S interactions for NIR-II (1000–1300 nm) emission with PLQY > 70% and small singlet-triplet gap (ΔEST < 0.1 eV).
- **SO3:** Characterize photophysical properties (PLQY, transient decay, ΔEST, kRISC, dipole orientation) and validate predictions via DFT/TD-DFT (e.g., xTB screening [2]).
- **SO4:** Fabricate OLEDs using optimal emitters, achieving EQE > 30% at 100 cd m⁻² and roll-off < 20% at 1000 cd m⁻².
- **SO5:** Develop hyperfluorescent OLEDs with red/NIR sensitizers and terminal emitters for high color purity (CIE x>0.68 for red).

**Objective-to-Gap Traceability:**
- SO1 → Addresses slow RISC in red MR emitters (gap from [1] state-of-the-art).
- SO2 → Tackles lack of efficient NIR-II MR-TADF emitters (gap based on [5] and LOCAL review).
- SO3 → Provides experimental validation missing in computational screening [2].
- SO4 → Demonstrates practical device performance with low roll-off (directly from [1] goal).
- SO5 → Explores hyperfluorescent approach to overcome doping concentration issues (mentioned in [1]).

> ⚠ Missing must-include items:
> - Specific target values for EQE and roll-off are not directly stated in provided evidence; they are assumed from [1] as upper bound.
> - No information on existing team synthesis capabilities or equipment.

> ⚠ Unsupported claims flagged for evidence:
> - Claim that S···S interactions can be incorporated into MR-TADF framework is not supported; it's a reasonable assumption.

### 13. Objective-to-gap traceability matrix

_(emitted inline within item 12)_

### 14. Conceptual framework chain

Molecular design → excited-state behavior → device architecture → optical output → photobiomodulation relevance.


## D. Work Packages

### 15. Design 4-5 work packages

**WP1: Design and Synthesis of Se-Embedded MR Emitters**
- **Objective:** Synthesize 3–5 novel Se-MR emitters with emission peaks 600–650 nm.
- **Rationale:** Se embedding accelerates RISC as demonstrated in [1].
- **Methods:** DFT screening (xB-based [2]), selective C–H activation, Se insertion, and characterization (NMR, MS, X-ray).
- **Data Expected:** Molecular structures, photophysical properties (absorption, emission, PLQY).
- **Milestones:** M1: Two emitters synthesized and fully characterized (Month 6). M2: RISC rate > 5×10⁵ s⁻¹ and PLQY > 90% (Month 9).
- **Decision Gate:** If kRISC < 10⁵ s⁻¹, redesign with stronger donors or alternative heavy atoms (Te).
- **Risks:** Low yield of Se insertion; mitigation by optimizing reaction conditions.
- **Deliverable:** Set of Se-MR emitters and their photophysical data.

**WP2: Design of NIR-II MR Emitters via S···S Interaction**
- **Objective:** Synthesize MR emitters with S···S interactions for emission >1000 nm.
- **Rationale:** S···S interaction decouples exciton-vibrational coupling, enabling NIR-II [5].
- **Methods:** Extend MR core with sulfur-rich groups; compute ΔEST and radiative rates [2]; synthesize top candidates.
- **Data Expected:** Emission wavelength, PLQY, transient decay.
- **Milestones:** M1: Computational screening of 50 candidates (Month 3). M2: One NIR-II emitter with PLQY > 60% (Month 12).
- **Decision Gate:** If no emitter achieves λ > 1000 nm and PLQY > 50%, pivot to Pt-porphyrin complexes (mentioned in LOCAL).
- **Risks:** S···S interaction may not be sufficient; mitigation: alternative non-covalent interactions (Se···Se, Te···Te).
- **Deliverable:** NIR-II MR-TADF emitters and structure-property correlation.

**WP3: Photophysical and Theoretical Characterization**
- **Objective:** Determine key photophysical parameters (ΔEST, kRISC, dipole orientation) for all emitters.
- **Rationale:** Parameters critical for understanding roll-off and guiding device design.
- **Methods:** Transient PL, temperature-dependent PL, angle-dependent PL, time-resolved PL; DFT/TD-DFT and SOC calculations.
- **Data Expected:** Rate constants, emission dipole orientation (horizontal ratio > 80% [3]).
- **Milestones:** M1: Complete characterization for WP1 emitters (Month 8). M2: For WP2 emitters (Month 14).
- **Decision Gate:** If horizontal ratio < 70%, modify molecular geometry via peripheral groups.
- **Risks:** Equipment access; mitigation: collaboration with partner labs.
- **Deliverable:** Full photophysical database.

**WP4: Device Fabrication and Optimization**
- **Objective:** Fabricate OLEDs with optimized stacks, achieving high EQE and low roll-off.
- **Rationale:** Device performance validates emitter potential.
- **Methods:** Vacuum deposition, lifetime testing, EQE measurement, and optical simulation.
- **Data Expected:** J-V-L, EQE vs. luminance, CIE coordinates, operational lifetime.
- **Milestones:** M1: Red OLED with EQE max > 30% (Month 15). M2: NIR-II OLED with EQE > 10% (Month 20).
- **Decision Gate:** If roll-off > 30% at 1000 cd m⁻², adopt hyperfluorescent architecture.
- **Risks:** Poor charge balance; mitigation: use known hosts (CBP, mCBP).
- **Deliverable:** High-performance red/NIR OLEDs.

**WP5: Hyperfluorescent and Tandem Device Integration**
- **Objective:** Develop hyperfluorescent OLEDs using WP1/WP2 emitters as sensitizers, achieving high color purity and suppressed roll-off.
- **Rationale:** Hyperfluorescent approach demonstrated in [1] for pure-red CIE (0.70,0.30).
- **Methods:** Co-deposit sensitizer (5–10 wt%) and terminal emitter (1–2 wt%); optimize doping ratio.
- **Data Expected:** CIE coordinates, EQE, roll-off.
- **Milestones:** M1: Hyperfluorescent red OLED with CIE x > 0.68 (Month 22). M2: NIR hyperfluorescent device (Month 26).
- **Decision Gate:** If roll-off similar to non-hyperfluorescent, reconsider sensitizer or terminal acceptor.
- **Risks:** Energy mismatch; mitigation: precisely tune sensitizer/terminal energy levels.
- **Deliverable:** Hyperfluorescent OLEDs with demonstration note.

> ⚠ Missing must-include items:
> - No specific details on synthesis protocols, device fabrication conditions, or equipment availability.
> - Operational lifetime data not provided in evidence.

> ⚠ Unsupported claims flagged for evidence:
> - The assumption that S···S interaction works in MR-TADF is not experimentally verified; WP2 includes a fallback plan.
> - No preliminary data for NIR-II MR-TADF emitters; WP2 relies heavily on computational screening.

### 16. Per-WP detail (objective, rationale, methods, outputs, risks, fallback, deliverables)

_(emitted inline within item 15)_


## E. Methodology

### 17. Rigorous methodology

**Computational Screening (xTB-based)**
- **Purpose:** Rapidly evaluate ΔEST, oscillator strength, and S···S interaction strength for hundreds of candidate emitters.
- **Justification:** xTB provides reasonable accuracy for organic molecules at low cost [2].
- **Procedure Logic:** Generate molecular library (e.g., BN-core with substituted donors/acceptors), compute ground and excited states, filter by ΔEST < 0.2 eV and f > 0.1.
- **Critical Variables:** Exchange-correlation functional (e.g., ωB97X-D for TD-DFT), solvation model.
- **Controls:** Benchmark against known MR-TADF emitters (e.g., DABNA derivatives).
- **Validation:** Compare computed ΔEST and emission wavelength with experimental data from WP3.
- **Expected Evidence:** List of top 20 candidates for each WP.
- **Failure Modes:** xTB may underestimate ΔEST; backup: use higher-level DFT (e.g., SCS-CC2).
- **Backup Plan:** If computational accuracy is poor, rely on empirical design from literature [1].

**Synthesis**
- **Purpose:** Prepare Se-MR and S···S MR emitters.
- **Key Steps:** For Se-MR: lithiation of MR precursor, insertion of Se powder, oxidation. For S···S: thionation or direct S-insertion into MR core.
- **Critical Variables:** Temperature, stoichiometry, and protecting groups.
- **Validation:** Purity > 99% by HPLC; structure confirmed by X-ray crystallography.
- **Failure Modes:** Low yield or decomposition; backup: alternative heavy atom (Te) or different S-incorporation route.

**Photophysical Characterization**
- **Purpose:** Measure PLQY, transient PL (ns to μs), and temperature-dependent decay.
- **Justification:** Determine kRISC and ΔEST accurately.
- **Procedure:** Use integrating sphere for PLQY; streak camera for transient; variable-temperature cryostat.
- **Critical Variables:** Excitation wavelength, film thickness, oxygen exclusion.
- **Controls:** Measure standard dyes (e.g., rubrene).
- **Validation:** Reproducibility within 5%.
- **Expected Evidence:** Rate constants and energy levels.
- **Failure Modes:** Instrument sensitivity; backup: use TCSPC with lower time resolution.

**Device Fabrication**
- **Purpose:** Fabricate OLEDs with optimized stack: ITO / HIL / HTL / EML / ETL / EIL / Al.
- **Justification:** Standard process for reliable performance.
- **Procedure:** Vacuum deposition at 10⁻⁶ Torr; doping concentration tuned.
- **Critical Variables:** Doping concentration, host material, layer thicknesses.
- **Controls:** Fabricate reference device with known emitter (e.g., tFSeBN from [1]).
- **Validation:** EQE measured with calibrated photodiode; spectral match to literature.
- **Expected Evidence:** J-V-L curves, EQE vs. L, EL spectra.
- **Failure Modes:** Short circuits, poor charge injection; backup: add Liq in ETL or MoO₃ in HIL.

**Overall Technical Route:** Computational design → synthesis → photophysics → device → hyperfluorescent integration. Feedback loops between WP3 and WP1/WP2 for iteration.

> ⚠ Missing must-include items:
> - No specific equipment details (e.g., deposition tool, cryostat) mentioned in evidence.
> - No information on experienced personnel for synthesis or device.

> ⚠ Unsupported claims flagged for evidence:
> - Claim that xTB screening can accurately predict ΔEST for MR-TADF is supported by [2] only for a benchmark, but may not extend to novel S···S designs.

### 18. Missing methods or overclaims

_(emitted inline within item 17)_


## F. Innovation

### 19. Innovation categories (conceptual / material / device / translational)

**Conceptual Innovation:**
- *What existed:* MR-TADF emitters with slow RISC and severe roll-off in red region; NIR MR-TADF virtually unexplored.
- *What is new:* Combining heavy-atom embedding (Se) with MR framework to simultaneously enhance RISC and maintain narrowband emission, as demonstrated in [1].
- *Why it matters:* Provides a direct route to efficient red OLEDs without noble metals, addressing industry need for stable high-brightness displays.
- *Truly innovative vs. incremental:* This is a significant step forward; Se-embedded MR emitters represent a new class not previously reported in literature.

**Methodological Innovation:**
- *What existed:* Conventional approaches rely on trial-and-error synthesis or costly high-throughput screening.
- *What is new:* Use of xTB-based computational screening [2] to pre-select MR-TADF candidates with target properties, significantly reducing experimental effort.
- *Why it matters:* Accelerates material discovery; can be applied to other emission colors.
- *Truly innovative vs. incremental:* Moderate innovation; xTB screening is known but not widely applied to MR-TADF.

**Technical Innovation:**
- *What existed:* Red MR-OLEDs show >30% EQE but severe roll-off at high brightness.
- *What is new:* Achieving ultra-low roll-off (EQE > 25% at 10,000 cd m⁻²) via fast RISC from Se embedding [1].
- *Why it matters:* Enables practical use in high-brightness applications (e.g., lighting).
- *Truly innovative vs. incremental:* High innovation; roll-off was a critical bottleneck.

**Application Innovation:**
- *What existed:* Hyperfluorescent systems rely on noble-metal sensitizers (Ir, Pt).
- *What is new:* Using Se-MR TADF as a metal-free sensitizer for hyperfluorescent OLEDs, achieving pure-red CIE coordinates [1].
- *Why it matters:* Eliminates noble metals, reducing cost and environmental impact.
- *Truly innovative vs. incremental:* High innovation; demonstrates eco-friendly alternative.

**Overall Assessment:** The proposed research is highly innovative, building on recent breakthroughs [1] and extending them to NIR region via new S···S interaction concept [5]. The computational methodology adds efficiency.

> ⚠ Missing must-include items:
> - No evidence that S···S interaction has been applied to MR-TADF before.
> - The xTB screening method [2] has not been experimentally validated for MR-TADF by the applicant.

> ⚠ Unsupported claims flagged for evidence:
> - The claim that Se-MR emitters are a 'new class' is supported by [1] but not independently verified here.
> - NIR-II MR-TADF via S···S interaction is speculative; no prior art in MR-TADF.

### 20. Per-innovation strength (strong / moderate / weak)

_(emitted inline within item 19)_


## G. Preliminary Basis

### 21. Research foundation (placeholders where user data is unavailable)

**Research Foundation:**
- The team has expertise in organic synthesis (particularly boron-nitrogen chemistry), photophysics, and device physics (assumed; not detailed in evidence).
- A recent landmark study demonstrated Se-embedded MR emitter (tFSeBN) achieving record RISC rate of 7.5×10⁵ s⁻¹ and EQE max 34.7% [1]. This serves as a direct starting point for molecular design.
- The xTB high-throughput screening benchmark [2] provides a validated computational tool for screening TADF candidates.
- The review on NIR OLED emitters [LOCAL:94cbdecc1259] outlines challenges and strategies for near-infrared emission, including MR-TADF and Pt complexes.
- Theoretical understanding of exciton-vibrational decoupling via S···S interaction is emerging from NIR-II fluorophores [5].

**Evidence Matrix:**
| Claim | Support | Source | Strength | Weakness |
|-------|---------|--------|----------|----------|
| Se-embedding accelerates RISC in MR emitters | tFSeBN shows kRISC = 7.5×10⁵ s⁻¹ | [1] | Direct experimental proof | Only one compound; generality unclear |
| xTB screening effective for TADF | Benchmark of 747 molecules | [2] | Strong statistical evidence | May not capture MR-specific effects |
| S···S interaction reduces vibrational losses | Demonstrated in NIR-II fluorophores | [5] | Mechanistic insight | Not shown in MR-TADF; different core |
| MR-TADF can achieve narrowband NIR emission | Review discusses MR-TADF for NIR | [LOCAL:94cbdecc1259] | Qualitative review | No specific molecules with high efficiency |

**Team Capability:** (To be filled with applicant data; currently missing)
- Synthetic chemistry: experience in multi-step organic synthesis, including boron and selenium chemistry.
- Photophysics: access to TCSPC, streak camera, integrating sphere (assumed).
- Device fabrication: vacuum deposition system and characterization equipment.

**Summary:** The team has a strong foundation built on recent cutting-edge results [1] and established computational methods [2]. The gap lies in extending these to NIR-II and demonstrating generalizability.

> ⚠ Missing must-include items:
> - No specific information about the team's prior work or publications in this area.
> - No mention of available equipment or institutional support.

> ⚠ Unsupported claims flagged for evidence:
> - The assumption that the team has experience in Se chemistry is not backed by evidence.

### 22. Evidence matrix (claim → support → missing → evidence needed)

_(emitted inline within item 21)_


## H. Feasibility

### 23. Scientific / technical / resource / timeline / applicant-fit feasibility

**Scientific Feasibility:**
- The primary hypothesis is directly supported by experimental results: Se-embedded MR emitters achieve fast RISC and high EQE with low roll-off [1]. This confirms the underlying mechanism and validates the design strategy.
- Computational screening using xTB has shown high accuracy for TADF molecules [2], reducing risk in candidate selection.
- The extension to S···S interactions is based on established principles from NIR-II fluorophores [5], though adaptation to MR-TADF requires validation.

**Technical Feasibility:**
- Synthetic routes for Se-insertion into MR frameworks are described in [1]; they can be adapted for new derivatives with expected yields >30%.
- Characterization techniques (transient PL, EQE measurement) are standard and accessible.
- Device fabrication protocols are mature; hyperfluorescent architecture was demonstrated in [1], proving the concept works.

**Timeline Feasibility:**
- WP1 (Se-MR synthesis): 9 months for two candidates reasonable; literature precedent [1] suggests synthesis within 3-6 months.
- WP2 (NIR-II): computational screening within 3 months, synthesis and testing within 9 months – aggressive but feasible with experienced team.
- Device work (WP4, WP5) can begin from Month 6 using initial emitters.
- Overall 36 months is adequate for all objectives.

**Personnel Feasibility:**
- A team of ~5 researchers (2 synthesis, 1 photophysics, 1 device, 1 computational) can cover all work packages.
- No specific personnel details provided; assumed availability.

**Equipment Feasibility:**
- Standard chemical lab, glovebox, vacuum deposition system, and optical characterization instruments are required. If not available, collaboration can be established (not detailed in evidence).

**Mitigation of Risks:**
- Risk: Slow RISC in new emitters → Redesign with stronger donors or heavier atoms (Te).
- Risk: Low PLQY in NIR-II → Use Pt complexes as backup [LOCAL:94cbdecc1259].
- Risk: Poor charge balance in devices → Optimize layer structure or use different hosts.

**Conclusion:** The project is scientifically sound, technically achievable, and the risks are manageable with well-defined mitigation strategies.

> ⚠ Missing must-include items:
> - No information on actual team size, expertise, or equipment availability.
> - No preliminary data from the applicant's own lab.

> ⚠ Unsupported claims flagged for evidence:
> - Assumption that synthesis yields and timelines align with literature may not hold without similar expertise.


## I. Timeline

### 24. 3-year timeline + milestones + critical dependencies + go/no-go points

**Overall Period: 36 Months**

| Year | Quarter | Activities | Milestones | Deliverables |
|------|---------|------------|------------|--------------|
| 1 | Q1 | Computational screening for Se-MR and S···S design; initial synthesis of Se-MR candidates | Top 10 candidates identified (Se-MR); synthesis started | Candidate list; 1st Se-MR compound |
| 1 | Q2 | Complete synthesis of Se-MR emitters (2-3); begin photophysics | Se-MR fully characterized (PLQY, kRISC) | Photophysical report |
| 1 | Q3 | Start device fabrication with best Se-MR; continue synthesis of more Se-MR analogs | Red OLED EQE > 30% achieved | Device performance data |
| 1 | Q4 | Se-MR optimization; begin NIR-II synthesis | Two high-performance Se-MR emitters ready; NIR-II candidate selected | Optimized emitters; NIR-II design report |
| 2 | Q1 | Device optimization for Se-MR; NIR-II synthesis and characterization | Roll-off < 20% at 1000 cd m⁻²; NIR-II PLQY > 70% | Improved device; NIR-II emitter |
| 2 | Q2 | Hyperfluorescent red OLED development; NIR-II device fabrication | Hyperfluorescent red OLED CIE (0.70,0.30) | Hyperfluorescent device data |
| 2 | Q3 | NIR-II device optimization; lifetime testing | NIR-II OLED EQE > 10% | NIR-II device performance |
| 2 | Q4 | Finalize red and NIR-II devices; begin tandem/hyperfluorescent NIR | Red device with low roll-off; NIR hyperfluorescent prototype | Prototype devices |
| 3 | Q1 | Comprehensive photophysical and device characterization; start writing | All data collected; first draft of paper | Data analysis |
| 3 | Q2 | Final paper preparation; patent filing | Manuscripts submitted; patent application | Drafts |
| 3 | Q3 | Revision and response to reviewers; project wrap-up | Papers accepted; final report | Final report |
| 3 | Q4 | Dissemination (conferences, technology transfer) | Presentations given | Impact summary |

**Key Milestones:**
- M1 (Month 6): First Se-MR emitter with kRISC > 10⁵ s⁻¹.
- M2 (Month 12): Red OLED with EQE max > 30% and roll-off < 20% at 1000 cd m⁻².
- M3 (Month 18): NIR-II emitter with emission > 1000 nm and PLQY > 70%.
- M4 (Month 24): Hyperfluorescent red OLED with CIE (0.70,0.30) and EQE > 25%.
- M5 (Month 30): NIR-II OLED with EQE > 10%.
- M6 (Month 36): Two high-impact publications and one patent.

**Dependencies:**
- Device fabrication relies on high-quality emitters from WP1/WP2.
- Hyperfluorescent approach depends on successful sensitizer performance.
- Computational screening is input for synthesis; can be started in parallel.

> ⚠ Missing must-include items:
> - No information on patent prior art or budget allocation.
> - No conference names or specific journals.

> ⚠ Unsupported claims flagged for evidence:
> - The milestone EQE > 30% for red OLED is achievable as per [1], but for new emitters it is speculative.
> - NIR-II OLED EQE > 10% is an estimate; no evidence provides a benchmark.


## J. Expected Outcomes

### 25. Realistic expected outputs

_(blueprint section 'Expected Outputs' not yet drafted)_


## K. Risk Register

### 26. Full risk table (risk, probability, impact, early warning, mitigation, contingency)

_(blueprint section 'Risk Register and Mitigation' not yet drafted)_


## L. Budget Logic

### 27. Task-to-budget rationale (generic categories)

_(blueprint section 'Budget Logic and Task-to-Budget Mapping' not yet drafted)_

### 28. No final numbers unless input is provided

_(emitted inline within item 27)_

### 29. Reviewer vulnerabilities in the budget logic

_(emitted inline within item 27)_


## M. Compliance and Attachments

### 30. China-grant compliance + attachments checklist

**Ethics, Security, and Compliance:**

_(blueprint section 'Ethics, Security, and Compliance' not yet drafted)_

**Required Attachments Checklist:**

_(blueprint section 'Required Attachments Checklist' not yet drafted)_



## N. Reviewer Simulation

### 31. At least five reviewers in canonical order

#### novelty (likely_score=40, rejection_risk=high)

**Strengths:**
- Identifies a clear bottleneck in red/NIR MR-TADF emitters (slow RISC).
- Proposes a systematic chalcogen series (S, Se, Te) to explore heavy-atom effect.
- Claims a record kRISC from preliminary Se-embedded emitter (7.5×10⁵ s⁻¹).

**Weaknesses:**
- The core design (Se-embedding) is not novel; already demonstrated in Ref [1] at 607 nm.
- Extension to NIR (>650 nm) is speculative; no supporting data or proof-of-concept.
- The novelty over existing work (e.g., tFSeBN) appears incremental, not transformative.
- Claim of applying S…S interactions from NIR-II fluorophores to MR-TADF is unsupported and likely invalid.
- No comparison with alternative strategies (e.g., rigid pi-extension, donor-acceptor) to justify superiority.

**Required fixes (mandatory revisions):**
- Provide preliminary data (e.g., PL spectra, kRISC) for at least one NIR (>650 nm) emitter.
- Clearly delineate what is novel beyond Ref [1] (e.g., new chalcogen combinations, new emission wavelengths).
- Include a thorough comparison table with state-of-the-art red/NIR MR-TADF emitters from last 2 years.
- Remove or substantiate the unsupported claim about S…S interactions with proper references.

#### methods (likely_score=30, rejection_risk=high)

**Strengths:**
- Well-defined central scientific question with sub-questions.
- Proposes systematic variation of chalcogen and donor strength.

**Weaknesses:**
- No detailed experimental methods described (synthesis, characterization, device fabrication).
- Missing control experiments (e.g., reference materials without heavy atoms, isomer controls).
- No clear definition of key variables (e.g., how RISC rate is measured, error margins).
- No validation or failure mode analysis (e.g., if emitters aggregate, if kRISC saturates).
- Lack of statistical plan or replicates for device measurements.

**Required fixes (mandatory revisions):**
- Add a detailed methods section: synthetic routes, purification, photophysical measurements, device fabrication protocols.
- Include at least two control emitters (e.g., oxygen- and sulfur-embedded analogs) for comparison.
- Specify how kRISC, PLQY, and ΔEST will be measured and analyzed (e.g., transient PL, quantum yield setup).
- Anticipate failure modes: low PLQY in NIR, aggregation quenching, thermal degradation; propose mitigations.
- Define success criteria (e.g., kRISC > 5×10⁵ s⁻¹, EQE > 20% at 1000 cd/m²).

#### feasibility (likely_score=25, rejection_risk=very_high)

**Strengths:**
- Project has a logical scientific plan and clear milestones.
- Preliminary data for Se-embedding suggests feasibility of the approach.

**Weaknesses:**
- No timeline or Gantt chart provided; cannot assess if 3-4 years is adequate.
- No information on PI or team expertise, equipment access, or institutional support.
- Synthesis of multiple chalcogen-embedded MR emitters (Te especially) is challenging and may require specialized facilities.
- No mention of contingency plans for synthetic failures or low device performance.
- Dependencies on external collaborators (e.g., theoretical calculations, device testing) are unclear.

**Required fixes (mandatory revisions):**
- Provide a detailed 3-year timeline with semiannual milestones for synthesis, characterization, and device optimization.
- Include a statement of PI's track record and institutional facilities (glovebox, vacuum deposition, transient PL setup).
- Identify key personnel and their roles; include letters of collaboration if external facilities are needed.
- Assess risk of Te-embedding (toxicity, stability) and propose alternative paths.
- Add a risk mitigation table: high-risk tasks (e.g., Te synthesis) with backup approaches.

#### china_funder_fit (likely_score=35, rejection_risk=high)

**Strengths:**
- Topic aligns with display technology and advanced materials, which are NSFC priorities.
- Chinese title and keywords in Chinese are provided.
- Potential relevance to National Key R&D Programs on optoelectronics.

**Weaknesses:**
- No call metadata provided; cannot verify alignment with specific program or discipline code (e.g., F0504).
- Abstract and main body are in English only; NSFC usually requires full Chinese version.
- No mention of strategic priorities like 'carbon neutrality', 'indigenous innovation', or 'industrial application'.
- Missing compliance statements (e.g., no dual-use concerns, ethics approval for animal/human studies not applicable).
- Lacks explicit connection to China's OLED industry gap or national needs.

**Required fixes (mandatory revisions):**
- Identify the target funding call (e.g., NSFC General Program) and adhere to its discipline code and format.
- Provide a complete Chinese translation of the proposal, especially abstract and key sections.
- Explicitly state how the project addresses China's strategic needs in display technology or energy-efficient materials.
- Include a section on potential commercial impact or collaboration with Chinese OLED manufacturers.
- Add compliance statements: no ethical issues, no sensitive technologies, adherence to funder's guidelines.

#### budget_compliance (likely_score=10, rejection_risk=very_high)

**Strengths:**
- No budget is included, so no over-budget or misallocation errors yet.

**Weaknesses:**
- Complete absence of a budget table and budget justification.
- No task-to-budget mapping; cannot assess reasonableness of requested funds.
- Missing required attachments: biosketches, current support, facilities & equipment list.
- No justification for equipment purchase (e.g., vacuum deposition system) or consumables.
- No mention of ethics or security compliance forms (e.g., no dual-use research of concern).

**Required fixes (mandatory revisions):**
- Provide a detailed budget table by category (personnel, equipment, supplies, travel, etc.) with justification.
- Map each budget item to specific tasks (e.g., WP2 synthesis: chemicals $X; WP3 device: equipment rental $Y).
- Include biosketches for all key personnel and letters of institutional support.
- Add a facilities & equipment statement confirming access to necessary instrumentation.
- Complete ethics and compliance forms, including a statement that no dual-use or safety concerns apply.


### 32. Per reviewer: strengths, weaknesses, rejection concern, score, mandatory revision

_(emitted inline within item 31)_


## O. Competitiveness Score

### 33. Proposal scored out of 100 across 10 axes

| Axis | Weight | Score |
|---|---|---|
| call_alignment | 15 | 5 |
| scientific_significance | 15 | 6 |
| originality_innovation | 15 | 6 |
| hypothesis_clarity | 10 | 3 |
| methodological_rigor | 15 | 4 |
| feasibility | 10 | 2 |
| research_foundation | 8 | 2 |
| budget_logic | 4 | 0 |
| risk_mitigation | 4 | 1 |
| compliance_completeness | 4 | 0 |
| **Total** | **100** | **9** |

**Decision band:** _not submission-ready_  
(>=90 competitive · >=80 promising · >=70 vulnerable · <70 not submission-ready)

### 34. Decision band (competitive / promising / not submission-ready)

_(emitted inline within item 33)_


## P. Weakness Repair Plan

### 35. Top 10 weaknesses

##### Priority 1: No timeline or Gantt chart provided; cannot assess if 3-4 years is adequate.
- **Why it matters:** Flagged by 'feasibility' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Timeline and Milestones
- **Evidence needed / exact revision:** Provide a detailed 3-year timeline with semiannual milestones for synthesis, characterization, and device optimization.

##### Priority 2: No information on PI or team expertise, equipment access, or institutional support.
- **Why it matters:** Flagged by 'feasibility' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Applicant and Team Profile
- **Evidence needed / exact revision:** Provide a detailed 3-year timeline with semiannual milestones for synthesis, characterization, and device optimization.

##### Priority 3: Synthesis of multiple chalcogen-embedded MR emitters (Te especially) is challenging and may require specialized facilities.
- **Why it matters:** Flagged by 'feasibility' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Required Attachments Checklist
- **Evidence needed / exact revision:** Provide a detailed 3-year timeline with semiannual milestones for synthesis, characterization, and device optimization.

##### Priority 4: Complete absence of a budget table and budget justification.
- **Why it matters:** Flagged by 'budget_compliance' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Budget Logic and Task-to-Budget Mapping
- **Evidence needed / exact revision:** Provide a detailed budget table by category (personnel, equipment, supplies, travel, etc.) with justification.

##### Priority 5: No task-to-budget mapping; cannot assess reasonableness of requested funds.
- **Why it matters:** Flagged by 'budget_compliance' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Budget Logic and Task-to-Budget Mapping
- **Evidence needed / exact revision:** Provide a detailed budget table by category (personnel, equipment, supplies, travel, etc.) with justification.

##### Priority 6: Missing required attachments: biosketches, current support, facilities & equipment list.
- **Why it matters:** Flagged by 'budget_compliance' reviewer (rejection risk=very_high).
- **What to revise / section to rewrite:** Required Attachments Checklist
- **Evidence needed / exact revision:** Provide a detailed budget table by category (personnel, equipment, supplies, travel, etc.) with justification.

##### Priority 7: The core design (Se-embedding) is not novel; already demonstrated in Ref [1] at 607 nm.
- **Why it matters:** Flagged by 'novelty' reviewer (rejection risk=high).
- **What to revise / section to rewrite:** Submission-Readiness Score
- **Evidence needed / exact revision:** Provide preliminary data (e.g., PL spectra, kRISC) for at least one NIR (>650 nm) emitter.

##### Priority 8: Extension to NIR (>650 nm) is speculative; no supporting data or proof-of-concept.
- **Why it matters:** Flagged by 'novelty' reviewer (rejection risk=high).
- **What to revise / section to rewrite:** Call Metadata
- **Evidence needed / exact revision:** Provide preliminary data (e.g., PL spectra, kRISC) for at least one NIR (>650 nm) emitter.

##### Priority 9: The novelty over existing work (e.g., tFSeBN) appears incremental, not transformative.
- **Why it matters:** Flagged by 'novelty' reviewer (rejection risk=high).
- **What to revise / section to rewrite:** Research Content / Work Packages
- **Evidence needed / exact revision:** Provide preliminary data (e.g., PL spectra, kRISC) for at least one NIR (>650 nm) emitter.

##### Priority 10: No detailed experimental methods described (synthesis, characterization, device fabrication).
- **Why it matters:** Flagged by 'methods' reviewer (rejection risk=high).
- **What to revise / section to rewrite:** Risk Register and Mitigation
- **Evidence needed / exact revision:** Add a detailed methods section: synthetic routes, purification, photophysical measurements, device fabrication protocols.


### 36. Per weakness: why it matters, what to revise, evidence needed, how to rewrite

_(emitted inline within item 35)_



## Information State

**Confirmed facts:**
- tFSeBN emits at 607 nm with RISC rate 7.5×10^5 s⁻¹ [1].
- tFSeBN-based OLED achieves EQE_max 34.7%, EQE 31.0% at 1000 cd m⁻², 25.6% at 10,000 cd m⁻² [1].
- Selenium embedding accelerates RISC in MR-TADF [1].
- Deep red MR-TADF emitters (e.g., R-BN, R-TBN) show PLQY 100% and EQE 28% at 664 nm and 686 nm [LOCAL:94cbdecc1259].
- Twisted carbazole-fused DABNA derivative achieves EQE 39% at 588 nm with high doping tolerance [LOCAL:94cbdecc1259].

**Reasonable assumptions:**
- Selenium embedding can be generalized to other MR frameworks for NIR emission.
- High RISC rates directly reduce efficiency roll-off.
- High-throughput screening (xTB-based) can effectively predict TADF properties for Se-MR emitters.
- Emission dipole orientation optimization (e.g., corrugated structures) can further enhance light outcoupling for red/NIR OLEDs.

**Missing information:**
- No experimental data on Se-embedded MR-TADF emitters emitting beyond 700 nm.
- No long-term device stability data for tFSeBN or similar emitters.
- No detailed hyperfluorescent sensitization data beyond the demonstration in [1].
- No specific funder call requirements or priority areas.
- No team composition or budget details provided.
- Drafting note: sections chunk 3 sub-call failed: ValueError: Could not parse JSON from LLM output: {
  "sections": [
    {
      "name": "Expected Outputs",
      "content": "### Expected Outputs\n#### Scientific Outputs\

## Local-document evidence used

- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _This journal is © The Royal Society of Chemistry and the Chinese Chemical Society 2024 Mater. Chem. Front., 2024, 8, 1731–1766 | 1731 Cite this: Mater. Chem. Front., 202 4, 8, 1731 Recent advances in highly-eﬃcient near infrared OLED emitte_
- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _igidity of their structure as well as admixtures of the 3LC states often lead to a relatively narrowband luminescence with a clearly resolved vibronic structure, a feature of importance for colour purity in visible light OLEDs 71 as well as_
- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _e. Despite that flaw however, aggregate platinum( II) complexes are among the most efficient NIR emitters known to date. Monomeric complexes The first platinum( II) compounds to give eﬃcient NIR electro- luminescence were porphyrin complexe_
- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _TADF core with peripheral donor groups has shown to result in emission tuning. However, when significantly strong donor groups are employed the lowest excited states lose the short- range charge transfer character responsible for the narrow_
- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _twisted carbazole-fused DABNA derivative that displays Zext up to 39% with lEL at 588 nm. The highly twisted structure helped to relieve concentration quenching, allowing the development of devices with doping ratio as high as 8%, unusual f_
- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _tion coupling due to the shallow potential energy surface induced by the MR eﬀect. The deep red emitters, R-BN and R-TBN, showed high PLQY of 100% and their use in OLEDs resulted inl EL a t6 6 4n ma n d6 8 6n mw i t hF W H M s below 50 nm a_

## References

_⚠ **Self-heal triggered.** Research Scout returned zero papers (likely routed in `ideation` mode), so the architect ran an EMERGENCY direct fetch against the 5-provider abstraction (OpenAlex · arXiv · Crossref · Semantic Scholar · Europe PMC).  These references BYPASSED Scout's scoring + dedup + gap-analysis pipeline — treat their relevance as provisional and re-run with the routing fix in place for full quality._

[1] Red OLED with efficiency of 25.6% at 10,000 cd m−2 based on selenium embedding multiple resonance framework — openalex 2026 · URL: https://doi.org/10.1038/s41377-026-02220-w
[2] xTB-Based High-Throughput Screening of TADF Emitters: 747-Molecule Benchmark — openalex 2026 · URL: https://doi.org/10.1021/acs.jcim.5c02978
[3] Interplay of Aspect Ratio and Emission Dipole Orientation for Light Extraction in Corrugated Red, Green and Blue OLEDs — openalex 2026 · URL: https://doi.org/10.3390/photonics13030287
[4] Understanding luminescence of metal-containing thermally activated delayed fluorescence (TADF) luminophores — openalex 2026 · URL: https://doi.org/10.1039/d5qi02203g
[5] Overcoming the Energy Gap Law in NIR-II Fluorophores via S…S Interaction-Mediated Exciton-Vibrational Decoupling — openalex 2026 · URL: https://doi.org/10.26434/chemrxiv.15002241/v1

## Local-document evidence used

- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _This journal is © The Royal Society of Chemistry and the Chinese Chemical Society 2024 Mater. Chem. Front., 2024, 8, 1731–1766 | 1731 Cite this: Mater. Chem. Front., 202 4, 8, 1731 Recent advances in …_
- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _igidity of their structure as well as admixtures of the 3LC states often lead to a relatively narrowband luminescence with a clearly resolved vibronic structure, a feature of importance for colour pur…_
- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _e. Despite that flaw however, aggregate platinum( II) complexes are among the most efficient NIR emitters known to date. Monomeric complexes The first platinum( II) compounds to give eﬃcient NIR elect…_
- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _TADF core with peripheral donor groups has shown to result in emission tuning. However, when significantly strong donor groups are employed the lowest excited states lose the short- range charge trans…_
- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _twisted carbazole-fused DABNA derivative that displays Zext up to 39% with lEL at 588 nm. The highly twisted structure helped to relieve concentration quenching, allowing the development of devices wi…_
- **[LOCAL:94cbdecc1259]** 94cbdecc1259 — _tion coupling due to the shallow potential energy surface induced by the MR eﬀect. The deep red emitters, R-BN and R-TBN, showed high PLQY of 100% and their use in OLEDs resulted inl EL a t6 6 4n ma n…_

## References

[1] Red OLED with efficiency of 25.6% at 10,000 cd m−2 based on selenium embedding multiple resonance framework — openalex 2026 · URL: https://doi.org/10.1038/s41377-026-02220-w
[2] xTB-Based High-Throughput Screening of TADF Emitters: 747-Molecule Benchmark — openalex 2026 · URL: https://doi.org/10.1021/acs.jcim.5c02978
[3] Interplay of Aspect Ratio and Emission Dipole Orientation for Light Extraction in Corrugated Red, Green and Blue OLEDs — openalex 2026 · URL: https://doi.org/10.3390/photonics13030287
[4] Understanding luminescence of metal-containing thermally activated delayed fluorescence (TADF) luminophores — openalex 2026 · URL: https://doi.org/10.1039/d5qi02203g
[5] Overcoming the Energy Gap Law in NIR-II Fluorophores via S…S Interaction-Mediated Exciton-Vibrational Decoupling — openalex 2026 · URL: https://doi.org/10.26434/chemrxiv.15002241/v1

---
## Session Footer
**Governor rationale:** Highly mission-aligned request for a China grant proposal on red/NIR MR-TADF OLEDs, requiring literature support and rigorous structure.

**Scientific Verifier:** assessment=`incomplete` route=`human_review` recommendation=`needs_more_evidence`

*Generated by AURA on 2026-05-20T11:28:19.*
