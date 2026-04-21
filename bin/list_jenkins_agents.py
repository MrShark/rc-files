#!/usr/bin/env python3
"""
List Azure VM agent templates from a Jenkins server and emit them as CSV.

Usage:
    export JENKINS_USER="myuser"
    export JENKINS_TOKEN="11abc..."
    python list_jenkins_agents.py [--url URL] [-o OUTPUT]
"""

import argparse
import base64
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

JENKINS_USER = os.getenv("JENKINS_USER")
if not JENKINS_USER:
    msg = "JENKINS_USER not set"
    raise SystemExit(msg)

JENKINS_TOKEN = os.getenv("JENKINS_TOKEN")
if not JENKINS_TOKEN:
    msg = "JENKINS_TOKEN not set"
    raise SystemExit(msg)

# Preferred column order. Columns found in the data that are not listed here
# are appended alphabetically after these.
PREFERRED_COLUMNS = [
    "cloud_name",
    "templateName",
    "templateDesc",
    "labels",
    "vm_size",
    "os_type",
    "image_type",
    "galleryImageDefinition",
    "galleryImageVersion",
    "galleryImageSpecialized",
    "javaPath",
]

# Columns to exclude from the CSV output entirely.
HIDDEN_COLUMNS: set[str] = {
    "initScript",
    "terminateScript",
    "labelDataSet",
    "templateStatusDetails",
}

# Groovy script executed on the Jenkins script console.
# Uses metaClass introspection to capture every readable property on each
# AzureVMAgentTemplate, then flattens the retentionStrategy into three
# scalar columns.  Returns a JSON array of maps.
_GROOVY_SCRIPT = """\
import com.microsoft.azure.vmagent.AzureVMCloud
import groovy.json.JsonOutput

// Convert a value to a JSON-safe scalar.
def scalar = { val ->
    if (val == null) return ""
    if (val instanceof String || val instanceof Number || val instanceof Boolean) return val
    return val.toString()
}

def result = []
Jenkins.instance.clouds.each { cloud ->
    if (!(cloud instanceof AzureVMCloud)) return
    cloud.vmTemplates.each { t ->
        def row = [cloud_name: cloud.cloudName]
        // Reflect all readable properties from the template object.
        t.metaClass.properties.each { mp ->
            if (mp.name == 'class') return
            try {
                row[mp.name] = scalar(mp.getProperty(t))
            } catch (ignore) {
                row[mp.name] = ""
            }
        }
        // Replace the complex retentionStrategy object with flat scalar columns.
        row.remove('retentionStrategy')
        def rs = t.retentionStrategy
        row['retention_strategy']     = rs?.class?.simpleName ?: ""
        row['retention_time_minutes'] = rs?.hasProperty('retentionTimeInMin') ? (rs.retentionTimeInMin ?: "") : ""
        row['pool_size']              = rs?.hasProperty('poolSize')            ? (rs.poolSize            ?: "") : ""
        result << row
    }
}
println JsonOutput.toJson(result)
"""


def _build_auth_header(user: str, token: str) -> str:
    credentials = base64.b64encode(f"{user}:{token}".encode()).decode()
    return f"Basic {credentials}"


def _post_script(base_url: str, auth_header: str, groovy_code: str) -> str:
    """POST groovy_code to the Jenkins script console and return the response body."""
    endpoint = f"{base_url.rstrip('/')}/scriptText"
    body = urllib.parse.urlencode({"script": groovy_code}).encode()
    req = urllib.request.Request(  # noqa: S310
        endpoint,
        data=body,
        headers={
            "Authorization": auth_header,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310
        return response.read().decode()


def _write_csv(templates: list[dict], fieldnames: list[str], dest: Any) -> None:  # noqa: ANN401
    writer = csv.DictWriter(
        dest,
        fieldnames=fieldnames,
        extrasaction="ignore",
        restval="",
        lineterminator="\n",
        dialect="excel",
        delimiter=";",
    )
    writer.writeheader()
    writer.writerows(templates)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Azure VM agent templates from Jenkins as CSV."
    )
    parser.add_argument(
        "--url",
        default="https://build.rd.consafe1.org/",
        help="Jenkins base URL (default: https://build.rd.consafe1.org/)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="Write CSV to FILE instead of stdout",
    )
    args = parser.parse_args()

    auth_header = _build_auth_header(JENKINS_USER, JENKINS_TOKEN)
    raw = _post_script(args.url, auth_header, _GROOVY_SCRIPT)
    templates = json.loads(raw)

    all_keys: set[str] = set()
    for row in templates:
        all_keys.update(row.keys())
    visible_keys = all_keys - HIDDEN_COLUMNS
    preferred = [c for c in PREFERRED_COLUMNS if c in visible_keys]
    extra = sorted(visible_keys - set(PREFERRED_COLUMNS))
    fieldnames = preferred + extra

    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as fh:  # noqa: PTH123
            _write_csv(templates, fieldnames, fh)
    else:
        _write_csv(templates, fieldnames, sys.stdout)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.reason}", file=sys.stderr)
        sys.exit(exc.code)
