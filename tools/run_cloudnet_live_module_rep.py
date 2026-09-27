#!/usr/bin/env python3
"""Run a live disposable CloudNet module-load rep for EXP-000-CLOUDNET-001.

This uses the released CloudNet 4.0.0-RC17 container, verifies its OCI revision,
injects the already-qualified native-runtime module shape, starts a real node
with an empty pre-existing config (so no interactive setup/tasks are created),
proves the truenas-native factory is registered, then retires the container.

No TrueNAS endpoint or credential is used.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

UPSTREAM = "https://github.com/CloudNetService/CloudNet.git"
REF = "f8dc563272f2d4bf59772d0bcaeb713a5cc43ffb"
IMAGE = "cloudnetservice/cloudnet:4.0.0-RC17"
PROJECT = ":modules:collage-truenas-live:collage-truenas-live-impl"
CONTAINER = "collage-cloudnet-live-probe"
RUNTIME = "truenas-native"

BUILD_FILE = r"""plugins {
  id("cloudnet-modules")
}

dependencies {
  compileOnlyApi(projects.node.nodeImpl)
}

moduleJson {
  author = "SupraCraft RDTE"
  main = "org.supracraft.collage.cloudnet.TrueNASLiveProbeModule"
  description = "COLLAGE live native runtime registration probe"
  name = "COLLAGE-TrueNAS-Live-Probe"
  runtimeModule = true
}
"""

LOG_CACHE = r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.service.ServiceId;
import eu.cloudnetservice.node.config.Configuration;
import eu.cloudnetservice.node.impl.service.defaults.log.AbstractServiceLogCache;

public final class TrueNASLiveProbeLogCache extends AbstractServiceLogCache {
  public TrueNASLiveProbeLogCache(Configuration configuration, ServiceId serviceId) {
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

public final class TrueNASLiveProbeService extends AbstractService {
  private volatile boolean observedAlive;

  public TrueNASLiveProbeService(
    I18n i18n,
    DefaultTickLoop tickLoop,
    Configuration nodeConfig,
    ServiceConfiguration configuration,
    InternalCloudServiceManager manager,
    EventManager eventManager,
    ServiceConsoleLogCache logCache,
    ServiceVersionProvider versionProvider,
    ServiceConfigurationPreparer preparer
  ) {
    super(i18n, tickLoop, nodeConfig, configuration, manager, eventManager, logCache, versionProvider, preparer);
  }

  @Override protected void prepareService() {}
  @Override protected void startProcess() { this.observedAlive = true; }
  @Override protected void stopProcess() { this.observedAlive = false; }
  @Override protected void doDelete() { this.observedAlive = false; }
  @Override public void runCommand(String command) {}
  @Override public String runtime() { return "truenas-native"; }
  @Override public boolean alive() { return this.observedAlive; }
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
public final class TrueNASLiveProbeFactory extends BaseLocalCloudServiceFactory {
  private final I18n i18n;
  private final DefaultTickLoop tickLoop;
  private final EventManager eventManager;

  @Inject
  public TrueNASLiveProbeFactory(
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
  public CloudService createCloudService(CloudServiceManager manager, ServiceConfiguration configuration) {
    var config = this.validateConfiguration(manager, configuration);
    var preparer = manager.servicePreparer(config.serviceId().environment());
    var logCache = new TrueNASLiveProbeLogCache(this.configuration, config.serviceId());
    return new TrueNASLiveProbeService(
      this.i18n, this.tickLoop, this.configuration, config,
      (InternalCloudServiceManager) manager, this.eventManager, logCache,
      this.versionProvider, preparer);
  }

  @Override public String name() { return "truenas-native"; }
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
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

@Singleton
public final class TrueNASLiveProbeModule extends DriverModule {
  private static final String RUNTIME = "truenas-native";
  private static final Path SENTINEL = Path.of("collage-runtime-live.json");

  @ModuleTask(order = 22)
  public void registerFactory(
    CloudServiceManager manager,
    @Named("module") InjectionLayer<?> layer
  ) throws Exception {
    var factory = layer.instance(TrueNASLiveProbeFactory.class);
    manager.addCloudServiceFactory(RUNTIME, factory);
    var observed = manager.cloudServiceFactory(RUNTIME);
    if (observed == null || observed != factory) {
      throw new IllegalStateException("runtime factory registration did not read back exactly");
    }
    String body = "{\"schema_version\":1,\"result\":\"PASS\","
      + "\"runtime\":\"" + RUNTIME + "\","
      + "\"factory_class\":\"" + observed.getClass().getName() + "\"}\n";
    Files.writeString(
      SENTINEL,
      body,
      StandardOpenOption.CREATE,
      StandardOpenOption.TRUNCATE_EXISTING,
      StandardOpenOption.WRITE);
  }

  @ModuleTask(lifecycle = ModuleLifeCycle.STOPPED)
  public void unregisterFactory(CloudServiceManager manager) {
    manager.removeCloudServiceFactory(RUNTIME);
  }
}
"""

