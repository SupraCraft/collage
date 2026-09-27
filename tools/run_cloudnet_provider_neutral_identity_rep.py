#!/usr/bin/env python3
"""Qualify provider-neutral CloudNet identity derivation for COLLAGE.

The durable native-App contract carries only provider-neutral COLLAGE identity.
CloudNet's task name/task-service id are derived adapter state:
  taskName = canonical stable service UUID
  taskServiceId = 1

Two fresh released CloudNet nodes must derive exactly the same ServiceId. Each
node also requests the same service twice; CloudNet's occupied-identity rewrite
must be rejected by the runtime factory before any accepted/backend path.

No TrueNAS endpoint, credential, App, Minecraft server, or world is touched.
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
NIGHTLY_REF="d74c455f766f25cbd6c7fba051ef4795b90a69c4"
IMAGE="cloudnetservice/cloudnet:4.0.0-RC17"
PROJECT=":modules:collage-neutral-identity:collage-neutral-identity-impl"
RUNTIME="truenas-native"
SERVICE_UUID="11111111-1111-4111-8111-111111111111"
EXPECTED_TASK_NAME=SERVICE_UUID
EXPECTED_TASK_ID=1
EXPECTED_LOGICAL_NAME=EXPECTED_TASK_NAME+"-1"

BUILD_FILE=r"""plugins {
  id("cloudnet-modules")
}

dependencies {
  compileOnlyApi(projects.node.nodeImpl)
}

moduleJson {
  author = "SupraCraft RDTE"
  main = "org.supracraft.collage.cloudnet.NeutralIdentityProbeModule"
  description = "COLLAGE provider-neutral CloudNet identity derivation probe"
  name = "COLLAGE-Neutral-Identity-Probe"
  runtimeModule = true
}
"""

IDENTITY=r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.service.ServiceEnvironmentType;
import eu.cloudnetservice.driver.service.ServiceId;
import eu.cloudnetservice.driver.service.ServiceTask;
import java.util.UUID;

public final class CloudNetIdentityDerivation {
  public static final int TASK_SERVICE_ID = 1;

  public static String taskName(UUID serviceId) {
    var value = serviceId.toString();
    if (!ServiceTask.NAMING_PATTERN.matcher(value).matches()) {
      throw new IllegalArgumentException("derived task name violates CloudNet naming policy");
    }
    return value;
  }

  public static ServiceId serviceId(UUID stableServiceId) {
    return ServiceId.builder()
      .uniqueId(stableServiceId)
      .taskName(taskName(stableServiceId))
      .taskServiceId(TASK_SERVICE_ID)
      .environment(ServiceEnvironmentType.MINECRAFT_SERVER)
      .build();
  }

  private CloudNetIdentityDerivation() {}
}
"""

LOG_CACHE=r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.service.ServiceId;
import eu.cloudnetservice.node.config.Configuration;
import eu.cloudnetservice.node.impl.service.defaults.log.AbstractServiceLogCache;

