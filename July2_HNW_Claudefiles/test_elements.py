from milsoft_dss.elements.overhead_line import OverheadLine
from milsoft_dss.elements.step_transformer import StepTransformer

print("="*60)
print("TEST 1: OverheadLine — construct + emit + assumptions")
print("="*60)
oh_row = {
    "element_name": "oh_00012", "parent_element_name": "NODE_5",
    "phase_config_code": "ABC", "conductor_eqdb_label_a": "OH 477 ACSR",
    "impedance_length_ft": 312.0,
}
oh = OverheadLine.from_row(oh_row, "260316_std")
print("DSS :", oh.to_dss())
print("assume:", oh.assumptions)
print("flags :", oh.flags)

print("\n" + "="*60)
print("TEST 2: OverheadLine — single phase + missing conductor (flags)")
print("="*60)
oh2 = OverheadLine.from_row({
    "element_name": "oh_00099", "parent_element_name": "NODE_9",
    "phase_config_code": "A", "conductor_eqdb_label_a": None,
    "impedance_length_ft": 0,
}, "260316_std")
print("DSS :", oh2.to_dss())
print("flags :", oh2.flags)

print("\n" + "="*60)
print("TEST 3: StepTransformer — construct + RESOLVE (snap) + emit")
print("="*60)
xf_row = {
    "element_name": "xfmr_001", "parent_element_name": "NODE_5",
    "phase_config_code": "A",
    "rated_voltage_srcside": 14.39999996,      # -> 14.4 (24.9 class L-N)
    "reate_voltage_loadside": 0.1199999,       # -> 0.12
    "capacity_kva_a": 25.0, "capacity_kva_b": 0, "capacity_kva_c": 0,
}
xf = StepTransformer.from_row(xf_row, "260316_std")
print("before resolve: hv_kv =", xf.hv_kv, " lv_kv =", xf.lv_kv)
xf.resolve(feeder=None)
print("after  resolve: hv_kv =", xf.hv_kv, " lv_kv =", xf.lv_kv)
print("DSS :", xf.to_dss())
print("assume:", xf.assumptions)
print("flags :", xf.flags)

print("\n" + "="*60)
print("TEST 4: StepTransformer — oddball voltage (0.16) -> flagged")
print("="*60)
xf2 = StepTransformer.from_row({
    "element_name": "xfmr_002", "parent_element_name": "NODE_7",
    "phase_config_code": "ABC",
    "rated_voltage_srcside": 7.2, "reate_voltage_loadside": 0.159926,
    "capacity_kva_a": 167, "capacity_kva_b": 167, "capacity_kva_c": 167,
}, "260316_std")
xf2.resolve(feeder=None)
print("DSS :", xf2.to_dss())
print("flags :", xf2.flags)
