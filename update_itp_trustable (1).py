#!/usr/bin/env python3
"""
update_itp_trustable.py

Create a trustable HessFit/QM-MM torsion-refined GROMACS .itp file from
all data stored in ./data.

The script diagnoses:
  - missing QM/MM scan-energy CSV files
  - mismatched QM/MM point counts
  - incomplete Gaussian QM logs, if logs are present
  - failed Gaussian MM logs, if logs are present
  - topol.txt vs .itp bond consistency, if topol.txt is present
  - .xyz vs .itp atom-order consistency, if an .xyz file is present
  - whether each recommended scan torsion exists in the .itp

By default it updates ONLY scans that are trusted:
  - QM scan-energy CSV exists
  - MM scan-energy CSV exists
  - QM/MM point counts match
  - point count >= --expected-points
  - fit RMSE <= --rmse-max-kj, unless --allow-high-rmse is used

Typical usage:
  python update_itp_trustable.py --data ./data

Useful options:
  python update_itp_trustable.py --data ./data --base-itp LBAI_HessFit_updated.itp
  python update_itp_trustable.py --data ./data --allow-high-rmse
  python update_itp_trustable.py --data ./data --allow-incomplete
  python update_itp_trustable.py --data ./data --require-all

Expected data files:
  Required:
    - base .itp file
    - LBAI_torsion_refinement_candidates*.csv or equivalent
    - N_qm_scan_energy*.csv and N_mm_scan_energy*.csv for each scan N

  Optional but strongly recommended:
    - topol.txt
    - LBAI.xyz or any .xyz with matching atom order
    - N_qm.log and N_mm_*.log files
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterable

import numpy as np


HARTREE_TO_KCAL = 627.5094740631
KCAL_TO_KJ = 4.184


# -----------------------------
# Data classes
# -----------------------------

@dataclass
class Candidate:
    scan_idx: int
    torsion: Tuple[int, int, int, int]
    central_bond: Tuple[int, int]
    atom_names: str = ""
    atom_types: str = ""
    original_phase_deg: float = 180.0
    original_k_kj_mol: float = 0.0
    original_mult: int = 2
    raw_itp_line: str = ""


@dataclass
class ScanFit:
    scan_idx: int
    torsion: Tuple[int, int, int, int]
    central_bond: Tuple[int, int]
    qm_file: Optional[str]
    mm_file: Optional[str]
    n_qm: int
    n_mm: int
    n_used: int
    trusted: bool
    skip_reasons: List[str]
    multiplicity: int
    phase_deg: Optional[float]
    k_kj_mol: Optional[float]
    k_kcal_mol: Optional[float]
    rmse_kj_mol: Optional[float]
    rmse_kcal_mol: Optional[float]
    old_phase_deg: float
    old_k_kj_mol: float
    old_mult: int
    log_diagnostics: Dict


# -----------------------------
# File discovery
# -----------------------------

def version_score(path: Path) -> Tuple[int, float]:
    """
    Prefer corrected files such as 3_mm_scan_energy(1).csv over
    3_mm_scan_energy.csv. Then prefer newer mtime.
    """
    m = re.search(r"\((\d+)\)(?=\.[^.]+$)", path.name)
    version = int(m.group(1)) if m else 0
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return version, mtime


def choose_file(paths: Iterable[Path]) -> Optional[Path]:
    paths = list(paths)
    if not paths:
        return None
    return sorted(paths, key=version_score, reverse=True)[0]


def discover_base_itp(data_dir: Path, explicit: Optional[str]) -> Path:
    if explicit:
        p = data_dir / explicit
        if not p.exists():
            raise FileNotFoundError(f"Base ITP not found: {p}")
        return p

    priority = [
        "LBAI_HessFit_updated.itp",
        "LBAI_HessFit_scan_refined_fixed3_strict.itp",
        "LBAI_HessFit_scan_refined_conservative.itp",
        "LBAI(2).itp",
        "LBAI.itp",
    ]
    for name in priority:
        p = data_dir / name
        if p.exists():
            return p

    candidates = sorted(data_dir.glob("*.itp"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No .itp file found in {data_dir}")
    return candidates[0]


def discover_candidate_csv(data_dir: Path, explicit: Optional[str]) -> Path:
    if explicit:
        p = data_dir / explicit
        if not p.exists():
            raise FileNotFoundError(f"Candidate CSV not found: {p}")
        return p

    patterns = [
        "*torsion_refinement_candidates*.csv",
        "*scan_torsions*.csv",
    ]
    hits: List[Path] = []
    for pat in patterns:
        hits.extend(data_dir.glob(pat))
    hits = sorted(set(hits), key=lambda x: x.stat().st_mtime, reverse=True)

    if not hits:
        raise FileNotFoundError(
            f"No torsion candidate CSV found in {data_dir}. "
            "Expected something like LBAI_torsion_refinement_candidates.csv"
        )
    return hits[0]


def find_scan_energy_file(data_dir: Path, scan_idx: int, kind: str) -> Optional[Path]:
    """
    kind = 'qm' or 'mm'.
    Accepts:
      3_qm_scan_energy.csv
      3_qm_scan_energy(1).csv
    """
    paths = list(data_dir.glob(f"{scan_idx}_{kind}_scan_energy*.csv"))
    return choose_file(paths)


# -----------------------------
# Parsers
# -----------------------------

def to_int_list(text: str) -> Tuple[int, ...]:
    return tuple(int(float(x)) for x in re.findall(r"[-+]?\d+(?:\.\d+)?", str(text)))


def parse_candidates(path: Path) -> List[Candidate]:
    rows: List[Candidate] = []
    with path.open(newline="", errors="replace") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if "scan_torsion" not in row:
                raise ValueError(f"{path} lacks required column 'scan_torsion'")

            torsion = to_int_list(row.get("scan_torsion", ""))
            if len(torsion) != 4:
                raise ValueError(f"Bad scan_torsion in row {idx}: {row.get('scan_torsion')}")

            central = to_int_list(row.get("central_bond", ""))
            if len(central) != 2:
                central = (torsion[1], torsion[2])

            def fget(*names, default=None):
                for name in names:
                    if name in row and str(row[name]).strip() != "":
                        return row[name]
                return default

            phase = float(fget("itp_phi0_deg", "original_itp_phi0_deg", default=180.0))
            k = float(fget("itp_cp", "original_itp_cp_kj_mol", default=0.0))
            mult = int(float(fget("itp_mult", "original_itp_mult", default=2)))

            rows.append(
                Candidate(
                    scan_idx=idx,
                    torsion=tuple(torsion),
                    central_bond=tuple(central),
                    atom_names=str(fget("central_bond_atom_names", default="")),
                    atom_types=str(fget("central_bond_atom_types", default="")),
                    original_phase_deg=phase,
                    original_k_kj_mol=k,
                    original_mult=mult,
                    raw_itp_line=str(fget("raw_itp_line", default="")),
                )
            )
    return rows


def read_numeric_csv(path: Path) -> List[List[float]]:
    rows: List[List[float]] = []
    with path.open(errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # Supports comma, spaces, or tabs.
            parts = [x for x in re.split(r"[,\s]+", line) if x]
            vals = []
            ok = True
            for p in parts:
                try:
                    vals.append(float(p))
                except ValueError:
                    ok = False
                    break
            if ok and vals:
                rows.append(vals)
    return rows


def read_qm_scan(path: Path, unit: str = "kcal") -> Tuple[np.ndarray, np.ndarray]:
    rows = read_numeric_csv(path)
    if not rows:
        raise ValueError(f"No numeric rows in {path}")
    if len(rows[0]) < 2:
        raise ValueError(f"{path} must contain at least 2 columns: angle, energy")

    angles = np.array([r[0] for r in rows], dtype=float)
    e = np.array([r[1] for r in rows], dtype=float)

    unit = unit.lower()
    if unit == "kcal":
        rel_kcal = e
    elif unit == "kj":
        rel_kcal = e / KCAL_TO_KJ
    elif unit == "hartree":
        rel_kcal = (e - np.min(e)) * HARTREE_TO_KCAL
    else:
        raise ValueError(f"Unsupported QM unit: {unit}")

    return angles, rel_kcal


def read_mm_scan(path: Path, unit: str = "hartree") -> Tuple[np.ndarray, np.ndarray]:
    rows = read_numeric_csv(path)
    if not rows:
        raise ValueError(f"No numeric rows in {path}")

    # Usually get_mm_energy.py writes: point_index, energy_hartree
    if len(rows[0]) >= 2:
        point = np.array([r[0] for r in rows], dtype=float)
        e = np.array([r[1] for r in rows], dtype=float)
    else:
        point = np.arange(len(rows), dtype=float)
        e = np.array([r[0] for r in rows], dtype=float)

    unit = unit.lower()
    if unit == "auto":
        # get_mm_energy.py normally produces Hartree. Large absolute values are Hartree-like.
        unit = "hartree" if np.nanmax(np.abs(e)) > 50 else "kcal"

    if unit == "hartree":
        rel_kcal = (e - np.min(e)) * HARTREE_TO_KCAL
    elif unit == "kcal":
        rel_kcal = e - np.min(e)
    elif unit == "kj":
        rel_kcal = (e - np.min(e)) / KCAL_TO_KJ
    else:
        raise ValueError(f"Unsupported MM unit: {unit}")

    return point, rel_kcal


def parse_itp_sections(lines: List[str]) -> Dict[str, List[Tuple[int, str]]]:
    sections: Dict[str, List[Tuple[int, str]]] = {}
    current = None
    for lineno, line in enumerate(lines, start=1):
        s = line.strip()
        if s.startswith("[") and "]" in s:
            current = s.split("]", 1)[0].strip("[]").strip().lower()
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append((lineno, line))
    return sections


def parse_itp_atoms(lines: List[str]) -> List[Dict]:
    atoms = []
    sections = parse_itp_sections(lines)
    for lineno, line in sections.get("atoms", []):
        main = line.split(";", 1)[0].split()
        if len(main) < 7:
            continue
        try:
            nr = int(main[0])
            atom_type = main[1]
            atom_name = main[4]
            charge = float(main[6])
            mass = float(main[7]) if len(main) > 7 else None
        except Exception:
            continue
        atoms.append(
            {
                "nr": nr,
                "type": atom_type,
                "atom": atom_name,
                "charge": charge,
                "mass": mass,
                "element": infer_element(mass, atom_name, atom_type),
            }
        )
    atoms.sort(key=lambda x: x["nr"])
    return atoms


def infer_element(mass: Optional[float], atom_name: str, atom_type: str = "") -> str:
    if mass is not None:
        if abs(mass - 1.008) < 0.25:
            return "H"
        if abs(mass - 12.011) < 0.7:
            return "C"
        if abs(mass - 14.007) < 0.7:
            return "N"
        if abs(mass - 15.999) < 0.7:
            return "O"
        if abs(mass - 32.06) < 1.0:
            return "S"
        if abs(mass - 30.974) < 1.0:
            return "P"
    txt = (atom_name or atom_type).strip().lstrip("0123456789")
    if not txt:
        return "X"
    two = txt[:2].capitalize()
    if two in {"Cl", "Br", "Si", "Na", "Li", "Mg", "Ca", "Fe", "Zn", "Cu", "Mn", "Co", "Ni", "Al", "Se"}:
        return two
    return txt[0].upper()


def parse_itp_bonds(lines: List[str]) -> set:
    bonds = set()
    sections = parse_itp_sections(lines)
    for _, line in sections.get("bonds", []):
        main = line.split(";", 1)[0].split()
        if len(main) < 2:
            continue
        try:
            i, j = int(main[0]), int(main[1])
            bonds.add(tuple(sorted((i, j))))
        except Exception:
            pass
    return bonds


def parse_topol_bonds(path: Path) -> set:
    lines = [x.strip() for x in path.read_text(errors="replace").splitlines() if x.strip()]
    if not lines:
        return set()
    n = int(lines[0].split()[0])
    bonds = set()
    for line in lines[1:1+n]:
        p = line.split()
        if len(p) >= 2:
            bonds.add(tuple(sorted((int(p[0]), int(p[1])))))
    return bonds


def parse_xyz_elements(path: Path) -> List[str]:
    lines = path.read_text(errors="replace").splitlines()
    if not lines:
        return []
    nat = int(lines[0].split()[0])
    elems = []
    for line in lines[2:2+nat]:
        p = line.split()
        if p:
            elems.append(p[0].capitalize())
    return elems


# -----------------------------
# Diagnostics
# -----------------------------

def gaussian_log_summary(path: Path) -> Dict:
    if not path.exists():
        return {"exists": False}
    text = path.read_text(errors="replace")
    return {
        "exists": True,
        "normal_termination": "Normal termination" in text,
        "error_termination": "Error termination" in text,
        "optimization_completed_count": text.count("Optimization completed"),
        "optimization_stopped_count": text.count("Optimization stopped"),
        "scf_failure": ("Convergence failure" in text or "Convergence criterion not met" in text),
        "mm_function_not_complete": "MM function not complete" in text,
        "undefined_terms": len(re.findall(r"undefined", text, flags=re.I)),
    }


def scan_log_diagnostics(data_dir: Path, idx: int) -> Dict:
    qm_logs = sorted(data_dir.glob(f"{idx}_qm*.log"))
    mm_logs = sorted(data_dir.glob(f"{idx}_mm_*.log"))

    qm = [gaussian_log_summary(p) | {"file": p.name} for p in qm_logs]
    mm = [gaussian_log_summary(p) | {"file": p.name} for p in mm_logs]

    return {
        "qm_logs_found": len(qm_logs),
        "mm_logs_found": len(mm_logs),
        "qm_logs": qm,
        "mm_logs": mm,
        "mm_failed_logs": [
            x for x in mm if x.get("error_termination") or not x.get("normal_termination", False)
        ],
    }


def global_diagnostics(data_dir: Path, itp_path: Path, candidates: List[Candidate]) -> Dict:
    lines = itp_path.read_text(errors="replace").splitlines()
    itp_atoms = parse_itp_atoms(lines)
    itp_bonds = parse_itp_bonds(lines)

    diag = {
        "itp_atom_count": len(itp_atoms),
        "itp_bond_count": len(itp_bonds),
        "topol_check": None,
        "xyz_check": None,
        "candidate_central_bond_check": [],
    }

    topol_path = choose_file(list(data_dir.glob("topol*.txt")))
    if topol_path:
        topol_bonds = parse_topol_bonds(topol_path)
        missing_in_itp = sorted(topol_bonds - itp_bonds)
        extra_in_itp = sorted(itp_bonds - topol_bonds)
        diag["topol_check"] = {
            "file": topol_path.name,
            "topol_bond_count": len(topol_bonds),
            "itp_bond_count": len(itp_bonds),
            "missing_in_itp_count": len(missing_in_itp),
            "extra_in_itp_count": len(extra_in_itp),
            "missing_in_itp_first20": missing_in_itp[:20],
            "extra_in_itp_first20": extra_in_itp[:20],
        }
        for cand in candidates:
            cb = tuple(sorted(cand.central_bond))
            diag["candidate_central_bond_check"].append(
                {
                    "scan_idx": cand.scan_idx,
                    "central_bond": list(cand.central_bond),
                    "in_topol_bonds": cb in topol_bonds,
                    "in_itp_bonds": cb in itp_bonds,
                }
            )

    xyz_path = choose_file(list(data_dir.glob("*.xyz")))
    if xyz_path and itp_atoms:
        xyz_elems = parse_xyz_elements(xyz_path)
        itp_elems = [a["element"].capitalize() for a in itp_atoms]
        mismatches = []
        for i, (ie, xe) in enumerate(zip(itp_elems, xyz_elems), start=1):
            if ie != xe:
                mismatches.append({"index": i, "itp": ie, "xyz": xe})
        diag["xyz_check"] = {
            "file": xyz_path.name,
            "xyz_atom_count": len(xyz_elems),
            "itp_atom_count": len(itp_atoms),
            "element_mismatch_count": len(mismatches),
            "element_mismatches_first20": mismatches[:20],
        }

    return diag


# -----------------------------
# Fit and update
# -----------------------------

def fit_one_term(angle_deg: np.ndarray, target_kcal: np.ndarray, mult: int) -> Tuple[float, float, float, float]:
    """
    Fit target = C + A cos(n phi) + B sin(n phi).

    Convert to GROMACS function 1:
      V = k * (1 + cos(n phi - phase))

    Constant terms do not affect the torsional force, so:
      k = sqrt(A^2 + B^2)
      phase = atan2(B, A)
    """
    phi = np.deg2rad(angle_deg)
    X = np.column_stack([np.ones(len(phi)), np.cos(mult * phi), np.sin(mult * phi)])
    coef, *_ = np.linalg.lstsq(X, target_kcal, rcond=None)
    pred = X @ coef
    A, B = float(coef[1]), float(coef[2])
    k_kcal = math.hypot(A, B)
    phase_deg = math.degrees(math.atan2(B, A)) % 360.0
    rmse_kcal = float(np.sqrt(np.mean((target_kcal - pred) ** 2)))
    return phase_deg, k_kcal, rmse_kcal, float(coef[0])


def fit_scan(
    data_dir: Path,
    cand: Candidate,
    args,
) -> ScanFit:
    qm_file = find_scan_energy_file(data_dir, cand.scan_idx, "qm")
    mm_file = find_scan_energy_file(data_dir, cand.scan_idx, "mm")
    reasons = []

    if qm_file is None:
        reasons.append("missing QM scan-energy CSV")
    if mm_file is None:
        reasons.append("missing MM scan-energy CSV")

    log_diag = scan_log_diagnostics(data_dir, cand.scan_idx)

    if qm_file is None or mm_file is None:
        return ScanFit(
            scan_idx=cand.scan_idx, torsion=cand.torsion, central_bond=cand.central_bond,
            qm_file=qm_file.name if qm_file else None, mm_file=mm_file.name if mm_file else None,
            n_qm=0, n_mm=0, n_used=0, trusted=False, skip_reasons=reasons,
            multiplicity=cand.original_mult, phase_deg=None, k_kj_mol=None, k_kcal_mol=None,
            rmse_kj_mol=None, rmse_kcal_mol=None,
            old_phase_deg=cand.original_phase_deg, old_k_kj_mol=cand.original_k_kj_mol,
            old_mult=cand.original_mult, log_diagnostics=log_diag,
        )

    try:
        qm_angle, qm_rel = read_qm_scan(qm_file, unit=args.qm_unit)
        _, mm_rel = read_mm_scan(mm_file, unit=args.mm_unit)
    except Exception as exc:
        reasons.append(f"failed to read scan-energy CSV: {exc}")
        return ScanFit(
            scan_idx=cand.scan_idx, torsion=cand.torsion, central_bond=cand.central_bond,
            qm_file=qm_file.name, mm_file=mm_file.name,
            n_qm=0, n_mm=0, n_used=0, trusted=False, skip_reasons=reasons,
            multiplicity=cand.original_mult, phase_deg=None, k_kj_mol=None, k_kcal_mol=None,
            rmse_kj_mol=None, rmse_kcal_mol=None,
            old_phase_deg=cand.original_phase_deg, old_k_kj_mol=cand.original_k_kj_mol,
            old_mult=cand.original_mult, log_diagnostics=log_diag,
        )

    n_qm, n_mm = len(qm_angle), len(mm_rel)
    n_used = min(n_qm, n_mm)

    if n_qm != n_mm:
        reasons.append(f"QM/MM point-count mismatch: QM={n_qm}, MM={n_mm}")
    if n_used < args.expected_points:
        reasons.append(f"too few usable points: {n_used} < expected {args.expected_points}")

    if args.allow_incomplete:
        fit_n = n_used
    else:
        fit_n = n_used if n_qm == n_mm else 0

    if fit_n < 4:
        reasons.append("not enough points to fit")
        trusted = False
        return ScanFit(
            scan_idx=cand.scan_idx, torsion=cand.torsion, central_bond=cand.central_bond,
            qm_file=qm_file.name, mm_file=mm_file.name,
            n_qm=n_qm, n_mm=n_mm, n_used=n_used, trusted=trusted, skip_reasons=reasons,
            multiplicity=cand.original_mult, phase_deg=None, k_kj_mol=None, k_kcal_mol=None,
            rmse_kj_mol=None, rmse_kcal_mol=None,
            old_phase_deg=cand.original_phase_deg, old_k_kj_mol=cand.original_k_kj_mol,
            old_mult=cand.original_mult, log_diagnostics=log_diag,
        )

    angle = qm_angle[:fit_n]
    target = qm_rel[:fit_n] - mm_rel[:fit_n]

    if args.fit_mult == "original":
        mult = cand.original_mult
    elif args.fit_mult == "best":
        best = None
        for m in range(1, args.max_mult + 1):
            phase, k_kcal, rmse_kcal, _ = fit_one_term(angle, target, m)
            item = (rmse_kcal, m, phase, k_kcal)
            if best is None or item[0] < best[0]:
                best = item
        assert best is not None
        _, mult, phase_deg, k_kcal = best
        rmse_kcal = best[0]
    else:
        mult = int(args.fit_mult)

    if args.fit_mult != "best":
        phase_deg, k_kcal, rmse_kcal, _ = fit_one_term(angle, target, mult)

    k_kj = k_kcal * KCAL_TO_KJ
    rmse_kj = rmse_kcal * KCAL_TO_KJ

    if rmse_kj > args.rmse_max_kj:
        reasons.append(f"high fit RMSE: {rmse_kj:.3f} kJ/mol > limit {args.rmse_max_kj:.3f}")
    if k_kj > args.k_max_kj:
        reasons.append(f"large fitted k: {k_kj:.3f} kJ/mol > limit {args.k_max_kj:.3f}")

    trusted = True
    if not args.allow_incomplete and n_qm != n_mm:
        trusted = False
    if n_used < args.expected_points:
        trusted = False
    if not args.allow_high_rmse and rmse_kj > args.rmse_max_kj:
        trusted = False
    if k_kj > args.k_max_kj:
        trusted = False

    return ScanFit(
        scan_idx=cand.scan_idx,
        torsion=cand.torsion,
        central_bond=cand.central_bond,
        qm_file=qm_file.name,
        mm_file=mm_file.name,
        n_qm=n_qm,
        n_mm=n_mm,
        n_used=fit_n,
        trusted=trusted,
        skip_reasons=reasons,
        multiplicity=mult,
        phase_deg=phase_deg,
        k_kj_mol=k_kj,
        k_kcal_mol=k_kcal,
        rmse_kj_mol=rmse_kj,
        rmse_kcal_mol=rmse_kcal,
        old_phase_deg=cand.original_phase_deg,
        old_k_kj_mol=cand.original_k_kj_mol,
        old_mult=cand.original_mult,
        log_diagnostics=log_diag,
    )


def is_dihedral_tokens(tokens: List[str]) -> bool:
    if len(tokens) < 8:
        return False
    try:
        int(tokens[0]); int(tokens[1]); int(tokens[2]); int(tokens[3])
        int(float(tokens[4]))
        float(tokens[5]); float(tokens[6]); int(float(tokens[7]))
        return True
    except Exception:
        return False


def update_itp(itp_path: Path, out_path: Path, fits: List[ScanFit], match_reversed: bool = True) -> List[Dict]:
    trusted = [x for x in fits if x.trusted and x.phase_deg is not None and x.k_kj_mol is not None]
    fit_by_torsion: Dict[Tuple[int, int, int, int], ScanFit] = {}
    for f in trusted:
        fit_by_torsion[f.torsion] = f
        if match_reversed:
            fit_by_torsion[tuple(reversed(f.torsion))] = f

    lines = itp_path.read_text(errors="replace").splitlines()
    current_section = None
    output_lines = []
    changes = []

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()

        if stripped.startswith("[") and "]" in stripped:
            current_section = stripped.split("]", 1)[0].strip("[]").strip().lower()
            output_lines.append(line)
            continue

        if current_section == "dihedrals":
            main = line.split(";", 1)[0]
            tokens = main.split()

            if is_dihedral_tokens(tokens):
                torsion = tuple(int(tokens[i]) for i in range(4))
                funct = int(float(tokens[4]))

                # Skip likely impropers.
                if funct != 2 and torsion in fit_by_torsion:
                    f = fit_by_torsion[torsion]
                    old_phase = float(tokens[5])
                    old_k = float(tokens[6])
                    old_mult = int(float(tokens[7]))

                    new_line = (
                        f"{torsion[0]:6d}{torsion[1]:6d}{torsion[2]:6d}{torsion[3]:6d}"
                        f"{funct:6d}{f.phase_deg:12.4f}{f.k_kj_mol:12.5f}{f.multiplicity:6d}"
                        f"   ; trusted QM/MM HessFit scan={f.scan_idx} "
                        f"central={f.central_bond[0]}-{f.central_bond[1]} "
                        f"RMSE={f.rmse_kj_mol:.2f} kJ/mol"
                    )
                    output_lines.append(new_line)
                    changes.append(
                        {
                            "scan_idx": f.scan_idx,
                            "line_no": line_no,
                            "torsion": " ".join(map(str, torsion)),
                            "central_bond": f"{f.central_bond[0]} {f.central_bond[1]}",
                            "old_phase_deg": old_phase,
                            "old_k_kj_mol": old_k,
                            "old_mult": old_mult,
                            "new_phase_deg": f.phase_deg,
                            "new_k_kj_mol": f.k_kj_mol,
                            "new_mult": f.multiplicity,
                            "rmse_kj_mol": f.rmse_kj_mol,
                        }
                    )
                    continue

        output_lines.append(line)

    out_path.write_text("\n".join(output_lines) + "\n")
    return changes


def write_csv(path: Path, rows: List[Dict]) -> None:
    if not rows:
        path.write_text("")
        return
    keys = sorted({k for row in rows for k in row.keys()})
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def write_fit_csv(path: Path, fits: List[ScanFit]) -> None:
    rows = []
    for f in fits:
        row = asdict(f)
        row["torsion"] = " ".join(map(str, f.torsion))
        row["central_bond"] = " ".join(map(str, f.central_bond))
        row["skip_reasons"] = " | ".join(f.skip_reasons)
        row.pop("log_diagnostics", None)
        rows.append(row)
    write_csv(path, rows)


def write_report(path: Path, args, base_itp, candidate_csv, global_diag, fits, changes, skipped) -> None:
    lines = []
    lines.append("Trustable HessFit/QM-MM .itp update report")
    lines.append("=" * 64)
    lines.append("")
    lines.append(f"Data directory: {args.data}")
    lines.append(f"Base ITP: {base_itp.name}")
    lines.append(f"Candidate CSV: {candidate_csv.name}")
    lines.append(f"QM unit: {args.qm_unit}")
    lines.append(f"MM unit: {args.mm_unit}")
    lines.append(f"Fit multiplicity mode: {args.fit_mult}")
    lines.append(f"Expected points per scan: {args.expected_points}")
    lines.append("")
    lines.append("Global checks:")
    lines.append(f"  ITP atoms: {global_diag.get('itp_atom_count')}")
    lines.append(f"  ITP bonds: {global_diag.get('itp_bond_count')}")
    if global_diag.get("topol_check"):
        t = global_diag["topol_check"]
        lines.append(f"  topol file: {t['file']}")
        lines.append(f"  topol bonds: {t['topol_bond_count']}")
        lines.append(f"  topol missing in ITP: {t['missing_in_itp_count']}")
        lines.append(f"  ITP extra vs topol: {t['extra_in_itp_count']}")
    else:
        lines.append("  topol check: no topol*.txt found")
    if global_diag.get("xyz_check"):
        x = global_diag["xyz_check"]
        lines.append(f"  xyz file: {x['file']}")
        lines.append(f"  xyz atoms: {x['xyz_atom_count']}")
        lines.append(f"  element-order mismatches: {x['element_mismatch_count']}")
    else:
        lines.append("  xyz check: no .xyz file found")
    lines.append("")

    lines.append("Per-scan diagnostics:")
    for f in fits:
        status = "TRUSTED/UPDATED" if f.trusted else "SKIPPED"
        lines.append(
            f"  scan {f.scan_idx}: D {' '.join(map(str, f.torsion))}, "
            f"central {f.central_bond[0]}-{f.central_bond[1]}, "
            f"QM={f.n_qm}, MM={f.n_mm}, used={f.n_used}, status={status}"
        )
        lines.append(f"    QM file: {f.qm_file}")
        lines.append(f"    MM file: {f.mm_file}")
        if f.phase_deg is not None:
            lines.append(
                f"    fit: phase={f.phase_deg:.4f} deg, "
                f"k={f.k_kj_mol:.5f} kJ/mol, mult={f.multiplicity}, "
                f"RMSE={f.rmse_kj_mol:.4f} kJ/mol"
            )
        if f.skip_reasons:
            for reason in f.skip_reasons:
                lines.append(f"    warning: {reason}")

        qm_logs = f.log_diagnostics.get("qm_logs", [])
        mm_failed = f.log_diagnostics.get("mm_failed_logs", [])
        if qm_logs:
            for q in qm_logs[:3]:
                lines.append(
                    f"    QM log {q['file']}: normal={q.get('normal_termination')}, "
                    f"completed={q.get('optimization_completed_count')}, "
                    f"stopped={q.get('optimization_stopped_count')}, "
                    f"error={q.get('error_termination')}"
                )
        if mm_failed:
            lines.append(f"    failed/non-normal MM logs: {len(mm_failed)}")
            for m in mm_failed[:5]:
                lines.append(
                    f"      {m['file']}: normal={m.get('normal_termination')}, "
                    f"error={m.get('error_termination')}, "
                    f"MM incomplete={m.get('mm_function_not_complete')}, "
                    f"undefined terms={m.get('undefined_terms')}"
                )
    lines.append("")

    lines.append(f"Updated torsion lines: {len(changes)}")
    lines.append(f"Skipped scans: {len(skipped)}")
    if skipped:
        lines.append("Skipped scan indices: " + ", ".join(str(x.scan_idx) for x in skipped))
    lines.append("")
    if args.require_all and skipped:
        lines.append("NOTE: --require-all was requested. The script would fail before writing if untrusted scans remained.")
    lines.append("")

    lines.append("Recommended interpretation:")
    lines.append("  Use the generated .itp only if all chemically important scans are TRUSTED/UPDATED.")
    lines.append("  If a scan is skipped due to mismatch, rerun or re-extract that scan before production MD.")
    path.write_text("\n".join(lines) + "\n")


# -----------------------------
# Main
# -----------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a trustable HessFit/QM-MM torsion-refined GROMACS .itp from ./data."
    )
    parser.add_argument("--data", default="./data", help="Directory containing all input data files.")
    parser.add_argument("--base-itp", default=None, help="Base .itp filename inside --data.")
    parser.add_argument("--candidates", default=None, help="Torsion candidate CSV filename inside --data.")
    parser.add_argument("--out-dir", default=None, help="Output directory. Default: ./data/itp_update_output")
    parser.add_argument("--output-itp", default="LBAI_trustable_scan_refined.itp")
    parser.add_argument("--qm-unit", default="kcal", choices=["kcal", "kj", "hartree"])
    parser.add_argument("--mm-unit", default="hartree", choices=["hartree", "kcal", "kj", "auto"])
    parser.add_argument("--expected-points", type=int, default=11)
    parser.add_argument("--fit-mult", default="original", help="'original', 'best', or an integer multiplicity.")
    parser.add_argument("--max-mult", type=int, default=6, help="Used only when --fit-mult best.")
    parser.add_argument("--rmse-max-kj", type=float, default=15.0)
    parser.add_argument("--k-max-kj", type=float, default=250.0)
    parser.add_argument("--allow-high-rmse", action="store_true", help="Allow update even when RMSE is high.")
    parser.add_argument("--allow-incomplete", action="store_true", help="Allow update when QM/MM point counts mismatch.")
    parser.add_argument("--require-all", action="store_true", help="Abort unless every candidate scan is trusted.")
    parser.add_argument("--match-reversed", action="store_true", default=True, help="Also match reversed torsion order in .itp.")
    parser.add_argument("--no-backup", action="store_true", help="Do not copy the base ITP to output as backup.")
    args = parser.parse_args()

    data_dir = Path(args.data).resolve()
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    out_dir = Path(args.out_dir).resolve() if args.out_dir else data_dir / "itp_update_output"
    out_dir.mkdir(parents=True, exist_ok=True)

    base_itp = discover_base_itp(data_dir, args.base_itp)
    candidate_csv = discover_candidate_csv(data_dir, args.candidates)
    candidates = parse_candidates(candidate_csv)

    global_diag = global_diagnostics(data_dir, base_itp, candidates)
    fits = [fit_scan(data_dir, cand, args) for cand in candidates]

    skipped = [x for x in fits if not x.trusted]
    if args.require_all and skipped:
        # Still write diagnostics before aborting.
        write_fit_csv(out_dir / "scan_fit_results.csv", fits)
        write_report(out_dir / "diagnostics_report.txt", args, base_itp, candidate_csv, global_diag, fits, [], skipped)
        (out_dir / "manifest.json").write_text(json.dumps({
            "status": "aborted",
            "reason": "require_all requested but some scans are untrusted",
            "skipped_scan_indices": [x.scan_idx for x in skipped],
        }, indent=2) + "\n")
        raise SystemExit(
            f"Aborted: --require-all set, but skipped/untrusted scans remain: "
            f"{[x.scan_idx for x in skipped]}. See {out_dir / 'diagnostics_report.txt'}"
        )

    out_itp = out_dir / args.output_itp
    changes = update_itp(base_itp, out_itp, fits, match_reversed=args.match_reversed)

    if not args.no_backup:
        shutil.copy2(base_itp, out_dir / (base_itp.name + ".bak"))

    write_fit_csv(out_dir / "scan_fit_results.csv", fits)
    write_csv(out_dir / "itp_parameter_changes.csv", changes)
    write_report(out_dir / "diagnostics_report.txt", args, base_itp, candidate_csv, global_diag, fits, changes, skipped)

    manifest = {
        "status": "completed",
        "data_dir": str(data_dir),
        "base_itp": base_itp.name,
        "candidate_csv": candidate_csv.name,
        "output_itp": str(out_itp),
        "updated_torsion_lines": len(changes),
        "trusted_scan_indices": [x.scan_idx for x in fits if x.trusted],
        "skipped_scan_indices": [x.scan_idx for x in skipped],
        "outputs": {
            "updated_itp": str(out_itp),
            "diagnostics_report": str(out_dir / "diagnostics_report.txt"),
            "scan_fit_results": str(out_dir / "scan_fit_results.csv"),
            "itp_parameter_changes": str(out_dir / "itp_parameter_changes.csv"),
        }
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print("Completed trustable .itp update.")
    print(f"  Output ITP: {out_itp}")
    print(f"  Updated torsion lines: {len(changes)}")
    print(f"  Trusted scans: {[x.scan_idx for x in fits if x.trusted]}")
    print(f"  Skipped scans: {[x.scan_idx for x in skipped]}")
    print(f"  Diagnostics: {out_dir / 'diagnostics_report.txt'}")
    print(f"  Fit results: {out_dir / 'scan_fit_results.csv'}")

    if skipped:
        print("\nWARNING: Some scans were skipped. Inspect diagnostics_report.txt before production MD.")


if __name__ == "__main__":
    main()
