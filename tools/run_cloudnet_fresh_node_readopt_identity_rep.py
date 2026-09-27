#!/usr/bin/env python3
"""Qualify CloudNet logical service identity reconstruction on a fresh node.

No TrueNAS endpoint/credential is used. Two completely fresh released CloudNet
4.0.0-RC17 nodes independently reconstruct the same explicit ServiceId from the
same externally supplied identity. This tests only the CloudNet side of future
native-App re-adoption: controller-local state must not be required to recover
the logical service UUID/name.
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
PROJECT=":modules:collage-readopt:collage-readopt-impl"
RUNTIME="truenas-native"
FIXED_UUID="11111111-1111-4111-8111-111111111111"
EXPECTED_NAME="CollageReAdopt-37"

BUILD_FILE=r"""plugins {
  id("cloudnet-modules")
}

dependencies {
  compileOnlyApi(projects.node.nodeImpl)
}

moduleJson {
  author = "SupraCraft RDTE"
  main = "org.supracraft.collage.cloudnet.ReAdoptProbeModule"
  description = "COLLAGE fresh-node logical identity reconstruction probe"
  name = "COLLAGE-ReAdopt-Probe"
  runtimeModule = true
}
"""

LOG_CACHE=r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.service.ServiceId;
import eu.cloudnetservice.node.config.Configuration;
import eu.cloudnetservice.node.impl.service.defaults.log.AbstractServiceLogCache;

public final class ReAdoptProbeLogCache extends AbstractServiceLogCache {
  public ReAdoptProbeLogCache(Configuration configuration, ServiceId serviceId) {
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

public final class ReAdoptProbeService extends AbstractService {
  private volatile boolean alive;

  public ReAdoptProbeService(
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

  @Override
  protected void doDelete() {
    // Proposed ordinary native-runtime detach semantics: stop logical service
    // but do not represent destructive native-App deletion here.
    if (this.alive) {
      this.stopProcess();
    }
  }

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

@Singleton
public final class ReAdoptProbeFactory extends BaseLocalCloudServiceFactory {
  private final I18n i18n;
  private final DefaultTickLoop tickLoop;
  private final EventManager eventManager;

  @Inject
  public ReAdoptProbeFactory(
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
    var logCache = new ReAdoptProbeLogCache(this.configuration, config.serviceId());
    return new ReAdoptProbeService(
      this.i18n, this.tickLoop, this.configuration, config,
      (InternalCloudServiceManager) manager, this.eventManager, logCache,
      this.versionProvider, preparer);
  }

  @Override public String name() { return "truenas-native"; }
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
import eu.cloudnetservice.driver.service.ServiceLifeCycle;
import eu.cloudnetservice.node.service.CloudServiceManager;
import jakarta.inject.Named;
import jakarta.inject.Singleton;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;

@Singleton
public final class ReAdoptProbeModule extends DriverModule {
  private static final String RUNTIME = "truenas-native";
  private static final UUID EXPECTED_UUID = UUID.fromString("11111111-1111-4111-8111-111111111111");
  private static final String EXPECTED_NAME = "CollageReAdopt-37";
  private static final Path SENTINEL = Path.of("collage-readopt-identity.json");

  private static void require(boolean condition, String message) {
    if (!condition) {
      throw new IllegalStateException(message);
    }
  }

  @ModuleTask(order = 22)
  public void registerAndReconstruct(
    CloudServiceManager manager,
    CloudServiceFactory serviceFactory,
    @Named("module") InjectionLayer<?> layer
  ) throws Exception {
    var factory = layer.instance(ReAdoptProbeFactory.class);
    manager.addCloudServiceFactory(RUNTIME, factory);
    require(manager.cloudServiceFactory(RUNTIME) == factory, "runtime registration read-back failed");

    var requestedId = ServiceId.builder()
      .uniqueId(EXPECTED_UUID)
      .taskName("CollageReAdopt")
      .taskServiceId(37)
      .environment(ServiceEnvironmentType.MINECRAFT_SERVER);

    var configuration = ServiceConfiguration.builder()
      .serviceId(requestedId)
      .runtime(RUNTIME)
      .maxHeapMemory(64)
      .startPort(25594)
      .autoDeleteOnStop(false)
      .staticService(false)
      .build();

    var result = serviceFactory.createCloudService(configuration);
    require(result.state() == ServiceCreateResult.State.CREATED, "explicit identity create failed");
    var info = result.serviceInfo();
    require(info != null, "created service has no info snapshot");
    require(info.serviceId().uniqueId().equals(EXPECTED_UUID), "CloudNet rewrote explicit UUID");
    require(info.serviceId().taskServiceId() == 37, "CloudNet rewrote explicit task service id");
    require(info.serviceId().name().equals(EXPECTED_NAME), "CloudNet rewrote explicit logical name");

    var service = manager.localCloudService(EXPECTED_UUID);
    require(service instanceof ReAdoptProbeService, "service not materialized through native runtime");
    require(!Files.exists(service.directory()), "service directory payload materialized before start");

    service.start();
    require(service.lifeCycle() == ServiceLifeCycle.RUNNING, "reconstructed service did not start");
    require(service.alive(), "reconstructed service not alive after start");
    require(!Files.exists(service.directory()), "service directory payload materialized on start");

    service.delete();
    require(service.lifeCycle() == ServiceLifeCycle.DELETED, "ordinary detach did not reach DELETED");
    require(manager.localCloudService(EXPECTED_UUID) == null, "detached service remained registered");
    require(!Files.exists(service.directory()), "shadow path remained after detach");

    String body = "{"
      + "\"schema_version\":1,"
      + "\"result\":\"PASS\","
      + "\"runtime\":\"" + RUNTIME + "\","
      + "\"service_uuid\":\"" + info.serviceId().uniqueId() + "\","
      + "\"service_name\":\"" + info.serviceId().name() + "\","
      + "\"task_service_id\":" + info.serviceId().taskServiceId() + ","
      + "\"logical_identity_reconstructable_without_prior_node_state\":true,"
      + "\"shadow_directory_materialized\":false"
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

class RepError(RuntimeError):
    pass

def run(cmd:list[str], cwd:Path|None=None, timeout:int=1800, check:bool=True):
    print("+ "+" ".join(cmd), file=sys.stderr)
    try:
        cp=subprocess.run(cmd,cwd=cwd,text=True,capture_output=True,timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RepError("timeout: "+" ".join(cmd)) from exc
    if check and cp.returncode:
        detail=((cp.stdout or "")+"\n--- STDERR ---\n"+(cp.stderr or ""))[-30000:]
        raise RepError(f"command failed ({cp.returncode}): {' '.join(cmd)}\n{detail}")
    return cp

def inject(checkout:Path)->Path:
    settings=checkout/"settings.gradle.kts"
    text=settings.read_text(encoding="utf-8")
    needle='include("bom")'
    stanza='''registerSubProjects(
  root = "modules:collage-readopt",
  prefix = "collage-readopt",
  subProjects = arrayOf("impl"),
)

'''
    if needle not in text:
        raise RepError("settings insertion point changed")
    settings.write_text(text.replace(needle,stanza+needle,1),encoding="utf-8")

    root=checkout/"modules/collage-readopt/impl"
    java=root/"src/main/java/org/supracraft/collage/cloudnet"
    java.mkdir(parents=True,exist_ok=True)
    (root/"build.gradle.kts").write_text(BUILD_FILE,encoding="utf-8")
    (java/"ReAdoptProbeLogCache.java").write_text(LOG_CACHE,encoding="utf-8")
    (java/"ReAdoptProbeService.java").write_text(SERVICE,encoding="utf-8")
    (java/"ReAdoptProbeFactory.java").write_text(FACTORY,encoding="utf-8")
    (java/"ReAdoptProbeModule.java").write_text(MODULE,encoding="utf-8")
    run(["./gradlew",PROJECT+":jar","--no-daemon","--console=plain"],checkout)
    jars=[p for p in (root/"build/libs").glob("*.jar") if "sources" not in p.name and "javadoc" not in p.name]
    if len(jars)!=1:
        raise RepError(f"expected one probe jar; got {[p.name for p in jars]}")
    return jars[0]

def run_fresh_node(temp:Path, image:str, suffix:str)->dict:
    container=f"collage-readopt-{suffix}"
    run(["docker","rm","-f",container],temp,check=False)
    run(["docker","create","--name",container,image],temp)
    try:
        run(["docker","start",container],temp)
        deadline=time.monotonic()+120
        local=temp/f"{suffix}.json"
        observed=None
        while time.monotonic()<deadline:
            cp=run(["docker","cp",f"{container}:/home/cloudnet/collage-readopt-identity.json",str(local)],temp,check=False)
            if cp.returncode==0 and local.is_file():
                observed=json.loads(local.read_text(encoding="utf-8"))
                break
            state=run(["docker","inspect",container,"--format","{{.State.Status}} {{.State.ExitCode}}"],temp).stdout.strip()
            if state.startswith("exited"):
                break
            time.sleep(2)
        if not isinstance(observed,dict) or observed.get("result")!="PASS":
            logs=run(["docker","logs",container],temp,check=False)
            raise RepError("fresh node did not emit PASS sentinel\n"+((logs.stdout or "")+(logs.stderr or ""))[-24000:])
        if observed.get("service_uuid")!=FIXED_UUID or observed.get("service_name")!=EXPECTED_NAME:
            raise RepError(f"fresh node identity drift: {observed!r}")
        return observed
    finally:
        run(["docker","stop","--time","15",container],temp,timeout=60,check=False)
        run(["docker","rm","-f",container],temp,check=False)

def main()->int:
    for tool in ("git","java","docker"):
        if not shutil.which(tool):
            print(f"ERROR: missing tool {tool}",file=sys.stderr)
            return 2
    temp=Path(tempfile.mkdtemp(prefix="collage-readopt-"))
    evidence_path=Path("cloudnet-fresh-node-readopt-evidence.json")
    derived="collage/cloudnet-readopt:"+REF[:12]
    try:
        checkout=temp/"CloudNet"
        run(["git","init","--quiet",str(checkout)],temp)
        run(["git","-C",str(checkout),"remote","add","origin",UPSTREAM],temp)
        run(["git","-C",str(checkout),"fetch","--quiet","--depth","1","origin",REF],temp)
        run(["git","-C",str(checkout),"checkout","--quiet","--detach","FETCH_HEAD"],temp)
        actual=run(["git","-C",str(checkout),"rev-parse","HEAD"],temp).stdout.strip()
        if actual!=REF:
            raise RepError(f"source ref mismatch: {actual}")
        module_jar=inject(checkout)

        run(["docker","pull",IMAGE],temp,timeout=1200)
        revision=run(["docker","image","inspect",IMAGE,"--format",'{{ index .Config.Labels "org.opencontainers.image.revision" }}'],temp).stdout.strip()
        if revision!=REF:
            raise RepError(f"released image revision mismatch: {revision!r}")

        stage=temp/"derived"
        (stage/"modules").mkdir(parents=True)
        shutil.copy2(module_jar,stage/"modules/COLLAGE-ReAdopt-Probe.jar")
        (stage/"config.json").write_text("{}\n",encoding="utf-8")
        (stage/"Dockerfile").write_text(
            f"""FROM {IMAGE}
