#!/usr/bin/env python3
"""Compile/package a wrapper-free CloudNet native-runtime module probe.

The probe is injected only into disposable checkouts of exact CloudNet refs.
It proves module/factory/service wiring against both the current released RC
and current nightly source. It does not call TrueNAS or create a runtime.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

UPSTREAM = "https://github.com/CloudNetService/CloudNet.git"
REFS = [
    ("4.0.0-RC17", "f8dc563272f2d4bf59772d0bcaeb713a5cc43ffb"),
    ("nightly", "d74c455f766f25cbd6c7fba051ef4795b90a69c4"),
]
PROJECT = ":modules:collage-truenas:collage-truenas-impl"
RUNTIME = "truenas-native"

BUILD_FILE = r"""plugins {
  id("cloudnet-modules")
}

dependencies {
  compileOnlyApi(projects.node.nodeImpl)
}

moduleJson {
  author = "SupraCraft RDTE"
  main = "org.supracraft.collage.cloudnet.TrueNASNativeModuleProbe"
  description = "COLLAGE compile-only native TrueNAS runtime probe"
  name = "COLLAGE-TrueNAS-Runtime-Probe"
  runtimeModule = true
}
"""

LOG_CACHE = r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.service.ServiceId;
import eu.cloudnetservice.node.config.Configuration;
import eu.cloudnetservice.node.impl.service.defaults.log.AbstractServiceLogCache;

public final class TrueNASNativeLogCacheProbe extends AbstractServiceLogCache {
  public TrueNASNativeLogCacheProbe(Configuration configuration, ServiceId serviceId) {
    super(configuration, serviceId);
  }
}
"""

SERVICE = r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.event.EventManager;
import eu.cloudnetservice.driver.language.I18n;
import eu.cloudnetservice.driver.service.ServiceConfiguration;
import eu.cloudnetservice.node.config.Configuration;
import eu.cloudnetservice.node.impl.service.InternalCloudServiceManager;
import eu.cloudnetservice.node.impl.service.defaults.AbstractService;
import eu.cloudnetservice.node.impl.tick.DefaultTickLoop;
import eu.cloudnetservice.node.impl.version.ServiceVersionProvider;
import eu.cloudnetservice.node.service.ServiceConfigurationPreparer;
import eu.cloudnetservice.node.service.ServiceConsoleLogCache;

public final class TrueNASNativeServiceProbe extends AbstractService {
  private volatile boolean observedAlive;

  public TrueNASNativeServiceProbe(
    I18n i18n,
    DefaultTickLoop tickLoop,
    Configuration nodeConfig,
    ServiceConfiguration configuration,
    InternalCloudServiceManager manager,
    EventManager eventManager,
    ServiceConsoleLogCache logCache,
    ServiceVersionProvider versionProvider,
    ServiceConfigurationPreparer serviceConfigurationPreparer
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
    // External native runtime owns its files/world. No wrapper preparation.
  }

  @Override
  protected void startProcess() {
    // Real adapter: observe -> plan -> apply -> verify through TrueNAS Apps API.
    this.observedAlive = true;
  }

  @Override
  protected void stopProcess() {
    this.observedAlive = false;
  }

  @Override
  protected void doDelete() {
    // Real adapter deletes only the owned runtime object, never world data.
    this.observedAlive = false;
  }

  @Override
  public void runCommand(String command) {
    // Application-plane command transport is a separate qualification gate.
  }

  @Override
  public String runtime() {
    return "truenas-native";
  }