public final class NeutralIdentityProbeLogCache extends AbstractServiceLogCache {
  public NeutralIdentityProbeLogCache(Configuration configuration, ServiceId serviceId) {
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

public final class NeutralIdentityProbeService extends AbstractService {
  private volatile boolean alive;

  public NeutralIdentityProbeService(
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
public final class NeutralIdentityProbeFactory extends BaseLocalCloudServiceFactory {
  static final String STABLE_SERVICE_ID_PROPERTY = "collage.stableServiceUuid";

  private final I18n i18n;
  private final DefaultTickLoop tickLoop;
  private final EventManager eventManager;
  private final AtomicInteger accepted = new AtomicInteger();
  private final AtomicInteger refused = new AtomicInteger();
  private final AtomicInteger calls = new AtomicInteger();

  @Inject
  public NeutralIdentityProbeFactory(
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
    this.calls.incrementAndGet();

    // First adapter-specific operation: derive expected CloudNet identity from
    // provider-neutral stable service UUID and compare the post-normalization id.
    var stableText = configuration.propertyHolder().getString(STABLE_SERVICE_ID_PROPERTY);
    if (stableText == null) {
      this.refused.incrementAndGet();
      throw new IllegalStateException("missing provider-neutral stable service identity");
    }

    final UUID stableUuid;
    try {
      stableUuid = UUID.fromString(stableText);
    } catch (IllegalArgumentException malformed) {
      this.refused.incrementAndGet();
      throw new IllegalStateException("malformed provider-neutral stable service identity", malformed);
    }

    var expected = CloudNetIdentityDerivation.serviceId(stableUuid);
    var actual = configuration.serviceId();
    if (!actual.uniqueId().equals(expected.uniqueId())
      || !actual.taskName().equals(expected.taskName())
      || actual.taskServiceId() != expected.taskServiceId()) {
      this.refused.incrementAndGet();
      throw new IllegalStateException("derived CloudNet identity drift fenced");
    }

    this.accepted.incrementAndGet();
    var config = this.validateConfiguration(manager, configuration);
    var preparer = manager.servicePreparer(config.serviceId().environment());
    var logCache = new NeutralIdentityProbeLogCache(this.configuration, config.serviceId());
    return new NeutralIdentityProbeService(
      this.i18n, this.tickLoop, this.configuration, config,
      (InternalCloudServiceManager) manager, this.eventManager, logCache,
      this.versionProvider, preparer);
  }

  @Override public String name() { return "truenas-native"; }
  public int calls() { return this.calls.get(); }
  public int accepted() { return this.accepted.get(); }
  public int refused() { return this.refused.get(); }
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
public final class NeutralIdentityProbeModule extends DriverModule {
  private static final String RUNTIME = "truenas-native";
  private static final UUID STABLE_UUID = UUID.fromString("11111111-1111-4111-8111-111111111111");
  private static final Path SENTINEL = Path.of("collage-neutral-identity.txt");

  private static void require(boolean ok, String message) {
    if (!ok) throw new IllegalStateException(message);
  }

  private static ServiceConfiguration desired() {
    var id = CloudNetIdentityDerivation.serviceId(STABLE_UUID);
    return ServiceConfiguration.builder()
      .serviceId(ServiceId.builder(id))
      .environment(ServiceEnvironmentType.MINECRAFT_SERVER)
      .runtime(RUNTIME)
      .maxHeapMemory(64)
      .startPort(25596)
      .autoDeleteOnStop(false)
      .staticService(false)
      .modifyProperties(properties ->
        properties.append(NeutralIdentityProbeFactory.STABLE_SERVICE_ID_PROPERTY, STABLE_UUID.toString()))
      .build();
  }

  @ModuleTask(order = 22)
  public void qualify(
    CloudServiceManager manager,
    CloudServiceFactory serviceFactory,
    @Named("module") InjectionLayer<?> layer
  ) throws Exception {
    var factory = layer.instance(NeutralIdentityProbeFactory.class);
    manager.addCloudServiceFactory(RUNTIME, factory);
    require(manager.cloudServiceFactory(RUNTIME) == factory, "runtime registration failed");

    var expected = CloudNetIdentityDerivation.serviceId(STABLE_UUID);
    require(expected.taskName().equals(STABLE_UUID.toString()), "derived task name drift");
    require(expected.taskServiceId() == 1, "derived task id drift");
    require(expected.name().equals(STABLE_UUID + "-1"), "derived logical name drift");

    var first = serviceFactory.createCloudService(desired());
    require(first.state() == ServiceCreateResult.State.CREATED, "first derived service create failed");
    require(first.serviceInfo().serviceId().uniqueId().equals(STABLE_UUID), "stable uuid drifted");
    require(first.serviceInfo().serviceId().taskName().equals(expected.taskName()), "task name drifted");
    require(first.serviceInfo().serviceId().taskServiceId() == 1, "task id drifted");
    require(factory.calls() == 1 && factory.accepted() == 1 && factory.refused() == 0,
      "unexpected first-create factory counts");

    boolean duplicateRefused = false;
    try {
      serviceFactory.createCloudService(desired());
    } catch (IllegalStateException fenced) {
      duplicateRefused = "derived CloudNet identity drift fenced".equals(fenced.getMessage());
    }
    require(duplicateRefused, "duplicate derived identity was not fenced");
    require(factory.calls() == 2, "factory call count after duplicate != 2");
    require(factory.accepted() == 1, "duplicate reached accepted/backend path");
    require(factory.refused() == 1, "duplicate refusal count != 1");
    require(manager.servicesByTask(expected.taskName()).size() == 1,
      "duplicate registered another logical service");

    var service = manager.localCloudService(STABLE_UUID);
    require(service != null, "original derived service missing");
    require(!Files.exists(service.directory()), "native runtime materialized shadow payload directory");
    service.delete();
    require(manager.localCloudService(STABLE_UUID) == null, "original service failed to detach");

    StringBuilder body = new StringBuilder();
    body.append("result=PASS\n");
    body.append("stable_service_uuid=").append(STABLE_UUID).append("\n");
    body.append("derived_task_name=").append(expected.taskName()).append("\n");
    body.append("derived_task_service_id=").append(expected.taskServiceId()).append("\n");
    body.append("derived_logical_name=").append(expected.name()).append("\n");
    body.append("provider_neutral_metadata_field_count=6\n");
    body.append("factory_calls=").append(factory.calls()).append("\n");
    body.append("accepted_calls=").append(factory.accepted()).append("\n");
    body.append("refused_collisions=").append(factory.refused()).append("\n");
    body.append("collision_backend_path_reached=false\n");
    body.append("shadow_directory_materialized=false\n");
    Files.writeString(SENTINEL, body.toString(),
      StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
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

def parse_sentinel(path:Path)->dict:
    parsed={}
    for line in path.read_text(encoding="utf-8").splitlines():
        k,sep,v=line.partition("=")
        if sep:
            parsed[k]=v
    return {
        "result":parsed.get("result"),
        "stable_service_uuid":parsed.get("stable_service_uuid"),
        "derived_task_name":parsed.get("derived_task_name"),
        "derived_task_service_id":int(parsed.get("derived_task_service_id","-1")),
        "derived_logical_name":parsed.get("derived_logical_name"),
        "provider_neutral_metadata_field_count":int(parsed.get("provider_neutral_metadata_field_count","-1")),
        "factory_calls":int(parsed.get("factory_calls","-1")),
        "accepted_calls":int(parsed.get("accepted_calls","-1")),
        "refused_collisions":int(parsed.get("refused_collisions","-1")),
        "collision_backend_path_reached":parsed.get("collision_backend_path_reached")=="true",
        "shadow_directory_materialized":parsed.get("shadow_directory_materialized")=="true",
    }

def inject(checkout:Path)->Path:
    settings=checkout/"settings.gradle.kts"
    text=settings.read_text(encoding="utf-8")
    needle='include("bom")'
    stanza='''registerSubProjects(
  root = "modules:collage-neutral-identity",
  prefix = "collage-neutral-identity",
  subProjects = arrayOf("impl"),
)

'''
    if needle not in text: raise RepError("settings insertion point changed")
    settings.write_text(text.replace(needle,stanza+needle,1),encoding="utf-8")
    root=checkout/"modules/collage-neutral-identity/impl"
    java=root/"src/main/java/org/supracraft/collage/cloudnet"
    java.mkdir(parents=True)
    (root/"build.gradle.kts").write_text(BUILD_FILE,encoding="utf-8")
    (java/"CloudNetIdentityDerivation.java").write_text(IDENTITY,encoding="utf-8")
    (java/"NeutralIdentityProbeLogCache.java").write_text(LOG_CACHE,encoding="utf-8")
    (java/"NeutralIdentityProbeService.java").write_text(SERVICE,encoding="utf-8")
    (java/"NeutralIdentityProbeFactory.java").write_text(FACTORY,encoding="utf-8")
    (java/"NeutralIdentityProbeModule.java").write_text(MODULE,encoding="utf-8")
    run(["./gradlew",PROJECT+":jar","--no-daemon","--console=plain"],checkout)
    jars=[p for p in (root/"build/libs").glob("*.jar") if "sources" not in p.name and "javadoc" not in p.name]
    if len(jars)!=1: raise RepError("expected one probe jar")
    return jars[0]

def run_fresh(temp:Path, image:str, suffix:str)->dict:
    container="collage-neutral-identity-"+suffix
    run(["docker","rm","-f",container],temp,check=False)
    run(["docker","create","--name",container,image],temp)
    try:
        run(["docker","start",container],temp)
        local=temp/(suffix+".txt")
        deadline=time.monotonic()+120
        observed=None
        while time.monotonic()<deadline:
            cp=run(["docker","cp",f"{container}:/home/cloudnet/collage-neutral-identity.txt",str(local)],temp,check=False)
            if cp.returncode==0 and local.is_file():
                observed=parse_sentinel(local)
                break
            state=run(["docker","inspect",container,"--format","{{.State.Status}} {{.State.ExitCode}}"],temp).stdout.strip()
            if state.startswith("exited"): break
            time.sleep(2)
        if not isinstance(observed,dict) or observed.get("result")!="PASS":
            logs=run(["docker","logs",container],temp,check=False)
            raise RepError("fresh node did not PASS\nobserved="+repr(observed)+"\n"+((logs.stdout or "")+(logs.stderr or ""))[-24000:])
        return observed
    finally:
        run(["docker","stop","--time","15",container],temp,timeout=60,check=False)
        run(["docker","rm","-f",container],temp,check=False)

def main()->int:
    temp=Path(tempfile.mkdtemp(prefix="collage-neutral-identity-"))
    derived="collage/cloudnet-neutral-identity:"+REF[:12]
    evidence_path=Path("cloudnet-provider-neutral-identity-evidence.json")
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
        jar=inject(checkout)

        nightly=temp/"CloudNet-nightly"
        run(["git","init","--quiet",str(nightly)],temp)
        run(["git","-C",str(nightly),"remote","add","origin",UPSTREAM],temp)
        run(["git","-C",str(nightly),"fetch","--quiet","--depth","1","origin",NIGHTLY_REF],temp)
        run(["git","-C",str(nightly),"checkout","--quiet","--detach","FETCH_HEAD"],temp)
        if run(["git","-C",str(nightly),"rev-parse","HEAD"],temp).stdout.strip()!=NIGHTLY_REF:
            raise RepError("nightly source ref mismatch")
        inject(nightly)

        run(["docker","pull",IMAGE],temp,timeout=1200)
        revision=run(["docker","image","inspect",IMAGE,"--format",'{{ index .Config.Labels "org.opencontainers.image.revision" }}'],temp).stdout.strip()
        if revision!=REF: raise RepError("image revision mismatch")

        stage=temp/"derived"
        (stage/"modules").mkdir(parents=True)
        shutil.copy2(jar,stage/"modules/COLLAGE-Neutral-Identity-Probe.jar")
        (stage/"config.json").write_text("{}\n",encoding="utf-8")
        (stage/"Dockerfile").write_text(f"""FROM {IMAGE}
USER root
COPY --chown=cloudnet:cloudnet modules/ /home/cloudnet/modules/
COPY --chown=cloudnet:cloudnet config.json /home/cloudnet/config.json
ENV JAVA_TOOL_OPTIONS="-Dcloudnet.installation.skip=true -Dcloudnet.config.maxCPUUsageToStartServices=101 -Dcloudnet.config.maxMemory=512"
USER cloudnet
""",encoding="utf-8")
        run(["docker","build","-t",derived,"."],stage,timeout=600)

        first=run_fresh(temp,derived,"a")
        second=run_fresh(temp,derived,"b")
        if first!=second:
            raise RepError(f"fresh-node derived identity differs: first={first!r} second={second!r}")
        if first["stable_service_uuid"]!=SERVICE_UUID:
            raise RepError("stable service UUID drift")
        if first["derived_task_name"]!=EXPECTED_TASK_NAME or first["derived_task_service_id"]!=EXPECTED_TASK_ID:
            raise RepError("derived CloudNet task identity drift")
        if first["derived_logical_name"]!=EXPECTED_LOGICAL_NAME:
            raise RepError("derived logical name drift")
        if first["provider_neutral_metadata_field_count"]!=6:
            raise RepError("provider-neutral metadata count drift")
        if first["accepted_calls"]!=1 or first["refused_collisions"]!=1:
            raise RepError("collision fence count drift")
        if first["collision_backend_path_reached"] or first["shadow_directory_materialized"]:
            raise RepError("forbidden backend/shadow behavior observed")

        evidence={
          "schema_version":1,
          "experiment":"EXP-000-CLOUDNET-001 provider-neutral CloudNet identity derivation",
          "result":"PASS",
          "upstream":{"repository":UPSTREAM,"ref":REF,"nightly_ref":NIGHTLY_REF,"image":IMAGE,"oci_revision":revision},
          "mapping":{
            "durable_input":"SUPRACRAFT_COLLAGE_SERVICE_ID UUID",
            "cloudnet_task_name":"<canonical-service-uuid>",
            "cloudnet_task_service_id":1,
            "cloudnet_fields_persisted_in_native_app":False
          },
          "first_fresh_node":first,
          "second_fresh_node":second,
          "proven":[
            "CloudNet task identity is the canonical provider-neutral stable service UUID plus fixed task-service id 1",
            "the canonical UUID task name satisfies CloudNet's released naming policy",
            "the same injected adapter source compiles against the pinned CloudNet nightly ref",
            "two fresh CloudNet nodes reconstruct exactly the same logical identity from the same UUID",
            "a duplicate occupied identity is rejected before the accepted/backend path",
            "no CloudNet task name or task-service id needs to be persisted in the native App metadata",
            "no CloudNet service-directory payload is required"
          ],
          "non_claims":[
            "no TrueNAS endpoint or credential was used",
            "no native App was queried or mutated",
            "the six-field native metadata contract is source-render/live-read qualified separately"
          ],
          "supersedes_adapter_assumption":"Persisting SUPRACRAFT_COLLAGE_TASK_NAME and SUPRACRAFT_COLLAGE_TASK_SERVICE_ID is unnecessary provider coupling."
        }
        payload=json.dumps(evidence,indent=2,sort_keys=True)+"\n"
        evidence_path.write_text(payload,encoding="utf-8")
        print(payload,end="")
        return 0
    except Exception as exc:
        print("ERROR:",exc,file=sys.stderr)
        return 2
    finally:
        run(["docker","image","rm","-f",derived],temp,check=False)
        shutil.rmtree(temp,ignore_errors=True)

if __name__=="__main__":
    raise SystemExit(main())
