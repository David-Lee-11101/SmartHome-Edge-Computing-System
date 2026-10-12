package integration;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import concurrency.runtime.SchedulePlan;
import concurrency.runtime.SchedulerPorts;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.TimeUnit;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/** Trusted local integration callback; never accepts executable commands in a plan. */
public final class HubRpcBridge implements SchedulerPorts.ActionHandler, SchedulerPorts.ConditionEvaluator {
    private static final Gson JSON = new Gson();

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isEmpty()) throw new IllegalArgumentException("missing Hub runtime setting: " + name);
        return value;
    }

    private static JsonObject invoke(String operation, String arguments, boolean graph) throws Exception {
        Path output = Files.createTempFile("hub-rpc-", ".json");
        Path errors = Files.createTempFile("hub-rpc-", ".log");
        Process process = null;
        try {
            List<String> command = new ArrayList<>(Arrays.asList(required("HUB_JAVA"), "-cp", required("HUB_LOGIC_CP"),
                    "io.smarthome.logic.tinyrpc.TinyRpcLogicCli", graph ? "invoke-graph" : "invoke",
                    "127.0.0.1", required("HUB_PROVIDER_PORT"), required("HUB_SERVICE_ID"), operation, arguments));
            if (graph) command.addAll(Arrays.asList("--descriptor-file", required("HUB_DESCRIPTOR_FILE"),
                    "--trace-file", Paths.get(required("HUB_TRACE_ROOT"), "action-trace-" + java.util.UUID.randomUUID() + ".json").toString()));
            process = new ProcessBuilder(command)
                    .redirectOutput(output.toFile()).redirectError(errors.toFile()).start();
            if (!process.waitFor(15, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor(2, TimeUnit.SECONDS);
                throw new IllegalStateException("RPC callback timed out");
            }
            if (process.exitValue() != 0) throw new IllegalStateException("RPC callback failed");
            if (Files.size(output) > 65536) throw new IllegalStateException("RPC callback output exceeded bound");
            JsonObject result = JSON.fromJson(new String(Files.readAllBytes(output), StandardCharsets.UTF_8), JsonObject.class);
            if (!"success".equals(result.get("status").getAsString())) throw new IllegalStateException("RPC callback rejected");
            return result;
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw interrupted;
        } finally {
            try { terminateBounded(process); }
            finally { Files.deleteIfExists(output); Files.deleteIfExists(errors); }
        }
    }

    static void terminateBounded(Process process) {
        if (process == null || !process.isAlive()) return;
        boolean interrupted = Thread.interrupted();
        try {
            process.destroy();
            try {
                if (!process.waitFor(2, TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                    process.waitFor(2, TimeUnit.SECONDS);
                }
            } catch (InterruptedException interruption) {
                interrupted = true;
                process.destroyForcibly();
                try { process.waitFor(2, TimeUnit.SECONDS); }
                catch (InterruptedException repeated) { interrupted = true; }
            }
            if (process.isAlive()) throw new IllegalStateException("RPC subprocess cleanup did not complete");
        } finally { if (interrupted) Thread.currentThread().interrupt(); }
    }

    @Override public boolean evaluate(SchedulePlan plan, SchedulePlan.Task task) throws Exception {
        for (SchedulePlan.Condition condition : plan.getConditions()) {
            if (!"condition.enabled".equals(condition.getNodeId())) throw new IllegalArgumentException("unsupported live condition");
            JsonObject actual = invoke("readEnabled", "[]", false).getAsJsonObject("value");
            if (!actual.equals(JSON.toJsonTree(condition.getExpected()))) return false;
        }
        return true;
    }

    @Override public void invoke(SchedulePlan.Action action, SchedulerPorts.CancellationToken cancellation) throws Exception {
        if (cancellation.isCancelled()) throw new IllegalStateException("cancelled before action");
        if (!required("HUB_SERVICE_ID").equals(action.getServiceId()) || !"setEnabled".equals(action.getOperation())) {
            throw new IllegalArgumentException("unsupported integration action");
        }
        Path decisionFile = Paths.get(required("HUB_DECISION_FILE"));
        JsonObject decision = JSON.fromJson(new String(Files.readAllBytes(decisionFile), StandardCharsets.UTF_8), JsonObject.class);
        String kind = decision.get("decision").getAsString();
        if (!("proceed".equals(kind) || "reorder".equals(kind))) throw new IllegalStateException("decision did not authorize action");
        JsonObject record = new JsonObject();
        record.addProperty("decisionId", decision.get("decisionId").getAsString());
        record.addProperty("decisionBytesPresentBeforeAction", Files.size(decisionFile));
        record.addProperty("actionStartedAt", java.time.Instant.now().toString());
        record.add("result", invoke(action.getOperation(), JSON.toJson(action.getArguments()), true));
        Files.write(Paths.get(required("HUB_ACTION_JOURNAL")), (JSON.toJson(record) + "\n").getBytes(StandardCharsets.UTF_8),
                StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }
}
