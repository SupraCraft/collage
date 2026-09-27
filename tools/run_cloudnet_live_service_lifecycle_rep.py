#!/usr/bin/env python3
"""Run a live CloudNet service-lifecycle rep for EXP-000-CLOUDNET-001.

This rep starts the released CloudNet 4.0.0-RC17 node, loads an external
truenas-native runtime module, then exercises CloudNet's ordinary public
CloudServiceFactory + SpecificCloudServiceProvider lifecycle against a deliberately
inert backend.

The backend is not a TrueNAS mock. It performs no TrueNAS operation at all. The
purpose is narrower: falsify whether CloudNet itself requires a wrapper/JVM child,
service-directory payload, or hidden runtime state for create/start/restart/stop/
delete semantics before spending a real TrueNAS operation.
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
PROJECT = ":modules:collage-truenas-lifecycle:collage-truenas-lifecycle-impl"
CONTAINER = "collage-cloudnet-lifecycle-probe"
RUNTIME = "truenas-native"

BUILD_FILE = r"""plugins {
  id("cloudnet-modules")
}

dependencies {
  compileOnlyApi(projects.node.nodeImpl)
}

moduleJson {
  author = "SupraCraft RDTE"
  main = "org.supracraft.collage.cloudnet.TrueNASLifecycleProbeModule"
  description = "COLLAGE live native runtime service-lifecycle probe"
  name = "COLLAGE-TrueNAS-Lifecycle-Probe"
  runtimeModule = true
}
"""

LOG_CACHE = r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.service.ServiceId;
import eu.cloudnetservice.node.config.Configuration;
import eu.cloudnetservice.node.impl.service.defaults.log.AbstractServiceLogCache;

public final class TrueNASLifecycleProbeLogCache extends AbstractServiceLogCache {
  public TrueNASLifecycleProbeLogCache(Configuration configuration, ServiceId serviceId) {
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

public final class TrueNASLifecycleProbeService extends AbstractService {
  private volatile boolean observedAlive;
  private int prepareCount;
  private int startCount;
  private int stopCount;

  public TrueNASLifecycleProbeService(
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

  @Override
  protected void prepareService() {
    // Native runtimes must not materialize CloudNet wrapper/template state merely
    // to participate in the lifecycle. TrueNAS desired/observed state will be
    // authoritative in the later live adapter rep.
    this.prepareCount++;
  }

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

  @Override public void runCommand(String command) {}
  @Override public String runtime() { return "truenas-native"; }
  @Override public boolean alive() { return this.observedAlive; }

  public int prepareCount() { return this.prepareCount; }
  public int startCount() { return this.startCount; }
  public int stopCount() { return this.stopCount; }
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
public final class TrueNASLifecycleProbeFactory extends BaseLocalCloudServiceFactory {
  private final I18n i18n;
  private final DefaultTickLoop tickLoop;
  private final EventManager eventManager;

  @Inject
  public TrueNASLifecycleProbeFactory(
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
    var logCache = new TrueNASLifecycleProbeLogCache(this.configuration, config.serviceId());
    return new TrueNASLifecycleProbeService(
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
import java.util.ArrayList;
import java.util.List;

@Singleton
public final class TrueNASLifecycleProbeModule extends DriverModule {
  private static final String RUNTIME = "truenas-native";
  private static final Path SENTINEL = Path.of("collage-service-lifecycle-live.json");

  private static void require(boolean condition, String message) {
    if (!condition) {
      throw new IllegalStateException(message);
    }
  }

  private static void expectLifeCycle(
    TrueNASLifecycleProbeService service,
    ServiceLifeCycle expected,
    String step,
    List<String> transitions
  ) {
    var actual = service.lifeCycle();
    require(actual == expected, step + ": expected " + expected + " but got " + actual);
    transitions.add(step + ":" + actual.name());
  }

  @ModuleTask(order = 22)
  public void registerAndExercise(
    CloudServiceManager manager,
    CloudServiceFactory serviceFactory,
    @Named("module") InjectionLayer<?> layer
  ) throws Exception {
    var factory = layer.instance(TrueNASLifecycleProbeFactory.class);
    manager.addCloudServiceFactory(RUNTIME, factory);
    require(manager.cloudServiceFactory(RUNTIME) == factory, "runtime factory registration did not read back exactly");

    var configuration = ServiceConfiguration.builder()
      .taskName("CollageNative")
      .environment(ServiceEnvironmentType.MINECRAFT_SERVER)
      .runtime(RUNTIME)
      .maxHeapMemory(64)
      .startPort(25591)
      .autoDeleteOnStop(false)
      .staticService(false)
      .build();

    var createResult = serviceFactory.createCloudService(configuration);
    require(createResult.state() == ServiceCreateResult.State.CREATED, "ordinary CloudServiceFactory create did not succeed");

    var createdInfo = createResult.serviceInfo();
    require(createdInfo != null, "created service had no ServiceInfoSnapshot");
    var service = manager.localCloudService(createdInfo.serviceId().uniqueId());
    require(service instanceof TrueNASLifecycleProbeService, "created service did not use truenas-native factory");
    var probe = (TrueNASLifecycleProbeService) service;

    var transitions = new ArrayList<String>();
    expectLifeCycle(probe, ServiceLifeCycle.PREPARED, "create", transitions);
    require(!probe.alive(), "service unexpectedly alive immediately after create");
    require(!Files.exists(probe.directory()), "native runtime materialized CloudNet service directory during create");

    probe.start();
    expectLifeCycle(probe, ServiceLifeCycle.RUNNING, "start-1", transitions);
    require(probe.alive(), "service not alive after start");
    require(probe.prepareCount() == 1, "prepare hook count after first start != 1");
    require(probe.startCount() == 1, "start hook count after first start != 1");
    require(!Files.exists(probe.directory()), "native runtime materialized CloudNet service directory during start");

    probe.restart();
    expectLifeCycle(probe, ServiceLifeCycle.RUNNING, "restart", transitions);
    require(probe.alive(), "service not alive after restart");
    require(probe.prepareCount() == 2, "prepare hook count after restart != 2");
    require(probe.startCount() == 2, "start hook count after restart != 2");
    require(probe.stopCount() == 1, "stop hook count after restart != 1");
    require(!Files.exists(probe.directory()), "native runtime materialized CloudNet service directory during restart");

    probe.stop();
    expectLifeCycle(probe, ServiceLifeCycle.PREPARED, "stop", transitions);
    require(!probe.alive(), "service still alive after stop");
    require(probe.stopCount() == 2, "stop hook count after explicit stop != 2");
    require(manager.localCloudService(createdInfo.serviceId().uniqueId()) == probe,
      "autoDeleteOnStop=false did not preserve registered PREPARED service");

    probe.start();
    expectLifeCycle(probe, ServiceLifeCycle.RUNNING, "start-2", transitions);
    require(probe.alive(), "service not alive after second explicit start");
    require(probe.prepareCount() == 3, "prepare hook count after second explicit start != 3");
    require(probe.startCount() == 3, "start hook count after second explicit start != 3");

    var shadowPath = probe.directory().toString();
    probe.delete();
    expectLifeCycle(probe, ServiceLifeCycle.DELETED, "delete", transitions);
    require(!probe.alive(), "service still alive after delete");
    require(probe.stopCount() == 3, "delete while RUNNING did not invoke stop hook exactly once");
    require(manager.localCloudService(createdInfo.serviceId().uniqueId()) == null,
      "deleted service remained registered in CloudServiceManager");
    require(!Files.exists(Path.of(shadowPath)), "native runtime shadow path remained materialized after delete");

    var quotedTransitions = transitions.stream()
      .map(value -> "\"" + value + "\"")
      .toList();
    String body = "{"
      + "\"schema_version\":1,"
      + "\"result\":\"PASS\","
      + "\"runtime\":\"" + RUNTIME + "\","
      + "\"factory_class\":\"" + factory.getClass().getName() + "\","
      + "\"service_name\":\"" + createdInfo.serviceId().name() + "\","
      + "\"service_id\":\"" + createdInfo.serviceId().uniqueId() + "\","
      + "\"transitions\":[" + String.join(",", quotedTransitions) + "],"
      + "\"prepare_count\":" + probe.prepareCount() + ","
      + "\"start_count\":" + probe.startCount() + ","
      + "\"stop_count\":" + probe.stopCount() + ","
      + "\"shadow_directory_materialized\":false,"
      + "\"wrapper_connection_required\":false"
      + "}\n";
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
        detail = ((cp.stdout or "") + "\n--- STDERR ---\n" + (cp.stderr or ""))[-30000:]
        raise RepError(f"command failed ({cp.returncode}): {' '.join(cmd)}\n{detail}")
    return cp

def inject(checkout: Path) -> Path:
    settings = checkout / "settings.gradle.kts"
    text = settings.read_text(encoding="utf-8")
    needle = 'include("bom")'
    stanza = '''registerSubProjects(
  root = "modules:collage-truenas-lifecycle",
  prefix = "collage-truenas-lifecycle",
  subProjects = arrayOf("impl"),
)

'''
    if needle not in text:
        raise RepError("settings insertion point changed")
    settings.write_text(text.replace(needle, stanza + needle, 1), encoding="utf-8")

    root = checkout / "modules/collage-truenas-lifecycle/impl"
    java = root / "src/main/java/org/supracraft/collage/cloudnet"
    java.mkdir(parents=True, exist_ok=True)
    (root / "build.gradle.kts").write_text(BUILD_FILE, encoding="utf-8")
    (java / "TrueNASLifecycleProbeLogCache.java").write_text(LOG_CACHE, encoding="utf-8")
    (java / "TrueNASLifecycleProbeService.java").write_text(SERVICE, encoding="utf-8")
    (java / "TrueNASLifecycleProbeFactory.java").write_text(FACTORY, encoding="utf-8")
    (java / "TrueNASLifecycleProbeModule.java").write_text(MODULE, encoding="utf-8")

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

    temp = Path(tempfile.mkdtemp(prefix="collage-cloudnet-lifecycle-"))
    log_path = Path("cloudnet-live-service-lifecycle.log")
    evidence_path = Path("cloudnet-live-service-lifecycle-evidence.json")
    derived = "collage/cloudnet-lifecycle-probe:" + REF[:12]
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
        shutil.copy2(module_jar, stage / "modules" / "COLLAGE-TrueNAS-Lifecycle-Probe.jar")
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
        sentinel = temp / "sentinel.json"
        observed = None
        while time.monotonic() < deadline:
            cp = run(
                ["docker", "cp", f"{CONTAINER}:/home/cloudnet/collage-service-lifecycle-live.json", str(sentinel)],
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
        log_path.write_text(log_text[-40000:], encoding="utf-8")

        if not isinstance(observed, dict) or observed.get("result") != "PASS":
            state = run(
                ["docker", "inspect", CONTAINER, "--format", "{{json .State}}"],
                temp, check=False).stdout.strip()
            raise RepError(
                "live node did not emit lifecycle PASS sentinel"
                + "\ncontainer_state=" + state
                + "\n--- CLOUDNET LOG TAIL ---\n" + log_text[-24000:])
        if observed.get("runtime") != RUNTIME:
            raise RepError(f"unexpected runtime in sentinel: {observed!r}")

        expected_transitions = [
            "create:PREPARED",
            "start-1:RUNNING",
            "restart:RUNNING",
            "stop:PREPARED",
            "start-2:RUNNING",
            "delete:DELETED",
        ]
        if observed.get("transitions") != expected_transitions:
            raise RepError(f"unexpected lifecycle sequence: {observed.get('transitions')!r}")
        if [observed.get("prepare_count"), observed.get("start_count"), observed.get("stop_count")] != [3, 3, 3]:
            raise RepError(f"unexpected lifecycle hook counts: {observed!r}")
        if observed.get("shadow_directory_materialized") is not False:
            raise RepError("CloudNet shadow directory unexpectedly materialized")
        if observed.get("wrapper_connection_required") is not False:
            raise RepError("rep unexpectedly required wrapper connection")

        state_before_stop = run(
            ["docker", "inspect", CONTAINER, "--format", "{{.State.Status}}"],
            temp).stdout.strip()
        if state_before_stop != "running":
            raise RepError(f"node was not running after lifecycle rep: {state_before_stop}")

        run(["docker", "stop", "--time", "15", CONTAINER], temp, timeout=60)
        exit_code = int(run(
            ["docker", "inspect", CONTAINER, "--format", "{{.State.ExitCode}}"],
            temp).stdout.strip())

        evidence = {
            "schema_version": 1,
            "experiment": "EXP-000-CLOUDNET-001 live-service-lifecycle",
            "result": "PASS",
            "upstream": {"repository": UPSTREAM, "ref": REF},
            "runtime_image": {"image": IMAGE, "oci_revision": revision},
            "observed": observed,
            "node_state_after_rep": state_before_stop,
            "container_exit_code_after_controlled_stop": exit_code,
            "proven": [
                "CloudNet ordinary CloudServiceFactory creates a service through the registered truenas-native runtime",
                "create/start/restart/stop/start/delete lifecycle completes with exact read-back transitions",
                "native lifecycle hooks execute without a Minecraft-side CloudNet wrapper or child JVM process",
                "autoDeleteOnStop=false returns an explicitly stopped service to PREPARED and keeps it registered",
                "explicit delete unregisters the service",
                "overriding native preparation avoids materializing CloudNet service-directory payload state during the rep"
            ],
            "non_claims": [
                "no TrueNAS endpoint or credential was used",
                "the inert lifecycle hooks are not a TrueNAS mock and prove no TrueNAS API behavior",
                "no native TrueNAS App was created, adopted, started, stopped, or deleted",
                "no world lifecycle, Velocity routing, Minecraft readiness, or controller-loss behavior was tested"
            ],
            "next": "authenticated read-only TrueNAS app.query under an existing least-authority boundary, then one bounded native-App create-or-adopt lifecycle rep if the adapter remains thin"
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
