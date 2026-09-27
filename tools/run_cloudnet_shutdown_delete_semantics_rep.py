#!/usr/bin/env python3
"""Qualify CloudNet shutdown/delete semantics for a native external runtime.

This rep uses released CloudNet 4.0.0-RC17 and no TrueNAS endpoint or credential.
It proves whether ordinary service deletion (including graceful node shutdown) is
mechanically distinct from the explicit deleteFiles path.

The probe's deleteFiles override is only a counter. It is NOT a TrueNAS mock.
The experiment asks whether that separate hook is available for a later native
App purge mapping while ordinary CloudNet shutdown can remain stop/detach-only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

UPSTREAM = "https://github.com/CloudNetService/CloudNet.git"
REF = "f8dc563272f2d4bf59772d0bcaeb713a5cc43ffb"
IMAGE = "cloudnetservice/cloudnet:4.0.0-RC17"
PROJECT = ":modules:collage-truenas-shutdown:collage-truenas-shutdown-impl"
CONTAINER = "collage-cloudnet-shutdown-probe"
RUNTIME = "truenas-native"

BUILD_FILE = r"""plugins {
  id("cloudnet-modules")
}

dependencies {
  compileOnlyApi(projects.node.nodeImpl)
}

moduleJson {
  author = "SupraCraft RDTE"
  main = "org.supracraft.collage.cloudnet.TrueNASShutdownProbeModule"
  description = "COLLAGE CloudNet native-runtime shutdown/delete semantics probe"
  name = "COLLAGE-TrueNAS-Shutdown-Probe"
  runtimeModule = true
}
"""

LOG_CACHE = r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.service.ServiceId;
import eu.cloudnetservice.node.config.Configuration;
import eu.cloudnetservice.node.impl.service.defaults.log.AbstractServiceLogCache;

public final class TrueNASShutdownProbeLogCache extends AbstractServiceLogCache {
  public TrueNASShutdownProbeLogCache(Configuration configuration, ServiceId serviceId) {
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

public final class TrueNASShutdownProbeService extends AbstractService {
  private volatile boolean observedAlive;
  private int prepareCount;
  private int startCount;
  private int stopCount;
  private int ordinaryDeleteHookCount;
  private int deleteFilesOverrideCount;

  public TrueNASShutdownProbeService(
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

  @Override protected void prepareService() { this.prepareCount++; }

  @Override
  protected void startProcess() {
    this.startCount++;
    this.observedAlive = true;
  }

  @Override
  protected void stopProcess() {
    this.stopCount++;
    this.observedAlive = false;
  }

  @Override
  protected void doDelete() {
    // Proposed native-runtime meaning: ordinary CloudNet delete detaches the
    // control-plane service and stops an active external runtime, but does not
    // perform the destructive backend-App purge.
    this.ordinaryDeleteHookCount++;
    if (this.observedAlive) {
      this.stopProcess();
    }
  }

  @Override
  public void deleteFiles() {
    // This distinct override is the candidate explicit native-App purge seam.
    // The rep records invocation only; it performs no TrueNAS operation.
    this.deleteFilesOverrideCount++;
    super.deleteFiles();
  }

  @Override public void runCommand(String command) {}
  @Override public String runtime() { return "truenas-native"; }
  @Override public boolean alive() { return this.observedAlive; }

  public int prepareCount() { return this.prepareCount; }
  public int startCount() { return this.startCount; }
  public int stopCount() { return this.stopCount; }
  public int ordinaryDeleteHookCount() { return this.ordinaryDeleteHookCount; }
  public int deleteFilesOverrideCount() { return this.deleteFilesOverrideCount; }
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
public final class TrueNASShutdownProbeFactory extends BaseLocalCloudServiceFactory {
  private final I18n i18n;
  private final DefaultTickLoop tickLoop;
  private final EventManager eventManager;

  @Inject
  public TrueNASShutdownProbeFactory(
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
    var logCache = new TrueNASShutdownProbeLogCache(this.configuration, config.serviceId());
    return new TrueNASShutdownProbeService(
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
import eu.cloudnetservice.driver.provider.CloudServiceFactory;
import eu.cloudnetservice.driver.service.ServiceConfiguration;
import eu.cloudnetservice.driver.service.ServiceCreateResult;
import eu.cloudnetservice.driver.service.ServiceEnvironmentType;
import eu.cloudnetservice.driver.service.ServiceLifeCycle;
import eu.cloudnetservice.node.service.CloudServiceManager;
import jakarta.inject.Named;
import jakarta.inject.Singleton;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

@Singleton
public final class TrueNASShutdownProbeModule extends DriverModule {
  private static final String RUNTIME = "truenas-native";
  private static final Path READY = Path.of("collage-shutdown-ready.json");
  private static final Path SHUTDOWN = Path.of("collage-shutdown-observed.json");

  private TrueNASShutdownProbeService shutdownProbe;
  private CloudServiceManager manager;

  private static void require(boolean condition, String message) {
    if (!condition) {
      throw new IllegalStateException(message);
    }
  }

  private static TrueNASShutdownProbeService createProbe(
    CloudServiceFactory serviceFactory,
    CloudServiceManager manager,
    String taskName,
    int port
  ) {
    var config = ServiceConfiguration.builder()
      .taskName(taskName)
      .environment(ServiceEnvironmentType.MINECRAFT_SERVER)
      .runtime(RUNTIME)
      .maxHeapMemory(64)
      .startPort(port)
      .autoDeleteOnStop(false)
      .staticService(false)
      .build();
    var result = serviceFactory.createCloudService(config);
    require(result.state() == ServiceCreateResult.State.CREATED, taskName + " create failed");
    var service = manager.localCloudService(result.serviceInfo().serviceId().uniqueId());
    require(service instanceof TrueNASShutdownProbeService, taskName + " did not use native runtime");
    return (TrueNASShutdownProbeService) service;
  }

  @ModuleTask(order = 22)
  public void registerAndPrepare(
    CloudServiceManager manager,
    CloudServiceFactory serviceFactory,
    @Named("module") InjectionLayer<?> layer
  ) throws Exception {
    this.manager = manager;
    var factory = layer.instance(TrueNASShutdownProbeFactory.class);
    manager.addCloudServiceFactory(RUNTIME, factory);
    require(manager.cloudServiceFactory(RUNTIME) == factory, "runtime registration read-back failed");

    // First prove that explicit deleteFiles reaches a distinct overridable seam.
    var purgeProbe = createProbe(serviceFactory, manager, "CollagePurge", 25592);
    purgeProbe.start();
    require(purgeProbe.lifeCycle() == ServiceLifeCycle.RUNNING, "purge probe did not start");
    purgeProbe.deleteFiles();
    require(purgeProbe.lifeCycle() == ServiceLifeCycle.DELETED, "deleteFiles did not mark purge probe deleted");
    require(purgeProbe.deleteFilesOverrideCount() == 1, "deleteFiles override did not execute exactly once");
    require(purgeProbe.ordinaryDeleteHookCount() == 1, "deleteFiles did not pass through ordinary delete hook once");
    require(purgeProbe.stopCount() == 1, "deleteFiles did not stop the running purge probe");
    require(manager.localCloudService(purgeProbe.serviceId().uniqueId()) == null,
      "deleteFiles purge probe remained registered");

    // Leave a second service RUNNING. The real CloudNet shutdown handler will
    // decide which service-provider operation is invoked for it.
    this.shutdownProbe = createProbe(serviceFactory, manager, "CollageShutdown", 25593);
    this.shutdownProbe.start();
    require(this.shutdownProbe.lifeCycle() == ServiceLifeCycle.RUNNING, "shutdown probe did not start");
    require(this.shutdownProbe.deleteFilesOverrideCount() == 0, "shutdown probe deleteFiles invoked before shutdown");
    require(!Files.exists(this.shutdownProbe.directory()), "native probe materialized service-directory payload state");

    String ready = "{"
      + "\"schema_version\":1,"
      + "\"result\":\"READY\","
      + "\"runtime\":\"" + RUNTIME + "\","
      + "\"shutdown_service_id\":\"" + this.shutdownProbe.serviceId().uniqueId() + "\","
      + "\"shutdown_service_lifecycle\":\"" + this.shutdownProbe.lifeCycle().name() + "\","
      + "\"purge_delete_files_override_count\":" + purgeProbe.deleteFilesOverrideCount() + ","
      + "\"purge_ordinary_delete_hook_count\":" + purgeProbe.ordinaryDeleteHookCount() + ","
      + "\"purge_stop_count\":" + purgeProbe.stopCount()
      + "}\n";
    Files.writeString(READY, ready, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
  }

  @ModuleTask(lifecycle = ModuleLifeCycle.STOPPED, order = 22)
  public void observeShutdown() throws Exception {
    require(this.shutdownProbe != null, "shutdown probe was not initialized");
    require(this.manager != null, "manager was not captured");

    // DefaultShutdownHandler calls deleteAllCloudServices() before stopAll().
    // If that remains true, the service object should now be DELETED and
    // unregistered, while the distinct deleteFiles override remains untouched.
    require(this.shutdownProbe.lifeCycle() == ServiceLifeCycle.DELETED,
      "graceful CloudNet shutdown did not ordinary-delete the service");
    require(!this.shutdownProbe.alive(), "shutdown probe remained alive");
    require(this.shutdownProbe.ordinaryDeleteHookCount() == 1,
      "ordinary delete hook count during shutdown != 1");
    require(this.shutdownProbe.deleteFilesOverrideCount() == 0,
      "graceful shutdown unexpectedly invoked deleteFiles");
    require(this.shutdownProbe.stopCount() == 1,
      "graceful shutdown did not stop the running service exactly once");
    require(this.manager.localCloudService(this.shutdownProbe.serviceId().uniqueId()) == null,
      "graceful shutdown left service registered");

    String body = "{"
      + "\"schema_version\":1,"
      + "\"result\":\"PASS\","
      + "\"runtime\":\"" + RUNTIME + "\","
      + "\"service_id\":\"" + this.shutdownProbe.serviceId().uniqueId() + "\","
      + "\"lifecycle_after_shutdown_delete\":\"" + this.shutdownProbe.lifeCycle().name() + "\","
      + "\"ordinary_delete_hook_count\":" + this.shutdownProbe.ordinaryDeleteHookCount() + ","
      + "\"delete_files_override_count\":" + this.shutdownProbe.deleteFilesOverrideCount() + ","
      + "\"stop_count\":" + this.shutdownProbe.stopCount() + ","
      + "\"service_unregistered\":true,"
      + "\"destructive_purge_seam_invoked_by_shutdown\":false"
      + "}\n";
    Files.writeString(SHUTDOWN, body, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
    this.manager.removeCloudServiceFactory(RUNTIME);
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
        detail = ((cp.stdout or "") + "\n--- STDERR ---\n" + (cp.stderr or ""))[-30000:]
        raise RepError(f"command failed ({cp.returncode}): {' '.join(cmd)}\n{detail}")
    return cp

def inject(checkout: Path) -> Path:
    settings = checkout / "settings.gradle.kts"
    text = settings.read_text(encoding="utf-8")
    needle = 'include("bom")'
    stanza = '''registerSubProjects(
  root = "modules:collage-truenas-shutdown",
  prefix = "collage-truenas-shutdown",
  subProjects = arrayOf("impl"),
)

'''
    if needle not in text:
        raise RepError("settings insertion point changed")
    settings.write_text(text.replace(needle, stanza + needle, 1), encoding="utf-8")

    root = checkout / "modules/collage-truenas-shutdown/impl"
    java = root / "src/main/java/org/supracraft/collage/cloudnet"
    java.mkdir(parents=True, exist_ok=True)
    (root / "build.gradle.kts").write_text(BUILD_FILE, encoding="utf-8")
    (java / "TrueNASShutdownProbeLogCache.java").write_text(LOG_CACHE, encoding="utf-8")
    (java / "TrueNASShutdownProbeService.java").write_text(SERVICE, encoding="utf-8")
    (java / "TrueNASShutdownProbeFactory.java").write_text(FACTORY, encoding="utf-8")
    (java / "TrueNASShutdownProbeModule.java").write_text(MODULE, encoding="utf-8")

    run(["./gradlew", PROJECT + ":jar", "--no-daemon", "--console=plain"], checkout)
    libs = root / "build/libs"
    jars = [p for p in libs.glob("*.jar") if "sources" not in p.name and "javadoc" not in p.name]
    if len(jars) != 1:
        raise RepError(f"expected one probe jar; got {[p.name for p in jars]}")
    return jars[0]

def copy_json_from_container(temp: Path, container_path: str, local_name: str) -> dict:
    local = temp / local_name
    cp = run(["docker", "cp", f"{CONTAINER}:{container_path}", str(local)], temp, check=False)
    if cp.returncode != 0 or not local.is_file():
        raise RepError(f"missing expected container evidence {container_path}")
    try:
        return json.loads(local.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RepError(f"invalid JSON in {container_path}") from exc

def main() -> int:
    for tool in ("git", "java", "docker"):
        if not shutil.which(tool):
            print(f"ERROR: missing tool {tool}", file=sys.stderr)
            return 2

    temp = Path(tempfile.mkdtemp(prefix="collage-cloudnet-shutdown-"))
    log_path = Path("cloudnet-shutdown-delete-semantics.log")
    evidence_path = Path("cloudnet-shutdown-delete-semantics-evidence.json")
    derived = "collage/cloudnet-shutdown-probe:" + REF[:12]
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
        shutil.copy2(module_jar, stage / "modules" / "COLLAGE-TrueNAS-Shutdown-Probe.jar")
        (stage / "config.json").write_text("{}\n", encoding="utf-8")
        (stage / "Dockerfile").write_text(
            f"""FROM {IMAGE}
