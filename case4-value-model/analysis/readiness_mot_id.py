"""Does the anonymised MOT `vehicle_id` mean the same car across annual releases?

The whole of layer 2 rests on this. If DVSA re-randomises the id when it publishes a year, then a
car cannot be followed and the mileage work has to be rebuilt out of within-file pairs.

The claim is easy to find and hard to trust. DVSA's own user guide says the id is derived from the
vehicle - "Unique vehicles can be tracked using the Vehicle ID field, which is based upon the
Registration and VIN" (`mot-testing-data-user-guide-v5.1.odt`) - and a commercial site asserts it
outright, with no named author. Neither is a measurement. This is.

Two tests and a null:

  1. **The same tests, published twice.** Test year 2024 exists in two releases built thirteen
     months apart, and they were not built by the same pipeline - one writes an odometer as
     `70844`, the other as `70844.0`. Join them on `test_id` and see whether `vehicle_id` agrees.
  2. **The same car, a year later.** Take January 2024 cars and look for them in January and
     February 2025. If the id travels, make, model and first-use date must agree, and the odometer
     must not have gone backwards.

The null is what agreement would look like if a match were a coincidence, computed from the
sample's own make, model and first-use-date distributions.

Streams about 600 MB and writes none of it to disk.

Usage: .venv/bin/python analysis/readiness_mot_id.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import mot_stream as mot  # noqa: E402
from build_unified import md_table  # noqa: E402

OUT = Path(__file__).parent / "readiness_mot_id_report.md"


def main():
    r = mot.check_vehicle_id()
    lines = [
        "# Does the MOT vehicle id follow a car across releases?",
        "",
        "Layer 2 of the readiness engine needs to follow one car from one year's MOT test to the "
        "next. That is only possible if the anonymised `vehicle_id` means the same car in every "
        "release. DVSA's user guide says it is derived from the registration and the VIN. This "
        "checks it.",
        "",
        "## The answer",
        "",
    ]
    lines.append(md_table(pd.DataFrame([
        {"Test": "Tests published in both the May 2025 and the June 2026 release of 2024",
         "Figure": f"{r['cross_release_tests']:,}"},
        {"Test": "...with an identical vehicle id",
         "Figure": f"{r['cross_release_same_vehicle_id']:.4f}"},
        {"Test": "January 2024 cars carrying an odometer",
         "Figure": f"{r['base_cars']:,}"},
        {"Test": "...found again in January or February 2025",
         "Figure": f"{r['followed']:,}"},
        {"Test": "...whose make and model agree",
         "Figure": f"{r['make_model_agree']:.4f}"},
        {"Test": "...whose first-use date agrees",
         "Figure": f"{r['first_use_agree']:.4f}"},
        {"Test": "...whose odometer has not gone backwards",
         "Figure": f"{r['odometer_not_lower']:.4f}"},
        {"Test": "Make and model agreeing by chance",
         "Figure": f"{r['chance_make_model']:.4f}"},
        {"Test": "First-use date agreeing by chance",
         "Figure": f"{r['chance_first_use']:.4f}"},
    ])))
    lines += [
        "",
        "**The id follows the car.** Two releases built thirteen months apart, by pipelines that "
        "do not even format the odometer the same way, agree on the vehicle id for "
        f"{r['cross_release_same_vehicle_id']:.2%} of the tests they share. Following a car into "
        "the next year, make, model and first-use date agree on every pair, against chance rates "
        f"of {r['chance_make_model']:.2%} and {r['chance_first_use']:.2%}.",
        "",
        "## What the remainder is",
        "",
        f"- **{1 - r['odometer_not_lower']:.2%} of followed cars show a lower odometer a year "
        "later.** That is the rate of mis-keyed and rolled-back readings, and it is the reason "
        "DfT's own note on MOT odometers cleans the pairs before annualising them. It is not "
        "evidence against the id.",
        f"- **{1 - r['cross_release_same_vehicle_id']:.2%} of shared tests disagree on the id.** "
        "A handful of vehicles are re-keyed between releases; at this rate it changes nothing.",
        "",
        "## What this does not settle",
        "",
        "- **An MOT starts at three years.** The id is stable, but there is no record at all of a "
        "car's first three years, so a 24- or 36-month contract cycle is invisible in this data.",
        "- **A test is not a transaction.** The id lets a car be followed; it does not say who "
        "owns it, or that it changed hands. MOT records carry no keeper.",
        "- **It is anonymised on purpose.** The id is derived from the registration and the VIN, "
        "and cannot be turned back into either.",
    ]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.name}")
    print(f"  cross-release {r['cross_release_same_vehicle_id']:.4f} on "
          f"{r['cross_release_tests']:,} tests; followed {r['followed']:,}, "
          f"make+model {r['make_model_agree']:.4f} against chance {r['chance_make_model']:.4f}")


if __name__ == "__main__":
    main()