class RepError(RuntimeError):
    pass

def run(cmd: list[str], cwd: Path | None = None, timeout: int = 1800, check: bool = True):
    print("+ " + " ".join(cmd), file=sys.stderr)
    try:
        cp = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RepError("timeout: " + " ".join(cmd)) from exc
    if check and cp.returncode:
        detail = ((cp.stdout or "") + "\n--- STDERR ---\n" + (cp.stderr or ""))[-24000:]
        raise RepError(f"command failed ({cp.returncode}): {' '.join(cmd)}\n{detail}")
    return cp

def inject(checkout: Path) -> Path:
    settings = checkout / "settings.gradle.kts"
    text = settings.read_text(encoding="utf-8")
    needle = 'include("bom")'
    stanza = '''registerSubProjects(
  root = "modules:collage-truenas-live",
  prefix = "collage-truenas-live",
  subProjects = arrayOf("impl"),
)

'''
    if needle not in text:
        raise RepError("settings insertion point changed")
    settings.write_text(text.replace(needle, stanza + needle, 1), encoding="utf-8")

    root = checkout / "modules/collage-truenas-live/impl"
    java = root / "src/main/java/org/supracraft/collage/cloudnet"
    java.mkdir(parents=True, exist_ok=True)
    (root / "build.gradle.kts").write_text(BUILD_FILE, encoding="utf-8")
    (java / "TrueNASLiveProbeLogCache.java").write_text(LOG_CACHE, encoding="utf-8")
    (java / "TrueNASLiveProbeService.java").write_text(SERVICE, encoding="utf-8")
    (java / "TrueNASLiveProbeFactory.java").write_text(FACTORY, encoding="utf-8")
    (java / "TrueNASLiveProbeModule.java").write_text(MODULE, encoding="utf-8")

    run(["./gradlew", PROJECT + ":jar", "--no-daemon", "--console=plain"], checkout)
    libs = root / "build/libs"
    jars = [p for p in libs.glob("*.jar") if "sources" not in p.name and "javadoc" not in p.name]
    if len(jars) != 1:
        raise RepError(f"expected one probe jar; got {[p.name for p in jars]}")
    return jars[0]

