import org.thehill.hill175.gallery.EntryGalleryPublisher;
import org.thehill.hill175.gallery.GalleryHttpServer;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.CountDownLatch;

/** Local website preview using the same HTTP routes as the plugin, without starting Minecraft. */
public class CampusSitePreview {
    public static void main(String[] args) throws Exception {
        Path root = Path.of(args.length > 0 ? args[0] : ".").toAbsolutePath();
        int port = args.length > 1 ? Integer.parseInt(args[1]) : 8788;
        var publisher = new EntryGalleryPublisher(root.resolve("runtime/campus-site/empty-gallery"), List.of());
        var server = new GalleryHttpServer(port, publisher, root.resolve("runtime/gallery-assets"), root.resolve("runtime/campus-site"));
        Runtime.getRuntime().addShutdownHook(new Thread(server::close));
        server.start();
        System.out.println("Hill campus: http://127.0.0.1:" + server.port());
        new CountDownLatch(1).await();
    }
}
