"""Hard-gate computation for the Minervini SEPA pipeline.

There is no composite 0-100 score here, and that is deliberate. A single number
invites the analyst to defer to it instead of reasoning — to anchor on "72/100"
rather than read what the modules actually say. SEPA convergence is a JUDGMENT
(do the elements line up like four cars at a four-way stop?), and that judgment
belongs to the analyst reading the raw module outputs against doctrine, not to a
weighted average frozen in code.

What DOES belong in code is the part that admits no judgment: the two
deterministic hard gates. They are binary, non-negotiable, and identical every
time — exactly what a machine should own so the analyst can't rationalize past
them.

- Stage 2:        stage_analysis.stage must == 2 (Stage 1/3/4 -> disqualified)
- Trend Template: trend_template.overall_pass, all 8/8 (no partial credit)

A failed hard gate means structurally disqualified. A missing required source is
different: it makes the verdict incomplete and must never masquerade as AVOID.
"""


PASS = "PASS"
FAIL = "FAIL"
UNAVAILABLE = "UNAVAILABLE"


def _source_error(payload, default):
	"""Extract a child module's structured reason without flattening its JSON."""
	if not isinstance(payload, dict):
		return default
	error = payload.get("error")
	if isinstance(error, dict):
		return error.get("message") or str(error)
	return str(error or payload.get("unavailable") or default)


def compute_hard_gates(results):
	"""Compute the two deterministic SEPA hard gates.

	Returns ``(hard_gate_fail, hard_gates, overall_pass)``. The outer booleans are
	three-state values: ``False/True`` for a complete PASS/FAIL and ``None`` when
	required evidence is unavailable and no known gate has failed. A known failure
	takes precedence; otherwise missing evidence can never be turned into AVOID.
	"""
	hard_gates = []

	# Gate 1 — Stage 2 (lifecycle timing: only Stage 2 advances)
	stage = results.get("stage_analysis", {})
	if not isinstance(stage, dict) or stage.get("error") or "stage" not in stage:
		current_stage = None
		stage_status = UNAVAILABLE
		stage_passed = None
		stage_reason = _source_error(stage, "stage result is missing")
	else:
		current_stage = stage.get("stage")
		stage_passed = current_stage == 2
		stage_status = PASS if stage_passed else FAIL
		stage_reason = None
	stage_gate = {
		"gate": "stage_2",
		"status": stage_status,
		"passed": stage_passed,
		"current_stage": current_stage,
		"required": 2,
	}
	if stage_reason:
		stage_gate["unavailable"] = stage_reason
	# Ship the classification's basis WITH the verdict: the structural reads that
	# drove the stage (price-vs-200, MA stack, trend structure) let the analyst
	# read WHY, not just the number. A gate that hides its basis invites the model
	# to anchor on the label instead of reasoning about the evidence.
	if isinstance(stage, dict) and isinstance(stage.get("structural_reads"), dict):
		stage_gate["basis"] = stage["structural_reads"]
	hard_gates.append(stage_gate)

	# Gate 2 — Trend Template (all 8 criteria; no in-between)
	tt = results.get("trend_template", {})
	if not isinstance(tt, dict) or tt.get("error"):
		tt_status = UNAVAILABLE
		tt_passed = None
		tt_reason = _source_error(tt, "Trend Template result is missing")
	elif tt.get("overall_status") == UNAVAILABLE or tt.get("overall_pass") is None:
		tt_status = UNAVAILABLE
		tt_passed = None
		rs_detail = tt.get("rs", {})
		tt_reason = _source_error(rs_detail, "one or more Trend Template criteria are unavailable")
	elif tt.get("overall_status") in (PASS, FAIL):
		tt_status = tt["overall_status"]
		tt_passed = tt_status == PASS
		tt_reason = None
	elif "overall_pass" in tt:
		tt_passed = bool(tt.get("overall_pass"))
		tt_status = PASS if tt_passed else FAIL
		tt_reason = None
	else:
		tt_status = UNAVAILABLE
		tt_passed = None
		tt_reason = "Trend Template result has no overall status"

	tt_count = tt.get("passed_count", 0) if isinstance(tt, dict) else 0
	tt_total = tt.get("total_count", 8) if isinstance(tt, dict) else 8
	tt_gate = {
		"gate": "trend_template",
		"status": tt_status,
		"passed": tt_passed,
		"score": f"{tt_count}/{tt_total}",
		"required": f"{tt_total}/{tt_total}",
	}
	if tt_reason:
		tt_gate["unavailable"] = tt_reason
	# Ship the per-criterion basis WITH the verdict. Trend Template is an 8-of-8
	# AND gate; "7/8" alone cannot tell the analyst WHICH criterion failed or by
	# how much, and the child already computed exactly that (id, description,
	# measured value vs required threshold). Propagate the full criteria array so
	# a 7/8 near-miss is distinguishable from a 2/8 wreck, and so a screening
	# scout carries the failing criterion forward instead of an opaque count.
	if isinstance(tt, dict) and isinstance(tt.get("criteria"), list):
		tt_gate["criteria"] = tt["criteria"]
	hard_gates.append(tt_gate)

	statuses = {gate["status"] for gate in hard_gates}
	if FAIL in statuses:
		return True, hard_gates, False
	if UNAVAILABLE in statuses:
		return None, hard_gates, None
	return False, hard_gates, True
