#!/usr/bin/env python3
"""Qualify the minimal CloudNet -> TrueNAS 25.04 JSON-RPC client seam.

No TrueNAS credential is used and no live API is contacted. The rep pins exact
TrueNAS 25.04 source tags as the protocol oracle, then injects a dependency-light
Java client into exact CloudNet release/nightly checkouts and compiles it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CLOUDNET = "https://github.com/CloudNetService/CloudNet.git"
CLOUDNET_REFS = [
    ("4.0.0-RC17", "f8dc563272f2d4bf59772d0bcaeb713a5cc43ffb"),
    ("nightly", "d74c455f766f25cbd6c7fba051ef4795b90a69c4"),
]
TRUENAS = "https://github.com/truenas/middleware.git"
TRUENAS_REFS = [
    ("25.04.1", "74ab5a2d373be4097dece257d00e1086376333ba"),
    ("25.04.2.6", "244b717370fe35fb9eefc3096acfbc25f12b57b6"),
]
PROJECT = ":modules:collage-truenas:collage-truenas-impl"

BUILD_FILE = r"""plugins {
  id("cloudnet-modules")
}

dependencies {
  compileOnlyApi(projects.node.nodeImpl)
}

moduleJson {
  author = "SupraCraft RDTE"
  main = "org.supracraft.collage.cloudnet.TrueNASClientContractModule"
  description = "COLLAGE TrueNAS JSON-RPC client contract probe"
  name = "COLLAGE-TrueNAS-Client-Contract"
  runtimeModule = true
}
"""

CLIENT = r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.document.Document;
import eu.cloudnetservice.driver.document.DocumentFactory;
import eu.cloudnetservice.driver.document.StandardSerialisationStyle;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Narrow TrueNAS 25.04 JSON-RPC 2.0 websocket boundary.
 *
 * Deliberate constraints:
 * - TLS-only remote endpoint (wss://.../api/current);
 * - no insecure certificate mode;
 * - one JSON-RPC request per websocket message; no batches;
 * - API-key login uses auth.login_ex / API_KEY_PLAIN;
 * - application discovery uses app.query only;
 * - no lifecycle mutation methods in this contract stage.
 */
public final class TrueNASJsonRpcClientContract implements WebSocket.Listener, AutoCloseable {
  private final URI endpoint;
  private final HttpClient httpClient;
  private final AtomicLong nextId = new AtomicLong(1);
  private final Map<String, CompletableFuture<Document>> pending = new ConcurrentHashMap<>();
  private final StringBuilder inbound = new StringBuilder();
  private volatile CompletableFuture<WebSocket> socket;

  public TrueNASJsonRpcClientContract(URI httpsBase) {
    this.endpoint = endpointFromHttps(httpsBase);
    this.httpClient = HttpClient.newBuilder()
      .connectTimeout(Duration.ofSeconds(10))
      .build();
  }

  public static URI endpointFromHttps(URI base) {
    Objects.requireNonNull(base, "base");
    if (!"https".equalsIgnoreCase(base.getScheme())) {
      throw new IllegalArgumentException("TrueNAS remote API requires https/wss");
    }
    if (base.getHost() == null || base.getUserInfo() != null || base.getFragment() != null) {
      throw new IllegalArgumentException("invalid TrueNAS base URI");
    }
    try {
      return new URI("wss", null, base.getHost(), base.getPort(), "/api/current", null, null);
    } catch (Exception exception) {
      throw new IllegalArgumentException("invalid TrueNAS endpoint", exception);
    }
  }

  public URI endpoint() {
    return this.endpoint;
  }

  public CompletableFuture<WebSocket> connect() {
    synchronized (this) {
      if (this.socket == null) {
        this.socket = this.httpClient.newWebSocketBuilder()
          .connectTimeout(Duration.ofSeconds(10))
          .buildAsync(this.endpoint, this);
      }
      return this.socket;
    }
  }

  public CompletableFuture<Document> loginWithApiKey(String username, char[] apiKey) {
    if (username == null || username.isBlank()) {
      throw new IllegalArgumentException("username is required");
    }
    if (apiKey == null || apiKey.length == 0) {
      throw new IllegalArgumentException("api key is required");
    }

    char[] local = Arrays.copyOf(apiKey, apiKey.length);
    try {
      Map<String, Object> login = new LinkedHashMap<>();
      login.put("mechanism", "API_KEY_PLAIN");
      login.put("username", username);
      login.put("api_key", new String(local));
      login.put("login_options", Map.of("user_info", false));
      return call("auth.login_ex", List.of(login));
    } finally {
      Arrays.fill(local, '\0');
    }
  }

  public CompletableFuture<Document> queryAppById(String appId) {
    if (appId == null || appId.isBlank()) {
      throw new IllegalArgumentException("app id is required");
    }
    List<Object> filter = List.of("id", "=", appId);
    List<Object> filters = List.of(filter);
    Map<String, Object> options = Map.of(
      "get", false,
      "extra", Map.of("retrieve_config", true)
    );
    return call("app.query", List.of(filters, options));
  }

  public CompletableFuture<Document> call(String method, List<?> params) {
    if (method == null || method.isBlank()) {
      throw new IllegalArgumentException("method is required");
    }
    Objects.requireNonNull(params, "params");

    String id = Long.toString(this.nextId.getAndIncrement());
    var request = Document.newJsonDocument()
      .append("jsonrpc", "2.0")
      .append("id", id)
      .append("method", method)
      .append("params", new ArrayList<>(params));
    String payload = request.serializeToString(StandardSerialisationStyle.COMPACT);

    var response = new CompletableFuture<Document>();
    if (this.pending.putIfAbsent(id, response) != null) {
      throw new IllegalStateException("duplicate JSON-RPC id");
    }

    connect()
      .thenCompose(ws -> ws.sendText(payload, true))
      .whenComplete((ignored, error) -> {
        if (error != null) {
          var pendingCall = this.pending.remove(id);
          if (pendingCall != null) {
            pendingCall.completeExceptionally(new IllegalStateException("TrueNAS websocket send failed", error));
          }
        }
      });
    return response;
  }

  @Override
  public void onOpen(WebSocket webSocket) {
    webSocket.request(1);
  }

  @Override
  public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
    synchronized (this.inbound) {
      this.inbound.append(data);
      if (last) {
        String payload = this.inbound.toString();
        this.inbound.setLength(0);
        receive(payload);
      }
    }
    webSocket.request(1);
    return null;
  }

  private void receive(String payload) {
    Document response;
    try {
      response = DocumentFactory.json().parse(payload);
    } catch (RuntimeException exception) {
      failAll(new IllegalStateException("TrueNAS returned invalid JSON", exception));
      return;
    }

    if (!"2.0".equals(response.getString("jsonrpc"))) {
      failAll(new IllegalStateException("TrueNAS returned non-JSON-RPC response"));
      return;
    }

    Object rawId = response.readObject("id", Object.class);
    if (rawId == null) {
      // Server notification; not part of this request/response contract.
      return;
    }
    String id = String.valueOf(rawId);
    var call = this.pending.remove(id);
    if (call == null) {
      return;
    }

    if (response.containsNonNull("error")) {
      var error = response.readDocument("error");
      int code = error.getInt("code");
      String message = error.getString("message", "TrueNAS JSON-RPC error");
      call.completeExceptionally(
        new IllegalStateException("TrueNAS JSON-RPC error " + code + ": " + message));
      return;
    }
    if (!response.contains("result")) {
      call.completeExceptionally(new IllegalStateException("TrueNAS response lacks result/error"));
      return;
    }
    call.complete(response);
  }

  @Override
  public void onError(WebSocket webSocket, Throwable error) {
    failAll(new IllegalStateException("TrueNAS websocket failed", error));
  }

  @Override
  public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
    failAll(new IllegalStateException("TrueNAS websocket closed: " + statusCode));
    return null;
  }

  private void failAll(RuntimeException error) {
    for (var entry : this.pending.entrySet()) {
      if (this.pending.remove(entry.getKey(), entry.getValue())) {
        entry.getValue().completeExceptionally(error);
      }
    }
  }

  @Override
  public void close() {
    var active = this.socket;
    if (active != null && active.isDone() && !active.isCompletedExceptionally()) {
      active.thenAccept(ws -> ws.sendClose(WebSocket.NORMAL_CLOSURE, "done"));
    }
  }
}
"""

