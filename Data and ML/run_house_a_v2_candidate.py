"""Build the HouseA_v2 candidate from controls and the excluded pilot only.

Confirmation outputs are retrospective diagnostics. The candidate parameters
are frozen now, before evaluation on new, untouched sessions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd

from experiment_config import load_experiment_config
from house_a_robustness import (
    _event_from_active,
    _write_json,
    bootstrap_false_alarm,
    calibrate_core,
    discover_sessions,
    full_leave_one_control_out,
    load_feature_set,
    parameter_sensitivity,
)
from unsupervised_models import calibrate_controls, score_session


RULES = (
    "full", "nh3_and_bme", "h2s_and_bme", "protein_only",
    "bme_only", "nh3_only", "h2s_only", "ch4_only",
)
CALIBRATION_IDENTITY_FIELDS = (
    "site_id", "pcb_design_id", "device_id", "container_id"
)


def _control_identity(paths: list[Path]) -> dict[str, str]:
    identity = {}
    metadata = [
        json.loads((path / "metadata.json").read_text(encoding="utf-8"))
        for path in paths
    ]
    for field in CALIBRATION_IDENTITY_FIELDS:
        values = {str(item.get(field, "")).strip() for item in metadata}
        if "" in values or len(values) != 1:
            raise ValueError(f"Candidate controls do not share a valid {field}: {values}")
        identity[field] = values.pop()
    return identity


def _detection(data: pd.DataFrame, rule: str) -> float | None:
    event = _event_from_active(data, rule)
    rows = data.loc[event]
    return None if rows.empty else float(rows["session_time_h"].iloc[0])


def select_rule(
    pilot_detail: pd.DataFrame,
    loo_control_details: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Evaluate candidate rules without reading confirmation outcomes."""
    rows = []
    for rule in RULES:
        pilot_time = _detection(pilot_detail, rule)
        control_times = {
            session_id: _detection(data, rule)
            for session_id, data in loo_control_details.items()
        }
        rows.append(
            {
                "rule": rule,
                "pilot_detected": pilot_time is not None,
                "pilot_detection_h": pilot_time,
                "loo_control_events": sum(value is not None for value in control_times.values()),
                "loo_control_detection_times_h": json.dumps(control_times),
                "eligible_from_development_data": (
                    pilot_time is not None
                    and all(value is None for value in control_times.values())
                    and rule in {"full", "nh3_and_bme", "h2s_and_bme"}
                ),
            }
        )
    return pd.DataFrame(rows)


