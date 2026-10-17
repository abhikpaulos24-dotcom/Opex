from app.simulation.engine import FactorySimulation, SimulationParams
from app.simulation.report import build_report


def run(seed=7, adoption=0.85):
    sim = FactorySimulation(SimulationParams(years=1, seed=seed, adoption_rate=adoption))
    return build_report(sim, sim.run())


def test_same_seed_gives_identical_history():
    assert run()["delta"] == run()["delta"]


def test_opex_reduces_breakdowns_and_pays_back():
    delta = run()["delta"]
    assert delta["failures_avoided"] > 0
    assert delta["downtime_avoided_h"] > 0
    assert delta["total_benefit_inr"] > delta["opex_cost_inr"] / 5  # one year of a five-year cost


def test_nobody_following_advice_means_little_benefit():
    followed = run(adoption=1.0)["delta"]["failures_avoided"]
    ignored = run(adoption=0.3)["delta"]["failures_avoided"]
    assert followed > ignored
