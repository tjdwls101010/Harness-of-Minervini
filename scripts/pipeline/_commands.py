"""Minervini SEPA pipeline command implementations.

Two composable subcommands — NOT a closed pipeline, and deliberately WITHOUT an
"analyze everything at once" command. That monolith was the Serenity-style
total-collect crutch: it reasoned FOR the analyst by grouping every module into
one verdict-shaped blob, which invites deference to the shape instead of reading
the evidence. Deepening past the gate is done by calling the individual module
CLIs directly (vcp, earnings_acceleration, rs_ranking, volume_analysis, …), in
the order the funnel earns.

- qualify: low-cost Tier-0 gate (Stage 2 + Trend Template + RS) — run this FIRST
- discover: market environment + RS leader discovery

Each module result is checked for errors and missing modules are tracked
(graceful degradation).
"""

import concurrent.futures
import time

from rs_ranking import call_backend
from utils import output_json, safe_run

from ._runner import _run_script
from ._gates import compute_hard_gates


# ---------------------------------------------------------------------------
# cmd_qualify — Tier-0 low-cost gate
# ---------------------------------------------------------------------------

@safe_run
def cmd_qualify(args):
	"""Tier-0 gate: the lowest-cost read that can disqualify a ticker.

	Runs the two nonduplicative reads that decide whether deeper work is worth it —
	Trend Template (which owns the RS criterion) and Stage analysis — and returns the deterministic hard-gate
	verdict. AVOID means structurally disqualified: stop, don't spend a full
	analyze pass. PROCEED means the name earned a closer look, NOT that it's a buy.
	INCOMPLETE means a required source was unavailable and no known gate failed;
	it must never be flattened into AVOID.
	"""
	ticker = args.ticker.upper()
	start = time.time()
	no_cache = bool(getattr(args, "no_cache", False))
	cache_args = ["--no-cache"] if no_cache else []

	scripts = {
		"trend_template": ("modules/trend_template.py", ["check", ticker, *cache_args]),
		"stage_analysis": ("modules/stage_analysis.py", ["classify", ticker, *cache_args]),
	}

	with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
		futures = {
			name: executor.submit(_run_script, path, a)
			for name, (path, a) in scripts.items()
		}
		results = {name: future.result() for name, future in futures.items()}

	hard_gate_fail, hard_gates, overall_pass = compute_hard_gates(results)

	stage = results.get("stage_analysis", {})
	trend = results.get("trend_template", {})
	rs_eligibility = trend.get("rs", {}) if isinstance(trend, dict) else {}
	tt_gate = next((g for g in hard_gates if g["gate"] == "trend_template"), {})

	if overall_pass is True:
		verdict = "PROCEED"
	elif overall_pass is False:
		verdict = "AVOID"
	else:
		verdict = "INCOMPLETE"
	failed = [gate["gate"] for gate in hard_gates if gate["passed"] is False]
	unavailable = [gate["gate"] for gate in hard_gates if gate["passed"] is None]
	elapsed = round(time.time() - start, 1)

	output_json({
		"ticker": ticker,
		"verdict": verdict,
		"overall_pass": overall_pass,
		"hard_gate_fail": hard_gate_fail,
		"failed_gates": failed,
		"unavailable_gates": unavailable,
		"hard_gates": hard_gates,
		"stage": stage.get("stage") if not stage.get("error") else None,
		"trend_template_score": tt_gate.get("score"),
		"rs_rating": trend.get("rs_score") if isinstance(trend, dict) and not trend.get("error") else None,
		"rs_rating_date": rs_eligibility.get("rating_date"),
		"rs_status": rs_eligibility.get("status"),
		"rs_source": rs_eligibility.get("source"),
		"interpretation": {
			"PROCEED": "both hard gates pass (Stage 2 + Trend Template 8/8) — worth a full read, NOT yet a buy",
			"AVOID": "a hard gate failed — structurally disqualified; stop here, do not deepen",
			"INCOMPLETE": "required gate evidence is unavailable and no known gate failed — retry once, then report unavailable",
		},
		"metadata": {"execution_time_seconds": elapsed},
	})



# ---------------------------------------------------------------------------
# cmd_market_leaders
# ---------------------------------------------------------------------------

