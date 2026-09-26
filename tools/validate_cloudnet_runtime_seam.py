#!/usr/bin/env python3
"""Validate the exact CloudNet runtime-extension seam used by EXP-000-CLOUDNET-001."""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

UPSTREAM = "https://github.com/CloudNetService/CloudNet.git"
REF = "d74c455f766f25cbd6c7fba051ef4795b90a69c4"
FILES = {
    "factory": "node/api/src/main/java/eu/cloudnetservice/node/service/LocalCloudServiceFactory.java",
    "service": "node/api/src/main/java/eu/cloudnetservice/node/service/CloudService.java",
    "manager": "node/api/src/main/java/eu/cloudnetservice/node/service/CloudServiceManager.java",
    "abstract": "node/impl/src/main/java/eu/cloudnetservice/node/impl/service/defaults/AbstractService.java",
    "config": "driver/api/src/main/java/eu/cloudnetservice/driver/service/ServiceConfiguration.java",
    "docker_module": "modules/dockerized-services/impl/src/main/java/eu/cloudnetservice/modules/docker/impl/DockerizedServicesModule.java",
    "docker_factory": "modules/dockerized-services/impl/src/main/java/eu/cloudnetservice/modules/docker/impl/DockerizedLocalCloudServiceFactory.java",
    "docker_service": "modules/dockerized-services/impl/src/main/java/eu/cloudnetservice/modules/docker/impl/DockerizedService.java",
}

class ContractError(RuntimeError):
    pass

def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if cp.returncode:
        raise ContractError((cp.stderr or cp.stdout or "")[-4000:])
    return cp

def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise ContractError(f"missing {label}: {needle}")

def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def method_names(interface: str) -> list[str]:
    names = []
    pattern = r"(?m)^\s*(?:@[A-Za-z0-9_.()]+\s*)*(?:public\s+)?(?:@[A-Za-z0-9_.]+\s+)?[A-Za-z0-9_<>,?\[\] .@]+\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^;{}]*\)\s*;"
    for match in re.finditer(pattern, interface):
        names.append(match.group(1))
    return sorted(set(names))

