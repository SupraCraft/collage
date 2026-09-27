#!/usr/bin/env python3
"""Qualify fail-closed CloudNet identity fencing before native backend mutation.

Released CloudNet rewrites occupied task ids and UUIDs during pre-create
normalization. This live rep proves a truenas-native factory can compare the
post-normalization ServiceId to an externally anchored expected identity carried
as immutable service properties and reject a collision before any backend
materialization hook executes.

No TrueNAS endpoint or credential is used.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

UPSTREAM="https://github.com/CloudNetService/CloudNet.git"
REF="f8dc563272f2d4bf59772d0bcaeb713a5cc43ffb"
IMAGE="cloudnetservice/cloudnet:4.0.0-RC17"
PROJECT=":modules:collage-identity-fence:collage-identity-fence-impl"
CONTAINER="collage-cloudnet-identity-fence"
RUNTIME="truenas-native"

BUILD_FILE=r"""plugins {
  id("cloudnet-modules")
}

dependencies {
  compileOnlyApi(projects.node.nodeImpl)
}

moduleJson {
  author = "SupraCraft RDTE"
  main = "org.supracraft.collage.cloudnet.IdentityFenceProbeModule"
  description = "COLLAGE native-runtime identity collision fencing probe"
  name = "COLLAGE-Identity-Fence-Probe"
  runtimeModule = true
}
"""

LOG_CACHE=r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.service.ServiceId;
import eu.cloudnetservice.node.config.Configuration;
import eu.cloudnetservice.node.impl.service.defaults.log.AbstractServiceLogCache;

public final class IdentityFenceProbeLogCache extends AbstractServiceLogCache {
  public IdentityFenceProbeLogCache(Configuration configuration, ServiceId serviceId) {
    super(configuration, serviceId);
  }
}
"""

SERVICE=r"""package org.supracraft.collage.cloudnet;

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

public final class IdentityFenceProbeService extends AbstractService {
  private volatile boolean alive;

  public IdentityFenceProbeService(
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
  @Override protected void startProcess() { this.alive = true; }
  @Override protected void stopProcess() { this.alive = false; }
  @Override protected void doDelete() { if (this.alive) this.stopProcess(); }
  @Override public void runCommand(String command) {}
  @Override public String runtime() { return "truenas-native"; }
  @Override public boolean alive() { return this.alive; }
}
"""

FACTORY=r"""package org.supracraft.collage.cloudnet;

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
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

@Singleton
public final class IdentityFenceProbeFactory extends BaseLocalCloudServiceFactory {
  static final String EXPECTED_UUID_PROPERTY = "collage.expectedServiceUuid";
  static final String EXPECTED_TASK_ID_PROPERTY = "collage.expectedTaskServiceId";

  private final I18n i18n;
  private final DefaultTickLoop tickLoop;
  private final EventManager eventManager;
  private final AtomicInteger factoryCalls = new AtomicInteger();
  private final AtomicInteger acceptedCalls = new AtomicInteger();
  private final AtomicInteger rejectedIdentityDrift = new AtomicInteger();

  @Inject
  public IdentityFenceProbeFactory(
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
    this.factoryCalls.incrementAndGet();

    // This check is intentionally the first adapter-specific operation. A real
    // native adapter must do the same before app.create/app.update/app.start.
    var expectedUuidText = configuration.propertyHolder().getString(EXPECTED_UUID_PROPERTY);
    var expectedTaskIdText = configuration.propertyHolder().getString(EXPECTED_TASK_ID_PROPERTY);
    if (expectedUuidText == null || expectedTaskIdText == null) {
      this.rejectedIdentityDrift.incrementAndGet();
      throw new IllegalStateException("missing externally anchored identity fence");
    }

    var expectedUuid = UUID.fromString(expectedUuidText);
    var expectedTaskId = Integer.parseInt(expectedTaskIdText);
    var actualId = configuration.serviceId();
    if (!actualId.uniqueId().equals(expectedUuid) || actualId.taskServiceId() != expectedTaskId) {
      this.rejectedIdentityDrift.incrementAndGet();
      throw new IllegalStateException(
        "CloudNet pre-create identity rewrite fenced: expected "
          + expectedUuid + "/" + expectedTaskId + " but got "
          + actualId.uniqueId() + "/" + actualId.taskServiceId());
    }

    this.acceptedCalls.incrementAndGet();
    var config = this.validateConfiguration(manager, configuration);
    var preparer = manager.servicePreparer(config.serviceId().environment());
    var logCache = new IdentityFenceProbeLogCache(this.configuration, config.serviceId());
    return new IdentityFenceProbeService(
      this.i18n, this.tickLoop, this.configuration, config,
      (InternalCloudServiceManager) manager, this.eventManager, logCache,
      this.versionProvider, preparer);
  }

  @Override public String name() { return "truenas-native"; }

  public int factoryCalls() { return this.factoryCalls.get(); }
  public int acceptedCalls() { return this.acceptedCalls.get(); }
  public int rejectedIdentityDrift() { return this.rejectedIdentityDrift.get(); }
}
"""

