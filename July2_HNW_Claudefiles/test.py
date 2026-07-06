"""
tests.py — comprehensive test suite for the milsoft_dss pipeline.

Run:  python tests.py

Covers each element (construct -> resolve -> emit), the feeder assembly, the
meter-load split, and end-to-end OpenDSS solves. Prints PASS/FAIL per test and
a summary. No external test framework needed -- plain asserts with a tiny runner.
"""
from __future__ import annotations
import sys, traceback

# ---- tiny test runner ------------------------------------------------------
_results = []
def test(fn):
    _results.append(fn); return fn

def check(cond, msg):
    if not cond:
        raise AssertionError(msg)

def run_all():
    passed = 0
    for fn in _results:
        name = fn.__name__
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            traceback.print_exc()
    print(f"\n{passed}/{len(_results)} passed")
    return passed == len(_results)


# ========================================================================== #
# ELEMENT TESTS
# ========================================================================== #
from milsoft_dss.elements.source import Source
from milsoft_dss.elements.line import Line
from milsoft_dss.elements.transformer import Transformer
from milsoft_dss.elements.consumer import Consumer
from milsoft_dss.elements.switch import Switch
from milsoft_dss.elements.capacitor import Capacitor
from milsoft_dss.elements.regulator import Regulator


@test
def source_voltage_snapping():
    s = Source.from_row(
        {"target_node_id":"SUB","source_node_id":"ROOT","element_name":"SUB"},
        {"nominal_voltage":14.4,"voltage_bus_ratio":1.05}, "snap")
    s.resolve()
    check(s.basekv_ll == 24.94, f"expected 24.94, got {s.basekv_ll}")
    check("pu=1.05" in s.to_dss(), "pu setpoint missing")
    check(s.to_dss().startswith("New Circuit."), "should emit New Circuit")


@test
def source_12kv_class():
    s = Source.from_row(
        {"target_node_id":"S","source_node_id":"ROOT","element_name":"S"},
        {"nominal_voltage":7.2,"voltage_bus_ratio":1.05}, "s")
    s.resolve()
    check(s.basekv_ll == 12.47, f"expected 12.47, got {s.basekv_ll}")


@test
def transformer_single_phase_LN():
    xf = Transformer.from_row(
        {"target_node_id":"T","source_node_id":"N","element_name":"T"},
        {"rated_voltage_srcside":14.4,"rated_voltage_loadside":0.12,
         "capacity_kva_a":25,"capacity_kva_b":0,"capacity_kva_c":0,
         "TRANSFORMER_PHASE":"ABC","USAGE_POINT_PHASE":"A"}, "s")
    xf.resolve()
    d = xf.to_dss()
    check("phases=1" in d, "single-phase should be phases=1")
    check(".1" in d and ".1.2" not in d, "should be on phase 1 only")
    # 1-phase uses L-N kv (14.4-ish), not L-L
    check(xf._emit_kv(xf.hv_kv_ln, xf.hv_kv_ll) < 20, "1ph should use L-N kv")


@test
def transformer_three_phase_LL():
    xf = Transformer.from_row(
        {"target_node_id":"T","source_node_id":"N","element_name":"T"},
        {"rated_voltage_srcside":14.4,"rated_voltage_loadside":0.277,
         "capacity_kva_a":167,"capacity_kva_b":167,"capacity_kva_c":167,
         "TRANSFORMER_PHASE":"ABC","USAGE_POINT_PHASE":"ABC"}, "s")
    xf.resolve()
    d = xf.to_dss()
    check("phases=3" in d, "should be phases=3")
    check("24.94" in d, f"3ph should use L-L 24.94; got {d}")


@test
def transformer_two_phase_line_to_line():
    xf = Transformer.from_row(
        {"target_node_id":"T","source_node_id":"N","element_name":"T"},
        {"rated_voltage_srcside":14.4,"rated_voltage_loadside":0.24,
         "capacity_kva_a":50,"capacity_kva_b":50,"capacity_kva_c":0,
         "TRANSFORMER_PHASE":"ABC","USAGE_POINT_PHASE":"AB"}, "s")
    xf.resolve()
    d = xf.to_dss()
    check(".1.2" in d, "AB should connect .1.2")
    check("delta" in d, "line-to-line primary should be delta")
    check("24.94" in d, "AB uses L-L kv")


