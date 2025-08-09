from schema_agent.core.planner.postgres import Step
from schema_agent.core.sched import schedule_steps


def test_topological_and_phase_order():
    s1 = Step(id="s1", table="orders", sql="A", phase="prep")
    s2 = Step(id="s2", table="orders", sql="B", phase="tighten", depends_on=["s1"])  # depends on s1
    s3 = Step(id="s3", table="orders", sql="C", phase="indexes")
    ordered = schedule_steps([s2, s3, s1])
    ids = [s.id for s in ordered]
    assert ids.index("s1") < ids.index("s2")


