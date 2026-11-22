package org.thehill.hill175.download;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickEvent;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.function.Predicate;

public final class StudentMapDownloadService implements CommandExecutor, AutoCloseable {
    private static final String ROUTE = "/student-map/";
    private final Path source;
    private final Path stateDir;
    private final URI publicBase;
    private final int port;
    private final Predicate<Player> authenticated;
    private final MapDownloadTickets tickets;
    private final MapDownloadAudit audit;
    private final ThreadPoolExecutor httpWorkers = new ThreadPoolExecutor(4, 4, 0, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(32), task -> daemon(task, "hill175-map-http"), new ThreadPoolExecutor.AbortPolicy());
    private final ThreadPoolExecutor builders = new ThreadPoolExecutor(2, 2, 0, TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(64), task -> daemon(task, "hill175-map-build"), new ThreadPoolExecutor.AbortPolicy());
    private final ScheduledExecutorService housekeeping = Executors.newSingleThreadScheduledExecutor(task -> daemon(task, "hill175-map-cleanup"));
    private final Map<String, CompletableFuture<Artifact>> builds = new HashMap<>();
    private final Map<String, MapDownloadTickets.Ticket> issuedLinks = new HashMap<>();
    private final Set<Path> artifacts = new HashSet<>();
    private final Map<Path, Integer> inFlight = new HashMap<>();
    private HttpServer server;
    private boolean closed;

    public static Optional<StudentMapDownloadService> fromEnvironment(Path pluginData, Predicate<Player> authenticated) {
        String directory = System.getenv("HILL175_STUDENT_DOWNLOAD_EXPORT");
        String url = System.getenv("HILL175_STUDENT_DOWNLOAD_URL");
        if ((directory == null || directory.isBlank()) && (url == null || url.isBlank())) return Optional.empty();
        if (directory == null || directory.isBlank() || url == null || url.isBlank())
            throw new IllegalArgumentException("Configure both HILL175_STUDENT_DOWNLOAD_EXPORT and HILL175_STUDENT_DOWNLOAD_URL.");
        Path export = Path.of(directory);
        if (!export.isAbsolute()) throw new IllegalArgumentException("Prepared world export path must be absolute.");
        int port = Integer.parseInt(System.getenv().getOrDefault("HILL175_STUDENT_DOWNLOAD_PORT", "8791"));
        return Optional.of(new StudentMapDownloadService(export, pluginData.resolve("student-downloads"),
                URI.create(url), port, authenticated));
    }

    public StudentMapDownloadService(Path source, Path stateDir, URI publicBase, int port, Predicate<Player> authenticated) {
        if (!"https".equalsIgnoreCase(publicBase.getScheme()) || publicBase.getHost() == null
                || publicBase.getRawUserInfo() != null || publicBase.getRawQuery() != null || publicBase.getRawFragment() != null
                || !ROUTE.equals(publicBase.getRawPath()))
            throw new IllegalArgumentException("Public download URL must be HTTPS and end in /student-map/ without a query.");
        if (port < 0 || port > 65535) throw new IllegalArgumentException("Invalid download port.");
        this.source = source.toAbsolutePath().normalize();
        this.stateDir = stateDir.toAbsolutePath().normalize();
        this.publicBase = publicBase;
        this.port = port;
        this.authenticated = java.util.Objects.requireNonNull(authenticated);
        this.tickets = new MapDownloadTickets(this.stateDir.resolve("fingerprints.tsv"));
        this.audit = new MapDownloadAudit(this.stateDir.resolve("transfers.tsv"));
    }