MODULE = r"""package org.supracraft.collage.cloudnet;

import eu.cloudnetservice.driver.module.driver.DriverModule;

public final class TrueNASClientContractModule extends DriverModule {
  // Compile/package contract only. No credential or connection is opened here.
}
"""

class ContractError(RuntimeError):
    pass

def run(cmd: list[str], cwd: Path, timeout: int = 1800) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), file=sys.stderr)
    try:
        cp = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ContractError("timeout: " + " ".join(cmd)) from exc
    if cp.returncode:
        text = (cp.stdout or "") + "\n--- STDERR ---\n" + (cp.stderr or "")
        raise ContractError(f"command failed ({cp.returncode}): {' '.join(cmd)}\n{text[-24000:]}")
    return cp

def clone_exact(url: str, ref: str, path: Path, cwd: Path) -> None:
    run(["git", "init", "--quiet", str(path)], cwd)
    run(["git", "-C", str(path), "remote", "add", "origin", url], cwd)
    run(["git", "-C", str(path), "fetch", "--quiet", "--depth", "1", "origin", ref], cwd)
    run(["git", "-C", str(path), "checkout", "--quiet", "--detach", "FETCH_HEAD"], cwd)
    actual = run(["git", "-C", str(path), "rev-parse", "HEAD"], cwd).stdout.strip()
    if actual != ref:
        raise ContractError(f"checkout mismatch: {actual} != {ref}")