def validate() -> dict:
    if not shutil.which("git"):
        raise ContractError("git is required")
    temp = Path(tempfile.mkdtemp(prefix="collage-cloudnet-contract-"))
    try:
        checkout = temp / "CloudNet"
        run(["git", "init", "--quiet", str(checkout)], temp)
        run(["git", "-C", str(checkout), "remote", "add", "origin", UPSTREAM], temp)
        run(["git", "-C", str(checkout), "fetch", "--quiet", "--depth", "1", "origin", REF], temp)
        run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", "FETCH_HEAD"], temp)
        actual = run(["git", "-C", str(checkout), "rev-parse", "HEAD"], temp).stdout.strip()
        if actual != REF:
            raise ContractError(f"commit mismatch: {actual}")

        src = {key: (checkout / path).read_text(encoding="utf-8") for key, path in FILES.items()}

        require(src["factory"], "public interface LocalCloudServiceFactory extends Named", "runtime factory interface")
        require(src["factory"], "CloudService createCloudService", "factory creation method")
        require(src["manager"], "addCloudServiceFactory", "factory registration API")
        require(src["manager"], "removeCloudServiceFactory", "factory removal API")
        require(src["manager"], "cloudServiceFactory(@NonNull String runtime)", "runtime lookup API")
        require(src["config"], "public @NonNull String runtime()", "service runtime selector")
        require(src["docker_module"], "serviceManager.addCloudServiceFactory", "real module factory registration")
        require(src["docker_module"], "DockerizedLocalCloudServiceFactory.class", "real Docker runtime factory")
        require(src["docker_factory"], "extends BaseLocalCloudServiceFactory", "Docker factory extension")
        require(src["docker_factory"], "new DockerizedService(", "Docker service realization")

        require(src["service"], "@NonNull Path directory()", "CloudService directory contract")
        require(src["service"], "@NonNull Path pluginDirectory()", "CloudService plugin directory contract")
        require(src["service"], "@NonNull Queue<ServiceTemplate> waitingTemplates()", "template contract")
        require(src["service"], "@NonNull Queue<ServiceDeployment> waitingDeployments()", "deployment contract")
        require(src["service"], "@NonNull Queue<ServiceRemoteInclusion> waitingIncludes()", "inclusion contract")
        require(src["service"], "@NonNull ServiceConsoleLogCache serviceConsoleLogCache()", "console cache contract")

        abstract = src["abstract"]
        require(abstract, "this.serviceDirectory = resolveServicePath", "CloudNet service directory ownership")
        require(abstract, "this.pluginDirectory = this.serviceDirectory", "CloudNet plugin directory")
        require(abstract, "manager.registerUnacceptedService(this)", "CloudNet local registration")
        require(abstract, "this.prepareService();", "RUNNING prepare path")
        require(abstract, "FileUtil.createDirectory(this.serviceDirectory)", "service directory creation")
        require(abstract, "FileUtil.createDirectory(this.pluginDirectory)", "plugin directory creation")
        require(abstract, "this.waitingTemplates.addAll(this.serviceConfiguration.templates())", "template preparation")
        require(abstract, "this.waitingDeployments.addAll(this.serviceConfiguration.deployments())", "deployment preparation")
        require(abstract, "this.waitingRemoteInclusions.addAll(this.serviceConfiguration.inclusions())", "inclusion preparation")
        require(abstract, "writeTo(this.serviceDirectory.resolve(WRAPPER_CONFIG_PATH))", "wrapper config write")
        require(abstract, "protected abstract void startProcess();", "externalizable start hook")
        require(abstract, "protected abstract void stopProcess();", "externalizable stop hook")
        require(abstract, "protected void doDelete()", "deletion hook")
        require(abstract, "protected void prepareService()", "preparation hook")
        require(abstract, "protected void updateLifecycle(", "lifecycle hook")
        require(src["docker_service"], "public class DockerizedService extends JVMService", "Docker runtime inheritance")

        methods = method_names(src["service"])
        return {
            "schema_version": 1,
            "result": "PASS",
            "experiment": "EXP-000-CLOUDNET-001 source-contract",
            "upstream": {"repository": UPSTREAM, "ref": REF},
            "extension_seam": {
                "named_runtime_factory": True,
                "module_can_register_factory_without_core_fork": True,
                "service_runtime_selector": True,
                "docker_module_uses_same_factory_seam": True,
            },
            "mandatory_semantics_observed": {
                "cloudservice_declared_method_count": len(methods),
                "cloudservice_declared_methods": methods,
                "service_directory": True,
                "plugin_directory": True,
                "templates": True,
                "deployments": True,
                "remote_inclusions": True,
                "console_log_cache": True,
                "cloudnet_registration": True,
            },
            "abstract_service_defaults": {
                "prepare_service_before_start": True,
                "creates_service_and_plugin_directories": True,
                "loads_templates_deployments_inclusions": True,
                "writes_wrapper_config": True,
                "start_hook_overridable": True,
                "stop_hook_overridable": True,
                "prepare_hook_overridable": True,
                "delete_hook_overridable": True,
                "lifecycle_hook_overridable": True,
            },
            "interpretation": {
                "seam_is_real": True,
                "thinness_not_yet_proven": True,
                "next_test": "compile a minimal native-runtime subclass/module that bypasses wrapper/world ownership without forking CloudNet core",
            },
            "source_sha256": {key: sha(value) for key, value in src.items()},
            "non_claims": [
                "no TrueNAS adapter implemented",
                "no live CloudNet runtime tested",
                "no H1-H4 verdict",
                "no decision yet to adopt or reject CloudNet",
            ],
        }
    finally:
        shutil.rmtree(temp, ignore_errors=True)

def main() -> int:
    try:
        evidence = validate()
        payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        Path("cloudnet-runtime-seam-evidence.json").write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
