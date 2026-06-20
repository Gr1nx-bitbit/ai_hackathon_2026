# Problem Statement & Productionisation Blockers

## The Problem

Gene editing therapies—CRISPR-Cas systems, base editors, prime editors—introduce targeted modifications to a patient's genetic code. The modified proteins they produce are novel sequences; the immune system has never seen them before and may treat them as foreign invaders.

Two independent failure modes can kill a therapy:

**1. Immunogenic rejection (Stages 1–3)**  
The immune system discovers the modified protein. Proteasomes cleave it into peptide fragments (neoepitopes). If those fragments bind the patient's HLA molecules and are presented on the cell surface, T-cells and B-cells are activated. The result: therapeutic cells are destroyed before they can act. This is a hard failure with no recovery path at the cellular level.

**2. Systems-level disruption (Stage 4)**  
Even if the immune system tolerates the edit, the cell may not. Cells are highly-connected biochemical networks. A single gene change can cascade into unintended transcriptome drift, cryptic splice events, metabolic stress, or activation of apoptotic programs—even with zero immune signal.

Current clinical practice handles these risks largely in series and in wet-lab settings: run an immunogenicity assay, wait for results, then run separate cell-line assays. Each iteration takes weeks. Patient-specific HLA diversity means results from one patient don't transfer to another. There is no unified, automated, patient-personalised screening loop that evaluates both risks concurrently before a therapy enters the clinic.

This pipeline is that loop—in silico, personalised, and fast.

---

## What This POC Demonstrates

- A **multi-stage, state-driven screening workflow** built on LangGraph that handles the non-linear dependencies of biological data (conditional routing, cyclic retry, parallel branches, early exits).
- A **mock-to-real swap architecture**: every computational biology tool is abstracted behind an interface. Replacing a mock with a real binary requires touching two files (`registry.py` + the new implementation) and zero graph logic.
- A **patient-specific risk model** that combines structural, immunogenic, reactivity, and systems-dynamics scores into a single weighted risk vector.
- A **Fetch AI uAgent wrapper** that exposes the pipeline as a callable agent on the Agentverse network, making it composable with any other agent in the ecosystem.
- An **LLM clinical report node** (Claude or ASI:One) that translates raw scores into physician-readable findings.

---

## What Is Holding This Back From a Real Product

### 1. The Computational Biology Tools Are Not Deployed

The biggest blocker. The pipeline mocks four categories of specialised software:

| Stage | Real Tool | Deployment Status |
|---|---|---|
| Stage 1 | ~~AlphaFold3 or ESMFold + FreeSASA~~ → **ESMFold via ESM Atlas REST API** | **Implemented.** Free public API, no download needed. Enable with `ESMFOLD_ENABLED=1`. Submits the sequence to Meta's ESM Atlas endpoint, parses the returned PDB for pLDDT and SASA using BioPython. See `src/tools/real/structural_tool.py`. |
| Stage 2 (Class I + II) | ~~NetMHCpan / NetMHCIIpan~~ → **IEDB REST API** | **Implemented.** Free public API, no download needed. Enable with `IEDB_ENABLED=1`. Calls NetMHCpan-4.1 (Class I) and NetMHCIIpan-4.0 (Class II) via the IEDB Analysis Resource. See `src/tools/real/hla_tool.py`. |
| Stage 2 (processing) | NetChop-3.1 | IEDB's "recommended" method includes antigen processing scoring via NetMHCpan's EL (eluted ligand) model, which implicitly captures processing probability. Explicit cleavage site modelling (NetChop) is not exposed separately. |
| Stage 3 (T-cell) | NetTCR-2.0 | DTU Bioinformatics. No public REST API; requires Docker or Conda install. Same containerisation strategy applies as for Stage 4. |
| Stage 3 (B-cell) | ~~DiscoTope-3.0~~ → **BepiPred via IEDB REST API** | **Implemented (linear epitopes).** Free public API, no download needed. Enable with `BEPIPRED_ENABLED=1`. See `src/tools/real/bcell_tool.py`. **Note:** This detects *linear* B-cell epitopes. *Conformational* epitope prediction (the clinically dominant pathway, ~80–90% of antibody epitopes) would require DiscoTope-3.0 applied to the Stage 1 PDB structure. DiscoTope-3.0 is CLI-only (no PyPI package, complex conda env) — impractical for a REST-API-first POC. Linear screening is a well-validated surrogate for initial risk stratification. |
| Stage 4 | GenBio AI AIDO (ModelGenerator) | Requires GenBio AI API access or self-hosted inference. The `model_generator` Python package is available but the foundation model weights are not publicly downloadable. Requires partnership or API key. |