USER root
COPY --chown=cloudnet:cloudnet modules/ /home/cloudnet/modules/
COPY --chown=cloudnet:cloudnet config.json /home/cloudnet/config.json
ENV JAVA_TOOL_OPTIONS="-Dcloudnet.installation.skip=true -Dcloudnet.config.maxCPUUsageToStartServices=101 -Dcloudnet.config.maxMemory=512"
USER cloudnet
""",
            encoding="utf-8")

        run(["docker", "build", "-t", derived, "."], stage, timeout=600)
        run(["docker", "rm", "-f", CONTAINER], temp, check=False)
        run(["docker", "create", "--name", CONTAINER, derived], temp)
        run(["docker", "start", CONTAINER], temp)

        deadline = time.monotonic() + 120
        ready = None
        while time.monotonic() < deadline:
            local = temp / "ready.json"
            cp = run(
                ["docker", "cp", f"{CONTAINER}:/home/cloudnet/collage-shutdown-ready.json", str(local)],
                temp, check=False)
            if cp.returncode == 0 and local.is_file():
                ready = json.loads(local.read_text(encoding="utf-8"))
                break
            state = run(
                ["docker", "inspect", CONTAINER, "--format", "{{.State.Status}} {{.State.ExitCode}}"],
                temp).stdout.strip()
            if state.startswith("exited"):
                break
            time.sleep(2)

        if not isinstance(ready, dict) or ready.get("result") != "READY":
            logs = run(["docker", "logs", CONTAINER], temp, check=False)
            log_text = (logs.stdout or "") + (logs.stderr or "")
            raise RepError("node did not reach shutdown-ready state\n" + log_text[-24000:])
        if ready.get("purge_delete_files_override_count") != 1:
            raise RepError(f"explicit deleteFiles seam was not proven: {ready!r}")

        state_before_stop = run(
            ["docker", "inspect", CONTAINER, "--format", "{{.State.Status}}"],
            temp).stdout.strip()
        if state_before_stop != "running":
            raise RepError(f"node was not running before graceful stop: {state_before_stop}")

        run(["docker", "stop", "--time", "15", CONTAINER], temp, timeout=60)
        exit_code = int(run(
            ["docker", "inspect", CONTAINER, "--format", "{{.State.ExitCode}}"],
            temp).stdout.strip())

        logs = run(["docker", "logs", CONTAINER], temp, check=False)
        log_text = (logs.stdout or "") + (logs.stderr or "")
        log_path.write_text(log_text[-50000:], encoding="utf-8")

        shutdown = copy_json_from_container(
            temp,
            "/home/cloudnet/collage-shutdown-observed.json",
            "shutdown.json")
        if shutdown.get("result") != "PASS":
            raise RepError(f"shutdown sentinel was not PASS: {shutdown!r}")
        if shutdown.get("lifecycle_after_shutdown_delete") != "DELETED":
            raise RepError(f"unexpected shutdown lifecycle: {shutdown!r}")
        if shutdown.get("ordinary_delete_hook_count") != 1:
            raise RepError(f"ordinary delete hook count mismatch: {shutdown!r}")
        if shutdown.get("delete_files_override_count") != 0:
            raise RepError(f"graceful shutdown invoked destructive deleteFiles seam: {shutdown!r}")
        if shutdown.get("destructive_purge_seam_invoked_by_shutdown") is not False:
            raise RepError(f"destructive seam flag mismatch: {shutdown!r}")

        evidence = {
            "schema_version": 1,
            "experiment": "EXP-000-CLOUDNET-001 shutdown-delete-semantics",
            "result": "PASS",
            "upstream": {"repository": UPSTREAM, "ref": REF},
            "runtime_image": {"image": IMAGE, "oci_revision": revision},
            "ready_observation": ready,
            "shutdown_observation": shutdown,
            "node_state_before_graceful_stop": state_before_stop,
            "container_exit_code_after_graceful_stop": exit_code,
            "proven": [
                "explicit deleteFiles reaches a distinct overridable service seam",
                "released CloudNet graceful shutdown ordinary-deletes registered local services before module stop",
                "graceful shutdown does not invoke the deleteFiles override",
                "a native adapter can therefore reserve deleteFiles for explicit destructive runtime purge while ordinary delete remains stop/detach",
                "the distinction requires no CloudNet wrapper, child JVM, service-directory payload, or parallel generic lifecycle API"
            ],
            "non_claims": [
                "the deleteFiles counter is not a TrueNAS mock and performs no native App deletion",
                "no TrueNAS endpoint or credential was used",
                "no native App survival/adoption, world survival, or controller restart was tested"
            ],
            "next": [
                "preserve this mapping in the native adapter design: ordinary delete=stop/detach, deleteFiles=explicit native App purge",
                "qualify read-only TrueNAS app.query under existing least authority",
                "then prove native App create/adopt/purge plus controller-loss/re-adoption on the live TrueNAS target"
            ]
        }
        payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        evidence_path.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (RepError, OSError, json.JSONDecodeError, ValueError) as exc:
        try:
            logs = run(["docker", "logs", CONTAINER], temp, check=False)
            diagnostic = (logs.stdout or "") + (logs.stderr or "")
            if diagnostic:
                log_path.write_text(diagnostic[-50000:], encoding="utf-8")
        except Exception:
            pass
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2
    finally:
        run(["docker", "rm", "-f", CONTAINER], temp, check=False)
        run(["docker", "image", "rm", "-f", derived], temp, check=False)
        shutil.rmtree(temp, ignore_errors=True)

if __name__ == "__main__":
    raise SystemExit(main())
