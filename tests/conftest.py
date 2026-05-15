import json
from pathlib import Path

import pytest

CONTRACTS_DIR = Path(__file__).parents[1] / "contracts"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"


@pytest.fixture
def gnss_example():
    with open(EXAMPLES_DIR / "gnss-shangtan.json") as f:
        return json.load(f)


@pytest.fixture
def rainfall_example():
    with open(EXAMPLES_DIR / "rainfall-shangtan.json") as f:
        return json.load(f)


@pytest.fixture
def strain_example():
    with open(EXAMPLES_DIR / "strain-shangtan.json") as f:
        return json.load(f)


@pytest.fixture
def soil_pressure_example():
    with open(EXAMPLES_DIR / "soil-pressure-shangtan.json") as f:
        return json.load(f)


@pytest.fixture
def deep_displacement_example():
    with open(EXAMPLES_DIR / "deep-displacement-lingzhan.json") as f:
        return json.load(f)


@pytest.fixture(
    params=["gnss", "rainfall", "strain", "soil_pressure", "deep_displacement"]
)
def any_example(
    request,
    gnss_example,
    rainfall_example,
    strain_example,
    soil_pressure_example,
    deep_displacement_example,
):
    return {
        "gnss": gnss_example,
        "rainfall": rainfall_example,
        "strain": strain_example,
        "soil_pressure": soil_pressure_example,
        "deep_displacement": deep_displacement_example,
    }[request.param]
