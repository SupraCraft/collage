#!/usr/bin/env python3
"""Qualify fail-closed native-App adoption policy against released CloudNet.

No TrueNAS endpoint/credential is used. The rep loads a tiny CloudNet module and
exercises the exact ownership metadata fields intended to come from sanitized
TrueNAS app.query read-back. Only an exact metadata/context/ServiceId match is
adoptable; every drift case must refuse closed.
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
PROJECT=":modules:collage-adoption-policy:collage-adoption-policy-impl"
CONTAINER="collage-cloudnet-adoption-policy"

BUILD_FILE=r"""plugins {
  id("cloudnet-modules")
}

dependencies {
  compileOnlyApi(projects.node.nodeImpl)
}

moduleJson {
  author = "SupraCraft RDTE"
  main = "org.supracraft.collage.cloudnet.AdoptionPolicyProbeModule"
  description = "COLLAGE native-App ownership/adoption policy probe"
  name = "COLLAGE-Adoption-Policy-Probe"
  runtimeModule = true
}
"""

POLICY=r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.service.ServiceId;
import java.util.Map;
import java.util.UUID;

public final class NativeAppAdoptionPolicy {
  public static final String MANAGED = "SUPRACRAFT_COLLAGE_MANAGED";
  public static final String SCHEMA = "SUPRACRAFT_COLLAGE_SCHEMA";
  public static final String MANAGER = "SUPRACRAFT_COLLAGE_MANAGER_ID";
  public static final String FLEET = "SUPRACRAFT_COLLAGE_FLEET_ID";
  public static final String SERVICE = "SUPRACRAFT_COLLAGE_SERVICE_ID";
  public static final String TASK_NAME = "SUPRACRAFT_COLLAGE_TASK_NAME";
  public static final String TASK_ID = "SUPRACRAFT_COLLAGE_TASK_SERVICE_ID";
  public static final String WORLD = "SUPRACRAFT_COLLAGE_WORLD_ID";

  public enum Decision {
    ADOPT,
    REFUSE_INCOMPLETE,
    REFUSE_SCHEMA,
    REFUSE_FOREIGN,
    REFUSE_IDENTITY,
    REFUSE_WORLD
  }

  private static String required(Map<String, String> metadata, String key) {
    var value = metadata.get(key);
    return value == null || value.isBlank() ? null : value;
  }

  public static Decision evaluate(
    Map<String, String> metadata,
    String expectedManager,
    String expectedFleet,
    String expectedWorld,
    ServiceId preparedId
  ) {
    var managed = required(metadata, MANAGED);
    var schema = required(metadata, SCHEMA);
    var manager = required(metadata, MANAGER);
    var fleet = required(metadata, FLEET);
    var service = required(metadata, SERVICE);
    var taskName = required(metadata, TASK_NAME);
    var taskId = required(metadata, TASK_ID);
    var world = required(metadata, WORLD);

    if (managed == null || schema == null || manager == null || fleet == null
      || service == null || taskName == null || taskId == null || world == null) {
      return Decision.REFUSE_INCOMPLETE;
    }
    if (!"true".equals(managed) || !"1".equals(schema)) {
      return Decision.REFUSE_SCHEMA;
    }
    if (!expectedManager.equals(manager) || !expectedFleet.equals(fleet)) {
      return Decision.REFUSE_FOREIGN;
    }
    if (!expectedWorld.equals(world)) {
      return Decision.REFUSE_WORLD;
    }

    final UUID expectedUuid;
    final int expectedTaskId;
    try {
      expectedUuid = UUID.fromString(service);
      expectedTaskId = Integer.parseInt(taskId);
    } catch (RuntimeException malformed) {
      return Decision.REFUSE_IDENTITY;
    }

    if (expectedTaskId <= 0
      || !preparedId.uniqueId().equals(expectedUuid)
      || !preparedId.taskName().equals(taskName)
      || preparedId.taskServiceId() != expectedTaskId) {
      return Decision.REFUSE_IDENTITY;
    }
    return Decision.ADOPT;
  }

  private NativeAppAdoptionPolicy() {}
}
"""

MODULE=r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.module.ModuleTask;
import eu.cloudnetservice.driver.module.driver.DriverModule;
import eu.cloudnetservice.driver.service.ServiceEnvironmentType;
import eu.cloudnetservice.driver.service.ServiceId;
import jakarta.inject.Singleton;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

@Singleton
public final class AdoptionPolicyProbeModule extends DriverModule {
  private static final Path SENTINEL = Path.of("collage-adoption-policy.json");
  private static final UUID UUID_VALUE = UUID.fromString("11111111-1111-4111-8111-111111111111");

  private static void require(boolean ok, String message) {
    if (!ok) throw new IllegalStateException(message);
  }

  private static ServiceId prepared() {
    return ServiceId.builder()
      .uniqueId(UUID_VALUE)
      .taskName("CollageReAdopt")
      .taskServiceId(37)
      .environment(ServiceEnvironmentType.MINECRAFT_SERVER)
      .build();
  }