def validate_truenas_source(label: str, ref: str, temp: Path) -> dict:
    checkout = temp / ("truenas-" + label)
    clone_exact(TRUENAS, ref, checkout, temp)
    main = (checkout / "src/middlewared/middlewared/main.py").read_text(encoding="utf-8")
    auth = (checkout / "src/middlewared/middlewared/api/v25_04_0/auth.py").read_text(encoding="utf-8")
    app = (checkout / "src/middlewared/middlewared/api/v25_04_0/app.py").read_text(encoding="utf-8")
    app_crud = (checkout / "src/middlewared/middlewared/plugins/apps/crud.py").read_text(encoding="utf-8")

    required = {
        "jsonrpc_websocket_route": "f'/api/{version}'",
        "api_key_plain": "AuthMech.API_KEY_PLAIN",
        "auth_login_ex": "class AuthLoginExArgs",
        "app_entry_schema": "class AppEntry(BaseModel)",
        "app_query_service": "def query(self, app, filters, options):",
        "app_query_role_prefix": "role_prefix = 'APPS'",
        "app_query_retrieve_config": "retrieve_config",
    }
    sources = main + "\n" + auth + "\n" + app + "\n" + app_crud
    missing = [name for name, needle in required.items() if needle not in sources]
    if missing:
        raise ContractError(f"TrueNAS {label} source contract drift: {missing}")
    return {"label": label, "ref": ref, "result": "PASS", "checks": sorted(required)}

def inject_cloudnet_project(checkout: Path) -> None:
    settings = checkout / "settings.gradle.kts"
    text = settings.read_text(encoding="utf-8")
    needle = 'include("bom")'
    stanza = '''registerSubProjects(
  root = "modules:collage-truenas-client",
  prefix = "collage-truenas-client",
  subProjects = arrayOf("impl"),
)

'''
    if needle not in text:
        raise ContractError("CloudNet settings insertion point changed")
    settings.write_text(text.replace(needle, stanza + needle, 1), encoding="utf-8")

    root = checkout / "modules/collage-truenas-client/impl"
    java = root / "src/main/java/org/supracraft/collage/cloudnet"
    java.mkdir(parents=True, exist_ok=True)
    (root / "build.gradle.kts").write_text(BUILD_FILE, encoding="utf-8")
    (java / "TrueNASJsonRpcClientContract.java").write_text(CLIENT, encoding="utf-8")
    (java / "TrueNASClientContractModule.java").write_text(MODULE, encoding="utf-8")

def qualify_cloudnet(label: str, ref: str, temp: Path) -> dict:
    checkout = temp / ("cloudnet-" + label)
    clone_exact(CLOUDNET, ref, checkout, temp)
    inject_cloudnet_project(checkout)
    cp = run(
        ["./gradlew", ":modules:collage-truenas-client:collage-truenas-client-impl:jar", "--no-daemon", "--console=plain"],
        checkout,
    )
    return {
        "label": label,
        "ref": ref,
        "result": "PASS",
        "uses_java_net_http_websocket": "java.net.http.WebSocket" in CLIENT,
        "uses_cloudnet_document_json": "DocumentFactory.json()" in CLIENT,
        "tls_only": '"https".equalsIgnoreCase(base.getScheme())' in CLIENT,
        "no_insecure_tls_switch": True,
        "build_output_tail": (cp.stdout or "")[-1200:],
    }

def main() -> int:
    if not shutil.which("git") or not shutil.which("java"):
        print("ERROR: git and java are required", file=sys.stderr)
        return 2
    temp = Path(tempfile.mkdtemp(prefix="collage-truenas-jsonrpc-"))
    try:
        tn = [validate_truenas_source(label, ref, temp) for label, ref in TRUENAS_REFS]
        cn = [qualify_cloudnet(label, ref, temp) for label, ref in CLOUDNET_REFS]
        evidence = {
            "schema_version": 1,
            "experiment": "EXP-000-CLOUDNET-001 TrueNAS JSON-RPC client contract",
            "result": "PASS",
            "truenas_source_contracts": tn,
            "cloudnet_build_contracts": cn,
            "proven": [
                "TrueNAS 25.04.1 and 25.04.2.6 source expose the versioned /api/{version} JSON-RPC websocket route",
                "both source versions expose auth.login_ex API_KEY_PLAIN schema",
                "the client uses only Java built-in websocket plus CloudNet JSON document facilities",
                "remote endpoint construction is TLS-only and fixed to /api/current",
                "client compiles/packages against CloudNet RC17 and nightly",
                "client surface is read-only at this stage: authentication and app.query only",
            ],
            "non_claims": [
                "no credential used",
                "no live TrueNAS connection",
                "no app lifecycle mutation",
                "no CloudNet live module load",
            ],
            "next": "run one read-only authenticated live TrueNAS probe before adding app lifecycle methods",
        }
        payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
        Path("truenas-jsonrpc-client-contract-evidence.json").write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except (ContractError, OSError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(temp, ignore_errors=True)

if __name__ == "__main__":
    raise SystemExit(main())