USER root
COPY --chown=cloudnet:cloudnet modules/ /home/cloudnet/modules/
COPY --chown=cloudnet:cloudnet config.json /home/cloudnet/config.json
ENV JAVA_TOOL_OPTIONS="-Dcloudnet.installation.skip=true -Dcloudnet.config.maxCPUUsageToStartServices=101 -Dcloudnet.config.maxMemory=512"
USER cloudnet
""",encoding="utf-8")
        run(["docker","build","-t",derived,"."],stage,timeout=600)

        first=run_fresh_node(temp,derived,"a")
        second=run_fresh_node(temp,derived,"b")
        if first!=second:
            raise RepError(f"fresh-node observations differ: first={first!r}, second={second!r}")

        evidence={
            "schema_version":1,
            "experiment":"EXP-000-CLOUDNET-001 fresh-node logical identity reconstruction",
            "result":"PASS",
            "upstream":{"repository":UPSTREAM,"ref":REF,"image":IMAGE,"oci_revision":revision},
            "first_fresh_node":first,
            "second_fresh_node":second,
            "proven":[
                "two independent fresh released CloudNet nodes reconstruct the same explicit logical service UUID",
                "explicit task service id and logical service name are preserved exactly",
                "ordinary detach unregisters the logical service without requiring prior node-local service state",
                "no CloudNet service-directory payload is required for this native-runtime identity cycle"
            ],
            "non_claims":[
                "the externally supplied identity is a test constant, not live TrueNAS metadata",
                "no TrueNAS App was discovered or adopted",
                "no controller database restoration was tested",
                "no world or Minecraft runtime was touched"
            ],
            "next":"supply the same identity from live read-only TrueNAS ownership metadata, then prove actual native App adoption without duplicate creation"
        }
        payload=json.dumps(evidence,indent=2,sort_keys=True)+"\n"
        evidence_path.write_text(payload,encoding="utf-8")
        print(payload,end="")
        return 0
    except (RepError,OSError,json.JSONDecodeError,ValueError) as exc:
        print("ERROR: "+str(exc),file=sys.stderr)
        return 2
    finally:
        run(["docker","image","rm","-f",derived],temp,check=False)
        shutil.rmtree(temp,ignore_errors=True)

if __name__=="__main__":
    raise SystemExit(main())
