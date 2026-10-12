package integration;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.concurrent.TimeUnit;

/** Focused real-process regression; no simulated Process or timing assertion. */
public final class HubRpcBridgeProcessTest {
    public static void main(String[] args) throws Exception {
        if (args.length == 2 && "child".equals(args[0])) {
            Files.write(Paths.get(args[1]), new byte[]{1});
            Thread.sleep(60000);
            return;
        }
        for (boolean interrupted : new boolean[]{false, true}) {
            Path directory = Files.createTempDirectory("hub-process-test-");
            Path ready = directory.resolve("ready");
            Process child = new ProcessBuilder(Paths.get(System.getProperty("java.home"), "bin", "java").toString(),
                    "-cp", System.getProperty("java.class.path"), HubRpcBridgeProcessTest.class.getName(), "child", ready.toString()).start();
            try {
                long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
                while (!Files.exists(ready) && child.isAlive() && System.nanoTime() < deadline) Thread.sleep(10);
                if (!Files.exists(ready)) throw new AssertionError("test child did not start");
                if (interrupted) Thread.currentThread().interrupt();
                HubRpcBridge.terminateBounded(child);
                if (child.isAlive()) throw new AssertionError("child survived bounded cleanup");
                if (Thread.currentThread().isInterrupted() != interrupted) throw new AssertionError("interrupt state was not preserved");
            } finally {
                Thread.interrupted();
                HubRpcBridge.terminateBounded(child);
                Files.deleteIfExists(ready); Files.delete(directory);
            }
        }
        System.out.println("PASS normal and interrupted subprocess cleanup");
    }
}