MODULE=r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.inject.InjectionLayer;
import eu.cloudnetservice.driver.module.ModuleLifeCycle;
import eu.cloudnetservice.driver.module.ModuleTask;
import eu.cloudnetservice.driver.module.driver.DriverModule;
import eu.cloudnetservice.driver.provider.CloudServiceFactory;
import eu.cloudnetservice.driver.service.ServiceConfiguration;
import eu.cloudnetservice.driver.service.ServiceCreateResult;
import eu.cloudnetservice.driver.service.ServiceEnvironmentType;
import eu.cloudnetservice.driver.service.ServiceId;
import eu.cloudnetservice.node.service.CloudServiceManager;
import jakarta.inject.Named;
import jakarta.inject.Singleton;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;

@Singleton
public final class IdentityFenceProbeModule extends DriverModule {
  private static final String RUNTIME = "truenas-native";
  private static final UUID EXPECTED_UUID = UUID.fromString("22222222-2222-4222-8222-222222222222");
  private static final int EXPECTED_TASK_ID = 41;
  private static final Path SENTINEL = Path.of("collage-identity-fence.json");

  private static void require(boolean condition, String message) {
    if (!condition) throw new IllegalStateException(message);
  }

  private static ServiceConfiguration desiredConfiguration() {
    var requestedId = ServiceId.builder()
      .uniqueId(EXPECTED_UUID)
      .taskName("CollageFence")
      .taskServiceId(EXPECTED_TASK_ID)
      .environment(ServiceEnvironmentType.MINECRAFT_SERVER);

    return ServiceConfiguration.builder()
      .serviceId(requestedId)
      .environment(ServiceEnvironmentType.MINECRAFT_SERVER)
      .runtime(RUNTIME)
      .maxHeapMemory(64)
      .startPort(25595)
      .autoDeleteOnStop(false)
      .staticService(false)
      .modifyProperties(properties -> properties
        .append(IdentityFenceProbeFactory.EXPECTED_UUID_PROPERTY, EXPECTED_UUID.toString())
        .append(IdentityFenceProbeFactory.EXPECTED_TASK_ID_PROPERTY, Integer.toString(EXPECTED_TASK_ID)))
      .build();
  }

