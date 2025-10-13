"""Automation helpers for iteratively searching regression specifications.

This module implements a command line utility that mirrors a common
workflow when empirical researchers in economics search for regression
specifications that deliver stronger statistical significance for key
explanatory variables.  The workflow is based on the process described in
the project documentation and includes four main pieces:

1. Baseline regressions that only include the key explanatory variables.
2. Incremental addition of control variables, one at a time.
3. Moderation (interaction) checks where each focal explanatory variable is
   paired with a moderator.
4. Optional removal of the earliest years in the sample to evaluate whether
   early-period observations drive insignificant results.

The script is intentionally conservative: it does not select the "best"
model automatically.  Instead, it stores detailed regression diagnostics for
each specification so that the researcher can review them, interpret the
economic meaning, and avoid mechanical cherry-picking.

Example usage::

    python model_search.py \
        --data data/panel.csv \
        --config configs/spec_config.json \
        --output results/

The configuration file must be JSON and contain the fields documented in
``ConfigSchema``.  Results are saved as CSV and JSON files inside the output
directory together with a human-readable Markdown summary.
"""

from __future__ import annotations

import argparse
import json
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
import statsmodels.formula.api as smf


@dataclass
class ConfigSchema:
    """Configuration options required by the automation utility."""

    dependent: str
    main_predictors: Sequence[str]
    controls: Sequence[str] = field(default_factory=list)
    moderators: Sequence[str] = field(default_factory=list)
    year_variable: Optional[str] = None
    drop_earliest_years: Sequence[int] = field(default_factory=lambda: [0])
    model_type: str = "ols"

    @staticmethod
    def from_dict(config_dict: Dict[str, object]) -> "ConfigSchema":
        required = ["dependent", "main_predictors"]
        for key in required:
            if key not in config_dict:
                raise ValueError(f"Missing required config key: {key}")

        unsupported = set(config_dict).difference(
            {
                "dependent",
                "main_predictors",
                "controls",
                "moderators",
                "year_variable",
                "drop_earliest_years",
                "model_type",
            }
        )
        if unsupported:
            raise ValueError(
                "Unsupported config keys: " + ", ".join(sorted(unsupported))
            )

        model_type = config_dict.get("model_type", "ols")
        if model_type.lower() != "ols":
            raise ValueError(
                "Only OLS models are supported in this reference implementation."
            )

        return ConfigSchema(
            dependent=str(config_dict["dependent"]),
            main_predictors=list(config_dict["main_predictors"]),
            controls=list(config_dict.get("controls", [])),
            moderators=list(config_dict.get("moderators", [])),
            year_variable=config_dict.get("year_variable"),
            drop_earliest_years=list(config_dict.get("drop_earliest_years", [0])),
            model_type=model_type.lower(),
        )


@dataclass
class RegressionResult:
    """Structured container for regression diagnostics."""

    model_label: str
    formula: str
    dropped_years: int
    coefficient: str
    estimate: float
    p_value: float
    std_error: float
    significant_10: bool
    significant_5: bool
    significant_1: bool

    def as_dict(self) -> Dict[str, object]:
        return {
            "model_label": self.model_label,
            "formula": self.formula,
            "dropped_earliest_years": self.dropped_years,
            "coefficient": self.coefficient,
            "estimate": self.estimate,
            "std_error": self.std_error,
            "p_value": self.p_value,
            "significant_at_10pct": self.significant_10,
            "significant_at_5pct": self.significant_5,
            "significant_at_1pct": self.significant_1,
        }


def build_formula(dependent: str, rhs_terms: Iterable[str]) -> str:
    cleaned_terms = [term for term in rhs_terms if term]
    if not cleaned_terms:
        raise ValueError("At least one right-hand-side term is required")
    rhs = " + ".join(cleaned_terms)
    return f"{dependent} ~ {rhs}"


def run_regression(formula: str, data: pd.DataFrame) -> Tuple[str, Dict[str, Tuple[float, float, float]]]:
    """Fit an OLS regression and return coefficient statistics.

    The returned dictionary maps coefficient names to ``(estimate, std_error,
    p_value)`` tuples.  ``model_summary`` contains the statsmodels text summary
    for optional logging.
    """

    model = smf.ols(formula=formula, data=data).fit()
    summary_text = model.summary().as_text()
    coeff_stats = {
        name: (float(model.params[name]), float(model.bse[name]), float(model.pvalues[name]))
        for name in model.params.index
    }
    return summary_text, coeff_stats


def record_coefficients(
    results: List[RegressionResult],
    model_label: str,
    formula: str,
    dropped_years: int,
    coeff_stats: Dict[str, Tuple[float, float, float]],
    focus_terms: Sequence[str],
) -> None:
    for term in focus_terms:
        if term not in coeff_stats:
            # Skip silently so that interaction-only models do not break when
            # statsmodels drops collinear terms.
            continue
        estimate, std_error, p_value = coeff_stats[term]
        results.append(
            RegressionResult(
                model_label=model_label,
                formula=formula,
                dropped_years=dropped_years,
                coefficient=term,
                estimate=estimate,
                std_error=std_error,
                p_value=p_value,
                significant_10=p_value < 0.1,
                significant_5=p_value < 0.05,
                significant_1=p_value < 0.01,
            )
        )