    public synchronized void start() throws IOException {
        if (closed || server != null) throw new IllegalStateException("Download service already started or closed.");
        if (Files.isSymbolicLink(stateDir)) throw new IOException("Download state directory may not be a symlink.");
        Files.createDirectories(stateDir);
        privatePermissions(stateDir, true);
        try (DirectoryStream<Path> previous = Files.newDirectoryStream(stateDir, "prepared-map-*.zip")) {
            for (Path file : previous) {
                if (!Files.isSymbolicLink(file) && Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) Files.delete(file);
            }
        }
        if (Files.isSymbolicLink(source) || !Files.isRegularFile(source.resolve("level.dat"), LinkOption.NOFOLLOW_LINKS))
            throw new IOException("The prepared world export is missing or unsafe.");
        HttpServer created = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 32);
        created.createContext(ROUTE, this::handle);
        created.setExecutor(httpWorkers);
        created.start();
        server = created;
        housekeeping.scheduleAtFixedRate(this::cleanup, 1, 1, TimeUnit.MINUTES);
    }

    public synchronized int port() {
        return server == null ? port : server.getAddress().getPort();
    }

    @Override public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("Only players can request a map copy.");
            return true;
        }
        if (args.length != 0) {
            player.sendMessage("Usage: /download");
            return true;
        }
        if (!authenticated.test(player)) {
            player.sendMessage("Sign in before requesting a map copy.");
            return true;
        }
        try {
            MapDownloadTickets.Issue issued;
            synchronized (this) {
                if (closed || server == null) throw new IllegalStateException("Downloads are not available.");
                cleanup();
                issued = tickets.issue(player.getUniqueId(), Instant.now());
                if (issued.fresh()) {
                    MapDownloadTickets.Ticket ticket = issued.ticket();
                    try {
                        audit.append(Instant.now(), "ISSUED", ticket.player(), ticket.fingerprint(), "PENDING", 0);
                        CompletableFuture<Artifact> future = CompletableFuture.supplyAsync(() -> build(ticket), builders);
                        builds.put(ticket.token(), future);
                        issuedLinks.put(ticket.token(), ticket);
                        future.thenAccept(artifact -> { synchronized (StudentMapDownloadService.this) { artifacts.add(artifact.file()); } });
                    } catch (IOException | RejectedExecutionException failure) {
                        tickets.revoke(ticket.token());
                        throw failure;
                    }
                }
            }
            String url = publicBase.resolve(issued.ticket().token()).toString();
            player.sendMessage(Component.text("Your private map-copy link (15 minutes): ").append(
                    Component.text(url).clickEvent(ClickEvent.openUrl(url))));
            player.sendMessage("Keep the link private. Preparation may take a few minutes; refresh the page to check.");
        } catch (IOException | IllegalStateException | RejectedExecutionException failure) {
            player.sendMessage("Map downloads are unavailable right now. Try again later or ask staff.");
        }
        return true;
    }

    private Artifact build(MapDownloadTickets.Ticket ticket) {
        Path file = null;
        try {
            file = Files.createTempFile(stateDir, "prepared-map-", ".zip");
            privatePermissions(file, false);
            String mapDigest = new PreparedWorldArchive(source).build(file, ticket.fingerprint());
            audit.append(Instant.now(), "READY", ticket.player(), ticket.fingerprint(), mapDigest, 0);
            return new Artifact(file, mapDigest);
        } catch (IOException | RuntimeException failure) {
            tickets.revoke(ticket.token());
            if (file != null) try { Files.deleteIfExists(file); } catch (IOException ignored) { }
            try { audit.append(Instant.now(), "BUILD_FAILED", ticket.player(), ticket.fingerprint(), "PENDING", 0); }
            catch (IOException auditFailure) { failure.addSuppressed(auditFailure); }
            throw new IllegalStateException("Could not prepare map copy.", failure);
        }
    }

    private void handle(HttpExchange exchange) throws IOException {
        try (exchange) {
            exchange.getResponseHeaders().set("Cache-Control", "no-store, max-age=0");
            exchange.getResponseHeaders().set("Pragma", "no-cache");
            exchange.getResponseHeaders().set("Referrer-Policy", "no-referrer");
            exchange.getResponseHeaders().set("X-Content-Type-Options", "nosniff");
            exchange.getResponseHeaders().set("Content-Security-Policy", "default-src 'none'; style-src 'none'; base-uri 'none'; form-action 'none'");
            exchange.getResponseHeaders().set("X-Robots-Tag", "noindex, nofollow, noarchive");
            if (!"GET".equals(exchange.getRequestMethod())) { respond(exchange, 405, "Method not allowed."); return; }
            String path = exchange.getRequestURI().getRawPath();
            if (exchange.getRequestURI().getRawQuery() != null || path == null
                    || !path.matches("/student-map/[A-Za-z0-9_-]{43}(/archive)?")) {
                respond(exchange, 404, "Not found."); return;
            }
            String token = path.substring(ROUTE.length()).replace("/archive", "");
            MapDownloadTickets.Ticket ticket = tickets.lookup(token, Instant.now());
            if (ticket == null) { respond(exchange, 404, "Link unavailable or expired."); return; }
            CompletableFuture<Artifact> future;
            synchronized (this) { future = builds.get(token); }
            if (future == null || future.isCompletedExceptionally()) { respond(exchange, 503, "Map copy unavailable. Request another link in-game."); return; }
            if (!future.isDone()) { exchange.getResponseHeaders().set("Retry-After", "5"); respond(exchange, 503, "Map copy is being prepared. Refresh in a moment."); return; }
            if (!path.endsWith("/archive")) {
                exchange.getResponseHeaders().set("Content-Type", "text/html; charset=utf-8");
                respond(exchange, 200, "<!doctype html><html lang=\"en\"><meta name=\"referrer\" content=\"no-referrer\"><title>Hill map copy</title><p>Your private map copy expires in 15 minutes.</p><a href=\""
                        + token + "/archive\">Download your map (ZIP)</a><p>Keep this link private.</p></html>");
                return;
            }
            Artifact artifact = future.getNow(null);
            if (artifact == null || !Files.isRegularFile(artifact.file(), LinkOption.NOFOLLOW_LINKS)) {
                respond(exchange, 503, "Map copy unavailable."); return;
            }
            try {
                transfer(exchange, ticket, artifact);
            } catch (IOException unavailable) {
                if (!exchange.getResponseHeaders().containsKey("Content-Disposition"))
                    respond(exchange, 503, "Map copy unavailable.");
            }
        }
    }

    private void transfer(HttpExchange exchange, MapDownloadTickets.Ticket ticket, Artifact artifact) throws IOException {
        Path file = artifact.file();
        long sent = 0;
        boolean started = false;
        boolean expired = false;
        var deadline = housekeeping.schedule(exchange::close,
                Math.max(0, java.time.Duration.between(Instant.now(), ticket.expires()).toMillis()), TimeUnit.MILLISECONDS);
        synchronized (this) { inFlight.merge(file, 1, Integer::sum); }
        try (InputStream input = Files.newInputStream(file, LinkOption.NOFOLLOW_LINKS)) {
            if (tickets.lookup(ticket.token(), Instant.now()) == null) { respond(exchange, 404, "Link unavailable or expired."); return; }
            audit.append(Instant.now(), "STARTED", ticket.player(), ticket.fingerprint(), artifact.mapDigest(), 0);
            started = true;
            exchange.getResponseHeaders().set("Content-Type", "application/zip");
            exchange.getResponseHeaders().set("Content-Disposition", "attachment; filename=\"Hill-175-Campus.zip\"");
            exchange.sendResponseHeaders(200, Files.size(file));
            byte[] bytes = new byte[64 * 1024];
            int count;
            while ((count = input.read(bytes)) != -1) {
                if (tickets.lookup(ticket.token(), Instant.now()) == null) { expired = true; break; }
                exchange.getResponseBody().write(bytes, 0, count);
                sent += count;
            }
            if (expired) {
                audit.append(Instant.now(), "EXPIRED", ticket.player(), ticket.fingerprint(), artifact.mapDigest(), sent);
                return;
            }
            exchange.getResponseBody().flush();
            audit.append(Instant.now(), "COMPLETED", ticket.player(), ticket.fingerprint(), artifact.mapDigest(), sent);
        } catch (IOException failure) {
            if (started) {
                String outcome = Instant.now().isBefore(ticket.expires()) ? "DISCONNECTED" : "EXPIRED";
                try { audit.append(Instant.now(), outcome, ticket.player(), ticket.fingerprint(), artifact.mapDigest(), sent); }
                catch (IOException auditFailure) {
                    failure.addSuppressed(auditFailure);
                    System.getLogger(StudentMapDownloadService.class.getName()).log(System.Logger.Level.ERROR,
                            "Map transfer outcome could not be audited. Check protected transfer records and disk availability.");
                }
            }
            throw failure;
        } finally {
            deadline.cancel(false);
            synchronized (this) {
                inFlight.computeIfPresent(file, (ignored, count) -> count == 1 ? null : count - 1);
            }
        }
    }

    private static void respond(HttpExchange exchange, int status, String text) throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", exchange.getResponseHeaders().getFirst("Content-Type") == null
                ? "text/plain; charset=utf-8" : exchange.getResponseHeaders().getFirst("Content-Type"));
        exchange.sendResponseHeaders(status, data.length);
        exchange.getResponseBody().write(data);
    }

    private synchronized void cleanup() {
        Instant now = Instant.now();
        tickets.purge(now);
        issuedLinks.entrySet().removeIf(entry -> {
            MapDownloadTickets.Ticket ticket = entry.getValue();
            if (now.isBefore(ticket.expires())) return false;
            CompletableFuture<Artifact> future = builds.get(entry.getKey());
            Artifact artifact = future != null && future.isDone() && !future.isCompletedExceptionally() ? future.getNow(null) : null;
            try {
                audit.append(now, "LINK_EXPIRED", ticket.player(), ticket.fingerprint(),
                        artifact == null ? "PENDING" : artifact.mapDigest(), 0);
                return true;
            } catch (IOException unavailable) { return false; }
        });
        Set<Path> retained = new HashSet<>(inFlight.keySet());
        for (Map.Entry<String, CompletableFuture<Artifact>> entry : builds.entrySet()) {
            if (tickets.lookup(entry.getKey(), Instant.now()) == null && !issuedLinks.containsKey(entry.getKey())) {
                entry.getValue().thenAccept(artifact -> { try { Files.deleteIfExists(artifact.file()); } catch (IOException ignored) { } });
            } else if (entry.getValue().isDone() && !entry.getValue().isCompletedExceptionally()) {
                retained.add(entry.getValue().getNow(null).file());
            }
        }
        builds.keySet().removeIf(token -> tickets.lookup(token, Instant.now()) == null && !issuedLinks.containsKey(token));
        artifacts.removeIf(file -> {
            if (retained.contains(file)) return false;
            try { Files.deleteIfExists(file); return true; } catch (IOException ignored) { return false; }
        });
    }

    @Override public synchronized void close() {
        if (closed) return;
        closed = true;
        if (server != null) server.stop(1);
        httpWorkers.shutdownNow();
        housekeeping.shutdownNow();
        builders.shutdownNow();
        for (CompletableFuture<Artifact> future : builds.values()) future.thenAccept(artifact -> {
            try { Files.deleteIfExists(artifact.file()); } catch (IOException ignored) { }
        });
        builds.clear();
        issuedLinks.clear();
        for (Path file : artifacts) try { Files.deleteIfExists(file); } catch (IOException ignored) { }
        artifacts.clear();
    }

    private record Artifact(Path file, String mapDigest) { }

    static void privatePermissions(Path path, boolean directory) throws IOException {
        if (Files.getFileStore(path).supportsFileAttributeView("posix"))
            Files.setPosixFilePermissions(path, java.nio.file.attribute.PosixFilePermissions.fromString(directory ? "rwx------" : "rw-------"));
    }

    private static Thread daemon(Runnable task, String name) {
        Thread thread = new Thread(task, name);
        thread.setDaemon(true);
        return thread;
    }
}