  @ModuleTask(order = 22)
  public void registerAndFence(
    CloudServiceManager manager,
    CloudServiceFactory serviceFactory,
    @Named("module") InjectionLayer<?> layer
  ) throws Exception {
    var factory = layer.instance(IdentityFenceProbeFactory.class);
    manager.addCloudServiceFactory(RUNTIME, factory);
    require(manager.cloudServiceFactory(RUNTIME) == factory, "runtime registration read-back failed");

    var first = serviceFactory.createCloudService(desiredConfiguration());
    require(first.state() == ServiceCreateResult.State.CREATED, "first exact-identity service was not created");
    require(first.serviceInfo().serviceId().uniqueId().equals(EXPECTED_UUID), "first UUID drifted");
    require(first.serviceInfo().serviceId().taskServiceId() == EXPECTED_TASK_ID, "first task id drifted");
    require(factory.acceptedCalls() == 1, "first exact identity was not accepted exactly once");

    boolean collisionRejected = false;
    String collisionMessage = "";
    try {
      serviceFactory.createCloudService(desiredConfiguration());
    } catch (IllegalStateException expected) {
      collisionRejected = true;
      collisionMessage = expected.getMessage() == null ? "" : expected.getMessage();
    }

    require(collisionRejected, "occupied logical identity did not fail closed");
    require(collisionMessage.contains("identity rewrite fenced"), "collision rejection did not come from identity fence");
    require(factory.factoryCalls() == 2, "unexpected runtime factory call count");
    require(factory.acceptedCalls() == 1, "collision reached accepted/backend path");
    require(factory.rejectedIdentityDrift() == 1, "identity drift rejection count != 1");
    require(manager.servicesByTask("CollageFence").size() == 1, "collision registered a second logical service");

    var original = manager.localCloudService(EXPECTED_UUID);
    require(original != null, "original service disappeared after collision rejection");
    original.delete();
    require(manager.localCloudService(EXPECTED_UUID) == null, "original service did not detach cleanly");

    String body = "{"
      + "\"schema_version\":1,"
      + "\"result\":\"PASS\","
      + "\"runtime\":\"" + RUNTIME + "\","
      + "\"expected_uuid\":\"" + EXPECTED_UUID + "\","
      + "\"expected_task_service_id\":" + EXPECTED_TASK_ID + ","
      + "\"factory_calls\":" + factory.factoryCalls() + ","
      + "\"accepted_calls\":" + factory.acceptedCalls() + ","
      + "\"rejected_identity_drift\":" + factory.rejectedIdentityDrift() + ","
      + "\"registered_services_after_collision\":1,"
      + "\"backend_path_reached_by_collision\":false,"
      + "\"collision_fail_closed\":true"
      + "}\n";
    Files.writeString(
      SENTINEL, body,
      StandardOpenOption.CREATE,
      StandardOpenOption.TRUNCATE_EXISTING,
      StandardOpenOption.WRITE);
  }

  @ModuleTask(lifecycle = ModuleLifeCycle.STOPPED)
  public void unregister(CloudServiceManager manager) {
    manager.removeCloudServiceFactory(RUNTIME);
  }
}
"""

class RepError(RuntimeError): pass

def run(cmd:list[str], cwd:Path|None=None, timeout:int=1800, check:bool=True):
    print("+ "+" ".join(cmd), file=sys.stderr)
    cp=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True,timeout=timeout)
    if check and cp.returncode:
        raise RepError(((cp.stdout or "")+"\n--- STDERR ---\n"+(cp.stderr or ""))[-30000:])
    return cp

def main()->int:
    temp=Path(tempfile.mkdtemp(prefix="collage-identity-fence-"))
    derived="collage/cloudnet-identity-fence:"+REF[:12]
    evidence_path=Path("cloudnet-identity-fencing-evidence.json")
    try:
        for tool in ("git","java","docker"):
            if not shutil.which(tool): raise RepError("missing tool "+tool)
        checkout=temp/"CloudNet"
        run(["git","init","--quiet",str(checkout)],temp)
        run(["git","-C",str(checkout),"remote","add","origin",UPSTREAM],temp)
        run(["git","-C",str(checkout),"fetch","--quiet","--depth","1","origin",REF],temp)
        run(["git","-C",str(checkout),"checkout","--quiet","--detach","FETCH_HEAD"],temp)
        if run(["git","-C",str(checkout),"rev-parse","HEAD"],temp).stdout.strip()!=REF:
            raise RepError("source ref mismatch")

        settings=checkout/"settings.gradle.kts"
        st=settings.read_text(encoding="utf-8")
        needle='include("bom")'
        stanza='''registerSubProjects(
  root = "modules:collage-identity-fence",
  prefix = "collage-identity-fence",
  subProjects = arrayOf("impl"),
)

'''
        settings.write_text(st.replace(needle,stanza+needle,1),encoding="utf-8")
        root=checkout/"modules/collage-identity-fence/impl"
        java=root/"src/main/java/org/supracraft/collage/cloudnet"
        java.mkdir(parents=True)
        (root/"build.gradle.kts").write_text(BUILD_FILE,encoding="utf-8")
        (java/"IdentityFenceProbeLogCache.java").write_text(LOG_CACHE,encoding="utf-8")
        (java/"IdentityFenceProbeService.java").write_text(SERVICE,encoding="utf-8")
        (java/"IdentityFenceProbeFactory.java").write_text(FACTORY,encoding="utf-8")
        (java/"IdentityFenceProbeModule.java").write_text(MODULE,encoding="utf-8")
        run(["./gradlew",PROJECT+":jar","--no-daemon","--console=plain"],checkout)
        jars=[p for p in (root/"build/libs").glob("*.jar") if "sources" not in p.name and "javadoc" not in p.name]
        if len(jars)!=1: raise RepError("expected one probe jar")

        run(["docker","pull",IMAGE],temp,timeout=1200)
        revision=run(["docker","image","inspect",IMAGE,"--format",'{{ index .Config.Labels "org.opencontainers.image.revision" }}'],temp).stdout.strip()
        if revision!=REF: raise RepError("image revision mismatch")

        stage=temp/"derived"
        (stage/"modules").mkdir(parents=True)
        shutil.copy2(jars[0],stage/"modules/COLLAGE-Identity-Fence-Probe.jar")
        (stage/"config.json").write_text("{}\n",encoding="utf-8")
        (stage/"Dockerfile").write_text(f"""FROM {IMAGE}
