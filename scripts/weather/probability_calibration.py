"""Leakage-safe binary probability calibration (Platt and isotonic).

Callers must pass a calibration partition distinct from model-training rows;
this module does not discover or silently reuse training data.
"""
from __future__ import annotations

import argparse, csv, math
from pathlib import Path

EPS = 1e-9

def _pairs(rows, probability_field="prediction", outcome_field="outcome"):
    pairs = []
    for row in rows:
        try:
            p = float(row[probability_field]); y = float(row[outcome_field])
            if math.isfinite(p) and 0 <= p <= 1 and y in (0, 1): pairs.append((min(1-EPS, max(EPS, p)), y))
        except (KeyError, TypeError, ValueError): continue
    return pairs

def fit_platt(rows, probability_field="prediction", outcome_field="outcome", ridge=1e-3):
    """Fit ``sigmoid(a*logit(p)+b)`` by deterministic Newton iterations."""
    pairs = _pairs(rows, probability_field, outcome_field)
    if len(pairs) < 2: return {"method": "platt", "a": 1.0, "b": 0.0, "training_rows": len(pairs), "fallback": True}
    x = [math.log(p/(1-p)) for p, _ in pairs]; a, b = 1.0, 0.0
    def objective(aa, bb):
        loss = 0.0
        for xi, (_, y) in zip(x, pairs):
            z = max(-35.0, min(35.0, aa*xi+bb))
            loss += math.log1p(math.exp(-z)) + (1-y)*z
        return loss + .5 * ridge * ((aa-1.0)**2 + bb*bb)
    current = objective(a, b)
    for _ in range(100):
        grad_a = grad_b = h_aa = h_ab = h_bb = 0.0
        for xi, y in zip(x, (y for _, y in pairs)):
            z = max(-35.0, min(35.0, a*xi+b)); q = 1/(1+math.exp(-z)); w = q*(1-q)
            grad_a += (q-y)*xi; grad_b += q-y; h_aa += w*xi*xi; h_ab += w*xi; h_bb += w
        grad_a += ridge * (a - 1.0); grad_b += ridge * b
        h_aa += ridge; h_bb += ridge; det = h_aa*h_bb-h_ab*h_ab
        if det <= 1e-12: break
        da = (h_bb*grad_a-h_ab*grad_b)/det; db = (-h_ab*grad_a+h_aa*grad_b)/det
        step = 1.0
        while step >= 1e-6:
            candidate_a = max(-20.0, min(20.0, a - step*da)); candidate_b = max(-20.0, min(20.0, b - step*db))
            if objective(candidate_a, candidate_b) <= current + 1e-12: break
            step *= .5
        if step < 1e-6: break
        a, b = candidate_a, candidate_b; current = objective(a, b)
        if max(abs(step*da), abs(step*db)) < 1e-8: break
    # Preserve the ordering of the base probability (a non-negative slope).
    a = max(0.0, a)
    return {"method": "platt", "a": a, "b": b, "training_rows": len(pairs), "fallback": False}

def apply_platt(probability, model):
    p = min(1-EPS, max(EPS, float(probability))); z = max(-35.0, min(35.0, model["a"]*math.log(p/(1-p))+model["b"]))
    return 1/(1+math.exp(-z))

