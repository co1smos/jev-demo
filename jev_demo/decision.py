"""One bounded, persisted JEV stock decision."""

import math
from dataclasses import asdict
import json
from urllib.request import Request, urlopen


MODEL = "jev-1.13.0"
QUESTION_VERSION = "stock_action_v1"
ACTIONS = ("BUY", "HOLD", "SELL", "ABSTAIN")
QUESTION = {
    "version": QUESTION_VERSION,
    "text": "Choose the action best supported by the supplied precomputed strategy features.",
    "options": ACTIONS,
    "criteria": {
        "BUY": "Open a long position.",
        "HOLD": "Make no position change.",
        "SELL": "Close the long position.",
        "ABSTAIN": "The supplied features do not support a decision.",
    },
}


class TypeSafeDecisionProvider:
    """Small stdlib adapter for the TypeSafe System One endpoint."""

    def __init__(self, api_key, request=None):
        if not api_key:
            raise ValueError("TypeSafe API key is required")
        self.api_key = api_key
        self.request = request or self._request

    def decide(self, state, model, question):
        payload = json.dumps({
            "state": state,
            "model": model,
            "questions": {"action": {
                "type": "choice",
                "instructions": question["text"],
                "criteria": question["criteria"],
            }},
        }).encode()
        raw = json.loads(self.request(Request(
            "https://api.typesafe.ai/v1/systemone",
            data=payload,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )))
        if not isinstance(raw.get("answers"), dict) or set(raw["answers"]) != {"action"}:
            raise ValueError("unexpected answers")
        answer = raw["answers"]["action"]
        if answer.get("type") != "choice":
            raise ValueError("unexpected answer type")
        confidence = answer.get("confidence")
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("invalid confidence")
        return {"model": raw["model"], "action": answer["choice"],
                "probabilities": answer["probabilities"]}

    @staticmethod
    def _request(request):
        with urlopen(request, timeout=10) as response:
            return response.read()


def obtain_decision(run_id, request, provider, store):
    """Ask a replaceable provider for one decision and persist the result."""
    state = {"symbol": request.symbol, **{
        key: value.value if hasattr(value, "value") else value
        for key, value in asdict(request.features).items()
    }}
    error = "provider_error"
    for _ in range(3):
        try:
            response = provider.decide(state, MODEL, QUESTION)
            _validate(response)
        except TimeoutError:
            error = "timeout"
        except (KeyError, TypeError, ValueError):
            error = "invalid_response"
        except Exception:
            error = "provider_error"
        else:
            decision = _record(request, state, response)
            store.append(run_id, "jev_decision", decision)
            return decision

    decision = _record(request, state, {
        "model": None,
        "action": "ABSTAIN",
        "probabilities": {action: 1.0 if action == "ABSTAIN" else 0.0 for action in ACTIONS},
    })
    decision["error"] = error
    store.append(run_id, "jev_decision_error", decision)
    return decision


def _validate(response):
    if not isinstance(response, dict) or response.get("model") != MODEL:
        raise ValueError("unexpected model")
    if response.get("action") not in ACTIONS:
        raise ValueError("unexpected action")
    probabilities = response.get("probabilities")
    if not isinstance(probabilities, dict) or set(probabilities) != set(ACTIONS):
        raise ValueError("unexpected probability options")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
           not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities.values()):
        raise ValueError("invalid probability")
    if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=1e-6):
        raise ValueError("probabilities must sum to one")
    if probabilities[response["action"]] != max(probabilities.values()):
        raise ValueError("action must have the highest probability")


def _record(request, state, response):
    return {
        "symbol": request.symbol,
        "minute": request.minute,
        "action": response["action"],
        "probabilities": response["probabilities"],
        "input": state,
        "input_version": request.strategy_version,
        "question_version": QUESTION_VERSION,
        "requested_model": MODEL,
        "returned_model": response["model"],
    }
