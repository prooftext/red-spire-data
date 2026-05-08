from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT / "ml" / "models"


def _run(module: str, *args: str) -> None:
    cmd = [sys.executable, "-m", module, *args]
    subprocess.run(cmd, cwd=ROOT, check=True)


def retrain_from_db(mode_f1_tolerance: float = 0.02, eer_tolerance: float = 0.02) -> dict:
    if not os.getenv("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required for retrain_from_db")

    from ml.scripts.export_prod_data import export_prod_data

    export_summary = export_prod_data()

    _run("ml.src.dataset_builders", "--build-all")
    _run("ml.src.train_mode_classifier")
    _run("ml.src.train_user_encoder")
    _run("ml.src.train_multitask")
    _run("ml.src.evaluate")

    report = json.loads((MODELS_DIR / "eval_report.json").read_text(encoding="utf-8"))
    mode_f1 = float(report["mode_classification"]["macro_f1"])
    eer = float(report["user_verification"]["eer"])

    prev_path = MODELS_DIR / "last_deployed_metrics.json"
    publish = True
    reason = "first_model"
    if prev_path.exists():
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
        prev_f1 = float(prev.get("mode_macro_f1", 0.0))
        prev_eer = float(prev.get("user_eer", 1.0))

        if mode_f1 < (prev_f1 - mode_f1_tolerance):
            publish = False
            reason = "mode_macro_f1_regression"
        if eer > (prev_eer + eer_tolerance):
            publish = False
            reason = "user_eer_regression"

    if publish:
        _run("ml.src.export_model")
        prev_path.write_text(
            json.dumps({"mode_macro_f1": mode_f1, "user_eer": eer}, indent=2),
            encoding="utf-8",
        )

    out = {
        "export_summary": export_summary,
        "mode_macro_f1": mode_f1,
        "user_eer": eer,
        "published": publish,
        "decision_reason": reason,
    }
    (MODELS_DIR / "retrain_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(json.dumps(retrain_from_db(), indent=2))