@test
def line_phasing_from_conductors():
    ln = Line.from_row(
        {"target_node_id":"L","source_node_id":"N","element_name":"L",
         "has_phase_a":True,"has_phase_b":True,"has_phase_c":True},
        {"line_type":"overhead","conductor_eqdb_label_a":"477",
         "conductor_eqdb_label_b":"477","conductor_eqdb_label_c":"477",
         "impedance_length_ft":1000}, "s")
    ln.base_kv = 24.94
    d = ln.to_dss()
    check("phases=3" in d, "3-phase line")
    check(".1.2.3" in d, "should be on all 3 phases")
    check("linecode=" in d.lower(), "should reference a linecode")


@test
def consumer_per_phase_unbalanced():
    c = Consumer.from_row(
        {"target_node_id":"c","source_node_id":"T","element_name":"c"},
        {"USAGE_POINT_PHASE":"ABC","serving_kv_ln":0.277,
         "kw_coincident_a":80,"kw_coincident_b":50,"kw_coincident_c":110,
         "kvar_coincident_a":25,"kvar_coincident_b":15,"kvar_coincident_c":35}, "s")
    d = c.to_dss()
    # three separate single-phase loads
    check(d.count("New Load.") == 3, f"expected 3 loads, got {d.count('New Load.')}")
    check("kw=80" in d and "kw=50" in d and "kw=110" in d, "per-phase kw missing")
    check(abs(c.total_kw() - 240) < 0.01, f"total kw should be 240, got {c.total_kw()}")


@test
def consumer_scenario_switch():
    attr = {"USAGE_POINT_PHASE":"A","serving_kv_ln":0.12,
            "kw_coincident_a":8,"kw_max_a":12}
    c1 = Consumer.from_row({"target_node_id":"c","source_node_id":"T","element_name":"c"},
                           attr, "s", scenario="coincident")
    c2 = Consumer.from_row({"target_node_id":"c","source_node_id":"T","element_name":"c"},
                           attr, "s", scenario="max")
    check("kw=8" in c1.to_dss(), "coincident should be 8")
    check("kw=12" in c2.to_dss(), "max should be 12")


@test
def switch_closed_passthrough():
    sw = Switch.from_row(
        {"target_node_id":"sw","source_node_id":"N","element_name":"sw",
         "has_phase_a":True,"has_phase_b":True,"has_phase_c":True,
         "edge_type":"electric_switch"}, {}, "s")
    d = sw.to_dss()
    check("switch=yes" in d, "should emit switch=yes")
    check(sw.is_closed, "default should be closed")
    check("enabled=no" not in d, "closed switch should be enabled")


@test
def switch_recloser_detected():
    sw = Switch.from_row(
        {"target_node_id":"rclsr_5","source_node_id":"SUB","element_name":"rclsr_5",
         "has_phase_a":True,"has_phase_b":True,"has_phase_c":True,
         "edge_type":"overcurrent_device","is_feeder":True,"is_recloser":True}, {}, "s")
    check(sw.kind == "recloser", f"should detect recloser, got {sw.kind}")


@test
def capacitor_emit():
    cap = Capacitor.from_row(
        {"target_node_id":"cap","source_node_id":"N","element_name":"cap",
         "has_phase_a":True,"has_phase_b":True,"has_phase_c":True},
        {"kvar_a":100,"kvar_b":100,"kvar_c":100}, "s")
    cap.base_kv = 24.94
    cap.resolve()
    d = cap.to_dss()
    check("New Capacitor." in d, "should emit New Capacitor")
    check("kvar=300" in d, f"total kvar should be 300; got {d}")


@test
def regulator_emits_transformer_and_control():
    reg = Regulator.from_row(
        {"target_node_id":"reg","source_node_id":"N","element_name":"reg",
         "has_phase_a":True,"has_phase_b":True,"has_phase_c":True}, {}, "s")
    reg.base_kv = 24.94
    reg.resolve()
    d = reg.to_dss()
    check("New Transformer." in d, "regulator needs a transformer")
    check("New RegControl." in d, "regulator needs a RegControl")


# ========================================================================== #
# METER LOAD SPLIT TESTS
# ========================================================================== #
from milsoft_dss.io.meter_loads import build_consumer_attr


@test
def meter_split_by_vi():
    row = {"node_id":"c","usage_point_phase":"ABC","meter":"m",
           "kw_coincident":120,"kvar_coincident":36,
           "v_a":277,"v_b":277,"v_c":277,"i_a":165,"i_b":103,"i_c":226}
    a = build_consumer_attr(row)
    # phase C has most current -> most load
    check(a["kw_coincident_c"] > a["kw_coincident_a"] > a["kw_coincident_b"],
          "split should follow current C>A>B")


