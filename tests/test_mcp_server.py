"""The MCP server is tested through `handle`, the same function the stdio transport uses."""

import json

from atima_fl.engine import mcp_server

RUNS = ["list_runs", "run_summary", "pattern_report", "paired_verdict", "noise_thresholds", "detect_latency"]


def _request(method, params=None, request_id=1):
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}


def test_initialize_advertises_tools_capability():
    response = mcp_server.handle(_request("initialize"))
    assert response["result"]["serverInfo"]["name"] == mcp_server.SERVER_NAME
    assert "tools" in response["result"]["capabilities"]


def test_tools_list_is_complete_and_every_tool_has_a_handler():
    response = mcp_server.handle(_request("tools/list"))
    names = [tool["name"] for tool in response["result"]["tools"]]
    assert names == RUNS
    assert set(names) == set(mcp_server.HANDLERS)
    for tool in response["result"]["tools"]:
        assert tool["inputSchema"]["type"] == "object"
        assert tool["description"]


def test_unknown_method_and_unknown_tool_are_reported_not_swallowed():
    assert mcp_server.handle(_request("nope"))["error"]["code"] == -32601
    unknown = mcp_server.handle(_request("tools/call", {"name": "nope", "arguments": {}}))
    assert unknown["error"]["code"] == -32602


def test_tool_failure_returns_an_error_result():
    response = mcp_server.handle(
        _request("tools/call", {"name": "run_summary", "arguments": {"run": "does-not-exist"}})
    )
    assert response["result"]["isError"] is True
    assert "FileNotFoundError" in response["result"]["content"][0]["text"]


def test_notifications_get_no_answer():
    assert mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert mcp_server.handle({"jsonrpc": "2.0", "id": 7, "method": "ping"})["result"] == {}


def test_pattern_report_over_a_written_run(tmp_path):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from test_pattern import _episodic

    run = tmp_path / "campaign" / "E_lcg"
    run.mkdir(parents=True)
    (run / "validation_history.json").write_text(json.dumps(_episodic()), encoding="utf-8")
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "name": "E_lcg",
                "status": "complete",
                "last_valid_round": 50,
                "config": {"attack": "local_class_gradient", "seed": 1},
            }
        ),
        encoding="utf-8",
    )
    (run / "final_metrics.json").write_text(
        json.dumps({"test": {"macro_f1": 0.33}, "federated": {"rounds": []}}), encoding="utf-8"
    )

    listing = mcp_server.handle(
        _request("tools/call", {"name": "list_runs", "arguments": {"path": str(tmp_path)}})
    )
    payload = json.loads(listing["result"]["content"][0]["text"])
    assert payload["count"] == 1
    assert payload["runs"][0]["attack"] == "local_class_gradient"

    summary = mcp_server.handle(
        _request("tools/call", {"name": "run_summary", "arguments": {"run": str(run)}})
    )
    assert json.loads(summary["result"]["content"][0]["text"])["final_macro_f1"] == 0.33

    report = mcp_server.handle(
        _request("tools/call", {"name": "pattern_report", "arguments": {"run": str(run)}})
    )
    data = json.loads(report["result"]["content"][0]["text"])
    assert data["gate"]["rounds"] == 50
    assert data["structure"]["saturated_rounds"] == 3


def test_serve_round_trips_one_request(monkeypatch):
    import io

    source = io.StringIO(json.dumps(_request("ping")) + "\n")
    sink = io.StringIO()
    mcp_server.serve(source, sink)
    assert json.loads(sink.getvalue())["result"] == {}