  @Override
  public boolean alive() {
    return this.observedAlive;
  }
}
"""

FACTORY = r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.event.EventManager;
import eu.cloudnetservice.driver.language.I18n;
import eu.cloudnetservice.driver.registry.Service;
import eu.cloudnetservice.driver.service.ServiceConfiguration;
import eu.cloudnetservice.node.config.Configuration;
import eu.cloudnetservice.node.impl.service.InternalCloudServiceManager;
import eu.cloudnetservice.node.impl.service.defaults.factory.BaseLocalCloudServiceFactory;
import eu.cloudnetservice.node.impl.tick.DefaultTickLoop;
import eu.cloudnetservice.node.impl.version.ServiceVersionProvider;
import eu.cloudnetservice.node.service.CloudService;
import eu.cloudnetservice.node.service.CloudServiceManager;
import jakarta.inject.Inject;
import jakarta.inject.Singleton;

@Singleton
public final class TrueNASNativeFactoryProbe extends BaseLocalCloudServiceFactory {
  private final I18n i18n;
  private final DefaultTickLoop tickLoop;
  private final EventManager eventManager;

  @Inject
  public TrueNASNativeFactoryProbe(
    @Service I18n i18n,
    DefaultTickLoop tickLoop,
    Configuration nodeConfig,
    EventManager eventManager,
    ServiceVersionProvider versionProvider
  ) {
    super(nodeConfig, versionProvider);
    this.i18n = i18n;
    this.tickLoop = tickLoop;
    this.eventManager = eventManager;
  }

  @Override
  public CloudService createCloudService(
    CloudServiceManager manager,
    ServiceConfiguration configuration
  ) {
    var config = this.validateConfiguration(manager, configuration);
    var preparer = manager.servicePreparer(config.serviceId().environment());
    var logCache = new TrueNASNativeLogCacheProbe(this.configuration, config.serviceId());
    return new TrueNASNativeServiceProbe(
      this.i18n,
      this.tickLoop,
      this.configuration,
      config,
      (InternalCloudServiceManager) manager,
      this.eventManager,
      logCache,
      this.versionProvider,
      preparer);
  }

  @Override
  public String name() {
    return "truenas-native";
  }
}
"""

MODULE = r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.inject.InjectionLayer;
import eu.cloudnetservice.driver.module.ModuleLifeCycle;
import eu.cloudnetservice.driver.module.ModuleTask;
import eu.cloudnetservice.driver.module.driver.DriverModule;
import eu.cloudnetservice.node.service.CloudServiceManager;
import jakarta.inject.Named;
import jakarta.inject.Singleton;

@Singleton
public final class TrueNASNativeModuleProbe extends DriverModule {
  @ModuleTask(order = 22)
  public void registerFactory(
    CloudServiceManager serviceManager,
    @Named("module") InjectionLayer<?> moduleInjectionLayer
  ) {
    var factory = moduleInjectionLayer.instance(TrueNASNativeFactoryProbe.class);
    serviceManager.addCloudServiceFactory("truenas-native", factory);
  }