@test
def meter_single_phase_full_total():
    row = {"node_id":"c","usage_point_phase":"A","meter":"m",
           "kw_coincident":8,"kvar_coincident":2.5,"v_a":120,"i_a":70}
    a = build_consumer_attr(row)
    check(a["kw_coincident_a"] == 8, "single-phase gets full total")


@test
def meter_mislabel_flagged():
    row = {"node_id":"c","usage_point_phase":"ABC","meter":"m",
           "kw_coincident":60,"kvar_coincident":18,
           "v_a":277,"v_b":277,"v_c":277,"i_a":113,"i_b":113,"i_c":0.1}
    a = build_consumer_attr(row)
    check(a.get("kw_coincident_c",0)==0, "phase C (no current) should get 0 load")
    check(any("mislabel" in f for f in a.get("_flags",[])), "should flag mislabel")


# ========================================================================== #
# INTEGRATION: full feeder build + solve
# ========================================================================== #
from milsoft_dss.feeder import Feeder


def _build_test_feeder():
    return Feeder.build(
        "feeder_test", "s",
        source_rows={"edge":{"target_node_id":"SUB","source_node_id":"ROOT","element_name":"SUB"},
                     "attr":{"nominal_voltage":14.4,"voltage_bus_ratio":1.05,
                             "has_phase_a":True,"has_phase_b":True,"has_phase_c":True}},
        line_rows=[{"edge":{"target_node_id":"N1","source_node_id":"SUB","element_name":"N1",
                            "has_phase_a":True,"has_phase_b":True,"has_phase_c":True},
                    "attr":{"line_type":"overhead","conductor_eqdb_label_a":"477",
                            "conductor_eqdb_label_b":"477","conductor_eqdb_label_c":"477",
                            "impedance_length_ft":2500}}],
        transformer_rows=[{"edge":{"target_node_id":"T1","source_node_id":"N1","element_name":"T1"},
                           "attr":{"rated_voltage_srcside":14.4,"rated_voltage_loadside":0.277,
                                   "capacity_kva_a":167,"capacity_kva_b":167,"capacity_kva_c":167,
                                   "TRANSFORMER_PHASE":"ABC","USAGE_POINT_PHASE":"ABC"}}],
        region_voltage={"N1":24.94},
        consumer_rows=[{"edge":{"target_node_id":"T1","source_node_id":"T1","element_name":"T1"},
                        "attr":{"USAGE_POINT_PHASE":"ABC",
                                "kw_coincident_a":80,"kw_coincident_b":50,"kw_coincident_c":110,
                                "kvar_coincident_a":25,"kvar_coincident_b":15,"kvar_coincident_c":35}}],
        scenario="coincident")


@test
def feeder_builds_and_emits():
    f = _build_test_feeder()
    d = f.to_dss()
    check("New Circuit." in d, "missing circuit")
    check("New Transformer." in d, "missing transformer")
    check("New Line." in d, "missing line")
    check("New Load." in d, "missing loads")
    check(d.index("New Circuit.") < d.index("New Line."), "circuit must precede lines")


@test
def feeder_report_counts():
    f = _build_test_feeder()
    r = f.report()
    check(r["n_lines"] == 1, "should have 1 line")
    check(r["n_transformers"] == 1, "should have 1 transformer")
    check(r["n_consumers"] == 1, "should have 1 consumer")
    check(abs(r["total_load_kw"] - 240) < 0.1, f"total load 240; got {r['total_load_kw']}")


@test
def feeder_solves_with_unbalance():
    import opendssdirect as dss
    f = _build_test_feeder()
    dss.Text.Command("Clear")
    for stmt in f.to_dss().splitlines():
        if stmt.strip() and not stmt.startswith("!"):
            dss.Text.Command(stmt)
    dss.Solution.Solve()
    check(dss.Solution.Converged(), "feeder should converge")
    # unbalanced load -> per-phase voltages differ
    dss.Circuit.SetActiveBus("T1")
    v = dss.Bus.puVmagAngle()
    phase_v = [v[i] for i in range(0, len(v), 2)]
    check(len(set(round(x,3) for x in phase_v)) > 1,
          "unbalanced load should give different per-phase voltages")


if __name__ == "__main__":
    print("Running milsoft_dss test suite\n" + "="*50)
    ok = run_all()
    sys.exit(0 if ok else 1)