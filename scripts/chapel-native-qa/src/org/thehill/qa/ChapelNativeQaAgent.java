package org.thehill.qa;

import java.io.File;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.lang.instrument.Instrumentation;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;
import java.util.stream.Stream;

/**
 * Native Minecraft screenshot driver for the isolated Hill Chapel QA world.
 *
 * <p>The agent does not transform game classes. It waits for the named vanilla
 * client, schedules supported commands on the integrated-server executor, and
 * invokes vanilla Screenshot.grab on the render executor.</p>
 */
public final class ChapelNativeQaAgent {
    private static final String CLIENT_CLASS = "net.minecraft.client.Minecraft";
    private static final String SCREENSHOT_CLASS = "net.minecraft.client.Screenshot";
    private static final List<ViewResult> RESULTS = new ArrayList<>();
    private static final List<String> HANDLED_SCREENS = new ArrayList<>();
    private static final List<String> ACTIVE_RESOURCE_PACKS = new ArrayList<>();
    private static Properties configuration;
    private static Path reportPath;
    private static Object minecraft;
    private static String status = "starting";
    private static String failure;
    private static boolean nativeBackupRequested;
    private static boolean conversionCompleted;
    private static boolean captureInputProbePassed;

    private ChapelNativeQaAgent() {}

    public static void main(String[] arguments) throws Exception {
        if (arguments.length != 3 || !arguments[0].equals("--validate-config")) {
            throw new IllegalArgumentException(
                "usage: ChapelNativeQaAgent --validate-config CONFIG EXPECTED_BACKUP"
            );
        }
        Properties loaded = loadConfiguration(Path.of(arguments[1]));
        String actual = loaded.getProperty("preupgrade.backup");
        if (!arguments[2].equals(actual)) {
            throw new IllegalStateException(
                "properties round trip changed preupgrade.backup: expected="
                    + arguments[2] + ", actual=" + actual
            );
        }
        System.out.println("configuration round trip verified");
    }

    public static void premain(String agentArguments, Instrumentation instrumentation) {
        Thread worker = new Thread(ChapelNativeQaAgent::run, "hill-chapel-native-qa");
        worker.setDaemon(true);
        worker.setUncaughtExceptionHandler((thread, throwable) -> {
            failure = stackTrace(throwable);
            status = "failed";
            writeReportQuietly();
            stopClientQuietly();
        });
        worker.start();
    }

    private static void run() {
        try {
            Path configPath = requiredPathProperty("chapel.qa.config");
            reportPath = requiredPathProperty("chapel.qa.report");
            configuration = loadConfiguration(configPath);
            status = "waiting_for_world";
            writeReport();

            long startupTimeout = longProperty("startup.timeout.seconds", 180L);
            minecraft = waitForWorld(startupTimeout);
            conversionCompleted = nativeBackupRequested;
            String mode = System.getProperty("chapel.qa.mode", "capture");
            boolean interactive = mode.equals("interactive");
            if (!interactive && !mode.equals("capture")) {
                throw new IllegalArgumentException("chapel.qa.mode must be capture or interactive");
            }
            configureClient(minecraft, !interactive);
            verifyActiveResourcePacks(minecraft);
            Object server = invoke(minecraft, "getSingleplayerServer");
            if (interactive) {
                configureInteractiveStart(server);
                status = "ready";
                writeReport();
                if (Boolean.getBoolean("chapel.qa.exit.when.ready")) {
                    Thread.sleep(longProperty("exit.delay.millis", 1500L));
                    stopClient();
                }
                return;
            }
            configureWorld(server);
            probeCaptureInputIsolation();

            int viewCount = integerProperty("view.count", 0);
            if (viewCount < 1 || viewCount > 16) {
                throw new IllegalArgumentException("view.count must be between 1 and 16");
            }
            status = "capturing";
            writeReport();
            for (int index = 0; index < viewCount; index++) {
                captureView(server, readView(index));
            }
            status = "complete";
            writeReport();
            Thread.sleep(longProperty("exit.delay.millis", 1500L));
            stopClient();
        } catch (Throwable throwable) {
            failure = stackTrace(throwable);
            status = "failed";
            writeReportQuietly();
            stopClientQuietly();
        }
    }