def fit_beta(rows, probability_field="prediction", outcome_field="outcome", ridge=1e-3):
    """Fit beta calibration ``sigmoid(a log p + b log(1-p) + c)``."""
    pairs = _pairs(rows, probability_field, outcome_field)
    if len(pairs) < 3: return {"method": "beta", "a": 1.0, "b": -1.0, "c": 0.0, "training_rows": len(pairs), "fallback": True}
    features = [(math.log(p), math.log(1-p), 1.0) for p, _ in pairs]; params = [1.0, -1.0, 0.0]
    def objective(v):
        loss = 0.0
        for x, (_, y) in zip(features, pairs):
            z = max(-35.0, min(35.0, sum(a*b for a, b in zip(v, x))))
            loss += math.log1p(math.exp(-z)) + (1-y)*z
        return loss + .5*ridge*((v[0]-1)**2+(v[1]+1)**2+v[2]**2)
    current = objective(params)
    for _ in range(100):
        gradient = [ridge*(params[0]-1), ridge*(params[1]+1), ridge*params[2]]; h = [[0.0]*3 for _ in range(3)]
        for x, (_, y) in zip(features, pairs):
            z = max(-35.0, min(35.0, sum(a*b for a, b in zip(params, x)))); q = 1/(1+math.exp(-z)); w = q*(1-q)
            for i in range(3):
                gradient[i] += (q-y)*x[i]
                for j in range(3): h[i][j] += w*x[i]*x[j]
        for i in range(3): h[i][i] += ridge
        # Solve the 3x3 Newton system with Gaussian elimination.
        aug = [h[i][:] + [gradient[i]] for i in range(3)]
        for col in range(3):
            pivot = max(range(col, 3), key=lambda row: abs(aug[row][col]))
            if abs(aug[pivot][col]) < 1e-12: break
            aug[col], aug[pivot] = aug[pivot], aug[col]; scale = aug[col][col]
            aug[col] = [v/scale for v in aug[col]]
            for row in range(3):
                if row != col:
                    factor = aug[row][col]; aug[row] = [a-factor*b for a, b in zip(aug[row], aug[col])]
        step_vec = [aug[i][3] for i in range(3)]
        step = 1.0
        while step >= 1e-6:
            candidate = [max(-20.0, min(20.0, params[i]-step*step_vec[i])) for i in range(3)]
            if objective(candidate) <= current + 1e-12: break
            step *= .5
        if step < 1e-6: break
        params, current = candidate, objective(candidate)
        if max(abs(step*v) for v in step_vec) < 1e-8: break
    # Constrain the beta map to be monotone non-decreasing in the input p.
    # (a >= 0 and b <= 0 are the standard beta-calibration constraints.)
    params[0] = max(0.0, params[0]); params[1] = min(0.0, params[1])
    return {"method": "beta", "a": params[0], "b": params[1], "c": params[2], "training_rows": len(pairs), "fallback": False}

def apply_beta(probability, model):
    p = min(1-EPS, max(EPS, float(probability))); z = model["a"]*math.log(p) + model["b"]*math.log(1-p) + model["c"]
    z = max(-35.0, min(35.0, z)); return 1/(1+math.exp(-z))

def fit_isotonic(rows, probability_field="prediction", outcome_field="outcome"):
    values = sorted(_pairs(rows, probability_field, outcome_field))
    blocks = []
    for x, y in values:
        blocks.append([x, x, y, 1])
        while len(blocks) > 1 and blocks[-2][2]/blocks[-2][3] > blocks[-1][2]/blocks[-1][3]:
            right = blocks.pop(); left = blocks.pop(); blocks.append([left[0], right[1], left[2]+right[2], left[3]+right[3]])
    return {"method": "isotonic", "blocks": [[lo, hi, s/n] for lo, hi, s, n in blocks], "training_rows": len(values)}

def apply_isotonic(probability, model):
    p = float(probability); blocks = model.get("blocks", [])
    if not blocks: return p
    if p <= blocks[0][0]: return blocks[0][2]
    for lo, hi, value in blocks:
        if p <= hi: return value
    return blocks[-1][2]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--input", type=Path, required=True); parser.add_argument("--output", type=Path, required=True); parser.add_argument("--method", choices=("platt", "beta", "isotonic"), default="platt"); args = parser.parse_args()
    with args.input.open(newline="") as handle: rows = list(csv.DictReader(handle))
    model = fit_platt(rows) if args.method == "platt" else fit_beta(rows) if args.method == "beta" else fit_isotonic(rows); args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(__import__("json").dumps(model, indent=2, sort_keys=True) + "\n"); print(args.output)

if __name__ == "__main__": main()