def iteratively_drop_years(
    data: pd.DataFrame, year_var: str, drop_counts: Sequence[int]
) -> Dict[int, pd.DataFrame]:
    if not drop_counts:
        return {0: data}

    sorted_years = sorted(data[year_var].dropna().unique())
    frames: Dict[int, pd.DataFrame] = {}
    for drop_n in drop_counts:
        if drop_n <= 0:
            frames[0] = data
            continue
        if drop_n >= len(sorted_years):
            raise ValueError(
                "Cannot drop more years than exist in the dataset. "
                f"Attempted to drop {drop_n} of {len(sorted_years)} years."
            )
        threshold_years = sorted_years[drop_n:]
        frames[drop_n] = data[data[year_var].isin(threshold_years)].copy()
    if 0 not in frames:
        frames[0] = data
    return frames


def run_baseline_and_controls(
    cfg: ConfigSchema,
    data_variants: Dict[int, pd.DataFrame],
    results: List[RegressionResult],
) -> None:
    for drop_count, subset in data_variants.items():
        # Baseline: only main predictors
        formula = build_formula(cfg.dependent, cfg.main_predictors)
        _, coeff_stats = run_regression(formula, subset)
        record_coefficients(
            results,
            model_label="baseline_main_effects",
            formula=formula,
            dropped_years=drop_count,
            coeff_stats=coeff_stats,
            focus_terms=cfg.main_predictors,
        )

        if not cfg.controls:
            continue

        for end_idx in range(1, len(cfg.controls) + 1):
            active_controls = cfg.controls[:end_idx]
            rhs_terms = list(cfg.main_predictors) + list(active_controls)
            formula = build_formula(cfg.dependent, rhs_terms)
            _, coeff_stats = run_regression(formula, subset)
            label = f"incremental_controls_{end_idx}"
            record_coefficients(
                results,
                model_label=label,
                formula=formula,
                dropped_years=drop_count,
                coeff_stats=coeff_stats,
                focus_terms=list(cfg.main_predictors) + list(active_controls),
            )


def run_moderation_checks(
    cfg: ConfigSchema,
    data_variants: Dict[int, pd.DataFrame],
    results: List[RegressionResult],
) -> None:
    if not cfg.moderators:
        return

    for drop_count, subset in data_variants.items():
        for moderator in cfg.moderators:
            for predictor in cfg.main_predictors:
                interaction_term = f"{predictor}:{moderator}"
                rhs_terms = [predictor, moderator, f"{predictor}*{moderator}"]
                rhs_terms.extend(cfg.controls)
                formula = build_formula(cfg.dependent, rhs_terms)
                _, coeff_stats = run_regression(formula, subset)
                model_label = f"moderation_{predictor}_x_{moderator}"
                record_coefficients(
                    results,
                    model_label=model_label,
                    formula=formula,
                    dropped_years=drop_count,
                    coeff_stats=coeff_stats,
                    focus_terms=[predictor, moderator, interaction_term],
                )


def summarise_results(results: Sequence[RegressionResult]) -> str:
    if not results:
        return "No models were estimated."

    lines = ["# Model search summary", ""]
    grouped: Dict[str, List[RegressionResult]] = {}
    for item in results:
        grouped.setdefault(item.model_label, []).append(item)

    for label, group in sorted(grouped.items()):
        lines.append(f"## {label}")
        lines.append("|Coefficient|Drop earliest years|Estimate|Std. Error|p-value|Sig. 10%|Sig. 5%|Sig. 1%|")
        lines.append("|---|---|---|---|---|---|---|---|")
        for entry in sorted(group, key=lambda x: (x.dropped_years, x.coefficient)):
            lines.append(
                "|{coef}|{drop}|{est:.4f}|{se:.4f}|{pval:.4f}|{sig10}|{sig5}|{sig1}|".format(
                    coef=entry.coefficient,
                    drop=entry.dropped_years,
                    est=entry.estimate,
                    se=entry.std_error,
                    pval=entry.p_value,
                    sig10="✅" if entry.significant_10 else "",
                    sig5="✅" if entry.significant_5 else "",
                    sig1="✅" if entry.significant_1 else "",
                )
            )
        lines.append("")

    return "\n".join(lines)


def ensure_output_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_results(results: Sequence[RegressionResult], output_dir: Path) -> None:
    ensure_output_directory(output_dir)
    records = [entry.as_dict() for entry in results]
    df = pd.DataFrame.from_records(records)
    csv_path = output_dir / "regression_search_results.csv"
    json_path = output_dir / "regression_search_results.json"
    markdown_path = output_dir / "regression_search_summary.md"
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2)
    markdown_path.write_text(summarise_results(results), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Iteratively search for statistically significant regression models.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--data", type=Path, required=True, help="Path to the dataset (CSV format).")
    parser.add_argument(
        "--config", type=Path, required=True, help="Path to the JSON configuration file."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("regression_search_output"), help="Directory to store outputs."
    )
    return parser.parse_args()


def load_configuration(path: Path) -> ConfigSchema:
    config_dict = json.loads(path.read_text(encoding="utf-8"))
    return ConfigSchema.from_dict(config_dict)


def load_data(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def main() -> None:
    args = parse_args()
    config = load_configuration(args.config)
    data = load_data(args.data)

    if config.year_variable and config.year_variable not in data.columns:
        raise ValueError(
            textwrap.fill(
                f"Year variable '{config.year_variable}' is not present in the dataset."
            )
        )

    data_variants = (
        iteratively_drop_years(data, config.year_variable, config.drop_earliest_years)
        if config.year_variable
        else {0: data}
    )

    results: List[RegressionResult] = []
    run_baseline_and_controls(config, data_variants, results)
    run_moderation_checks(config, data_variants, results)
    save_results(results, args.output)

    print(f"Stored {len(results)} regression coefficient records in {args.output}.")


if __name__ == "__main__":
    main()