@safe_run
def cmd_discover(args):
	"""Market environment + RS leader discovery.

	Collects breadth, the QQQ information switch, and bottom-up leader evidence, and identifies
	RS leaders (sector/industry rankings, top stocks, movers) for
	candidate discovery using the ibd-rs-rating library.
	"""
	start = time.time()

	no_cache = bool(getattr(args, "no_cache", False))
	child_cache_args = ["--no-cache"] if no_cache else []
	rs_errors = {}

	# Single executor: RS calls complete in ~1s, finviz market-breadth ~20-30s.
	# Submit industry_top as soon as industry_ranking completes (overlaps with
	# market-breadth wait, so adds zero wall-clock time).
	with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
		f_breadth = executor.submit(_run_script, "modules/market_breadth.py", ["breadth", *child_cache_args])
		f_rs_ref = executor.submit(call_backend, "reference", no_cache=no_cache)
		f_rs_top = executor.submit(call_backend, "top", params={"n": 20}, no_cache=no_cache)
		f_sector_rank = executor.submit(call_backend, "sector_ranking", no_cache=no_cache)
		f_industry_rank = executor.submit(call_backend, "industry_ranking", no_cache=no_cache)
		f_movers = executor.submit(
			call_backend,
			"movers",
			params={"days": 5, "n": 20, "direction": "up"},
			no_cache=no_cache,
		)

		# Wait for industry_ranking first (~0.8s) then submit industry_top
		# while market-breadth is still running (~20-30s remaining)
		try:
			industry_rank = f_industry_rank.result() or []
		except Exception as exc:
			industry_rank = []
			rs_errors["leadership_dashboard"] = f"{type(exc).__name__}: {exc}"

		industry_futures = {}
		for ind in industry_rank[:15]:
			ind_name = ind.get("industry", "")
			if ind_name:
				f = executor.submit(
					call_backend,
					"industry_top",
					symbol=ind_name,
					params={"industry": ind_name, "n": 5},
					no_cache=no_cache,
				)
				industry_futures[f] = ind

		# Collect remaining Phase 1 results (market-breadth is the bottleneck)
		try:
			breadth_result = f_breadth.result()
		except Exception as exc:
			breadth_result = {"error": f"{type(exc).__name__}: {exc}"}

		# RS data (graceful on failure)
		try:
			rs_ref = f_rs_ref.result() or []
		except Exception as exc:
			rs_ref = []
			rs_errors["reference"] = f"{type(exc).__name__}: {exc}"
		try:
			rs_top = f_rs_top.result() or []
		except Exception as exc:
			rs_top = []
			rs_errors["top_20"] = f"{type(exc).__name__}: {exc}"
		try:
			sector_rank = f_sector_rank.result() or []
		except Exception as exc:
			sector_rank = []
			rs_errors["sector_ranking"] = f"{type(exc).__name__}: {exc}"
		try:
			movers_result = f_movers.result() or []
		except Exception as exc:
			movers_result = []
			rs_errors["movers_5d"] = f"{type(exc).__name__}: {exc}"

		# Collect industry_top results (already completed during breadth wait)
		for f in concurrent.futures.as_completed(industry_futures):
			ind = industry_futures[f]
			try:
				tickers = f.result() or []
				ind["leader_tickers"] = [t["ticker"] for t in tickers]
				ind["leader_count"] = len(ind["leader_tickers"])
			except Exception as exc:
				ind["leader_tickers"] = []
				ind["leader_count"] = 0
				ind["leader_tickers_unavailable"] = f"{type(exc).__name__}: {exc}"
				rs_errors.setdefault("industry_top", {})[ind.get("industry", "unknown")] = (
					f"{type(exc).__name__}: {exc}"
				)

	# Assign leadership ranks
	for i, ind in enumerate(industry_rank):
		ind["leadership_rank"] = i + 1

	# Market breadth. A missing scrape must not turn two synthetic zeros into a
	# fabricated directional verdict.
	hl = breadth_result.get("new_high_low", {}) if isinstance(breadth_result, dict) else {}
	breadth_reason = None
	if not isinstance(breadth_result, dict):
		breadth_reason = "market-breadth child returned a non-object payload"
	elif breadth_result.get("error"):
		breadth_reason = str(breadth_result["error"])
	elif hl.get("unavailable"):
		breadth_reason = str(hl.get("reason") or "new-high/new-low section unavailable")
	try:
		new_highs = int(hl["new_high"]["count"]) if breadth_reason is None else None
		new_lows = int(hl["new_low"]["count"]) if breadth_reason is None else None
	except (KeyError, TypeError, ValueError):
		new_highs = None
		new_lows = None
		breadth_reason = "new-high/new-low section is missing valid counts"

	# Build RS leaders section
	spy_rs = None
	qqq_rs = None
	for ref in (rs_ref or []):
		if ref.get("ticker") == "SPY":
			spy_rs = ref.get("rs_rating")
		elif ref.get("ticker") == "QQQ":
			qqq_rs = ref.get("rs_rating")

	rs_leaders = {
		"source": "ibd-rs-rating",
		"spy_rs": spy_rs,
		"qqq_rs": qqq_rs,
		"top_20": rs_top[:20] if rs_top else [],
		"movers_5d": movers_result[:20],
		"unavailable": {
			key: reason
			for key, reason in rs_errors.items()
			if key in {"reference", "top_20", "movers_5d"}
		} or None,
	}

	# Add rank to sector_ranking
	for i, s in enumerate(sector_rank):
		s["rank"] = i + 1

	# The maps provide one mechanical *information* signal (the asymmetric QQQ
	# switch), but deliberately do not provide a numeric bull/bear breadth formula
	# or distribution-day counter. Discover therefore reports evidence readiness;
	# the market-scan skill makes the bottom-up regime judgment from leaders,
	# breadth expansion, switch context, and actual trade feedback.
	qqq_switch = breadth_result.get("qqq_21ema_switch", {}) if isinstance(breadth_result, dict) else {}
	qqq_state = qqq_switch.get("state") if isinstance(qqq_switch, dict) else None
	qqq_available = qqq_state in {"ON", "OFF"}
	breadth_available = breadth_reason is None
	leaders_available = bool(rs_top or sector_rank or industry_rank or movers_result)
	axis_availability = {
		"breadth": breadth_available,
		"qqq_information_switch": qqq_available,
		"bottom_up_leaders": leaders_available,
	}
	available_axes = sum(axis_availability.values())
	regime_status = "evidence_ready" if available_axes == 3 else "partial" if available_axes else "incomplete"
	market_verdict = "requires_bottom_up_judgment" if available_axes else "incomplete"
	verdict_evidence = {
		"axis_availability": axis_availability,
		"new_highs": new_highs,
		"new_lows": new_lows,
		"new_high_minus_low_count": new_highs - new_lows if breadth_available else None,
		"qqq_21ema_switch": qqq_switch,
		"package_top_leader_count": len(rs_top),
		"sector_count": len(sector_rank),
		"industry_count": len(industry_rank),
	}

	elapsed = round(time.time() - start, 1)
	section_unavailable = {}
	if breadth_reason is not None:
		section_unavailable["breadth"] = breadth_reason
	if not qqq_available:
		section_unavailable["qqq_21ema_switch"] = (
			str(qqq_switch.get("reason") or "QQQ 21-EMA switch unavailable")
			if isinstance(qqq_switch, dict)
			else "QQQ 21-EMA switch unavailable"
		)
	for section in ("sector_ranking", "leadership_dashboard", "industry_top"):
		if section in rs_errors:
			section_unavailable[section] = rs_errors[section]
	if rs_leaders["unavailable"]:
		section_unavailable["rs_leaders"] = rs_leaders["unavailable"]

	output_json({
		"market_verdict": market_verdict,
		"regime_status": regime_status,
		"verdict_evidence": verdict_evidence,
		"breadth": {
			"new_highs": new_highs,
			"new_lows": new_lows,
			"detail": breadth_result if isinstance(breadth_result, dict) else None,
			"unavailable": breadth_reason,
		},
		"qqq_21ema_switch": qqq_switch,
		"rs_leaders": rs_leaders,
		"sector_ranking": sector_rank,
		"leadership_dashboard": industry_rank,
		"unavailable": section_unavailable,
		"regime_contract": {
			"bottom_up_decider": "[M] leader quality, new-high/new-low expansion, and actual trade feedback decide the regime",
			"information_filter": "[TL] QQQ 21-EMA ON/OFF is context for probes, never a standalone exposure or directional verdict",
			"forbidden_inference": "No numeric bull/bear breadth bands or distribution-day tally exist in the authorized maps, so this command does not invent them",
		},
		"doctrine": "[M] Read the market from resilient leaders and trade feedback. [TL] Use the asymmetric QQQ switch only as an information filter; ON starts observation/probes, not automatic exposure.",
		"provenance": {"bottom_up_regime": "[M] cluster B", "qqq_switch": "[TL] cluster F and conflict ruling 4.7"},
		"metadata": {
			"execution_time_seconds": elapsed,
		},
	})