**Path forward:** Stages 1, 2, and 3 B-cell are now real. Stage 1 uses ESMFold via the ESM Atlas REST API (pLDDT + SASA from BioPython); Stage 2 uses the IEDB REST API (NetMHCpan-4.1 Class I + NetMHCIIpan-4.0 Class II); Stage 3 B-cell uses BepiPred via the same IEDB API (linear epitope prediction). Next priorities: containerise NetTCR-2.0 for Stage 3 T-cell reactivity, then negotiate API access to GenBio AIDO (Stage 4). For a production system, Stage 3 B-cell should be extended to conformational epitope prediction (DiscoTope-3.0 applied to the Stage 1 PDB output) once a containerised CLI wrapper is available. Each mock ABC maps 1:1 to a real implementation — the graph requires no changes.

#### Tool-Specific Limitations

**AlphaFold3 / ESMFold (Stage 1)**
- **Static single conformation.** Both tools output a single predicted structure. Proteins are dynamic; the SASA of an edit zone can vary considerably across a conformational ensemble. A residue that appears buried in the static structure may be transiently surface-exposed in vivo. Molecular dynamics sampling would capture this but at much higher computational cost.
- **Post-translational modifications (PTMs) not modelled.** Glycosylation, phosphorylation, and ubiquitination can dramatically alter surface accessibility and antigenicity. Neither tool accounts for PTMs in the edited zone, so SASA estimates for glycoprotein edits are unreliable.
- **Multimeric context ignored.** The pipeline processes the edited protein in isolation. If the target protein is part of a stable complex in vivo, the interface residues contribute to burial — an edit flagged as exposed in the monomer may be sterically shielded in the complex.
- **Performance degrades beyond training distribution.** Both models were trained on structures in the PDB. Novel synthetic proteins or heavily engineered sequences with no close structural homologue will yield lower pLDDT scores and less reliable SASA estimates. The retry/fallback loop handles the extreme case but cannot improve accuracy.

**NetChop-3.1 (Stage 2 — proteasomal cleavage)**
- **Models the constitutive proteasome only.** In inflamed tissues and activated antigen-presenting cells, the immunoproteasome is expressed. It has different catalytic subunits and produces a distinct cleavage pattern. A peptide predicted not to be generated by the constitutive proteasome may still be produced — at high yield — in the inflammatory microenvironment a gene therapy triggers.
- **ERAP1/ERAP2 and TAP trimming not modelled.** After proteasomal cleavage, peptides are transported into the ER by TAP and trimmed by ERAP aminopeptidases before MHC loading. Both steps are selective and alter the final presented peptide repertoire. NetChop stops at the proteasome exit; a full processing model would need TAP selectivity scores and ERAP1/2 trimming predictions.