def main() -> int:
    for tool in ("git", "java", "docker"):
        if not shutil.which(tool):
            print(f"ERROR: missing tool {tool}", file=sys.stderr)
            return 2

    temp = Path(tempfile.mkdtemp(prefix="collage-cloudnet-live-"))
    log_path = Path("cloudnet-live-module.log")
    evidence_path = Path("cloudnet-live-module-evidence.json")
    derived = "collage/cloudnet-live-probe:" + REF[:12]
    try:
        checkout = temp / "CloudNet"
        run(["git", "init", "--quiet", str(checkout)], temp)
        run(["git", "-C", str(checkout), "remote", "add", "origin", UPSTREAM], temp)
        run(["git", "-C", str(checkout), "fetch", "--quiet", "--depth", "1", "origin", REF], temp)
        run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", "FETCH_HEAD"], temp)
        actual = run(["git", "-C", str(checkout), "rev-parse", "HEAD"], temp).stdout.strip()
        if actual != REF:
            raise RepError(f"source ref mismatch: {actual}")

        module_jar = inject(checkout)

        run(["docker", "pull", IMAGE], temp, timeout=1200)
        revision = run(
            ["docker", "image", "inspect", IMAGE, "--format", "{{ index .Config.Labels \"org.opencontainers.image.revision\" }}"],
            temp).stdout.strip()
        if revision != REF:
            raise RepError(f"released image revision mismatch: {revision!r} != {REF!r}")

        stage = temp / "derived"
        (stage / "modules").mkdir(parents=True)
        shutil.copy2(module_jar, stage / "modules" / "COLLAGE-TrueNAS-Live-Probe.jar")
        (stage / "config.json").write_text("{}\n", encoding="utf-8")
        (stage / "Dockerfile").write_text(
            f"""FROM {IMAGE}
USER root
COPY --chown=cloudnet:cloudnet modules/ /home/cloudnet/modules/
COPY --chown=cloudnet:cloudnet config.json /home/cloudnet/config.json
ENV JAVA_TOOL_OPTIONS="-Dcloudnet.installation.skip=true"
ENV JAVA_TOOL_OPTIONS="-Dcloudnet.installation.skip=true"
USER cloudnet
""",
            encoding="utf-8")

        run(["docker", "build", "-t", derived, "."], stage, timeout=600)
        run(["docker", "rm", "-f", CONTAINER], temp, check=False)
        run(["docker", "create", "--name", CONTAINER, derived], temp)
        run(["docker", "start", CONTAINER], temp)

        deadline = time.monotonic() + 120
        sentinel = temp / "sentinel.json"
        observed = None
        while time.monotonic() < deadline:
            cp = run(
                ["docker", "cp", f"{CONTAINER}:/home/cloudnet/collage-runtime-live.json", str(sentinel)],
                temp, check=False)
            if cp.returncode == 0 and sentinel.is_file():
                observed = json.loads(sentinel.read_text(encoding="utf-8"))
                break
            state = run(
                ["docker", "inspect", CONTAINER, "--format", "{{.State.Status}} {{.State.ExitCode}}"],
                temp).stdout.strip()
            if state.startswith("exited"):
                break
            time.sleep(2)

        logs = run(["docker", "logs", CONTAINER], temp, check=False)
        log_text = (logs.stdout or "") + (logs.stderr or "")
        log_path.write_text(log_text[-30000:], encoding="utf-8")

        if not isinstance(observed, dict) or observed.get("result") != "PASS":
            state = run(
                ["docker", "inspect", CONTAINER, "--format", "{{json .State}}"],
                temp, check=False).stdout.strip()
            diagnostic = log_text[-16000:]
            raise RepError(
                "live node did not emit exact runtime registration sentinel"
                + "\ncontainer_state=" + state
                + "\n--- CLOUDNET LOG TAIL ---\n" + diagnostic)
        if observed.get("runtime") != RUNTIME:
            raise RepError(f"unexpected runtime in sentinel: {observed!r}")

        state_before_stop = run(
            ["docker", "inspect", CONTAINER, "--format", "{{.State.Status}}"],
            temp).stdout.strip()
        if state_before_stop != "running":
            raise RepError(f"node was not running after module registration: {state_before_stop}")

        run(["docker", "stop", "--time", "15", CONTAINER], temp, timeout=60)
        exit_code = int(run(
            ["docker", "inspect", CONTAINER, "--format", "{{.State.ExitCode}}"],
            temp).stdout.strip())

        evidence = {
            "schema_version": 1,
            "experiment": "EXP-000-CLOUDNET-001 live-module",
            "result": "PASS",
            "upstream": {"repository": UPSTREAM, "ref": REF},
            "runtime_image": {"image": IMAGE, "oci_revision": revision},
            "observed": observed,
            "node_state_after_registration": state_before_stop,
            "container_exit_code_after_stop": exit_code,
            "proven": [
                "released CloudNet RC17 node starts as a real disposable process",
                "the external runtime module loads without a CloudNet core fork",
                "truenas-native factory registration reads back exactly from CloudServiceManager",
                "no Minecraft service or TrueNAS API call is needed for module registration",
                "node can be retired after the bounded rep"
            ],
            "non_claims": [
                "no TrueNAS endpoint contacted",
                "no native app created or adopted",
                "no world lifecycle tested",
                "no CloudNet service materialized through the runtime"
            ],
            "next": "add read-only TrueNAS observation and then one disposable native-app lifecycle rep only if least-authority live access is available"
        }
        payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        evidence_path.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (RepError, OSError, json.JSONDecodeError, ValueError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2
    finally:
        run(["docker", "rm", "-f", CONTAINER], temp, check=False)
        run(["docker", "image", "rm", "-f", derived], temp, check=False)
        shutil.rmtree(temp, ignore_errors=True)

if __name__ == "__main__":
    raise SystemExit(main())