  private static Map<String, String> exact() {
    var m = new LinkedHashMap<String, String>();
    m.put(NativeAppAdoptionPolicy.MANAGED, "true");
    m.put(NativeAppAdoptionPolicy.SCHEMA, "1");
    m.put(NativeAppAdoptionPolicy.MANAGER, "manager-rdte");
    m.put(NativeAppAdoptionPolicy.FLEET, "rdte");
    m.put(NativeAppAdoptionPolicy.SERVICE, UUID_VALUE.toString());
    m.put(NativeAppAdoptionPolicy.TASK_NAME, "CollageReAdopt");
    m.put(NativeAppAdoptionPolicy.TASK_ID, "37");
    m.put(NativeAppAdoptionPolicy.WORLD, "world-rdte-001");
    return m;
  }

  private static void expect(
    String name,
    Map<String,String> metadata,
    ServiceId id,
    NativeAppAdoptionPolicy.Decision expected,
    Map<String,String> observed
  ) {
    var actual = NativeAppAdoptionPolicy.evaluate(
      metadata, "manager-rdte", "rdte", "world-rdte-001", id);
    require(actual == expected, name + ": expected " + expected + " got " + actual);
    observed.put(name, actual.name());
  }

  @ModuleTask(order = 22)
  public void qualify() throws Exception {
    var observed = new LinkedHashMap<String,String>();
    var id = prepared();

    expect("exact", exact(), id, NativeAppAdoptionPolicy.Decision.ADOPT, observed);

    var missing = exact(); missing.remove(NativeAppAdoptionPolicy.TASK_ID);
    expect("missing_field", missing, id, NativeAppAdoptionPolicy.Decision.REFUSE_INCOMPLETE, observed);

    var managed = exact(); managed.put(NativeAppAdoptionPolicy.MANAGED, "false");
    expect("not_managed", managed, id, NativeAppAdoptionPolicy.Decision.REFUSE_SCHEMA, observed);

    var schema = exact(); schema.put(NativeAppAdoptionPolicy.SCHEMA, "2");
    expect("schema_drift", schema, id, NativeAppAdoptionPolicy.Decision.REFUSE_SCHEMA, observed);

    var manager = exact(); manager.put(NativeAppAdoptionPolicy.MANAGER, "manager-other");
    expect("manager_drift", manager, id, NativeAppAdoptionPolicy.Decision.REFUSE_FOREIGN, observed);

    var fleet = exact(); fleet.put(NativeAppAdoptionPolicy.FLEET, "other");
    expect("fleet_drift", fleet, id, NativeAppAdoptionPolicy.Decision.REFUSE_FOREIGN, observed);

    var world = exact(); world.put(NativeAppAdoptionPolicy.WORLD, "world-other");
    expect("world_drift", world, id, NativeAppAdoptionPolicy.Decision.REFUSE_WORLD, observed);

    var malformedUuid = exact(); malformedUuid.put(NativeAppAdoptionPolicy.SERVICE, "not-a-uuid");
    expect("malformed_uuid", malformedUuid, id, NativeAppAdoptionPolicy.Decision.REFUSE_IDENTITY, observed);

    var uuidDrift = exact(); uuidDrift.put(NativeAppAdoptionPolicy.SERVICE, "22222222-2222-4222-8222-222222222222");
    expect("uuid_drift", uuidDrift, id, NativeAppAdoptionPolicy.Decision.REFUSE_IDENTITY, observed);

    var taskName = exact(); taskName.put(NativeAppAdoptionPolicy.TASK_NAME, "OtherTask");
    expect("task_name_drift", taskName, id, NativeAppAdoptionPolicy.Decision.REFUSE_IDENTITY, observed);

    var malformedTaskId = exact(); malformedTaskId.put(NativeAppAdoptionPolicy.TASK_ID, "x");
    expect("malformed_task_id", malformedTaskId, id, NativeAppAdoptionPolicy.Decision.REFUSE_IDENTITY, observed);

    var taskId = exact(); taskId.put(NativeAppAdoptionPolicy.TASK_ID, "38");
    expect("task_id_drift", taskId, id, NativeAppAdoptionPolicy.Decision.REFUSE_IDENTITY, observed);

    var preparedDrift = ServiceId.builder(id).taskServiceId(38).build();
    expect("prepared_identity_drift", exact(), preparedDrift, NativeAppAdoptionPolicy.Decision.REFUSE_IDENTITY, observed);

    long adoptCount = observed.values().stream().filter("ADOPT"::equals).count();
    require(adoptCount == 1, "only exact match may adopt");

    StringBuilder body = new StringBuilder();
    body.append("result=PASS\n");
    body.append("metadata_field_count=8\n");
    body.append("case_count=").append(observed.size()).append("\n");
    body.append("adopt_count=").append(adoptCount).append("\n");
    body.append("exact_logical_name=").append(id.name()).append("\n");
    body.append("exact_service_uuid=").append(id.uniqueId()).append("\n");
    for (var entry : observed.entrySet()) {
      body.append("case.").append(entry.getKey()).append("=").append(entry.getValue()).append("\n");
    }
    Files.writeString(SENTINEL, body.toString(),
      StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
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
    temp=Path(tempfile.mkdtemp(prefix="collage-adoption-policy-"))
    derived="collage/cloudnet-adoption-policy:"+REF[:12]
    evidence_path=Path("cloudnet-adoption-policy-evidence.json")
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
  root = "modules:collage-adoption-policy",
  prefix = "collage-adoption-policy",
  subProjects = arrayOf("impl"),
)

'''
        if needle not in st: raise RepError("settings insertion point changed")
        settings.write_text(st.replace(needle,stanza+needle,1),encoding="utf-8")
        root=checkout/"modules/collage-adoption-policy/impl"
        java=root/"src/main/java/org/supracraft/collage/cloudnet"
        java.mkdir(parents=True)
        (root/"build.gradle.kts").write_text(BUILD_FILE,encoding="utf-8")
        (java/"NativeAppAdoptionPolicy.java").write_text(POLICY,encoding="utf-8")
        (java/"AdoptionPolicyProbeModule.java").write_text(MODULE,encoding="utf-8")
        run(["./gradlew",PROJECT+":jar","--no-daemon","--console=plain"],checkout)
        jars=[p for p in (root/"build/libs").glob("*.jar") if "sources" not in p.name and "javadoc" not in p.name]
        if len(jars)!=1: raise RepError("expected one probe jar")

        run(["docker","pull",IMAGE],temp,timeout=1200)
        revision=run(["docker","image","inspect",IMAGE,"--format",'{{ index .Config.Labels "org.opencontainers.image.revision" }}'],temp).stdout.strip()
        if revision!=REF: raise RepError("image revision mismatch")

        stage=temp/"derived"
        (stage/"modules").mkdir(parents=True)
        shutil.copy2(jars[0],stage/"modules/COLLAGE-Adoption-Policy-Probe.jar")
        (stage/"config.json").write_text("{}\n",encoding="utf-8")
        (stage/"Dockerfile").write_text(f"""FROM {IMAGE}
USER root
COPY --chown=cloudnet:cloudnet modules/ /home/cloudnet/modules/
COPY --chown=cloudnet:cloudnet config.json /home/cloudnet/config.json
ENV JAVA_TOOL_OPTIONS="-Dcloudnet.installation.skip=true"
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
            cp=run(["docker","cp",f"{CONTAINER}:/home/cloudnet/collage-adoption-policy.json",str(local)],temp,check=False)
            if cp.returncode==0 and local.is_file():
                raw=local.read_text(encoding="utf-8")
                parsed={}
                cases={}
                for line in raw.splitlines():
                    key,sep,value=line.partition("=")
                    if not sep:
                        continue
                    if key.startswith("case."):
                        cases[key[5:]]=value
                    else:
                        parsed[key]=value
                observed={
                    "result":parsed.get("result"),
                    "metadata_field_count":int(parsed.get("metadata_field_count","-1")),
                    "case_count":int(parsed.get("case_count","-1")),
                    "adopt_count":int(parsed.get("adopt_count","-1")),
                    "exact_logical_name":parsed.get("exact_logical_name"),
                    "exact_service_uuid":parsed.get("exact_service_uuid"),
                    "cases":cases,
                }
                break
            state=run(["docker","inspect",CONTAINER,"--format","{{.State.Status}} {{.State.ExitCode}}"],temp).stdout.strip()
            if state.startswith("exited"): break
            time.sleep(2)

        if not isinstance(observed,dict) or observed.get("result")!="PASS":
            logs=run(["docker","logs",CONTAINER],temp,check=False)
            raise RepError("no PASS sentinel\nobserved="+repr(observed)+"\n"+((logs.stdout or "")+(logs.stderr or ""))[-24000:])
        if observed.get("metadata_field_count")!=8 or observed.get("adopt_count")!=1:
            raise RepError("policy count mismatch: "+repr(observed))
        if observed.get("case_count")!=13:
            raise RepError("unexpected policy case count: "+repr(observed))

        evidence={
          "schema_version":1,
          "experiment":"EXP-000-CLOUDNET-001 native-App adoption policy",
          "result":"PASS",
          "upstream":{"repository":UPSTREAM,"ref":REF,"image":IMAGE,"oci_revision":revision},
          "observed":observed,
          "proven":[
            "the minimum re-adoption metadata set is eight non-secret fields",
            "the same service UUID, task name, and task-service id reconstruct exact CloudNet logical identity",
            "only an exact manager/fleet/world/schema/managed/ServiceId match is adoptable",
            "missing, foreign, malformed, world-drifted, or identity-drifted metadata fails closed"
          ],
          "non_claims":[
            "metadata cases are synthetic and no TrueNAS endpoint or credential was used",
            "no native App was created, queried, adopted, started, stopped, or deleted",
            "transport and runtime mutation remain separate later gates"
          ]
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
