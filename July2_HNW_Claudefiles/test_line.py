from milsoft_dss.elements.line import Line

def show(title, edge, attr):
    print("="*66); print(title); print("="*66)
    ln = Line.from_row(edge, attr, "260316_std")
    print("DSS  :", ln.to_dss())
    print("type :", ln.line_type, "| phases:", (ln.has_a,ln.has_b,ln.has_c), "| len:", ln.length_ft)
    for a in ln.assumptions: print("  assume:", a)
    for f in ln.flags:       print("  FLAG  :", f)
    print()

# 1) overhead 3-phase, uniform conductor
show("1) Overhead 3-phase uniform",
    {"target_node_id":"oh_1","element_name":"oh_1","source_node_id":"N5",
     "has_phase_a":True,"has_phase_b":True,"has_phase_c":True},
    {"line_type":"overhead","conductor_eqdb_label_a":"OH 477 ACSR",
     "conductor_eqdb_label_b":"OH 477 ACSR","conductor_eqdb_label_c":"OH 477 ACSR",
     "conductor_eqdb_label_neutral":"OH 4/0 ACSR","impedance_length_ft":312.0,
     "neutral_impedance_length_ft":312.0,"latitude":44.5,"longitude":-73.2})

# 2) underground single-phase URD (only A conductor)
show("2) Underground 1-phase URD (conductor presence -> phase A)",
    {"target_node_id":"ug_1","element_name":"ug_1","source_node_id":"N7",
     "has_phase_a":None,"has_phase_b":None,"has_phase_c":None},
    {"line_type":"underground","conductor_eqdb_label_a":"UG 1/0 URD 25KV",
     "conductor_eqdb_label_b":None,"conductor_eqdb_label_c":None,
     "conductor_eqdb_label_neutral":"UG 1/0 URD 25KV","impedance_length_ft":150.0})

# 3) overhead phase B only (conductor presence -> .2)
show("3) Overhead single-phase B (conductor on B only)",
    {"target_node_id":"oh_b","element_name":"oh_b","source_node_id":"N9",
     "has_phase_a":None,"has_phase_b":None,"has_phase_c":None},
    {"line_type":"overhead","conductor_eqdb_label_a":None,
     "conductor_eqdb_label_b":"OH #2 ACSR","conductor_eqdb_label_c":None,
     "conductor_eqdb_label_neutral":"OH #2 ACSR","impedance_length_ft":200.0})

# 4) mixed conductors -> flagged
show("4) Overhead mixed conductors (asymmetric -> flag)",
    {"target_node_id":"oh_m","element_name":"oh_m","source_node_id":"N3",
     "has_phase_a":True,"has_phase_b":True,"has_phase_c":True},
    {"line_type":"overhead","conductor_eqdb_label_a":"OH 477 ACSR",
     "conductor_eqdb_label_b":"OH 336 ACSR","conductor_eqdb_label_c":"OH 477 ACSR",
     "impedance_length_ft":500.0})

# 5) edge/conductor phase MISMATCH -> cross-check flag
show("5) Edge says ABC but conductor only on A,B (mismatch flag)",
    {"target_node_id":"oh_x","element_name":"oh_x","source_node_id":"N2",
     "has_phase_a":True,"has_phase_b":True,"has_phase_c":True},
    {"line_type":"overhead","conductor_eqdb_label_a":"OH 1/0 ACSR",
     "conductor_eqdb_label_b":"OH 1/0 ACSR","conductor_eqdb_label_c":None,
     "impedance_length_ft":300.0})