**IEDB REST API / NetMHCpan-4.1 / NetMHCIIpan-4.0 (Stage 2 — MHC binding)**
- **Population representation bias.** NetMHCpan uses a pan-allele pseudo-sequence approach and can in principle predict for any HLA allele whose protein sequence is known — including novel alleles, provided you supply the binding-groove pseudo-sequence. However, its training data is drawn primarily from European-ancestry immunopeptidomics studies. For alleles frequent in African, East Asian, South Asian, or Indigenous populations, the model has seen fewer binding examples during training; %Rank calibration is less reliable for these alleles, leading to both over- and under-prediction of binders.
- **Binding affinity ≠ immunogenicity.** A strong HLA binder is necessary but not sufficient for T-cell activation. Central tolerance may have deleted T-cells reactive to self-similar peptides; peripheral tolerance mechanisms further dampen responses. %Rank captures binding but not the probability that a cognate T-cell exists in this patient's repertoire.
- **Class II predictions are substantially less accurate.** The MHC Class II groove is open-ended and accommodates peptides of 13–25 residues with a variable binding register. Compared to the well-constrained Class I 9-mer problem, Class II binding is significantly harder to predict. The pipeline's more lenient Class II threshold (10.0 vs 2.0) partly compensates, but false-negative rates are higher.
- **Peptide-MHC complex stability not captured.** Binding affinity (IC50) and off-rate (stability) are correlated but not identical. Some low-affinity peptides form surprisingly stable complexes that generate strong T-cell responses; some high-affinity peptides dissociate quickly and are poor immunogens.

**NetTCR-2.0 (Stage 3 — T-cell reactivity)**
- **Sparse training data.** Experimentally validated TCR:pMHC binding pairs are rare and biased toward a small number of well-studied antigens (CMV pp65, influenza NP, MART-1). For truly novel neoepitopes — which all gene therapy edits are by definition — the model is extrapolating far from its training distribution.
- **Polyclonal repertoire not modelled.** NetTCR-2.0 scores a specific TCR sequence against a peptide. In vivo, the patient has a polyclonal T-cell repertoire of ~10⁶–10⁷ unique TCR clonotypes. The relevant clinical question is whether any TCR in that repertoire can bind the neoepitope — a fundamentally different (and harder) question. Without repertoire sequencing data the pipeline cannot answer this directly.
- **Thymic selection and tolerance gaps not accounted for.** If the edited peptide is similar to a self-antigen, the corresponding T-cell clones may have been deleted during thymic negative selection, making the epitope non-immunogenic despite high predicted binding probability. Conversely, molecular mimicry with a pathogen antigen could mean a pre-existing memory T-cell pool is primed to cross-react.

**DiscoTope-3.0 (Stage 3 — B-cell reactivity)**
- **Static structure dependency.** DiscoTope scores 3D surface geometry from the Stage 1 structure file. All the conformational flexibility limitations of AlphaFold3/ESMFold carry forward here: a transiently exposed loop that forms a conformational epitope during protein dynamics may be missed if the static structure buries it.
- **Training set selection bias.** DiscoTope was trained on antibody-bound crystal structures from the PDB. Proteins that are immunogenic enough to generate characterised antibodies are overrepresented; proteins that generate weak or no B-cell responses are underrepresented. This inflates the prior probability of calling a conformational epitope.
- **Linear epitopes not covered.** DiscoTope only predicts conformational (discontinuous) epitopes. Linear B-cell epitopes — contiguous sequence stretches recognised by antibodies against denatured or partially unfolded protein — require a separate tool (e.g., BepiPred). For therapeutic contexts where the edited protein may be processed through endosomal pathways, linear epitopes are clinically relevant.
- **Existing antibody repertoire not considered.** Pre-existing cross-reactive antibodies (from prior infections or vaccines) could accelerate B-cell responses against the neoepitope. DiscoTope cannot capture this patient-specific priming.