  @ModuleTask(lifecycle = ModuleLifeCycle.STOPPED)
  public void unregisterFactory(CloudServiceManager serviceManager) {
    serviceManager.removeCloudServiceFactory("truenas-native");
  }
}
"""

class ProbeError(RuntimeError):
    pass

def run(cmd: list[str], cwd: Path, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), file=sys.stderr)
    try:
        cp = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ProbeError("timeout: " + " ".join(cmd)) from exc
    if cp.returncode:
        stdout = cp.stdout or ""
        stderr = cp.stderr or ""
        marker = stdout.find("* What went wrong:")
        if marker < 0:
            marker = stdout.find("FAILURE:")
        if marker < 0:
            marker = max(0, len(stdout) - 16000)
        detail = stdout[marker:marker + 20000]
        if stderr:
            detail += "\n--- STDERR TAIL ---\n" + stderr[-5000:]
        raise ProbeError(f"command failed ({cp.returncode}): {' '.join(cmd)}\n{detail}")
    return cp

def inject_project(checkout: Path) -> None:
    settings = checkout / "settings.gradle.kts"
    text = settings.read_text(encoding="utf-8")
    needle = 'include("bom")'
    stanza = '''registerSubProjects(
  root = "modules:collage-truenas",
  prefix = "collage-truenas",
  subProjects = arrayOf("impl"),
)

'''
    if needle not in text:
        raise ProbeError("CloudNet settings insertion point changed")
    settings.write_text(text.replace(needle, stanza + needle, 1), encoding="utf-8")

    root = checkout / "modules/collage-truenas/impl"
    java = root / "src/main/java/org/supracraft/collage/cloudnet"
    java.mkdir(parents=True, exist_ok=True)
    (root / "build.gradle.kts").write_text(BUILD_FILE, encoding="utf-8")
    (java / "TrueNASNativeLogCacheProbe.java").write_text(LOG_CACHE, encoding="utf-8")
    (java / "TrueNASNativeServiceProbe.java").write_text(SERVICE, encoding="utf-8")
    (java / "TrueNASNativeFactoryProbe.java").write_text(FACTORY, encoding="utf-8")
    (java / "TrueNASNativeModuleProbe.java").write_text(MODULE, encoding="utf-8")

def qualify_ref(label: str, ref: str, temp: Path) -> dict:
    checkout = temp / label
    run(["git", "init", "--quiet", str(checkout)], temp)
    run(["git", "-C", str(checkout), "remote", "add", "origin", UPSTREAM], temp)
    run(["git", "-C", str(checkout), "fetch", "--quiet", "--depth", "1", "origin", ref], temp)
    run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", "FETCH_HEAD"], temp)
    actual = run(["git", "-C", str(checkout), "rev-parse", "HEAD"], temp).stdout.strip()
    if actual != ref:
        raise ProbeError(f"{label}: checkout mismatch {actual}")

    inject_project(checkout)
    gradle = run(
        ["./gradlew", PROJECT + ":jar", "--no-daemon", "--console=plain"],
        checkout,
        timeout=1800,
    )

    libs = checkout / "modules/collage-truenas/impl/build/libs"
    jars = [p for p in libs.glob("*.jar") if "sources" not in p.name and "javadoc" not in p.name]
    if len(jars) != 1:
        raise ProbeError(f"{label}: expected exactly one module jar, got {[p.name for p in jars]}")
    jar = jars[0]
    with zipfile.ZipFile(jar) as zf:
        names = zf.namelist()
        module_entries = [n for n in names if n.endswith("module.json")]
        if len(module_entries) != 1:
            raise ProbeError(f"{label}: module metadata missing/ambiguous: {module_entries}")
        module_json = json.loads(zf.read(module_entries[0]).decode("utf-8"))

    main = module_json.get("main")
    if main != "org.supracraft.collage.cloudnet.TrueNASNativeModuleProbe":
        raise ProbeError(f"{label}: unexpected module main {main!r}")
    if module_json.get("runtimeModule") is not True:
        raise ProbeError(f"{label}: runtimeModule flag missing")
    if RUNTIME.encode() not in jar.read_bytes():
        raise ProbeError(f"{label}: runtime identifier not present in packaged module")

    return {
        "label": label,
        "ref": ref,
        "result": "PASS",
        "gradle_task": PROJECT + ":jar",
        "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        "module_entry": module_entries[0],
        "module_main": main,
        "runtime_module": module_json.get("runtimeModule"),
        "build_output_tail": (gradle.stdout or "")[-1600:],
    }

def main() -> int:
    for tool in ("git", "java"):
        if not shutil.which(tool):
            print(f"ERROR: missing tool {tool}", file=sys.stderr)
            return 2

    temp = Path(tempfile.mkdtemp(prefix="collage-cloudnet-module-"))
    try:
        results = [qualify_ref(label, ref, temp) for label, ref in REFS]
        evidence = {
            "schema_version": 1,
            "experiment": "EXP-000-CLOUDNET-001 registered-module-spike",
            "result": "PASS",
            "upstream": UPSTREAM,
            "refs": results,
            "proven": [
                "a separate CloudNet module project can register a named native runtime factory without modifying CloudNet runtime core",
                "the factory can construct a wrapper-free AbstractService subclass",
                "module metadata packages the probe as a CloudNet runtime module",
                "the same source shape compiles/packages against current released RC17 and current nightly source",
            ],
            "non_claims": [
                "no TrueNAS API calls",
                "no live CloudNet node",
                "no native app adoption/reconciliation",
                "no world lifecycle qualification",
                "no controller-loss qualification",
            ],
            "next": "replace compile stubs with a narrow TrueNAS Apps client boundary, then run non-mutating contract tests before any live rep",
        }
        payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        Path("cloudnet-registered-module-spike-evidence.json").write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (ProbeError, OSError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(temp, ignore_errors=True)

if __name__ == "__main__":
    raise SystemExit(main())
