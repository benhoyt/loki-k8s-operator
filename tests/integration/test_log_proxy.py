#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from helpers import loki_alerts, loki_api_query, oci_image

logger = logging.getLogger(__name__)

resources = {"loki-image": oci_image("./metadata.yaml", "loki-image")}
tester_resources = {
    "workload-image": oci_image(
        "./tests/integration/log-proxy-tester/metadata.yaml", "workload-image"
    )
}


@pytest.mark.abort_on_fail
async def test_alert_rules_do_fire_from_log_proxy(ops_test, loki_charm, log_proxy_tester_charm):
    """Test basic functionality of Log Proxy."""
    loki_app_name = "loki"
    tester_app_name = "log-proxy-tester"
    app_names = [loki_app_name, tester_app_name]

    await asyncio.gather(
        ops_test.model.deploy(
            loki_charm,
            resources=resources,
            application_name=loki_app_name,
            trust=True,
        ),
        ops_test.model.deploy(
            log_proxy_tester_charm,
            resources=tester_resources,
            application_name=tester_app_name,
        ),
    )
    await ops_test.model.wait_for_idle(apps=app_names, status="active")

    await ops_test.model.add_relation(loki_app_name, tester_app_name)
    await ops_test.model.wait_for_idle(apps=[loki_app_name, tester_app_name], status="active")

    # Trigger a log message to fire an alert on
    await ops_test.model.applications[tester_app_name].set_config({"rate": "5"})
    alerts = await loki_alerts(ops_test, "loki")
    assert all(
        key in alert["labels"].keys()
        for key in ["juju_application", "juju_model", "juju_model_uuid"]
        for alert in alerts
    )
    await ops_test.model.applications[tester_app_name].remove()
    await ops_test.model.block_until(
        lambda: tester_app_name not in ops_test.model.applications, timeout=300
    )


@pytest.mark.abort_on_fail
async def test_logproxy_file_logs(ops_test, log_proxy_tester_charm):
    """Make sure Loki endpoints propagate on scaling."""
    loki_app_name = "loki"
    tester_app_name = "log-proxy-tester-file"

    await ops_test.model.deploy(
        log_proxy_tester_charm,
        resources=tester_resources,
        application_name=tester_app_name,
    )
    await ops_test.model.block_until(
        lambda: (
            len(ops_test.model.applications[loki_app_name].units) > 0
            and len(ops_test.model.applications[tester_app_name].units) > 0
        )
    )
    await ops_test.model.add_relation(loki_app_name, tester_app_name)
    await ops_test.model.wait_for_idle(apps=[loki_app_name, tester_app_name], status="active")

    logs = await loki_api_query(
        ops_test, loki_app_name, f'{{juju_application=~"{tester_app_name}",filename=~".+"}}'
    )
    assert len(logs[0]["values"]) > 0


@pytest.mark.abort_on_fail
async def test_logproxy_syslog_logs(ops_test, log_proxy_tester_charm):
    """Make sure Loki endpoints propagate on scaling."""
    loki_app_name = "loki"
    tester_app_name = "log-proxy-tester-syslog"

    await ops_test.model.deploy(
        log_proxy_tester_charm,
        resources=tester_resources,
        application_name=tester_app_name,
        config={"syslog": "true", "file_forwarding": "false"},
    )
    await ops_test.model.block_until(
        lambda: (
            len(ops_test.model.applications[loki_app_name].units) > 0
            and len(ops_test.model.applications[tester_app_name].units) > 0
        )
    )
    await ops_test.model.add_relation(loki_app_name, tester_app_name)
    await ops_test.model.wait_for_idle(apps=[loki_app_name, tester_app_name], status="active")

    logs = await loki_api_query(
        ops_test, loki_app_name, f'{{juju_application=~"{tester_app_name}",job=~".+syslog"}}'
    )

    # Default syslog labels and one structured one to remap
    syslog_labels = ["facility", "hostname", "severity", "timeQuality_syncAccuracy"]
    assert all([label in logs[0]["stream"] for label in syslog_labels])
    assert len(logs[0]["values"]) > 0


@pytest.mark.abort_on_fail
async def test_logproxy_logs_to_file_and_syslog(ops_test, log_proxy_tester_charm):
    """Make sure Loki endpoints propagate on scaling."""
    loki_app_name = "loki"
    tester_app_name = "log-proxy-tester-both"

    await ops_test.model.deploy(
        log_proxy_tester_charm,
        resources=tester_resources,
        application_name=tester_app_name,
        config={
            "syslog": "true",
        },
    )
    await ops_test.model.block_until(
        lambda: (
            len(ops_test.model.applications[loki_app_name].units) > 0
            and len(ops_test.model.applications[tester_app_name].units) > 0
        )
    )
    await ops_test.model.add_relation(loki_app_name, tester_app_name)
    await ops_test.model.wait_for_idle(apps=[loki_app_name, tester_app_name], status="active")

    syslogs = await loki_api_query(
        ops_test, loki_app_name, f'{{juju_application=~"{tester_app_name}",job=~".+syslog"}}'
    )
    assert len(syslogs[0]["values"]) > 0
    file_logs = await loki_api_query(
        ops_test, loki_app_name, f'{{juju_application=~"{tester_app_name}",filename=~".+"}}'
    )
    assert len(file_logs[0]["values"]) > 0