    private static Object waitForWorld(long timeoutSeconds) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(timeoutSeconds);
        Class<?> clientClass = null;
        Throwable lastProblem = null;
        while (System.nanoTime() < deadline) {
            try {
                if (clientClass == null) {
                    clientClass = Class.forName(
                        CLIENT_CLASS,
                        false,
                        ClassLoader.getSystemClassLoader()
                    );
                }
                Object candidate = clientClass.getMethod("getInstance").invoke(null);
                if (candidate != null) {
                    minecraft = candidate;
                    handleKnownStartupScreens(candidate);
                }
                if (candidate != null && publicField(candidate, "player") != null
                    && publicField(candidate, "level") != null
                    && invoke(candidate, "getSingleplayerServer") != null
                    && Boolean.TRUE.equals(invoke(candidate, "isGameLoadFinished"))) {
                    return candidate;
                }
            } catch (Throwable throwable) {
                lastProblem = throwable;
            }
            Thread.sleep(250L);
        }
        throw new IllegalStateException(
            "Minecraft integrated world did not become ready within " + timeoutSeconds + " seconds",
            lastProblem
        );
    }

    private static void configureClient(Object client, boolean captureMode) throws Exception {
        runOn(client, () -> {
            Object options = publicField(client, "options");
            setPublicField(options, "hideGui", captureMode);
            setPublicField(options, "pauseOnLostFocus", false);
            setPublicField(options, "skipMultiplayerWarning", true);
            setPublicField(options, "joinedFirstServer", true);
            setOption(options, "renderDistance", integerProperty("render.distance", 16));
            setOption(options, "simulationDistance", integerProperty("simulation.distance", 10));
            setOption(options, "fov", integerProperty("fov", 70));
            setOption(options, "narratorHotkey", false);
            setEnumOption(options, "narrator", "net.minecraft.client.NarratorStatus", "OFF");
            setEnumOption(options, "cloudStatus", "net.minecraft.client.CloudStatus", "OFF");
            setMusicVolume(options, 0.0D);
            setPublicEnumField(
                options,
                "tutorialStep",
                "net.minecraft.client.tutorial.TutorialSteps",
                "NONE"
            );
            String resourcePack = configuration.getProperty("resource.pack.id");
            if (resourcePack != null && !resourcePack.isBlank()) {
                setPublicField(
                    options,
                    "resourcePacks",
                    new ArrayList<>(List.of("vanilla", resourcePack))
                );
                setPublicField(options, "incompatibleResourcePacks", new ArrayList<>());
            }
            invoke(options, "onboardingAccessibilityFinished");
            setFirstPerson(options);
            invoke(options, "save");
            if (captureMode) {
                clearScreen(client);
                suppressCaptureInputOnRenderThread(client);
            }
        });
    }

    private static void handleKnownStartupScreens(Object client) throws Exception {
        runOn(client, () -> {
            Object screen = publicField(client, "screen");
            if (screen == null) {
                return;
            }
            String screenClass = screen.getClass().getName();
            if (screenClass.equals("net.minecraft.client.gui.screens.BackupConfirmScreen")
                && !nativeBackupRequested) {
                Path launcherBackup = Path.of(requiredProperty("preupgrade.backup"));
                if (!Files.isRegularFile(launcherBackup) || Files.size(launcherBackup) == 0L) {
                    throw new IllegalStateException(
                        "refusing native upgrade without verified launcher backup: " + launcherBackup
                    );
                }
                Field listenerField = screen.getClass().getDeclaredField("onProceed");
                listenerField.setAccessible(true);
                Object listener = listenerField.get(screen);
                Class<?> listenerClass = Class.forName(
                    "net.minecraft.client.gui.screens.BackupConfirmScreen$Listener"
                );
                listenerClass.getMethod("proceed", boolean.class, boolean.class)
                    .invoke(listener, true, false);
                nativeBackupRequested = true;
                HANDLED_SCREENS.add("BackupConfirmScreen:backup_and_join");
                status = "upgrading_world";
                writeReport();
                return;
            }
            if (screenClass.equals("net.minecraft.client.gui.screens.ConfirmScreen")
                && componentTranslationKey(invoke(screen, "getTitle")).equals("upgradeWorld.done")
                && !HANDLED_SCREENS.contains("ConfirmScreen:upgradeWorld.done:join_now")) {
                Field callbackField = screen.getClass().getDeclaredField("callback");
                callbackField.setAccessible(true);
                Object callback = callbackField.get(screen);
                Class<?> booleanConsumer = Class.forName(
                    "it.unimi.dsi.fastutil.booleans.BooleanConsumer"
                );
                booleanConsumer.getMethod("accept", boolean.class).invoke(callback, true);
                HANDLED_SCREENS.add("ConfirmScreen:upgradeWorld.done:join_now");
                status = "joining_converted_world";
                writeReport();
            }
        });
    }

    private static String componentTranslationKey(Object component) throws Exception {
        Object contents = invoke(component, "getContents");
        if (!contents.getClass().getName().equals(
            "net.minecraft.network.chat.contents.TranslatableContents"
        )) {
            return "";
        }
        return String.valueOf(invoke(contents, "getKey"));
    }

    private static void configureInteractiveStart(Object server) throws Exception {
        String playerName = requiredProperty("player.name");
        View start = readView(0);
        double feetY = start.eye[1] - doubleProperty("camera.eye.height", 1.62);
        double[] angles = minecraftAngles(start.eye, start.target);
        String teleport = String.format(
            Locale.ROOT,
            "teleport %s %.6f %.6f %.6f %.6f %.6f",
            playerName,
            start.eye[0],
            feetY,
            start.eye[2],
            angles[0],
            angles[1]
        );
        runOn(server, () -> {
            executeCommand(server, "gamemode creative " + playerName);
            executeCommand(server, teleport);
        });
        ensureGameplayScreen(false);
    }

    private static void verifyActiveResourcePacks(Object client) throws Exception {
        runOn(client, () -> {
            Object manager = invoke(client, "getResourceManager");
            Object rawStream = invoke(manager, "listPacks");
            Class<?> packResources = Class.forName("net.minecraft.server.packs.PackResources");
            Method packId = packResources.getMethod("packId");
            ACTIVE_RESOURCE_PACKS.clear();
            try (Stream<?> stream = (Stream<?>) rawStream) {
                for (Object pack : stream.toList()) {
                    ACTIVE_RESOURCE_PACKS.add(String.valueOf(packId.invoke(pack)));
                }
            }
            String expected = configuration.getProperty("resource.pack.id");
            if (expected != null && !expected.isBlank() && !ACTIVE_RESOURCE_PACKS.contains(expected)) {
                throw new IllegalStateException(
                    "configured resource pack is not active: " + expected
                        + "; active=" + ACTIVE_RESOURCE_PACKS
                );
            }
        });
    }

    private static void configureWorld(Object server) throws Exception {
        String playerName = requiredProperty("player.name");
        runOn(server, () -> {
            executeCommand(server, "gamerule advance_time false");
            executeCommand(server, "gamerule advance_weather false");
            executeCommand(server, "gamerule spawn_mobs false");
            executeCommand(server, "time set noon");
            executeCommand(server, "weather clear");
            executeCommand(server, "gamemode spectator " + playerName);
        });
        Thread.sleep(1000L);
    }

    private static void probeCaptureInputIsolation() throws Exception {
        suppressCaptureInput();
        CameraState before = readCameraState();
        runOn(minecraft, () -> {
            Object options = publicField(minecraft, "options");
            Object forward = publicField(options, "keyUp");
            findMethod(forward.getClass(), "setDown", 1).invoke(forward, true);
            if (!Boolean.TRUE.equals(invoke(forward, "isDown"))) {
                throw new IllegalStateException("capture input probe could not hold forward mapping");
            }
            assertCaptureInputIsIdleOnRenderThread();
        });

        boolean passed = false;
        try {
            Thread.sleep(250L);
            CameraState after = readCameraState();
            if (distance(after.eye, before.eye) > 0.01
                || angleDistance(after.yaw, before.yaw) > 0.01
                || Math.abs(after.pitch - before.pitch) > 0.01) {
                throw new IllegalStateException(
                    "held-key capture input probe moved camera; before=" + before + ", after=" + after
                );
            }
            runOn(minecraft, ChapelNativeQaAgent::assertCaptureInputIsIdleOnRenderThread);
            passed = true;
        } finally {
            suppressCaptureInput();
        }
        captureInputProbePassed = passed;
    }

    private static void captureView(Object server, View view) throws Exception {
        double eyeHeight = doubleProperty("camera.eye.height", 1.62);
        double feetY = view.eye[1] - eyeHeight;
        double[] angles = minecraftAngles(view.eye, view.target);
        int actualFov = applyFov(view.fov);
        String playerName = requiredProperty("player.name");
        String command = String.format(
            Locale.ROOT,
            "teleport %s %.6f %.6f %.6f %.6f %.6f",
            playerName,
            view.eye[0],
            feetY,
            view.eye[2],
            angles[0],
            angles[1]
        );
        runOn(server, () -> executeCommand(server, command));

        ensureGameplayScreen(true);
        CameraState actual = waitForCamera(view.eye, angles, longProperty("camera.timeout.seconds", 20L));
        long settleMillis = longProperty("settle.millis", 8000L);
        Thread.sleep(settleMillis);
        // Reapply the requested pose after chunk/render settling. A focused game
        // window can otherwise accumulate mouse input during the settle period.
        runOn(server, () -> executeCommand(server, command));
        ensureGameplayScreen(true);
        actual = waitForCamera(view.eye, angles, longProperty("camera.timeout.seconds", 20L));
        actualFov = applyFov(view.fov);
        suppressCaptureInput();
        actual = readCameraState();
        requireCameraPose(actual, view.eye, angles);

        String filename = view.name + ".png";
        ScreenshotResult screenshot = grabScreenshot(filename);
        ViewResult result = new ViewResult(
            view,
            angles[0],
            angles[1],
            feetY,
            actualFov,
            actual,
            screenshot.path,
            screenshot.callback,
            Files.size(screenshot.path),
            sha256(screenshot.path),
            Instant.now().toString()
        );
        synchronized (RESULTS) {
            RESULTS.add(result);
        }
        writeReport();
    }

    private static int applyFov(int requestedFov) throws Exception {
        if (requestedFov < 30 || requestedFov > 110) {
            throw new IllegalArgumentException("view FOV must be between 30 and 110");
        }
        AtomicReference<Integer> actual = new AtomicReference<>();
        runOn(minecraft, () -> {
            Object options = publicField(minecraft, "options");
            setOption(options, "fov", requestedFov);
            Object option = invoke(options, "fov");
            actual.set(((Number) invoke(option, "get")).intValue());
        });
        if (actual.get() == null || actual.get() != requestedFov) {
            throw new IllegalStateException(
                "camera FOV did not apply; requested=" + requestedFov + ", actual=" + actual.get()
            );
        }
        return actual.get();
    }

    private static CameraState waitForCamera(
        double[] expectedEye,
        double[] expectedAngles,
        long timeoutSeconds
    ) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(timeoutSeconds);
        CameraState latest = null;
        while (System.nanoTime() < deadline) {
            latest = readCameraState();
            if (distance(latest.eye, expectedEye) <= 0.01
                && angleDistance(latest.yaw, expectedAngles[0]) <= 0.01
                && Math.abs(latest.pitch - expectedAngles[1]) <= 0.01) {
                return latest;
            }
            Thread.sleep(100L);
        }
        throw new IllegalStateException(
            "camera did not reach requested pose; latest=" + (latest == null ? "none" : latest)
        );
    }

    private static void requireCameraPose(
        CameraState actual,
        double[] expectedEye,
        double[] expectedAngles
    ) {
        if (distance(actual.eye, expectedEye) > 0.01
            || angleDistance(actual.yaw, expectedAngles[0]) > 0.01
            || Math.abs(actual.pitch - expectedAngles[1]) > 0.01) {
            throw new IllegalStateException("camera moved before screenshot; actual=" + actual);
        }
    }

    private static CameraState readCameraState() throws Exception {
        AtomicReference<CameraState> value = new AtomicReference<>();
        runOn(minecraft, () -> {
            Object camera = invoke(minecraft, "getCameraEntity");
            Object eye = invoke(camera, "getEyePosition");
            value.set(new CameraState(
                new double[] {
                    ((Number) publicField(eye, "x")).doubleValue(),
                    ((Number) publicField(eye, "y")).doubleValue(),
                    ((Number) publicField(eye, "z")).doubleValue()
                },
                ((Number) invoke(camera, "getYRot")).doubleValue(),
                ((Number) invoke(camera, "getXRot")).doubleValue()
            ));
        });
        return value.get();
    }

    private static ScreenshotResult grabScreenshot(String filename) throws Exception {
        CountDownLatch callbackLatch = new CountDownLatch(1);
        AtomicReference<String> callback = new AtomicReference<>();
        AtomicReference<Throwable> problem = new AtomicReference<>();
        runOn(minecraft, () -> {
            try {
                Class<?> screenshotClass = Class.forName(SCREENSHOT_CLASS);
                Method grab = findMethod(screenshotClass, "grab", 5);
                File gameDirectory = (File) publicField(minecraft, "gameDirectory");
                Object renderTarget = invoke(minecraft, "getMainRenderTarget");
                Consumer<Object> consumer = message -> {
                    callback.set(String.valueOf(message));
                    callbackLatch.countDown();
                };
                grab.invoke(null, gameDirectory, filename, renderTarget, 1, consumer);
            } catch (Throwable throwable) {
                problem.set(throwable);
                callbackLatch.countDown();
            }
        });
        if (!callbackLatch.await(longProperty("screenshot.timeout.seconds", 30L), TimeUnit.SECONDS)) {
            throw new IllegalStateException("screenshot callback timed out for " + filename);
        }
        if (problem.get() != null) {
            throw new IllegalStateException("screenshot invocation failed for " + filename, problem.get());
        }
        File gameDirectory = (File) publicField(minecraft, "gameDirectory");
        Path screenshotPath = gameDirectory.toPath().resolve("screenshots").resolve(filename);
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10L);
        while (System.nanoTime() < deadline && !Files.isRegularFile(screenshotPath)) {
            Thread.sleep(50L);
        }
        if (!Files.isRegularFile(screenshotPath) || Files.size(screenshotPath) == 0L) {
            throw new IllegalStateException("vanilla screenshot file was not written: " + screenshotPath);
        }
        return new ScreenshotResult(screenshotPath, callback.get());
    }

    private static void executeCommand(Object server, String command) throws Exception {
        Object commands = invoke(server, "getCommands");
        Object source = invoke(server, "createCommandSourceStack");
        Method perform = findMethod(commands.getClass(), "performPrefixedCommand", 2);
        perform.invoke(commands, source, command);
    }

    private static void setOption(Object options, String methodName, Object value) throws Exception {
        Object option = invoke(options, methodName);
        findMethod(option.getClass(), "set", 1).invoke(option, value);
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static void setMusicVolume(Object options, double volume) throws Exception {
        Class<?> soundSource = Class.forName("net.minecraft.sounds.SoundSource");
        Object music = Enum.valueOf((Class<? extends Enum>) soundSource, "MUSIC");
        Object option = options.getClass()
            .getMethod("getSoundSourceOptionInstance", soundSource)
            .invoke(options, music);
        findMethod(option.getClass(), "set", 1).invoke(option, volume);
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static void setEnumOption(
        Object options,
        String methodName,
        String enumClassName,
        String constant
    ) throws Exception {
        Class<?> enumClass = Class.forName(enumClassName);
        Object value = Enum.valueOf((Class<? extends Enum>) enumClass, constant);
        setOption(options, methodName, value);
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static void setPublicEnumField(
        Object target,
        String fieldName,
        String enumClassName,
        String constant
    ) throws Exception {
        Class<?> enumClass = Class.forName(enumClassName);
        Object value = Enum.valueOf((Class<? extends Enum>) enumClass, constant);
        setPublicField(target, fieldName, value);
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private static void setFirstPerson(Object options) throws Exception {
        Class<?> cameraType = Class.forName("net.minecraft.client.CameraType");
        Object firstPerson = Enum.valueOf((Class<? extends Enum>) cameraType, "FIRST_PERSON");
        options.getClass().getMethod("setCameraType", cameraType).invoke(options, firstPerson);
    }

    private static void ensureGameplayScreen(boolean suppressInput) throws Exception {
        for (int attempt = 0; attempt < 5; attempt++) {
            AtomicReference<Boolean> clear = new AtomicReference<>(false);
            runOn(minecraft, () -> {
                Object options = publicField(minecraft, "options");
                setPublicField(options, "pauseOnLostFocus", false);
                clearScreen(minecraft);
                if (suppressInput) {
                    suppressCaptureInputOnRenderThread(minecraft);
                }
            });
            Thread.sleep(350L);
            runOn(minecraft, () -> clear.set(publicField(minecraft, "screen") == null));
            if (Boolean.TRUE.equals(clear.get())) {
                return;
            }
        }
        throw new IllegalStateException("client screen could not be cleared before screenshot");
    }

    private static void suppressCaptureInput() throws Exception {
        runOn(minecraft, () -> suppressCaptureInputOnRenderThread(minecraft));
    }

    private static void suppressCaptureInputOnRenderThread(Object client) throws Exception {
        // setScreen(null) grabs the mouse and restores held key states. Capture
        // mode immediately reverses both effects, then installs vanilla's
        // public no-op ClientInput so physical keys cannot move the spectator.
        Object mouseHandler = publicField(client, "mouseHandler");
        invoke(mouseHandler, "releaseMouse");
        Class<?> keyMapping = Class.forName("net.minecraft.client.KeyMapping");
        keyMapping.getMethod("releaseAll").invoke(null);

        Object player = publicField(client, "player");
        Class<?> clientInput = Class.forName("net.minecraft.client.player.ClientInput");
        Object idleInput = clientInput.getConstructor().newInstance();
        setPublicField(player, "input", idleInput);
    }

    private static void assertCaptureInputIsIdleOnRenderThread() throws Exception {
        Object mouseHandler = publicField(minecraft, "mouseHandler");
        if (Boolean.TRUE.equals(invoke(mouseHandler, "isMouseGrabbed"))) {
            throw new IllegalStateException("capture input probe found the mouse grabbed");
        }

        Object player = publicField(minecraft, "player");
        Object input = publicField(player, "input");
        Class<?> clientInput = Class.forName("net.minecraft.client.player.ClientInput");
        if (input.getClass() != clientInput) {
            throw new IllegalStateException(
                "capture input probe found active input class " + input.getClass().getName()
            );
        }
        Object move = invoke(input, "getMoveVector");
        double sideways = ((Number) publicField(move, "x")).doubleValue();
        double forward = ((Number) publicField(move, "y")).doubleValue();
        Object presses = publicField(input, "keyPresses");
        Class<?> inputState = Class.forName("net.minecraft.world.entity.player.Input");
        Object empty = inputState.getField("EMPTY").get(null);
        if (sideways != 0.0D || forward != 0.0D || !empty.equals(presses)) {
            throw new IllegalStateException("capture input probe found non-idle ClientInput");
        }
    }

    private static void clearScreen(Object client) throws Exception {
        Class<?> screenClass = Class.forName("net.minecraft.client.gui.screens.Screen");
        client.getClass().getMethod("setScreen", screenClass).invoke(client, new Object[] {null});
    }

    private static void runOn(Object executorObject, ThrowingRunnable operation) throws Exception {
        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<Throwable> problem = new AtomicReference<>();
        Runnable task = () -> {
            try {
                operation.run();
            } catch (Throwable throwable) {
                problem.set(throwable);
            } finally {
                latch.countDown();
            }
        };
        if (executorObject instanceof Executor executor) {
            executor.execute(task);
        } else {
            executorObject.getClass().getMethod("execute", Runnable.class).invoke(executorObject, task);
        }
        if (!latch.await(30L, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Minecraft executor task timed out");
        }
        if (problem.get() != null) {
            throw new IllegalStateException("Minecraft executor task failed", problem.get());
        }
    }

    private static Object invoke(Object target, String methodName) throws Exception {
        return target.getClass().getMethod(methodName).invoke(target);
    }

    private static Object publicField(Object target, String fieldName) throws Exception {
        return target.getClass().getField(fieldName).get(target);
    }

    private static void setPublicField(Object target, String fieldName, Object value) throws Exception {
        Field field = target.getClass().getField(fieldName);
        field.set(target, value);
    }

    private static Method findMethod(Class<?> type, String name, int parameterCount) {
        for (Method method : type.getMethods()) {
            if (method.getName().equals(name) && method.getParameterCount() == parameterCount) {
                return method;
            }
        }
        throw new IllegalArgumentException(
            "public method not found: " + type.getName() + "." + name + "/" + parameterCount
        );
    }

    private static View readView(int index) {
        String prefix = "view." + index + ".";
        return new View(
            requiredProperty(prefix + "name"),
            parseVector(requiredProperty(prefix + "eye")),
            parseVector(requiredProperty(prefix + "target")),
            integerProperty(prefix + "fov", integerProperty("fov", 70))
        );
    }

    private static double[] parseVector(String value) {
        String[] parts = value.trim().split("\\s*,\\s*");
        if (parts.length != 3) {
            throw new IllegalArgumentException("expected three comma-separated coordinates: " + value);
        }
        return new double[] {
            Double.parseDouble(parts[0]),
            Double.parseDouble(parts[1]),
            Double.parseDouble(parts[2])
        };
    }

    static double[] minecraftAngles(double[] eye, double[] target) {
        double dx = target[0] - eye[0];
        double dy = target[1] - eye[1];
        double dz = target[2] - eye[2];
        double horizontal = Math.sqrt(dx * dx + dz * dz);
        if (horizontal < 1.0e-9 && Math.abs(dy) < 1.0e-9) {
            throw new IllegalArgumentException("camera eye and target must differ");
        }
        double yaw = Math.toDegrees(Math.atan2(-dx, dz));
        double pitch = Math.toDegrees(-Math.atan2(dy, horizontal));
        return new double[] {yaw, pitch};
    }

    private static double distance(double[] left, double[] right) {
        double dx = left[0] - right[0];
        double dy = left[1] - right[1];
        double dz = left[2] - right[2];
        return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }

    private static double angleDistance(double left, double right) {
        return Math.abs(((left - right + 540.0) % 360.0) - 180.0);
    }

    private static String sha256(Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (var input = Files.newInputStream(path)) {
            byte[] buffer = new byte[1024 * 1024];
            int read;
            while ((read = input.read(buffer)) >= 0) {
                digest.update(buffer, 0, read);
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private static void stopClient() throws Exception {
        if (minecraft != null) {
            runOn(minecraft, () -> invoke(minecraft, "stop"));
        }
    }

    private static void stopClientQuietly() {
        try {
            stopClient();
        } catch (Throwable ignored) {
            // The report already contains the primary failure.
        }
    }

    private static String requiredProperty(String name) {
        String value = configuration.getProperty(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("missing configuration property: " + name);
        }
        return value;
    }

    private static Path requiredPathProperty(String name) {
        String value = System.getProperty(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("missing system property: " + name);
        }
        return Path.of(value).toAbsolutePath().normalize();
    }

    private static Properties loadConfiguration(Path path) throws Exception {
        Properties loaded = new Properties();
        try (var reader = Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            loaded.load(reader);
        }
        return loaded;
    }

    private static long longProperty(String name, long defaultValue) {
        return Long.parseLong(configuration.getProperty(name, Long.toString(defaultValue)));
    }

    private static int integerProperty(String name, int defaultValue) {
        return Integer.parseInt(configuration.getProperty(name, Integer.toString(defaultValue)));
    }

    private static double doubleProperty(String name, double defaultValue) {
        return Double.parseDouble(configuration.getProperty(name, Double.toString(defaultValue)));
    }

    private static void writeReportQuietly() {
        try {
            writeReport();
        } catch (Throwable ignored) {
            // There is no safer output channel during client shutdown.
        }
    }

    private static void writeReport() throws Exception {
        if (reportPath == null) {
            return;
        }
        Files.createDirectories(reportPath.getParent());
        StringBuilder json = new StringBuilder();
        json.append("{\n");
        json.append("  \"format\": \"hill-chapel-native-qa-v1\",\n");
        json.append("  \"status\": ").append(quote(status)).append(",\n");
        json.append("  \"updated_at_utc\": ").append(quote(Instant.now().toString())).append(",\n");
        json.append("  \"minecraft_version\": ").append(quote("26.1.2")).append(",\n");
        json.append("  \"renderer\": \"native Minecraft client\",\n");
        json.append("  \"mode\": ")
            .append(quote(System.getProperty("chapel.qa.mode", "capture"))).append(",\n");
        json.append("  \"native_backup_requested\": ")
            .append(nativeBackupRequested).append(",\n");
        json.append("  \"conversion_completed\": ").append(conversionCompleted).append(",\n");
        json.append("  \"capture_input_probe_passed\": ")
            .append(captureInputProbePassed).append(",\n");
        json.append("  \"handled_known_screen_count\": ").append(HANDLED_SCREENS.size())
            .append(",\n");
        json.append("  \"handled_known_screens\": [");
        for (int index = 0; index < HANDLED_SCREENS.size(); index++) {
            if (index > 0) {
                json.append(", ");
            }
            json.append(quote(HANDLED_SCREENS.get(index)));
        }
        json.append("],\n");
        String expectedPack = configuration == null ? null : configuration.getProperty("resource.pack.id");
        json.append("  \"expected_resource_pack\": ")
            .append(expectedPack == null ? "null" : quote(expectedPack)).append(",\n");
        json.append("  \"active_resource_packs\": [");
        for (int index = 0; index < ACTIVE_RESOURCE_PACKS.size(); index++) {
            if (index > 0) {
                json.append(", ");
            }
            json.append(quote(ACTIVE_RESOURCE_PACKS.get(index)));
        }
        json.append("],\n");
        json.append("  \"failure\": ").append(failure == null ? "null" : quote(failure)).append(",\n");
        json.append("  \"views\": [");
        synchronized (RESULTS) {
            for (int index = 0; index < RESULTS.size(); index++) {
                if (index > 0) {
                    json.append(',');
                }
                json.append("\n").append(RESULTS.get(index).toJson("    "));
            }
        }
        if (!RESULTS.isEmpty()) {
            json.append("\n  ");
        }
        json.append("]\n}\n");
        Files.writeString(reportPath, json.toString(), StandardCharsets.UTF_8);
    }

    private static String vectorJson(double[] vector) {
        return String.format(Locale.ROOT, "[%.6f, %.6f, %.6f]", vector[0], vector[1], vector[2]);
    }

    private static String quote(String value) {
        StringBuilder escaped = new StringBuilder("\"");
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '\\' -> escaped.append("\\\\");
                case '"' -> escaped.append("\\\"");
                case '\n' -> escaped.append("\\n");
                case '\r' -> escaped.append("\\r");
                case '\t' -> escaped.append("\\t");
                default -> {
                    if (character < 0x20) {
                        escaped.append(String.format(Locale.ROOT, "\\u%04x", (int) character));
                    } else {
                        escaped.append(character);
                    }
                }
            }
        }
        return escaped.append('"').toString();
    }

    private static String stackTrace(Throwable throwable) {
        StringWriter writer = new StringWriter();
        throwable.printStackTrace(new PrintWriter(writer));
        return writer.toString();
    }

    @FunctionalInterface
    private interface ThrowingRunnable {
        void run() throws Exception;
    }

    private record View(String name, double[] eye, double[] target, int fov) {}

    private record CameraState(double[] eye, double yaw, double pitch) {
        @Override
        public String toString() {
            return "eye=" + vectorJson(eye) + ", yaw=" + yaw + ", pitch=" + pitch;
        }
    }

    private record ScreenshotResult(Path path, String callback) {}

    private record ViewResult(
        View view,
        double requestedYaw,
        double requestedPitch,
        double commandedFeetY,
        int actualFov,
        CameraState actual,
        Path screenshot,
        String callback,
        long bytes,
        String sha256,
        String capturedAt
    ) {
        String toJson(String indent) {
            return indent + "{\n"
                + indent + "  \"name\": " + quote(view.name) + ",\n"
                + indent + "  \"requested_eye\": " + vectorJson(view.eye) + ",\n"
                + indent + "  \"requested_target\": " + vectorJson(view.target) + ",\n"
                + indent + "  \"requested_yaw\": " + format(requestedYaw) + ",\n"
                + indent + "  \"requested_pitch\": " + format(requestedPitch) + ",\n"
                + indent + "  \"commanded_feet_y\": " + format(commandedFeetY) + ",\n"
                + indent + "  \"requested_fov\": " + view.fov + ",\n"
                + indent + "  \"actual_fov\": " + actualFov + ",\n"
                + indent + "  \"actual_eye\": " + vectorJson(actual.eye) + ",\n"
                + indent + "  \"actual_yaw\": " + format(actual.yaw) + ",\n"
                + indent + "  \"actual_pitch\": " + format(actual.pitch) + ",\n"
                + indent + "  \"screenshot\": " + quote(screenshot.toString()) + ",\n"
                + indent + "  \"bytes\": " + bytes + ",\n"
                + indent + "  \"sha256\": " + quote(sha256) + ",\n"
                + indent + "  \"callback\": " + (callback == null ? "null" : quote(callback)) + ",\n"
                + indent + "  \"captured_at_utc\": " + quote(capturedAt) + "\n"
                + indent + "}";
        }

        private static String format(double value) {
            return String.format(Locale.ROOT, "%.6f", value);
        }
    }
}