**GenBio AI AIDO (Stage 4 — systems dynamics)**
- **Black-box neural network.** AIDO.Cell produces perturbation vectors without explicit mechanistic explanation. When the model flags CASP3 upregulation, it is reporting a pattern learned from training data, not simulating an actual biochemical pathway. Interpretability tools (attention maps, gradient attribution) can provide post-hoc reasoning but do not constitute a mechanistic explanation for regulatory review.
- **Training cell type coverage.** The foundation model was trained primarily on widely-used cancer cell lines (HEK293, HeLa, Jurkat) and a limited set of primary cell types. Predictions for rare primary tissues, patient-derived organoids, or stem-cell-derived therapeutic cells may be extrapolating beyond the training distribution.
- **Patient-specific genetic background ignored.** AIDO.Cell predicts transcriptome perturbation against a reference cell type. A patient with loss-of-function SNPs in the edited gene's regulatory network, or with germline CNVs affecting pathway members, will have a different baseline transcriptome. The model cannot account for this without patient-matched single-cell sequencing as input.
- **Temporal dynamics not captured.** The perturbation output is a snapshot — the predicted transcriptome state at an unspecified time after the edit. Cells have compensatory and adaptive mechanisms; an initial apoptotic signal may resolve, or a sub-threshold perturbation may compound over time. A single vector cannot distinguish transient stress from sustained toxicity.

### 2. HLA Database and Allele Coverage

The mock uses a fixed set of HLA alleles. Real clinical use requires:
- Access to a current IMGT/HLA database (updated quarterly)
- Coverage across all alleles the patient's HLA profile includes — NetMHCpan covers >16,000 HLA alleles but requires the full model weights
- Allele frequency weighting for population-level risk stratification (not just per-patient)

### 3. Structural Prediction Reliability in Disordered Regions

AlphaFold3 and ESMFold both struggle with intrinsically disordered regions (IDRs)—sequences that lack stable 3D conformation. The pipeline's pLDDT retry loop handles this conservatively (fallback: assume full surface exposure), but a real product needs:
- Molecular dynamics (MD) sampling for IDR regions to estimate ensemble-averaged SASA
- Integration with databases like DisProt or MobiDB to flag known disordered zones

### 4. Validation Against Clinical Ground Truth

The risk thresholds (pLDDT < 50, %Rank > 2.0, TCR threshold 0.5, etc.) and the scoring weights (10/35/35/20) are biologically motivated but not yet calibrated against patient outcome data. Productionisation requires:
- A labelled dataset of gene therapy trial outcomes with matched HLA profiles
- Retrospective validation: does a `high_risk` call from this pipeline correlate with observed immune rejection in trials?
- Prospective validation in a clinical research setting before any diagnostic claim

### 5. Regulatory and Clinical Validation

In silico predictions are not a substitute for wet-lab validation—they are a pre-screening filter to reduce the candidate space. Before this pipeline informs clinical decisions:
- The model would need to be qualified as a Software as a Medical Device (SaMD) under FDA 21 CFR Part 11 or EU MDR depending on jurisdiction
- Each individual computational tool (NetMHCpan, GenBio AIDO) would need cited performance benchmarks for the specific edit type and gene family
- The output report must make clear what it is: a probabilistic screening result, not a diagnosis

### 6. Personalisation Depth

The current pipeline screens a single edit against a single patient's HLA profile. A clinical-grade system would need to:
- Screen combinatorial edit sets (multiple simultaneous edits)
- Account for compound HLA heterozygosity effects
- Integrate patient co-morbidities and prior immunological history
- Run iterative design loops: suggest alternative edit positions with lower predicted immunogenicity

### 7. Fetch AI / Agentverse Integration

The uAgent wrapper is functional but running in local-only mode without a mailbox key:
- Agentverse registration requires a funded wallet address (for testnet or mainnet)
- The uagents SDK connects to the Almanac smart contract on the Fetch.ai blockchain to register the agent's endpoint
- In production, the agent would need a persistent hosting environment (a cloud VM or container) with a stable public endpoint rather than `127.0.0.1`
- Message schemas (`PipelineRequest` / `PipelineResponse`) would need to be published to the Agentverse schema registry so other agents can discover and invoke the pipeline without manual coordination