USER root
COPY --chown=cloudnet:cloudnet modules/ /home/cloudnet/modules/
COPY --chown=cloudnet:cloudnet config.json /home/cloudnet/config.json
ENV JAVA_TOOL_OPTIONS="-Dcloudnet.installation.skip=true -Dcloudnet.config.maxCPUUsageToStartServices=101 -Dcloudnet.config.maxMemory=512"
USER cloudnet
""",encoding="utf-8")
        run(["docker","build","-t",derived,"."],stage,timeout=600)
        run(["docker","rm","-f",CONTAINER],temp,check=False)
        run(["docker","create","--name",CONTAINER,derived],temp)
        run(["docker","start",CONTAINER],temp)

        deadline=time.monotonic()+120
        local=temp/"sentinel.json"
        observed=None
        while time.monotonic()<deadline:
            cp=run(["docker","cp",f"{CONTAINER}:/home/cloudnet/collage-identity-fence.json",str(local)],temp,check=False)
            if cp.returncode==0 and local.is_file():
                observed=json.loads(local.read_text(encoding="utf-8"))
                break
            state=run(["docker","inspect",CONTAINER,"--format","{{.State.Status}} {{.State.ExitCode}}"],temp).stdout.strip()
            if state.startswith("exited"): break
            time.sleep(2)

        if not isinstance(observed,dict) or observed.get("result")!="PASS":
            logs=run(["docker","logs",CONTAINER],temp,check=False)
            raise RepError("no PASS sentinel\nobserved="+repr(observed)+"\n"+((logs.stdout or "")+(logs.stderr or ""))[-24000:])
        if observed.get("accepted_calls")!=1 or observed.get("rejected_identity_drift")!=1:
            raise RepError("unexpected fence counts: "+repr(observed))
        if observed.get("backend_path_reached_by_collision") is not False:
            raise RepError("collision reached backend path")

        evidence={
          "schema_version":1,
          "experiment":"EXP-000-CLOUDNET-001 identity-fencing",
          "result":"PASS",
          "upstream":{"repository":UPSTREAM,"ref":REF,"image":IMAGE,"oci_revision":revision},
          "observed":observed,
          "proven":[
            "CloudNet rewrites occupied identity before invoking the registered runtime factory",
            "an externally anchored expected UUID/task-id property survives pre-create normalization",
            "the native runtime factory can compare prepared identity to that anchor as its first operation",
            "an occupied UUID/task-id collision is rejected before the adapter accepted/backend path",
            "only the original logical service remains registered after collision rejection"
          ],
          "non_claims":[
            "no TrueNAS API or credential was used",
            "no native App mutation was attempted",
            "the expected identity property is a stand-in for live TrueNAS ownership metadata"
          ],
          "required_adapter_invariant":"compare prepared CloudNet service identity to externally observed native-App ownership identity before any app.create/app.update/app.start side effect"
        }
        payload=json.dumps(evidence,indent=2,sort_keys=True)+"\n"
        evidence_path.write_text(payload,encoding="utf-8")
        print(payload,end="")
        return 0
    except Exception as exc:
        print("ERROR:",exc,file=sys.stderr)
        return 2
    finally:
        run(["docker","rm","-f",CONTAINER],temp,check=False)
        run(["docker","image","rm","-f",derived],temp,check=False)
        shutil.rmtree(temp,ignore_errors=True)

if __name__=="__main__":
    raise SystemExit(main())