def _score_rows(
    records: pd.DataFrame, calibration: dict, config: dict
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    rows, details = [], {}
    for item in records.itertuples(index=False):
        frame = load_feature_set(
            [item.path], config["aggregation_minutes"], config["baseline_minutes"]
        )
        detail, summary = score_session(frame, calibration, config)
        details[item.session_id] = detail
        rows.append(
            {
                "session_id": item.session_id,
                "session_role": item.session_role,
                "primary_event": summary["primary_event_detected"],
                "detection_time_h": summary["time_to_sustained_change_h"],
                "auc_0_8h": summary["auc_change_index_hours"],
                "maximum_index": summary["maximum_change_index"],
                "environment_outside_control_domain_fraction": summary.get(
                    "environment_outside_control_domain_fraction"
                ),
                "environment_domain_warning": summary.get("environment_domain_warning"),
                **{
                    f"index_{hour}h": summary["index_at_fixed_hours"].get(str(hour))
                    for hour in (1, 2, 4, 6, 8)
                },
            }
        )
    return pd.DataFrame(rows), details


def write_report(
    output: Path,
    selection: pd.DataFrame,
    results: pd.DataFrame,
    loo: pd.DataFrame,
    bootstrap: pd.DataFrame,
    sensitivity: pd.DataFrame,
) -> None:
    pilot = results.loc[results.session_role == "pilot"].iloc[0]
    confirmations = results.loc[results.session_role == "confirmation"]
    controls = results.loc[results.session_role == "control"]
    selected = selection.loc[selection.eligible_from_development_data, "rule"].tolist()
    block8 = bootstrap.loc[bootstrap.window_hours == 8]
    strict = int(sensitivity.retains_3_of_3_and_0_of_3.sum())
    report = f"""# HouseA_v2 candidate report

## Status

Frozen development candidate awaiting prospective validation. It must not
replace HouseA_v1 for claims about the completed confirmation experiments.

## Development-only rule selection

Candidate rules were evaluated using only the excluded pilot and three
leave-one-control-out controls. Confirmation outcomes were not inputs to the
selection calculation.

The analysts had already inspected the confirmation results before this
calculation was created, so this is not equivalent to blinded model selection.
That is why a new prospective experiment remains mandatory.

- Eligible multichannel rules: {', '.join(selected) or 'none'}
- Selected rule: H2S AND BME
- Pilot detection: {pilot.detection_time_h:.2f} h
- Leave-one-control-out events: {int(loo.held_out_control_event.sum())}/{len(loo)}

## Retrospective confirmation check

- Confirmations detected: {int(confirmations.primary_event.sum())}/{len(confirmations)}
- Detection times: {', '.join(f'{value:.2f} h' for value in confirmations.detection_time_h)}
- Full-calibration control events: {int(controls.primary_event.sum())}/{len(controls)}
- Minimum leave-one-control-out chicken/control AUC margin: {loo.auc_absolute_margin.min():.2f}

The continuous index and weights are unchanged from HouseA_v1. Only the Boolean
event rule changed, so AUC and displayed index values remain directly
comparable.

## Conditional false-alarm stress test

Eight-hour moving-block bootstrap rates range from
{100 * block8.false_session_rate.min():.2f}% to
{100 * block8.false_session_rate.max():.2f}% across the tested block lengths.
These are conditional simulations based on three controls, not a household
false-alarm guarantee.

## Candidate parameter sensitivity

{strict}/{len(sensitivity)} prespecified one-factor configurations retained all
three retrospective confirmation events and zero leave-one-control-out control
events. AUC separation remained positive in
{int((sensitivity.auc_absolute_margin > 0).sum())}/{len(sensitivity)} configurations.
This is retrospective robustness, not prospective validation.

## Environmental handling

Environmental compensation remains disabled. The previously tested RH/T model
did not improve held-out-control RMSE and all chicken trajectories left the
control environmental domain. HouseA_v2 therefore retains the original drift
correction and reports environmental-domain violations as diagnostic flags.

## Decision

The H2S-and-BME candidate removes the observed S005 cross-fitted event while
retaining the pilot and all three retrospective confirmations. Its parameters
are now frozen for the next prospective control and chicken sessions, but the
existing confirmation data cannot validate a rule developed after their
analysis.
"""
    (output / "HOUSE_A_V2_CANDIDATE_REPORT.md").write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--session-root", type=Path,
        default=Path("evaluation_output/full_stack_4runs_20260806/staged_sessions"),
    )
    parser.add_argument("--v1-config", type=Path, default=Path("configs/house_a_v1.json"))
    parser.add_argument(
        "--v1-calibration", type=Path,
        default=Path("evaluation_output/full_stack_4runs_20260806/model/control_calibration.joblib"),
    )
    parser.add_argument(
        "--candidate-config", type=Path,
        default=Path("configs/house_a_v2_candidate.json"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("evaluation_output/house_a_v2_candidate"),
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    v1 = load_experiment_config(args.v1_config)
    candidate = load_experiment_config(args.candidate_config)
    records = discover_sessions(args.session_root)
    controls_paths = records.loc[records.session_role == "control", "path"].tolist()
    confirmation_paths = records.loc[
        records.session_role == "confirmation", "path"
    ].tolist()

    # Development-only selection: excluded pilot plus cross-fitted controls.
    _, _, loo_control_details = full_leave_one_control_out(
        controls_paths, confirmation_paths, v1
    )
    pilot_record = records.loc[records.session_role == "pilot"].iloc[0]
    pilot_frame = load_feature_set(
        [pilot_record.path], v1["aggregation_minutes"], v1["baseline_minutes"]
    )
    pilot_detail, _ = score_session(
        pilot_frame, joblib.load(args.v1_calibration), v1
    )
    selection = select_rule(pilot_detail, loo_control_details)
    selection.to_csv(args.output / "development_rule_selection.csv", index=False)
    eligible = selection.loc[selection.eligible_from_development_data, "rule"].tolist()
    if eligible != ["h2s_and_bme"]:
        raise RuntimeError(f"Expected one development-eligible rule; got {eligible}")
    if candidate["cusum"]["primary_rule"] != "h2s_and_bme_voc":
        raise ValueError("Candidate config does not encode the selected H2S+BME rule")

    controls = load_feature_set(
        controls_paths, candidate["aggregation_minutes"], candidate["baseline_minutes"]
    )
    calibration = calibrate_controls(controls, candidate, random_state=42)
    calibration.update(_control_identity(controls_paths))
    loo_null = calibration.pop("loo_residuals")
    joblib.dump(calibration, args.output / "control_calibration_candidate.joblib")
    loo_null.to_csv(args.output / "control_loo_residuals_candidate.csv", index=False)
    _write_json(
        args.output / "control_calibration_candidate.json",
        {
            "analysis_version": candidate.get("analysis_version"),
            **{field: calibration[field] for field in CALIBRATION_IDENTITY_FIELDS},
            "control_sessions": calibration["control_sessions"],
            "loo_scales": calibration["scales"],
            "cusum_h": calibration["cusum_h"],
            "primary_rule": candidate["cusum"]["primary_rule"],
            "bootstrap_false_session_rates": calibration[
                "bootstrap_false_session_rates"
            ],
            "environmental_domain": calibration.get("environmental_domain"),
            "warning": "Frozen development candidate; prospective validation required.",
        },
    )
    results, _ = _score_rows(records, calibration, candidate)
    results.to_csv(args.output / "candidate_session_results.csv", index=False)

    loo, scales, _ = full_leave_one_control_out(
        controls_paths, confirmation_paths, candidate
    )
    loo.to_csv(args.output / "candidate_full_leave_one_control_out.csv", index=False)
    scales.to_csv(args.output / "candidate_loo_scales.csv", index=False)
    sensitivity = parameter_sensitivity(
        controls_paths, confirmation_paths, candidate
    )
    sensitivity.to_csv(
        args.output / "candidate_parameter_sensitivity.csv", index=False
    )
    core = calibrate_core(controls, candidate)
    bootstrap = bootstrap_false_alarm(core["loo"], candidate)
    bootstrap.to_csv(args.output / "candidate_bootstrap_false_alarm.csv", index=False)

    summary = {
        "analysis_version": candidate.get("analysis_version"),
        "status": candidate.get("analysis_status"),
        "parameters_frozen": candidate.get("parameters_frozen"),
        "selected_rule": candidate["cusum"]["primary_rule"],
        "selection_used_confirmation_outcomes": False,
        "development_eligible_rules": eligible,
        "pilot_detected": bool(
            results.loc[results.session_role == "pilot", "primary_event"].iloc[0]
        ),
        "loo_control_events": int(loo.held_out_control_event.sum()),
        "retrospective_confirmation_events": int(
            results.loc[results.session_role == "confirmation", "primary_event"].sum()
        ),
        "parameter_sensitivity_strict_passes": int(
            sensitivity.retains_3_of_3_and_0_of_3.sum()
        ),
        "parameter_sensitivity_configurations": len(sensitivity),
        "prospective_validation_required": True,
        "environmental_compensation_enabled": False,
    }
    _write_json(args.output / "candidate_summary.json", summary)
    (args.output / "config_used.json").write_text(
        json.dumps(candidate, indent=2), encoding="utf-8"
    )
    write_report(args.output, selection, results, loo, bootstrap, sensitivity)
    print(f"HouseA_v2 candidate outputs written to {args.output}")


if __name__ == "__main__":
    main()
