#!/usr/bin/env python3
"""Compile-only CloudNet native-runtime spike for EXP-000-CLOUDNET-001.

The probe modifies only a temporary checkout of one exact CloudNet commit.
It adds a minimal AbstractService subclass that deliberately overrides
prepare/start/stop/delete hooks so no CloudNet wrapper payload is required.
No TrueNAS API is contacted and no runtime is created.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

UPSTREAM = "https://github.com/CloudNetService/CloudNet.git"
REF = "d74c455f766f25cbd6c7fba051ef4795b90a69c4"

PROBE = r"""/*
 * COLLAGE EXP-000-CLOUDNET-001 compile probe.
 * This file is injected only into a disposable exact-source checkout.
 */
package eu.cloudnetservice.node.impl.service.defaults;

import eu.cloudnetservice.driver.event.EventManager;
import eu.cloudnetservice.driver.language.I18n;
import eu.cloudnetservice.driver.service.ServiceConfiguration;
import eu.cloudnetservice.node.config.Configuration;
import eu.cloudnetservice.node.impl.service.InternalCloudServiceManager;
import eu.cloudnetservice.node.impl.tick.DefaultTickLoop;
import eu.cloudnetservice.node.impl.version.ServiceVersionProvider;
import eu.cloudnetservice.node.service.ServiceConfigurationPreparer;
import eu.cloudnetservice.node.service.ServiceConsoleLogCache;
import lombok.NonNull;

public final class TrueNASNativeServiceCompileProbe extends AbstractService {

  public TrueNASNativeServiceCompileProbe(
    @NonNull I18n i18n,
    @NonNull DefaultTickLoop tickLoop,
    @NonNull Configuration nodeConfig,
    @NonNull ServiceConfiguration configuration,
    @NonNull InternalCloudServiceManager manager,
    @NonNull EventManager eventManager,
    @NonNull ServiceConsoleLogCache logCache,
    @NonNull ServiceVersionProvider versionProvider,
    @NonNull ServiceConfigurationPreparer serviceConfigurationPreparer
  ) {
    super(
      i18n,
      tickLoop,
      nodeConfig,
      configuration,
      manager,
      eventManager,
      logCache,
      versionProvider,
      serviceConfigurationPreparer);
  }

  @Override
  protected void prepareService() {
    // Native runtime owns its own files/world. Deliberately bypass CloudNet
    // wrapper config, templates, inclusions and plugin-directory preparation.
  }

  @Override
  protected void startProcess() {
    // A real adapter would call the supported TrueNAS App lifecycle API.
  }

  @Override
  protected void stopProcess() {
    // A real adapter would call the supported TrueNAS App lifecycle API.
  }

  @Override
  protected void doDelete() {
    // A real adapter would delete only the owned runtime object, never world data.
  }

  @Override
  public void runCommand(@NonNull String command) {
    // Application-plane control must be separately qualified.
  }

  @Override
  public @NonNull String runtime() {
    return "truenas-native";
  }

  @Override
  public boolean alive() {
    // A real adapter would observe native TrueNAS App state.
    return false;
  }
}
"""

class SpikeError(RuntimeError):
    pass

def run(cmd: list[str], cwd: Path, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), file=sys.stderr)
    try:
        cp = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise SpikeError(f"timeout running {' '.join(cmd)}") from exc
    if cp.returncode:
        combined = (cp.stdout or "") + "\n--- STDERR ---\n" + (cp.stderr or "")
        detail = combined[-16000:]
        raise SpikeError(f"command failed ({cp.returncode}): {' '.join(cmd)}\n{detail}")
    return cp

def main() -> int:
    for tool in ("git", "java"):
        if not shutil.which(tool):
            print(f"ERROR: missing tool {tool}", file=sys.stderr)
            return 2

    temp = Path(tempfile.mkdtemp(prefix="collage-cloudnet-spike-"))
    evidence_path = Path("cloudnet-native-service-spike-evidence.json")
    try:
        checkout = temp / "CloudNet"
        run(["git", "init", "--quiet", str(checkout)], temp)
        run(["git", "-C", str(checkout), "remote", "add", "origin", UPSTREAM], temp)
        run(["git", "-C", str(checkout), "fetch", "--quiet", "--depth", "1", "origin", REF], temp)
        run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", "FETCH_HEAD"], temp)
        actual = run(["git", "-C", str(checkout), "rev-parse", "HEAD"], temp).stdout.strip()
        if actual != REF:
            raise SpikeError(f"upstream ref mismatch: {actual}")

        target = checkout / "node/impl/src/main/java/eu/cloudnetservice/node/impl/service/defaults/TrueNASNativeServiceCompileProbe.java"
        target.write_text(PROBE, encoding="utf-8")

        java_version = run(["java", "-version"], checkout).stderr.strip().splitlines()[0]
        gradle = run(
            ["./gradlew", ":node:impl:compileJava", "--no-daemon", "--console=plain"],
            checkout,
            timeout=1800,
        )

        evidence = {
            "schema_version": 1,
            "result": "PASS",
            "experiment": "EXP-000-CLOUDNET-001 minimal-adapter-spike",
            "upstream": {"repository": UPSTREAM, "ref": REF},
            "java": java_version,
            "gradle_task": ":node:impl:compileJava",
            "probe_sha256": hashlib.sha256(PROBE.encode()).hexdigest(),
            "proven": [
                "an AbstractService subclass can compile against exact CloudNet source without patching CloudNet core",
                "prepareService can be overridden to bypass wrapper/template/inclusion preparation",
                "startProcess and stopProcess can be overridden for external native lifecycle delegation",
                "doDelete can be overridden for native-runtime-only deletion semantics",
                "runtime and alive observation can be supplied by the adapter",
            ],
            "not_proven": [
                "factory/module wiring",
                "service registration without CloudNet wrapper connection",
                "TrueNAS API lifecycle calls",
                "post-CloudNet native app operability",
                "world independence",
                "adapter thinness overall",
            ],
            "next": "compile a registered runtime factory/module and prove wrapper-free local registration path",
            "gradle_output_tail": (gradle.stdout or "")[-2000:],
        }
        payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        evidence_path.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (SpikeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(temp, ignore_errors=True)

if __name__ == "__main__":
    raise SystemExit(main())
